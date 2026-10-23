#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Read-only JVM measurement diagnostic analyzer.

Results are diagnostic only and never certify JIT convergence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from pathlib import Path

TIMING = re.compile(
    r"^(sample|thread_cpu) phase=(cold|warmup|steady) "
    r"iteration=(\d+) elapsed_ns=(\d+)$"
)
SWITCH = re.compile(
    r"^ctx_switch phase=(cold|warmup|steady) "
    r"iteration=(\d+) voluntary=(\d+) nonvoluntary=(\d+)$"
)
GC_SAMPLE = re.compile(
    r"^gc_sample phase=(cold|warmup|steady) "
    r"iteration=(\d+) count_delta=(\d+) time_ms_delta=(\d+)$"
)
TRUFFLE = re.compile(
    r"\[engine\]\s+opt done.*?\bid=\d+\s+"
    r"(.*?)\s+\|Tier\s+(\d+)\|"
)
HOTSPOT = re.compile(r"^\s*\d+\s+\d+\s+")


def summarize(items, calls):
    wall = [item["wall_ns"] for item in items]
    cpu_complete = bool(items) and all(
        "thread_cpu_ns" in item for item in items
    )
    switches_complete = bool(items) and all(
        "voluntary" in item and "nonvoluntary" in item
        for item in items
    )

    def median(values):
        return statistics.median(values) / calls if values else None

    gc_complete = bool(items) and all(
        "gc_count_delta" in item and "gc_time_ms_delta" in item
        for item in items
    )

    result = {
        "samples": len(items),
        "wall_p50_ns_per_call": median(wall),
        "context_switches_complete": switches_complete,
        "gc_samples_complete": gc_complete,
        "gc_count_delta_total": None,
        "gc_time_ms_delta_total": None,
        "thread_cpu_complete": cpu_complete,
        "thread_cpu_p50_ns_per_call": None,
        "cpu_first5_p50_ns_per_call": None,
        "cpu_last5_p50_ns_per_call": None,
        "offcpu_positive_total_ns": None,
        "offcpu_over_1ms_samples": None,
        "voluntary_switches": None,
        "involuntary_switches": None,
    }

    if cpu_complete:
        cpu = [item["thread_cpu_ns"] for item in items]
        offcpu = [
            item["wall_ns"] - item["thread_cpu_ns"]
            for item in items
        ]
        result["thread_cpu_p50_ns_per_call"] = median(cpu)
        result["offcpu_positive_total_ns"] = sum(
            max(0, value) for value in offcpu
        )
        result["offcpu_over_1ms_samples"] = sum(
            value > 1_000_000 for value in offcpu
        )

        if len(cpu) >= 10:
            result["cpu_first5_p50_ns_per_call"] = median(cpu[:5])
            result["cpu_last5_p50_ns_per_call"] = median(cpu[-5:])

    if switches_complete:
        result["voluntary_switches"] = sum(
            item["voluntary"] for item in items
        )
        result["involuntary_switches"] = sum(
            item["nonvoluntary"] for item in items
        )

    if gc_complete:
        result["gc_count_delta_total"] = sum(
            item["gc_count_delta"] for item in items
        )
        result["gc_time_ms_delta_total"] = sum(
            item["gc_time_ms_delta"] for item in items
        )

    return result


def analyze(path: Path, expected: str):
    raw = path.read_bytes()
    lines = raw.decode("utf-8", "replace").splitlines()

    samples = {}
    declarations = {}
    observed = []
    calls = None
    truffle = []
    hotspot = []
    gc = []
    safepoints = []

    for line in lines:
        if line.startswith("sample_calls="):
            calls = int(line.split("=", 1)[1])

        for phase in ("warmup", "steady"):
            prefix = phase + "_iterations="
            if line.startswith(prefix):
                declarations[phase] = int(line.split("=", 1)[1])

        if line.startswith("result="):
            observed.append(line.split("=", 1)[1])

        match = TIMING.match(line)
        if match:
            kind, phase, number, elapsed = match.groups()
            item = samples.setdefault((phase, int(number)), {})
            field = (
                "wall_ns" if kind == "sample"
                else "thread_cpu_ns"
            )
            if field in item:
                raise ValueError(
                    f"Duplicate {field}: {phase}:{number}"
                )
            item[field] = int(elapsed)
            continue

        match = SWITCH.match(line)
        if match:
            phase, number, voluntary, involuntary = match.groups()
            item = samples.setdefault((phase, int(number)), {})
            if "voluntary" in item:
                raise ValueError(
                    f"Duplicate context switches: {phase}:{number}"
                )
            item["voluntary"] = int(voluntary)
            item["nonvoluntary"] = int(involuntary)
            continue

        match = GC_SAMPLE.match(line)
        if match:
            phase, number, count_delta, time_delta = match.groups()
            item = samples.setdefault((phase, int(number)), {})

            if "gc_count_delta" in item:
                raise ValueError(
                    f"Duplicate GC sample: {phase}:{number}"
                )

            item["gc_count_delta"] = int(count_delta)
            item["gc_time_ms_delta"] = int(time_delta)
            continue

        if line.startswith("gc_sample "):
            raise ValueError(f"Malformed GC sample: {line}")

        if "[engine]" in line and "opt done" in line:
            match = TRUFFLE.search(line)
            truffle.append({
                "root": match.group(1).strip() if match else None,
                "tier": int(match.group(2)) if match else None,
                "raw": line,
            })

        if HOTSPOT.match(line) and "::" in line:
            hotspot.append(line)

        if "[info][gc" in line:
            gc.append(line)

        if "[info][safepoint" in line:
            safepoints.append(line)

    if calls is None or calls <= 0:
        raise ValueError("Missing sample_calls")

    if observed != [expected]:
        raise ValueError(
            f"Expected result {expected!r}, got {observed!r}"
        )

    phases = {}
    phase_samples = {}

    for phase in ("cold", "warmup", "steady"):
        indices = sorted(
            number for candidate, number in samples
            if candidate == phase
        )

        if indices != list(range(1, len(indices) + 1)):
            raise ValueError(f"Noncontiguous {phase} samples")

        items = []
        for number in indices:
            item = samples[(phase, number)]
            if "wall_ns" not in item:
                raise ValueError(
                    f"Missing wall sample: {phase}:{number}"
                )
            items.append({"iteration": number, **item})

        if phase in declarations:
            if len(items) != declarations[phase]:
                raise ValueError(
                    f"Incomplete {phase}: "
                    f"expected {declarations[phase]}, got {len(items)}"
                )

        phase_samples[phase] = items
        phases[phase] = summarize(items, calls)

    if not phase_samples["steady"]:
        raise ValueError("No steady samples")

    metadata_path = path.parent.parent / "metadata.json"
    metadata = None
    metadata_hash = None
    prior_gate = False

    if metadata_path.is_file():
        metadata_raw = metadata_path.read_bytes()
        metadata = json.loads(metadata_raw)
        metadata_hash = hashlib.sha256(metadata_raw).hexdigest()

        if str(metadata.get("expected_result")) != expected:
            raise ValueError("Metadata expected result mismatch")

        prior_gate = (
            metadata.get("correctness", {}).get("result") == "PASS"
        )
        if not prior_gate:
            raise ValueError("Prior correctness gate not PASS")

    roots = {}
    for event in truffle:
        if event["root"] is not None:
            roots.setdefault(event["root"], set()).add(
                event["tier"]
            )

    return {
        "schema": 1,
        "classification": "DIAGNOSTIC_ONLY",
        "reference_eligible": False,
        "jit_maturity": "NOT_PROVEN",
        "event_sample_correlation": "NOT_ESTABLISHED",
        "source": {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        },
        "identity": {
            "metadata_sha256": metadata_hash,
            "harness_git_head": (
                metadata.get("harness_git_head")
                if metadata else None
            ),
            "language": (
                metadata.get("language") if metadata else None
            ),
            "workload": (
                metadata.get("workload") if metadata else None
            ),
        },
        "correctness": {
            "expected": expected,
            "observed": observed[0],
            "result_matches_expected": True,
            "prior_gate_verified": prior_gate,
        },
        "sample_calls": calls,
        "phases": phases,
        "samples": phase_samples,
        "compilation": {
            "truffle_completed": truffle,
            "truffle_roots_and_tiers": {
                root: sorted(tiers)
                for root, tiers in sorted(roots.items())
            },
            "hotspot_events": hotspot,
            "hotspot_osr_events": [
                line for line in hotspot
                if re.match(r"^\s*\d+\s+\d+\s+%", line)
            ],
        },
        "runtime_events": {
            "gc": gc,
            "safepoints": safepoints,
        },
        "limitations": [
            "Tier 2 completion does not prove JIT convergence.",
            "Stable timing does not prove equivalent optimized code.",
            "Mixed output order does not prove event/sample timing.",
            "Wall minus thread CPU is not scheduler-only time.",
            "Standalone logs may lack prior correctness metadata.",
            "GC deltas are observations around each sample, "
            "not proof that GC occurred inside its wall interval.",
            "Diagnostic wall timing includes Thread CPU clock reads.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, action="append", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        parser.error("Refusing to overwrite existing report")

    reports = [
        analyze(path, args.expected)
        for path in args.log
    ]

    payload = {
        "schema": 1,
        "classification": "DIAGNOSTIC_ONLY",
        "runs": reports,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )

    for report in reports:
        steady = report["phases"]["steady"]
        print("LOG=", report["source"]["path"])
        print(
            "WALL_P50_NS_PER_CALL=",
            steady["wall_p50_ns_per_call"]
        )
        print(
            "CPU_P50_NS_PER_CALL=",
            steady["thread_cpu_p50_ns_per_call"]
        )
        print(
            "OFFCPU_TOTAL_MS=",
            (
                steady["offcpu_positive_total_ns"] / 1e6
                if steady["offcpu_positive_total_ns"] is not None
                else "NOT_AVAILABLE"
            )
        )
        print(
            "TRUFFLE_ROOTS=",
            report["compilation"]["truffle_roots_and_tiers"]
        )
        print("JIT_MATURITY=NOT_PROVEN")

    print("REPORT=", args.output)


if __name__ == "__main__":
    main()
