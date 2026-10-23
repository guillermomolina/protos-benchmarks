# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "truffle"))

from measure_diagnostics import analyze


class MeasurementDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.log = Path(self.directory.name) / "run.log"

    def tearDown(self):
        self.directory.cleanup()

    def sample_log(self):
        lines = [
            "sample_calls=10000",
            "warmup_iterations=10",
            "steady_iterations=10",
            "sample phase=cold iteration=1 elapsed_ns=100",
        ]

        for i in range(1, 11):
            lines.append(
                f"sample phase=warmup iteration={i} "
                "elapsed_ns=540000"
            )

        for i in range(1, 11):
            wall = 2160000 if i == 10 else 540000
            lines.extend([
                f"sample phase=steady iteration={i} elapsed_ns={wall}",
                f"thread_cpu phase=steady iteration={i} "
                "elapsed_ns=540000",
                f"ctx_switch phase=steady iteration={i} "
                f"voluntary=0 nonvoluntary={int(i == 10)}",
            ])

        lines.extend([
            "[engine] opt done engine=1 id=259 "
            "run |Tier 2|Time 3ms",
            "2239 2626 % 4 "
            "example.MeasurementEngine::invokeRepeated @ 2",
            "result=1",
        ])
        return "\n".join(lines) + "\n"

    def write(self, content):
        self.log.write_text(content)

    def test_offcpu_and_compilation_not_mistaken_for_maturity(self):
        self.write(self.sample_log())
        report = analyze(self.log, "1")
        steady = report["phases"]["steady"]

        self.assertEqual(steady["samples"], 10)
        self.assertEqual(steady["wall_p50_ns_per_call"], 54)
        self.assertEqual(steady["thread_cpu_p50_ns_per_call"], 54)
        self.assertEqual(steady["offcpu_over_1ms_samples"], 1)
        self.assertEqual(steady["involuntary_switches"], 1)
        self.assertEqual(report["jit_maturity"], "NOT_PROVEN")
        self.assertEqual(
            report["compilation"]["truffle_roots_and_tiers"],
            {"run": [2]},
        )
        self.assertEqual(
            len(report["compilation"]["hotspot_osr_events"]), 1
        )
        self.assertFalse(report["reference_eligible"])
        self.assertFalse(
            report["correctness"]["prior_gate_verified"]
        )

    def test_wrong_result_rejected(self):
        self.write(
            self.sample_log().replace("result=1", "result=2")
        )
        with self.assertRaises(ValueError):
            analyze(self.log, "1")

    def test_missing_wall_sample_rejected(self):
        self.write(
            self.sample_log().replace(
                "sample phase=steady iteration=10 "
                "elapsed_ns=2160000\n",
                "",
            )
        )
        with self.assertRaises(ValueError):
            analyze(self.log, "1")

    def test_duplicate_sample_rejected(self):
        self.write(
            self.sample_log().replace(
                "result=1",
                "sample phase=steady iteration=1 "
                "elapsed_ns=540000\nresult=1",
            )
        )
        with self.assertRaises(ValueError):
            analyze(self.log, "1")


if __name__ == "__main__":
    unittest.main()
