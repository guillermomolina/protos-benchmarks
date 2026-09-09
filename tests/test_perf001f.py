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
            "faa1714523d68650447047a05d184ab17a747c06",
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


if __name__ == "__main__":
    unittest.main()
