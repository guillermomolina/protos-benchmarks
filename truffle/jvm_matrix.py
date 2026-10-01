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
    cases_for_selection,
    expected_result,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
CACHE = ROOT / "results" / "local" / "truffle-cache"
MAIN_CLASS = "com.guillermomolina.protos.benchmarks.truffle.TruffleJvmRunner"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(path: Path) -> str:
    h = hashlib.sha256()

    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(str(item.relative_to(path)).encode())
        h.update(b"\0")
        h.update(item.read_bytes())
        h.update(b"\0")

    return h.hexdigest()


def parse_cpu_list(value: str) -> set[int]:
    cpus: set[int] = set()

    for part in value.strip().split(","):
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            cpus.update(range(start, end + 1))
        elif part:
            cpus.add(int(part))

    return cpus


def choose_cpu() -> tuple[int, list[int]]:
    allowed = set(os.sched_getaffinity(0))

    requested = os.environ.get("CPU")
    if requested is not None:
        cpu = int(requested)
        if cpu not in allowed:
            raise RuntimeError(
                f"CPU={cpu} is outside allowed affinity {sorted(allowed)}"
            )
    else:
        cpu = min(allowed)

    sibling_file = Path(
        f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list"
    )

    if sibling_file.exists():
        siblings = sorted(
            parse_cpu_list(sibling_file.read_text(encoding="utf-8"))
        )
    else:
        siblings = [cpu]

    return cpu, siblings


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass

    return "unknown"


def command_version(*command: str) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", "/workspaces/protos", *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def protos_maven_version() -> str:
    pom = TRUFFLE / "pom.xml"
    root = ET.parse(pom).getroot()

    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    properties: dict[str, str] = {}
    properties_node = root.find(f"{namespace}properties")
    if properties_node is not None:
        for child in properties_node:
            name = child.tag
            if name.startswith("{"):
                name = name.split("}", 1)[1]
            properties[name] = (child.text or "").strip()

    dependencies = root.find(f"{namespace}dependencies")
    if dependencies is None:
        raise RuntimeError("pom.xml has no dependencies section")

    for dependency in dependencies.findall(f"{namespace}dependency"):
        group_id = dependency.findtext(f"{namespace}groupId", "").strip()
        artifact_id = dependency.findtext(f"{namespace}artifactId", "").strip()

        if (
            group_id == "com.guillermomolina"
            and artifact_id == "protos"
        ):
            version = dependency.findtext(
                f"{namespace}version",
                "",
            ).strip()

            if version.startswith("${") and version.endswith("}"):
                property_name = version[2:-1]
                try:
                    version = properties[property_name]
                except KeyError as exc:
                    raise RuntimeError(
                        f"unresolved Maven property: {property_name}"
                    ) from exc

            if not version:
                raise RuntimeError(
                    "Protos Maven dependency has no explicit version"
                )

            return version

    raise RuntimeError(
        "com.guillermomolina:protos dependency not found in pom.xml"
    )


def protos_identity() -> dict[str, str]:
    version = protos_maven_version()

    jar = (
        Path.home()
        / ".m2/repository/com/guillermomolina/protos"
        / version
        / f"protos-{version}.jar"
    )

    if not jar.is_file():
        raise RuntimeError(f"Protos JVM artifact not found: {jar}")

    return {
        "version": version,
        "revision": git_value("rev-parse", "HEAD"),
        "jar_sha256": sha256_file(jar),
        "core_sha256": sha256_tree(
            Path("/workspaces/protos/protos/lib/core")
        ),
    }


def identity(
    language: str,
    workload: str,
    source: Path,
    cpu: int,
    siblings: list[int],
    warmup: int,
    steady: int,
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema": 1,
        "mode": "jvm",
        "language": language,
        "workload": workload,
        "source_sha256": sha256_file(source),
        "runner_sha256": sha256_file(
            TRUFFLE
            / "src/main/java/com/guillermomolina/protos/benchmarks"
            / "truffle/TruffleJvmRunner.java"
        ),
        "pom_sha256": sha256_file(TRUFFLE / "pom.xml"),
        "warmup_iterations": warmup,
        "steady_iterations": steady,
        "cpu": cpu,
        "cpu_siblings": siblings,
        "cpu_model": cpu_model(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "java_version": command_version("java", "-version"),
    }

    if language == "protos":
        data["protos"] = protos_identity()

    return data


def cache_key(data: dict[str, object]) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()



def summarize_output(output: str) -> str | None:
    setup_ns: int | None = None
    cold: list[int] = []
    warmup: list[int] = []
    steady: list[int] = []
    result_value: str | None = None

    sample_pattern = re.compile(
        r"^sample phase=(cold|warmup|steady) "
        r"iteration=\d+ elapsed_ns=(\d+)$"
    )

    for line in output.splitlines():
        if line.startswith("setup_ns="):
            setup_ns = int(line.split("=", 1)[1])
            continue

        match = sample_pattern.match(line)
        if match:
            phase = match.group(1)
            elapsed = int(match.group(2))

            if phase == "cold":
                cold.append(elapsed)
            elif phase == "warmup":
                warmup.append(elapsed)
            else:
                steady.append(elapsed)

            continue

        if line.startswith("result="):
            result_value = line.split("=", 1)[1]

    if setup_ns is None or not cold or not steady or result_value is None:
        print(output, end="")
        return None

    def ms(ns: float) -> float:
        return ns / 1_000_000.0

    print(f"setup_ms={ms(setup_ns):.3f}")
    print(f"cold_ms={ms(cold[0]):.3f}")

    if warmup:
        print(f"warmup_last_ms={ms(warmup[-1]):.3f}")

    print(f"steady_p50_ms={ms(statistics.median(steady)):.3f}")
    print(f"steady_min_ms={ms(min(steady)):.3f}")
    print(f"steady_max_ms={ms(max(steady)):.3f}")
    print(f"result={result_value}")
    return result_value


def require_expected(
    workload: str,
    actual: str | None,
) -> None:
    expected = expected_result(workload)

    if actual != expected:
        raise RuntimeError(
            f"{workload}: expected {expected}, got {actual!r}"
        )


def run_case(
    language: str,
    workload: str,
    source: Path,
    cpu: int,
    siblings: list[int],
    warmup: int,
    steady: int,
) -> None:
    ident = identity(
        language,
        workload,
        source,
        cpu,
        siblings,
        warmup,
        steady,
    )

    key = cache_key(ident)
    cache_file = CACHE / f"{key}.json"

    print()
    print(f"=== {language} {workload} ===")
    print(f"cpu={cpu}")
    print(f"cpu_siblings={','.join(map(str, siblings))}")

    if cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        print("cache=hit")
        actual = summarize_output(cached["output"])
        require_expected(workload, actual)
        return

    print("cache=miss")

    relative_source = source.relative_to(ROOT)

    command = [
        "taskset",
        "-c",
        str(cpu),
        "mvn",
        "-f",
        str(TRUFFLE / "pom.xml"),
        "-q",
        "exec:java",
        f"-Dexec.mainClass={MAIN_CLASS}",
        (
            "-Dexec.args="
            f"measure {language} {relative_source} {warmup} {steady}"
        ),
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.returncode != 0:
        print(result.stdout, end="")
        raise RuntimeError(
            f"benchmark failed for {language}/{workload}"
        )

    CACHE.mkdir(parents=True, exist_ok=True)

    cache_file.write_text(
        json.dumps(
            {
                "identity": ident,
                "output": result.stdout,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    actual = summarize_output(result.stdout)
    require_expected(workload, actual)


def compile_runner() -> None:
    subprocess.run(
        ["mvn", "-f", str(TRUFFLE / "pom.xml"), "-q", "compile"],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    if (
        len(sys.argv) not in {2, 3}
        or sys.argv[1] not in {"smoke", "benchmark"}
    ):
        raise SystemExit(
            "usage: jvm_matrix.py "
            "<smoke|benchmark> [all|<workload>]"
        )

    mode = sys.argv[1]
    selected = sys.argv[2] if len(sys.argv) == 3 else "all"

    try:
        cases = cases_for_selection(selected)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if mode == "smoke":
        warmup, steady = 2, 3
    else:
        warmup, steady = 5, 10

    cpu, siblings = choose_cpu()

    identities = [
        (
            case,
            identity(
                *case,
                cpu,
                siblings,
                warmup,
                steady,
            ),
        )
        for case in cases
    ]

    needs_measurement = any(
        not (CACHE / f"{cache_key(ident)}.json").is_file()
        for _, ident in identities
    )

    if needs_measurement:
        compile_runner()

    print("mode=jvm-matrix")
    print(f"profile={mode}")
    print(f"cpu={cpu}")
    print(f"cpu_siblings={','.join(map(str, siblings))}")

    for case in cases:
        run_case(
            *case,
            cpu,
            siblings,
            warmup,
            steady,
        )


if __name__ == "__main__":
    main()
