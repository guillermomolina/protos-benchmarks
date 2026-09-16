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
import re
import subprocess
import tempfile
import unittest

from runner.perf009a import (
    load_config,
    materialize_source,
    materialized_source_identity,
    measurement_plan,
    parse_makefile_contract_text,
    parse_test_tool_phase_names_text,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf009a.json"
EXPECTED_PROTOS_REVISION = "e5f56c6ee829090c3ed12a9b6703f5984d872a90"


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


class Perf009aConfigTest(unittest.TestCase):
    def test_config_pins_reproducible_protos_source(self) -> None:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

        self.assertEqual(2, cfg["schema_version"])
        self.assertEqual("PERF009", cfg["perf_item"])
        self.assertEqual("PERF009-A", cfg["slice"])
        self.assertEqual(
            "baseline-and-critical-path-attribution",
            cfg["phase"],
        )
        self.assertIs(False, cfg["timing_claim"])

        self.assertEqual(
            "https://github.com/guillermomolina/protos.git",
            cfg["protos_repository"],
        )
        self.assertEqual(
            EXPECTED_PROTOS_REVISION,
            cfg["protos_revision"],
        )
        self.assertRegex(cfg["protos_revision"], r"^[0-9a-f]{40}$")

        self.assertEqual(
            {
                "mode": "isolated-git-fetch",
                "require_exact_revision": True,
            },
            cfg["source_materialization"],
        )

    def test_config_has_no_local_layout_or_duplicated_toolchain(self) -> None:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        raw = CONFIG.read_text(encoding="utf-8")

        self.assertNotIn("../protos", raw)
        self.assertNotIn("/home/", raw)
        self.assertNotIn("toolchain", cfg)


    def test_a1_contract_pins_current_measurement_surface(self) -> None:
        cfg = load_config()
        contract = cfg["a1_inventory_contract"]
        self.assertEqual(4, contract["ci_java_jobs"])
        self.assertEqual(4, contract["ci_protos_jobs"])
        self.assertEqual(3, contract["minimum_repetitions"])
        self.assertEqual([1, 2, 4, 8], contract["diagnostic_protos_jobs"])
        self.assertEqual("ProtosI026FDapBehaviorTest", contract["expected_java_serial_test"])
        self.assertEqual(8, len(contract["expected_java_slow_test_classes"]))
        self.assertEqual(18, len(contract["expected_test_tool_phases"]))
        self.assertEqual("package-toml", contract["expected_test_tool_phases"][4])
        self.assertEqual("package-tool-project-projection", contract["expected_test_tool_phases"][-1])

    def test_makefile_contract_parser_keeps_quarantine_distinct(self) -> None:
        makefile = "\n".join([
            "JAVA_TEST_JOBS ?= 8",
            "PROTOS_TEST_JOBS ?= 8",
            "JAVA_SLOW_TEST_EXCLUDES := **/SlowOne.java,**/SlowTwo.java",
            "JAVA_SERIAL_TEST := SerialOnly",
            "test: test-java test-protos",
            "test-protos:",
            "\\tbin/protos test --jobs $(PROTOS_TEST_JOBS)",
        ]) + "\n"
        parsed = parse_makefile_contract_text(makefile)
        self.assertEqual(8, parsed["java_test_jobs_default"])
        self.assertEqual(8, parsed["protos_test_jobs_default"])
        self.assertEqual(["SlowOne", "SlowTwo"], parsed["slow_test_classes"])
        self.assertEqual("SerialOnly", parsed["serial_test_class"])
        self.assertEqual(["test-java", "test-protos"], parsed["test_target_order"])

    def test_test_tool_phase_parser_preserves_order(self) -> None:
        main = (
            'phaseNames: Array(\n'
            '    "main",\n'
            '    "actor",\n'
            '    "package-toml"\n'
            ')\n'
            'phaseNames.freeze()\n'
        )

        self.assertEqual(
            ["main", "actor", "package-toml"],
            parse_test_tool_phase_names_text(main),
        )

    def test_measurement_plan_separates_operational_and_complete_reference(self) -> None:
        plan = measurement_plan(load_config())
        lanes = {lane["id"]: lane for lane in plan["lanes"]}
        self.assertEqual(
            ["make", "test", "JAVA_TEST_JOBS=4", "PROTOS_TEST_JOBS=4"],
            lanes["current-ci"]["command"],
        )
        self.assertEqual("CURRENT_OPERATIONAL_PATH_WITH_QUARANTINE", lanes["current-ci"]["role"])
        self.assertEqual(["mvn", "test"], lanes["java-complete-reference"]["command"])
        self.assertEqual(
            "COMPLETE_JAVA_COVERAGE_REFERENCE_NOT_CURRENT_CI_TOPOLOGY",
            lanes["java-complete-reference"]["role"],
        )
        self.assertEqual([1, 2, 4, 8], plan["diagnostic_protos_jobs"])


class Perf009aMaterializationTest(unittest.TestCase):
    def test_materializes_exact_revision_into_isolated_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / "origin"
            destination = root / "materialized"

            origin.mkdir()
            git(origin, "init")
            git(origin, "config", "user.name", "PERF009 test")
            git(origin, "config", "user.email", "perf009@example.invalid")

            (origin / "toolchain.json").write_text(
                json.dumps(
                    {
                        "schema": "protos-toolchain-v1",
                        "java": {
                            "bytecode_release": 21,
                        },
                        "graalvm": {
                            "release": "25.3.4.1",
                            "jdk_feature": 25,
                            "jdk_version": "25.0.4.1",
                            "container_channel": "25i3",
                            "container_image": (
                                "ghcr.io/graalvm/graalvm-community:"
                                "25i3-25.0.4.1-ol10-20260825"
                            ),
                        },
                        "graal_components": {
                            "version": "25.3.4.1",
                        },
                        "maven": {
                            "version": "3.9.9",
                        },
                        "policy": {
                            "floating_primary_runtime": False,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            git(origin, "add", "toolchain.json")
            git(origin, "commit", "-m", "test revision")

            revision = git(origin, "rev-parse", "HEAD")
            self.assertRegex(revision, r"^[0-9a-f]{40}$")

            observed = materialize_source(
                str(origin),
                revision,
                destination,
            )

            self.assertEqual(destination, observed)
            self.assertEqual(
                revision,
                git(destination, "rev-parse", "HEAD"),
            )
            self.assertTrue((destination / "toolchain.json").is_file())
            self.assertEqual(
                "",
                git(destination, "status", "--porcelain"),
            )

            identity = materialized_source_identity(
                str(origin),
                revision,
                root / "identity-source",
            )

            self.assertEqual(str(origin), identity["protos_repository"])
            self.assertEqual(revision, identity["protos_revision"])
            self.assertEqual(
                "25.3.4.1",
                identity["toolchain"]["graalvm_release"],
            )
            self.assertEqual(
                "25.0.4.1",
                identity["toolchain"]["jdk_version"],
            )
            self.assertEqual(
                "3.9.9",
                identity["toolchain"]["maven_version"],
            )


if __name__ == "__main__":
    unittest.main()
