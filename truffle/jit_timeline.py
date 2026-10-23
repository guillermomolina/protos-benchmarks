#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Correlate JVM JFR events with benchmark sample windows.

Temporal overlap is evidence of concurrent timing, not causality.
All timestamps and durations use integer nanoseconds.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

EVENT_TYPES = (
    "protos.benchmarks.SampleWindow",
    "jdk.Compilation",
    "jdk.Deoptimization",
    "jdk.GarbageCollection",
)

TIMESTAMP = re.compile(
    r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)"
    r"(?:\.(\d{1,9}))?Z$"
)
DURATION = re.compile(
    r"^PT(?:(\d+)H)?(?:(\d+)M)?"
    r"(?:(\d+)(?:\.(\d{1,9}))?S)?$"
)


def timestamp_ns(value: str) -> int:
    match = TIMESTAMP.fullmatch(value)
    if not match:
        raise ValueError(f"Unsupported JFR timestamp: {value!r}")

    whole = datetime.strptime(
        match.group(1), "%Y-%m-%dT%H:%M:%S"
    ).replace(tzinfo=timezone.utc)

    seconds = calendar.timegm(whole.utctimetuple())
    fraction = (match.group(2) or "").ljust(9, "0")
    return seconds * 1_000_000_000 + int(fraction or "0")


def duration_ns(value: str) -> int:
    match = DURATION.fullmatch(value)
    if not match or not any(
        match.group(i) is not None for i in (1, 2, 3)
    ):
        raise ValueError(f"Unsupported JFR duration: {value!r}")

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    fraction = (match.group(4) or "").ljust(9, "0")

    return (
        (hours * 3600 + minutes * 60 + seconds) * 1_000_000_000
        + int(fraction or "0")
    )


def read_events(path: Path) -> list[dict]:
    result = subprocess.run(
        [
            "jfr", "print", "--json",
            "--events", ",".join(EVENT_TYPES),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode:
        raise ValueError(
            "JFR extraction failed: " + result.stderr[-2000:]
        )

    try:
        events = json.loads(result.stdout)["recording"]["events"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Invalid JFR JSON") from exc

    if not isinstance(events, list):
        raise ValueError("JFR events must be an array")

    return events


def method_name(value: dict) -> str | None:
    method = value.get("method")
    if not isinstance(method, dict):
        return None

    owner = method.get("type") or {}
    owner_name = owner.get("name") if isinstance(owner, dict) else None
    name = method.get("name")

    if not name:
        return None

    return (
        owner_name.replace("/", ".") + "::" + name
        if isinstance(owner_name, str)
        else name
    )


def relation(event: dict, window: dict) -> str:
    start = event["start_epoch_ns"]
    end = event["end_epoch_ns"]
    left = window["start_epoch_ns"]
    right = window["end_epoch_ns"]

    # Deoptimizations are point events. Intervals are half-open.
    if start == end:
        if start < left:
            return "before"
        if start >= right:
            return "after"
        return "overlap"

    if end <= left:
        return "before"
    if start >= right:
        return "after"

    return "overlap"


def analyze_jfr(
    path: Path,
    expected_counts: dict[str, int],
    sample_calls: int,
    *,
    events: list[dict] | None = None,
) -> dict:
    if sample_calls <= 0:
        raise ValueError("Invalid sample_calls")

    if events is None:
        events = read_events(path)

    windows = []
    extracted = {
        "jdk.Compilation": [],
        "jdk.Deoptimization": [],
        "jdk.GarbageCollection": [],
    }

    for event in events:
        kind = event.get("type")
        values = event.get("values")

        if kind not in EVENT_TYPES:
            continue
        if not isinstance(values, dict):
            raise ValueError(f"Malformed JFR event: {kind}")

        start_text = values["startTime"]
        start = timestamp_ns(start_text)

        if kind == "protos.benchmarks.SampleWindow":
            duration = duration_ns(values["duration"])
            if duration <= 0:
                raise ValueError("Nonpositive sample duration")

            phase = values["phase"]
            iteration = values["iteration"]
            calls = values["sampleCalls"]

            if (
                type(iteration) is not int
                or type(calls) is not int
            ):
                raise ValueError("Invalid JFR sample fields")

            windows.append({
                "phase": phase,
                "iteration": iteration,
                "sample_calls": calls,
                "start_time_utc": start_text,
                "start_epoch_ns": start,
                "duration_ns": duration,
                "end_epoch_ns": start + duration,
            })
            continue

        if kind == "jdk.Deoptimization":
            duration = 0
        else:
            duration = duration_ns(values.get("duration", "PT0S"))

        thread = values.get("eventThread") or {}
        thread_name = (
            thread.get("javaName") if isinstance(thread, dict)
            else None
        )

        record = {
            "start_time_utc": start_text,
            "start_epoch_ns": start,
            "duration_ns": duration,
            "end_epoch_ns": start + duration,
            "method": method_name(values),
            "thread": thread_name,
        }

        if kind == "jdk.Compilation":
            record.update({
                "compile_id": values.get("compileId"),
                "compiler": values.get("compiler"),
                "level": values.get("compileLevel"),
                "osr": values.get("isOsr"),
                "succeeded": values.get("succeded"),
            })
        elif kind == "jdk.Deoptimization":
            record.update({
                "compile_id": values.get("compileId"),
                "reason": values.get("reason"),
                "action": values.get("action"),
                "bci": values.get("bci"),
            })

        extracted[kind].append(record)

    expected_order = [
        (phase, i)
        for phase in ("cold", "warmup", "steady")
        for i in range(1, expected_counts[phase] + 1)
    ]

    windows.sort(key=lambda w: w["start_epoch_ns"])

    actual_order = [
        (w["phase"], w["iteration"]) for w in windows
    ]

    if actual_order != expected_order:
        raise ValueError(
            "JFR windows missing, duplicated or out of order: "
            f"expected {expected_order}, got {actual_order}"
        )

    for index, window in enumerate(windows):
        expected_calls = (
            1 if window["phase"] == "cold" else sample_calls
        )

        if window["sample_calls"] != expected_calls:
            raise ValueError(
                f"JFR sample call count mismatch: "
                f"{window['phase']}:{window['iteration']}"
            )

        if index and windows[index - 1]["end_epoch_ns"] > (
            window["start_epoch_ns"]
        ):
            raise ValueError("Overlapping JFR sample windows")

    for kind, records in extracted.items():
        records.sort(key=lambda r: r["start_epoch_ns"])
        prefix = {
            "jdk.Compilation": "compilation",
            "jdk.Deoptimization": "deoptimization",
            "jdk.GarbageCollection": "gc",
        }[kind]

        for i, record in enumerate(records, 1):
            record["id"] = f"{prefix}-{i}"

    for window in windows:
        window["events"] = {}

        for kind, records in extracted.items():
            grouped = {
                "before": 0,
                "overlap": 0,
                "after": 0,
                "overlap_ids": [],
            }

            for record in records:
                position = relation(record, window)
                grouped[position] += 1

                if position == "overlap":
                    grouped["overlap_ids"].append(record["id"])

            window["events"][kind] = grouped

    return {
        "schema": 1,
        "classification": "DIAGNOSTIC_ONLY",
        "reference_eligible": False,
        "jit_maturity": "NOT_PROVEN",
        "event_sample_correlation": "TEMPORAL_OVERLAP_ONLY",
        "source": {
            "file": "raw/jit-timeline.jfr",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "window_count": len(windows),
        "event_counts": {
            kind: len(records)
            for kind, records in extracted.items()
        },
        "windows": windows,
        "events": extracted,
        "limitations": [
            "Temporal overlap does not prove causality.",
            "A compilation may run on another JVM thread.",
            "A deoptimization may concern unrelated code.",
            "Truffle textual compilation events are not aligned.",
            "JIT maturity and optimized code equivalence are unproven.",
        ],
    }
