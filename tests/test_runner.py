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
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runner import bench


class RunnerTest(unittest.TestCase):
    def test_revision_requires_exact_sha(self) -> None:
        sha = "a" * 40
        self.assertEqual(sha, bench.validate_revision(sha))
        with self.assertRaises(ValueError):
            bench.validate_revision("main")

    def test_architecture_normalization(self) -> None:
        self.assertEqual("amd64", bench.normalize_architecture("x86_64"))
        self.assertEqual("arm64", bench.normalize_architecture("aarch64"))

    def test_last_nonempty_line(self) -> None:
        self.assertEqual("2", bench.last_nonempty_line("warning\n2\n"))

    def test_perf001b_configuration(self) -> None:
        protos = json.loads((ROOT / "config/protos.json").read_text(encoding="utf-8"))
        runtimes = json.loads((ROOT / "config/runtimes.json").read_text(encoding="utf-8"))
        self.assertEqual("1 + 1", protos["smoke"]["source"])
        self.assertEqual("2", protos["smoke"]["expected_stdout"])
        self.assertEqual("24.0.0", runtimes["runtimes"]["protos"]["graalvm"]["graal_truffle_line"])
        self.assertEqual("ghcr.io/graalvm/jdk-community:22.0.0", runtimes["runtimes"]["protos"]["graalvm"]["base"])

    def test_protos_docker_from_args_are_global(self) -> None:
        dockerfile = (ROOT / "docker/protos/Dockerfile").read_text(encoding="utf-8")
        lines = [line.strip() for line in dockerfile.splitlines()]
        first_from = next(i for i, line in enumerate(lines) if line.startswith("FROM "))
        global_lines = lines[:first_from]
        self.assertIn("ARG BUILD_BASE=maven:3.9.9-eclipse-temurin-21", global_lines)
        self.assertIn("ARG GRAAL_BASE=ghcr.io/graalvm/jdk-community:22.0.0", global_lines)
        self.assertIn("FROM ${GRAAL_BASE}", lines[first_from + 1:])

    def test_protos_runtime_launches_packaged_jar_directly(self) -> None:
        dockerfile = (ROOT / "docker/protos/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY --from=build /out/protos.jar /opt/protos/protos.jar", dockerfile)
        self.assertIn('ENTRYPOINT ["java", "--enable-native-access=ALL-UNNAMED", "-jar", "/opt/protos/protos.jar"]', dockerfile)
        self.assertNotIn('ENTRYPOINT ["/opt/protos/bin/protos"]', dockerfile)
        self.assertIn("! -name 'original-*'", dockerfile)


if __name__ == "__main__":
    unittest.main()
