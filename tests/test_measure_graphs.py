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

"""Graph-parity driver (harness/measure_graphs.py) without JVM or Docker:
policy/catalog consistency, analyze through a fake analyzer script, and
summarize from synthetic retained captures to the rung matrix."""

from __future__ import annotations

import argparse
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
sys.path.insert(0, str(ROOT / "harness"))

import measure_graphs as mg  # noqa: E402
import measure_protos as mp  # noqa: E402
import workload_catalog  # noqa: E402



class BytecodeCaptureContractTest(unittest.TestCase):

    def test_histogram_uses_engine_shutdown_default(self):
        options = mg.bytecode_histogram_options()

        self.assertIn(
            "-Dpolyglot.engine.BytecodeHistogram=language,root",
            options,
        )

        self.assertFalse(
            any(
                "BytecodeHistogramInterval" in option
                for option in options
            )
        )

    def test_options_are_diagnostic_only(self):
        options = mg.bytecode_histogram_options()
        self.assertIn(
            "-Dpolyglot.engine.BytecodeHistogram=language,root",
            options,
        )
        self.assertFalse(
            any("TraceCompilation" in value for value in options)
        )
        self.assertFalse(
            any("jdk.graal.Dump" in value for value in options)
        )

    def test_missing_histogram_is_explicit_and_not_timing(self):
        runtime = {
            "runtime_cp": "fake",
            "main_class": "FakeMain",
            "system_properties": [],
            "core_arg": "-",
        }

        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "histogram.log"

            def fake_run(command, destination):
                self.assertIn(
                    "-Dpolyglot.engine.BytecodeHistogram=language,root",
                    command,
                )
                destination.write_text(
                    "result=1",
                    encoding="utf-8",
                )
                return 0, "result=1"

            with (
                patch.object(
                    mg.mp,
                    "run_logged",
                    side_effect=fake_run,
                ),
                patch.object(
                    mg.ge,
                    "parse_bytecode_histogram",
                    return_value={"status": "UNAVAILABLE"},
                ),
            ):
                result = mg.run_bytecode_diagnostic(
                    runtime,
                    Path("/fake/workload"),
                    "1",
                    100,
                    0,
                    log,
                )

            self.assertEqual(result["status"], "UNAVAILABLE")
            self.assertEqual(result["timing_evidence"], "NONE")
            self.assertEqual(
                result["raw_log_sha256"],
                mg.mp.sha256_file(log),
            )

    def test_incorrect_result_is_rejected(self):
        runtime = {
            "runtime_cp": "fake",
            "main_class": "FakeMain",
            "system_properties": [],
            "core_arg": "-",
        }

        with patch.object(
            mg.mp,
            "run_logged",
            return_value=(0, "result=wrong"),
        ):
            with self.assertRaises(mp.InvalidMeasurement):
                mg.run_bytecode_diagnostic(
                    runtime,
                    Path("/fake/workload"),
                    "1",
                    100,
                    0,
                    Path("/fake/log"),
                )

    def test_bytecode_command_has_no_graph_tier(self):
        args = mg.parse_args([
            "bytecode",
            "--language", "js",
            "--workload", "factorial",
            "--output", "/tmp/bytecode-test",
        ])
        self.assertEqual(args.calls, 100)
        self.assertFalse(hasattr(args, "tier"))



class CompiledRootInventoryTest(unittest.TestCase):
    def compilation(self, target, label, tier, comp_id):
        return {
            "seq": comp_id,
            "target": target,
            "label": label,
            "tier": tier,
            "comp_id": comp_id,
            "src": None,
            "ir_after_truffle_tier": 100 + comp_id,
            "ir_final": 200 + comp_id,
            "compilation_time_ms": 10,
            "truffle_compilation_ms": 6,
            "graal_compilation_ms": 4,
            "machine_code_bytes": 1000 + comp_id,
            "ast_nodes": 20,
            "inline_tree": [],
            "expansion": None,
        }

    def parsed(self, compilations):
        return {
            "compilations": compilations,
            "failures": [],
            "invalidations": [],
            "option_rejections": [],
            "unknown_lifecycle_events": [],
        }

    def test_roots_remain_independent(self):
        parsed = self.parsed([
            self.compilation("target-1", "run", 1, 10),
            self.compilation("target-2", "helper", 1, 20),
        ])

        inventory = mg.ge.observed_compilation_roots(
            parsed, 1
        )

        self.assertEqual(inventory["available"], 2)
        self.assertEqual(inventory["unavailable"], 0)
        self.assertEqual(
            {
                item["normalized_label"]
                for item in inventory["roots"]
            },
            {"run", "helper"},
        )
        self.assertEqual(
            {
                item["selected"]["comp_id"]
                for item in inventory["roots"]
            },
            {10, 20},
        )

    def test_missing_tier_is_explicit(self):
        parsed = self.parsed([
            self.compilation("target-1", "run", 1, 10),
            self.compilation("target-1", "run", 2, 11),
            self.compilation("target-2", "helper", 1, 20),
        ])

        inventory = mg.ge.observed_compilation_roots(
            parsed, 2
        )

        self.assertEqual(inventory["available"], 1)
        self.assertEqual(inventory["unavailable"], 1)

        unavailable = [
            item
            for item in inventory["roots"]
            if item["status"] == "UNAVAILABLE"
        ]

        self.assertEqual(
            unavailable[0]["reason"],
            "REQUESTED_TIER_NOT_OBSERVED",
        )
        self.assertIsNone(unavailable[0]["selected"])

    def test_normalized_identity_collisions_are_explicit(self):
        parsed = self.parsed([
            self.compilation("target-1", "Root@aa11", 1, 10),
            self.compilation("target-2", "Root@bb22", 1, 20),
        ])

        inventory = mg.ge.observed_compilation_roots(
            parsed, 1
        )

        self.assertEqual(len(inventory["roots"]), 2)
        self.assertTrue(all(
            item["cross_run_identity"] == "AMBIGUOUS"
            for item in inventory["roots"]
        ))
        self.assertEqual(
            inventory["interpreted_roots_coverage"],
            "NOT_ESTABLISHED",
        )

    def test_no_compilations_does_not_mean_zero_roots(self):
        inventory = mg.ge.observed_compilation_roots(
            self.parsed([]), 1
        )

        self.assertEqual(inventory["status"], "UNAVAILABLE")
        self.assertEqual(
            inventory["reason"],
            "NO_COMPILED_ROOTS_REPORTED",
        )
        self.assertEqual(inventory["roots"], [])

    def test_unknown_trace_events_fail_closed(self):
        parsed = self.parsed([
            self.compilation("target-1", "run", 1, 10),
        ])
        parsed["unknown_lifecycle_events"] = [
            {"line": 1, "header": "unknown"}
        ]

        with self.assertRaises(mg.ge.EvidenceError):
            mg.ge.observed_compilation_roots(parsed, 1)



class ColdRootPairingTest(unittest.TestCase):
    def capture(self, tier, root, producer="producer-a"):
        return {
            "mode": "cold-compilation",
            "capture_valid": True,
            "requested_root": "all",
            "requested_tier": tier,
            "language": "protos",
            "workload": "factorial",
            "surface": "canonical",
            "expected_result": "1",
            "selected_phase": "After TruffleTier",
            "correctness": {"result": "PASS"},
            "product_before": {
                "revision": "revision-a",
                "source_state_sha256": "source-a",
                "version": "0.3.147-SNAPSHOT",
            },
            "harness": {
                "git_head": "head-a",
                "source_sha256": {"source": producer},
            },
            "java": {
                "java.runtime.version": "25",
                "java.vm.version": "25",
            },
            "root_inventory": {
                "roots": [{
                    "target": f"target-{tier}",
                    "label": root,
                    "normalized_label": mg.ge.normalize_label(root),
                    "status": "AVAILABLE",
                    "cross_run_identity": "UNIQUE",
                }],
            },
            "unavailable_roots": [],
            "selected_compilations": [{
                "comp_id": 40 + tier,
                "root": root,
                "machine_code_bytes": 1000 + tier,
            }],
        }

    def summary(self, tier, root, count):
        return {
            "schema": 1,
            "mode": "cold-all-compiled-roots",
            "requested_tier": tier,
            "language": "protos",
            "workload": "factorial",
            "phase": "After TruffleTier",
            "units": [{
                "label": root,
                "target": f"target-{tier}",
                "tier": tier,
                "comp_id": 40 + tier,
                "graph": {
                    "node_count": count,
                    "node_class_histogram": {
                        "ExampleNode": count,
                    },
                },
            }],
        }

    def test_matching_roots_pair_across_process_addresses(self):
        report = mg.ge.pair_compiled_root_tiers(
            self.capture(1, "run@aa11"),
            self.summary(1, "run@aa11", 100),
            self.capture(2, "run@bb22"),
            self.summary(2, "run@bb22", 60),
        )

        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(len(report["roots"]), 1)
        self.assertEqual(
            report["roots"][0]["pair_status"], "PAIRED"
        )
        self.assertEqual(
            report["roots"][0]["node_count_delta_t2_minus_t1"],
            -40,
        )
        self.assertEqual(
            report["roots"][0]["tier_1"]["machine_code_bytes"],
            1001,
        )
        self.assertEqual(
            report["roots"][0]["tier_2"]["machine_code_bytes"],
            1002,
        )

    def test_missing_tier_is_not_zero(self):
        report = mg.ge.pair_compiled_root_tiers(
            self.capture(1, "run"),
            self.summary(1, "run", 100),
            None,
            None,
        )

        self.assertEqual(report["status"], "INCOMPATIBLE")
        self.assertEqual(
            report["roots"][0]["tier_2"]["status"],
            "UNAVAILABLE",
        )
        self.assertIsNone(
            report["roots"][0]["node_count_delta_t2_minus_t1"]
        )

    def test_different_producer_is_not_paired(self):
        report = mg.ge.pair_compiled_root_tiers(
            self.capture(1, "run", "producer-a"),
            self.summary(1, "run", 100),
            self.capture(2, "run", "producer-b"),
            self.summary(2, "run", 60),
        )

        self.assertFalse(
            report["producer_identity_compatible"]
        )
        self.assertEqual(
            report["roots"][0]["pair_status"],
            "PRODUCER_IDENTITY_MISMATCH",
        )

    def test_duplicate_normalized_identity_is_rejected(self):
        first = self.capture(1, "run@aa11")
        first["root_inventory"]["roots"].append({
            "target": "other-target",
            "label": "run@bb22",
            "normalized_label": "run@*",
            "status": "AVAILABLE",
            "cross_run_identity": "AMBIGUOUS",
        })

        report = mg.ge.pair_compiled_root_tiers(
            first,
            self.summary(1, "run@aa11", 100),
            self.capture(2, "run@cc33"),
            self.summary(2, "run@cc33", 60),
        )

        self.assertEqual(
            report["roots"][0]["pair_status"],
            "ROOT_IDENTITY_AMBIGUOUS",
        )
        self.assertIsNone(
            report["roots"][0]["node_count_delta_t2_minus_t1"]
        )


    def test_foreign_compilation_is_not_attributed_to_root(self):
        summary = self.summary(1, "run", 100)
        summary["units"][0]["comp_id"] = 999

        report = mg.ge.pair_compiled_root_tiers(
            self.capture(1, "run"),
            summary,
            self.capture(2, "run"),
            self.summary(2, "run", 60),
        )

        self.assertEqual(
            report["roots"][0]["tier_1"]["status"],
            "UNAVAILABLE",
        )
        self.assertEqual(
            report["roots"][0]["tier_1"]["reason"],
            "ROOT_COMPILATION_METADATA_NOT_UNIQUE",
        )
        self.assertIsNone(
            report["roots"][0]["node_count_delta_t2_minus_t1"]
        )

    def test_foreign_target_is_not_attributed_to_root(self):
        summary = self.summary(1, "run", 100)
        summary["units"][0]["target"] = "foreign-target"

        report = mg.ge.pair_compiled_root_tiers(
            self.capture(1, "run"),
            summary,
            self.capture(2, "run"),
            self.summary(2, "run", 60),
        )

        self.assertEqual(
            report["roots"][0]["tier_1"]["reason"],
            "ROOT_TARGET_MISMATCH",
        )


    def test_inconsistent_node_histogram_fails(self):
        summary = self.summary(1, "run", 100)
        summary["units"][0]["graph"][
            "node_class_histogram"
        ] = {"ExampleNode": 99}

        with self.assertRaises(mg.ge.EvidenceError):
            mg.ge.pair_compiled_root_tiers(
                self.capture(1, "run"),
                summary,
                self.capture(2, "run"),
                self.summary(2, "run", 60),
            )


class ColdPolicyTest(unittest.TestCase):
    def test_explicit_tier_thresholds(self):
        policy = mg.load_policy()
        options = mg.cold_jvm_options(
            policy, 1, 100, 1000000, Path("/tmp/graphs")
        )
        self.assertIn(
            "-Dpolyglot.engine.DynamicCompilationThresholds=false",
            options,
        )
        self.assertIn(
            "-Dpolyglot.engine.FirstTierCompilationThreshold=100",
            options,
        )
        self.assertIn(
            "-Dpolyglot.engine.LastTierCompilationThreshold=1000000",
            options,
        )

        with self.assertRaises(mp.UsageError):
            mg.cold_jvm_options(
                policy, 2, 100, 100, Path("/tmp/graphs")
            )

    def test_exact_invocation_sequence(self):
        args, sequence = mg.cold_invocation_arguments(
            "-", Path("/tmp/workload.mjs"), 25, 500
        )
        self.assertEqual(args[3:6], ["25", "500", "1"])
        self.assertEqual(sequence["cold_calls"], 1)
        self.assertEqual(sequence["warmup_calls"], 25)
        self.assertEqual(sequence["post_warmup_calls"], 500)
        self.assertEqual(
            sequence["total_measured_invocations"], 526
        )


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
            expected_policy = {
                "reference": {
                    "jfr": {"sample_calls": 1_000_000},
                    "timing": {
                        "warmup_iterations": (
                            150 if workload == "primitive-while-zero" else 50
                        ),
                        "steady_iterations": 10,
                        "sample_calls": (
                            1_000_000
                            if workload == "primitive-while-zero"
                            else 10_000
                        ),
                    },
                },
            }
            self.assertEqual(
                expected_policy,
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
            patch.dict(mg.os.environ, {"PODMAN": ""}),
            contextlib.redirect_stderr(stderr),
        ):
            code, output = self.run_cmd(
                "analyze", "--output", str(self.output)
            )

        self.assertEqual(mp.EXIT_USAGE, code)
        self.assertIn("CONTAINER_RUNTIME_NOT_FOUND", stderr.getvalue())
        self.assertIn("Linux host with Podman installed", stderr.getvalue())
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
            good = "harness/graph_evidence.py"
            mp.write_json(output / "w" / "js" / "capture.json", {"harness": {"source_sha256": {
                good: mp.sha256_file(ROOT / good), "harness/measure_graphs.py": "0" * 64}}})
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = mg.main(["verify", "--output", str(output)])
            self.assertEqual(1, code)
            self.assertIn("WORKING_TREE_MISMATCH=harness/measure_graphs.py", out.getvalue())
            self.assertNotIn(f"WORKING_TREE_MISMATCH={good}", out.getvalue())





class ColdCaptureIntegrationTest(unittest.TestCase):
    """Exercise cold capture with synthetic JVM traces and BGV files."""

    def run_fake_capture(
        self, requested_tier, root="run", with_helper=False
    ):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        output = Path(tmp.name) / "results"
        expected = "1"

        product = {
            "clean": True,
            "revision": "test-revision",
            "source_state_sha256": "test-source-state",
        }

        compilation = {
            "seq": 1,
            "target": "engine:1/target:7",
            "label": "run",
            "tier": 1,
            "comp_id": 42,
            "src": None,
            "ir_after_truffle_tier": 218,
            "ir_final": 365,
            "compilation_time_ms": 14,
            "truffle_compilation_ms": 11,
            "graal_compilation_ms": 3,
            "machine_code_bytes": 1386,
            "ast_nodes": 31,
            "inline_tree": [],
            "expansion": None,
        }

        parsed = {
            "compilations": [compilation],
            "failures": [],
            "invalidations": [],
            "option_rejections": [],
            "unknown_lifecycle_events": [],
        }

        bgv_name = "TruffleHotSpotCompilation-42[run].bgv"
        helper_bgv = None

        if with_helper:
            parsed["compilations"].append({
                **compilation,
                "seq": 2,
                "target": "engine:1/target:8",
                "label": "helper",
                "comp_id": 43,
            })
            helper_bgv = (
                "TruffleHotSpotCompilation-43[helper].bgv"
            )

        def fake_run_logged(command, log):
            log.parent.mkdir(parents=True, exist_ok=True)

            if "correctness" in command:
                text = f"result={expected}\\n"
            else:
                dumps = log.parent / "dumps"
                dumps.mkdir(exist_ok=True)
                (dumps / bgv_name).write_bytes(b"synthetic-bgv")
                if helper_bgv is not None:
                    (dumps / helper_bgv).write_bytes(
                        b"synthetic-helper-bgv"
                    )
                text = f"result={expected}\\n"

            text = text.replace(chr(92) + "n", "\n")
            log.write_text(text, encoding="utf-8")
            return 0, text

        runtime = {
            "runtime_cp": "/fake/classpath",
            "main_class": "FakeMain",
            "system_properties": [],
            "core_arg": "-",
            "classes": None,
        }

        args = argparse.Namespace(
            dir=Path(tmp.name),
            output=output,
            language="js",
            workload="primitive-return-literal",
            tier=requested_tier,
            root=root,
            warmup_calls=25,
            invocations=500,
            first_threshold=100,
            last_threshold=1000,
            jvm_option=[],
            cpu=None,
        )

        with (
            patch.object(
                mg.mp, "product_identity",
                return_value=product,
            ),
            patch.object(
                mg.mp, "harness_identity",
                return_value={
                    "git_head": "test",
                    "dirty": True,
                    "source_sha256": {},
                },
            ),
            patch.object(
                mg.mp, "producer_hashes",
                return_value={},
            ),
            patch.object(
                mg.mp, "java_identity",
                return_value={"java.runtime.version": "25"},
            ),
            patch.object(
                mg.mp, "choose_cpu",
                return_value=(0, [0], [0]),
            ),
            patch.object(
                mg.mp, "host_identity",
                return_value={"cpu": 0},
            ),
            patch.object(
                mg.mp, "prepare_surface_runtime",
                return_value=runtime,
            ),
            patch.object(
                mg.mp, "run_logged",
                side_effect=fake_run_logged,
            ),
            patch.object(
                mg.mp, "compare_product",
                return_value=[],
            ),
            patch.object(
                mg.mp.jvm_runtime,
                "harness_graalvm_version",
                return_value="25.4.4.1.1",
            ),
            patch.object(
                mg.mp.jvm_runtime,
                "peer_pom",
                return_value="<project/>",
            ),
            patch.object(
                mg.ge, "parse_trace",
                return_value=parsed,
            ),
            patch.object(
                mg.ge, "expansion_attribution",
                return_value=[],
            ),
        ):
            code = mg.cold_capture(args)

        destination = (
            output / "primitive-return-literal" / "js"
        )

        metadata = json.loads(
            (destination / "capture.json").read_text(
                encoding="utf-8"
            )
        )

        return code, metadata, destination, bgv_name


    def test_all_roots_retains_each_bgv(self):
        code, metadata, destination, _ = (
            self.run_fake_capture(
                1, root="all", with_helper=True
            )
        )

        self.assertEqual(code, mp.EXIT_OK)
        self.assertTrue(metadata["capture_valid"])
        self.assertEqual(
            metadata["requested_root"], "all"
        )

        self.assertEqual(
            len(metadata["selected_compilations"]), 2
        )
        self.assertEqual(
            len(metadata["runs"][0]["resolution"]["units"]), 2
        )
        self.assertEqual(
            len(metadata["runs"][0]["retained_bgv"]), 2
        )
        self.assertEqual(
            metadata["unavailable_roots"], []
        )

        for relative in metadata["runs"][0]["retained_bgv"]:
            self.assertTrue(
                (destination / relative).is_file()
            )

        self.assertEqual(
            metadata["timing_evidence"], "NONE"
        )

    def test_all_roots_missing_tier_is_recorded(self):
        code, metadata, destination, _ = (
            self.run_fake_capture(
                2, root="all", with_helper=True
            )
        )

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertFalse(metadata["capture_valid"])
        self.assertEqual(
            metadata["invalid_reason"],
            "NO_REQUESTED_TIER_BGV_AVAILABLE",
        )
        self.assertEqual(
            len(metadata["root_inventory"]["roots"]), 2
        )

        for item in metadata["root_inventory"]["roots"]:
            self.assertEqual(
                item["reason"],
                "REQUESTED_TIER_NOT_OBSERVED",
            )

        self.assertTrue(
            (destination / "raw/cold-jvm/trace.log").is_file()
        )

    def test_all_roots_summary_keeps_units_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)

            metadata = {
                "mode": "cold-compilation",
                "capture_valid": True,
                "requested_root": "all",
                "requested_tier": 1,
                "language": "protos",
                "workload": "factorial",
                "selected_phase": "After TruffleTier",
                "invocation_sequence": {
                    "process": "fresh-jvm",
                },
                "unavailable_roots": [],
                "root_inventory": {
                    "scope": "observed-compiled-call-targets-only",
                    "roots": [],
                },
                "runs": [{"budget": 100}],
            }

            units = [
                {
                    "label": "run",
                    "tier": 1,
                    "comp_id": 42,
                    "graph": {"node_count": 100},
                },
                {
                    "label": "helper",
                    "tier": 1,
                    "comp_id": 43,
                    "graph": {"node_count": 50},
                },
            ]

            with (
                patch.object(
                    mg,
                    "iter_cases",
                    return_value=[(directory, metadata)],
                ),
                patch.object(
                    mg,
                    "unit_graphs",
                    return_value=units,
                ),
            ):
                code = mg.cold_summarize(
                    argparse.Namespace(output=directory)
                )

            self.assertEqual(code, mp.EXIT_OK)

            summary = json.loads(
                (directory / "cold-summary.json").read_text()
            )

            self.assertEqual(
                summary["mode"], "cold-all-compiled-roots"
            )
            self.assertEqual(len(summary["units"]), 2)
            self.assertEqual(
                {
                    item["graph"]["node_count"]
                    for item in summary["units"]
                },
                {100, 50},
            )
            self.assertEqual(
                summary["timing_evidence"], "NONE"
            )


    def test_selected_tier_retains_exactly_one_bgv(self):
        code, metadata, destination, bgv_name = (
            self.run_fake_capture(1)
        )

        self.assertEqual(code, mp.EXIT_OK)
        self.assertTrue(metadata["capture_valid"])
        self.assertTrue(metadata["fresh_jvm"])
        self.assertTrue(
            metadata["correctness_uses_separate_jvm"]
        )
        self.assertEqual(
            metadata["selected_compilation"]["comp_id"], 42
        )
        self.assertEqual(
            metadata["selected_compilation"]["tier"], 1
        )
        self.assertEqual(
            metadata["invocation_sequence"]["warmup_calls"], 25
        )
        self.assertEqual(
            metadata["invocation_sequence"]["post_warmup_calls"],
            500,
        )

        runs = metadata["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(
            len(runs[0]["resolution"]["units"]), 1
        )
        self.assertEqual(
            len(runs[0]["retained_bgv"]), 1
        )

        retained = (
            destination / runs[0]["retained_bgv"][0]
        )
        self.assertTrue(retained.is_file())
        self.assertIn(bgv_name, retained.name)
        self.assertEqual(metadata["timing_evidence"], "NONE")

    def test_wrong_tier_is_invalid_not_relabeled(self):
        code, metadata, destination, _ = (
            self.run_fake_capture(2)
        )

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertFalse(metadata["capture_valid"])
        self.assertEqual(
            metadata["invalid_reason"],
            "REQUESTED_TIER_NOT_OBSERVED",
        )
        self.assertNotIn(
            "selected_compilation", metadata
        )
        self.assertTrue(
            (destination / "raw/cold-jvm/trace.log").is_file()
        )

    def test_existing_capture_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            mg.prepare_output(output)
            destination = (
                output / "primitive-return-literal" / "js"
            )
            destination.mkdir(parents=True)
            sentinel = destination / "user-result.json"
            sentinel.write_text("keep", encoding="utf-8")

            args = argparse.Namespace(
                dir=Path(tmp),
                output=output,
                workload="primitive-return-literal",
                language="js",
            )

            with self.assertRaises(mp.UsageError):
                mg.cold_capture(args)

            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "keep",
            )

    def test_cold_summary_uses_single_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            metadata = {
                "mode": "cold-compilation",
                "capture_valid": True,
                "language": "js",
                "workload": "primitive-return-literal",
                "selected_phase": "After TruffleTier",
                "selected_compilation": {
                    "tier": 1,
                    "comp_id": 42,
                },
                "invocation_sequence": {
                    "process": "fresh-jvm",
                },
                "runs": [{"budget": 500}],
            }

            units = [{
                "label": "run",
                "tier": 1,
                "comp_id": 42,
                "graph": {"node_count": 218},
                "bgv": "selected.bgv.gz",
                "analysis": "selected.filter.json.gz",
            }]

            with (
                patch.object(
                    mg, "iter_cases",
                    return_value=[(directory, metadata)],
                ),
                patch.object(
                    mg, "unit_graphs",
                    return_value=units,
                ),
            ):
                code = mg.cold_summarize(
                    argparse.Namespace(output=directory)
                )

            self.assertEqual(code, mp.EXIT_OK)
            summary = json.loads(
                (directory / "cold-summary.json").read_text()
            )
            self.assertEqual(summary["comp_id"], 42)
            self.assertEqual(summary["tier"], 1)
            self.assertEqual(
                summary["graph"]["node_count"], 218
            )
            self.assertEqual(
                summary["phase"], "After TruffleTier"
            )



class BytecodeHistogramLiveFormatTest(unittest.TestCase):
    @staticmethod
    def live_format(total=12):
        return "\n".join([
            "[engine] [bc] Instruction histogram for: "
            "com.guillermomolina.protos.execution.ProtosBytecodeRootNode",
            "------------------------------------------",
            "Count | Percent | Group / Instruction",
            "------------------------------------------",
            "12 | 100.0 | ▶ protos",
            "8 | 66.7 |   ▶ Root: ProtosBytecodeRootNodeGen@2a65bb85",
            "5 | 41.7 |     015 load.local$generic",
            "3 | 25.0 |     020 store.local$generic",
            "4 | 33.3 |   ▶ Root: ProtosBytecodeRootNodeGen@3d08f3f5",
            "4 | 33.3 |     006 load.constant",
            f"Total executed instructions: {total}",
        ])

    def test_real_engine_prefix_and_bare_language(self):
        from harness import graph_evidence as evidence

        parsed = evidence.parse_bytecode_histogram(
            self.live_format()
        )

        self.assertEqual(parsed["status"], "AVAILABLE")
        self.assertEqual(
            parsed["total_executed_instructions"], 12
        )
        self.assertEqual(len(parsed["groups"]), 2)
        self.assertEqual(
            {group["language"] for group in parsed["groups"]},
            {"protos"},
        )
        self.assertEqual(
            sorted(
                group["executed_instructions"]
                for group in parsed["groups"]
            ),
            [4, 8],
        )

    def test_real_format_rejects_incorrect_total(self):
        from harness import graph_evidence as evidence

        with self.assertRaises(evidence.EvidenceError):
            evidence.parse_bytecode_histogram(
                self.live_format(total=11)
            )


class BytecodeHistogramTest(unittest.TestCase):
    SAMPLE = """
[bc] Instruction histogram for: ProtosBytecodeRootNodeGen
-----------------------------------------
 Count | Percent | Group / Instruction
-----------------------------------------
     5 | 100.0 | ▶ Language: protos
     5 | 100.0 |   ▶ Root: ProtosRootNode@abc123
     3 |  60.0 |     00d load.local$Int$unboxed
     2 |  40.0 |     01b branch.backward
Total executed instructions: 5
"""

    def test_histogram_keeps_real_root_and_operations(self):
        result = mg.ge.parse_bytecode_histogram(self.SAMPLE)

        self.assertEqual(result["schema"], 1)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["total_executed_instructions"], 5)
        self.assertEqual(len(result["groups"]), 1)

        group = result["groups"][0]

        self.assertEqual(group["language"], "protos")
        self.assertEqual(group["root"], "ProtosRootNode@abc123")
        self.assertEqual(
            group["operation_counts"],
            {
                "branch.backward": 2,
                "load.local$Int$unboxed": 3,
            },
        )
        self.assertEqual(group["executed_instructions"], 5)

    def test_histogram_unavailable_is_not_zero(self):
        result = mg.ge.parse_bytecode_histogram(
            "result=1\n"
        )

        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(
            result["total_executed_instructions"]
        )
        self.assertEqual(result["groups"], [])

    def test_histogram_rejects_inconsistent_total(self):
        corrupted = self.SAMPLE.replace(
            "Total executed instructions: 5",
            "Total executed instructions: 99",
        )

        with self.assertRaises(mg.ge.EvidenceError):
            mg.ge.parse_bytecode_histogram(corrupted)

    def test_histogram_keeps_roots_separate(self):
        sample = self.SAMPLE.replace(
            "Total executed instructions: 5",
            """     4 | 100.0 |   ▶ Root: OtherRoot@def456
     4 | 100.0 |     00d load.local$Int$unboxed
Total executed instructions: 9""",
        )

        result = mg.ge.parse_bytecode_histogram(sample)

        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(len(result["groups"]), 2)
        self.assertEqual(
            result["total_executed_instructions"], 9
        )
        self.assertEqual(
            sorted(
                group["executed_instructions"]
                for group in result["groups"]
            ),
            [4, 5],
        )





class StructuralReportPhysicalV2ContractTest(unittest.TestCase):
    @staticmethod
    def run_report(evidence):
        import argparse
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bytecode = root / "bytecode"
            capture = bytecode / "factorial/protos/capture.json"

            capture.parent.mkdir(parents=True)
            capture.write_text("{}", encoding="utf-8")

            output = root / "report"

            args = argparse.Namespace(
                tier1=root / "missing-tier1",
                tier2=root / "missing-tier2",
                bytecode=bytecode,
                output=output,
                workload="factorial",
                language="protos",
            )

            with patch.object(
                mg,
                "read_structural_bytecode",
                return_value=evidence,
            ):
                code = mg.structural_report(args)

            report_path = (
                output / "factorial/protos/structural-report.json"
            )

            report = json.loads(
                report_path.read_text(encoding="utf-8")
            )

            return code, report

    @staticmethod
    def evidence_with_size():
        label = "ProtosBytecodeRootNodeGen@abcd"

        return {
            "status": "UNATTRIBUTABLE",
            "reason": "NO_VALID_GRAPH_PRODUCER",
            "capture_status": "AVAILABLE",
            "groups": [{
                "language": "protos",
                "root": label,
                "executed_instructions": 20,
            }],
            "total_executed_instructions": 20,
            "size_evidence": {
                "status": "AVAILABLE",
                "unit": "bytes",
                "observations": [{
                    "root_name": "factorial",
                    "root_instance": 1,
                    "physical_root_label": label,
                    "bytecode_tier": "CACHED",
                    "instruction_count": 3,
                    "bytecode_bytes": 12,
                    "first_bci": 0,
                    "last_end_bci": 12,
                }],
            },
        }

    def test_report_preserves_physical_join_without_graph_tiers(self):
        code, report = self.run_report(
            self.evidence_with_size()
        )

        physical = report["bytecode_dsl"][
            "physical_root_attribution"
        ]

        self.assertNotEqual(code, 0)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["timing_evidence"], "NONE")
        self.assertEqual(physical["status"], "COMPLETE")
        self.assertEqual(physical["matched_roots"], 1)
        self.assertEqual(
            physical["compiler_tier_equivalence"],
            "NONE",
        )

        entry = physical["per_histogram_root"][0]

        self.assertEqual(
            entry["histogram_group"]["executed_instructions"],
            20,
        )
        self.assertEqual(
            entry["interpreter_states"]["CACHED"]["bytecode_bytes"],
            12,
        )
        self.assertEqual(
            entry["interpreter_states"]["UNCACHED"]["status"],
            "UNAVAILABLE",
        )

    def test_missing_size_is_explicit_in_report(self):
        evidence = self.evidence_with_size()

        evidence["size_evidence"] = {
            "status": "UNAVAILABLE",
            "reason": "NO_BYTECODE_SIZE_RECORDS",
            "observations": [],
        }

        code, report = self.run_report(evidence)

        physical = report["bytecode_dsl"][
            "physical_root_attribution"
        ]

        self.assertNotEqual(code, 0)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(physical["status"], "UNAVAILABLE")
        self.assertEqual(
            physical["reason"],
            "NO_BYTECODE_SIZE_RECORDS",
        )
        self.assertEqual(
            physical["per_histogram_root"],
            [],
        )


class StructuralReportCommandTest(unittest.TestCase):
    def test_missing_capture_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            capture, summary, info = (
                mg.read_structural_input(
                    directory,
                    "factorial",
                    "protos",
                    1,
                )
            )

            self.assertIsNone(capture)
            self.assertIsNone(summary)
            self.assertEqual(
                info["status"], "MISSING"
            )
            self.assertEqual(
                info["reason"], "CAPTURE_NOT_FOUND"
            )

    def test_corrupt_bgv_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            mp.write_json(
                directory / "capture.json",
                {
                    "mode": "cold-compilation",
                    "workload": "factorial",
                    "language": "protos",
                    "requested_tier": 1,
                    "requested_root": "all",
                    "selected_phase": "After TruffleTier",
                    "capture_valid": True,
                    "harness": {
                        "source_sha256": {
                            "test": "abc"
                        }
                    },
                    "harness_after_source_sha256": {
                        "test": "abc"
                    },
                },
            )

            bgv = directory / "one.bgv.gz"

            with gzip.open(bgv, "wb") as stream:
                stream.write(b"example")

            mp.write_json(
                directory / "cold-summary.json",
                {
                    "mode": "cold-all-compiled-roots",
                    "workload": "factorial",
                    "language": "protos",
                    "requested_tier": 1,
                    "phase": "After TruffleTier",
                    "units": [
                        {
                            "bgv": "one.bgv.gz",
                            "bgv_sha256": "0" * 64,
                            "analysis": (
                                "one.filter.json.gz"
                            ),
                        }
                    ],
                },
            )

            # The analysis path must exist so the BGV
            # digest check is the decisive failure.
            (directory / "one.filter.json.gz").write_bytes(
                b"placeholder"
            )

            _, summary, info = (
                mg.read_structural_input(
                    directory,
                    "factorial",
                    "protos",
                    1,
                )
            )

            self.assertIsNone(summary)
            self.assertEqual(
                info["status"], "INVALID"
            )
            self.assertEqual(
                info["reason"], "BGV_SHA256_MISMATCH"
            )

    def test_derived_report_does_not_rewrite_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tier1 = root / "tier1"
            tier2 = root / "tier2"
            output = root / "report"

            input_dir = (
                tier1 / "factorial" / "protos"
            )

            mp.write_json(
                input_dir / "capture.json",
                {
                    "mode": "cold-compilation",
                    "workload": "factorial",
                    "language": "protos",
                    "requested_tier": 1,
                    "requested_root": "all",
                    "capture_valid": False,
                    "invalid_reason": (
                        "NO_REQUESTED_TIER_BGV_AVAILABLE"
                    ),
                },
            )

            before = (
                input_dir / "capture.json"
            ).read_bytes()

            args = argparse.Namespace(
                tier1=tier1,
                tier2=tier2,
                bytecode=root / "bytecode",
                output=output,
                workload="factorial",
                language="protos",
            )

            with patch.object(
                mg.ge,
                "pair_compiled_root_tiers",
                return_value={
                    "status": "PARTIAL",
                    "roots": [],
                },
            ):
                code = mg.structural_report(args)

            self.assertEqual(code, mp.EXIT_INVALID)

            report = json.loads(
                (
                    output / "factorial" / "protos"
                    / "structural-report.json"
                ).read_text()
            )

            self.assertEqual(
                report["status"], "INCOMPLETE"
            )
            self.assertEqual(
                report["tier_1"]["status"],
                "INVALID",
            )
            self.assertEqual(
                report["tier_2"]["status"],
                "MISSING",
            )
            self.assertEqual(
                (
                    input_dir / "capture.json"
                ).read_bytes(),
                before,
            )
            self.assertFalse(tier2.exists())




class StructuralBytecodeAttributionTest(unittest.TestCase):
    def sample_group(self, root):
        return {
            "interpreter": "Protos",
            "language": "protos",
            "root": root,
            "normalized_root": root,
            "operation_counts": {
                "ADD": 7,
                "RETURN": 7,
            },
            "executed_instructions": 14,
        }

    def pairing(self):
        return {
            "status": "COMPLETE",
            "producer_identity_compatible": True,
            "roots": [
                {"normalized_root": "run"},
                {"normalized_root": "helper"},
            ],
        }

    def test_groups_are_attributed_per_root(self):
        histogram = {
            "status": "AVAILABLE",
            "groups": [
                self.sample_group("run"),
                self.sample_group("helper"),
            ],
        }

        result = mg.attribute_bytecode_groups(
            self.pairing(),
            histogram,
        )

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(
            len(result["per_compiled_root"]), 2
        )
        self.assertEqual(
            result["per_compiled_root"][0]["status"],
            "AVAILABLE",
        )
        self.assertEqual(
            result["per_compiled_root"][0]["groups"][0][
                "operation_counts"
            ]["ADD"],
            7,
        )
        self.assertIsNone(
            result["bytecode_size_bytes"]
        )

    def test_missing_root_is_not_zero(self):
        result = mg.attribute_bytecode_groups(
            self.pairing(),
            {
                "status": "AVAILABLE",
                "groups": [
                    self.sample_group("run")
                ],
            },
        )

        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(
            result["per_compiled_root"][1]["status"],
            "UNAVAILABLE",
        )
        self.assertEqual(
            result["per_compiled_root"][1]["reason"],
            "BYTECODE_ROOT_NOT_OBSERVED",
        )

    def test_ambiguous_root_is_not_attributed(self):
        result = mg.attribute_bytecode_groups(
            self.pairing(),
            {
                "status": "AVAILABLE",
                "groups": [
                    self.sample_group("run"),
                    {
                        **self.sample_group("run"),
                        "interpreter": "AnotherInterpreter",
                    },
                ],
            },
        )

        self.assertEqual(
            result["per_compiled_root"][0]["status"],
            "AMBIGUOUS",
        )
        self.assertEqual(
            len(result["unattributed_groups"]), 2
        )

    def test_incompatible_graphs_are_not_joined(self):
        pairing = self.pairing()
        pairing["producer_identity_compatible"] = False

        result = mg.attribute_bytecode_groups(
            pairing,
            {
                "status": "AVAILABLE",
                "groups": [
                    self.sample_group("run")
                ],
            },
        )

        self.assertEqual(
            result["status"], "UNAVAILABLE"
        )
        self.assertEqual(
            result["reason"],
            "GRAPH_TIERS_NOT_COMPATIBLE",
        )

    def test_modified_raw_log_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw = directory / "raw"
            raw.mkdir()

            log = raw / "bytecode-histogram.log"
            log.write_text(
                "result=1",
                encoding="utf-8",
            )

            mp.write_json(
                directory / "capture.json",
                {
                    "mode": "bytecode-diagnostic",
                    "workload": "factorial",
                    "language": "protos",
                    "capture_valid": True,
                    "bytecode": {
                        "status": "AVAILABLE",
                        "raw_log": (
                            "raw/bytecode-histogram.log"
                        ),
                        "raw_log_sha256": "0" * 64,
                        "histogram": {
                            "status": "AVAILABLE",
                            "groups": [],
                        },
                    },
                },
            )

            result = mg.read_structural_bytecode(
                directory,
                "factorial",
                "protos",
                (None, None),
            )

            self.assertEqual(
                result["status"], "INVALID"
            )
            self.assertEqual(
                result["reason"],
                "BYTECODE_RAW_LOG_SHA256_MISMATCH",
            )




class StructuralBytecodeSizeAttributionTest(unittest.TestCase):
    """Preserve exact interpreter-state snapshots per physical root."""

    def pairing(self, names=("factorial",), compatible=True):
        return {
            "producer_identity_compatible": compatible,
            "roots": [
                {"normalized_root": name}
                for name in names
            ],
        }

    def observation(
        self,
        root="factorial",
        instance=1,
        state="UNCACHED",
        size=20,
        instructions=4,
    ):
        return {
            "root_name": root,
            "root_instance": instance,
            "bytecode_tier": state,
            "instruction_count": instructions,
            "bytecode_bytes": size,
            "first_bci": 0,
            "last_end_bci": size,
        }

    def evidence(self, observations):
        return {
            "status": "AVAILABLE",
            "size_evidence": {
                "status": "AVAILABLE",
                "source": "TRUFFLE_INSTRUCTION_LENGTH",
                "unit": "bytes",
                "scope": "OBSERVED_INSTRUMENTED_ROOTS",
                "observations": observations,
            },
        }

    def test_uncached_and_cached_are_independent(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(),
            self.evidence([
                self.observation(state="UNCACHED", size=20),
                self.observation(state="CACHED", size=24),
            ]),
        )

        self.assertEqual(report["status"], "COMPLETE")
        root = report["per_compiled_root"][0]
        self.assertEqual(root["root_instance"], 1)

        states = root["interpreter_states"]
        self.assertEqual(states["UNCACHED"]["bytecode_bytes"], 20)
        self.assertEqual(states["CACHED"]["bytecode_bytes"], 24)
        self.assertEqual(states["UNCACHED"]["instruction_count"], 4)
        self.assertEqual(report["compiler_tier_equivalence"], "NONE")

    def test_missing_cached_is_not_zero(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(),
            self.evidence([self.observation()]),
        )

        self.assertEqual(report["status"], "PARTIAL")
        root = report["per_compiled_root"][0]
        self.assertEqual(root["status"], "PARTIAL")

        cached = root["interpreter_states"]["CACHED"]
        self.assertEqual(cached["status"], "UNAVAILABLE")
        self.assertIsNone(cached["bytecode_bytes"])
        self.assertIsNone(cached["instruction_count"])

    def test_changed_snapshot_is_variable(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(),
            self.evidence([
                self.observation(size=20),
                self.observation(size=24),
                self.observation(state="CACHED", size=28),
            ]),
        )

        root = report["per_compiled_root"][0]
        self.assertEqual(root["status"], "VARIABLE")
        uncached = root["interpreter_states"]["UNCACHED"]
        self.assertEqual(uncached["status"], "VARIABLE")
        self.assertIsNone(uncached["bytecode_bytes"])
        self.assertEqual(len(uncached["snapshots"]), 2)
        self.assertEqual(
            root["interpreter_states"]["CACHED"]["bytecode_bytes"],
            28,
        )

    def test_two_physical_instances_are_ambiguous(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(),
            self.evidence([
                self.observation(instance=1),
                self.observation(instance=2),
            ]),
        )

        root = report["per_compiled_root"][0]
        self.assertEqual(root["status"], "AMBIGUOUS")
        self.assertIsNone(root["root_instance"])
        self.assertEqual(root["observed_root_instances"], [1, 2])
        self.assertEqual(len(report["unattributed_observations"]), 2)

    def test_duplicate_compiled_identity_is_ambiguous(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(("factorial", "factorial")),
            self.evidence([self.observation()]),
        )

        self.assertEqual(report["status"], "PARTIAL")
        self.assertTrue(all(
            item["status"] == "AMBIGUOUS"
            for item in report["per_compiled_root"]
        ))
        self.assertEqual(len(report["unattributed_observations"]), 1)

    def test_incompatible_producers_are_not_joined(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(compatible=False),
            self.evidence([self.observation()]),
        )

        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(
            report["reason"],
            "GRAPH_TIERS_NOT_COMPATIBLE",
        )
        self.assertEqual(len(report["unattributed_observations"]), 1)

    def test_unmatched_root_is_retained(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(),
            self.evidence([
                self.observation(root="other"),
            ]),
        )

        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(
            report["per_compiled_root"][0]["status"],
            "UNAVAILABLE",
        )
        self.assertEqual(len(report["unattributed_observations"]), 1)

    def test_missing_size_evidence_is_explicit(self):
        report = mg.attribute_bytecode_sizes(
            self.pairing(),
            {"status": "AVAILABLE"},
        )

        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(
            report["reason"],
            "BYTECODE_SIZE_EVIDENCE_MISSING",
        )



if __name__ == "__main__":
    unittest.main()



import base64 as _bytecode_size_base64
import graph_evidence as _bytecode_size_evidence



class BytecodeSizeV2IdentityTest(unittest.TestCase):
    @staticmethod
    def record(label, instance=1):
        import base64

        return "\t".join([
            "BENCH_BYTECODE_SIZE_V2",
            base64.b64encode(
                b"com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen"
            ).decode("ascii"),
            str(instance),
            "UNCACHED",
            "4",
            "23",
            "0",
            "23",
            base64.b64encode(
                label.encode("utf-8")
            ).decode("ascii"),
        ])

    def test_physical_identity_is_retained(self):
        from harness import graph_evidence as evidence

        parsed = evidence.parse_bytecode_size_trace(
            self.record("ProtosBytecodeRootNodeGen@2a65bb85")
        )

        self.assertEqual(parsed["status"], "AVAILABLE")
        self.assertEqual(
            parsed["observations"][0]["physical_root_label"],
            "ProtosBytecodeRootNodeGen@2a65bb85",
        )

    def test_conflicting_instance_identity_is_rejected(self):
        from harness import graph_evidence as evidence

        raw = "\n".join([
            self.record("ProtosBytecodeRootNodeGen@111", 1),
            self.record("ProtosBytecodeRootNodeGen@222", 1),
        ])

        with self.assertRaises(evidence.EvidenceError):
            evidence.parse_bytecode_size_trace(raw)

    def test_physical_handle_collision_is_rejected(self):
        from harness import graph_evidence as evidence

        raw = "\n".join([
            self.record("ProtosBytecodeRootNodeGen@111", 1),
            self.record("ProtosBytecodeRootNodeGen@111", 2),
        ])

        with self.assertRaises(evidence.EvidenceError):
            evidence.parse_bytecode_size_trace(raw)

    def test_malformed_physical_label_is_rejected(self):
        from harness import graph_evidence as evidence

        with self.assertRaises(evidence.EvidenceError):
            evidence.parse_bytecode_size_trace(
                self.record("unknown physical root")
            )


class BytecodeSizeEvidenceTest(unittest.TestCase):

    @staticmethod
    def record(
        name="factorial",
        instance=1,
        tier="CACHED",
        instructions=4,
        size=20,
        start=0,
    ):
        encoded = _bytecode_size_base64.b64encode(
            name.encode("utf-8")
        ).decode("ascii")

        return "\\t".join([
            "BENCH_BYTECODE_SIZE_V2",
            encoded,
            str(instance),
            tier,
            str(instructions),
            str(size),
            str(start),
            str(start + size),
            _bytecode_size_base64.b64encode(
                f"ProtosBytecodeRootNodeGen@{instance:x}".encode("utf-8")
            ).decode("ascii"),
        ]).replace("\\t", "\t")

    def test_exact_bytes_and_instruction_count_are_separate(self):
        parsed = _bytecode_size_evidence.parse_bytecode_size_trace(
            self.record(instructions=4, size=23)
        )

        self.assertEqual(parsed["status"], "AVAILABLE")
        self.assertEqual(parsed["unit"], "bytes")
        self.assertEqual(
            parsed["observations"][0]["instruction_count"], 4
        )
        self.assertEqual(
            parsed["observations"][0]["bytecode_bytes"], 23
        )

    def test_physical_root_instances_remain_separate(self):
        parsed = _bytecode_size_evidence.parse_bytecode_size_trace(
            self.record(instance=1)
            + "\n"
            + self.record(instance=2)
        )

        self.assertEqual(len(parsed["observations"]), 2)

    def test_uncached_and_cached_snapshots_remain_separate(self):
        parsed = _bytecode_size_evidence.parse_bytecode_size_trace(
            self.record(tier="UNCACHED", size=20)
            + "\n"
            + self.record(tier="CACHED", size=24)
        )

        self.assertEqual(len(parsed["observations"]), 2)
        self.assertEqual(
            {
                entry["bytecode_tier"]
                for entry in parsed["observations"]
            },
            {"UNCACHED", "CACHED"},
        )

    def test_changed_snapshot_is_not_silently_collapsed(self):
        parsed = _bytecode_size_evidence.parse_bytecode_size_trace(
            self.record(size=20)
            + "\n"
            + self.record(size=24)
            + "\n"
            + self.record(size=24)
        )

        self.assertEqual(len(parsed["observations"]), 2)

    def test_absent_bytecode_size_is_not_zero(self):
        parsed = _bytecode_size_evidence.parse_bytecode_size_trace(
            "unrelated diagnostic output"
        )

        self.assertEqual(parsed["status"], "UNAVAILABLE")
        self.assertEqual(parsed["observations"], [])

    def test_inconsistent_bytecode_size_is_rejected(self):
        record = self.record(size=20)
        inconsistent = record.rsplit("\t", 1)[0] + "\t19"

        with self.assertRaises(
            _bytecode_size_evidence.EvidenceError
        ):
            _bytecode_size_evidence.parse_bytecode_size_trace(
                inconsistent
            )

    def test_malformed_size_record_is_rejected(self):
        with self.assertRaises(
            _bytecode_size_evidence.EvidenceError
        ):
            _bytecode_size_evidence.parse_bytecode_size_trace(
                "BENCH_BYTECODE_SIZE_V2\tbroken"
            )



import bytecode_size_runtime as _bytecode_size_runtime


class BytecodeInstrumentBuildTest(unittest.TestCase):

    def test_runtime_version_comes_from_exact_truffle_jar(self):
        version = _bytecode_size_runtime.runtime_truffle_version(
            "/tmp/truffle-api-25.4.4.1.1.jar"
        )
        self.assertEqual(version, "25.4.4.1.1")

    def test_missing_truffle_api_version_fails_closed(self):
        with self.assertRaises(
            _bytecode_size_runtime.InstrumentError
        ):
            _bytecode_size_runtime.runtime_truffle_version(
                "/tmp/polyglot-25.4.4.1.1.jar"
            )

    def test_processor_must_be_prepared(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(
                _bytecode_size_runtime.InstrumentError
            ):
                _bytecode_size_runtime.processor_jar(
                    "25.4.4.1.1",
                    Path(directory),
                )

    def test_java_instrument_exposes_option_descriptors(self):
        source = (
            ROOT
            / "harness/instruments/BytecodeSizeInstrument.java"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "BytecodeSizeInstrumentOptionDescriptors",
            source,
        )
        self.assertIn(
            'id = "bench-bytecode-size"',
            source,
        )
        self.assertIn(
            "instruction.getLength()",
            source,
        )



class BytecodeInstrumentCompileCommandTest(unittest.TestCase):

    def test_compile_peer_uses_prepared_classpath(self):
        output = io.StringIO()
        compiled = {
            "status": "COMPILED",
            "classes": Path("/tmp/bytecode-classes"),
            "version": "25.4.4.1.1",
            "cache_key": "abc123",
        }

        with (
            patch.object(
                sys,
                "argv",
                [
                    "bytecode_size_runtime.py",
                    "compile-peer",
                    "--version",
                    "25.4.4.1.1",
                ],
            ),
            patch(
                "measure_protos.peer_classpath",
                return_value=(
                    "25.4.4.1.1",
                    "/tmp/truffle-api-25.4.4.1.1.jar",
                ),
            ) as peer,
            patch.object(
                _bytecode_size_runtime,
                "compile_instrument",
                return_value=compiled,
            ) as compile_call,
            contextlib.redirect_stdout(output),
        ):
            _bytecode_size_runtime.main()

        peer.assert_called_once_with("25.4.4.1.1")
        compile_call.assert_called_once_with(
            "/tmp/truffle-api-25.4.4.1.1.jar"
        )

        self.assertIn(
            "BYTECODE_INSTRUMENT_COMPILED=YES",
            output.getvalue(),
        )

    def test_compile_peer_rejects_version_mismatch(self):
        with (
            patch.object(
                sys,
                "argv",
                [
                    "bytecode_size_runtime.py",
                    "compile-peer",
                    "--version",
                    "25.4.4.1.1",
                ],
            ),
            patch(
                "measure_protos.peer_classpath",
                return_value=("25.0.1", "/tmp/peer"),
            ),
            patch.object(
                _bytecode_size_runtime,
                "compile_instrument",
            ) as compile_call,
        ):
            with self.assertRaises(
                _bytecode_size_runtime.InstrumentError
            ):
                _bytecode_size_runtime.main()

        compile_call.assert_not_called()



class BytecodeSizeDiagnosticIntegrationTest(unittest.TestCase):

    def test_diagnostic_activates_instrument_and_keeps_bytes(self):
        import base64

        encoded = base64.b64encode(
            b"factorial"
        ).decode("ascii")

        record = "\t".join([
            "BENCH_BYTECODE_SIZE_V2",
            encoded,
            "1",
            "CACHED",
            "3",
            "12",
            "0",
            "12",
            base64.b64encode(
                b"ProtosBytecodeRootNodeGen@1"
            ).decode("ascii"),
        ])

        runtime = {
            "runtime_cp": "/tmp/truffle-api-25.4.4.1.1.jar",
            "main_class": "BenchmarkMain",
            "system_properties": [],
            "core_arg": "-",
        }

        compiled = {
            "classes": Path("/tmp/instrument-classes"),
            "version": "25.4.4.1.1",
            "cache_key": "test-cache",
            "processor_sha256": "processor-hash",
        }

        with (
            patch.object(
                mg.bsr,
                "compile_instrument",
                return_value=compiled,
            ),
            patch.object(
                mp,
                "java_command",
                return_value=["java", "diagnostic"],
            ) as java_command,
            patch.object(
                mp,
                "run_logged",
                return_value=(
                    0,
                    "result=1\n" + record + "\n",
                ),
            ),
            patch.object(
                mp,
                "sha256_file",
                return_value="raw-log-hash",
            ),
        ):
            result = mg.run_bytecode_diagnostic(
                runtime,
                Path("/tmp/factorial.mjs"),
                "1",
                100,
                0,
                Path("/tmp/bytecode.log"),
            )

        self.assertIn(
            "/tmp/instrument-classes",
            java_command.call_args.args[0],
        )

        self.assertIn(
            "-Dpolyglot.bench-bytecode-size=true",
            java_command.call_args.args[3],
        )

        self.assertEqual(
            result["size"]["status"],
            "AVAILABLE",
        )

        self.assertEqual(
            result["size"]["observations"][0]["bytecode_bytes"],
            12,
        )

        self.assertEqual(
            result["timing_evidence"],
            "NONE",
        )

    def test_unavailable_size_is_not_zero(self):
        runtime = {
            "runtime_cp": "synthetic-classpath",
            "main_class": "BenchmarkMain",
            "system_properties": [],
            "core_arg": "-",
        }

        with (
            patch.object(
                mg.bsr,
                "compile_instrument",
                side_effect=mg.bsr.InstrumentError(
                    "TRUFFLE_API_VERSION_UNRESOLVED"
                ),
            ),
            patch.object(
                mp,
                "java_command",
                return_value=["java", "diagnostic"],
            ),
            patch.object(
                mp,
                "run_logged",
                return_value=(0, "result=1\n"),
            ),
            patch.object(
                mp,
                "sha256_file",
                return_value="raw-log-hash",
            ),
        ):
            result = mg.run_bytecode_diagnostic(
                runtime,
                Path("/tmp/factorial.mjs"),
                "1",
                100,
                0,
                Path("/tmp/bytecode.log"),
            )

        self.assertEqual(
            result["size"]["status"],
            "UNAVAILABLE",
        )
        self.assertEqual(
            result["size"]["observations"],
            [],
        )




class PhysicalBytecodeRootAttributionTest(unittest.TestCase):
    @staticmethod
    def observation(label, instance=1, tier="CACHED", size=12):
        return {
            "root_name": "factorial",
            "physical_root_label": label,
            "root_instance": instance,
            "bytecode_tier": tier,
            "instruction_count": 3,
            "bytecode_bytes": size,
            "first_bci": 0,
            "last_end_bci": size,
        }

    @staticmethod
    def evidence(roots, observations, status="UNATTRIBUTABLE"):
        return {
            "status": status,
            "capture_status": "AVAILABLE",
            "groups": [
                {
                    "root": root,
                    "language": "protos",
                    "executed_instructions": count,
                }
                for root, count in roots
            ],
            "size_evidence": {
                "status": "AVAILABLE",
                "observations": observations,
            },
        }

    def test_exact_physical_roots_join_without_graph_producer(self):
        first = "ProtosBytecodeRootNodeGen@abcd"
        second = "ProtosBytecodeRootNodeGen@ef01"

        result = mg.attribute_physical_bytecode_roots(
            self.evidence(
                [(first, 30), (second, 70)],
                [
                    self.observation(first, 1, "UNCACHED", 12),
                    self.observation(first, 1, "CACHED", 15),
                    self.observation(second, 2, "CACHED", 25),
                ],
            )
        )

        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["matched_roots"], 2)
        self.assertEqual(result["histogram_roots"], 2)
        self.assertEqual(result["size_roots"], 2)

        entries = {
            item["physical_root_label"]: item
            for item in result["per_histogram_root"]
        }

        self.assertEqual(
            entries[first]["histogram_group"]["executed_instructions"],
            30,
        )
        self.assertEqual(
            entries[first]["interpreter_states"]["UNCACHED"]["bytecode_bytes"],
            12,
        )
        self.assertEqual(
            entries[first]["interpreter_states"]["CACHED"]["bytecode_bytes"],
            15,
        )
        self.assertEqual(
            entries[second]["interpreter_states"]["UNCACHED"]["status"],
            "UNAVAILABLE",
        )
        self.assertEqual(result["compiled_root_identity"], "NOT_ESTABLISHED")

    def test_changed_snapshots_remain_variable(self):
        label = "ProtosBytecodeRootNodeGen@abcd"

        result = mg.attribute_physical_bytecode_roots(
            self.evidence(
                [(label, 10)],
                [
                    self.observation(label, size=12),
                    self.observation(label, size=16),
                ],
            )
        )

        self.assertEqual(result["status"], "COMPLETE")
        cached = result["per_histogram_root"][0][
            "interpreter_states"
        ]["CACHED"]

        self.assertEqual(cached["status"], "VARIABLE")
        self.assertIsNone(cached["bytecode_bytes"])
        self.assertEqual(len(cached["snapshots"]), 2)

    def test_missing_and_extra_roots_are_not_silently_joined(self):
        first = "ProtosBytecodeRootNodeGen@abcd"
        missing = "ProtosBytecodeRootNodeGen@ef01"
        extra = "ProtosBytecodeRootNodeGen@beef"

        result = mg.attribute_physical_bytecode_roots(
            self.evidence(
                [(first, 10), (missing, 20)],
                [
                    self.observation(first),
                    self.observation(extra, instance=3),
                ],
            )
        )

        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["matched_roots"], 1)
        self.assertEqual(
            result["per_histogram_root"][1]["status"],
            "UNAVAILABLE",
        )
        self.assertEqual(
            len(result["unattributed_size_observations"]), 1
        )

    def test_colliding_physical_root_instances_are_rejected(self):
        label = "ProtosBytecodeRootNodeGen@abcd"

        result = mg.attribute_physical_bytecode_roots(
            self.evidence(
                [(label, 10)],
                [
                    self.observation(label, instance=1),
                    self.observation(label, instance=2),
                ],
            )
        )

        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(
            result["reason"],
            "BYTECODE_SIZE_PHYSICAL_IDENTITY_COLLISION",
        )

    def test_duplicate_histogram_identity_is_rejected(self):
        label = "ProtosBytecodeRootNodeGen@abcd"

        result = mg.attribute_physical_bytecode_roots(
            self.evidence(
                [(label, 10), (label, 20)],
                [self.observation(label)],
            )
        )

        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(
            result["reason"],
            "DUPLICATE_HISTOGRAM_PHYSICAL_ROOT",
        )


class StructuralBytecodeSizeIntegrityTest(unittest.TestCase):

    def test_diagnostic_only_producer_files_are_allowed(self):
        graph = {
            "harness/measure_graphs.py": "same-hash",
            "harness/graph_evidence.py": "same-hash-2",
        }

        diagnostic = {
            **graph,
            "harness/bytecode_size_runtime.py": "helper-hash",
            "harness/instruments/BytecodeSizeInstrument.java": (
                "instrument-hash"
            ),
        }

        self.assertTrue(
            mg.compatible_bytecode_harness_hashes(
                graph,
                diagnostic,
                require_size_instrument=True,
            )
        )

    def test_shared_producer_mismatch_is_rejected(self):
        graph = {
            "harness/measure_graphs.py": "graph-hash",
        }

        diagnostic = {
            "harness/measure_graphs.py": "different-hash",
            "harness/bytecode_size_runtime.py": "helper-hash",
            "harness/instruments/BytecodeSizeInstrument.java": (
                "instrument-hash"
            ),
        }

        self.assertFalse(
            mg.compatible_bytecode_harness_hashes(
                graph,
                diagnostic,
                require_size_instrument=True,
            )
        )

    def test_modified_stored_size_is_not_accepted(self):
        import base64

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            raw_dir = destination / "raw"
            raw_dir.mkdir()

            encoded = base64.b64encode(
                b"factorial"
            ).decode("ascii")

            record = "\t".join([
                "BENCH_BYTECODE_SIZE_V2",
                encoded,
                "1",
                "CACHED",
                "3",
                "12",
                "0",
                "12",
                base64.b64encode(
                    b"ProtosBytecodeRootNodeGen@1"
                ).decode("ascii"),
            ])

            raw_text = "result=1\n" + record + "\n"
            raw = raw_dir / "bytecode-histogram.log"
            raw.write_text(
                raw_text,
                encoding="utf-8",
            )

            histogram = mg.ge.parse_bytecode_histogram(
                raw_text
            )

            size = mg.ge.parse_bytecode_size_trace(
                raw_text
            )

            size["observations"][0]["bytecode_bytes"] = 13

            capture = {
                "mode": "bytecode-diagnostic",
                "workload": "factorial",
                "language": "protos",
                "capture_valid": True,
                "bytecode": {
                    "status": histogram["status"],
                    "histogram": histogram,
                    "size": size,
                    "size_instrument": {
                        "status": "AVAILABLE",
                    },
                    "raw_log": (
                        "raw/bytecode-histogram.log"
                    ),
                    "raw_log_sha256": mp.sha256_file(raw),
                },
            }

            (destination / "capture.json").write_text(
                json.dumps(capture),
                encoding="utf-8",
            )

            result = mg.read_structural_bytecode(
                destination,
                "factorial",
                "protos",
                (None, None),
            )

            self.assertEqual(
                result["status"],
                "INVALID",
            )

            self.assertEqual(
                result["reason"],
                "BYTECODE_SIZE_DIFFERS_FROM_RAW_LOG",
            )
