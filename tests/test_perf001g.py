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
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Perf001GConfigTest(unittest.TestCase):
    def test_owner_approved_bounded_replay_policy_is_pinned(self) -> None:
        cfg = json.loads((ROOT / "config/perf001g.json").read_text(encoding="utf-8"))
        self.assertEqual("PERF001-G", cfg["slice"])
        self.assertEqual("bounded_exact_pin_reproducibility_replay", cfg["methodology"])
        self.assertEqual("project-owner-approved-2026-09-10", cfg["methodology_approval"])
        self.assertFalse(cfg["timing_values_are_pass_fail_threshold"])
        self.assertFalse(cfg["report_policy"]["cross_generation_normalization"])
        self.assertFalse(cfg["report_policy"]["cross_generation_performance_ranking"])
        self.assertFalse(cfg["report_policy"]["replay_timings_retained"])

    def test_exact_historical_harnesses_are_immutable(self) -> None:
        cfg = json.loads((ROOT / "config/perf001g.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "perf001d": "0a406373c497df1173ff26a3ed4fcada015e0879",
                "perf001e": "280173d743b2ed838a89be0ad930b20828d89558",
                "perf001f_h3": "b8a9eeca85c241f544512a02a6fa29d935f240ef",
                "perf001f_h4_evidence": "f34e37da11f209aa9f9ea84465822c3362fc4da0",
            },
            cfg["historical_harnesses"],
        )

    def test_replay_counts_preserve_approved_scope(self) -> None:
        cfg = json.loads((ROOT / "config/perf001g.json").read_text(encoding="utf-8"))
        replay = cfg["expected_replay"]
        self.assertEqual(44, replay["perf001d_correctness_cases"])
        self.assertEqual(18, replay["perf001e_correctness_cases"])
        self.assertEqual(12, replay["perf001f_reference_smoke_configurations"])
        self.assertEqual((2, 2, 2), (
            replay["perf001f_startup_samples_per_configuration"],
            replay["perf001f_warmup_iterations_per_configuration"],
            replay["perf001f_steady_samples_per_configuration"],
        ))

    def test_controller_has_no_timing_acceptance_threshold(self) -> None:
        text = (ROOT / "runner/perf001g.py").read_text(encoding="utf-8")
        self.assertIn("timing_values_are_pass_fail_threshold", text)
        self.assertIn("replacement_timing_samples_retained", text)
        self.assertNotIn("timing_tolerance", text)
        self.assertNotIn("regression_threshold", text)
        self.assertIn("git\", \"worktree\", \"add\", \"--detach", text)
        self.assertIn("perf001f_reference.py\", \"--smoke", text)


if __name__ == "__main__":
    unittest.main()
