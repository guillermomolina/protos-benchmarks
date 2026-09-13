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

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runner" / "perf006d.py"

spec = importlib.util.spec_from_file_location("perf006d", MODULE_PATH)
perf006d = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(perf006d)


class Perf006dContractTest(unittest.TestCase):
    def test_static_contract(self):
        cfg = perf006d.validate()
        self.assertFalse(cfg["timing_claim"])
        self.assertEqual(5, len(cfg["workloads"]))

    def test_warning_classifier(self):
        self.assertTrue(
            perf006d.FALLBACK_WARNING_RE.search(
                "No optimizing Truffle runtime found on the module or class-path."
            )
        )
        self.assertTrue(
            perf006d.FALLBACK_WARNING_RE.search(
                "fallback runtime that does not support runtime compilation"
            )
        )
        self.assertFalse(
            perf006d.FALLBACK_WARNING_RE.search(
                "sun.misc.Unsafe::objectFieldOffset will be removed"
            )
        )

    def test_historical_suite_pin_is_unchanged(self):
        suite = json.loads((ROOT / "config" / "suite.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "42b8264a36254dafbd97d80f5181790e28b9de12",
            suite["protos_corpus_revision"],
        )


if __name__ == "__main__":
    unittest.main()
