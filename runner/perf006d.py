# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
# THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
# OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
# THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
# FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf006d.json"
D1_HARNESS = "1dc27dda3033f1d447b5525c9e40b6a93d03232d"
EXPECTED_PROTOS_REVISION = "4a03efc15620b37b2e418b3df30b4a26486446ec"
EXPECTED_EXECUTABLE_BASELINE = "428e46523e8fa0b3f0260b5a6e76c198725c041b"
EXPECTED_OPTIMIZER = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_FALLBACK = "com.oracle.truffle.api.impl.DefaultTruffleRuntime"
FALLBACK_WARNING_RE = re.compile(
    r"No optimizing Truffle runtime found|fallback runtime that does not support runtime compilation|"
    r"does not support runtime compilation to native code|executed in interpreted mode only",
    re.IGNORECASE,
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def output(command: list[str], *, cwd: Path = ROOT) -> str:
    completed = run(command, cwd=cwd, capture=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "command failed: "
            + " ".join(command)
            + "\nstdout:\n"
            + (completed.stdout or "")[-6000:]
            + "\nstderr:\n"
            + (completed.stderr or "")[-6000:]
        )
    return (completed.stdout or "").strip()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    cfg = load_config()
    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF006"
    assert cfg["slice"] == "PERF006-D2A"
    assert cfg["phase"] == "controlled-timing-harness-ready"
    assert cfg["d1_harness_revision"] == D1_HARNESS
    assert cfg["timing_claim"] is False
    assert cfg["protos_revision"] == EXPECTED_PROTOS_REVISION
    assert cfg["protos_executable_baseline"] == EXPECTED_EXECUTABLE_BASELINE
    assert cfg["protos_implementation_version"] == "0.2.492-SNAPSHOT"

    toolchain = cfg["toolchain"]
    assert toolchain == {
        "graalvm_release": "25.3.4.1",
        "jdk_feature": 25,
        "jdk_version": "25.0.4.1",
        "container_image": "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825",
        "graal_truffle_version": "25.3.4.1",
        "maven_version": "3.9.9",
        "java_stack": "128m",
    }

    variants = cfg["runtime_variants"]
    assert variants["optimizer"]["expected_runtime"] == EXPECTED_OPTIMIZER
    assert variants["fallback"]["expected_runtime"] == EXPECTED_FALLBACK
    assert variants["fallback"]["diagnostic_only"] is True
    assert variants["fallback"]["warning_suppression"] is False

    expected_workloads = [
        ("micro/closure-call", "micro/closure-call.protos", "42", "5ed62d6e67e2ec02195383987ca3f367c18ac947"),
        ("micro/method-call", "micro/method-call.protos", "42", "630ed821cc9b62c71f843859fb16b963414a0f52"),
        ("runtime/monomorphic-dispatch", "runtime/monomorphic-dispatch.protos", "42", "9ba70de276572f11771de4d98ebbed165e8892b2"),
        ("runtime/polymorphic-dispatch", "runtime/polymorphic-dispatch.protos", "15000", "ac0814f4dc6f5e2f3ac69e07b5738d0301aa7f38"),
        ("algorithms/fibonacci/recursive", "algorithms/fibonacci/recursive.protos", "832040", "4e8967a904425b189775640232bd4861009ab7dd"),
    ]
    observed_workloads = [
        (w["id"], w["source"], w["expected"], w["source_blob_sha"])
        for w in cfg["workloads"]
    ]
    assert observed_workloads == expected_workloads

    d2 = cfg["d2_measurement_contract"]
    assert d2["startup_process_samples_per_variant_workload"] == 10
    assert d2["persistent_forks_per_variant_workload"] == 5
    assert d2["warmup_iterations_per_fork"] == 20
    assert d2["steady_samples_per_fork"] == 20
    assert d2["primary_statistic"] == "median"
    assert d2["dispersion"] == ["mad", "min", "max", "p95"]
    assert d2["reference_timing_diagnostics"] is False
    assert d2["heavy_compiler_diagnostics_separate"] is True

    smoke = cfg["d2_harness_smoke"]
    assert smoke == {
        "workload": "micro/closure-call",
        "startup_samples_per_variant": 1,
        "persistent_forks_per_variant": 1,
        "warmup_iterations_per_fork": 2,
        "steady_samples_per_fork": 2,
        "retained": False,
    }
    assert cfg["d2_reference_output"] == "results/perf006-d2"

    historical = cfg["historical_policy"]
    assert historical["rewrite_existing_perf001_perf003_evidence"] is False
    assert historical["cross_generation_speedup_claim_from_20_to_8_minute_full_suite"] is False

    suite = json.loads((ROOT / "config" / "suite.json").read_text(encoding="utf-8"))
    assert suite["protos_corpus_revision"] == "42b8264a36254dafbd97d80f5181790e28b9de12"
    perf001g = json.loads((ROOT / "config" / "perf001g.json").read_text(encoding="utf-8"))
    assert perf001g["slice"] == "PERF001-G"

    dockerfile = (ROOT / "docker" / "protos-perf006d" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    for required in (
        "Perf006dPersistentDriver.java",
        "Perf006dStartupController.java",
        "/out/timing",
        "/opt/perf006d/timing",
        "*truffle-runtime-*",
        "*truffle-compiler-*",
    ):
        assert required in dockerfile

    persistent = (
        ROOT / "docker" / "protos-perf006d" / "Perf006dPersistentDriver.java"
    ).read_text(encoding="utf-8")
    for required in (
        "freshModuleActivation",
        "prelude.newExecutionContext()",
        "template.actorModuleState()",
        "template.currentModuleKey().orElse(null)",
        "template.executionDomain()",
        "processContext.execute(source, activation)",
        "fresh_activation_per_iteration",
    ):
        assert required in persistent
    assert "Source.newBuilder" in persistent
    assert "Files.readString" in persistent

    startup = (
        ROOT / "docker" / "protos-perf006d" / "Perf006dStartupController.java"
    ).read_text(encoding="utf-8")
    assert "builder.start()" in startup
    assert "fresh_jvm_per_sample" in startup
    assert "docker_start_outside_timing" in startup
    assert "Perf006dPersistentDriver" in startup

    runner_text = (ROOT / "runner" / "perf006d.py").read_text(encoding="utf-8")
    for forbidden in ("Trace" + "Compilation", "Dump" + "=Truffle"):
        assert forbidden not in runner_text
    assert "def reference(" in runner_text
    assert "def timing_smoke(" in runner_text

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "perf006d-timing-smoke:" in makefile
    assert "perf006d-reference:" in makefile

    print("PERF006D2A_CONFIG=PASS")
    print("PERF006D2A_D1_PREREQUISITE=PASS")
    print("PERF006D2A_CURRENT_TOOLCHAIN_PROFILE=PASS")
    print("PERF006D2A_HISTORICAL_EVIDENCE_IMMUTABILITY=PASS")
    print("PERF006D2A_TIMING_CLAIM=NO")
    print("PERF006D2A_SELECTED_WORKLOADS=%d" % len(cfg["workloads"]))
    return cfg


def first_allowed_cpu() -> str:
    status = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Cpus_allowed_list:\s*(.+)$", status, re.M)
    if not match:
        raise RuntimeError("cannot determine current Cpus_allowed_list")
    return match.group(1).strip().split(",")[0].split("-")[0]


def image_tag(cfg: dict[str, Any]) -> str:
    return "protos-benchmarks-perf006d:" + cfg["protos_revision"][:12]


def build_image(cfg: dict[str, Any]) -> str:
    tag = image_tag(cfg)
    print("PERF006D_IMAGE_BUILD_BEGIN")
    run(
        [
            "docker",
            "build",
            "--build-arg",
            "GRAAL_BASE=" + cfg["toolchain"]["container_image"],
            "--build-arg",
            "MAVEN_VERSION=" + cfg["toolchain"]["maven_version"],
            "--build-arg",
            "PROTOS_REPOSITORY=" + cfg["protos_repository"],
            "--build-arg",
            "PROTOS_REVISION=" + cfg["protos_revision"],
            "--label",
            "org.opencontainers.image.revision=" + cfg["protos_revision"],
            "-t",
            tag,
            "-f",
            "docker/protos-perf006d/Dockerfile",
            ".",
        ]
    )
    print("PERF006D_IMAGE_BUILD=PASS")
    return tag


def image_identity(tag: str) -> dict[str, Any]:
    data = json.loads(output(["docker", "image", "inspect", tag]))[0]
    return {
        "tag": tag,
        "id": data.get("Id", ""),
        "repo_digests": data.get("RepoDigests") or [],
    }


def runtime_dir(variant: str) -> str:
    if variant == "optimizer":
        return "/opt/protos/lib/runtime"
    if variant == "fallback":
        return "/opt/perf006d/runtime-fallback"
    raise ValueError("unknown runtime variant: " + variant)


def expected_runtime(variant: str) -> str:
    if variant == "optimizer":
        return EXPECTED_OPTIMIZER
    if variant == "fallback":
        return EXPECTED_FALLBACK
    raise ValueError("unknown runtime variant: " + variant)


def docker_java(
    tag: str,
    cpu: str,
    classpath: str,
    main_class: str,
    *args: str,
    stack: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpuset-cpus",
        cpu,
        "--entrypoint",
        "java",
        tag,
    ]
    if stack:
        command.append("-Xss128m")
    command.extend(
        [
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            classpath,
            main_class,
            *args,
        ]
    )
    completed = run(command, capture=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Docker Java case failed main={main_class} exit={completed.returncode}\n"
            f"stdout:\n{(completed.stdout or '')[-8000:]}\n"
            f"stderr:\n{(completed.stderr or '')[-8000:]}"
        )
    return completed


def runtime_probe(tag: str, cpu: str, variant: str) -> str:
    completed = docker_java(
        tag,
        cpu,
        f"/opt/perf006d/probe:/opt/protos/lib/protos.jar:{runtime_dir(variant)}/*",
        "Perf006dRuntimeProbe",
        stack=False,
    )
    observed = ""
    for line in (completed.stdout or "").splitlines():
        if line.startswith("PERF006D_RUNTIME="):
            observed = line.split("=", 1)[1].strip()
            break
    expected = expected_runtime(variant)
    if observed != expected:
        raise RuntimeError(
            f"runtime mismatch variant={variant} expected={expected!r} observed={observed!r}"
        )
    if variant == "optimizer" and FALLBACK_WARNING_RE.search(completed.stderr or ""):
        raise RuntimeError("optimizer runtime probe emitted fallback warning")
    return observed


def correctness_case(
    tag: str, cpu: str, variant: str, workload: dict[str, Any]
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpuset-cpus",
            cpu,
            tag,
            "correctness",
            variant,
            workload["source"],
            workload["expected"],
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"correctness failed variant={variant} workload={workload['id']} "
            f"exit={completed.returncode}\nstdout:\n{completed.stdout[-6000:]}\n"
            f"stderr:\n{completed.stderr[-6000:]}"
        )
    observed = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    if observed != workload["expected"]:
        raise RuntimeError(
            f"correctness mismatch variant={variant} workload={workload['id']} "
            f"expected={workload['expected']} observed={observed}"
        )
    warning = bool(FALLBACK_WARNING_RE.search(completed.stderr or ""))
    if variant == "optimizer" and warning:
        raise RuntimeError(
            f"optimizer correctness emitted fallback warning: {workload['id']}"
        )
    return {
        "workload": workload["id"],
        "variant": variant,
        "expected": workload["expected"],
        "observed": observed,
        "fallback_warning": warning,
    }


def parse_json_last_line(text: str, label: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(label + " emitted no stdout")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(label + " emitted invalid JSON: " + lines[-1]) from exc
    if payload.get("schema_version") != 1:
        raise RuntimeError(label + " payload schema mismatch")
    return payload


def startup_series(
    tag: str,
    cpu: str,
    variant: str,
    workload: dict[str, Any],
    samples: int,
) -> tuple[dict[str, Any], str]:
    completed = docker_java(
        tag,
        cpu,
        "/opt/perf006d/timing",
        "Perf006dStartupController",
        runtime_dir(variant),
        expected_runtime(variant),
        "/opt/perf006d/corpus/" + workload["source"],
        workload["expected"],
        str(samples),
        "180",
        stack=False,
    )
    payload = parse_json_last_line(completed.stdout or "", "startup controller")
    if payload.get("expected") != workload["expected"]:
        raise RuntimeError("startup expected-result identity mismatch")
    if payload.get("runtime") != expected_runtime(variant):
        raise RuntimeError("startup runtime identity mismatch")
    values = payload.get("startup_ns")
    if not isinstance(values, list) or len(values) != samples:
        raise RuntimeError("startup sample-count mismatch")
    if any(not isinstance(value, int) or value <= 0 for value in values):
        raise RuntimeError("startup contains non-positive sample")
    return payload, completed.stderr or ""


def persistent_fork(
    tag: str,
    cpu: str,
    variant: str,
    workload: dict[str, Any],
    warmup: int,
    steady: int,
) -> tuple[dict[str, Any], str]:
    completed = docker_java(
        tag,
        cpu,
        f"/opt/perf006d/timing:/opt/protos/lib/protos.jar:{runtime_dir(variant)}/*",
        "Perf006dPersistentDriver",
        "/opt/perf006d/corpus/" + workload["source"],
        workload["expected"],
        str(warmup),
        str(steady),
        stack=True,
    )
    payload = parse_json_last_line(completed.stdout or "", "persistent driver")
    if payload.get("expected") != workload["expected"]:
        raise RuntimeError("persistent expected-result identity mismatch")
    if payload.get("runtime") != expected_runtime(variant):
        raise RuntimeError("persistent runtime identity mismatch")
    for flag in (
        "source_reused",
        "process_reused",
        "context_reused",
        "fresh_activation_per_iteration",
    ):
        if payload.get(flag) is not True:
            raise RuntimeError("persistent hosting contract failed: " + flag)
    warmup_ns = payload.get("warmup_ns")
    steady_ns = payload.get("steady_ns")
    if not isinstance(warmup_ns, list) or len(warmup_ns) != warmup:
        raise RuntimeError("persistent warmup count mismatch")
    if not isinstance(steady_ns, list) or len(steady_ns) != steady:
        raise RuntimeError("persistent steady count mismatch")
    if any(not isinstance(value, int) or value <= 0 for value in warmup_ns + steady_ns):
        raise RuntimeError("persistent driver emitted non-positive timing sample")
    stderr = completed.stderr or ""
    if variant == "optimizer" and FALLBACK_WARNING_RE.search(stderr):
        raise RuntimeError("optimizer persistent fork emitted fallback warning")
    return payload, stderr


def summary(values: list[int]) -> dict[str, float | int]:
    if not values:
        raise ValueError("cannot summarize an empty timing sample")
    ordered = sorted(values)
    median = float(statistics.median(ordered))
    deviations = [abs(float(value) - median) for value in ordered]
    mad = float(statistics.median(deviations))
    p95_index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return {
        "count": len(ordered),
        "median_ns": median,
        "mad_ns": mad,
        "min_ns": ordered[0],
        "max_ns": ordered[-1],
        "p95_ns": ordered[p95_index],
    }


def per_iteration_medians(forks: list[list[int]]) -> list[float]:
    if not forks:
        return []
    width = len(forks[0])
    if any(len(values) != width for values in forks):
        raise ValueError("fork iteration lengths differ")
    return [
        float(statistics.median([fork[index] for fork in forks]))
        for index in range(width)
    ]


def host_inventory(cpu: str) -> dict[str, Any]:
    cpu_model = ""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
                break
    return {
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "cpu_model": cpu_model,
        "cpu_count": os.cpu_count() or 1,
        "cpuset": cpu,
        "docker_server_version": output(
            ["docker", "version", "--format", "{{.Server.Version}}"]
        ),
    }


def git_head() -> str:
    return output(["git", "rev-parse", "HEAD"])


def require_clean_exact_harness(revision: str) -> None:
    if not SHA_RE.fullmatch(revision):
        raise RuntimeError("harness revision must be an exact lowercase 40-character SHA")
    head = git_head()
    if head != revision:
        raise RuntimeError(f"harness revision mismatch: HEAD={head} expected={revision}")
    dirty = output(["git", "status", "--porcelain", "--untracked-files=all"])
    if dirty:
        raise RuntimeError("reference timing requires a clean exact harness worktree")


def timing_smoke() -> None:
    cfg = validate()
    cpu = first_allowed_cpu()
    tag = build_image(cfg)
    smoke = cfg["d2_harness_smoke"]
    workload = next(
        entry for entry in cfg["workloads"] if entry["id"] == smoke["workload"]
    )

    identities = {
        variant: runtime_probe(tag, cpu, variant)
        for variant in ("optimizer", "fallback")
    }
    fallback_warning_seen = False
    cases: dict[str, Any] = {}

    for variant in ("optimizer", "fallback"):
        startup, startup_stderr = startup_series(
            tag,
            cpu,
            variant,
            workload,
            smoke["startup_samples_per_variant"],
        )
        persistent, persistent_stderr = persistent_fork(
            tag,
            cpu,
            variant,
            workload,
            smoke["warmup_iterations_per_fork"],
            smoke["steady_samples_per_fork"],
        )
        stderr = startup_stderr + "\n" + persistent_stderr
        warning = bool(FALLBACK_WARNING_RE.search(stderr))
        if variant == "optimizer" and warning:
            raise RuntimeError("optimizer timing smoke emitted fallback warning")
        if variant == "fallback":
            fallback_warning_seen = fallback_warning_seen or warning
        cases[variant] = {
            "startup": startup,
            "persistent": persistent,
            "fallback_warning": warning,
        }

    if not fallback_warning_seen:
        raise RuntimeError("fallback timing smoke did not expose expected fallback warning")

    work = ROOT / ".work"
    work.mkdir(parents=True, exist_ok=True)
    path = work / "perf006-d2a-timing-smoke.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slice": "PERF006-D2A",
                "retained": False,
                "timing_claim": False,
                "cpu": cpu,
                "runtime_identity": identities,
                "workload": workload["id"],
                "cases": cases,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print("PERF006D2A_RUNTIME_IDENTITY=PASS")
    print("PERF006D2A_TIMING_SMOKE=PASS")
    print("PERF006D2A_FALLBACK_WARNING=OBSERVED_EXPECTED")
    print("PERF006D2A_RETAINED_TIMING=NO")
    print("PERF006D2A_TIMING_CLAIM=NO")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(harness_revision: str, output_dir: Path) -> None:
    cfg = validate()
    require_clean_exact_harness(harness_revision)

    expected_output = Path(cfg["d2_reference_output"])
    if output_dir != expected_output:
        raise RuntimeError(
            f"reference output must be {expected_output}, got {output_dir}"
        )
    if output_dir.exists():
        raise RuntimeError("reference output already exists: " + str(output_dir))

    cpu = first_allowed_cpu()
    tag = build_image(cfg)
    identities = {
        variant: runtime_probe(tag, cpu, variant)
        for variant in ("optimizer", "fallback")
    }

    correctness: list[dict[str, Any]] = []
    fallback_warning_seen = False
    for workload in cfg["workloads"]:
        for variant in ("optimizer", "fallback"):
            case = correctness_case(tag, cpu, variant, workload)
            correctness.append(case)
            if variant == "fallback":
                fallback_warning_seen = fallback_warning_seen or bool(
                    case["fallback_warning"]
                )
            print(
                "CORRECTNESS PASS variant=%s workload=%s"
                % (variant, workload["id"])
            )
    if not fallback_warning_seen:
        raise RuntimeError("reference correctness control exposed no fallback warning")

    policy = cfg["d2_measurement_contract"]
    startup_count = int(policy["startup_process_samples_per_variant_workload"])
    forks_count = int(policy["persistent_forks_per_variant_workload"])
    warmup_count = int(policy["warmup_iterations_per_fork"])
    steady_count = int(policy["steady_samples_per_fork"])

    raw_cases: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    speedups: list[dict[str, Any]] = []

    for workload in cfg["workloads"]:
        by_variant: dict[str, dict[str, Any]] = {}
        for variant in ("fallback", "optimizer"):
            print(
                f"MEASURE BEGIN variant={variant} workload={workload['id']} "
                f"startup={startup_count} forks={forks_count} "
                f"warmup={warmup_count} steady={steady_count}"
            )
            startup, startup_stderr = startup_series(
                tag, cpu, variant, workload, startup_count
            )
            persistent_forks: list[dict[str, Any]] = []
            warmup_forks: list[list[int]] = []
            steady_forks: list[list[int]] = []
            warning = bool(FALLBACK_WARNING_RE.search(startup_stderr))
            for fork in range(forks_count):
                payload, stderr = persistent_fork(
                    tag,
                    cpu,
                    variant,
                    workload,
                    warmup_count,
                    steady_count,
                )
                warning = warning or bool(FALLBACK_WARNING_RE.search(stderr))
                warmup_values = [int(value) for value in payload["warmup_ns"]]
                steady_values = [int(value) for value in payload["steady_ns"]]
                warmup_forks.append(warmup_values)
                steady_forks.append(steady_values)
                persistent_forks.append(
                    {
                        "fork": fork + 1,
                        "warmup_ns": warmup_values,
                        "steady_ns": steady_values,
                    }
                )
                print(
                    f"MEASURE FORK PASS variant={variant} "
                    f"workload={workload['id']} fork={fork + 1}/{forks_count}"
                )

            if variant == "optimizer" and warning:
                raise RuntimeError(
                    f"optimizer reference timing emitted fallback warning: {workload['id']}"
                )
            if variant == "fallback" and not warning:
                raise RuntimeError(
                    f"fallback reference timing exposed no fallback warning: {workload['id']}"
                )

            startup_values = [int(value) for value in startup["startup_ns"]]
            warmup_values = [value for fork in warmup_forks for value in fork]
            steady_values = [value for fork in steady_forks for value in fork]

            variant_summary = {
                "workload": workload["id"],
                "variant": variant,
                "startup": summary(startup_values),
                "warmup": summary(warmup_values),
                "steady": summary(steady_values),
                "warmup_iteration_median_ns": per_iteration_medians(warmup_forks),
                "steady_iteration_median_ns": per_iteration_medians(steady_forks),
            }
            summaries.append(variant_summary)
            raw_case = {
                "workload": workload["id"],
                "source": workload["source"],
                "source_blob_sha": workload["source_blob_sha"],
                "expected": workload["expected"],
                "variant": variant,
                "runtime": expected_runtime(variant),
                "fallback_warning": warning,
                "startup_ns": startup_values,
                "persistent_forks": persistent_forks,
            }
            raw_cases.append(raw_case)
            by_variant[variant] = variant_summary
            print(f"MEASURE PASS variant={variant} workload={workload['id']}")

        fallback_summary = by_variant["fallback"]
        optimizer_summary = by_variant["optimizer"]
        speedups.append(
            {
                "workload": workload["id"],
                "ratio_definition": "fallback_median_ns / optimizer_median_ns",
                "startup_ratio": (
                    fallback_summary["startup"]["median_ns"]
                    / optimizer_summary["startup"]["median_ns"]
                ),
                "warmup_ratio": (
                    fallback_summary["warmup"]["median_ns"]
                    / optimizer_summary["warmup"]["median_ns"]
                ),
                "steady_ratio": (
                    fallback_summary["steady"]["median_ns"]
                    / optimizer_summary["steady"]["median_ns"]
                ),
            }
        )

    output_dir.mkdir(parents=True)

    raw_payload = {
        "schema_version": 1,
        "perf_item": "PERF006",
        "slice": "PERF006-D2",
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "protos_implementation_version": cfg["protos_implementation_version"],
        "toolchain": cfg["toolchain"],
        "cpu_policy": cfg["execution_policy"]["cpu_affinity"],
        "host": host_inventory(cpu),
        "image": image_identity(tag),
        "runtime_identity": identities,
        "measurement_policy": policy,
        "correctness_cases": correctness,
        "cases": raw_cases,
    }
    summary_payload = {
        "schema_version": 1,
        "perf_item": "PERF006",
        "slice": "PERF006-D2",
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "primary_statistic": policy["primary_statistic"],
        "dispersion": policy["dispersion"],
        "summaries": summaries,
        "speedups": speedups,
        "interpretation_policy": {
            "ratio_definition": "fallback_median_ns / optimizer_median_ns",
            "ratio_above_1": "optimizer faster",
            "ratio_below_1": "fallback faster",
            "full_suite_20_to_8_minute_observation_used_as_claim": False,
            "heavy_compiler_diagnostics_in_reference_timing": False,
        },
    }

    raw_path = output_dir / "raw.json"
    summary_path = output_dir / "summary.json"
    raw_path.write_text(
        json.dumps(raw_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = []
    for item in speedups:
        rows.append(
            "| %s | %.4f | %.4f | %.4f |"
            % (
                item["workload"],
                item["startup_ratio"],
                item["warmup_ratio"],
                item["steady_ratio"],
            )
        )
    readme = """# PERF006-D2 controlled fallback/optimizer timing evidence

Exact-source comparison of the D1-proven runtime variants.

- harness revision: `%s`
- Protos revision: `%s`
- implementation version: `%s`
- optimizer: `%s`
- fallback control: `%s`
- ratio definition: `fallback median / optimizer median`
- ratio > 1 means optimizer is faster
- heavy compiler diagnostics: excluded from reference timing and deferred to D3
- historical ~20 min -> ~8 min full-suite observation: not used as a benchmark claim

| workload | startup ratio | warmup ratio | steady ratio |
| --- | ---: | ---: | ---: |
%s

See `raw.json` for every ordered sample and `summary.json` for
median/MAD/min/max/p95 summaries and per-iteration medians.
""" % (
        harness_revision,
        cfg["protos_revision"],
        cfg["protos_implementation_version"],
        EXPECTED_OPTIMIZER,
        EXPECTED_FALLBACK,
        "\n".join(rows),
    )
    readme_path = output_dir / "README.md"
    readme_path.write_text(readme, encoding="utf-8")

    manifest_path = output_dir / "SHA256SUMS"
    manifest_path.write_text(
        "%s  raw.json\n%s  summary.json\n%s  README.md\n"
        % (
            sha256_file(raw_path),
            sha256_file(summary_path),
            sha256_file(readme_path),
        ),
        encoding="utf-8",
    )

    print("PERF006D2_REFERENCE=PASS")
    print("PERF006D2_CORRECTNESS_CASES=%d" % len(correctness))
    print("PERF006D2_STARTUP_SAMPLES_PER_VARIANT_WORKLOAD=%d" % startup_count)
    print("PERF006D2_PERSISTENT_FORKS_PER_VARIANT_WORKLOAD=%d" % forks_count)
    print("PERF006D2_WARMUP_ITERATIONS_PER_FORK=%d" % warmup_count)
    print("PERF006D2_STEADY_SAMPLES_PER_FORK=%d" % steady_count)
    print("PERF006D2_OUTPUT=" + str(output_dir))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PERF006-D controlled optimizer/fallback benchmark harness"
    )
    parser.add_argument(
        "command", choices=("validate", "timing-smoke", "reference")
    )
    parser.add_argument("--harness-revision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if args.command == "validate":
        validate()
        return 0
    if args.command == "timing-smoke":
        timing_smoke()
        return 0

    if not args.harness_revision:
        parser.error("reference requires --harness-revision")
    if not args.output_dir:
        parser.error("reference requires --output-dir")
    reference(args.harness_revision, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
