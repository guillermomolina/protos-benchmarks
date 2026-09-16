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
import tempfile
import unittest

from runner.toolchain import read_toolchain, validate_toolchain_payload


def valid_payload() -> dict:
    return {
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


class ToolchainTest(unittest.TestCase):
    def test_valid_payload_resolves_canonical_identity(self) -> None:
        observed = validate_toolchain_payload(valid_payload())

        self.assertEqual("protos-toolchain-v1", observed["schema"])
        self.assertEqual(21, observed["bytecode_release"])
        self.assertEqual("3.9.9", observed["maven_version"])
        self.assertEqual("25.3.4.1", observed["graalvm_release"])
        self.assertEqual(25, observed["jdk_feature"])
        self.assertEqual("25.0.4.1", observed["jdk_version"])
        self.assertEqual("25.3.4.1", observed["graal_components_version"])
        self.assertEqual("25i3", observed["container_channel"])
        self.assertEqual(
            "ghcr.io/graalvm/graalvm-community:"
            "25i3-25.0.4.1-ol10-20260825",
            observed["container_image"],
        )

    def test_read_toolchain_reads_measured_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "toolchain.json").write_text(
                json.dumps(valid_payload()),
                encoding="utf-8",
            )

            observed = read_toolchain(source)

        self.assertEqual("25.3.4.1", observed["graalvm_release"])
        self.assertEqual("25.0.4.1", observed["jdk_version"])

    def test_floating_runtime_is_rejected(self) -> None:
        payload = valid_payload()
        payload["policy"]["floating_primary_runtime"] = True

        with self.assertRaises(RuntimeError):
            validate_toolchain_payload(payload)


    def test_invalid_toolchain_contracts_are_rejected(self) -> None:
        cases = []

        payload = valid_payload()
        payload["schema"] = "unsupported"
        cases.append(("schema", payload))

        payload = valid_payload()
        payload["java"]["bytecode_release"] = 20
        cases.append(("bytecode release", payload))

        payload = valid_payload()
        payload["maven"]["version"] = "latest"
        cases.append(("Maven version", payload))

        payload = valid_payload()
        payload["graalvm"]["jdk_version"] = ""
        cases.append(("runtime identity", payload))

        payload = valid_payload()
        payload["graal_components"]["version"] = "25.3.4.2"
        cases.append(("component mismatch", payload))

        payload = valid_payload()
        payload["graalvm"]["container_image"] = (
            "ghcr.io/graalvm/graalvm-community:latest"
        )
        cases.append(("floating image", payload))

        for name, payload in cases:
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):
                    validate_toolchain_payload(payload)

    def test_missing_toolchain_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                read_toolchain(Path(directory))


if __name__ == "__main__":
    unittest.main()
