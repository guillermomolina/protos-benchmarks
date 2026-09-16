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

import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class IgvAnalyzerTest(unittest.TestCase):
    def test_help_exposes_commands(self):
        result = subprocess.run(
            [str(ROOT / "scripts" / "igv_analyzer.sh"), "--help"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for command in ("build", "smoke", "list", "filter", "flatten"):
            self.assertIn(command, result.stdout)

    def test_dockerfile_pins_current_toolchain(self):
        dockerfile = (
            ROOT / "docker" / "igv-analyzer" / "Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "GRAAL_REV=7b025988a922a73286d1326e1eddc1ca39d3f569",
            dockerfile,
        )
        self.assertIn(
            "MX_REV=22381992c7322f661498cd6101144f0f49c72ae1",
            dockerfile,
        )
        self.assertIn("GRAAL_IGVUTIL", dockerfile)
        self.assertIn("eclipse-temurin:21.0.12_8-jre-jammy", dockerfile)

    def test_default_and_historical_analyzers_are_explicit(self):
        current_docker = ROOT / "docker" / "igv-analyzer"
        current_script = ROOT / "scripts" / "igv_analyzer.sh"
        historical_docker = ROOT / "docker" / "igv-analyzer24"
        historical_script = ROOT / "scripts" / "igv_analyzer24.sh"

        self.assertTrue(current_docker.is_dir())
        self.assertTrue(current_script.is_file())
        self.assertTrue(historical_docker.is_dir())
        self.assertTrue(historical_script.is_file())

        current_text = current_script.read_text(encoding="utf-8")
        historical_text = historical_script.read_text(encoding="utf-8")

        self.assertIn("graal-25.3.4.1", current_text)
        self.assertNotIn("graal-24.0.0", current_text)
        self.assertIn("graal-24.0.0", historical_text)

    def test_analyzer_contract_has_no_machine_local_checkout_path(self):
        paths = (
            ROOT / "docker" / "igv-analyzer" / "Dockerfile",
            ROOT / "docker" / "igv-analyzer24" / "Dockerfile",
            ROOT / "scripts" / "igv_analyzer.sh",
            ROOT / "scripts" / "igv_analyzer24.sh",
            ROOT / "BENCHMARKING.md",
        )
        forbidden_patterns = (
            re.compile(r"/home/[^/\\s]+/"),
            re.compile(r"/Users/[^/\\s]+/"),
            re.compile(r"~/(?:[^/\\s]+/)+"),
            re.compile(r"protos-benchmarks-igv[0-9]+"),
        )
        for path in paths:
            content = path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                self.assertIsNone(pattern.search(content), str(path))


if __name__ == "__main__":
    unittest.main()
