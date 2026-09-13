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
import json
import os
from pathlib import Path
import platform
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf006d.json"
EXPECTED_BENCHMARK_BASE = "45493b49872860f5d29ad3d3a624e0af040c743b"
EXPECTED_PROTOS_REVISION = "4a03efc15620b37b2e418b3df30b4a26486446ec"
EXPECTED_EXECUTABLE_BASELINE = "428e46523e8fa0b3f0260b5a6e76c198725c041b"
EXPECTED_OPTIMIZER = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_FALLBACK = "com.oracle.truffle.api.impl.DefaultTruffleRuntime"
FALLBACK_WARNING_RE = re.compile(
    r"No optimizing Truffle runtime found|fallback runtime that does not support runtime compilation|"
    r"does not support runtime compilation to native code|executed in interpreted mode only",
    re.IGNORECASE,
)


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def output(command: list[str], *, cwd: Path = ROOT) -> str:
    try:
        return run(command, cwd=cwd, capture=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        details = ["command failed: " + " ".join(command)]
        if exc.stdout:
            details.append("stdout:\n" + exc.stdout[-6000:])
        if exc.stderr:
            details.append("stderr:\n" + exc.stderr[-6000:])
        raise RuntimeError("\n".join(details)) from exc


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    cfg = load_config()
    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF006"
    assert cfg["slice"] == "PERF006-D1"
    assert cfg["phase"] == "current-runtime-benchmark-contract"
    assert cfg["timing_claim"] is False
    assert cfg["protos_revision"] == EXPECTED_PROTOS_REVISION
    assert cfg["protos_executable_baseline"] == EXPECTED_EXECUTABLE_BASELINE
    assert cfg["protos_implementation_version"] == "0.2.492-SNAPSHOT"

    toolchain = cfg["toolchain"]
    assert toolchain["graalvm_release"] == "25.3.4.1"
    assert toolchain["jdk_feature"] == 25
    assert toolchain["jdk_version"] == "25.0.4.1"
    assert toolchain["container_image"] == (
        "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825"
    )
    assert toolchain["graal_truffle_version"] == "25.3.4.1"
    assert toolchain["maven_version"] == "3.9.9"
    assert toolchain["java_stack"] == "128m"

    variants = cfg["runtime_variants"]
    assert variants["optimizer"]["expected_runtime"] == EXPECTED_OPTIMIZER
    assert variants["fallback"]["expected_runtime"] == EXPECTED_FALLBACK
    assert variants["fallback"]["diagnostic_only"] is True
    assert variants["fallback"]["warning_suppression"] is False

    workloads = cfg["workloads"]
    assert [(x["id"], x["expected"]) for x in workloads] == [
        ("micro/closure-call", "42"),
        ("micro/method-call", "42"),
        ("runtime/monomorphic-dispatch", "42"),
        ("runtime/polymorphic-dispatch", "15000"),
        ("algorithms/fibonacci/recursive", "832040"),
    ]
    assert len({x["source"] for x in workloads}) == len(workloads)

    d2 = cfg["d2_measurement_contract"]
    assert d2["startup_process_samples_per_variant_workload"] == 10
    assert d2["persistent_forks_per_variant_workload"] == 5
    assert d2["warmup_iterations_per_fork"] == 20
    assert d2["steady_samples_per_fork"] == 20
    assert d2["primary_statistic"] == "median"
    assert d2["dispersion"] == ["mad", "min", "max", "p95"]
    assert d2["reference_timing_diagnostics"] is False
    assert d2["heavy_compiler_diagnostics_separate"] is True

    historical = cfg["historical_policy"]
    assert historical["rewrite_existing_perf001_perf003_evidence"] is False
    assert historical["cross_generation_speedup_claim_from_20_to_8_minute_full_suite"] is False

    # Preserve the original PERF001-C authority rather than silently repinning it.
    suite = json.loads((ROOT / "config" / "suite.json").read_text(encoding="utf-8"))
    assert suite["protos_corpus_revision"] == "42b8264a36254dafbd97d80f5181790e28b9de12"
    perf001g = json.loads((ROOT / "config" / "perf001g.json").read_text(encoding="utf-8"))
    assert perf001g["slice"] == "PERF001-G"

    dockerfile = (ROOT / "docker" / "protos-perf006d" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "ARG GRAAL_BASE=" + toolchain["container_image"] in dockerfile
    assert "ARG MAVEN_VERSION=3.9.9" in dockerfile
    assert "ARG PROTOS_REVISION=" + EXPECTED_PROTOS_REVISION in dockerfile
    assert "*truffle-runtime-*" in dockerfile
    assert "*truffle-compiler-*" in dockerfile
    assert "python3 dist/build_portable.py" in dockerfile

    run_sh = (ROOT / "docker" / "protos-perf006d" / "run.sh").read_text(
        encoding="utf-8"
    )
    assert "polyglot.engine.WarnInterpreterOnly" not in run_sh
    assert "truffle.UseFallbackRuntime" not in run_sh
    assert "/opt/perf006d/runtime-fallback" in run_sh
    assert "/opt/protos/lib/runtime" in run_sh

    runner_text = (ROOT / "runner" / "perf006d.py").read_text(encoding="utf-8")
    assert "--entrypoint" in runner_text
    assert '"java"' in runner_text
    assert "def runtime_probe(" in runner_text
    assert "no benchmark recursion stack" in runner_text

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "perf006d-validate:" in makefile
    assert "perf006d-smoke:" in makefile

    print("PERF006D1_CONFIG=PASS")
    print("PERF006D1_CURRENT_TOOLCHAIN_PROFILE=PASS")
    print("PERF006D1_HISTORICAL_EVIDENCE_IMMUTABILITY=PASS")
    print("PERF006D1_TIMING_CLAIM=NO")
    print("PERF006D1_SELECTED_WORKLOADS=%d" % len(workloads))
    return cfg


def first_allowed_cpu() -> str:
    status = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Cpus_allowed_list:\s*(.+)$", status, re.M)
    if not match:
        raise RuntimeError("cannot determine current Cpus_allowed_list")
    return match.group(1).strip().split(",")[0].split("-")[0]


def image_identity(tag: str) -> dict[str, Any]:
    data = json.loads(output(["docker", "image", "inspect", tag]))[0]
    return {
        "tag": tag,
        "id": data.get("Id", ""),
        "repo_digests": data.get("RepoDigests") or [],
    }


def docker_case(
    tag: str,
    cpu: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
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
            *args,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Docker PERF006-D1 case failed: "
            f"exit={completed.returncode} args={args!r}\n"
            f"stdout:\n{completed.stdout[-6000:]}\n"
            f"stderr:\n{completed.stderr[-6000:]}"
        )
    return completed


def runtime_probe(
    tag: str,
    cpu: str,
    variant: str,
) -> subprocess.CompletedProcess[str]:
    if variant == "optimizer":
        runtime_dir = "/opt/protos/lib/runtime"
    elif variant == "fallback":
        runtime_dir = "/opt/perf006d/runtime-fallback"
    else:
        raise ValueError("unknown runtime variant: " + variant)

    # Match the already-proven PERF001-F runtime probe shape:
    # direct java entrypoint, no benchmark recursion stack.
    completed = subprocess.run(
        [
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
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            f"/opt/perf006d/probe:/opt/protos/lib/protos.jar:{runtime_dir}/*",
            "Perf006dRuntimeProbe",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "PERF006-D1 runtime probe failed: "
            f"variant={variant} exit={completed.returncode}\n"
            f"stdout:\n{completed.stdout[-6000:]}\n"
            f"stderr:\n{completed.stderr[-6000:]}"
        )
    return completed


def runtime_from_probe(result: subprocess.CompletedProcess[str]) -> str:
    for line in result.stdout.splitlines():
        if line.startswith("PERF006D_RUNTIME="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("runtime probe emitted no PERF006D_RUNTIME line:\n" + result.stdout)


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


def smoke() -> None:
    cfg = validate()
    cpu = first_allowed_cpu()
    tag = "protos-benchmarks-perf006d1:" + cfg["protos_revision"][:12]

    print("PERF006D1_BUILD_BEGIN")
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
            "-t",
            tag,
            "-f",
            "docker/protos-perf006d/Dockerfile",
            ".",
        ]
    )
    identity = image_identity(tag)
    print("PERF006D1_BUILD=PASS")
    print("PERF006D1_IMAGE_ID=" + identity["id"])
    print("PERF006D1_CPUSET=" + cpu)

    optimizer_probe = runtime_probe(tag, cpu, "optimizer")
    fallback_probe = runtime_probe(tag, cpu, "fallback")
    optimizer_runtime = runtime_from_probe(optimizer_probe)
    fallback_runtime = runtime_from_probe(fallback_probe)

    if optimizer_runtime != EXPECTED_OPTIMIZER:
        raise RuntimeError(
            "optimizer runtime mismatch: %s != %s"
            % (optimizer_runtime, EXPECTED_OPTIMIZER)
        )
    if fallback_runtime != EXPECTED_FALLBACK:
        raise RuntimeError(
            "fallback runtime mismatch: %s != %s"
            % (fallback_runtime, EXPECTED_FALLBACK)
        )

    print("PERF006D1_OPTIMIZER_RUNTIME=" + optimizer_runtime)
    print("PERF006D1_FALLBACK_RUNTIME=" + fallback_runtime)
    print("PERF006D1_RUNTIME_IDENTITY=PASS")

    cases: list[dict[str, Any]] = []
    fallback_warning_seen = False
    total = len(cfg["workloads"]) * 2
    index = 0
    for workload in cfg["workloads"]:
        for variant in ("optimizer", "fallback"):
            index += 1
            result = docker_case(
                tag,
                cpu,
                "correctness",
                variant,
                workload["source"],
                workload["expected"],
            )
            observed = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
            if observed != workload["expected"]:
                raise RuntimeError(
                    "correctness mismatch variant=%s workload=%s expected=%s observed=%s"
                    % (variant, workload["id"], workload["expected"], observed)
                )
            warning = bool(FALLBACK_WARNING_RE.search(result.stderr))
            if variant == "optimizer" and warning:
                raise RuntimeError(
                    "optimizer emitted fallback/interpreter warning for %s:\n%s"
                    % (workload["id"], result.stderr[-4000:])
                )
            if variant == "fallback":
                fallback_warning_seen = fallback_warning_seen or warning
            cases.append(
                {
                    "workload": workload["id"],
                    "variant": variant,
                    "expected": workload["expected"],
                    "observed": observed,
                    "fallback_warning": warning,
                }
            )
            print(
                "PERF006D1_CORRECTNESS_CASE=%d/%d variant=%s workload=%s PASS"
                % (index, total, variant, workload["id"])
            )

    if not fallback_warning_seen:
        raise RuntimeError(
            "diagnostic fallback control never emitted the expected interpreter/fallback warning"
        )

    work = ROOT / ".work"
    work.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "slice": "PERF006-D1",
        "timing_claim": False,
        "protos_revision": cfg["protos_revision"],
        "benchmark_candidate_tree": output(["git", "write-tree"]),
        "image": identity,
        "host": host_inventory(cpu),
        "runtime_identity": {
            "optimizer": optimizer_runtime,
            "fallback": fallback_runtime,
        },
        "correctness_cases": cases,
        "fallback_warning_observed": True,
    }
    (work / "perf006-d1-smoke.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("PERF006D1_CORRECTNESS_CASES=%d" % total)
    print("PERF006D1_CORRECTNESS=PASS")
    print("PERF006D1_FALLBACK_WARNING=OBSERVED_EXPECTED")
    print("PERF006D1_OPTIMIZER_FALLBACK_WARNING=ABSENT")
    print("PERF006D1_SMOKE=PASS")
    print("PERF006D1_TIMING_CLAIM=NO")


def main() -> int:
    parser = argparse.ArgumentParser(description="PERF006-D1 current runtime contract")
    parser.add_argument("command", choices=("validate", "smoke"))
    args = parser.parse_args()
    if args.command == "validate":
        validate()
    else:
        smoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
