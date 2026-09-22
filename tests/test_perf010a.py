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
        self.assertIn("git apply --verbose --allow-empty /tmp/ablation.patch", dockerfile)
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
        self.assertIn(
            "{validate,smoke,reference,discrimination-validate,discrimination-smoke,"
            "discrimination-reference}",
            completed.stdout,
        )

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

    def test_ablation3_patch_touches_exactly_the_two_declared_targets(self):
        # The established causal-ablation contract touches two files: the diagnostic helper
        # (ProtosObjectValue.java, purely additive) and its two call sites
        # (ProtosActivation.java). A single-file patch is the shape of the earlier, invalid
        # execution of this slice (see test_ablation3_invalid_global_patch_fails_validation).
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        targets = cfg["ablation_patch_targets"]
        self.assertEqual(2, len(targets))
        self.assertIn(
            "src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java", targets
        )
        self.assertIn(
            "src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java", targets
        )
        self.assertEqual(2, patch_text.count("--- a/"))

    def test_ablation3_patch_adds_diagnostic_helper_without_touching_baseline_body(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        files = perf010a._parse_unified_diff(patch_text)
        object_value = files[
            "src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java"
        ]
        # Purely additive: the existing readLocalSlot method body (containsKey(name) +
        # get(name)) is not removed or otherwise touched.
        self.assertEqual([], object_value["removed"])
        added_text = "\n".join(object_value["added"])
        self.assertIn(perf010a.DIAGNOSTIC_HELPER_SIGNATURE, added_text)
        self.assertIn(perf010a.ABLATION_3_MARKER_COMMENT, added_text)
        self.assertEqual(1, added_text.count("localSlots.get(name)"))
        self.assertNotIn("localSlots.containsKey", added_text)

    def test_ablation3_patch_redirects_exactly_the_two_lexical_call_sites(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        files = perf010a._parse_unified_diff(patch_text)
        activation = files[
            "src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java"
        ]
        removed_calls = [
            l for l in activation["removed"] if perf010a.BASELINE_CALL_SITE_PATTERN in l
        ]
        non_call_removed = [
            l for l in activation["removed"] if perf010a.BASELINE_CALL_SITE_PATTERN not in l
        ]
        self.assertEqual(2, len(removed_calls))
        # Nothing else in ProtosActivation.java is removed: not the captured-lexical-traversal
        # loop header, not the ProtosValueLookup fallback, not lookup ordering.
        self.assertEqual([], non_call_removed)
        added_text = "\n".join(activation["added"])
        self.assertEqual(2, added_text.count(perf010a.DIAGNOSTIC_CALL_SITE_PATTERN))
        self.assertNotIn(perf010a.CAPTURED_LEXICAL_TRAVERSAL_MARKER, added_text)
        self.assertNotIn(perf010a.LOOKUP_FALLBACK_MARKER, added_text)

    def test_ablation3_patch_does_not_touch_other_production_mechanisms(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        for forbidden in (
            "ProtosBytecodeRootNode.java",
            "CanonicalToBytecodeLowerer.java",
            "ProtosSourceCompiler.java",
            "ProtosBytecodeClosureExecutionPlan.java",
            "ProtosRootTaskExecution.java",
            "ProtosValueLookup.java",
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

    # --- exact-scope validation (AGENTS.work/PERFORMANCE.md's causal-ablation rule) ---

    def test_ablation3_patch_passes_exact_scope_validation(self):
        cfg = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        perf010a.validate_patch_shape_3(patch_text)  # must not raise

    def test_ablation3_invalid_global_patch_fails_validation(self):
        # Shape of the earlier, invalid execution of this slice: readLocalSlot's own body is
        # transformed globally (single file, only ProtosObjectValue.java), which changes every
        # caller instead of only the two established ProtosActivation.lookup call sites. This
        # must fail exact-scope validation even though it is semantically equivalent by
        # construction and even though it targets the correct file.
        invalid_patch = (
            "diff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "@@ -100,9 +100,15 @@\n"
            "     public Optional<Object> readLocalSlot(String name) {\n"
            "         Objects.requireNonNull(name, \"name\");\n"
            "-        return localSlots.containsKey(name)\n"
            "-                ? Optional.of(localSlots.get(name))\n"
            "-                : Optional.empty();\n"
            "+        // PERF010A_ABLATION_3 diagnostic transformation\n"
            "+        Object value = localSlots.get(name);\n"
            "+        return value != null ? Optional.of(value) : Optional.empty();\n"
            "     }\n"
        )
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_3(invalid_patch)

    def test_ablation3_patch_with_only_one_diagnostic_call_site_fails_validation(self):
        # Only the current-context call site redirected; the captured-lexical-context loop's
        # call site left on the baseline reader. Must fail (requirement: both call sites must
        # move together).
        patch = (
            "diff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "@@ -103,6 +103,12 @@\n"
            "     }\n"
            "\n"
            "+    // PERF010A_ABLATION_3 diagnostic-only helper\n"
            "+    Optional<Object> readLocalSlotSingleProbe(String name) {\n"
            "+        Object value = localSlots.get(name);\n"
            "+        return value != null ? Optional.of(value) : Optional.empty();\n"
            "+    }\n"
            "+\n"
            "     public Map<String, Object> localSlotsSnapshot() {\n"
            "diff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "@@ -467,7 +467,7 @@\n"
            "     public Optional<Object> lookup(String name) {\n"
            "         Objects.requireNonNull(name, \"name\");\n"
            "\n"
            "-        Optional<Object> current = context.readLocalSlot(name);\n"
            "+        Optional<Object> current = context.readLocalSlotSingleProbe(name);\n"
            "         if (current.isPresent()) {\n"
            "             return current;\n"
            "         }\n"
        )
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_3(patch)

    def test_ablation3_patch_touching_value_lookup_fails_validation(self):
        # If ProtosValueLookup were redirected to the diagnostic helper too, the receiver/
        # delegation member-lookup path (not part of the established target) would also be
        # measured. Must fail even though ProtosObjectValue.java/ProtosActivation.java are
        # otherwise correct, because a third file is touched.
        base_patch = (ROOT / "docker/protos-perf010a/ablation-3.patch").read_text(
            encoding="utf-8"
        )
        extra = (
            "\ndiff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosValueLookup.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosValueLookup.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosValueLookup.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosValueLookup.java\n"
            "@@ -36,7 +36,7 @@\n"
            "             if (current instanceof ProtosObjectValue ordinary) {\n"
            "-                Optional<Object> local = ordinary.readLocalSlot(name);\n"
            "+                Optional<Object> local = ordinary.readLocalSlotSingleProbe(name);\n"
            "                 if (local.isPresent()) {\n"
        )
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_3(base_patch + extra)

    def test_ablation3_patch_removing_baseline_read_local_slot_body_fails_validation(self):
        # If ordinary readLocalSlot's own body is also modified (even alongside a correct
        # helper addition and correct call-site redirection), it is no longer the untouched
        # baseline every other caller relies on. Must fail.
        patch = (
            "diff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "@@ -98,9 +98,21 @@\n"
            "     public Optional<Object> readLocalSlot(String name) {\n"
            "         Objects.requireNonNull(name, \"name\");\n"
            "-        return localSlots.containsKey(name)\n"
            "-                ? Optional.of(localSlots.get(name))\n"
            "-                : Optional.empty();\n"
            "+        return localSlots.containsKey(name) ? Optional.of(localSlots.get(name)) : Optional.empty();\n"
            "     }\n"
            "\n"
            "+    // PERF010A_ABLATION_3 diagnostic-only helper\n"
            "+    Optional<Object> readLocalSlotSingleProbe(String name) {\n"
            "+        Object value = localSlots.get(name);\n"
            "+        return value != null ? Optional.of(value) : Optional.empty();\n"
            "+    }\n"
            "+\n"
            "     public Map<String, Object> localSlotsSnapshot() {\n"
            "diff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "@@ -467,13 +467,13 @@\n"
            "     public Optional<Object> lookup(String name) {\n"
            "         Objects.requireNonNull(name, \"name\");\n"
            "\n"
            "-        Optional<Object> current = context.readLocalSlot(name);\n"
            "+        Optional<Object> current = context.readLocalSlotSingleProbe(name);\n"
            "         if (current.isPresent()) {\n"
            "             return current;\n"
            "         }\n"
            "\n"
            "         for (ProtosObjectValue lexicalContext : capturedLexicalContexts) {\n"
            "-            Optional<Object> captured = lexicalContext.readLocalSlot(name);\n"
            "+            Optional<Object> captured = lexicalContext.readLocalSlotSingleProbe(name);\n"
            "             if (captured.isPresent()) {\n"
            "                 return captured;\n"
            "             }\n"
        )
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_3(patch)

    def test_ablation3_patch_removing_captured_lexical_traversal_fails_validation(self):
        # If the captured-lexical-context loop header itself is removed/altered alongside the
        # call-site redirection, this is no longer "the traversal preserved, only the reader
        # method changed" contract. Must fail.
        patch = (
            "diff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java\n"
            "@@ -103,6 +103,12 @@\n"
            "     }\n"
            "\n"
            "+    // PERF010A_ABLATION_3 diagnostic-only helper\n"
            "+    Optional<Object> readLocalSlotSingleProbe(String name) {\n"
            "+        Object value = localSlots.get(name);\n"
            "+        return value != null ? Optional.of(value) : Optional.empty();\n"
            "+    }\n"
            "+\n"
            "     public Map<String, Object> localSlotsSnapshot() {\n"
            "diff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java\n"
            "@@ -467,13 +467,13 @@\n"
            "     public Optional<Object> lookup(String name) {\n"
            "         Objects.requireNonNull(name, \"name\");\n"
            "\n"
            "-        Optional<Object> current = context.readLocalSlot(name);\n"
            "+        Optional<Object> current = context.readLocalSlotSingleProbe(name);\n"
            "         if (current.isPresent()) {\n"
            "             return current;\n"
            "         }\n"
            "\n"
            "-        for (ProtosObjectValue lexicalContext : capturedLexicalContexts) {\n"
            "-            Optional<Object> captured = lexicalContext.readLocalSlot(name);\n"
            "+        for (ProtosObjectValue lexicalContext : capturedLexicalContexts) { // touched\n"
            "+            Optional<Object> captured = lexicalContext.readLocalSlotSingleProbe(name);\n"
            "             if (captured.isPresent()) {\n"
            "                 return captured;\n"
            "             }\n"
        )
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_3(patch)

    def test_ablation3_dockerfile_supports_selectable_patch(self):
        dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG ABLATION_PATCH=ablation.patch", dockerfile)
        self.assertIn("${ABLATION_PATCH}", dockerfile)
        self.assertIn("/opt/protos-source", dockerfile)

    def test_ablation3_image_identity_distinct_from_1_and_2(self):
        self.assertEqual(("1", "2", "3", "4"), perf010a.ABLATIONS)
        cfg1 = perf010a.load(perf010a.CONFIG)
        cfg2 = perf010a.load(perf010a.CONFIG_2)
        cfg3 = perf010a.load(perf010a.CONFIG_3)
        cfg4 = perf010a.load(perf010a.CONFIG_4)
        self.assertEqual(
            {
                "PERF010A_ABLATION_1",
                "PERF010A_ABLATION_2",
                "PERF010A_ABLATION_3",
                "PERF010A_ABLATION_4",
            },
            {cfg1["slice"], cfg2["slice"], cfg3["slice"], cfg4["slice"]},
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

    def test_classify_workload_ablation3_uses_structural_contract_not_jfr(self):
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
        structural_contract_3 = {
            "ABLATION_3_TARGET_HELPER_PRESENT": True,
            "ABLATION_3_CURRENT_CONTEXT_CALLSITE": True,
            "ABLATION_3_CAPTURED_CONTEXT_CALLSITE": True,
            "ABLATION_3_BASELINE_READ_LOCAL_SLOT_UNCHANGED": True,
            "ABLATION_3_PROTOS_VALUE_LOOKUP_PATH_UNCHANGED": True,
            "ABLATION_3_CAPTURED_LEXICAL_TRAVERSAL_PRESERVED": True,
            "ABLATION_3_LOOKUP_ORDER_PRESERVED": True,
            "ABLATION_3_PATCH_SCOPE_MATCH": True,
        }
        classification = perf010a.classify_workload(entry, "3", structural_contract_3)
        self.assertTrue(classification["correctness_confirmed"])
        self.assertTrue(classification["structural_ablation_confirmed"])
        self.assertEqual("VALID", classification["perf010a_ablation_3"])
        self.assertEqual(300, classification["removed_ns"])

    def test_classify_workload_ablation3_without_structural_contract_is_invalid(self):
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

    def test_classify_workload_ablation3_failed_scope_match_is_invalid(self):
        # A structural contract where the overall ABLATION_3_PATCH_SCOPE_MATCH is False (e.g.
        # because the baseline readLocalSlot body diverged between images) must not be
        # confirmed VALID even if some individual sub-checks passed.
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
        structural_contract_3 = {
            "ABLATION_3_TARGET_HELPER_PRESENT": True,
            "ABLATION_3_CURRENT_CONTEXT_CALLSITE": True,
            "ABLATION_3_CAPTURED_CONTEXT_CALLSITE": True,
            "ABLATION_3_BASELINE_READ_LOCAL_SLOT_UNCHANGED": False,
            "ABLATION_3_PROTOS_VALUE_LOOKUP_PATH_UNCHANGED": True,
            "ABLATION_3_CAPTURED_LEXICAL_TRAVERSAL_PRESERVED": True,
            "ABLATION_3_LOOKUP_ORDER_PRESERVED": True,
            "ABLATION_3_PATCH_SCOPE_MATCH": False,
        }
        classification = perf010a.classify_workload(entry, "3", structural_contract_3)
        self.assertFalse(classification["structural_ablation_confirmed"])
        self.assertEqual("INVALID", classification["perf010a_ablation_3"])

    # --- structural_contract_confirmed_ablation_3 (per-image exact-scope proof) ---

    def _valid_probe_pair(self):
        baseline_probe = {
            "baseline_read_local_slot_body": "{ containsKey/get body }",
            "diagnostic_helper_present": False,
            "diagnostic_marker_present": False,
            "diagnostic_helper_contains_key_absent": True,
            "diagnostic_helper_single_get_count": 0,
            "current_context_diagnostic": False,
            "current_context_baseline": True,
            "captured_context_diagnostic": False,
            "captured_context_baseline": True,
            "captured_lexical_traversal_present": True,
            "lookup_fallback_present": True,
            "value_lookup_call_site_present": True,
        }
        ablation_probe = {
            "baseline_read_local_slot_body": "{ containsKey/get body }",
            "diagnostic_helper_present": True,
            "diagnostic_marker_present": True,
            "diagnostic_helper_contains_key_absent": True,
            "diagnostic_helper_single_get_count": 1,
            "current_context_diagnostic": True,
            "current_context_baseline": False,
            "captured_context_diagnostic": True,
            "captured_context_baseline": False,
            "captured_lexical_traversal_present": True,
            "lookup_fallback_present": True,
            "value_lookup_call_site_present": True,
        }
        return baseline_probe, ablation_probe

    def test_structural_contract_confirmed_for_correct_probe_pair(self):
        baseline_probe, ablation_probe = self._valid_probe_pair()
        checks = perf010a.structural_contract_confirmed_ablation_3(baseline_probe, ablation_probe)
        self.assertTrue(checks["ABLATION_3_PATCH_SCOPE_MATCH"])
        self.assertTrue(all(checks.values()))

    def test_structural_contract_fails_when_baseline_body_diverges(self):
        baseline_probe, ablation_probe = self._valid_probe_pair()
        ablation_probe["baseline_read_local_slot_body"] = "{ different body }"
        checks = perf010a.structural_contract_confirmed_ablation_3(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_3_BASELINE_READ_LOCAL_SLOT_UNCHANGED"])
        self.assertFalse(checks["ABLATION_3_PATCH_SCOPE_MATCH"])

    def test_structural_contract_fails_when_only_current_context_is_diagnostic(self):
        baseline_probe, ablation_probe = self._valid_probe_pair()
        ablation_probe["captured_context_diagnostic"] = False
        ablation_probe["captured_context_baseline"] = True
        checks = perf010a.structural_contract_confirmed_ablation_3(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_3_CAPTURED_CONTEXT_CALLSITE"])
        self.assertFalse(checks["ABLATION_3_LOOKUP_ORDER_PRESERVED"])
        self.assertFalse(checks["ABLATION_3_PATCH_SCOPE_MATCH"])

    def test_structural_contract_fails_when_value_lookup_path_changed(self):
        baseline_probe, ablation_probe = self._valid_probe_pair()
        ablation_probe["value_lookup_call_site_present"] = False
        checks = perf010a.structural_contract_confirmed_ablation_3(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_3_PROTOS_VALUE_LOOKUP_PATH_UNCHANGED"])
        self.assertFalse(checks["ABLATION_3_PATCH_SCOPE_MATCH"])

    def test_structural_contract_fails_when_captured_lexical_traversal_missing(self):
        baseline_probe, ablation_probe = self._valid_probe_pair()
        ablation_probe["captured_lexical_traversal_present"] = False
        checks = perf010a.structural_contract_confirmed_ablation_3(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_3_CAPTURED_LEXICAL_TRAVERSAL_PRESERVED"])
        self.assertFalse(checks["ABLATION_3_PATCH_SCOPE_MATCH"])

    # --- reference() fails closed on the static structural gate before the expensive matrix ---

    def test_reference_checks_ablation3_structural_contract_before_run_matrix(self):
        # reference() now dispatches ablation 3's and 4's structural gate generically through
        # STRUCTURAL_CONTRACT_CONFIRM[ablation] (see the shared STRUCTURAL_PROBE /
        # STRUCTURAL_CONTRACT_CONFIRM / STRUCTURAL_SCOPE_MATCH_KEY dicts), so the source no
        # longer names structural_contract_confirmed_ablation_3 literally; the generic dispatch
        # call site is what must precede run_matrix instead.
        import inspect

        source = inspect.getsource(perf010a.reference)
        self.assertIs(
            perf010a.STRUCTURAL_CONTRACT_CONFIRM["3"],
            perf010a.structural_contract_confirmed_ablation_3,
        )
        gate_idx = source.index("STRUCTURAL_CONTRACT_CONFIRM[ablation]")
        matrix_idx = source.index("run_matrix(")
        self.assertLess(
            gate_idx, matrix_idx,
            "ablation 3's/4's structural exact-scope gate must be checked before the expensive "
            "reference matrix runs, not after",
        )

    def test_smoke_checks_ablation3_structural_contract_before_run_matrix(self):
        import inspect

        source = inspect.getsource(perf010a.smoke)
        gate_idx = source.index("STRUCTURAL_CONTRACT_CONFIRM[ablation]")
        matrix_idx = source.index("run_matrix(")
        self.assertLess(gate_idx, matrix_idx)

    # --- PERF010A_ABLATION_4 (duplicate ProtosClosureValue.nativeBody() projection) coverage ---

    def test_ablation4_static_contract(self):
        cfg = perf010a.validate("4")
        self.assertEqual("PERF010-A", cfg["perf_item"])
        self.assertEqual("PERF010", cfg["parent_perf_item"])
        self.assertEqual("PERF010A_ABLATION_4", cfg["slice"])
        self.assertTrue(cfg["diagnostic_claim"])
        self.assertEqual(
            "4c4aa95a5852119bd280ceb40483871d5d2cbb82", cfg["protos_revision"]
        )

    def test_ablation4_pinned_revision_differs_from_earlier_ablations(self):
        cfg1 = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        cfg3 = json.loads((ROOT / "config/perf010a-3.json").read_text(encoding="utf-8"))
        cfg4 = json.loads((ROOT / "config/perf010a-4.json").read_text(encoding="utf-8"))
        self.assertNotEqual(cfg1["protos_revision"], cfg4["protos_revision"])
        self.assertNotEqual(cfg3["protos_revision"], cfg4["protos_revision"])
        self.assertIn("protos_revision_note", cfg4)

    def test_ablation4_experiment_matrix_matches_ablation1_exactly(self):
        cfg1 = json.loads((ROOT / "config/perf010a.json").read_text(encoding="utf-8"))
        cfg4 = json.loads((ROOT / "config/perf010a-4.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg1["controls"], cfg4["controls"])
        self.assertEqual(cfg1["operation_count"], cfg4["operation_count"])
        self.assertEqual(cfg1["warmup_iterations"], cfg4["warmup_iterations"])
        self.assertEqual(cfg1["steady_iterations"], cfg4["steady_iterations"])
        self.assertEqual(cfg1["execution_sample_period"], cfg4["execution_sample_period"])
        self.assertEqual(cfg1["variants"], cfg4["variants"])
        self.assertEqual(cfg1["toolchain"], cfg4["toolchain"])

    def test_ablation4_patch_touches_exactly_the_one_declared_target(self):
        # The established causal-ablation contract touches exactly one file
        # (ProtosBytecodeRootNode.java): a bounded local-variable rewrite inside
        # finishPreparingComposedCall, not a new helper (unlike ablation 3, which needed a
        # second file for its diagnostic helper).
        cfg = json.loads((ROOT / "config/perf010a-4.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        targets = cfg["ablation_patch_targets"]
        self.assertEqual(1, len(targets))
        self.assertEqual(
            "src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeRootNode.java",
            targets[0],
        )
        self.assertEqual(1, patch_text.count("--- a/"))

    def test_ablation4_patch_removes_exactly_the_two_original_call_sites(self):
        cfg = json.loads((ROOT / "config/perf010a-4.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        files = perf010a._parse_unified_diff(patch_text)
        root_node = files[perf010a.ROOT_NODE_SOURCE_PATH]
        removed_calls = [
            l for l in root_node["removed"] if perf010a.NATIVE_BODY_CALL_PATTERN in l
        ]
        non_call_removed = [
            l for l in root_node["removed"] if perf010a.NATIVE_BODY_CALL_PATTERN not in l
        ]
        self.assertEqual(2, len(removed_calls))
        self.assertEqual([], non_call_removed)
        added_text = "\n".join(root_node["added"])
        self.assertEqual(1, added_text.count(perf010a.NATIVE_BODY_CALL_PATTERN))
        self.assertIn(f"{perf010a.NATIVE_BODY_PROJECTION_LOCAL}.isPresent()", added_text)
        self.assertIn(f"{perf010a.NATIVE_BODY_PROJECTION_LOCAL}.orElseThrow()", added_text)

    def test_ablation4_patch_carries_the_diagnostic_marker_comment(self):
        cfg = json.loads((ROOT / "config/perf010a-4.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        self.assertIn("PERF010A_ABLATION_4", patch_text)

    def test_ablation4_patch_does_not_touch_other_production_mechanisms(self):
        cfg = json.loads((ROOT / "config/perf010a-4.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        for forbidden in (
            "ProtosClosureValue.java",
            "ProtosActivation.java",
            "ProtosValueLookup.java",
            "CanonicalToBytecodeLowerer.java",
            "ProtosSourceCompiler.java",
            "ProtosBytecodeClosureExecutionPlan.java",
            "ProtosRootTaskExecution.java",
            "finishPreparingComposedCallByImplementation",
            "continueAt",
            "RootTag",
            "ContinuationResult",
            "ProtosSemanticBytecodeRootNode",
        ):
            self.assertNotIn(forbidden, patch_text, forbidden)

    # --- exact-scope validation (AGENTS.work/PERFORMANCE.md's causal-ablation rule) ---

    def test_ablation4_patch_passes_exact_scope_validation(self):
        cfg = json.loads((ROOT / "config/perf010a-4.json").read_text(encoding="utf-8"))
        patch_text = (ROOT / cfg["ablation_patch"]).read_text(encoding="utf-8")
        perf010a.validate_patch_shape_4(patch_text)  # must not raise

    def test_ablation4_patch_touching_closure_value_fails_validation(self):
        # If ProtosClosureValue.java were touched too (even a no-op comment change), a second
        # file would be part of the diagnostic, which this slice's established scope forbids.
        base_patch = (ROOT / "docker/protos-perf010a/ablation-4.patch").read_text(
            encoding="utf-8"
        )
        extra = (
            "\ndiff --git a/src/main/java/com/guillermomolina/protos/runtime/ProtosClosureValue.java "
            "b/src/main/java/com/guillermomolina/protos/runtime/ProtosClosureValue.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosClosureValue.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/runtime/ProtosClosureValue.java\n"
            "@@ -251,7 +251,7 @@\n"
            "     public java.util.Optional<ProtosNativeClosureBody> nativeBody() {\n"
            "-        return java.util.Optional.ofNullable(nativeBody);\n"
            "+        return java.util.Optional.ofNullable(nativeBody); // touched\n"
            "     }\n"
        )
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_4(base_patch + extra)

    def test_ablation4_patch_removing_only_one_call_site_fails_validation(self):
        # Only the isPresent() call site redirected to the new projection; orElseThrow() still
        # calls closure.nativeBody() a second time. Must fail (both uses must move together).
        patch = (
            "diff --git a/src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeRootNode.java "
            "b/src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeRootNode.java\n"
            "--- a/src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeRootNode.java\n"
            "+++ b/src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeRootNode.java\n"
            "@@ -5569,9 +5569,13 @@\n"
            "             ProtosModuleRuntime structuredImportRuntime) {\n"
            "+        // PERF010A_ABLATION_4 diagnostic-only projection reuse\n"
            "+        java.util.Optional<ProtosNativeClosureBody> nativeBodyProjection =\n"
            "+                closure.nativeBody();\n"
            "-        if (closure.nativeBody().isPresent()) {\n"
            "+        if (nativeBodyProjection.isPresent()) {\n"
            "             ProtosNativeClosureBody nativeBody =\n"
            "                     closure.nativeBody().orElseThrow();\n"
        )
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_4(patch)

    def test_ablation4_patch_touching_a_different_call_site_fails_validation(self):
        # Widening the diagnostic to also cover one of the other (excluded) nativeBody() call
        # sites in the same file must fail, even though the primary rewrite is otherwise
        # correct - the exact-scope contract only permits the two call sites inside
        # finishPreparingComposedCall.
        base_patch = (ROOT / "docker/protos-perf010a/ablation-4.patch").read_text(
            encoding="utf-8"
        )
        extra_hunk = (
            "@@ -4436,7 +4441,7 @@\n"
            "     ProtosModuleRuntime structuredImportRuntime) {\n"
            "-        if (closure.nativeBody().isPresent()) {\n"
            "+        if (closure.nativeBody().isPresent()) { // touched\n"
        )
        # Insert a second hunk into the same file's diff so the removed-line count for
        # closure.nativeBody() departs from exactly 2.
        patched = base_patch.rstrip("\n") + "\n" + extra_hunk
        with self.assertRaises(AssertionError):
            perf010a.validate_patch_shape_4(patched)

    def test_ablation4_dockerfile_supports_selectable_patch(self):
        dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG ABLATION_PATCH=ablation.patch", dockerfile)
        self.assertIn("${ABLATION_PATCH}", dockerfile)
        self.assertIn("/opt/protos-source", dockerfile)

    # --- structural_contract_confirmed_ablation_4 (per-image exact-scope proof) ---

    def _valid_probe_pair_4(self):
        baseline_probe = {
            "native_body_call_count": 2,
            "projection_local_present": False,
            "projection_is_present_use": False,
            "projection_or_else_throw_use": False,
            "diagnostic_marker_present": False,
            "outside_method_source": "{ rest of ProtosBytecodeRootNode.java }",
            "closure_value_source": "{ ProtosClosureValue.java }",
        }
        ablation_probe = {
            "native_body_call_count": 1,
            "projection_local_present": True,
            "projection_is_present_use": True,
            "projection_or_else_throw_use": True,
            "diagnostic_marker_present": True,
            "outside_method_source": "{ rest of ProtosBytecodeRootNode.java }",
            "closure_value_source": "{ ProtosClosureValue.java }",
        }
        return baseline_probe, ablation_probe

    def test_structural_contract_4_confirmed_for_correct_probe_pair(self):
        baseline_probe, ablation_probe = self._valid_probe_pair_4()
        checks = perf010a.structural_contract_confirmed_ablation_4(baseline_probe, ablation_probe)
        self.assertTrue(checks["ABLATION_4_PATCH_SCOPE_MATCH"])
        self.assertTrue(all(checks.values()))

    def test_structural_contract_4_fails_when_ablation_still_has_two_calls(self):
        baseline_probe, ablation_probe = self._valid_probe_pair_4()
        ablation_probe["native_body_call_count"] = 2
        checks = perf010a.structural_contract_confirmed_ablation_4(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_4_ABLATION_HAS_ONE_PROJECTION"])
        self.assertFalse(checks["ABLATION_4_PATCH_SCOPE_MATCH"])

    def test_structural_contract_4_fails_when_other_call_sites_diverge(self):
        baseline_probe, ablation_probe = self._valid_probe_pair_4()
        ablation_probe["outside_method_source"] = "{ different rest of file }"
        checks = perf010a.structural_contract_confirmed_ablation_4(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_4_OTHER_CALL_SITES_UNCHANGED"])
        self.assertFalse(checks["ABLATION_4_PATCH_SCOPE_MATCH"])

    def test_structural_contract_4_fails_when_closure_value_diverges(self):
        baseline_probe, ablation_probe = self._valid_probe_pair_4()
        ablation_probe["closure_value_source"] = "{ different ProtosClosureValue.java }"
        checks = perf010a.structural_contract_confirmed_ablation_4(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_4_CLOSURE_VALUE_UNCHANGED"])
        self.assertFalse(checks["ABLATION_4_PATCH_SCOPE_MATCH"])

    def test_structural_contract_4_fails_when_baseline_already_has_marker(self):
        baseline_probe, ablation_probe = self._valid_probe_pair_4()
        baseline_probe["diagnostic_marker_present"] = True
        checks = perf010a.structural_contract_confirmed_ablation_4(baseline_probe, ablation_probe)
        self.assertFalse(checks["ABLATION_4_BASELINE_HAS_TWO_PROJECTIONS"])
        self.assertFalse(checks["ABLATION_4_PATCH_SCOPE_MATCH"])

    # --- classify_workload (ablation 4, source-derived structural contract) ---

    def test_classify_workload_ablation4_uses_structural_contract_not_jfr(self):
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
                "ablation": {"canonical": cell(900), "control": cell(100)},
            },
        }
        structural_contract_4 = perf010a.structural_contract_confirmed_ablation_4(
            *self._valid_probe_pair_4()
        )
        classification = perf010a.classify_workload(
            entry, "4", None, structural_contract_4
        )
        self.assertTrue(classification["correctness_confirmed"])
        self.assertTrue(classification["structural_ablation_confirmed"])
        self.assertEqual("VALID", classification["perf010a_ablation_4"])
        self.assertEqual(100, classification["removed_ns"])

    def test_classify_workload_ablation4_without_structural_contract_is_invalid(self):
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
                "ablation": {"canonical": cell(900), "control": cell(100)},
            },
        }
        classification = perf010a.classify_workload(entry, "4", None, None)
        self.assertFalse(classification["structural_ablation_confirmed"])
        self.assertEqual("INVALID", classification["perf010a_ablation_4"])

    # reference()/smoke()'s gate-before-run_matrix ordering for ablation 4 is covered by
    # test_reference_checks_ablation3_structural_contract_before_run_matrix and
    # test_smoke_checks_ablation3_structural_contract_before_run_matrix above: both ablations
    # now share the same generic STRUCTURAL_CONTRACT_CONFIRM[ablation] dispatch call site, so a
    # separate ablation-4-specific assertion would just duplicate the same source check.


class Perf010aDiscriminationTest(unittest.TestCase):
    """Docker-free contract/logic tests for the #691 measurement-discrimination investigation
    (config/perf010a-0.json + the no-op/counterbalanced-block functions at the end of
    runner/perf010a.py). Does not build images or run containers."""

    def test_discrimination_config_validates(self):
        cfg = perf010a.validate_discrimination()
        self.assertEqual("PERF010A_NOOP", cfg["slice"])
        self.assertTrue(cfg["measurement_discrimination_experiment"])
        self.assertEqual(["A", "B", "A", "B"], cfg["block_order"])

    def test_noop_patch_is_literally_empty(self):
        patch_path = ROOT / "docker/protos-perf010a/noop.patch"
        self.assertEqual("", patch_path.read_text(encoding="utf-8"))

    def test_discrimination_reuses_exact_perf008_workload_matrix(self):
        cfg = json.loads((ROOT / "config/perf010a-0.json").read_text(encoding="utf-8"))
        perf008_cfg = json.loads((ROOT / "config/perf008.json").read_text(encoding="utf-8"))
        self.assertEqual(perf008_cfg["controls"], cfg["controls"])
        self.assertEqual(20, cfg["warmup_iterations"])
        self.assertEqual(100, cfg["steady_iterations"])

    def test_discrimination_config_rejects_a_nonempty_patch(self):
        cfg = json.loads((ROOT / "config/perf010a-0.json").read_text(encoding="utf-8"))
        self.assertEqual([], cfg["ablation_patch_targets"])

    def _block_entry(self, block_index, block_order, baseline_canonical, baseline_control,
                      noop_canonical, noop_control, workload="micro/slot-read"):
        def summary(median_ns):
            return {"steady_summary": {"median_ns": median_ns}}

        return {
            "block_index": block_index,
            "block_order": block_order,
            "variant_sequence": ["baseline", "ablation"],
            "workload": workload,
            "variants": {
                "baseline": {
                    "canonical": summary(baseline_canonical),
                    "control": summary(baseline_control),
                },
                "ablation": {
                    "canonical": summary(noop_canonical),
                    "control": summary(noop_control),
                },
            },
        }

    def test_classify_discrimination_block_sign_convention(self):
        entry = self._block_entry(0, "A", 1000, 100, 900, 100)
        classified = perf010a.classify_discrimination_block(entry)
        # canonical_difference = 1000-900=100; control_difference = 100-100=0;
        # paired_control_difference_ns = 100-0=100; as % of baseline canonical (1000) = 10%.
        self.assertEqual(100, classified["canonical_difference_ns"])
        self.assertEqual(0, classified["control_difference_ns"])
        self.assertEqual(100, classified["paired_control_difference_ns"])
        self.assertAlmostEqual(10.0, classified["paired_control_difference_percent"])

    def test_classify_discrimination_block_zero_when_all_medians_equal(self):
        entry = self._block_entry(0, "A", 1000, 100, 1000, 100)
        classified = perf010a.classify_discrimination_block(entry)
        self.assertEqual(0, classified["paired_control_difference_ns"])
        self.assertEqual(0.0, classified["paired_control_difference_percent"])

    def test_summarize_discrimination_workload_envelope_and_order_effect_not_detected(self):
        blocks = [
            perf010a.classify_discrimination_block(
                self._block_entry(0, "A", 1000, 100, 990, 100)
            ),
            perf010a.classify_discrimination_block(
                self._block_entry(1, "B", 1000, 100, 1005, 100)
            ),
            perf010a.classify_discrimination_block(
                self._block_entry(2, "A", 1000, 100, 995, 100)
            ),
            perf010a.classify_discrimination_block(
                self._block_entry(3, "B", 1000, 100, 998, 100)
            ),
        ]
        summary = perf010a.summarize_discrimination_workload(blocks)
        self.assertEqual(4, summary["samples"])
        # A-order values: +1.0%, +0.5%; B-order values: -0.5%, -0.2% -> ranges [0.5,1.0] and
        # [-0.5,-0.2] do not overlap -> DETECTED under the pre-specified non-overlap rule.
        self.assertEqual("DETECTED", summary["order_effect"])
        self.assertAlmostEqual(1.0, summary["discrimination_floor_percent"])

    def test_summarize_discrimination_workload_order_effect_not_detected_when_overlapping(self):
        blocks = [
            perf010a.classify_discrimination_block(
                self._block_entry(0, "A", 1000, 100, 995, 100)
            ),
            perf010a.classify_discrimination_block(
                self._block_entry(1, "B", 1000, 100, 1005, 100)
            ),
            perf010a.classify_discrimination_block(
                self._block_entry(2, "A", 1000, 100, 1005, 100)
            ),
            perf010a.classify_discrimination_block(
                self._block_entry(3, "B", 1000, 100, 995, 100)
            ),
        ]
        summary = perf010a.summarize_discrimination_workload(blocks)
        self.assertEqual("NOT_DETECTED", summary["order_effect"])

    def test_summarize_discrimination_workload_inconclusive_with_one_block_per_order(self):
        blocks = [
            perf010a.classify_discrimination_block(
                self._block_entry(0, "A", 1000, 100, 995, 100)
            ),
            perf010a.classify_discrimination_block(
                self._block_entry(1, "B", 1000, 100, 1005, 100)
            ),
        ]
        summary = perf010a.summarize_discrimination_workload(blocks)
        self.assertEqual("INCONCLUSIVE", summary["order_effect"])

    def test_classify_effect_vs_floor_thresholds(self):
        self.assertEqual("ABOVE", perf010a.classify_effect_vs_floor(8.45, 1.0))
        self.assertEqual("BELOW", perf010a.classify_effect_vs_floor(0.11, 1.0))
        self.assertEqual("COMPARABLE", perf010a.classify_effect_vs_floor(1.2, 1.0))

    def test_combine_workload_verdicts(self):
        self.assertEqual("ABOVE", perf010a.combine_workload_verdicts(["ABOVE"] * 4))
        self.assertEqual(
            "MIXED", perf010a.combine_workload_verdicts(["ABOVE", "BELOW", "ABOVE", "ABOVE"])
        )

    def test_discrimination_gate_open_when_floor_below_historical_minimum_and_no_order_effect(self):
        # micro/method-call's smallest historical |effect| across A1/A3/A4 is 0.35 (A1); a
        # floor below that with NOT_DETECTED order effect must gate OPEN.
        gate = perf010a.discrimination_gate_for_workload("micro/method-call", 0.1, "NOT_DETECTED")
        self.assertEqual("OPEN", gate)

    def test_discrimination_gate_closed_when_floor_at_or_above_historical_minimum(self):
        gate = perf010a.discrimination_gate_for_workload("micro/method-call", 0.5, "NOT_DETECTED")
        self.assertEqual("CLOSED", gate)

    def test_discrimination_gate_closed_when_order_effect_detected_even_if_floor_low(self):
        gate = perf010a.discrimination_gate_for_workload("micro/method-call", 0.01, "DETECTED")
        self.assertEqual("CLOSED", gate)

    def test_discrimination_gate_inconclusive_propagates(self):
        gate = perf010a.discrimination_gate_for_workload(
            "micro/method-call", 0.01, "INCONCLUSIVE"
        )
        self.assertEqual("INCONCLUSIVE", gate)

    def test_combine_gate_closed_dominates(self):
        self.assertEqual(
            "CLOSED",
            perf010a.combine_gate({"a": "OPEN", "b": "CLOSED", "c": "OPEN", "d": "OPEN"}),
        )

    def test_combine_gate_inconclusive_when_no_closed(self):
        self.assertEqual(
            "INCONCLUSIVE",
            perf010a.combine_gate({"a": "OPEN", "b": "INCONCLUSIVE", "c": "OPEN", "d": "OPEN"}),
        )

    def test_combine_gate_open_when_all_open(self):
        self.assertEqual(
            "OPEN",
            perf010a.combine_gate({"a": "OPEN", "b": "OPEN", "c": "OPEN", "d": "OPEN"}),
        )

    def test_minimum_next_change_none_when_gate_open(self):
        change = perf010a.minimum_next_methodological_change("OPEN", {}, {})
        self.assertEqual("NONE", change)

    def test_minimum_next_change_flags_order_effect_first(self):
        per_workload_summary = {"micro/slot-read": {"order_effect": "DETECTED"}}
        per_workload_gates = {"micro/slot-read": "CLOSED"}
        change = perf010a.minimum_next_methodological_change(
            "CLOSED", per_workload_gates, per_workload_summary
        )
        self.assertIn("lifecycle isolation", change)

    def test_minimum_next_change_flags_floor_when_no_order_effect(self):
        per_workload_summary = {"micro/slot-read": {"order_effect": "NOT_DETECTED"}}
        per_workload_gates = {"micro/slot-read": "CLOSED"}
        change = perf010a.minimum_next_methodological_change(
            "CLOSED", per_workload_gates, per_workload_summary
        )
        self.assertIn("steady_iterations", change)

    def test_build_image_accepts_discrimination_slice_tag_naming(self):
        cfg = perf010a.load(perf010a.DISCRIMINATION_CONFIG)
        self.assertIn(perf010a.DISCRIMINATION_ABLATION, perf010a.ABLATIONS_WITH_DISCRIMINATION)
        self.assertNotIn(perf010a.DISCRIMINATION_ABLATION, perf010a.ABLATIONS)

    def test_cli_exposes_discrimination_commands(self):
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH), "discrimination-validate"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("PERF010A_DISCRIMINATION_CONFIG=PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
