# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "truffle"))

from jit_timeline import analyze_jfr, duration_ns, timestamp_ns


def window(phase, iteration, time):
    return {
        "type": "protos.benchmarks.SampleWindow",
        "values": {
            "startTime": f"2026-10-23T00:00:00.{time:09d}Z",
            "duration": "PT0.001S",
            "phase": phase,
            "iteration": iteration,
            "sampleCalls": 1 if phase == "cold" else 10,
        },
    }


def compiler(time, duration="PT0.0001S"):
    return {
        "type": "jdk.Compilation",
        "values": {
            "startTime": f"2026-10-23T00:00:00.{time:09d}Z",
            "duration": duration,
            "compileId": 42,
            "compileLevel": 4,
            "compiler": "jvmci",
            "isOsr": True,
            "succeded": True,
        },
    }


def deopt(time):
    return {
        "type": "jdk.Deoptimization",
        "values": {
            "startTime": f"2026-10-23T00:00:00.{time:09d}Z",
            "compileId": 42,
            "reason": "synthetic-reason",
            "action": "synthetic-action",
        },
    }


class JitTimelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.jfr"
        self.path.write_bytes(b"synthetic-recording")
        self.events = [
            window("cold", 1, 0),
            window("warmup", 1, 2_000_000),
            window("steady", 1, 4_000_000),
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def analyze(self, events=None):
        return analyze_jfr(
            self.path,
            {"cold": 1, "warmup": 1, "steady": 1},
            10,
            events=self.events if events is None else events,
        )

    def test_integer_nanosecond_precision(self):
        first = timestamp_ns("2026-10-23T00:00:00.000000001Z")
        next_tick = timestamp_ns(
            "2026-10-23T00:00:00.000000002Z"
        )
        self.assertEqual(next_tick - first, 1)
        self.assertEqual(duration_ns("PT0.000000001S"), 1)
        self.assertEqual(duration_ns("PT1.000000001S"), 1_000_000_001)

    def test_interval_and_point_event_boundaries(self):
        events = self.events + [
            compiler(3_999_999, "PT0.000000001S"),
            compiler(4_000_000, "PT0.0005S"),
            compiler(5_000_000),
            deopt(4_000_000),
            deopt(5_000_000),
        ]
        report = self.analyze(events)
        steady = report["windows"][-1]["events"]

        compilations = steady["jdk.Compilation"]
        self.assertEqual(compilations["before"], 1)
        self.assertEqual(compilations["overlap"], 1)
        self.assertEqual(compilations["after"], 1)
        self.assertEqual(len(compilations["overlap_ids"]), 1)

        deopts = steady["jdk.Deoptimization"]
        self.assertEqual(deopts["overlap"], 1)
        self.assertEqual(deopts["after"], 1)

        self.assertEqual(
            report["event_sample_correlation"],
            "TEMPORAL_OVERLAP_ONLY",
        )
        self.assertEqual(report["jit_maturity"], "NOT_PROVEN")
        self.assertFalse(report["reference_eligible"])

    def test_missing_and_duplicate_windows_fail(self):
        with self.assertRaisesRegex(ValueError, "windows missing"):
            self.analyze(self.events[:-1])

        with self.assertRaisesRegex(ValueError, "duplicated"):
            self.analyze(self.events + [self.events[-1]])

    def test_overlapping_windows_fail(self):
        events = list(self.events)
        events[1] = window("warmup", 1, 500_000)

        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.analyze(events)

    def test_wrong_call_count_fails(self):
        events = list(self.events)
        changed = {
            **events[-1],
            "values": {
                **events[-1]["values"],
                "sampleCalls": 11,
            },
        }
        events[-1] = changed

        with self.assertRaisesRegex(ValueError, "call count mismatch"):
            self.analyze(events)

    def test_invalid_time_and_duration_fail(self):
        with self.assertRaises(ValueError):
            timestamp_ns("2026-10-23T00:00:00.1234567890Z")

        with self.assertRaises(ValueError):
            duration_ns("PT-1S")

        events = list(self.events)
        events[0] = {
            **events[0],
            "values": {
                **events[0]["values"],
                "duration": "PT0S",
            },
        }

        with self.assertRaisesRegex(ValueError, "Nonpositive"):
            self.analyze(events)

    def test_events_outside_windows_are_retained(self):
        events = self.events + [
            compiler(1_500_000),
            deopt(6_000_000),
        ]
        report = self.analyze(events)

        self.assertEqual(report["window_count"], 3)
        self.assertEqual(
            report["event_counts"]["jdk.Compilation"], 1
        )
        self.assertEqual(
            report["event_counts"]["jdk.Deoptimization"], 1
        )
        self.assertEqual(len(report["events"]["jdk.Compilation"]), 1)
        self.assertEqual(len(report["events"]["jdk.Deoptimization"]), 1)


if __name__ == "__main__":
    unittest.main()
