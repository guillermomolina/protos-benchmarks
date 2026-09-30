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
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_runner(name):
    key = "pb_" + name
    module = sys.modules.get(key)
    if module is None:
        spec = importlib.util.spec_from_file_location(key, ROOT / "runner" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return module


contract = load_runner("perf010a_hot_root_contract")
runner = load_runner("perf010a_hot_root")
identity = load_runner("perf010a_hot_root_identity")
shape = load_runner("perf010a_hot_root_shape")

ACCEPTANCE_FLAGS = (
    "HARNESS_PRODUCT_REVISION_FAIL_CLOSED",
    "HARNESS_PRODUCT_VERSION_FAIL_CLOSED",
    "HARNESS_TOOLCHAIN_FAIL_CLOSED",
    "HARNESS_RUNTIME_IDENTITY_FAIL_CLOSED",
    "SOURCE_IDENTITY_STABLE_WITHOUT_ROOT_NUMBERS",
    "REQUIRED_WORKLOAD_MATRIX_PRESENT",
    "LIFECYCLE_RAW_EVENTS_RETAINED",
    "LIFECYCLE_ORDER_PRESERVED",
    "LIFECYCLE_PARSER_NEVER_COMPILED",
    "LIFECYCLE_PARSER_FIRST_TIER_ONLY",
    "LIFECYCLE_PARSER_FINAL_TIER_DONE",
    "LIFECYCLE_PARSER_PERMANENT_FAILURE",
    "LIFECYCLE_PARSER_TEMPORARY_FAILURE_RETRY",
    "LIFECYCLE_PARSER_INVALIDATE",
    "LIFECYCLE_PARSER_RECOMPILE_SUCCESS",
    "LIFECYCLE_PARSER_GENERIC_REPLACEMENT",
    "LIFECYCLE_PARSER_STABLE_FINAL_STATE",
    "GRAPH_CAPTURE_ISOLATED_PER_WORKLOAD",
    "GRAPH_MANIFEST_ROOT_CORRELATION",
    "COMPILED_SHAPE_RESULT_SUPPORTS_YES_NO_INCONCLUSIVE",
    "NO_HARD_CODED_ROOT_NUMBERS",
    "NO_PRODUCT_PATCH",
    "NO_OBSERVABLE_PROTOS_SEMANTIC_CHANGE",
)


def config():
    return json.loads((ROOT / "config/perf010a-hot-root-lifecycle.json").read_text(encoding="utf-8"))


class StaticContractTest(unittest.TestCase):
    def test_validate_proves_every_acceptance_item(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cfg = contract.validate()
        printed = dict(line.split("=", 1) for line in buffer.getvalue().splitlines() if "=" in line)
        for flag in ACCEPTANCE_FLAGS:
            self.assertEqual("PASS", printed.get(flag), flag)
        self.assertEqual("NO", printed["PERF020_IMPLEMENTED"])
        self.assertEqual("NO", printed["AUTHORITATIVE_DISCRIMINATOR_EXECUTED"])
        self.assertEqual("NOT_CLASSIFIED", printed["CAUSAL_CLASS"])
        self.assertEqual("b72778ca446b602f33af5027a0ed28ab788b39ce", cfg["protos"]["revision"])
        self.assertEqual("0.3.119-SNAPSHOT", cfg["protos"]["version"])

    def test_admitted_build_allows_additive_toolchain_metadata(self):
        cfg = config()
        toolchain = {
            key: copy.deepcopy(cfg["toolchain"][key])
            for key in (
                "schema",
                "java",
                "graalvm",
                "graal_components",
                "maven",
                "policy",
            )
        }
        toolchain["ci"] = {
            "image": "ghcr.io/guillermomolina/protos-ci@sha256:additional-metadata"
        }

        jvmci = cfg["toolchain"]["jvmci"]
        runtime_version = (
            "25.0.4.1.1+0-jvmci-" + jvmci
        )

        build = {
            "revision_label": cfg["protos"]["revision"],
            "source_head": cfg["protos"]["revision"],
            "product_version": cfg["protos"]["version"],
            "toolchain": toolchain,
            "runtime": {
                "runtime_class": contract.EXPECTED_RUNTIME,
                "engine_version": contract.EXPECTED_GRAALVM_RELEASE,
                "java_version": contract.EXPECTED_JDK_VERSION,
                "java_runtime_version": runtime_version,
                "java_vm_version": runtime_version,
            },
        }

        contract.verify_admitted_build(cfg, build)

    def test_required_matrix_is_three_workloads_by_two_variants(self):
        cfg = config()
        self.assertEqual(
            ["micro/closure-call#canonical", "micro/closure-call#workload_control", "micro/method-call#canonical", "micro/method-call#workload_control", "runtime/monomorphic-dispatch#canonical", "runtime/monomorphic-dispatch#workload_control"],
            [u["id"] for u in contract.units(cfg)],
        )

    def test_config_is_fail_closed(self):
        cfg = config()
        for name, mutate in (
            ("floating revision", lambda c: c["protos"].__setitem__("revision", "main")),
            ("other revision", lambda c: c["protos"].__setitem__("revision", "e" * 40)),
            ("other version", lambda c: c["protos"].__setitem__("version", "0.3.120-SNAPSHOT")),
            ("stale 25.3 toolchain", lambda c: c["toolchain"]["graalvm"].__setitem__("release", "25.3.4.1")),
            ("tuning option", lambda c: c["diagnostic"]["run_kinds"]["lifecycle"]["options"].append({"name": "polyglot.compiler.InliningRecursionDepth", "value": "1", "purpose": "x"})),
            ("perf020 flag", lambda c: c["boundaries"].__setitem__("perf020_implemented", True)),
        ):
            with self.subTest(name):
                payload = copy.deepcopy(cfg)
                mutate(payload)
                with self.assertRaises(RuntimeError):
                    contract.validate_config_payload(payload)

    def test_toolchain_is_single_sourced_with_dist006d(self):
        dist006d = contract.load_dist006d()
        self.assertEqual(dist006d.load()["toolchain"], config()["toolchain"])

    def test_workload_targets_are_single_sourced_with_dist006d(self):
        base = {w["id"]: w for w in contract.load_dist006d().load()["workloads"]}
        for workload in config()["workloads"]:
            self.assertEqual(base[workload["id"]]["replace"], workload["target_text"])
            self.assertEqual("sink = 42", workload["control_text"])

    def test_historical_mechanism_is_reused_unchanged(self):
        pins = config()["reused_infrastructure"]["source_identity_mechanism"]["files"]
        self.assertEqual(3, len(pins))
        dockerfile = contract.OVERLAY_DOCKERFILE.read_text(encoding="utf-8")
        for rel in pins:
            self.assertIn("COPY " + rel, dockerfile)

    def test_overlay_is_not_the_stale_25_3_contract(self):
        text = contract.OVERLAY_DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("FROM ${BASE_IMAGE}", text)
        for stale in ("25i3", "25.3", "python39", "EXPECTED_MAVEN_VERSION", "git apply", "microdnf"):
            self.assertNotIn(stale, text)

    def test_no_product_patch_anywhere_in_the_harness_image(self):
        self.assertEqual([], list(contract.HOT_ROOT_DIR.rglob("*.patch")))
        self.assertNotIn("--allow-dirty", (ROOT / "runner/perf010a_hot_root.py").read_text(encoding="utf-8"))

    def test_perf020_is_not_implemented_here(self):
        text = (ROOT / "runner/perf010a_hot_root.py").read_text(encoding="utf-8").lower()
        # Identifiers of a two-revision timing comparator, not prose: the docstring may say what this
        # harness is not.
        for forbidden in ("intervention_revision", "control_revision", "paired_control", "quick", "median_ns", "nanotime", "warmup_ns", "steady_ns"):
            self.assertNotIn(forbidden, text)

    def test_makefile_targets_exist(self):
        make = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ("perf010a-hot-root-validate:", "perf010a-hot-root-smoke:", "perf010a-hot-root-diagnostic:"):
            self.assertIn(target, make)


class CommandLineTest(unittest.TestCase):
    def test_lifecycle_options_precede_graph_options_and_carry_the_target_source(self):
        cfg = config()
        unit = contract.units(cfg)[0]
        lifecycle = runner.java_args(cfg, "lifecycle", unit, (2, 2), "/work/closure-call.protos")
        graph = runner.java_args(cfg, "graph", unit, (2, 2), "/work/closure-call.protos")
        self.assertIn("-Dperf010a.hotRoot.engineOption.engine.TraceCompilation=true", lifecycle)
        self.assertIn("-Dperf010a.hotRoot.engineOption.engine.TraceInlining=true", lifecycle)
        self.assertIn(
            "-Dperf010a.hotRoot.engineOption.engine.TraceInliningDetails=true",
            lifecycle,
        )
        self.assertIn(
            "-Dperf010a.hotRoot.engineOption.engine.TracePerformanceWarnings=all",
            lifecycle,
        )
        self.assertIn(
            "-Dperf010a.hotRoot.engineOption.engine.NodeSourcePositions=true",
            lifecycle,
        )
        self.assertFalse(
            [
                arg
                for arg in lifecycle
                if arg.startswith("-Dpolyglot.")
            ]
        )
        self.assertIn("-Dperf010a.hotRoot.targetSource=closure-call.protos", lifecycle)
        self.assertFalse(
            [arg for arg in lifecycle if arg.startswith("-Dpolyglot.")]
        )
        self.assertFalse([a for a in lifecycle if a.startswith("-Djdk.graal.Dump")])
        self.assertIn("-Djdk.graal.Dump=Truffle:2", graph)
        self.assertIn("-Djdk.graal.DumpPath=/diag-out/graal_dumps", graph)
        self.assertTrue(set(lifecycle[:-5]) <= set(graph))
        self.assertEqual(["Perf010aHotRootDriver", "/work/closure-call.protos", "42", "2", "2", "/diag-out/root-identity.json"], lifecycle[-6:])
        self.assertIn("-Xss128m", lifecycle)

    def test_no_compilation_policy_option_is_ever_set(self):
        cfg = config()
        for kind in contract.RUN_KINDS:
            for option in runner.kind_options(cfg, kind):
                self.assertNotIn(option["name"].rsplit(".", 1)[-1], contract.TUNING_OPTION_SEGMENTS)

    def test_rejected_options_are_detected(self):
        self.assertTrue(runner.scan_option_problems("java.lang.IllegalArgumentException: Could not find option with name engine.Nope."))
        self.assertFalse(runner.scan_option_problems("[engine] opt done engine=2  id=1   R@1 |Tier 1"))


class SourceTest(unittest.TestCase):
    def workload(self):
        return config()["workloads"][0]

    def test_workload_control_replaces_exactly_the_target(self):
        source = b"repeat: (count, operation) => {}\nsink: 0\nrepeat(10000, () => { sink = identity(42) })\nsink\n"
        control = runner.control_bytes(source, self.workload())
        self.assertIn(b"sink = 42", control)
        self.assertNotIn(b"identity(42)", control)

    def test_missing_or_duplicated_target_fails_closed(self):
        with self.assertRaises(RuntimeError):
            runner.control_bytes(b"nothing", self.workload())
        with self.assertRaises(RuntimeError):
            runner.control_bytes(b"sink = identity(42) sink = identity(42)", self.workload())

    def test_shared_driver_text_is_required(self):
        with self.assertRaises(RuntimeError):
            runner.require_shared_driver(config(), b"sink = identity(42)", self.workload())


class ClassificationInputsTest(unittest.TestCase):
    def row(self, role, state, **classes):
        base = {"never_compiled": False, "permanent_bailout": False, "final_tier_done": False}
        base.update(classes)
        return {"role_id": role, "kind": "helper", "STABLE_FINAL_OPTIMIZED_STATE": state, "classes": base}

    def test_predicates_only_and_no_class_is_chosen(self):
        units = [
            {"unit": "u1", "required_roots": [self.row("callback", "NO", permanent_bailout=True), self.row("repeat", "YES", final_tier_done=True)], "compiled_shape": {"families": {"activation_creation": {"SURVIVES_OPTIMIZED_GRAPH": "YES"}}}},
            {"unit": "u2", "required_roots": [self.row("repeat", "NO", final_tier_done=True)]},
        ]
        result = runner.classification_inputs(units)
        self.assertEqual(["u1::callback::helper"], result["A_required_roots_permanently_failed_without_later_success"])
        self.assertEqual(["u2::repeat::helper"], result["B_required_roots_compiled_but_not_stable"])
        self.assertEqual(["u1::repeat::helper"], result["required_roots_stable"])
        self.assertEqual(["u1"], result["C_D_family_survival_by_unit"]["activation_creation"]["YES"])
        self.assertNotIn("causal_class", result)


if __name__ == "__main__":
    unittest.main()
