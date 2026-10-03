#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import jvm_runtime
from workload_catalog import (
    cases_for_selection,
    expected_result,
)


def run_case(
    language: str,
    workload: str,
    source: Path,
) -> None:
    if language == "protos":
        runtime = jvm_runtime.protos_runtime()

        command = jvm_runtime.protos_measure_command(
            runtime,
            source,
            0,
            1,
            1,
            None,
        )
    else:
        runtime = jvm_runtime.peer_runtime()

        command = jvm_runtime.peer_correctness_command(
            runtime,
            language,
            source,
        )

    result = subprocess.run(
        command,
        cwd=jvm_runtime.ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.returncode != 0:
        print(result.stdout, end="")

        raise RuntimeError(
            f"correctness failed for "
            f"{language}/{workload}"
        )

    if language == "protos":
        values = [
            line.split("=", 1)[1]
            for line in result.stdout.splitlines()
            if line.startswith("result=")
        ]
    else:
        values = [
            line.strip()
            for line in result.stdout.splitlines()
            if re.fullmatch(
                r"-?\d+",
                line.strip(),
            )
        ]

    expected = expected_result(workload)
    actual = values[-1] if values else None

    if actual != expected:
        print(result.stdout, end="")

        raise RuntimeError(
            f"{language}/{workload}: expected "
            f"{expected}, got {actual!r}"
        )

    if language == "protos":
        print(
            f"{language}/{workload}=PASS "
            f"result={actual} "
            f"revision={runtime['revision']} "
            f"version={runtime['version']} "
            f"run_mode={runtime['run_mode']}"
        )
    else:
        print(
            f"{language}/{workload}=PASS "
            f"result={actual} "
            f"run_mode=prepared"
        )


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit(
            "usage: jvm_correctness.py "
            "[all|<workload>]"
        )

    selected = (
        sys.argv[1]
        if len(sys.argv) == 2
        else "all"
    )

    try:
        cases = cases_for_selection(
            selected
        )
    except ValueError as exc:
        raise SystemExit(
            str(exc)
        ) from exc

    for case in cases:
        run_case(*case)


if __name__ == "__main__":
    main()
