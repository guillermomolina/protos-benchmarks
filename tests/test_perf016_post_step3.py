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

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runner/perf016_post_step3.py"
spec = importlib.util.spec_from_file_location("perf016_post_step3", MODULE_PATH)
perf016 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(perf016)


@contextlib.contextmanager
def captured_stdout():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(["docker"], returncode, stdout, stderr)


def timing_payload(warmup, steady, **overrides):
    payload = {
        "schema_version": 1,
        "mode": "timing",
        "expected": "42",
        "runtime": perf016.EXPECTED_RUNTIME,
        "source_reused": True,
        "process_reused": True,
        "context_reused": True,
        "fresh_activation_per_iteration": True,
        "diagnostic_instrumentation_present": False,
        "warmup_ns": list(range(1, warmup + 1)),
        "steady_ns": list(range(100, 100 + steady)),
    }
    payload.update(overrides)
    return json.dumps(payload)


def admission_with_sources(cfg):
    admission = perf016.synthetic_admission(cfg)
    admission["workload_control_bytes"] = {
        role: {item["id"]: b"sink = 42\n" for item in cfg["workloads"]} for role in perf016.ROLES
    }
    return admission


class Perf016ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = perf016.load()

    def assert_config_rejected(self, mutator, tag):
        cfg = copy.deepcopy(self.cfg)
        mutator(cfg)
        with self.assertRaisesRegex(RuntimeError, tag):
            perf016.validate_config_payload(cfg)

    def test_static_validation_passes_and_reports_the_contract(self):
        with captured_stdout() as out:
            cfg = perf016.validate()
        text = out.getvalue()
        self.assertEqual("PERF016", cfg["work_item"])
        for marker in (
            "PERF016_POST_STEP3_STATIC_VALIDATION=PASS",
            "CONTROL_REVISION=2e3f56fae3a500d3e4193e3345d8a82c35e4590e",
            "CONTROL_VERSION=0.3.117-SNAPSHOT",
            "INTERVENTION_REVISION=696b0f9797ebc8ced80009fb583027513852f55c",
            "INTERVENTION_VERSION=0.3.119-SNAPSHOT",
            "PRODUCT_COMMITS_BETWEEN_ENDPOINTS=2",
            "TOOLCHAIN=25.4.4.1.1",
            "JDK=25.0.4.1.1",
            "JVMCI=25.4-b23",
            "COUNTERBALANCE=A,B,A,B",
            "STEP_3_TIMING_CLASS=NOT_CLASSIFIED",
            "STEP3_NEXT_ROUTING=NOT_CLASSIFIED",
            "PERF016_POST_STEP3_OUTPUT_NAMESPACE=results/perf016-post-step3",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker + "\n", text)

    def test_pinned_endpoints_and_policy(self):
        cfg = self.cfg
        self.assertEqual("2e3f56fae3a500d3e4193e3345d8a82c35e4590e", cfg["control"]["revision"])
        self.assertEqual("0.3.117-SNAPSHOT", cfg["control"]["version"])
        self.assertEqual(
            "696b0f9797ebc8ced80009fb583027513852f55c", cfg["intervention"]["revision"]
        )
        self.assertEqual("0.3.119-SNAPSHOT", cfg["intervention"]["version"])
        self.assertNotEqual(cfg["control"]["revision"], cfg["intervention"]["revision"])
        self.assertEqual("baseline", cfg["control"]["variant"])
        self.assertEqual("baseline", cfg["intervention"]["variant"])
        self.assertEqual("none", cfg["patches_applied"])
        self.assertEqual(2, cfg["product_lineage"]["commit_count_between_endpoints"])
        self.assertFalse(cfg["product_lineage"]["unrelated_product_commit_between_endpoints"])
        self.assertEqual(10000, cfg["operation_count"])
        self.assertEqual(120, cfg["warmup_iterations"])
        self.assertEqual(100, cfg["steady_iterations"])
        self.assertEqual(["A", "B", "A", "B"], cfg["block_order"])
        self.assertEqual("none", cfg["network"])
        self.assertEqual("results/perf016-post-step3", cfg["reference"]["output"])

    def test_toolchain_block_is_the_dist006d_canonical_25_4_contract(self):
        self.assertEqual(perf016.dist006d.load()["toolchain"], self.cfg["toolchain"])
        graalvm = self.cfg["toolchain"]["graalvm"]
        self.assertEqual("25.4.4.1.1", graalvm["release"])
        self.assertEqual("25.0.4.1.1", graalvm["jdk_version"])
        self.assertEqual("25.4-b23", self.cfg["toolchain"]["jvmci"])
        self.assertEqual("protos-toolchain-v2", self.cfg["toolchain"]["schema"])
        self.assertEqual(
            {"minimum_version": "3.9.9", "supported_major": 3}, self.cfg["toolchain"]["maven"]
        )
        self.assertNotIn("25i3", graalvm["container_image"])

    def test_workload_matrix_is_the_established_perf010_matrix(self):
        controls = {item["id"]: item for item in perf016.load(
            ROOT / "config/perf014-direct-closure-call.json"
        )["controls"]}
        dist006d_workloads = {
            item["id"]: {key: item[key] for key in ("id", "source", "expected", "replace", "with")}
            for item in perf016.dist006d.load()["workloads"]
        }
        self.assertEqual(
            [item["id"] for item in perf016.EXPECTED_WORKLOADS], [w["id"] for w in self.cfg["workloads"]]
        )
        for item in self.cfg["workloads"]:
            with self.subTest(workload=item["id"]):
                self.assertEqual(controls[item["id"]], item)
                self.assertEqual(dist006d_workloads[item["id"]], item)
                self.assertEqual("42", item["expected"])
                self.assertEqual("sink = 42", item["with"])

    def test_rejection_battery_covers_every_required_category(self):
        keys = {key for key, _tag, _mutator in perf016.CONFIG_REJECTION_CASES}
        required = {
            "wrong_control_revision",
            "wrong_control_version",
            "wrong_intervention_revision",
            "wrong_intervention_version",
            "control_equals_intervention_revision",
            "control_equals_intervention_version",
            "toolchain_release_25_3",
            "container_25_3_selected",
            "legacy_toolchain_schema",
            "missing_workload",
            "changed_control_replacement",
            "changed_control_target",
            "wrong_operation_count",
            "wrong_warmup_policy",
            "wrong_steady_policy",
            "block_order_grouped",
            "block_order_short",
            "block_order_reversed",
            "output_collides_perf014",
            "output_collides_dist006d",
            "reference_without_exact_harness_sha",
            "automatic_step3_class",
            "automatic_step3_routing",
            "classification_threshold_introduced",
        }
        self.assertEqual(set(), required - keys)
        self.assertEqual(len(keys), len(perf016.CONFIG_REJECTION_CASES))

    def test_every_rejection_case_is_rejected_for_the_intended_reason(self):
        for key, tag, mutator in perf016.CONFIG_REJECTION_CASES:
            with self.subTest(case=key):
                self.assert_config_rejected(mutator, tag)

    def test_wrong_product_identity_fails_closed(self):
        self.assert_config_rejected(
            perf016.set_value("control", "revision", value="1" * 40), "CONTROL_REVISION_MISMATCH"
        )
        self.assert_config_rejected(
            perf016.set_value("intervention", "version", value="0.3.118-SNAPSHOT"),
            "INTERVENTION_VERSION_MISMATCH",
        )
        self.assert_config_rejected(
            lambda cfg: cfg["intervention"].__setitem__("revision", cfg["control"]["revision"]),
            "SAME_REVISION_REJECTED",
        )

    def test_25_3_toolchain_is_rejected_everywhere_it_can_be_selected(self):
        image_25_3 = "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825"
        for label, mutator in (
            ("container", perf016.set_value("toolchain", "graalvm", "container_image", value=image_25_3)),
            ("release", perf016.set_value("toolchain", "graalvm", "release", value="25.3.4.1")),
            ("components", perf016.set_value("toolchain", "graal_components", "version", value="25.3.4.1")),
            ("jvmci", perf016.set_value("toolchain", "jvmci", value="25.3-b12")),
        ):
            with self.subTest(selected_by=label):
                self.assert_config_rejected(mutator, "PERF016_25_3_TOOLCHAIN_REJECTED")

    def test_classification_thresholds_are_rejected_at_any_depth(self):
        for mutator in (
            perf016.set_value("classification", "large_factor_threshold", value=2),
            lambda cfg: cfg.__setitem__("threshold", 1),
            lambda cfg: cfg["measurement_views"]["paired_control_effect"].__setitem__(
                "mad_threshold_percent", 3.0
            ),
        ):
            self.assert_config_rejected(mutator, "PERF016_THRESHOLD_REJECTED")
        self.assertEqual([], perf016.find_threshold_keys(self.cfg))
        self.assertEqual(
            ["/a/b_threshold", "/c[0]/Threshold"],
            perf016.find_threshold_keys({"a": {"b_threshold": 1}, "c": [{"Threshold": 2}]}),
        )

    def test_output_namespace_must_be_dedicated_and_independent(self):
        perf016.require_independent_output_namespace("results/perf016-post-step3")
        for value in (
            "results/perf014-direct-closure-call",
            "results/dist006d-baseline",
            "results/upstream003-platform-comparison",
            "results/perf014-direct-closure-call/nested",
            "results",
            "results/",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "PERF016_OUTPUT_NAMESPACE_COLLISION"):
                    perf016.require_independent_output_namespace(value)
        for value in ("results/perf016", "results/perf016-post-step3/x", "", None, 7):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "PERF016_OUTPUT_NAMESPACE_MISMATCH"):
                    perf016.require_independent_output_namespace(value)

    def test_stale_or_changed_dist006d_infrastructure_fails_closed(self):
        with mock.patch.object(perf016, "dist006d", types.SimpleNamespace()):
            with self.assertRaisesRegex(RuntimeError, "PERF016_REUSED_INFRASTRUCTURE_MISSING"):
                perf016.require_dist006d_contract()
        pre_dist008 = types.SimpleNamespace(
            **{
                name: getattr(perf016.dist006d, name)
                for name in perf016.REQUIRED_DIST006D_SYMBOLS
                if name not in ("MAVEN_MINIMUM_VERSION", "MAVEN_SUPPORTED_MAJOR")
            }
        )
        with mock.patch.object(perf016, "dist006d", pre_dist008):
            with self.assertRaisesRegex(RuntimeError, "MAVEN_MINIMUM_VERSION"):
                perf016.require_dist006d_contract()

    def test_reused_dist006d_drift_is_not_silently_accepted(self):
        for name, value in (
            ("EXPECTED_ENGINE_VERSION", "25.5.0.0.0"),
            ("EXPECTED_JVMCI", "25.5-b01"),
            ("MAVEN_SUPPORTED_MAJOR", 4),
        ):
            with self.subTest(constant=name):
                with mock.patch.object(perf016.dist006d, name, value):
                    with self.assertRaisesRegex(RuntimeError, "PERF016_TOOLCHAIN_GENERATION_MISMATCH"):
                        perf016.validate_reused_infrastructure(self.cfg)

    def test_reference_refuses_a_missing_or_malformed_harness_sha_before_docker(self):
        for value in perf016.MALFORMED_HARNESS_REVISIONS:
            with self.subTest(value=value):
                with mock.patch.object(
                    perf016, "admit_products", side_effect=AssertionError("Docker must not run")
                ), mock.patch.object(
                    perf016.dist006d, "build_and_probe", side_effect=AssertionError("Docker must not run")
                ), captured_stdout():
                    with self.assertRaises(RuntimeError):
                        perf016.reference(value)
        self.assertEqual(len(perf016.MALFORMED_HARNESS_REVISIONS), perf016.run_harness_revision_self_test())

    def test_unclassified_placeholders_are_enforced_on_evidence(self):
        raw = perf016.synthetic_raw(self.cfg)
        perf016.require_unclassified(raw)
        for key, value in (
            ("STEP_3_TIMING_CLASS", "MATERIAL_LARGE_FACTOR_IMPROVEMENT"),
            ("STEP_3_TIMING_CLASS", "MATERIAL_PARTIAL_IMPROVEMENT"),
            ("STEP_3_TIMING_CLASS", "ESSENTIALLY_UNCHANGED"),
            ("STEP3_NEXT_ROUTING", "STEP4"),
            ("numeric_classification_thresholds_defined", True),
        ):
            with self.subTest(key=key, value=value):
                tampered = copy.deepcopy(raw)
                tampered[key] = value
                with self.assertRaisesRegex(
                    RuntimeError, "PERF016_AUTOMATIC_CLASSIFICATION_REJECTED"
                ):
                    perf016.require_unclassified(tampered)
        self.assertEqual("NOT_CLASSIFIED", raw["STEP_3_TIMING_CLASS"])
        self.assertEqual("NOT_CLASSIFIED", raw["STEP3_NEXT_ROUTING"])


class Perf016SignConventionTest(unittest.TestCase):
    def test_direct_effect_is_control_minus_intervention(self):
        faster = perf016.direct_revision_effect(1000, 400)
        self.assertEqual(600, faster["effect_ns"])
        self.assertAlmostEqual(60.0, faster["effect_percent"])
        slower = perf016.direct_revision_effect(400, 1000)
        self.assertEqual(-600, slower["effect_ns"])
        self.assertAlmostEqual(-150.0, slower["effect_percent"])
        same = perf016.direct_revision_effect(700, 700)
        self.assertEqual(0, same["effect_ns"])
        self.assertAlmostEqual(0.0, same["effect_percent"])
        with self.assertRaises(ValueError):
            perf016.direct_revision_effect(0, 5)

    def test_paired_control_residual_sign(self):
        cases = (
            # control canonical, control workload-control, intervention canonical, intervention wc
            ((1000, 400, 500, 200), 500, 200, 300, 30.0),
            ((1000, 400, 800, 200), 200, 200, 0, 0.0),
            ((1000, 400, 900, 200), 100, 200, -100, -10.0),
            ((1000, 400, 1100, 600), -100, -200, 100, 10.0),
            ((1000, 400, 1000, 400), 0, 0, 0, 0.0),
        )
        for inputs, improvement, movement, residual, percent in cases:
            with self.subTest(inputs=inputs):
                result = perf016.paired_control_residual(*inputs)
                self.assertEqual(improvement, result["canonical_improvement_ns"])
                self.assertEqual(movement, result["control_movement_ns"])
                self.assertEqual(residual, result["paired_control_effect_ns"])
                self.assertAlmostEqual(percent, result["paired_control_effect_percent"])

    def test_shared_driver_improvement_cancels_in_the_residual_but_not_in_the_direct_views(self):
        entry = {
            "block_index": 0,
            "block_order": "A",
            "workload": "micro/slot-read",
            "role_sequence": ["control", "intervention"],
            "roles": {
                role: {
                    variant: {"steady_summary": {"median_ns": level}}
                    for variant, level in variants.items()
                }
                for role, variants in {
                    "control": {"canonical": 1000, "workload_control": 400},
                    "intervention": {"canonical": 800, "workload_control": 200},
                }.items()
            },
        }
        block = perf016.classify_block(entry)
        self.assertEqual(200, block["control_variant_effect_ns"])
        self.assertAlmostEqual(50.0, block["control_variant_effect_percent"])
        self.assertEqual(200, block["canonical_effect_ns"])
        self.assertAlmostEqual(20.0, block["canonical_effect_percent"])
        self.assertEqual(0, block["paired_control_effect_ns"])
        self.assertEqual(block["canonical_effect_ns"], block["canonical_improvement_ns"])
        self.assertEqual(block["control_variant_effect_ns"], block["control_movement_ns"])


class Perf016AnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = perf016.load()
        cls.raw = perf016.synthetic_raw(cls.cfg)

    def test_block_role_order_counterbalances_control_and_intervention(self):
        self.assertEqual(("control", "intervention"), perf016.block_role_order("A"))
        self.assertEqual(("intervention", "control"), perf016.block_role_order("B"))
        with self.assertRaises(ValueError):
            perf016.block_role_order("C")

    def test_order_effect_uses_the_perf014_range_separation_method(self):
        self.assertEqual("DETECTED", perf016.order_effect([1.0, 2.0], [3.0, 4.0]))
        self.assertEqual("DETECTED", perf016.order_effect([3.0, 4.0], [1.0, 2.0]))
        self.assertEqual("NOT_DETECTED", perf016.order_effect([1.0, 3.0], [2.0, 4.0]))
        self.assertEqual("NOT_DETECTED", perf016.order_effect([5.0, 5.0], [5.0, 5.0]))
        self.assertEqual("INCONCLUSIVE", perf016.order_effect([1.0], [3.0, 4.0]))
        self.assertEqual("INCONCLUSIVE", perf016.order_effect([], []))

    def test_summarize_series(self):
        summary = perf016.summarize_series([1.0, 2.0, 3.0, 10.0])
        self.assertEqual({"median": 2.5, "mad": 1.0, "min": 1.0, "max": 10.0}, summary)

    def test_stationarity_requires_exactly_one_hundred_samples(self):
        drift = perf016.stationarity_diagnostics([1000] * 75 + [1100] * 25)
        self.assertEqual(1000, drift["first_quarter_median_ns"])
        self.assertEqual(1100, drift["last_quarter_median_ns"])
        self.assertAlmostEqual(10.0, drift["last_quarter_vs_first_quarter_percent"])
        flat = perf016.stationarity_diagnostics([500] * 100)
        self.assertAlmostEqual(0.0, flat["last_quarter_vs_first_quarter_percent"])
        for count in (0, 99, 101):
            with self.subTest(count=count):
                with self.assertRaises(RuntimeError):
                    perf016.stationarity_diagnostics([500] * count)

    def test_synthetic_blocks_have_the_designed_effects(self):
        classified = self.raw["classified_blocks"]
        self.assertEqual(16, len(classified))
        first_a, first_b = classified[0], classified[4]
        self.assertEqual(("A", 0, 2000, 2000, 0), (
            first_a["block_order"],
            first_a["block_index"],
            first_a["control_variant_effect_ns"],
            first_a["canonical_effect_ns"],
            first_a["paired_control_effect_ns"],
        ))
        self.assertAlmostEqual(50.0, first_a["control_variant_effect_percent"])
        self.assertAlmostEqual(20.0, first_a["canonical_effect_percent"])
        self.assertEqual(("B", 1), (first_b["block_order"], first_b["block_index"]))
        self.assertEqual(1500, first_b["canonical_effect_ns"])
        self.assertAlmostEqual(15.0, first_b["canonical_effect_percent"])
        self.assertEqual(-500, first_b["paired_control_effect_ns"])
        self.assertAlmostEqual(-5.0, first_b["paired_control_effect_percent"])

    def test_per_workload_summary_reports_all_three_views_and_order_effects(self):
        for workload in self.raw["workload_ids"]:
            views = self.raw["per_workload_summary"][workload]["views"]
            with self.subTest(workload=workload):
                self.assertEqual(set(perf016.VIEWS), set(views))
                self.assertEqual(4, self.raw["per_workload_summary"][workload]["blocks"])
                shared, canonical, paired = (
                    views["control_variant_effect"],
                    views["canonical_effect"],
                    views["paired_control_effect"],
                )
                self.assertAlmostEqual(50.0, shared["percent"]["median"])
                self.assertAlmostEqual(0.0, shared["percent"]["mad"])
                self.assertEqual("NOT_DETECTED", shared["order_effect"])
                self.assertAlmostEqual(17.5, canonical["percent"]["median"])
                self.assertAlmostEqual(2.5, canonical["percent"]["mad"])
                self.assertAlmostEqual(15.0, canonical["percent"]["min"])
                self.assertAlmostEqual(20.0, canonical["percent"]["max"])
                self.assertEqual("DETECTED", canonical["order_effect"])
                self.assertAlmostEqual(-2.5, paired["percent"]["median"])
                self.assertEqual("DETECTED", paired["order_effect"])
                self.assertEqual([20.0, 20.0], canonical["a_order_percent"])
                self.assertEqual([15.0, 15.0], canonical["b_order_percent"])
                self.assertEqual(4, len(canonical["per_block_percent"]))
                self.assertEqual("SHARED_DRIVER_TIMING_EFFECT", shared["evidence_input"])
                self.assertEqual("COMMON_WORKLOAD_TIMING_EFFECTS", canonical["evidence_input"])
                self.assertEqual("SECONDARY_PAIRED_CONTROL_DISCRIMINATOR", paired["evidence_input"])

    def test_workload_controls_are_preserved_individually(self):
        # The four workloads have different levels (scale 1..4); merging them would change the
        # per-workload level medians, so each must keep its own.
        levels = [
            self.raw["per_workload_summary"][workload]["level_medians_ns"]["control_canonical"]["median"]
            for workload in self.raw["workload_ids"]
        ]
        self.assertEqual([10000.0, 20000.0, 30000.0, 40000.0], levels)

    def test_stationarity_rows_cover_every_timed_unit(self):
        rows = self.raw["per_timed_unit_stationarity"]
        self.assertEqual(64, len(rows))
        self.assertEqual(
            {(role, variant) for role in perf016.ROLES for variant in perf016.VARIANTS},
            {(row["role"], row["variant"]) for row in rows},
        )
        # Sixteen units per block: block 0 (A) runs the control role first, block 1 (B) the
        # intervention role first.
        self.assertEqual(["control", "intervention"], [r["role"] for r in rows[0:4:2]])
        self.assertEqual(["intervention", "control"], [r["role"] for r in rows[16:20:2]])
        self.assertEqual(["A", "B"], [rows[0]["block_order"], rows[16]["block_order"]])

    def test_raw_carries_every_required_field(self):
        required = {
            "schema_version",
            "work_item",
            "slice",
            "control_revision",
            "control_version",
            "intervention_revision",
            "intervention_version",
            "harness_revision",
            "host_identity",
            "cpu_policy",
            "network",
            "toolchain",
            "runtime_identity",
            "base_image_identity",
            "built_image_identity",
            "operation_count",
            "warmup_iterations",
            "steady_iterations",
            "block_order",
            "workload_source_sha256",
            "blocks",
            "classified_blocks",
            "per_workload_summary",
            "per_timed_unit_stationarity",
            "diagnostic_instrumentation_present",
            "STEP_3_TIMING_CLASS",
            "STEP3_NEXT_ROUTING",
        }
        self.assertEqual(set(), required - set(self.raw))
        self.assertEqual("PERF016", self.raw["work_item"])
        self.assertEqual("POST_STEP3_CONTROLLED_TIMING", self.raw["slice"])
        self.assertFalse(self.raw["diagnostic_instrumentation_present"])
        self.assertEqual(["control", "intervention"], sorted(self.raw["built_image_identity"]))
        unit = self.raw["blocks"][0]["roles"]["control"]["canonical"]
        self.assertEqual(perf016.WARMUP_ITERATIONS, len(unit["raw"]["warmup_ns"]))
        self.assertEqual(perf016.STEADY_ITERATIONS, len(unit["raw"]["steady_ns"]))
        self.assertEqual([], perf016.find_threshold_keys(self.raw))

    def test_verify_raw_accepts_the_raw_and_its_json_round_trip(self):
        perf016.verify_raw(self.raw)
        perf016.verify_raw(json.loads(json.dumps(self.raw, indent=2, sort_keys=True)))

    def test_verify_raw_detects_tampering(self):
        def tamper(mutator, tag):
            retained = json.loads(json.dumps(self.raw))
            mutator(retained)
            with self.assertRaisesRegex(RuntimeError, tag):
                perf016.verify_raw(retained)

        first = "control", "canonical"
        tamper(
            lambda r: r["blocks"][0]["roles"][first[0]][first[1]]["steady_summary"].__setitem__(
                "median_ns", 1.0
            ),
            "PERF016_DERIVED_ANALYSIS_NOT_REPRODUCIBLE",
        )
        tamper(
            lambda r: r["blocks"][0]["roles"][first[0]][first[1]]["raw"].__setitem__(
                "steady_ns", [7] * perf016.STEADY_ITERATIONS
            ),
            "PERF016_DERIVED_ANALYSIS_NOT_REPRODUCIBLE",
        )
        tamper(
            lambda r: r["classified_blocks"][0].__setitem__("paired_control_effect_percent", 99.0),
            "PERF016_DERIVED_ANALYSIS_NOT_REPRODUCIBLE",
        )
        tamper(
            lambda r: r["blocks"][0]["roles"]["control"]["canonical"]["raw"].__setitem__(
                "diagnostic_instrumentation_present", True
            ),
            "PERF016_RAW_IDENTITY_MISMATCH",
        )
        tamper(lambda r: r.__setitem__("control_revision", "0" * 40), "PERF016_RAW_IDENTITY_MISMATCH")
        tamper(lambda r: r.__setitem__("harness_revision", "main"), "40 lowercase hexadecimal")
        tamper(lambda r: r.__setitem__("network", "bridge"), "PERF016_RAW_IDENTITY_MISMATCH")
        tamper(
            lambda r: r["runtime_identity"]["intervention"].__setitem__("engine_version", "25.3.4.1"),
            "PERF016_RAW_IDENTITY_MISMATCH",
        )
        tamper(
            lambda r: r["correctness_gate"]["cases"][0].__setitem__("observed", "41"),
            "PERF016_RAW_IDENTITY_MISMATCH",
        )
        tamper(
            lambda r: r["correctness_gate"]["cases"].pop(),
            "PERF016_RAW_IDENTITY_MISMATCH",
        )
        tamper(
            lambda r: r["workload_source_sha256"]["micro/slot-read"]["canonical"].__setitem__(
                "intervention", "0" * 64
            ),
            "PERF016_RAW_IDENTITY_MISMATCH",
        )
        tamper(lambda r: r.__setitem__("STEP_3_TIMING_CLASS", "ESSENTIALLY_UNCHANGED"), "AUTOMATIC")
        tamper(lambda r: r["blocks"].pop(), "PERF016_RAW_IDENTITY_MISMATCH")

    def test_derived_views_are_reproducible_from_raw_and_well_formed(self):
        retained = json.loads(json.dumps(self.raw, sort_keys=True))
        views = perf016.render_derived_views(retained)
        self.assertEqual(views, perf016.render_derived_views(self.raw))
        self.assertEqual(
            {"summary.tsv", "blocks.tsv", "stationarity.tsv", "README.md"}, set(views)
        )

        summary = views["summary.tsv"].splitlines()
        self.assertEqual(1 + 4 * 3, len(summary))
        self.assertEqual(
            "workload\tview\tevidence_input\tblocks\tmedian_ns\tmad_ns\tmin_ns\tmax_ns\t"
            "median_percent\tmad_percent\tmin_percent\tmax_percent\torder_effect",
            summary[0],
        )
        self.assertTrue(summary[1].startswith("micro/slot-read\tcontrol_variant_effect\t"))

        blocks = views["blocks.tsv"].splitlines()
        self.assertEqual(1 + 16, len(blocks))
        self.assertEqual(13, len(blocks[0].split("\t")))
        self.assertTrue(all(len(line.split("\t")) == 13 for line in blocks))

        stationarity = views["stationarity.tsv"].splitlines()
        self.assertEqual(1 + 64, len(stationarity))
        self.assertTrue(all(len(line.split("\t")) == 9 for line in stationarity))

        readme = views["README.md"]
        self.assertIn("## STEP_3_TIMING_CLASS = NOT_CLASSIFIED\n", readme)
        self.assertIn("## STEP3_NEXT_ROUTING = NOT_CLASSIFIED\n", readme)
        self.assertIn("positive value means the INTERVENTION is faster", readme)
        self.assertIn("SHARED_DRIVER_TIMING_EFFECT", readme)
        for name, text in views.items():
            with self.subTest(view=name):
                self.assertTrue(text.endswith("\n"))
                self.assertFalse(text.endswith("\n\n"))
                # Retained evidence must survive `git diff --check`: no trailing whitespace.
                for line in text.splitlines():
                    self.assertEqual(line, line.rstrip(" \t"))


class Perf016AdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = perf016.load()

    def canonical_sources(self, *, drift=None):
        sources = {
            role: {
                item["id"]: f"sink = 0\n{item['replace']}\nprint(sink)\n".encode("utf-8")
                for item in self.cfg["workloads"]
            }
            for role in perf016.ROLES
        }
        if drift is not None:
            sources["intervention"][drift] += b"# drift\n"
        return sources

    def test_workload_control_source_replaces_exactly_one_target(self):
        item = perf016.EXPECTED_WORKLOADS[1]
        generated = perf016.workload_control_source(
            f"a\n{item['replace']}\nb\n".encode("utf-8"), item
        )
        self.assertEqual(b"a\nsink = 42\nb\n", generated)
        for canonical in (b"nothing to replace\n", f"{item['replace']}\n{item['replace']}\n".encode()):
            with self.subTest(canonical=canonical):
                with self.assertRaisesRegex(RuntimeError, "exactly one workload-control target"):
                    perf016.workload_control_source(canonical, item)
        with self.assertRaisesRegex(RuntimeError, "not valid UTF-8"):
            perf016.workload_control_source(b"\xff\xfe", item)

    def test_source_identity_gate_passes_for_identical_sources(self):
        identity, generated = perf016.verify_workload_source_identity(
            self.cfg, self.canonical_sources()
        )
        self.assertEqual(
            [item["id"] for item in self.cfg["workloads"]], list(identity)
        )
        for item in self.cfg["workloads"]:
            record = identity[item["id"]]
            self.assertEqual(record["canonical"]["control"], record["canonical"]["intervention"])
            self.assertEqual(
                record["workload_control"]["control"], record["workload_control"]["intervention"]
            )
            self.assertNotEqual(record["canonical"]["control"], record["workload_control"]["control"])
            self.assertEqual(
                {"replace": item["replace"], "with": item["with"]}, record["transform"]
            )
            self.assertIn(b"sink = 42", generated["control"][item["id"]])
            self.assertNotIn(item["replace"].encode(), generated["control"][item["id"]])
            self.assertEqual(generated["control"][item["id"]], generated["intervention"][item["id"]])

    def test_source_identity_gate_fails_closed_on_any_drift(self):
        for item in self.cfg["workloads"]:
            with self.subTest(workload=item["id"]):
                with self.assertRaisesRegex(RuntimeError, "WORKLOAD_SOURCE_IDENTITY_MISMATCH"):
                    perf016.verify_workload_source_identity(
                        self.cfg, self.canonical_sources(drift=item["id"])
                    )

    def test_source_identity_is_exact_bytes_not_normalized_text(self):
        sources = self.canonical_sources()
        first = self.cfg["workloads"][0]["id"]
        sources["control"][first] = sources["control"][first].replace(b"\n", b"\r\n")
        with self.assertRaisesRegex(RuntimeError, "WORKLOAD_SOURCE_IDENTITY_MISMATCH"):
            perf016.verify_workload_source_identity(self.cfg, sources)

    def test_canonical_sources_are_read_from_both_images_at_the_corpus_path(self):
        requested = []

        def reader(tag, cpu, path):
            requested.append((tag, cpu, path))
            return b"x"

        sources = perf016.read_canonical_sources(
            self.cfg, {"control": "c-tag", "intervention": "i-tag"}, "3", reader
        )
        self.assertEqual(set(perf016.ROLES), set(sources))
        self.assertEqual(8, len(requested))
        self.assertIn(("c-tag", "3", "/opt/dist006d/corpus/micro/slot-read.protos"), requested)
        self.assertIn(
            ("i-tag", "3", "/opt/dist006d/corpus/runtime/monomorphic-dispatch.protos"), requested
        )

    def test_control_sources_are_written_per_role_from_the_generated_bytes(self):
        generated = {
            role: {item["id"]: f"{role}-{item['id']}".encode() for item in self.cfg["workloads"]}
            for role in perf016.ROLES
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = perf016.write_control_sources(generated, Path(tmp))
            for role in perf016.ROLES:
                for workload, path in paths[role].items():
                    self.assertEqual(generated[role][workload], path.read_bytes())
                    self.assertEqual(Path(tmp) / role, path.parent)
            self.assertNotEqual(paths["control"]["micro/slot-read"], paths["intervention"]["micro/slot-read"])

    def test_jvmci_identity_must_match(self):
        runtime = {
            "java_runtime_version": "25.0.4.1.1+1-jvmci-25.4-b23",
            "java_vm_version": "25.0.4.1.1+1-jvmci-25.4-b23",
        }
        perf016.require_jvmci(runtime, "25.4-b23", "control")
        for field in runtime:
            with self.subTest(field=field):
                broken = dict(runtime, **{field: "25.0.4.1.1+1-LTS"})
                with self.assertRaisesRegex(RuntimeError, "PERF016_JVMCI_IDENTITY_MISMATCH"):
                    perf016.require_jvmci(broken, "25.4-b23", "control")
        with self.assertRaisesRegex(RuntimeError, "PERF016_JVMCI_IDENTITY_MISMATCH"):
            perf016.require_jvmci({}, "25.4-b23", "intervention")

    def test_both_images_must_prove_the_same_toolchain_and_be_distinct(self):
        builds = perf016.synthetic_admission(self.cfg)["builds"]
        perf016.require_same_toolchain_identity(builds)
        for key, value in (
            ("runtime", dict(builds["intervention"]["runtime"], engine_version="25.3.4.1")),
            ("toolchain", {"schema": "protos-toolchain-v1"}),
            ("runtime_components", [{"jar": "extra.jar", "manifest": ""}]),
            ("base_image_identity", dict(builds["intervention"]["base_image_identity"], id="sha256:x")),
        ):
            with self.subTest(key=key):
                mutated = copy.deepcopy(builds)
                mutated["intervention"][key] = value
                with self.assertRaisesRegex(RuntimeError, "PERF016_TOOLCHAIN_IDENTITY_MISMATCH"):
                    perf016.require_same_toolchain_identity(mutated)
        same = copy.deepcopy(builds)
        same["intervention"]["built_image_identity"] = same["control"]["built_image_identity"]
        with self.assertRaisesRegex(RuntimeError, "PERF016_IMAGES_NOT_DISTINCT"):
            perf016.require_same_toolchain_identity(same)

    def test_product_version_is_read_from_the_image_pom(self):
        pom = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            "  <modelVersion>4.0.0</modelVersion>\n"
            "  <artifactId>protos</artifactId>\n"
            "  <version>0.3.117-SNAPSHOT</version>\n"
            "</project>\n"
        )
        with mock.patch.object(perf016.dist006d, "image_text", return_value=pom) as image_text:
            self.assertEqual("0.3.117-SNAPSHOT", perf016.image_product_version("tag", "0"))
        image_text.assert_called_once_with("tag", "0", "/opt/protos-source/pom.xml")
        with mock.patch.object(
            perf016.dist006d, "image_text", return_value='<project><artifactId>x</artifactId></project>'
        ):
            self.assertEqual("", perf016.image_product_version("tag", "0"))

    def fake_build(self, *, jvmci_for=None, engine_for=None):
        def build(cfg, revision, cpu):
            role = "control" if revision == perf016.EXPECTED_CONTROL_REVISION else "intervention"
            result = copy.deepcopy(perf016.synthetic_admission(cfg)["builds"][role])
            result["tag"] = f"protos-benchmarks-dist006d:{revision[:12]}"
            if role == jvmci_for:
                result["runtime"]["java_vm_version"] = "25.0.4.1.1+1-LTS"
            if role == engine_for:
                result["runtime"]["engine_version"] = "25.4.4.1.2"
            return result

        return build

    def version_of(self, tag, cpu):
        return {
            "protos-benchmarks-dist006d:2e3f56fae3a5": perf016.EXPECTED_CONTROL_VERSION,
            "protos-benchmarks-dist006d:696b0f9797eb": perf016.EXPECTED_INTERVENTION_VERSION,
        }[tag]

    def admit(self, *, build=None, version=None, sources=None):
        with mock.patch.object(
            perf016.dist006d, "build_and_probe", side_effect=build or self.fake_build()
        ) as build_mock, mock.patch.object(
            perf016, "image_product_version", side_effect=version or self.version_of
        ), mock.patch.object(
            perf016, "read_canonical_sources", return_value=sources or self.canonical_sources()
        ), captured_stdout() as out:
            admission = perf016.admit_products(self.cfg, "0")
        return admission, build_mock, out.getvalue()

    def test_admission_builds_both_exact_revisions_and_returns_the_identity(self):
        admission, build_mock, output = self.admit()
        self.assertEqual(
            [perf016.EXPECTED_CONTROL_REVISION, perf016.EXPECTED_INTERVENTION_REVISION],
            [call.args[1] for call in build_mock.call_args_list],
        )
        self.assertEqual({"control", "intervention"}, set(admission["builds"]))
        self.assertEqual(4, len(admission["workload_source_sha256"]))
        self.assertIn("PERF016_BOTH_IMAGES_TOOLCHAIN_IDENTITY=PASS\n", output)
        self.assertIn("WORKLOAD_SOURCE_IDENTITY=PASS\n", output)
        for role in perf016.ROLES:
            self.assertEqual(4, len(admission["workload_control_bytes"][role]))

    def test_admission_fails_closed_on_every_identity_violation(self):
        cases = (
            (
                "PERF016_VERSION_IDENTITY_MISMATCH",
                {"version": lambda tag, cpu: "0.3.999-SNAPSHOT"},
            ),
            ("PERF016_JVMCI_IDENTITY_MISMATCH", {"build": self.fake_build(jvmci_for="intervention")}),
            (
                "PERF016_TOOLCHAIN_IDENTITY_MISMATCH",
                {"build": self.fake_build(engine_for="intervention")},
            ),
            (
                "WORKLOAD_SOURCE_IDENTITY_MISMATCH",
                {"sources": self.canonical_sources(drift="micro/method-call")},
            ),
        )
        for tag, kwargs in cases:
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(RuntimeError, tag):
                    self.admit(**kwargs)


class Perf016TimingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = perf016.load()
        cls.item = perf016.EXPECTED_WORKLOADS[0]

    def run_unit(self, stdout, *, variant="canonical", warmup=2, steady=3, stderr="", returncode=0):
        calls = []

        def fake(cpu, tag, entrypoint, *args, volume=None):
            calls.append((cpu, tag, entrypoint, list(args), volume))
            return completed(stdout=stdout, stderr=stderr, returncode=returncode)

        with mock.patch.object(perf016.dist006d, "docker_entrypoint", side_effect=fake):
            result = perf016.timing_unit(
                "the-tag",
                "5",
                self.item,
                variant,
                Path("/tmp/control.protos"),
                "the-label",
                warmup,
                steady,
                collect_stationarity=False,
            )
        return result, calls

    def test_driver_arguments_match_the_reused_dist006d_timing_driver(self):
        recorded = []

        def fake(cpu, tag, entrypoint, *args, volume=None):
            recorded.append((cpu, tag, entrypoint, list(args), volume))
            return completed(stdout=timing_payload(1, 2) + "\n")

        source = "/opt/dist006d/corpus/micro/slot-read.protos"
        with mock.patch.object(perf016.dist006d, "docker_entrypoint", side_effect=fake):
            perf016.dist006d.driver_timing("tag", "0", source, "42", 1, 2)
            perf016.dist006d.driver_timing(
                "tag", "0", "", "42", 1, 2, source_host=Path("/tmp/control.protos")
            )
        self.assertEqual(
            perf016.driver_java_args("timing", source, "42", "1", "2"), recorded[0][3]
        )
        self.assertEqual(
            perf016.driver_java_args("timing", "/work/source.protos", "42", "1", "2"), recorded[1][3]
        )
        self.assertEqual((Path("/tmp/control.protos"), "/work/source.protos"), recorded[1][4])

    def test_timing_command_contains_no_diagnostic_instrumentation(self):
        args = perf016.driver_java_args("timing", "/x.protos", "42", "120", "100")
        joined = " ".join(args).lower()
        for forbidden in ("jfr", "trace", "igv", "-xx:", "-dpolyglot", "-dgraal", "-agentlib", "profil"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, joined)
        self.assertEqual("Dist006dDriver", args[4])
        self.assertIn("-Xss128m", args)

    def test_canonical_unit_runs_the_in_image_source(self):
        stderr = "WARNING: deprecated\n"
        (unit, stdout, err), calls = self.run_unit(
            "banner line\n" + timing_payload(2, 3) + "\n", stderr=stderr
        )
        self.assertEqual(1, len(calls))
        cpu, tag, entrypoint, args, volume = calls[0]
        self.assertEqual(("5", "the-tag", "java", None), (cpu, tag, entrypoint, volume))
        self.assertEqual(
            ["timing", "/opt/dist006d/corpus/micro/slot-read.protos", "42", "2", "3"], args[-5:]
        )
        self.assertEqual(101, unit["steady_summary"]["median_ns"])
        self.assertEqual([1, 2], unit["raw"]["warmup_ns"])
        self.assertIsNone(unit["stationarity"])
        self.assertEqual("the-label.stdout.log", unit["stdout_log"])
        self.assertEqual("the-label.stderr.log", unit["stderr_log"])
        self.assertEqual(perf016.sha256_text(stdout), unit["stdout_sha256"])
        self.assertEqual(perf016.sha256_text(stderr), unit["stderr_sha256"])
        self.assertEqual(stderr, err)
        self.assertTrue(stdout.startswith("banner line\n"))

    def test_workload_control_unit_mounts_the_generated_source_read_only_by_the_driver(self):
        (unit, _out, _err), calls = self.run_unit(
            timing_payload(2, 3) + "\n", variant="workload_control"
        )
        _cpu, _tag, _entrypoint, args, volume = calls[0]
        self.assertEqual(
            ["timing", "/work/source.protos", "42", "2", "3"], args[-5:]
        )
        self.assertEqual((Path("/tmp/control.protos"), "/work/source.protos"), volume)
        self.assertEqual(0, unit["returncode"])

    def test_stationarity_is_collected_only_when_requested(self):
        stdout = timing_payload(120, 100) + "\n"
        with mock.patch.object(
            perf016.dist006d,
            "docker_entrypoint",
            side_effect=lambda *a, **k: completed(stdout=stdout),
        ):
            unit, _o, _e = perf016.timing_unit(
                "t", "0", self.item, "canonical", Path("/x"), "l", 120, 100, collect_stationarity=True
            )
        self.assertEqual(
            {
                "steady_median_ns",
                "first_quarter_median_ns",
                "last_quarter_median_ns",
                "last_quarter_vs_first_quarter_percent",
            },
            set(unit["stationarity"]),
        )

    def test_timing_fails_closed_on_any_invalid_output(self):
        cases = (
            ("PERF016_TIMING_OUTPUT_EMPTY", "\n  \n", {}),
            (
                "PERF016_DIAGNOSTIC_INSTRUMENTATION_PRESENT",
                timing_payload(2, 3, diagnostic_instrumentation_present=True),
                {},
            ),
            ("PERF016_TIMING_IDENTITY_MISMATCH", timing_payload(2, 3, runtime="DefaultTruffleRuntime"), {}),
            ("PERF016_TIMING_IDENTITY_MISMATCH", timing_payload(2, 3, mode="correctness"), {}),
            ("PERF016_TIMING_RESULT_MISMATCH", timing_payload(2, 3, expected="41"), {}),
            ("PERF016_TIMING_SAMPLE_COUNT_MISMATCH", timing_payload(3, 3), {}),
            ("PERF016_TIMING_SAMPLE_COUNT_MISMATCH", timing_payload(2, 2), {}),
            ("PERF016_TIMING_SAMPLE_INVALID", timing_payload(2, 3, steady_ns=[100, 0, 102]), {}),
            ("PERF016_TIMING_SAMPLE_INVALID", timing_payload(2, 3, steady_ns=[True, 2, 3]), {}),
            ("PERF016_TIMING_SAMPLE_INVALID", timing_payload(2, 3, warmup_ns=[1.5, 2]), {}),
        )
        for tag, stdout, kwargs in cases:
            with self.subTest(tag=tag, stdout=stdout[:60]):
                with self.assertRaisesRegex(RuntimeError, tag):
                    self.run_unit(stdout, **kwargs)
        with self.assertRaises(json.JSONDecodeError):
            self.run_unit("not json\n")

    def test_docker_failure_is_not_swallowed(self):
        with mock.patch.object(
            perf016.dist006d, "docker_entrypoint", side_effect=RuntimeError("docker entrypoint failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "docker entrypoint failed"):
                perf016.timing_unit(
                    "t", "0", self.item, "canonical", Path("/x"), "l", 2, 3, collect_stationarity=False
                )

    def run_matrix(self, block_order, *, show_timing=True):
        calls = []

        def fake_unit(tag, cpu, item, variant, control_source, label, warmup, steady, *, collect_stationarity):
            calls.append((tag, item["id"], variant, label, warmup, steady, collect_stationarity))
            return perf016.synthetic_unit(1000), "out\n", "err\n"

        admission = {"builds": {role: {"tag": "tag-" + role} for role in perf016.ROLES}}
        sources = {
            role: {item["id"]: Path("/tmp") / role for item in self.cfg["workloads"]}
            for role in perf016.ROLES
        }
        with mock.patch.object(perf016, "timing_unit", side_effect=fake_unit), captured_stdout() as out:
            blocks, logs = perf016.run_blocks(
                self.cfg,
                admission,
                "0",
                sources,
                block_order,
                3,
                4,
                collect_stationarity=False,
                show_timing=show_timing,
            )
        return blocks, logs, calls, out.getvalue()

    def test_counterbalanced_block_order_and_pairing(self):
        blocks, logs, calls, _out = self.run_matrix(("A", "B"))
        self.assertEqual(2 * 4 * 2 * 2, len(calls))
        self.assertEqual(8, len(blocks))
        self.assertEqual(["A"] * 4 + ["B"] * 4, [b["block_order"] for b in blocks])
        self.assertEqual(["control", "intervention"], blocks[0]["role_sequence"])
        self.assertEqual(["intervention", "control"], blocks[4]["role_sequence"])
        first_workload = self.cfg["workloads"][0]["id"]
        self.assertEqual(
            [
                ("tag-control", first_workload, "canonical"),
                ("tag-control", first_workload, "workload_control"),
                ("tag-intervention", first_workload, "canonical"),
                ("tag-intervention", first_workload, "workload_control"),
            ],
            [call[:3] for call in calls[0:4]],
        )
        self.assertEqual(
            [
                ("tag-intervention", first_workload, "canonical"),
                ("tag-intervention", first_workload, "workload_control"),
                ("tag-control", first_workload, "canonical"),
                ("tag-control", first_workload, "workload_control"),
            ],
            [call[:3] for call in calls[16:20]],
        )
        self.assertTrue(all(call[4:] == (3, 4, False) for call in calls))
        labels = {call[3] for call in calls}
        self.assertLessEqual(
            {
                "block0-A-micro__slot-read-control-canonical",
                "block1-B-micro__slot-read-intervention-workload_control",
            },
            labels,
        )
        self.assertEqual({"synthetic.stdout.log", "synthetic.stderr.log"}, set(logs))

    def test_full_reference_matrix_has_sixty_four_timed_units(self):
        blocks, _logs, calls, _out = self.run_matrix(perf016.BLOCK_ORDER)
        self.assertEqual(64, len(calls))
        self.assertEqual(16, len(blocks))
        self.assertEqual(len(calls), len({call[3] for call in calls}))

    def test_timing_is_printed_only_when_requested(self):
        _b, _l, _c, shown = self.run_matrix(("A",), show_timing=True)
        _b, _l, _c, hidden = self.run_matrix(("A",), show_timing=False)
        self.assertIn("median_ns=", shown)
        self.assertNotIn("median_ns", hidden)
        self.assertIn("PERF016 TIMING PASS unit=16/16", hidden)


class Perf016EvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = perf016.load()

    def test_unpopulated_output_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            empty = Path(tmp) / "empty"
            empty.mkdir()
            populated = Path(tmp) / "populated"
            populated.mkdir()
            (populated / "raw.json").write_text("{}", encoding="utf-8")
            plain_file = Path(tmp) / "file"
            plain_file.write_text("x", encoding="utf-8")
            perf016.require_unpopulated_output(missing)
            perf016.require_unpopulated_output(empty)
            for path in (populated, plain_file):
                with self.subTest(path=path.name):
                    with self.assertRaisesRegex(RuntimeError, "PERF016_OUTPUT_ALREADY_POPULATED"):
                        perf016.require_unpopulated_output(path)

    def test_harness_must_be_unchanged_after_the_run(self):
        harness = "a" * 40

        def outputs(head, status):
            def fake(command):
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return head
                if command[:3] == ["git", "status", "--porcelain"]:
                    return status
                raise AssertionError(command)

            return fake

        with mock.patch.object(perf016.dist006d, "output", side_effect=outputs(harness, "")):
            perf016.require_harness_unchanged(harness)
        with mock.patch.object(perf016.dist006d, "output", side_effect=outputs("b" * 40, "")):
            with self.assertRaisesRegex(RuntimeError, "HEAD moved"):
                perf016.require_harness_unchanged(harness)
        with mock.patch.object(
            perf016.dist006d, "output", side_effect=outputs(harness, " M runner/perf016_post_step3.py")
        ):
            with self.assertRaisesRegex(RuntimeError, "became dirty"):
                perf016.require_harness_unchanged(harness)

    def test_write_evidence_is_atomic_complete_and_reproducible_from_raw(self):
        raw = perf016.synthetic_raw(self.cfg)
        logs = {"block0-A-x-control-canonical.stdout.log": "{}\n", "a.stderr.log": "warn\n"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "results" / "perf016-post-step3"
            with mock.patch.object(perf016, "ROOT", root):
                perf016.write_evidence(out, raw, logs)
                self.assertEqual(
                    {"raw.json", "summary.tsv", "blocks.tsv", "stationarity.tsv", "README.md", "SHA256SUMS", "logs"},
                    {path.name for path in out.iterdir()},
                )
                self.assertEqual([], list((root / ".work").iterdir()))
                retained = json.loads((out / "raw.json").read_text(encoding="utf-8"))
                for name, text in perf016.render_derived_views(retained).items():
                    self.assertEqual(text, (out / name).read_text(encoding="utf-8"))
                manifest = (out / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
                listed = {line.split("  ", 1)[1] for line in manifest}
                self.assertEqual(
                    {
                        "raw.json",
                        "summary.tsv",
                        "blocks.tsv",
                        "stationarity.tsv",
                        "README.md",
                        "logs/a.stderr.log",
                        "logs/block0-A-x-control-canonical.stdout.log",
                    },
                    listed,
                )
                for line in manifest:
                    digest, name = line.split("  ", 1)
                    self.assertEqual(
                        perf016.sha256_bytes((out / name).read_bytes()), digest, name
                    )
                with self.assertRaisesRegex(RuntimeError, "PERF016_OUTPUT_ALREADY_POPULATED"):
                    perf016.write_evidence(out, raw, logs)

    def test_write_evidence_leaves_no_partial_output_when_the_raw_is_inconsistent(self):
        raw = perf016.synthetic_raw(self.cfg)
        raw["classified_blocks"][0]["paired_control_effect_percent"] = 99.0
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "results" / "perf016-post-step3"
            with mock.patch.object(perf016, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "PERF016_DERIVED_ANALYSIS_NOT_REPRODUCIBLE"):
                    perf016.write_evidence(out, raw, {})
            self.assertFalse(out.exists())

    def reference_mocks(self, root, admission, *, stack):
        stack.enter_context(mock.patch.object(perf016, "ROOT", root))
        stack.enter_context(mock.patch.object(perf016, "validate", return_value=self.cfg))
        stack.enter_context(
            mock.patch.object(perf016.dist006d, "exact_published_harness_revision", return_value="a" * 40)
        )
        stack.enter_context(mock.patch.object(perf016.dist006d, "first_cpu", return_value="0"))
        stack.enter_context(mock.patch.object(perf016, "allowed_cpus", return_value="0"))
        stack.enter_context(mock.patch.object(perf016, "admit_products", return_value=admission))
        stack.enter_context(
            mock.patch.object(
                perf016, "correctness_gate", return_value=perf016.synthetic_correctness(self.cfg)
            )
        )
        stack.enter_context(
            mock.patch.object(
                perf016,
                "run_blocks",
                return_value=(perf016.synthetic_blocks(), {"u.stdout.log": "x\n", "u.stderr.log": ""}),
            )
        )
        stack.enter_context(mock.patch.object(perf016, "require_harness_unchanged"))

    def test_reference_writes_the_full_evidence_unit_without_classifying(self):
        admission = admission_with_sources(self.cfg)
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            root = Path(tmp)
            self.reference_mocks(root, admission, stack=stack)
            with captured_stdout() as out:
                perf016.reference("a" * 40)
            evidence = root / "results" / "perf016-post-step3"
            raw = json.loads((evidence / "raw.json").read_text(encoding="utf-8"))
            self.assertEqual("RETAINED", raw["evidence_status"])
            self.assertEqual("a" * 40, raw["harness_revision"])
            self.assertEqual("NOT_CLASSIFIED", raw["STEP_3_TIMING_CLASS"])
            self.assertEqual("NOT_CLASSIFIED", raw["STEP3_NEXT_ROUTING"])
            self.assertEqual(["A", "B", "A", "B"], raw["block_order"])
            self.assertEqual(
                {"raw.json", "summary.tsv", "blocks.tsv", "stationarity.tsv", "README.md", "SHA256SUMS", "logs"},
                {path.name for path in evidence.iterdir()},
            )
            printed = out.getvalue()
            for marker in (
                "PERF016_POST_STEP3_REFERENCE=PASS\n",
                "PERF016_POST_STEP3_EVIDENCE_STATUS=RETAINED\n",
                "STEP_3_TIMING_CLASS=NOT_CLASSIFIED\n",
                "STEP3_NEXT_ROUTING=NOT_CLASSIFIED\n",
                "COUNTERBALANCE=A,B,A,B\n",
                "WORKLOAD=micro/slot-read SHARED_DRIVER_EFFECT_MEDIAN_PERCENT=50.0000 "
                "CANONICAL_EFFECT_MEDIAN_PERCENT=17.5000 "
                "PAIRED_CONTROL_EFFECT_MEDIAN_PERCENT=-2.5000\n",
            ):
                with self.subTest(marker=marker):
                    self.assertIn(marker, printed)
            self.assertNotIn("PERF016_CLOSE", printed)
            self.assertNotIn("STEP4_AUTHORIZED", printed)

    def test_reference_refuses_populated_output_before_any_docker_work(self):
        admission = admission_with_sources(self.cfg)
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            root = Path(tmp)
            self.reference_mocks(root, admission, stack=stack)
            evidence = root / "results" / "perf016-post-step3"
            evidence.mkdir(parents=True)
            (evidence / "raw.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(
                perf016, "admit_products", side_effect=AssertionError("Docker must not run")
            ), captured_stdout():
                with self.assertRaisesRegex(RuntimeError, "PERF016_OUTPUT_ALREADY_POPULATED"):
                    perf016.reference("a" * 40)
            self.assertEqual(["raw.json"], [path.name for path in evidence.iterdir()])

    def test_reference_stops_if_the_harness_changes_during_the_run(self):
        admission = admission_with_sources(self.cfg)
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            root = Path(tmp)
            self.reference_mocks(root, admission, stack=stack)
            with mock.patch.object(
                perf016,
                "require_harness_unchanged",
                side_effect=RuntimeError("PERF016_HARNESS_CHANGED_DURING_RUN"),
            ), captured_stdout():
                with self.assertRaisesRegex(RuntimeError, "PERF016_HARNESS_CHANGED_DURING_RUN"):
                    perf016.reference("a" * 40)
            self.assertFalse((root / "results" / "perf016-post-step3").exists())

    def test_smoke_retains_nothing_and_prints_no_timing(self):
        admission = admission_with_sources(self.cfg)
        state = {"head": "a" * 40, "clean": False, "identity": "WORKTREE_PRECOMMIT"}
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(perf016, "ROOT", Path(tmp)))
            stack.enter_context(mock.patch.object(perf016, "validate", return_value=self.cfg))
            stack.enter_context(mock.patch.object(perf016.dist006d, "first_cpu", return_value="0"))
            stack.enter_context(
                mock.patch.object(perf016.dist006d, "worktree_harness_state", return_value=state)
            )
            stack.enter_context(mock.patch.object(perf016, "allowed_cpus", return_value="0"))
            stack.enter_context(mock.patch.object(perf016, "admit_products", return_value=admission))
            stack.enter_context(
                mock.patch.object(
                    perf016, "correctness_gate", return_value=perf016.synthetic_correctness(self.cfg)
                )
            )
            run_blocks = stack.enter_context(
                mock.patch.object(perf016, "run_blocks", return_value=(perf016.synthetic_blocks()[:8], {}))
            )
            stack.enter_context(
                mock.patch.object(
                    perf016, "write_evidence", side_effect=AssertionError("smoke must not write evidence")
                )
            )
            with captured_stdout() as out:
                perf016.smoke()
            self.assertFalse((Path(tmp) / "results").exists())
        args, kwargs = run_blocks.call_args
        self.assertEqual((("A", "B"), 1, 2), (args[4], args[5], args[6]))
        self.assertEqual({"collect_stationarity": False, "show_timing": False}, kwargs)
        printed = out.getvalue()
        for marker in (
            "SOURCE_IDENTITY_GATE=PASS\n",
            "SMOKE_RETAINED_TIMING_EVIDENCE=NO\n",
            "TIMING_EVIDENCE=NO\n",
            "REFERENCE_EVIDENCE=NO\n",
            "PERF016_POST_STEP3_SMOKE=PASS\n",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, printed)
        self.assertNotIn("median_ns", printed)
        identity = json.loads(
            next(
                line for line in printed.splitlines() if line.startswith("PERF016_SMOKE_IDENTITY=")
            ).split("=", 1)[1]
        )
        self.assertFalse(identity["retained_performance_evidence"])
        self.assertFalse(identity["timing_evidence"])
        self.assertFalse(identity["reference_evidence"])


class Perf016CommandLineAndMakefileTest(unittest.TestCase):
    def make_block(self):
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        start = text.index(".PHONY: perf016-post-step3-validate")
        end = text.find("\n.PHONY:", start + 1)
        return text[start:] if end < 0 else text[start:end]

    def test_makefile_exposes_the_three_stages(self):
        block = self.make_block()
        self.assertIn(
            ".PHONY: perf016-post-step3-validate perf016-post-step3-smoke "
            "perf016-post-step3-reference\n",
            block,
        )
        self.assertIn(
            "perf016-post-step3-validate:\n\tpython3 runner/perf016_post_step3.py validate\n", block
        )
        self.assertIn(
            "perf016-post-step3-smoke:\n\tpython3 runner/perf016_post_step3.py smoke\n", block
        )
        self.assertIn(
            'python3 runner/perf016_post_step3.py reference --harness-revision "$(HARNESS_REVISION)"',
            block,
        )

    def test_reference_target_requires_the_harness_sha_and_has_no_output_override(self):
        block = self.make_block()
        reference = block[block.index("perf016-post-step3-reference:") :]
        self.assertIn('@test -n "$(HARNESS_REVISION)"', reference)
        self.assertNotIn("OUT", reference)
        self.assertNotIn("--output-dir", reference)
        self.assertNotIn("PROTOS_REVISION", reference)

    def test_cli_rejects_a_harness_revision_outside_reference(self):
        for command in ("validate", "smoke"):
            with self.subTest(command=command):
                with mock.patch.object(
                    sys, "argv", ["perf016_post_step3.py", command, "--harness-revision", "a" * 40]
                ), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        perf016.main()
                self.assertEqual(2, raised.exception.code)

    def test_cli_reference_forwards_the_harness_revision(self):
        with mock.patch.object(
            sys, "argv", ["perf016_post_step3.py", "reference", "--harness-revision", "c" * 40]
        ), mock.patch.object(perf016, "reference") as reference:
            perf016.main()
        reference.assert_called_once_with("c" * 40)
        with mock.patch.object(sys, "argv", ["perf016_post_step3.py", "reference"]), mock.patch.object(
            perf016, "reference"
        ) as reference:
            perf016.main()
        reference.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
