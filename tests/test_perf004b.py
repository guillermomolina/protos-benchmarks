# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
# THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
# "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

import json
from pathlib import Path
import unittest
from runner import perf004b

ROOT = Path(__file__).resolve().parents[1]

class Perf004bTest(unittest.TestCase):
    def test_contract(self):
        cfg = perf004b.validate()
        self.assertEqual("PERF004-B1", cfg["slice"])
        self.assertFalse(cfg["diagnostic_claim"])
        self.assertEqual(9, len(cfg["workloads"]))
        self.assertEqual("4a03efc15620b37b2e418b3df30b4a26486446ec", cfg["protos_revision"])
        self.assertEqual("5e8ff21f966c6c506652eef79c684d8b286bb546", cfg["baseline_evidence_revision"])

if __name__ == "__main__":
    unittest.main()
