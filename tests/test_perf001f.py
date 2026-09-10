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

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runner import perf001f


class Perf001fHarnessTest(unittest.TestCase):
    def test_config_preserves_six_approved_workloads(self) -> None:
        cfg = perf001f.validate_config()
        self.assertEqual(
            "0372a58addc63f305c911811659edd9b2b508420",
            cfg["protos_revision"],
        )
        self.assertEqual(list(perf001f.EXPECTED_IDS), [entry["id"] for entry in cfg["workloads"]])
        self.assertEqual(
            list(perf001f.EXPECTED_RESULTS),
            [entry["expected"] for entry in cfg["workloads"]],
        )

    def test_cpu_list_parser(self) -> None:
        self.assertEqual([0, 1, 2, 4, 7, 8], perf001f.parse_cpu_list("0-2,4,7-8"))
        with self.assertRaises(ValueError):
            perf001f.parse_cpu_list("4-2")

    def test_physical_core_selection_avoids_smt_siblings(self) -> None:
        records = [
            {"cpu": 0, "package": 0, "core": 0},
            {"cpu": 4, "package": 0, "core": 0},
            {"cpu": 1, "package": 0, "core": 1},
            {"cpu": 5, "package": 0, "core": 1},
            {"cpu": 2, "package": 0, "core": 2},
            {"cpu": 6, "package": 0, "core": 2},
            {"cpu": 3, "package": 0, "core": 3},
            {"cpu": 7, "package": 0, "core": 3},
        ]
        series = perf001f.select_physical_core_series(records, [1, 2, 4, 8])
        self.assertEqual([1, 2, 4], [entry["width"] for entry in series])
        self.assertEqual("0", series[0]["cpuset"])
        self.assertEqual("0,1", series[1]["cpuset"])
        self.assertEqual("0,1,2,3", series[2]["cpuset"])

    def test_physical_core_selection_is_package_aware(self) -> None:
        records = [
            {"cpu": 8, "package": 1, "core": 0},
            {"cpu": 0, "package": 0, "core": 0},
            {"cpu": 9, "package": 1, "core": 1},
            {"cpu": 1, "package": 0, "core": 1},
        ]
        series = perf001f.select_physical_core_series(records, [1, 2, 4])
        self.assertEqual("0,1,8,9", series[-1]["cpuset"])

    def test_toolchain_validation_uses_pinned_primary_runtime(self) -> None:
        payload = {
            "schema": "protos-toolchain-v1",
            "java": {"bytecode_release": 21},
            "graalvm": {
                "distribution": "graalvm-community",
                "release": "25.3.4.1",
                "jdk_feature": 25,
                "jdk_version": "25.0.4.1",
                "container_channel": "25i3",
                "container_image": "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825",
            },
            "graal_components": {"version": "25.3.4.1"},
            "maven": {"version": "3.9.9"},
            "policy": {"floating_primary_runtime": False},
        }
        observed = perf001f.validate_toolchain_payload(payload)
        self.assertEqual("3.9.9", observed["maven_version"])
        self.assertEqual("25.0.4.1", observed["jdk_version"])
        floating = json.loads(json.dumps(payload))
        floating["policy"]["floating_primary_runtime"] = True
        with self.assertRaises(RuntimeError):
            perf001f.validate_toolchain_payload(floating)

    def test_dockerfile_builds_official_portable_distribution_and_runtime_probe(self) -> None:
        text = (ROOT / "docker" / "protos-perf001f" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("python3 dist/build_portable.py", text)
        self.assertIn("dist/smoke_optimizing_runtime.sh", text)
        self.assertIn("dist/Dist001RuntimeProbe.java", text)
        self.assertIn("/out/protos", text)
        self.assertIn('ENTRYPOINT ["/opt/protos/bin/protos"]', text)
        self.assertNotIn("ProtosSourceCompiler", text)
        self.assertNotIn("-Xss128m", text)
        self.assertNotIn("COPY --from=build /src /opt/protos", text)

    def test_correctness_observation_wrapper_changes_only_terminal_run(self) -> None:
        original_root = perf001f.ROOT
        original_work = perf001f.WORK
        original_config = perf001f.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                temp = Path(tmp)
                source = temp / "source"
                corpus = source / "protos/benchmarks/concurrency"
                corpus.mkdir(parents=True)
                cfg = {
                    "canonical_corpus": "protos/benchmarks/concurrency",
                    "workloads": [{"source": "case.protos"}],
                }
                config_path = temp / "perf001f.json"
                config_path.write_text(json.dumps(cfg), encoding="utf-8")
                canonical = "worker: () => { 7 }\n\nrun: () => { worker() }\n\nrun()\n"
                (corpus / "case.protos").write_text(canonical, encoding="utf-8")
                perf001f.ROOT = temp
                perf001f.WORK = temp / "work"
                perf001f.CONFIG_PATH = config_path
                observed = perf001f.prepare_observation_sources(source)
                wrapper = (perf001f.WORK / "observed/case.protos").read_text(encoding="utf-8")
                self.assertEqual(
                    "worker: () => { 7 }\n\nrun: () => { worker() }\n\nprint(run())\n",
                    wrapper,
                )
                meta = observed["case.protos"]
                self.assertEqual(perf001f.sha256_text(canonical), meta["canonical_sha256"])
                self.assertEqual(perf001f.sha256_text(wrapper), meta["observation_sha256"])
                self.assertEqual("terminal run() -> print(run())", meta["observation_transform"])
        finally:
            perf001f.ROOT = original_root
            perf001f.WORK = original_work
            perf001f.CONFIG_PATH = original_config

    def test_correctness_observation_wrapper_rejects_noncanonical_terminal(self) -> None:
        original_root = perf001f.ROOT
        original_work = perf001f.WORK
        original_config = perf001f.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                temp = Path(tmp)
                source = temp / "source"
                corpus = source / "protos/benchmarks/concurrency"
                corpus.mkdir(parents=True)
                cfg = {
                    "canonical_corpus": "protos/benchmarks/concurrency",
                    "workloads": [{"source": "case.protos"}],
                }
                config_path = temp / "perf001f.json"
                config_path.write_text(json.dumps(cfg), encoding="utf-8")
                (corpus / "case.protos").write_text("run: () => { 7 }\n7\n", encoding="utf-8")
                perf001f.ROOT = temp
                perf001f.WORK = temp / "work"
                perf001f.CONFIG_PATH = config_path
                with self.assertRaises(RuntimeError):
                    perf001f.prepare_observation_sources(source)
        finally:
            perf001f.ROOT = original_root
            perf001f.WORK = original_work
            perf001f.CONFIG_PATH = original_config

    def test_new_executable_files_carry_apl_notice(self) -> None:
        notice = "THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE"
        for relative in (
            "runner/perf001f.py",
            "tests/test_perf001f.py",
            "docker/protos-perf001f/Dockerfile",
        ):
            self.assertIn(notice, (ROOT / relative).read_text(encoding="utf-8"), relative)


# PERF001F-H2-PERSISTENT-DRIVER
class Perf001fPersistentDriverH2Test(unittest.TestCase):
    def test_h2_config_retains_corpus_origin_and_gate_closure(self) -> None:
        cfg = perf001f.validate_config(announce=False)
        self.assertEqual("reference-evidence-runner-ready", cfg["phase"])
        self.assertEqual("faa1714523d68650447047a05d184ab17a747c06", cfg["corpus_publication_revision"])
        self.assertEqual("0372a58addc63f305c911811659edd9b2b508420", cfg["protos_revision"])
        self.assertEqual("a08844c7ba59f4a213e4d318bcf3bee32393c2a9", cfg["reference_gate_satisfied_by"])
        self.assertEqual("0372a58addc63f305c911811659edd9b2b508420", cfg["runtime_blocker_239_fixed_by"])

    def test_persistent_driver_command_uses_portable_runtime_classpath(self) -> None:
        cfg = perf001f.config()
        workload = cfg["workloads"][0]
        command = perf001f.persistent_driver_command(
            "image:test", "2", workload["source"], workload["expected"], 20, 20
        )
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("--cpuset-cpus", command)
        self.assertIn("/opt/perf001f/driver:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*", command)
        self.assertIn("Perf001fPersistentDriver", command)
        self.assertEqual("20", command[-2])
        self.assertEqual("20", command[-1])

    def test_persistent_driver_is_production_hosted_and_parse_free_in_timed_loop(self) -> None:
        text = (ROOT / "docker/protos-perf001f/Perf001fPersistentDriver.java").read_text(encoding="utf-8")
        self.assertIn("ProtosPolyglotRuntimeHost.open()", text)
        self.assertIn("runtimeHost.hostProcess(", text)
        self.assertIn("processContext.execute(source, bootstrap.activation())", text)
        self.assertIn('readLocalSlot("run")', text)
        self.assertIn('String terminal = "run()"', text)
        self.assertIn(' + "run\\n"', text)
        self.assertIn("ProtosClosureInvoker.invokeInTask(", text)
        self.assertIn("dispatchUntilTerminal(task, () -> false)", text)
        self.assertNotIn("ProtosSourceCompiler", text)
        self.assertNotIn("Thread.sleep", text)
        measure_body = text.split("private static List<Long> measureSeries", 1)[1]
        self.assertNotIn("Source.newBuilder", measure_body.split("private static void requireCompletedInteger", 1)[0])

    def test_h2_driver_has_apl_notice(self) -> None:
        notice = "THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE"
        self.assertIn(
            notice,
            (ROOT / "docker/protos-perf001f/Perf001fPersistentDriver.java").read_text(encoding="utf-8"),
        )


# PERF001F-H3-REFERENCE-RUNNER
class Perf001fReferenceRunnerH3Test(unittest.TestCase):
    def test_h3_config_repins_runtime_without_rewriting_i026_gate_provenance(self) -> None:
        cfg = perf001f.validate_config(announce=False)
        self.assertEqual("reference-evidence-runner-ready", cfg["phase"])
        self.assertEqual("0372a58addc63f305c911811659edd9b2b508420", cfg["protos_revision"])
        self.assertEqual("faa1714523d68650447047a05d184ab17a747c06", cfg["corpus_publication_revision"])
        self.assertEqual("a08844c7ba59f4a213e4d318bcf3bee32393c2a9", cfg["reference_gate_satisfied_by"])
        self.assertEqual("0372a58addc63f305c911811659edd9b2b508420", cfg["runtime_blocker_239_fixed_by"])

    def test_h3_startup_controller_is_bounded_and_non_pipe(self) -> None:
        text = (ROOT / "docker/protos-perf001f/Perf001fStartupDriver.java").read_text(encoding="utf-8")
        for required in (
            "builder.redirectOutput(stdout.toFile())",
            "builder.redirectError(stderr.toFile())",
            "child.waitFor(timeoutSeconds, TimeUnit.SECONDS)",
            "child.destroyForcibly()",
            "STARTUP_SAMPLE_BEGIN",
            "STARTUP_SAMPLE_PASS",
            "Perf001fPersistentDriver",
        ):
            self.assertIn(required, text)
        self.assertNotIn(".readAllBytes(", text)
        self.assertNotIn("Thread.sleep", text)
        self.assertNotIn("-Xss", text)

    def test_h3_dockerfile_compiles_both_measurement_drivers(self) -> None:
        text = (ROOT / "docker/protos-perf001f/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("Perf001fPersistentDriver.java", text)
        self.assertIn("Perf001fStartupDriver.java", text)
        self.assertIn("/out/driver", text)
        self.assertIn("/out/startup", text)
        self.assertIn("/opt/perf001f/driver", text)
        self.assertIn("/opt/perf001f/startup", text)

    def test_h3_new_executables_have_apl_notice(self) -> None:
        notice = "THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE"
        for relative in (
            "docker/protos-perf001f/Perf001fStartupDriver.java",
            "runner/perf001f_reference.py",
        ):
            self.assertIn(notice, (ROOT / relative).read_text(encoding="utf-8"), relative)

if __name__ == "__main__":
    unittest.main()
