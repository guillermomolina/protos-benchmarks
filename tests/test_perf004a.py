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
import unittest

from runner import perf004a

ROOT = Path(__file__).resolve().parents[1]


class Perf004aTimingHarnessTest(unittest.TestCase):
    def test_static_contract(self):
        cfg = perf004a.validate()
        self.assertEqual("PERF004-A2", cfg["slice"])
        self.assertFalse(cfg["timing_claim"])
        self.assertEqual(11, len(cfg["workloads"]))
        self.assertEqual(
            "d8df6daf11015b0a074ed47456e946d985d111db",
            cfg["a1_revision"],
        )

    def test_statistics_are_deterministic(self):
        observed = perf004a.summary([10, 20, 30, 40, 50])
        self.assertEqual(5, observed["count"])
        self.assertEqual(30.0, observed["median_ns"])
        self.assertEqual(10.0, observed["mad_ns"])
        self.assertEqual(10, observed["min_ns"])
        self.assertEqual(50, observed["max_ns"])
        self.assertEqual(50, observed["p95_ns"])

    def test_per_iteration_medians(self):
        self.assertEqual(
            [20.0, 30.0],
            perf004a.per_iteration_medians([[10, 20], [20, 30], [30, 40]]),
        )

    def test_workload_mapping_remains_complete(self):
        cfg = json.loads((ROOT / "config/perf004a.json").read_text(encoding="utf-8"))
        entries = perf004a.workload_entries(cfg)
        self.assertEqual(tuple(item["id"] for item in entries), perf004a.EXPECTED_IDS)
        for item in entries:
            self.assertRegex(item["source_blob_sha"], r"^[0-9a-f]{40}$")

    def test_reused_protos_persistent_driver_is_production_hosted_and_parse_free_in_timed_loop(self):
        text = (
            ROOT / "docker/protos-perf006d/Perf006dPersistentDriver.java"
        ).read_text(encoding="utf-8")
        self.assertIn("ProtosPolyglotRuntimeHost.open()", text)
        self.assertIn("runtimeHost.hostProcess(", text)
        self.assertIn("processContext.execute(source, activation)", text)
        self.assertIn("freshModuleActivation", text)
        self.assertNotIn("ProtosSourceCompiler", text)
        self.assertNotIn("Thread.sleep", text)
        measure_body = text.split("private static List<Long> measureSeries", 1)[1]
        measure_body = measure_body.split(
            "private static ProtosActivation freshModuleActivation", 1
        )[0]
        self.assertNotIn("Source.newBuilder", measure_body)

    def test_reused_protos_startup_controller_is_bounded_and_non_pipe(self):
        text = (
            ROOT / "docker/protos-perf006d/Perf006dStartupController.java"
        ).read_text(encoding="utf-8")
        for required in (
            "builder.redirectOutput(stdout.toFile())",
            "builder.redirectError(stderr.toFile())",
            "child.waitFor(timeoutSeconds, TimeUnit.SECONDS)",
            "child.destroyForcibly()",
            "STARTUP_SAMPLE_BEGIN",
            "STARTUP_SAMPLE_PASS",
            "Perf006dPersistentDriver",
        ):
            self.assertIn(required, text)
        self.assertNotIn(".readAllBytes(", text)
        self.assertNotIn("Thread.sleep", text)

    def test_protos_timing_uses_java_entrypoint_override(self):
        text = (ROOT / "runner/perf004a.py").read_text(encoding="utf-8")
        self.assertIn('"--entrypoint",\n        "java",', text)
        self.assertIn("def docker_java(", text)
        self.assertIn("reused[\"startup_controller\"]", text)
        self.assertIn("reused[\"persistent_driver\"]", text)

    def test_reference_requires_exact_clean_harness(self):
        with self.assertRaises(RuntimeError):
            perf004a.require_clean_exact_harness("main")


if __name__ == "__main__":
    unittest.main()
