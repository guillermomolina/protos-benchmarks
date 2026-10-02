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
    jvm_sample_calls,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
CACHE = ROOT / "results" / "local" / "truffle-cache"
REJECTED = ROOT / "results" / "local" / "truffle-rejected"
PREPARE_STATE = ROOT / ".work" / "truffle-prepare"
AB_ROOT = ROOT / ".work" / "protos-ab"
PROTOS_WORKSPACE = Path("/workspaces/protos")

MAIN_CLASS = "com.guillermomolina.protos.benchmarks.truffle.TruffleJvmRunner"

REFERENCE_WARMUP = 60
REFERENCE_STEADY = 10
STABILITY_WINDOW = 5
STABILITY_MEDIAN_DRIFT_PCT = 15.0
STABILITY_MAD_PCT = 20.0
STABILITY_MAX_INTERNAL_GAP_PCT = 20.0
STABILITY_MIN_GAP_CLUSTER_SIZE = 3

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


def git_capture(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def benchmark_revision() -> str:
    return git_capture(ROOT, "rev-parse", "HEAD")


def benchmark_dirty() -> bool:
    return bool(
        git_capture(
            ROOT,
            "status",
            "--porcelain",
            "--untracked-files=all",
        )
    )


def require_clean_reference_harness() -> None:
    changed = git_capture(
        ROOT,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )

    if changed:
        raise RuntimeError(
            "reference measurement requires a clean "
            "published benchmark harness revision:\n"
            + changed
        )


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


def protos_identity() -> dict[str, object]:
    version = protos_maven_version()

    jar = (
        Path.home()
        / ".m2/repository/com/guillermomolina/protos"
        / version
        / f"protos-{version}.jar"
    )

    if not jar.is_file():
        raise RuntimeError(
            f"Protos JVM artifact not found: {jar}; "
            "run make truffle-prepare"
        )

    stamp = PREPARE_STATE / f"jvm-{version}.json"

    if not stamp.is_file():
        raise RuntimeError(
            f"prepared JVM identity missing: {stamp}; "
            "run make truffle-prepare"
        )

    state = json.loads(
        stamp.read_text(encoding="utf-8")
    )

    artifact_revision = state.get("revision")
    artifact_version = state.get("version")
    prepared_jar_sha = state.get("jar_sha256")
    actual_jar_sha = sha256_file(jar)

    if (
        not isinstance(artifact_revision, str)
        or len(artifact_revision) != 40
    ):
        raise RuntimeError(
            "prepared JVM artifact revision is invalid"
        )

    if artifact_version != version:
        raise RuntimeError(
            "prepared JVM artifact version mismatch: "
            f"{artifact_version} != {version}"
        )

    if prepared_jar_sha != actual_jar_sha:
        raise RuntimeError(
            "prepared JVM artifact hash mismatch"
        )

    artifact_checkout = (
        AB_ROOT
        / version.removesuffix("-SNAPSHOT")
    )

    checkout_revision = git_capture(
        artifact_checkout,
        "rev-parse",
        "HEAD",
    )

    if checkout_revision != artifact_revision:
        raise RuntimeError(
            "prepared checkout revision mismatch: "
            f"{checkout_revision} != {artifact_revision}"
        )

    artifact_core_sha = sha256_tree(
        artifact_checkout
        / "protos"
        / "lib"
        / "core"
    )

    workspace_core_sha = sha256_tree(
        PROTOS_WORKSPACE
        / "protos"
        / "lib"
        / "core"
    )

    if workspace_core_sha != artifact_core_sha:
        raise RuntimeError(
            "workspace Core differs from prepared "
            "JVM artifact Core"
        )

    return {
        "artifact": {
            "version": version,
            "revision": artifact_revision,
            "jar_sha256": actual_jar_sha,
        },
        "core": {
            "workspace_revision": git_capture(
                PROTOS_WORKSPACE,
                "rev-parse",
                "HEAD",
            ),
            "artifact_revision": artifact_revision,
            "sha256": workspace_core_sha,
        },
    }


def identity(
    language: str,
    workload: str,
    source: Path,
    cpu: int,
    siblings: list[int],
    profile: str,
    warmup: int,
    steady: int,
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema": 2,
        "measurement_definition":
            "jvm-cross-truffle-v2",
        "mode": "jvm",
        "profile": profile,
        "language": language,
        "workload": workload,
        "source_sha256": sha256_file(source),
        "harness_revision": benchmark_revision(),
        "harness_dirty": benchmark_dirty(),
        "matrix_sha256": sha256_file(Path(__file__)),
        "runner_sha256": sha256_file(
            TRUFFLE
            / "src/main/java/com/guillermomolina/protos/benchmarks"
            / "truffle/TruffleJvmRunner.java"
        ),
        "catalog_sha256": sha256_file(
            TRUFFLE / "workloads" / "catalog.json"
        ),
        "pom_sha256": sha256_file(TRUFFLE / "pom.xml"),
        "warmup_iterations": warmup,
        "steady_iterations": steady,
        "sample_calls": jvm_sample_calls(workload),
        "cpu": cpu,
        "cpu_siblings": siblings,
        "cpu_model": cpu_model(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "java_version": command_version("java", "-version"),
    }

    if profile == "benchmark":
        data["steady_state_admission"] = {
            "window": STABILITY_WINDOW,
            "median_drift_pct_max":
                STABILITY_MEDIAN_DRIFT_PCT,
            "mad_pct_max":
                STABILITY_MAD_PCT,
            "max_internal_gap_pct":
                STABILITY_MAX_INTERNAL_GAP_PCT,
            "min_gap_cluster_size":
                STABILITY_MIN_GAP_CLUSTER_SIZE,
        }

    if language == "protos":
        data["protos"] = protos_identity()

    return data


def cache_key(data: dict[str, object]) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def write_rejected_observation(
    key: str,
    identity_data: dict[str, object],
    admission: dict[str, object] | None,
    output: str,
) -> Path:
    REJECTED.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = REJECTED / f"{key}.json"

    path.write_text(
        json.dumps(
            {
                "identity": identity_data,
                "admission": admission,
                "evidence_status":
                    "REJECTED_NOT_STABLE",
                "output": output,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def parse_output(
    output: str,
) -> dict[str, object] | None:
    setup_ns: int | None = None
    sample_calls = 1
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
            setup_ns = int(
                line.split("=", 1)[1]
            )
            continue

        if line.startswith("sample_calls="):
            sample_calls = int(
                line.split("=", 1)[1]
            )
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

    if (
        setup_ns is None
        or not cold
        or not steady
        or result_value is None
    ):
        print(output, end="")
        return None

    return {
        "setup_ns": setup_ns,
        "sample_calls": sample_calls,
        "cold_ns": cold[0],
        "warmup_ns": warmup,
        "steady_ns": steady,
        "result": result_value,
    }


def median_absolute_deviation(
    values: list[int],
) -> float:
    median = float(statistics.median(values))

    return float(
        statistics.median(
            [
                abs(value - median)
                for value in values
            ]
        )
    )


def internal_gap_check(
    samples: list[int],
) -> dict[str, object]:
    ordered = sorted(samples)
    count = len(ordered)

    candidates = []

    for index in range(count - 1):
        left_count = index + 1
        right_count = count - left_count

        if (
            left_count < STABILITY_MIN_GAP_CLUSTER_SIZE
            or right_count < STABILITY_MIN_GAP_CLUSTER_SIZE
        ):
            continue

        low = ordered[index]
        high = ordered[index + 1]
        gap = high - low

        candidates.append(
            (
                gap,
                low,
                high,
                left_count,
                right_count,
            )
        )

    if not candidates:
        return {
            "status": "NOT_STABLE",
            "reason": "insufficient-gap-cluster-samples",
        }

    gap, low, high, left_count, right_count = max(
        candidates
    )

    median = float(statistics.median(ordered))

    gap_pct = (
        float(gap)
        / median
        * 100.0
    )

    stable = (
        gap_pct
        <= STABILITY_MAX_INTERNAL_GAP_PCT
    )

    return {
        "status":
            "PASS" if stable else "NOT_STABLE",
        "largest_internal_gap_ns": gap,
        "largest_internal_gap_pct": gap_pct,
        "gap_low_ns": low,
        "gap_high_ns": high,
        "gap_left_count": left_count,
        "gap_right_count": right_count,
    }


def stability_window(
    samples: list[int],
) -> dict[str, object]:
    required = STABILITY_WINDOW * 2

    if len(samples) < required:
        return {
            "status": "NOT_STABLE",
            "reason": "insufficient-samples",
            "required_samples": required,
            "actual_samples": len(samples),
        }

    previous = samples[
        -required:-STABILITY_WINDOW
    ]
    latest = samples[
        -STABILITY_WINDOW:
    ]

    previous_p50 = float(
        statistics.median(previous)
    )
    latest_p50 = float(
        statistics.median(latest)
    )

    drift_pct = (
        abs(latest_p50 - previous_p50)
        / previous_p50
        * 100.0
    )

    previous_mad_pct = (
        median_absolute_deviation(previous)
        / previous_p50
        * 100.0
    )

    latest_mad_pct = (
        median_absolute_deviation(latest)
        / latest_p50
        * 100.0
    )

    shape = internal_gap_check(
        samples[-required:]
    )

    stable = (
        drift_pct <= STABILITY_MEDIAN_DRIFT_PCT
        and previous_mad_pct <= STABILITY_MAD_PCT
        and latest_mad_pct <= STABILITY_MAD_PCT
        and shape["status"] == "PASS"
    )

    return {
        "status": "PASS" if stable else "NOT_STABLE",
        "previous_p50_ns": previous_p50,
        "latest_p50_ns": latest_p50,
        "median_drift_pct": drift_pct,
        "previous_mad_pct": previous_mad_pct,
        "latest_mad_pct": latest_mad_pct,
        "shape": shape,
    }


def reference_admission(
    warmup: list[int],
    steady: list[int],
) -> dict[str, object]:
    warmup_check = stability_window(warmup)
    steady_check = stability_window(steady)

    admitted = (
        warmup_check["status"] == "PASS"
        and steady_check["status"] == "PASS"
    )

    return {
        "status":
            "PASS" if admitted else "NOT_STABLE",
        "warmup": warmup_check,
        "steady": steady_check,
    }


def summarize_output(
    output: str,
    profile: str,
    admission_scope: str = "warmup-and-steady",
) -> tuple[str | None, dict[str, object] | None]:
    parsed = parse_output(output)

    if parsed is None:
        return None, None

    setup_ns = int(parsed["setup_ns"])
    sample_calls = int(parsed["sample_calls"])
    cold_ns = int(parsed["cold_ns"])

    warmup = [
        int(value)
        for value in parsed["warmup_ns"]
    ]

    steady = [
        int(value)
        for value in parsed["steady_ns"]
    ]

    result_value = str(parsed["result"])

    def ms(ns: float) -> float:
        return ns / 1_000_000.0

    print(f"setup_ms={ms(setup_ns):.3f}")
    print(f"cold_ms={ms(cold_ns):.3f}")

    if warmup:
        print(
            f"warmup_last_ms={ms(warmup[-1]):.3f}"
        )

    steady_p50 = float(
        statistics.median(steady)
    )

    print(
        "steady_p50_ms="
        f"{ms(steady_p50):.3f}"
    )
    print(f"sample_calls={sample_calls}")
    print(
        "steady_amortized_p50_ms="
        f"{ms(steady_p50 / sample_calls):.6f}"
    )
    print(
        f"steady_min_ms={ms(min(steady)):.3f}"
    )
    print(
        f"steady_max_ms={ms(max(steady)):.3f}"
    )
    print(f"result={result_value}")

    if profile != "benchmark":
        print("reference_admission=N/A")
        return result_value, None

    if admission_scope == "warmup-and-steady":
        admission = reference_admission(
            warmup,
            steady,
        )
        admission["scope"] = admission_scope
    elif admission_scope == "steady-only":
        warmup_check = stability_window(warmup)
        steady_check = stability_window(steady)
        admission = {
            "status": steady_check["status"],
            "scope": admission_scope,
            "warmup": warmup_check,
            "steady": steady_check,
        }
    else:
        raise RuntimeError(
            f"unknown reference admission scope: {admission_scope}"
        )

    for name in ("warmup", "steady"):
        check = admission[name]

        print(
            f"{name}_stability="
            f"{check['status']}"
        )

        if "median_drift_pct" in check:
            print(
                f"{name}_median_drift_pct="
                f"{float(check['median_drift_pct']):.2f}"
            )
            print(
                f"{name}_previous_mad_pct="
                f"{float(check['previous_mad_pct']):.2f}"
            )
            print(
                f"{name}_latest_mad_pct="
                f"{float(check['latest_mad_pct']):.2f}"
            )

            shape = check.get("shape", {})

            print(
                f"{name}_shape="
                f"{shape.get('status')}"
            )

            if "largest_internal_gap_pct" in shape:
                print(
                    f"{name}_largest_internal_gap_pct="
                    f"{float(shape['largest_internal_gap_pct']):.2f}"
                )
                print(
                    f"{name}_gap_split="
                    f"{shape['gap_left_count']}:"
                    f"{shape['gap_right_count']}"
                )

    print(
        "reference_admission="
        f"{admission['status']}"
    )

    return result_value, admission


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
    profile: str,
    warmup: int,
    steady: int,
) -> None:
    ident = identity(
        language,
        workload,
        source,
        cpu,
        siblings,
        profile,
        warmup,
        steady,
    )

    key = cache_key(ident)
    cache_file = CACHE / f"{key}.json"

    print()
    print(f"=== {language} {workload} ===")
    sample_calls = jvm_sample_calls(workload)

    print(f"cpu={cpu}")
    print(f"cpu_siblings={','.join(map(str, siblings))}")
    print(f"sample_calls={sample_calls}")

    if cache_file.is_file():
        cached = json.loads(
            cache_file.read_text(encoding="utf-8")
        )

        print("cache=hit")

        actual, admission = summarize_output(
            cached["output"],
            profile,
        )

        require_expected(workload, actual)

        if (
            profile == "benchmark"
            and (
                admission is None
                or admission["status"] != "PASS"
            )
        ):
            raise RuntimeError(
                f"{language}/{workload}: "
                "cached reference is not "
                "steady-state admitted"
            )

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
            f"measure {language} {relative_source} "
            f"{warmup} {steady} {sample_calls}"
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

    actual, admission = summarize_output(
        result.stdout,
        profile,
    )

    require_expected(workload, actual)

    if (
        profile == "benchmark"
        and (
            admission is None
            or admission["status"] != "PASS"
        )
    ):
        rejected = write_rejected_observation(
            key,
            ident,
            admission,
            result.stdout,
        )

        print(
            "rejected_raw="
            + str(rejected.relative_to(ROOT))
        )

        raise RuntimeError(
            f"{language}/{workload}: "
            "reference_admission=NOT_STABLE; "
            "measurement retained as rejected local raw "
            "and not accepted into timing cache"
        )

    CACHE.mkdir(parents=True, exist_ok=True)

    cache_file.write_text(
        json.dumps(
            {
                "identity": ident,
                "admission": admission,
                "output": result.stdout,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


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
        warmup = REFERENCE_WARMUP
        steady = REFERENCE_STEADY

    cpu, siblings = choose_cpu()

    identities = [
        (
            case,
            identity(
                *case,
                cpu,
                siblings,
                mode,
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
        if mode == "benchmark":
            require_clean_reference_harness()

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
            mode,
            warmup,
            steady,
        )


if __name__ == "__main__":
    main()
