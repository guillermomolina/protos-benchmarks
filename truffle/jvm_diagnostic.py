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

import jvm_protos_ab as ab
from workload_catalog import (
    expected_result,
    select_workloads,
    source_for,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
WORK = ROOT / ".work" / "truffle-diagnostics"
RESULTS = ROOT / "results" / "local" / "truffle-diagnostics"

COMMON_MAIN = (
    "com.guillermomolina.protos.benchmarks.truffle."
    "TruffleJvmRunner"
)
PROTOS_MAIN = (
    "com.guillermomolina.protos.benchmarks.truffle."
    "ProtosJvmVariantRunner"
)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def key(value: dict[str, object]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(raw).hexdigest()


def common_classpath() -> str:
    WORK.mkdir(parents=True, exist_ok=True)

    runner_class = (
        TRUFFLE
        / "target/classes/com/guillermomolina/protos/benchmarks"
        / "truffle/TruffleJvmRunner.class"
    )

    if not runner_class.is_file():
        subprocess.run(
            ["mvn", "-q", "-f", str(TRUFFLE / "pom.xml"), "compile"],
            cwd=ROOT,
            check=True,
        )

    cp_file = WORK / "common-classpath.txt"

    if not cp_file.is_file():
        subprocess.run(
            [
                "mvn",
                "-q",
                "-f",
                str(TRUFFLE / "pom.xml"),
                "dependency:build-classpath",
                f"-Dmdep.outputFile={cp_file}",
            ],
            cwd=ROOT,
            check=True,
        )

    return os.pathsep.join(
        [
            str(TRUFFLE / "target" / "classes"),
            cp_file.read_text(encoding="utf-8").strip(),
        ]
    )


def protos_classpath(
    item: dict[str, object],
) -> str:
    revision = str(item["revision"])

    runner_class = (
        TRUFFLE
        / "target/classes/com/guillermomolina/protos/benchmarks"
        / "truffle/ProtosJvmVariantRunner.class"
    )

    repo_class = (
        item["repo"]
        / "target/classes/com/guillermomolina/protos/execution"
        / "ProtosStandaloneHostedSession.class"
    )

    cp_file = (
        ROOT
        / ".work/protos-ab/classpath"
        / f"{revision}.txt"
    )

    if (
        not runner_class.is_file()
        or not repo_class.is_file()
        or not cp_file.is_file()
    ):
        return ab.prepare_variant(item)

    return os.pathsep.join(
        [
            str(TRUFFLE / "target" / "classes"),
            str(item["repo"] / "target" / "classes"),
            cp_file.read_text(encoding="utf-8").strip(),
        ]
    )


def command_for(
    language: str,
    workload: str,
) -> tuple[list[str], dict[str, object]]:
    cpu, siblings = ab.choose_cpu()
    source = source_for(workload, language)

    base_identity: dict[str, object] = {
        "schema": 1,
        "definition": "jvm-diagnostic-v1",
        "language": language,
        "workload": workload,
        "source_sha256": sha256_file(source),
        "java_version": ab.capture("java", "-version"),
        "cpu": cpu,
        "cpu_siblings": siblings,
    }

    if language == "protos":
        repo_arg = os.environ.get(
            "PROTOS_REPO",
            ".work/protos-ab/0.3.128",
        )

        item = ab.variant(repo_arg)
        classpath = protos_classpath(item)

        base_identity.update(
            {
                "protos_revision": item["revision"],
                "protos_version": item["version"],
                "protos_core_sha256": item["core_sha256"],
            }
        )

        command = [
            "taskset",
            "-c",
            str(cpu),
            "java",
            "-cp",
            classpath,
            PROTOS_MAIN,
            str(item["core"]),
            str(source),
            "5",
            "10",
        ]

    else:
        classpath = common_classpath()

        base_identity.update(
            {
                "pom_sha256": sha256_file(TRUFFLE / "pom.xml"),
                "runner_sha256": sha256_file(
                    TRUFFLE
                    / "src/main/java/com/guillermomolina/protos"
                    / "benchmarks/truffle/TruffleJvmRunner.java"
                ),
            }
        )

        command = [
            "taskset",
            "-c",
            str(cpu),
            "java",
            "-cp",
            classpath,
            COMMON_MAIN,
            "measure",
            language,
            str(source),
            "5",
            "10",
        ]

    return command, base_identity


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: jvm_diagnostic.py <jfr|igv> "
            "<protos|js|python> <fibonacci|factorial>"
        )

    diagnostic, language, workload = sys.argv[1:]

    if diagnostic not in {"jfr", "igv"}:
        raise SystemExit("diagnostic must be jfr or igv")

    if language not in {"protos", "js", "python"}:
        raise SystemExit("language must be protos, js or python")

    if workload == "all":
        raise SystemExit(
            "diagnostics require one selected workload"
        )

    try:
        select_workloads(workload)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    command, identity = command_for(language, workload)
    identity["diagnostic"] = diagnostic

    artifact_dir = RESULTS / diagnostic / key(identity)

    if diagnostic == "jfr":
        artifact = artifact_dir / "recording.jfr"

        if artifact.is_file() and artifact.stat().st_size > 0:
            print("diagnostic=jfr")
            print("cache=hit")
            print(f"artifact={artifact}")
            return

    else:
        existing = (
            list(artifact_dir.rglob("*.bgv"))
            if artifact_dir.is_dir()
            else []
        )

        if existing:
            print("diagnostic=igv")
            print("cache=hit")
            print(f"bgv_files={len(existing)}")
            print(f"artifact_dir={artifact_dir}")
            return

    shutil.rmtree(artifact_dir, ignore_errors=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    java_index = command.index("java") + 1

    if diagnostic == "jfr":
        recording = artifact_dir / "recording.jfr"

        options = [
            (
                "-XX:StartFlightRecording="
                f"filename={recording},"
                "settings=profile,dumponexit=true"
            )
        ]

    else:
        dump_dir = artifact_dir / "graal_dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)

        options = [
            "-Djdk.graal.Dump=Truffle:1",
            f"-Djdk.graal.DumpPath={dump_dir}",
        ]

    command[java_index:java_index] = options

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    log = artifact_dir / "run.log"
    log.write_text(result.stdout, encoding="utf-8")

    if result.returncode != 0:
        print(result.stdout, end="")
        raise RuntimeError(
            f"{diagnostic} diagnostic failed"
        )

    expected = expected_result(workload)

    observed = None
    for line in result.stdout.splitlines():
        if line.startswith("result="):
            observed = line.split("=", 1)[1]

    if observed != expected:
        raise RuntimeError(
            f"diagnostic semantic mismatch: "
            f"expected {expected}, got {observed}"
        )

    (artifact_dir / "identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if diagnostic == "jfr":
        recording = artifact_dir / "recording.jfr"

        if not recording.is_file() or recording.stat().st_size == 0:
            raise RuntimeError("JFR recording was not produced")

        print("diagnostic=jfr")
        print("cache=miss")
        print("timing_evidence=NON_PRIMARY")
        print(f"artifact={recording}")

    else:
        bgv = list(artifact_dir.rglob("*.bgv"))

        if not bgv:
            print(result.stdout, end="")
            raise RuntimeError(
                "IGV requested but no .bgv files were produced"
            )

        print("diagnostic=igv")
        print("cache=miss")
        print("timing_evidence=NON_PRIMARY")
        print(f"bgv_files={len(bgv)}")
        print(f"artifact_dir={artifact_dir}")


if __name__ == "__main__":
    main()
