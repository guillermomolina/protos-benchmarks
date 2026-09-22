# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
# THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
# OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
# THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
# FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

"""Focal, Docker-free contract tests for the PERF010-A harness (config + source shape only).

These do not build images, run the container matrix, or invoke javac/java; that requires
Docker and is human-executed per this repository's human-executor mode.
"""

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runner/perf010a.py"
spec = importlib.util.spec_from_file_location("perf010a", MODULE_PATH)
perf010a = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(perf010a)


class Perf010aContractTest(unittest.TestCase):
    def test_static_contract(self):
        cfg = perf010a.validate()
        self.assertEqual("PERF010-A", cfg["perf_item"])
        self.assertEqual("PERF010", cfg["parent_perf_item"])
        self.assertEqual("PERF010A_ABLATION_1", cfg["slice"])
        self.assertTrue(cfg["diagnostic_claim"])
        self.assertEqual(
            "bc0471184bf6dbbf03d0c6b09ef7b9e28aede014", cfg["protos_revision"]
        )

    def test_experiment_matrix_matches_perf008_exactly(self):
        cfg = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        perf008_cfg = json.loads((ROOT / "config/perf008.json").read_text(encoding="utf-8"))
        self.assertEqual(perf008_cfg["controls"], cfg["controls"])
        self.assertEqual(10000, cfg["operation_count"])
        self.assertEqual(20, cfg["warmup_iterations"])
        self.assertEqual(100, cfg["steady_iterations"])
        self.assertEqual("10 ms", cfg["execution_sample_period"])
        self.assertEqual(4, len(cfg["controls"]))

    def test_two_variants_declared(self):
        cfg = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        self.assertEqual(["baseline", "ablation"], cfg["variants"])

    def test_external_baseline_not_silently_merged(self):
        # AGENTS.work/REPRODUCIBILITY.md forbids mixing revisions/hosts into one retained
        # evidence claim; the historical PERF004-A cross-language baseline pins a different
        # Protos revision and container base image, so it must be flagged, not blended.
        cfg = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        self.assertFalse(cfg["external_baseline"]["same_run_as_protos_measurement"])

    def test_ablation_patch_applies_to_exactly_the_three_declared_targets(self):
        cfg = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        targets = cfg["ablation_patch_targets"]
        self.assertEqual(3, len(targets))
        for target in targets:
            self.assertIn(f"--- a/{target}", patch_text)
            self.assertIn(f"+++ b/{target}", patch_text)
        # Exactly these three files, nothing else (a fourth "--- a/" would mean drift).
        self.assertEqual(3, patch_text.count("--- a/"))

    def test_ablation_patch_does_not_touch_the_bytecode_interpreter_or_lowering(self):
        cfg = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        self.assertNotIn("ProtosBytecodeRootNode.java", patch_text)
        self.assertNotIn("CanonicalToBytecodeLowerer.java", patch_text)
        self.assertNotIn("continueAt", patch_text)

    def test_ablation_patch_covers_both_wrap_call_sites(self):
        # The semantic wrapper is instantiated at two call sites in the pinned revision:
        # ProtosSourceCompiler.compileBytecode (top-level module root, runs once) and
        # ProtosBytecodeClosureExecutionPlan's constructor (closure/method activation root,
        # which is what all four PERF010-A workloads' 10,000-iteration hot loop actually
        # calls repeatedly). Patching only the former would leave the measured hot path
        # unchanged.
        cfg = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        self.assertIn("return helper.getCallTarget();", patch_text)
        self.assertIn("this.activationTarget = activationRoot.getCallTarget();", patch_text)

    def test_ablation_patch_widens_the_root_task_gate(self):
        # Without this, every root-task execution in the ablation build throws
        # IllegalArgumentException (ProtosRootTaskExecution.isProductionBytecodeRoot),
        # since compiled roots stop being ProtosSemanticBytecodeRootNode instances.
        cfg = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        self.assertIn("instanceof ProtosBytecodeRootNode", patch_text)
        self.assertIn("isProductionBytecodeRoot", patch_text)

    def test_timing_driver_never_imports_jfr(self):
        driver = (
            ROOT / "docker/protos-perf010a/Perf010aTimingDriver.java"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import jdk.jfr", driver)
        self.assertIn("steady_ns", driver)

    def test_dockerfile_builds_both_variants_from_one_source(self):
        dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG VARIANT=baseline", dockerfile)
        self.assertIn('if [ "$VARIANT" = "ablation" ]', dockerfile)
        self.assertIn("git apply --verbose /tmp/ablation.patch", dockerfile)
        self.assertIn("Perf010aTimingDriver.java", dockerfile)
        self.assertIn("Perf008SteadyStateDriver.java", dockerfile)

    def test_worktree_harness_revision_declares_exact_sha_or_precommit_sentinel(self):
        revision = perf010a.worktree_harness_revision()
        self.assertTrue(
            revision == "WORKTREE_PRECOMMIT" or re.fullmatch(r"[0-9a-f]{40}", revision),
            f"unexpected declared harness revision: {revision!r}",
        )

    def test_smoke_and_reference_are_top_level_commands(self):
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, completed.returncode)
        self.assertIn("{validate,smoke,reference}", completed.stdout)

    def test_reference_requires_output_dir(self):
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH), "reference"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("--output-dir", completed.stderr)

    def test_resolved_harness_revision_auto_detects_head(self):
        head = perf010a.output(["git", "rev-parse", "HEAD"])
        self.assertEqual(head, perf010a.resolved_harness_revision(None))

    def test_resolved_harness_revision_rejects_mismatched_explicit_sha(self):
        with self.assertRaises(RuntimeError):
            perf010a.resolved_harness_revision("0" * 40)

    def test_summarize_ns_matches_perf001f_reference_definitions(self):
        values = [10, 20, 30, 40, 100]
        summary = perf010a.summarize_ns(values)
        self.assertEqual(5, summary["samples"])
        self.assertEqual(30, summary["median_ns"])
        self.assertEqual(10, summary["mad_ns"])
        self.assertEqual(10, summary["min_ns"])
        self.assertEqual(100, summary["max_ns"])

    def test_summarize_ns_rejects_non_positive_samples(self):
        with self.assertRaises(ValueError):
            perf010a.summarize_ns([10, 0, 30])

    def test_marker_presence_detects_semantic_and_helper_markers(self):
        payload = {
            "execution_samples": {
                "top_frames": [
                    {
                        "name": (
                            "com.guillermomolina.protos.execution."
                            "ProtosSemanticBytecodeRootNodeGen$CachedBytecodeNode.continueAt"
                        ),
                        "count": 1,
                    }
                ],
                "call_paths": [],
            },
            "continue_at": {
                "callers": [],
                "callees": [
                    {
                        "name": (
                            "com.guillermomolina.protos.execution."
                            "ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt"
                        ),
                        "count": 1,
                    }
                ],
                "stacks": [],
            },
        }
        markers = perf010a.marker_presence(payload)
        self.assertTrue(markers["any_semantic_marker_present"])
        self.assertTrue(markers["helper_continue_at_present"])

    # --- PERF010A_ABLATION_2 (ProtosActivation.lookup) coverage ---

    def test_ablation2_static_contract(self):
        cfg = perf010a.validate("2")
        self.assertEqual("PERF010-A", cfg["perf_item"])
        self.assertEqual("PERF010", cfg["parent_perf_item"])
        self.assertEqual("PERF010A_ABLATION_2", cfg["slice"])
        self.assertTrue(cfg["diagnostic_claim"])
        self.assertEqual(
            "bc0471184bf6dbbf03d0c6b09ef7b9e28aede014", cfg["protos_revision"]
        )

    def test_ablation2_experiment_matrix_matches_ablation1_exactly(self):
        cfg1 = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        cfg2 = json.loads((ROOT / "config/perf010a-2.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg1["controls"], cfg2["controls"])
        self.assertEqual(cfg1["operation_count"], cfg2["operation_count"])
        self.assertEqual(cfg1["warmup_iterations"], cfg2["warmup_iterations"])
        self.assertEqual(cfg1["steady_iterations"], cfg2["steady_iterations"])
        self.assertEqual(cfg1["execution_sample_period"], cfg2["execution_sample_period"])
        self.assertEqual(cfg1["variants"], cfg2["variants"])
        self.assertEqual(cfg1["protos_revision"], cfg2["protos_revision"])
        self.assertEqual(cfg1["toolchain"], cfg2["toolchain"])

    def test_ablation2_patch_touches_exactly_lookup_perform(self):
        cfg = json.loads((ROOT / "config/perf010a-2.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        targets = cfg["ablation_patch_targets"]
        self.assertEqual(1, len(targets))
        self.assertEqual(
            "src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeRootNode.java",
            targets[0],
        )
        self.assertEqual(1, patch_text.count("--- a/"))
        self.assertIn("activation.context().readLocalSlot(name)", patch_text)

    def test_ablation2_patch_does_not_touch_other_production_mechanisms(self):
        cfg = json.loads((ROOT / "config/perf010a-2.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        for forbidden in (
            "CanonicalToBytecodeLowerer.java",
            "ProtosSourceCompiler.java",
            "ProtosBytecodeClosureExecutionPlan.java",
            "ProtosRootTaskExecution.java",
            "continueAt",
            "RootTag",
            "ContinuationResult",
            "ProtosSemanticBytecodeRootNode",
        ):
            self.assertNotIn(forbidden, patch_text, forbidden)

    def test_ablation2_dockerfile_supports_selectable_patch(self):
        dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG ABLATION_PATCH=ablation.patch", dockerfile)
        self.assertIn("${ABLATION_PATCH}", dockerfile)
        self.assertIn("ablation-slice.txt", dockerfile)

    def test_marker_presence_detects_lookup_marker(self):
        payload = {
            "execution_samples": {
                "top_frames": [
                    {
                        "name": (
                            "com.guillermomolina.protos.runtime."
                            "ProtosActivation.lookup"
                        ),
                        "count": 1,
                    }
                ],
                "call_paths": [],
            },
            "continue_at": {
                "callers": [],
                "callees": [
                    {
                        "name": (
                            "com.guillermomolina.protos.runtime."
                            "ProtosObjectValue.readLocalSlot"
                        ),
                        "count": 1,
                    }
                ],
                "stacks": [],
            },
        }
        markers = perf010a.marker_presence(
            payload, perf010a.LOOKUP_MARKERS, perf010a.READ_LOCAL_SLOT_MARKER
        )
        self.assertTrue(markers["any_semantic_marker_present"])
        self.assertTrue(markers["helper_continue_at_present"])

    def test_marker_presence_absent_in_pure_ablation2_profile(self):
        payload = {
            "execution_samples": {
                "top_frames": [
                    {
                        "name": (
                            "com.guillermomolina.protos.runtime."
                            "ProtosObjectValue.readLocalSlot"
                        ),
                        "count": 1,
                    }
                ],
                "call_paths": [],
            },
            "continue_at": {"callers": [], "callees": [], "stacks": []},
        }
        markers = perf010a.marker_presence(
            payload, perf010a.LOOKUP_MARKERS, perf010a.READ_LOCAL_SLOT_MARKER
        )
        self.assertFalse(markers["any_semantic_marker_present"])
        self.assertTrue(markers["helper_continue_at_present"])

    def test_marker_presence_absent_in_pure_ablation_profile(self):
        payload = {
            "execution_samples": {
                "top_frames": [
                    {
                        "name": (
                            "com.guillermomolina.protos.execution."
                            "ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt"
                        ),
                        "count": 1,
                    }
                ],
                "call_paths": [],
            },
            "continue_at": {"callers": [], "callees": [], "stacks": []},
        }
        markers = perf010a.marker_presence(payload)
        self.assertFalse(markers["any_semantic_marker_present"])
        self.assertTrue(markers["helper_continue_at_present"])

    def test_classify_workload_records_ablation_execution_failure_without_crashing(self):
        # Observed in practice for PERF010A_ABLATION_2: the diagnostic bypass fails closed
        # inside Core prelude bootstrap itself (before any workload code runs), so every
        # ablation-variant (mode) combination fails at the `timing` stage. classify_workload
        # must record this per this slice's fail-closed contract, not raise/crash.
        def cell(execution_failure=None, median_ns=None, marker_present=None):
            return {
                "timing": (
                    None
                    if execution_failure
                    else {"steady_summary": {"median_ns": median_ns}}
                ),
                "structural": (
                    None
                    if execution_failure
                    else {
                        "markers": {
                            "any_semantic_marker_present": marker_present,
                            "helper_continue_at_present": True,
                        }
                    }
                ),
                "execution_failure": execution_failure,
            }

        entry = {
            "workload": "micro/slot-read",
            "variants": {
                "baseline": {
                    "canonical": cell(median_ns=1000, marker_present=True),
                    "control": cell(median_ns=100, marker_present=True),
                },
                "ablation": {
                    "canonical": cell(
                        execution_failure={"stage": "timing", "detail": "boom"}
                    ),
                    "control": cell(
                        execution_failure={"stage": "timing", "detail": "boom"}
                    ),
                },
            },
        }
        classification = perf010a.classify_workload(entry, "2")
        self.assertFalse(classification["correctness_confirmed"])
        self.assertFalse(classification["structural_ablation_confirmed"])
        self.assertEqual("INVALID", classification["perf010a_ablation_2"])
        self.assertIsNone(classification["protos_ablation_steady_median_ns"])
        self.assertIsNone(classification["removed_ns"])
        self.assertIsNone(classification["removed_fraction_of_baseline"])
        self.assertEqual(1000, classification["protos_baseline_steady_median_ns"])
        self.assertEqual({"canonical", "control"}, set(classification["execution_failures"]))

    # --- smoke cost boundary (must stay far cheaper than reference scale) ---

    def test_smoke_scale_is_far_smaller_than_any_reference_scale(self):
        for ablation in perf010a.ABLATIONS:
            cfg = perf010a.validate(ablation)
            self.assertLess(
                perf010a.SMOKE_WARMUP_ITERATIONS, cfg["warmup_iterations"], ablation
            )
            self.assertLess(
                perf010a.SMOKE_STEADY_ITERATIONS, cfg["steady_iterations"], ablation
            )

    def test_run_matrix_defaults_to_reference_scale_when_unspecified(self):
        # run_matrix's warmup/steady default (None -> cfg's own reference-scale values) must
        # stay reference's behavior; only smoke() is allowed to override it to SMOKE_* scale.
        import inspect
        sig = inspect.signature(perf010a.run_matrix)
        self.assertIsNone(sig.parameters["warmup"].default)
        self.assertIsNone(sig.parameters["steady"].default)
        self.assertTrue(sig.parameters["collect_structural"].default)

    # --- PERF010A_ABLATION_3 (ProtosObjectValue.readLocalSlot) coverage ---

    def test_ablation3_static_contract(self):
        cfg = perf010a.validate("3")
        self.assertEqual("PERF010-A", cfg["perf_item"])
        self.assertEqual("PERF010", cfg["parent_perf_item"])
        self.assertEqual("PERF010A_ABLATION_3", cfg["slice"])
        self.assertTrue(cfg["diagnostic_claim"])
        self.assertEqual(
            "6e7d89194925ba9fa2cd9c5c45aefa72d9939621", cfg["protos_revision"]
        )

    def test_ablation3_pinned_revision_differs_from_ablation1_and_2_deliberately(self):
        cfg1 = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        cfg3 = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        self.assertNotEqual(cfg1["protos_revision"], cfg3["protos_revision"])
        self.assertIn("protos_revision_note", cfg3)

    def test_ablation3_experiment_matrix_matches_ablation1_exactly(self):
        cfg1 = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        cfg3 = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg1["controls"], cfg3["controls"])
        self.assertEqual(cfg1["operation_count"], cfg3["operation_count"])
        self.assertEqual(cfg1["warmup_iterations"], cfg3["warmup_iterations"])
        self.assertEqual(cfg1["steady_iterations"], cfg3["steady_iterations"])
        self.assertEqual(cfg1["execution_sample_period"], cfg3["execution_sample_period"])
        self.assertEqual(cfg1["variants"], cfg3["variants"])
        self.assertEqual(cfg1["toolchain"], cfg3["toolchain"])

    def test_ablation3_patch_touches_exactly_read_local_slot(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        targets = cfg["ablation_patch_targets"]
        self.assertEqual(1, len(targets))
        self.assertEqual(
            "src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java",
            targets[0],
        )
        self.assertEqual(1, patch_text.count("--- a/"))

    def test_ablation3_patch_removes_redundant_contains_key_and_get(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        self.assertIn("-        return localSlots.containsKey(name)", patch_text)
        self.assertIn("-                ? Optional.of(localSlots.get(name))", patch_text)
        self.assertIn("+        Object value = localSlots.get(name);", patch_text)
        self.assertIn("+        return value != null ? Optional.of(value) : Optional.empty();", patch_text)

    def test_ablation3_patch_does_not_touch_lexical_traversal_or_other_mechanisms(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        for forbidden in (
            "ProtosActivation.java",
            "ProtosBytecodeRootNode.java",
            "CanonicalToBytecodeLowerer.java",
            "capturedLexicalContexts",
            "continueAt",
            "RootTag",
            "ContinuationResult",
            "ProtosSemanticBytecodeRootNode",
        ):
            self.assertNotIn(forbidden, patch_text, forbidden)

    def test_ablation3_patch_carries_the_diagnostic_marker_comment(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        self.assertIn("PERF010A_ABLATION_3", patch_text)

    def test_ablation3_dockerfile_supports_selectable_patch(self):
        dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG ABLATION_PATCH=ablation.patch", dockerfile)
        self.assertIn("${ABLATION_PATCH}", dockerfile)
        self.assertIn("/opt/protos-source", dockerfile)

    def test_ablation3_image_identity_distinct_from_1_and_2(self):
        self.assertEqual(("1", "2", "3"), perf010a.ABLATIONS)
        cfg1 = perf010a.load(perf010a.CONFIG)
        cfg2 = perf010a.load(perf010a.CONFIG_2)
        cfg3 = perf010a.load(perf010a.CONFIG_3)
        self.assertEqual(
            {"PERF010A_ABLATION_1", "PERF010A_ABLATION_2", "PERF010A_ABLATION_3"},
            {cfg1["slice"], cfg2["slice"], cfg3["slice"]},
        )

    def test_extract_method_body_scopes_to_the_target_method_only(self):
        source = (
            "class X {\n"
            "    boolean hasLocalSlot(String name) {\n"
            "        return localSlots.containsKey(name);\n"
            "    }\n"
            "\n"
            "    public Optional<Object> readLocalSlot(String name) {\n"
            "        Object value = localSlots.get(name);\n"
            "        return value != null ? Optional.of(value) : Optional.empty();\n"
            "    }\n"
            "}\n"
        )
        body = perf010a._extract_method_body(source, perf010a.READ_LOCAL_SLOT_SIGNATURE)
        self.assertNotIn("containsKey", body)
        self.assertIn("localSlots.get(name)", body)

    def test_source_structural_markers_true_for_ablated_method_body(self):
        ablated_source = (
            "public Optional<Object> readLocalSlot(String name) {\n"
            "        Objects.requireNonNull(name, \"name\");\n"
            "        // PERF010A_ABLATION_3 diagnostic transformation\n"
            "        Object value = localSlots.get(name);\n"
            "        return value != null ? Optional.of(value) : Optional.empty();\n"
            "    }\n"
        )
        body = perf010a._extract_method_body(
            "class X {\n    " + ablated_source + "}\n", perf010a.READ_LOCAL_SLOT_SIGNATURE
        )
        self.assertIn(perf010a.ABLATION_3_MARKER_COMMENT, body)
        self.assertNotIn("containsKey", body)
        self.assertEqual(1, body.count(".get(name)"))

    def test_source_structural_markers_false_for_unmodified_baseline_method_body(self):
        baseline_source = (
            "public Optional<Object> readLocalSlot(String name) {\n"
            "        Objects.requireNonNull(name, \"name\");\n"
            "        return localSlots.containsKey(name)\n"
            "                ? Optional.of(localSlots.get(name))\n"
            "                : Optional.empty();\n"
            "    }\n"
        )
        body = perf010a._extract_method_body(
            "class X {\n    " + baseline_source + "}\n", perf010a.READ_LOCAL_SLOT_SIGNATURE
        )
        self.assertNotIn(perf010a.ABLATION_3_MARKER_COMMENT, body)
        self.assertIn("containsKey", body)

    def test_classify_workload_ablation3_uses_source_markers_not_jfr(self):
        def cell(median_ns):
            return {
                "timing": {"steady_summary": {"median_ns": median_ns}},
                "structural": None,
                "execution_failure": None,
            }

        entry = {
            "workload": "micro/slot-read",
            "variants": {
                "baseline": {
                    "canonical": cell(1000),
                    "control": cell(100),
                },
                "ablation": {
                    "canonical": cell(700),
                    "control": cell(100),
                },
            },
        }
        source_markers = {
            "baseline": {
                "marker_present": False,
                "contains_key_absent": False,
                "single_get_present": False,
                "captured_lexical_traversal_present": True,
            },
            "ablation": {
                "marker_present": True,
                "contains_key_absent": True,
                "single_get_present": True,
                "captured_lexical_traversal_present": True,
            },
        }
        classification = perf010a.classify_workload(entry, "3", source_markers)
        self.assertTrue(classification["correctness_confirmed"])
        self.assertTrue(classification["structural_ablation_confirmed"])
        self.assertEqual("VALID", classification["perf010a_ablation_3"])
        self.assertEqual(300, classification["removed_ns"])

    def test_classify_workload_ablation3_without_source_markers_is_invalid(self):
        def cell(median_ns):
            return {
                "timing": {"steady_summary": {"median_ns": median_ns}},
                "structural": None,
                "execution_failure": None,
            }

        entry = {
            "workload": "micro/slot-read",
            "variants": {
                "baseline": {"canonical": cell(1000), "control": cell(100)},
                "ablation": {"canonical": cell(700), "control": cell(100)},
            },
        }
        classification = perf010a.classify_workload(entry, "3", None)
        self.assertFalse(classification["structural_ablation_confirmed"])
        self.assertEqual("INVALID", classification["perf010a_ablation_3"])

    def test_classify_workload_ablation3_baseline_still_showing_ablation_marker_is_invalid(self):
        # If the "baseline" image's source somehow already carries the ablation marker/
        # single-get pattern, the source-marker check cannot distinguish baseline from
        # ablation, so it must not be confirmed VALID.
        def cell(median_ns):
            return {
                "timing": {"steady_summary": {"median_ns": median_ns}},
                "structural": None,
                "execution_failure": None,
            }

        entry = {
            "workload": "micro/slot-read",
            "variants": {
                "baseline": {"canonical": cell(1000), "control": cell(100)},
                "ablation": {"canonical": cell(700), "control": cell(100)},
            },
        }
        source_markers = {
            "baseline": {
                "marker_present": True,
                "contains_key_absent": True,
                "single_get_present": True,
                "captured_lexical_traversal_present": True,
            },
            "ablation": {
                "marker_present": True,
                "contains_key_absent": True,
                "single_get_present": True,
                "captured_lexical_traversal_present": True,
            },
        }
        classification = perf010a.classify_workload(entry, "3", source_markers)
        self.assertFalse(classification["structural_ablation_confirmed"])
        self.assertEqual("INVALID", classification["perf010a_ablation_3"])


if __name__ == "__main__":
    unittest.main()
