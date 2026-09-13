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
MODULE_PATH = ROOT / "runner/perf006d3.py"
spec = importlib.util.spec_from_file_location("perf006d3", MODULE_PATH)
perf006d3 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(perf006d3)


class Perf006d3ContractTest(unittest.TestCase):
    def test_static_contract(self):
        cfg = perf006d3.validate()
        self.assertEqual("PERF006-D3A", cfg["slice"])
        self.assertFalse(cfg["diagnostic_claim"])
        self.assertEqual("7e3c2a9554d7ac48d30e74572460e14aaecb8fec", cfg["d2_evidence_revision"])
        self.assertEqual("4a03efc15620b37b2e418b3df30b4a26486446ec", cfg["protos_revision"])

    def test_historical_evidence_is_structural_only(self):
        cfg = json.loads((ROOT / "config/perf006d3.json").read_text(encoding="utf-8"))
        historical = cfg["historical_pre_c_prime"]
        self.assertEqual(471.985, historical["wall_seconds_approx"])
        self.assertEqual(92.201, historical["hashmap_keyiterator_next_percent"])
        self.assertEqual(98.530, historical["main_thread_percent"])
        self.assertIn("not_absolute_performance_comparator", historical["classification"])

    def test_current_contract_does_not_enable_igv24(self):
        cfg = json.loads((ROOT / "config/perf006d3.json").read_text(encoding="utf-8"))
        self.assertFalse(cfg["current_diagnostic_contract"]["igv24_analyzer_used"])
        self.assertFalse(cfg["current_diagnostic_contract"]["production_optimization_allowed"])
        self.assertFalse(cfg["current_diagnostic_contract"]["reference_timing_changed"])
        self.assertFalse(cfg["current_diagnostic_contract"]["trace_compilation_details"])
        self.assertEqual("Print", cfg["current_diagnostic_contract"]["compilation_failure_action"])

    def test_trace_classifiers(self):
        sample = (
            "[engine] opt done engine=1 id=2 foo |Tier 1|\n"
            "[engine] opt failed engine=1 id=3 bar\n"
            "BailoutException\ninvalidated target\n"
        )
        self.assertEqual(1, len(perf006d3.TRACE_DONE_RE.findall(sample)))
        self.assertGreaterEqual(len(perf006d3.TRACE_FAILED_RE.findall(sample)), 1)
        self.assertEqual(1, len(perf006d3.TRACE_BAILOUT_RE.findall(sample)))
        self.assertEqual(1, len(perf006d3.TRACE_INVALIDATED_RE.findall(sample)))


if __name__ == "__main__":
    unittest.main()
