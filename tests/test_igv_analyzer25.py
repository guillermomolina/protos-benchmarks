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
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class IgvAnalyzer25Test(unittest.TestCase):
    def test_help_exposes_commands(self):
        result = subprocess.run(
            [str(ROOT / "scripts" / "igv_analyzer25.sh"), "--help"],
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
            ROOT / "docker" / "igv-analyzer25" / "Dockerfile"
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

    def test_historical_analyzer_is_retained(self):
        self.assertTrue((ROOT / "docker" / "igv-analyzer").is_dir())
        self.assertTrue((ROOT / "scripts" / "igv_analyzer.sh").is_file())


if __name__ == "__main__":
    unittest.main()
