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

"""Focal, Docker-free contract tests for the PERF008 harness (config + source shape only).

These do not build the image, run the container matrix, or invoke javac/java; that
requires Docker and is human-executed per this repository's human-executor mode.
"""

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runner/perf008.py"
spec = importlib.util.spec_from_file_location("perf008", MODULE_PATH)
perf008 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(perf008)


class Perf008ContractTest(unittest.TestCase):
    def test_static_contract(self):
        cfg = perf008.validate()
        self.assertEqual("PERF008", cfg["slice"])
        self.assertFalse(cfg["diagnostic_claim"])
        self.assertEqual(
            "529ab58c2cf57a2e4170dd5ffa972651e89ac92e", cfg["protos_revision"]
        )
        self.assertEqual(
            "4a03efc15620b37b2e418b3df30b4a26486446ec",
            cfg["historical_protos_revision"],
        )

    def test_experiment_matrix_matches_perf004_b2d_exactly(self):
        cfg = json.loads((ROOT / "config/perf008.json").read_text(encoding="utf-8"))
        b2d_cfg = json.loads(
            (ROOT / "config/perf004b2d.json").read_text(encoding="utf-8")
        )
        self.assertEqual(b2d_cfg["controls"], cfg["controls"])
        self.assertEqual(10000, cfg["operation_count"])
        self.assertEqual(20, cfg["warmup_iterations"])
        self.assertEqual(100, cfg["steady_iterations"])
        self.assertEqual("10 ms", cfg["execution_sample_period"])
        self.assertEqual(4, len(cfg["controls"]))

    def test_steady_state_only_and_stack_depth_declared(self):
        cfg = json.loads((ROOT / "config/perf008.json").read_text(encoding="utf-8"))
        self.assertEqual(32, cfg["stack_depth_limit"])
        self.assertEqual("steady_only", cfg["jfr_recording_phase"])

    def test_new_driver_is_not_an_in_place_edit_of_the_shared_driver(self):
        # Perf006dPersistentDriver.java must stay free of jdk.jfr references: six other
        # runner scripts invoke it without --add-modules jdk.jfr, and adding a jdk.jfr
        # import there would make the class fail to load for all of them.
        shared_driver = (
            ROOT / "docker/protos-perf006d/Perf006dPersistentDriver.java"
        ).read_text(encoding="utf-8")
        self.assertNotIn("jdk.jfr", shared_driver)

        new_driver = (
            ROOT / "docker/protos-perf006d3/Perf008SteadyStateDriver.java"
        ).read_text(encoding="utf-8")
        self.assertIn("import jdk.jfr.Recording;", new_driver)
        self.assertIn("import jdk.jfr.Configuration;", new_driver)

    def test_analyzer_output_schema_is_additive(self):
        # Every PERF006-D3 field name must still be present verbatim so
        # runner/perf006d3.py and runner/perf004b2d.py keep working unmodified.
        analyzer_src = (
            ROOT / "docker/protos-perf006d3/Perf006d3JfrAnalyzer.java"
        ).read_text(encoding="utf-8")
        for required in (
            "EXECUTION_SAMPLE",
            "HISTORICAL_SYMBOL",
            "topFrames",
            "threadSamples",
            "deoptReasons",
            "deoptActions",
            "deoptMethods",
            "MAX_STACK_DEPTH = 32",
        ):
            self.assertIn(required, analyzer_src)

    def test_dockerfile_extends_rather_than_replaces_diagnostic_compile_unit(self):
        dockerfile = (
            ROOT / "docker/protos-perf006d3/Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "/tmp/Perf006dRuntimeProbe.java /tmp/Perf006dPersistentDriver.java",
            dockerfile,
        )
        self.assertIn("Perf008SteadyStateDriver.java", dockerfile)
        self.assertIn("EXPECTED_CONTAINER_IMAGE", dockerfile)

    def test_python_package_is_parametrized_not_hardcoded(self):
        # Oracle Linux 8 (historical toolchain) needs the versioned `python39` module
        # package; Oracle Linux 10 (current toolchain) removed module packages and ships
        # a sufficient `python3` directly. A hardcoded package name breaks one of the two.
        dockerfile = (
            ROOT / "docker/protos-perf006d3/Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertIn("ARG PYTHON_PACKAGE=python39", dockerfile)
        self.assertIn("${PYTHON_PACKAGE}", dockerfile)
        self.assertNotIn("install -y git gzip tar findutils ca-certificates python39", dockerfile)

        cfg = json.loads((ROOT / "config/perf008.json").read_text(encoding="utf-8"))
        self.assertEqual("python3", cfg["toolchain"]["python_package"])


if __name__ == "__main__":
    unittest.main()
