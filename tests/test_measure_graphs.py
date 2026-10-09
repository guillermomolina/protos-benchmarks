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

"""Graph-parity driver (truffle/measure_graphs.py) without JVM or Docker:
policy/catalog consistency, analyze through a fake analyzer script, and
summarize from synthetic retained captures to the rung matrix."""

from __future__ import annotations

import contextlib
import gzip
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "truffle"))

import graph_cache as gc  # noqa: E402
import measure_graphs as mg  # noqa: E402
import measure_protos as mp  # noqa: E402
import workload_catalog  # noqa: E402


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = mg.load_policy()

    def test_ladder_is_the_exact_primitive_order_and_catalogued(self):
        self.assertEqual(
            [
                "primitive-return-literal",
                "primitive-local-read",
                "primitive-local-write",
                "primitive-integer-add",
                "primitive-object-slot-read",
                "primitive-object-slot-write",
                "primitive-closure-call",
                "primitive-method-call",
            ],
            mg.select_workloads(self.policy, "ladder"),
        )
        for workload in mg.select_workloads(self.policy, "ladder"):
            for language in mg.LANGUAGES:
                self.assertTrue(workload_catalog.source_for(workload, language).is_file())

    def test_all_graph_workloads_are_catalogued(self):
        self.assertEqual(
            list(workload_catalog.workload_ids()),
            mg.select_workloads(self.policy, "all"),
        )
        self.assertEqual(17, len(mg.select_workloads(self.policy, "all")))

    def test_peer_capture_key_is_independent_of_protos(self):
        java = {"java.runtime.version": "25.0.4.1.1"}
        old_product = {
            "revision": "a" * 40,
            "source_state_sha256": "b" * 64,
        }
        new_product = {
            "revision": "c" * 40,
            "source_state_sha256": "d" * 64,
        }

        for language in ("js", "python"):
            old = mg.graph_capture_key(
                self.policy, old_product, language, "executable-value",
                "primitive-return-literal", "reference", java,
            )
            new = mg.graph_capture_key(
                self.policy, new_product, language, "executable-value",
                "primitive-return-literal", "reference", java,
            )
            self.assertEqual(old, new)
            self.assertNotIn("protos_revision", old)
            self.assertNotIn("workload_source_sha256", old)

        old = mg.graph_capture_key(
            self.policy, old_product, "protos", "canonical",
            "primitive-return-literal", "reference", java,
        )
        new = mg.graph_capture_key(
            self.policy, new_product, "protos", "canonical",
            "primitive-return-literal", "reference", java,
        )
        self.assertNotEqual(old, new)

    def test_new_object_slot_workloads(self):
        self.assertEqual("1", workload_catalog.expected_result("primitive-object-slot-read"))
        self.assertEqual("2", workload_catalog.expected_result("primitive-object-slot-write"))
        for workload in ("primitive-object-slot-read", "primitive-object-slot-write"):
            for language in mg.LANGUAGES:
                text = workload_catalog.source_for(workload, language).read_text()
                body = text.split("run", 1)[1]
                self.assertNotIn("new ", body)
                self.assertIn("holder", text.split("run", 1)[0], f"{workload}/{language}: holder outside run")

    def test_control_flow_workloads_are_individual_and_outside_ladder(self):
        expected = {
            "primitive-if-true": "1",
            "primitive-if-false": "1",
            "primitive-while-zero": "1",
            "primitive-while-once": "1",
            "primitive-while-counted": "8",
        }
        ladder = mg.select_workloads(self.policy, "ladder")
        cases = mp.load_cases()
        for workload, result in expected.items():
            self.assertEqual(result, workload_catalog.expected_result(workload))
            self.assertEqual((workload,), workload_catalog.select_workloads(workload))
            self.assertEqual([workload], mg.select_workloads(self.policy, workload))
            self.assertNotIn(workload, ladder)
            self.assertEqual(
                cases["policy"]["workloads"]["primitive-method-call"],
                cases["policy"]["workloads"][workload],
            )
            for language in mg.LANGUAGES:
                self.assertTrue(workload_catalog.source_for(workload, language).is_file())
        protos = {w: workload_catalog.source_for(w, "protos").read_text() for w in expected}
        self.assertIn("true.ifTrue()", protos["primitive-if-true"])
        self.assertIn("false.ifTrue()", protos["primitive-if-false"])
        self.assertIn("(() => false).whileTrue()", protos["primitive-while-zero"])
        self.assertIn("(() => i < 1).whileTrue()", protos["primitive-while-once"])
        self.assertIn("(() => i < 8).whileTrue()", protos["primitive-while-counted"])

    def test_surfaces_exist_and_options_are_normal_capture(self):
        cases = mp.load_cases()
        for language, entry in self.policy["languages"].items():
            self.assertIn(entry["surface"], cases["surfaces"])
        options = self.policy["jvm_options"]
        self.assertIn("-Djdk.graal.Dump=Truffle:1", options)
        self.assertIn("-Dpolyglot.engine.BackgroundCompilation=false", options)
        self.assertIn("-Dpolyglot.compiler.TraceNodeExpansion=truffleTier", options)
        self.assertFalse(any("CompileImmediately" in o or "Dump=Truffle:2" in o for o in options))
        self.assertEqual([1000, 4000, 16000, 64000, 256000], self.policy["budgets"]["reference"])
        self.assertEqual("After TruffleTier", self.policy["selected_phase"])

    def test_graph_producer_files_are_hashed(self):
        names = {p.name for p in mg.GRAPH_PRODUCER_FILES}
        self.assertTrue({"measure_graphs.py", "graph_evidence.py", "graphs.json", "compiler_trace.py",
                         "igv_analyzer.sh"} <= names)


def igv_doc(classes):
    return {"name": "dump", "graphs": [
        {"name": "Before TruffleTier", "nodes": [{"id": 0, "properties": {"class": "StartNode"}}]},
        {"name": "After TruffleTier",
         "nodes": [{"id": i, "properties": {"class": c}} for i, c in enumerate(classes)]},
    ]}


def unit_record(role, label, comp_id):
    return {
        "role": role, "label": label, "via": None if role == "primary" else "run",
        "edge": None if role == "primary" else "Cutoff", "tier": 2, "comp_id": comp_id, "src": "n/a",
        "superseded_comp_ids": [comp_id - 1], "ir_after_truffle_tier": 1, "expansion_truffle_tier": None,
        "inlined": [], "attribution": [], "bgv": [f"TruffleHotSpotCompilation-{comp_id}[{label}].bgv"],
    }


def write_case(output, workload, language, units_by_budget, docs, stable=True):
    directory = output / workload / language
    runs = []
    for budget, units in units_by_budget.items():
        retained = []
        inventory = []
        for unit in units:
            name = unit["bgv"][0]
            packed = directory / f"budget-{budget}" / "bgv" / (name + ".gz")
            packed.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(packed, "wb") as stream:
                stream.write(json.dumps(docs[(budget, unit["label"])]).encode())  # fake BGV payload
            retained.append(str(packed.relative_to(directory)))
            inventory.append({"name": name, "bytes": 1, "sha256": "0" * 64})
        runs.append({
            "budget": budget, "trace_log": f"budget-{budget}/trace.log.gz", "retained_bgv": retained,
            "dump_inventory": inventory,
            "resolution": {"units": units, "unattributed_language_targets": [], "framework_targets": ["fw"]},
        })
    budgets = list(units_by_budget)
    metadata = {
        "capture_valid": True, "protos_revision": "a" * 40, "harness_git_head": "b" * 40,
        "harness_dirty": True, "harness": {"source_sha256": {}}, "language": language, "surface": "s",
        "surface_timed_call": "c", "workload": workload, "workload_source_sha256": "c" * 64,
        "expected_result": "1", "correctness": {"result": "PASS"}, "java": {}, "host": {},
        "graph_jvm_options": [], "budget_policy": budgets, "runs": runs,
        "stabilization": {"status": "STABLE" if stable else "GRAPH_NOT_STABLE",
                          "pair": budgets[-2:] if stable else None},
    }
    mp.write_json(directory / "capture.json", metadata)


FAKE_ANALYZER = """#!/usr/bin/env bash
# fake scripts/igv_analyzer.sh: the "BGV" already holds the JSON document
[ "$1" = filter ] || exit 9
cat "$2"
"""


class AnalyzeSummarizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / "out"
        self.output.mkdir()
        analyzer = Path(self.tmp.name) / "igv_analyzer.sh"
        analyzer.write_text(FAKE_ANALYZER)
        analyzer.chmod(0o755)
        self.saved = mg.ANALYZER
        mg.ANALYZER = analyzer
        self.addCleanup(setattr, mg, "ANALYZER", self.saved)
        self.addCleanup(self.tmp.cleanup)
        runtime_probe = patch.object(
            mg.shutil, "which", return_value="/usr/bin/podman"
        )
        runtime_probe.start()
        self.addCleanup(runtime_probe.stop)

    def run_cmd(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mg.main(list(argv))
        return code, out.getvalue()

    def single(self, workload, language, classes, label="run", extra=None):
        units = {b: [unit_record("primary", label, 10 + i)] for i, b in enumerate((4000, 16000))}
        docs = {(b, label): igv_doc(classes) for b in (4000, 16000)}
        if extra:
            for i, b in enumerate((4000, 16000)):
                units[b].append(unit_record("additional", "helper", 20 + i))
                docs[(b, "helper")] = igv_doc(extra)
        write_case(self.output, workload, language, units, docs)

    def test_analyze_without_runtime_reports_host_requirement(self):
        self.single("primitive-return-literal", "js", ["A"] * 3)
        stderr = io.StringIO()

        with (
            patch.object(mg.shutil, "which", return_value=None),
            patch.dict(mg.os.environ, {"DOCKER": ""}),
            contextlib.redirect_stderr(stderr),
        ):
            code, output = self.run_cmd(
                "analyze", "--output", str(self.output)
            )

        self.assertEqual(mp.EXIT_USAGE, code)
        self.assertIn("CONTAINER_RUNTIME_NOT_FOUND", stderr.getvalue())
        self.assertIn("outside the devcontainer", stderr.getvalue())
        self.assertNotIn("ANALYZED=", output)

    def test_analyze_without_pending_work_needs_no_runtime(self):
        self.single("primitive-return-literal", "js", ["A"] * 3)

        for packed in self.output.rglob("*.bgv.gz"):
            result = packed.with_name(
                packed.name[:-len(".bgv.gz")] + ".filter.json.gz"
            )
            with gzip.open(result, "wb") as stream:
                stream.write(b"{}")

        with (
            patch.object(mg.shutil, "which", return_value=None),
            patch.dict(mg.os.environ, {"DOCKER": ""}),
        ):
            code, output = self.run_cmd(
                "analyze", "--output", str(self.output)
            )

        self.assertEqual(mp.EXIT_OK, code)
        self.assertIn("ANALYZE_FAILURES=0", output)

    def test_analyze_then_summarize_builds_matrix(self):
        self.single("primitive-return-literal", "js", ["A"] * 10)
        self.single("primitive-return-literal", "python", ["A"] * 12)
        self.single("primitive-return-literal", "protos", ["A"] * 11)
        self.single("primitive-local-read", "js", ["A"] * 10)
        self.single("primitive-local-read", "python", ["A"] * 12)
        self.single("primitive-local-read", "protos", ["A"] * 11, label="ProtosRoot@1", extra=["NewInstanceNode"])

        code, out = self.run_cmd("analyze", "--output", str(self.output))
        self.assertEqual(0, code, out)
        self.assertIn("ANALYZE_FAILURES=0", out)

        code, out = self.run_cmd("summarize", "--output", str(self.output))
        self.assertEqual(0, code, out)
        matrix = json.loads((self.output / "matrix.json").read_text())
        first, second = matrix["rungs"]
        self.assertEqual((11, 10, 12, 2), (first["protos_total"], first["js_total"], first["python_total"],
                                           first["peer_spread"]))
        self.assertEqual("STRUCTURALLY_CONVERGED", first["protos_status"])
        self.assertEqual(12, second["protos_total"])
        self.assertEqual("STRUCTURAL_EXCESS", second["protos_status"])
        self.assertEqual("primitive-local-read", matrix["first_divergent_rung"]["workload"])
        unit = json.loads((self.output / "primitive-local-read" / "protos" / "unit.json").read_text())
        self.assertTrue(unit["evidence_valid"])
        self.assertEqual(16000, unit["selected_budget"])
        self.assertEqual(2, unit["summary"]["graph_count"])
        self.assertEqual(["helper"], [u["label"] for u in unit["summary"]["additional_language_owned_compiled_units"]])
        self.assertTrue(unit["stabilization"]["after_truffle_tier_confirmed"])
        self.assertEqual("After TruffleTier", unit["units"][0]["graph"]["phase"])

    def test_pair_that_differs_in_bgv_is_not_stable(self):
        units = {b: [unit_record("primary", "run", 10 + i)] for i, b in enumerate((4000, 16000))}
        docs = {(4000, "run"): igv_doc(["A"] * 10), (16000, "run"): igv_doc(["A"] * 11)}
        write_case(self.output, "primitive-return-literal", "js", units, docs)
        self.run_cmd("analyze", "--output", str(self.output))
        code, _ = self.run_cmd("summarize", "--output", str(self.output))
        self.assertEqual(1, code)
        unit = json.loads((self.output / "primitive-return-literal" / "js" / "unit.json").read_text())
        self.assertEqual("GRAPH_NOT_STABLE", unit["invalid_reason"])
        self.assertEqual("AFTER_TRUFFLE_TIER_DIFFERS_IN_PAIR", unit["stabilization"]["reason"])

    def test_unanalyzed_and_unstable_evidence_is_invalid(self):
        units = {b: [unit_record("primary", "run", 10 + i)] for i, b in enumerate((4000, 16000))}
        docs = {(b, "run"): igv_doc(["A"]) for b in (4000, 16000)}
        write_case(self.output, "primitive-return-literal", "js", units, docs)
        write_case(self.output, "primitive-return-literal", "python", units, docs, stable=False)
        code, _ = self.run_cmd("summarize", "--output", str(self.output))
        self.assertEqual(1, code)
        js = json.loads((self.output / "primitive-return-literal" / "js" / "unit.json").read_text())
        python = json.loads((self.output / "primitive-return-literal" / "python" / "unit.json").read_text())
        self.assertEqual("BGV_NOT_ANALYZED", js["invalid_reason"])
        self.assertEqual("GRAPH_NOT_STABLE", python["invalid_reason"])
        matrix = json.loads((self.output / "matrix.json").read_text())
        self.assertEqual("UNRESOLVED", matrix["rungs"][0]["peer_reference"])
        self.assertIsNone(matrix["first_divergent_rung"])


class VerifyTest(unittest.TestCase):
    def test_producer_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            good = "truffle/graph_evidence.py"
            mp.write_json(output / "w" / "js" / "capture.json", {"harness": {"source_sha256": {
                good: mp.sha256_file(ROOT / good), "truffle/measure_graphs.py": "0" * 64}}})
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = mg.main(["verify", "--output", str(output)])
            self.assertEqual(1, code)
            self.assertIn("WORKING_TREE_MISMATCH=truffle/measure_graphs.py", out.getvalue())
            self.assertNotIn(f"WORKING_TREE_MISMATCH={good}", out.getvalue())



class HistoricalCachePromotionTest(unittest.TestCase):
    def test_local_evidence_promotion_preserves_original(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = (
                root / "results" / "local" / "old"
                / "primitive-method-call" / "js"
            )
            original.mkdir(parents=True)

            capture = {
                "workload": "primitive-method-call",
                "language": "js",
                "protos_revision": "a" * 40,
                "harness_git_head": "b" * 40,
            }
            unit = {"evidence_valid": True}

            mp.write_json(original / "capture.json", capture)
            mp.write_json(original / "unit.json", unit)

            original_capture_sha = mp.sha256_file(
                original / "capture.json"
            )
            original_unit_sha = mp.sha256_file(
                original / "unit.json"
            )

            with patch.object(
                gc, "complete_evidence", return_value=True
            ):
                imported = gc.publishable_source(
                    root, original, capture, unit
                )

                self.assertTrue(imported.is_dir())
                self.assertTrue(
                    imported.is_relative_to(
                        root / "results" / "graph-cache-imported"
                    )
                )
                self.assertTrue(
                    (imported / "import-provenance.json").is_file()
                )

                self.assertEqual(
                    original_capture_sha,
                    mp.sha256_file(original / "capture.json"),
                )
                self.assertEqual(
                    original_unit_sha,
                    mp.sha256_file(original / "unit.json"),
                )

                self.assertEqual(
                    imported,
                    gc.publishable_source(
                        root, original, capture, unit
                    ),
                )

                (imported / "capture.json").write_text(
                    "{}", encoding="utf-8"
                )

                with self.assertRaises(mp.UsageError):
                    gc.publishable_source(
                        root, original, capture, unit
                    )


if __name__ == "__main__":
    unittest.main()
