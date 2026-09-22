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


if __name__ == "__main__":
    unittest.main()
