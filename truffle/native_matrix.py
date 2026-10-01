#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

from workload_catalog import (
    cases_for_selection,
    expected_result,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
WORK = ROOT / ".work" / "truffle-native"
GENERATED = WORK / "generated"
MANIFEST = WORK / "runtime-manifest.json"
CACHE = ROOT / "results" / "local" / "truffle-cache"

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_cpu_list(text: str) -> set[int]:
    result: set[int] = set()

    for part in text.strip().split(","):
        if "-" in part:
            first, last = map(int, part.split("-", 1))
            result.update(range(first, last + 1))
        elif part:
            result.add(int(part))

    return result


def choose_cpu() -> tuple[int, list[int]]:
    allowed = set(os.sched_getaffinity(0))
    requested = os.environ.get("CPU")
    cpu = int(requested) if requested is not None else min(allowed)

    if cpu not in allowed:
        raise RuntimeError(
            f"CPU={cpu} outside allowed affinity {sorted(allowed)}"
        )

    sibling_file = Path(
        f"/sys/devices/system/cpu/cpu{cpu}/topology/"
        "thread_siblings_list"
    )

    siblings = (
        sorted(parse_cpu_list(sibling_file.read_text()))
        if sibling_file.is_file()
        else [cpu]
    )

    return cpu, siblings


def cpu_model() -> str:
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()

    return "unknown"


def load_manifest() -> dict[str, object]:
    if not MANIFEST.is_file():
        raise RuntimeError(
            "native setup missing; run make truffle-native-setup"
        )

    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def generated_source(
    language: str,
    workload: str,
    source: Path,
    calls: int,
) -> Path:
    text = source.read_text(encoding="utf-8").rstrip() + "\n\n"

    if language == "protos":
        lines = [
            "run()"
            for _ in range(calls - 1)
        ]
        lines.append("print(run())")
        text += "\n".join(lines) + "\n"
        suffix = ".protos"

    elif language == "js":
        lines = [
            "globalThis.truffleRun();"
            for _ in range(calls - 1)
        ]
        lines.append(
            "console.log(globalThis.truffleRun().toString());"
        )
        text += "\n".join(lines) + "\n"
        suffix = ".mjs"

    elif language == "python":
        lines = [
            "truffleRun()"
            for _ in range(calls - 1)
        ]
        lines.append("print(truffleRun())")
        text += "\n".join(lines) + "\n"
        suffix = ".py"

    else:
        raise ValueError(language)

    GENERATED.mkdir(parents=True, exist_ok=True)
    output = GENERATED / f"{language}-{workload}-{calls}{suffix}"
    output.write_text(text, encoding="utf-8")
    return output


def execute(
    language: str,
    workload: str,
    runtime: dict[str, object],
    source: Path,
    calls: int,
    cpu: int,
) -> int:
    generated = generated_source(
        language,
        workload,
        source,
        calls,
    )

    command = [
        "taskset",
        "-c",
        str(cpu),
        str(runtime["path"]),
        str(generated),
    ]

    started = time.perf_counter_ns()

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    elapsed = time.perf_counter_ns() - started

    if result.returncode != 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(
            f"native execution failed: {language}/{workload}"
        )

    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    expected = expected_result(workload)
    if not lines or lines[-1] != expected:
        raise RuntimeError(
            f"{language}/{workload}: expected {expected}, "
            f"got {lines!r}"
        )

    return elapsed


def identity(
    language: str,
    workload: str,
    source: Path,
    runtime: dict[str, object],
    cpu: int,
    siblings: list[int],
    calls: int,
    batches: int,
) -> dict[str, object]:
    return {
        "schema": 1,
        "measurement_definition": "native-process-v2",
        "mode": "native",
        "language": language,
        "workload": workload,
        "source_sha256": sha256_file(source),
        "runtime_version": runtime["reported_version"],
        "runtime_binary_sha256": runtime["binary_sha256"],
        "runtime_archive_sha256": runtime["archive_sha256"],
        "cpu": cpu,
        "cpu_siblings": siblings,
        "cpu_model": cpu_model(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "sustained_calls": calls,
        "sustained_batches": batches,
    }


def cache_key(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(encoded).hexdigest()


def show(
    cached: bool,
    observation: dict[str, object],
) -> None:
    cold = int(observation["cold_process_ns"])
    calls = int(observation["sustained_calls"])
    batches = [
        int(value)
        for value in observation["sustained_batch_ns"]
    ]

    amortized = [value / calls for value in batches]

    print(f"cache={'hit' if cached else 'miss'}")
    print(f"cold_process_ms={cold / 1_000_000:.3f}")
    print(f"sustained_calls_per_batch={calls}")
    print(
        "sustained_amortized_p50_ms="
        f"{statistics.median(amortized) / 1_000_000:.3f}"
    )
    print(
        "sustained_amortized_min_ms="
        f"{min(amortized) / 1_000_000:.3f}"
    )
    print(
        "sustained_amortized_max_ms="
        f"{max(amortized) / 1_000_000:.3f}"
    )
    print(f"result={observation['result']}")


def run_case(
    language: str,
    workload: str,
    source: Path,
    manifest: dict[str, object],
    cpu: int,
    siblings: list[int],
    calls: int,
    batches: int,
) -> None:
    runtime = manifest[language]

    ident = identity(
        language,
        workload,
        source,
        runtime,
        cpu,
        siblings,
        calls,
        batches,
    )

    cache_file = CACHE / f"{cache_key(ident)}.json"

    print()
    print(f"=== {language} {workload} ===")
    print(f"runtime={runtime['reported_version']}")
    print(f"cpu={cpu}")
    print(
        "cpu_siblings="
        + ",".join(str(value) for value in siblings)
    )

    if cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        show(True, cached["observation"])
        return

    cold = execute(
        language,
        workload,
        runtime,
        source,
        1,
        cpu,
    )

    sustained = [
        execute(
            language,
            workload,
            runtime,
            source,
            calls,
            cpu,
        )
        for _ in range(batches)
    ]

    observation = {
        "cold_process_ns": cold,
        "sustained_calls": calls,
        "sustained_batch_ns": sustained,
        "result": expected_result(workload),
    }

    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "identity": ident,
                "observation": observation,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    show(False, observation)


def main() -> None:
    if (
        len(sys.argv) not in {2, 3}
        or sys.argv[1] not in {"smoke", "benchmark"}
    ):
        raise SystemExit(
            "usage: native_matrix.py "
            "<smoke|benchmark> [all|<workload>]"
        )

    profile = sys.argv[1]
    selected = sys.argv[2] if len(sys.argv) == 3 else "all"

    try:
        cases = cases_for_selection(selected)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if profile == "smoke":
        calls, batches = 2, 1
    else:
        calls, batches = 5, 3

    manifest = load_manifest()
    cpu, siblings = choose_cpu()

    print("mode=native-matrix")
    print(f"profile={profile}")
    print(f"cpu={cpu}")
    print(
        "cpu_siblings="
        + ",".join(str(value) for value in siblings)
    )

    for language, workload, source in cases:
        run_case(
            language,
            workload,
            source,
            manifest,
            cpu,
            siblings,
            calls,
            batches,
        )


if __name__ == "__main__":
    main()
