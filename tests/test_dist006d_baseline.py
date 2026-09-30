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

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runner/dist006d_baseline.py"
spec = importlib.util.spec_from_file_location("dist006d_baseline", MODULE_PATH)
dist006d = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(dist006d)


class Dist006dContractTest(unittest.TestCase):
    def config(self):
        return json.loads((ROOT / "config/dist006d-baseline.json").read_text(encoding="utf-8"))

    def assert_config_rejected(self, mutator):
        cfg = copy.deepcopy(self.config())
        mutator(cfg)
        with self.assertRaises(RuntimeError):
            dist006d.validate_config_payload(cfg)

    def test_static_contract(self):
        cfg = dist006d.validate()
        self.assertEqual("DIST006-D1", cfg["slice"])
        self.assertIsNone(cfg["protos"]["revision"])
        self.assertEqual(
            "protos-toolchain-v2",
            cfg["toolchain"]["schema"],
        )
        self.assertEqual(
            "3.9.9",
            cfg["toolchain"]["maven"]["minimum_version"],
        )
        self.assertEqual(
            3,
            cfg["toolchain"]["maven"]["supported_major"],
        )
        self.assertNotIn(
            "version",
            cfg["toolchain"]["maven"],
        )
        self.assertEqual(10000, cfg["operation_count"])
        self.assertEqual(120, cfg["warmup_iterations"])
        self.assertEqual(100, cfg["steady_iterations"])
        self.assertFalse(cfg["reference"]["paired_platform_formula"])
        self.assertFalse(cfg["smoke"]["retained_performance_evidence"])

    def test_workload_execution_preserves_recursive_benchmark_stack(self):
        module_text = MODULE_PATH.read_text(encoding="utf-8")

        correctness = module_text[
            module_text.index("def driver_correctness("):
            module_text.index("def driver_timing(")
        ]
        timing = module_text[
            module_text.index("def driver_timing("):
            module_text.index("def summarize_ns(")
        ]

        self.assertIn('"-Xss128m"', correctness)
        self.assertIn('"-Xss128m"', timing)

    def test_invalid_protos_sha_rejected(self):
        for value in (None, "main", "0" * 39, "A" * 40, "g" * 40):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    dist006d.require_exact_sha(value, "Protos revision")
        self.assertEqual("a" * 40, dist006d.require_exact_sha("a" * 40, "Protos revision"))

    def test_additive_toolchain_metadata_is_allowed(self):
        payload = copy.deepcopy(
            dist006d.CANONICAL_TOOLCHAIN_JSON
        )
        payload["ci"] = {
            "image": "ghcr.io/guillermomolina/protos-ci@sha256:example"
        }
        payload["graalvm"]["provenance"] = {
            "source": "additional-metadata"
        }

        self.assertIs(
            payload,
            dist006d.validate_toolchain_contract(payload),
        )

    def test_required_toolchain_fields_still_fail_closed(self):
        payload = copy.deepcopy(
            dist006d.CANONICAL_TOOLCHAIN_JSON
        )
        del payload["graalvm"]["release"]

        with self.assertRaisesRegex(
            RuntimeError,
            "toolchain[.]graalvm[.]release",
        ):
            dist006d.validate_toolchain_contract(payload)

        payload = copy.deepcopy(
            dist006d.CANONICAL_TOOLCHAIN_JSON
        )
        payload["graalvm"]["release"] = "25.4-wrong"

        with self.assertRaisesRegex(
            RuntimeError,
            "toolchain[.]graalvm[.]release",
        ):
            dist006d.validate_toolchain_contract(payload)

    def test_wrong_graalvm_release_fails_closed(self):
        self.assert_config_rejected(
            lambda cfg: cfg["toolchain"]["graalvm"].__setitem__("release", "25.3.4.1")
        )

    def test_wrong_jdk_version_fails_closed(self):
        self.assert_config_rejected(
            lambda cfg: cfg["toolchain"]["graalvm"].__setitem__("jdk_version", "25.0.4.1")
        )

    def test_wrong_container_image_fails_closed(self):
        self.assert_config_rejected(
            lambda cfg: cfg["toolchain"]["graalvm"].__setitem__(
                "container_image", "ghcr.io/graalvm/graalvm-community:25i4-ol10"
            )
        )

    def test_wrong_component_line_fails_closed(self):
        self.assert_config_rejected(
            lambda cfg: cfg["toolchain"]["graal_components"].__setitem__(
                "version", "25.3.4.1"
            )
        )

    def test_wrong_maven_minimum_fails_closed(self):
        self.assert_config_rejected(
            lambda cfg: cfg["toolchain"]["maven"].__setitem__(
                "minimum_version",
                "3.9.8",
            )
        )

    def test_wrong_maven_supported_major_fails_closed(self):
        self.assert_config_rejected(
            lambda cfg: cfg["toolchain"]["maven"].__setitem__(
                "supported_major",
                4,
            )
        )

    def test_maven_identity_parser_tolerates_preamble_and_ansi(self):
        identity = (
            "WARNING: distribution message\n"
            "\x1b[0mApache Maven 3.9.10 (Vendor build)\x1b[0m\n"
            "Maven home: /usr/share/maven\n"
            "Java version: 25.0.4.1.1\n"
        )

        self.assertEqual(
            "3.9.10",
            dist006d.extract_maven_runtime_version(identity),
        )

        with self.assertRaises(RuntimeError):
            dist006d.extract_maven_runtime_version(
                "WARNING only\nJava version: 25.0.4.1.1\n"
            )

        with self.assertRaises(RuntimeError):
            dist006d.extract_maven_runtime_version(
                "Apache Maven 3.9.9-RC1\n"
            )

    def test_actual_maven_runtime_uses_compatibility_range(self):
        for value in (
            "3.9.9",
            "3.9.10",
            "3.10.0",
            "3.99.1",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    value,
                    dist006d.validate_maven_runtime_version(value),
                )

        for value in (
            "3.9.8",
            "4.0.0",
            "3.9.9-RC1",
            "3.9",
            "latest",
            "03.9.9",
        ):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    dist006d.validate_maven_runtime_version(value)

    def test_floating_runtime_fails_closed(self):
        self.assert_config_rejected(
            lambda cfg: cfg["toolchain"]["policy"].__setitem__(
                "floating_primary_runtime", True
            )
        )

    def test_build_stage_toolchain_selection_fails_closed(self):
        docker_text = (
            ROOT / "docker/protos-dist006d/Dockerfile"
        ).read_text(encoding="utf-8")

        required_markers = (
            "ARG MAVEN_MINIMUM_VERSION=3.9.9",
            "ARG MAVEN_SUPPORTED_MAJOR=3",
            "--enablerepo=ol10_codeready_builder",
            "    maven \\",
            "    maven-unbound \\",
            'ENV PATH="${JAVA_HOME}/bin:${PATH}"',
            'test "$(command -v java)" = "$JAVA_HOME/bin/java"',
            'test "$(command -v javac)" = "$JAVA_HOME/bin/javac"',
            'grep -Fq "java.version = ${EXPECTED_JDK_VERSION}"',
            'grep -Fq "java.vm.vendor = GraalVM Community"',
            'JAVAC_FEATURE="${EXPECTED_JDK_VERSION%%.*}"',
            'grep -Eq "^javac ${JAVAC_FEATURE}([.]|$)"',
            "if actual < minimum:",
            "if actual[0] != supported_major:",
            'grep -Fq "Java version: ${EXPECTED_JDK_VERSION}"',
            'grep -Fq "vendor: GraalVM Community"',
            'grep -Fq "runtime: ${JAVA_HOME}"',
            '&& test -z "$(rpm -qa \'java-*-openjdk*\')"',
            "printf 'MAVEN_UNBOUND_RPM=%s\\n'",
            "printf 'REDUNDANT_OPENJDK_RPM=NO\\n'",
            '"schema": "protos-toolchain-v2"',
            '"minimum_version": "3.9.9"',
            '"supported_major": 3',
            '"$JAVA_HOME/bin/javac" -cp',
            (
                "printf 'JAVA_COMMAND=%s\\n' "
                '"$(command -v java)"'
            ),
            (
                "printf 'JAVAC_COMMAND=%s\\n' "
                '"$(command -v javac)"'
            ),
        )

        dist006d.validate_dockerfile_contract(docker_text)

        self.assertEqual(
            1,
            docker_text.count(
                "--enablerepo=ol10_codeready_builder"
            ),
        )

        self.assertNotIn(
            "EXPECTED_MAVEN_VERSION",
            docker_text,
        )

        for marker in required_markers:
            with self.subTest(marker=marker):
                mutated = docker_text.replace(
                    marker,
                    "DIST008_B2_MARKER_REMOVED",
                    1,
                )

                self.assertNotEqual(
                    docker_text,
                    mutated,
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    "Dockerfile structural contract"
                    "|Maven provisioning"
                    "|CodeReady Builder",
                ):
                    dist006d.validate_dockerfile_contract(
                        mutated
                    )

    def test_incomplete_workload_set_fails_closed(self):
        self.assert_config_rejected(lambda cfg: cfg["workloads"].pop())

    def test_reference_rejects_non_exact_harness_identity(self):
        expected = "a" * 40
        observed = "b" * 40
        with mock.patch.object(dist006d, "output", return_value=observed):
            with self.assertRaisesRegex(RuntimeError, "exact harness revision mismatch"):
                dist006d.exact_published_harness_revision(expected)

    def test_reference_rejects_dirty_harness_identity(self):
        revision = "a" * 40

        def fake_output(command):
            if command[:3] == ["git", "rev-parse", "HEAD"]:
                return revision
            if command[:3] == ["git", "status", "--porcelain"]:
                return " M runner/dist006d_baseline.py"
            raise AssertionError(command)

        with mock.patch.object(dist006d, "output", side_effect=fake_output):
            with self.assertRaisesRegex(RuntimeError, "clean harness worktree"):
                dist006d.exact_published_harness_revision(revision)

    def test_reference_rejects_unpublished_harness_identity(self):
        revision = "a" * 40

        def fake_output(command):
            if command[:3] == ["git", "rev-parse", "HEAD"]:
                return revision
            if command[:3] == ["git", "status", "--porcelain"]:
                return ""
            raise AssertionError(command)

        unpublished = subprocess.CompletedProcess(
            ["git", "merge-base", "--is-ancestor", revision, "origin/main"], 1, "", ""
        )
        with mock.patch.object(dist006d, "output", side_effect=fake_output), mock.patch.object(
            dist006d, "run", return_value=unpublished
        ):
            with self.assertRaisesRegex(RuntimeError, "published on origin/main"):
                dist006d.exact_published_harness_revision(revision)


if __name__ == "__main__":
    unittest.main()
