#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from workload_catalog import (
    expected_result,
    protos_workloads_for_selection,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
CACHE = ROOT / "results" / "local" / "truffle-cache"
WORK = ROOT / ".work" / "protos-ab"

MAIN_CLASS = (
    "com.guillermomolina.protos.benchmarks.truffle."
    "ProtosJvmVariantRunner"
)

def capture(*command: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()

    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(item.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")

    return digest.hexdigest()


def parse_cpu_list(value: str) -> set[int]:
    result: set[int] = set()

    for part in value.strip().split(","):
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


def pom_properties(repo: Path) -> tuple[str, str]:
    root = ET.parse(repo / "pom.xml").getroot()
    ns = ""

    if root.tag.startswith("{"):
        ns = root.tag.split("}", 1)[0] + "}"

    version = root.findtext(f"{ns}version", "").strip()

    properties = root.find(f"{ns}properties")
    graal = ""

    if properties is not None:
        graal = properties.findtext(
            f"{ns}graalvm.version",
            "",
        ).strip()

    if not version:
        raise RuntimeError(f"cannot resolve project version in {repo}")

    return version, graal


def variant(repo_argument: str) -> dict[str, object]:
    repo = Path(repo_argument)

    if not repo.is_absolute():
        repo = (ROOT / repo).resolve()

    if not (repo / ".git").exists():
        raise RuntimeError(f"not a git checkout: {repo}")

    dirty = capture(
        "git",
        "status",
        "--porcelain",
        "--untracked-files=no",
        cwd=repo,
    )

    if dirty:
        raise RuntimeError(
            f"A/B checkout has tracked modifications: {repo}\n{dirty}"
        )

    revision = capture("git", "rev-parse", "HEAD", cwd=repo)
    version, graal = pom_properties(repo)
    core = repo / "protos" / "lib" / "core"

    return {
        "repo": repo,
        "revision": revision,
        "version": version,
        "graalvm_version": graal,
        "core": core,
        "core_sha256": sha256_tree(core),
    }


def identity(
    item: dict[str, object],
    workload: str,
    source: Path,
    cpu: int,
    siblings: list[int],
    warmup: int,
    steady: int,
) -> dict[str, object]:
    return {
        "schema": 1,
        "measurement_definition": "jvm-protos-session-ab-v1",
        "mode": "jvm",
        "language": "protos",
        "workload": workload,
        "source_sha256": sha256_file(source),
        "protos_version": item["version"],
        "protos_revision": item["revision"],
        "protos_core_sha256": item["core_sha256"],
        "graalvm_version": item["graalvm_version"],
        "java_version": capture("java", "-version"),
        "cpu": cpu,
        "cpu_siblings": siblings,
        "cpu_model": cpu_model(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "warmup_iterations": warmup,
        "steady_iterations": steady,
    }


def cache_key(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(encoded).hexdigest()


def prepare_variant(item: dict[str, object]) -> str:
    repo = item["repo"]
    revision = str(item["revision"])

    runner_class = (
        TRUFFLE
        / "target/classes/com/guillermomolina/protos/benchmarks"
        / "truffle/ProtosJvmVariantRunner.class"
    )

    repo_class = (
        repo
        / "target/classes/com/guillermomolina/protos/execution"
        / "ProtosStandaloneHostedSession.class"
    )

    cp_dir = WORK / "classpath"
    cp_file = cp_dir / f"{revision}.txt"

    if (
        runner_class.is_file()
        and repo_class.is_file()
        and cp_file.is_file()
        and cp_file.read_text(encoding="utf-8").strip()
    ):
        print(
            f"prepare={item['version']} "
            f"revision={revision} action=reuse",
            flush=True,
        )

        return os.pathsep.join(
            [
                str(TRUFFLE / "target" / "classes"),
                str(repo / "target" / "classes"),
                cp_file.read_text(
                    encoding="utf-8"
                ).strip(),
            ]
        )

    print(
        f"prepare={item['version']} "
        f"revision={revision} action=build",
        flush=True,
    )

    subprocess.run(
        [
            "mvn",
            "-q",
            "-f",
            str(repo / "pom.xml"),
            "-DskipTests",
            "compile",
        ],
        cwd=ROOT,
        check=True,
    )

    cp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    subprocess.run(
        [
            "mvn",
            "-q",
            "-f",
            str(repo / "pom.xml"),
            "dependency:build-classpath",
            f"-Dmdep.outputFile={cp_file}",
        ],
        cwd=ROOT,
        check=True,
    )

    dependency_cp = cp_file.read_text(
        encoding="utf-8"
    ).strip()

    if not dependency_cp:
        raise RuntimeError(
            f"empty dependency classpath: {cp_file}"
        )

    return os.pathsep.join(
        [
            str(TRUFFLE / "target" / "classes"),
            str(repo / "target" / "classes"),
            dependency_cp,
        ]
    )


def parse_output(output: str) -> dict[str, object]:
    setup_ns = None
    cold_ns = None
    steady: list[int] = []
    result_value = None

    sample = re.compile(
        r"^sample phase=(cold|warmup|steady) "
        r"iteration=\d+ elapsed_ns=(\d+)$"
    )

    for line in output.splitlines():
        if line.startswith("setup_ns="):
            setup_ns = int(line.split("=", 1)[1])
            continue

        match = sample.match(line)

        if match:
            phase = match.group(1)
            elapsed = int(match.group(2))

            if phase == "cold":
                cold_ns = elapsed
            elif phase == "steady":
                steady.append(elapsed)

            continue

        if line.startswith("result="):
            result_value = line.split("=", 1)[1]

    if (
        setup_ns is None
        or cold_ns is None
        or not steady
        or result_value is None
    ):
        raise RuntimeError(
            "cannot parse A/B benchmark output:\n" + output
        )

    return {
        "setup_ns": setup_ns,
        "cold_ns": cold_ns,
        "steady_ns": steady,
        "result": result_value,
    }


def show(
    cached: bool,
    observation: dict[str, object],
) -> float:
    steady = [int(value) for value in observation["steady_ns"]]
    p50 = statistics.median(steady)

    print(f"cache={'hit' if cached else 'miss'}")
    print(
        f"setup_ms={int(observation['setup_ns']) / 1_000_000:.3f}"
    )
    print(
        f"cold_ms={int(observation['cold_ns']) / 1_000_000:.3f}"
    )
    print(f"steady_p50_ms={p50 / 1_000_000:.3f}")
    print(f"steady_min_ms={min(steady) / 1_000_000:.3f}")
    print(f"steady_max_ms={max(steady) / 1_000_000:.3f}")
    print(f"result={observation['result']}")

    return float(p50)


def execute_case(
    item: dict[str, object],
    classpath: str,
    workload: str,
    source: Path,
    cpu: int,
    warmup: int,
    steady: int,
) -> dict[str, object]:
    result = subprocess.run(
        [
            "taskset",
            "-c",
            str(cpu),
            "java",
            "-cp",
            classpath,
            MAIN_CLASS,
            str(item["core"]),
            str(source),
            str(warmup),
            str(steady),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.returncode != 0:
        print(result.stdout, end="")
        raise RuntimeError(
            f"A/B execution failed: "
            f"{item['version']} {workload}"
        )

    observation = parse_output(result.stdout)

    expected = expected_result(workload)

    if observation["result"] != expected:
        raise RuntimeError(
            f"{item['version']} {workload}: "
            f"expected {expected}, got {observation['result']}"
        )

    return observation


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] != "benchmark":
        raise SystemExit(
            "usage: jvm_protos_ab.py benchmark <repo-a> <repo-b> [...]"
        )

    repos = [variant(argument) for argument in sys.argv[2:]]

    selected = os.environ.get("WORKLOAD", "all")

    try:
        workloads = protos_workloads_for_selection(selected)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    warmup = 5
    steady = 10
    cpu, siblings = choose_cpu()

    plans: list[
        tuple[
            dict[str, object],
            str,
            Path,
            dict[str, object],
            Path,
        ]
    ] = []

    missing_revisions: set[str] = set()

    for item in repos:
        for workload, source in workloads:
            ident = identity(
                item,
                workload,
                source,
                cpu,
                siblings,
                warmup,
                steady,
            )

            cache_file = CACHE / f"{cache_key(ident)}.json"

            plans.append(
                (item, workload, source, ident, cache_file)
            )

            if not cache_file.is_file():
                missing_revisions.add(str(item["revision"]))

    classpaths: dict[str, str] = {}

    if missing_revisions:
        subprocess.run(
            ["mvn", "-q", "-f", str(TRUFFLE / "pom.xml"), "compile"],
            cwd=ROOT,
            check=True,
        )

        for item in repos:
            revision = str(item["revision"])

            if revision in missing_revisions:
                classpaths[revision] = prepare_variant(item)

    print("mode=jvm-protos-ab")
    print(f"cpu={cpu}")
    print(
        "cpu_siblings="
        + ",".join(str(value) for value in siblings)
    )

    summary: dict[str, list[tuple[str, float]]] = {
        workload: []
        for workload, _ in workloads
    }

    for item, workload, source, ident, cache_file in plans:
        print()
        print(
            f"=== {item['version']} "
            f"{str(item['revision'])[:12]} "
            f"{workload} ==="
        )

        if cache_file.is_file():
            cached = json.loads(
                cache_file.read_text(encoding="utf-8")
            )
            p50 = show(True, cached["observation"])
        else:
            observation = execute_case(
                item,
                classpaths[str(item["revision"])],
                workload,
                source,
                cpu,
                warmup,
                steady,
            )

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

            p50 = show(False, observation)

        summary[workload].append(
            (str(item["version"]), p50)
        )

    print()
    print("=== A/B SUMMARY ===")

    for workload, values in summary.items():
        baseline_version, baseline = values[0]

        print(f"workload={workload}")
        print(
            f"baseline={baseline_version} "
            f"steady_p50_ms={baseline / 1_000_000:.3f}"
        )

        for version, value in values[1:]:
            change = ((value / baseline) - 1.0) * 100.0

            print(
                f"candidate={version} "
                f"steady_p50_ms={value / 1_000_000:.3f} "
                f"change_vs_baseline_pct={change:+.2f}"
            )


if __name__ == "__main__":
    main()
