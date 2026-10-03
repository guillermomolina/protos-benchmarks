#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import jvm_matrix as matrix
import jvm_runtime
from workload_catalog import (
    expected_result,
    jvm_sample_calls,
    select_workloads,
    source_for,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
RESULTS = (
    ROOT
    / "results"
    / "local"
    / "truffle-diagnostics"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def key(value: dict[str, object]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(raw).hexdigest()


def env_int(
    name: str,
    default: int,
    allow_zero: bool = False,
) -> int:
    value = int(
        os.environ.get(
            name,
            str(default),
        )
    )

    minimum = 0 if allow_zero else 1

    if value < minimum:
        relation = ">= 0" if allow_zero else "> 0"

        raise RuntimeError(
            f"{name} must be {relation}"
        )

    return value


IGV_MIN_SAMPLE_CALLS = 10_000


def diagnostic_sample_calls(
    diagnostic: str,
    workload: str,
) -> tuple[int, str]:
    explicit = os.environ.get(
        "DIAGNOSTIC_SAMPLE_CALLS"
    )

    if explicit is not None:
        return (
            env_int(
                "DIAGNOSTIC_SAMPLE_CALLS",
                1,
            ),
            "explicit",
        )

    catalog_calls = jvm_sample_calls(
        workload
    )

    if diagnostic == "igv":
        return (
            max(
                catalog_calls,
                IGV_MIN_SAMPLE_CALLS,
            ),
            "igv-compilation-floor",
        )

    return (
        catalog_calls,
        "catalog",
    )


def command_for(
    diagnostic: str,
    language: str,
    workload: str,
) -> tuple[
    list[str],
    dict[str, object],
]:
    cpu, siblings = matrix.choose_cpu()

    source = source_for(
        workload,
        language,
    )

    warmup = env_int(
        "DIAGNOSTIC_WARMUP",
        5,
        allow_zero=True,
    )

    steady = env_int(
        "DIAGNOSTIC_STEADY",
        10,
    )

    (
        sample_calls,
        sample_calls_policy,
    ) = diagnostic_sample_calls(
        diagnostic,
        workload,
    )

    identity: dict[str, object] = {
        "schema": 3,
        "definition": "jvm-diagnostic-v3",
        "mode": "jvm",
        "language": language,
        "workload": workload,
        "source_sha256":
            sha256_file(source),
        "harness_revision":
            matrix.benchmark_revision(),
        "harness_dirty":
            matrix.benchmark_dirty(),
        "diagnostic_sha256":
            sha256_file(Path(__file__)),
        "runtime_sha256":
            sha256_file(
                TRUFFLE
                / "jvm_runtime.py"
            ),
        "catalog_sha256":
            sha256_file(
                TRUFFLE
                / "workloads"
                / "catalog.json"
            ),
        "java_version":
            matrix.command_version(
                "java",
                "-version",
            ),
        "cpu": cpu,
        "cpu_siblings": siblings,
        "warmup_iterations": warmup,
        "steady_iterations": steady,
        "sample_calls": sample_calls,
        "sample_calls_policy":
            sample_calls_policy,
        "diagnostic_scope":
            "whole-process-non-primary",
    }

    if language == "protos":
        runtime = (
            jvm_runtime.protos_runtime()
        )

        identity["run_mode"] = (
            runtime["run_mode"]
        )

        identity["protos"] = (
            jvm_runtime.protos_identity(
                runtime
            )
        )

        command = (
            jvm_runtime.protos_measure_command(
                runtime,
                source,
                warmup,
                steady,
                sample_calls,
                cpu,
            )
        )
    else:
        runtime = (
            jvm_runtime.peer_runtime()
        )

        identity["run_mode"] = "prepared"

        identity["peer_runtime"] = (
            jvm_runtime.peer_identity(
                runtime
            )
        )

        command = (
            jvm_runtime.peer_measure_command(
                runtime,
                language,
                source,
                warmup,
                steady,
                sample_calls,
                cpu,
            )
        )

    return command, identity


def show_identity(
    identity: dict[str, object],
) -> None:
    print(
        "language="
        + str(identity["language"])
    )

    print(
        "run_mode="
        + str(identity["run_mode"])
    )

    if identity["language"] == "protos":
        protos = identity["protos"]

        assert isinstance(
            protos,
            dict,
        )

        print(
            "protos_revision="
            + str(protos["revision"])
        )

        print(
            "protos_version="
            + str(protos["version"])
        )


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: jvm_diagnostic.py "
            "<jfr|igv> "
            "<protos|js|python> "
            "<workload>"
        )

    diagnostic, language, workload = (
        sys.argv[1:]
    )

    if diagnostic not in {
        "jfr",
        "igv",
    }:
        raise SystemExit(
            "diagnostic must be jfr or igv"
        )

    if language not in {
        "protos",
        "js",
        "python",
    }:
        raise SystemExit(
            "language must be "
            "protos, js or python"
        )

    if workload == "all":
        raise SystemExit(
            "diagnostics require "
            "one selected workload"
        )

    try:
        select_workloads(workload)
    except ValueError as exc:
        raise SystemExit(
            str(exc)
        ) from exc

    command, identity = command_for(
        diagnostic,
        language,
        workload,
    )

    identity["diagnostic"] = diagnostic

    artifact_dir = (
        RESULTS
        / diagnostic
        / key(identity)
    )

    if diagnostic == "jfr":
        artifact = (
            artifact_dir
            / "recording.jfr"
        )

        if (
            artifact.is_file()
            and artifact.stat().st_size > 0
        ):
            print("diagnostic=jfr")
            print("cache=hit")
            show_identity(identity)
            print(f"artifact={artifact}")
            return
    else:
        existing = (
            list(
                artifact_dir.rglob("*.bgv")
            )
            if artifact_dir.is_dir()
            else []
        )

        if existing:
            print("diagnostic=igv")
            print("cache=hit")
            show_identity(identity)
            print(
                f"bgv_files={len(existing)}"
            )
            print(
                f"artifact_dir={artifact_dir}"
            )
            return

    shutil.rmtree(
        artifact_dir,
        ignore_errors=True,
    )

    artifact_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    java_index = (
        command.index("java")
        + 1
    )

    if diagnostic == "jfr":
        recording = (
            artifact_dir
            / "recording.jfr"
        )

        options = [
            (
                "-XX:StartFlightRecording="
                f"filename={recording},"
                "settings=profile,"
                "dumponexit=true"
            )
        ]
    else:
        dump_dir = (
            artifact_dir
            / "graal_dumps"
        )

        dump_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        options = [
            "-Djdk.graal.Dump=Truffle:1",
            (
                "-Djdk.graal.DumpPath="
                + str(dump_dir)
            ),
        ]

    command[
        java_index:java_index
    ] = options

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    log = artifact_dir / "run.log"

    log.write_text(
        result.stdout,
        encoding="utf-8",
    )

    if result.returncode != 0:
        print(
            result.stdout,
            end="",
        )

        raise RuntimeError(
            f"{diagnostic} "
            "diagnostic failed"
        )

    expected = expected_result(
        workload
    )

    observed = None

    for line in result.stdout.splitlines():
        if line.startswith("result="):
            observed = line.split(
                "=",
                1,
            )[1]

    if observed != expected:
        raise RuntimeError(
            "diagnostic semantic mismatch: "
            f"expected {expected}, "
            f"got {observed}"
        )

    identity_path = (
        artifact_dir
        / "identity.json"
    )

    identity_path.write_text(
        json.dumps(
            identity,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"diagnostic={diagnostic}"
    )
    print("cache=miss")
    print(
        "timing_evidence=NON_PRIMARY"
    )

    show_identity(identity)

    print(
        "correctness=PASS "
        f"result={observed}"
    )

    print(
        f"identity={identity_path}"
    )

    if diagnostic == "jfr":
        recording = (
            artifact_dir
            / "recording.jfr"
        )

        if (
            not recording.is_file()
            or recording.stat().st_size == 0
        ):
            raise RuntimeError(
                "JFR recording "
                "was not produced"
            )

        print(
            f"artifact={recording}"
        )
    else:
        bgv = list(
            artifact_dir.rglob(
                "*.bgv"
            )
        )

        if not bgv:
            print(
                result.stdout,
                end="",
            )

            raise RuntimeError(
                "IGV requested but "
                "no .bgv files were produced"
            )

        print(
            f"bgv_files={len(bgv)}"
        )

        print(
            f"artifact_dir={artifact_dir}"
        )


if __name__ == "__main__":
    main()
