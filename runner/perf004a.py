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
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf004a.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FALLBACK_WARNING_RE = re.compile(
    r"No optimizing Truffle runtime found|fallback runtime that does not support runtime compilation|"
    r"does not support runtime compilation to native code|executed in interpreted mode only",
    re.IGNORECASE,
)
EXPECTED_OPTIMIZER = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_IDS = (
    "micro/slot-read",
    "micro/slot-write",
    "micro/closure-call",
    "micro/method-call",
    "micro/object-creation",
    "micro/delegation-shallow",
    "micro/delegation-deep",
    "runtime/monomorphic-dispatch",
    "runtime/polymorphic-dispatch",
    "algorithms/factorial/recursive",
    "algorithms/fibonacci/recursive",
)


def run(
    command: list[str],
    *,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )


def output(command: list[str]) -> str:
    completed = run(command, capture=True, check=False)
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def config() -> dict[str, Any]:
    return load_json(CONFIG)


def suite() -> dict[str, Any]:
    return load_json(ROOT / "config" / "suite.json")


def workload_entries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    pins = {str(item["id"]): str(item["source_blob_sha"]) for item in cfg["workloads"]}
    result = []
    for item in suite()["benchmarks"]:
        benchmark_id = str(item["id"])
        result.append(
            {
                "id": benchmark_id,
                "expected": str(item["expected_stdout"]),
                "protos": str(item["protos"]),
                "python": str(item["implementations"]["python"]),
                "javascript": str(item["implementations"]["javascript"]),
                "equivalence": str(item["equivalence"]),
                "source_blob_sha": pins[benchmark_id],
            }
        )
    return result


def validate() -> dict[str, Any]:
    cfg = config()
    if cfg.get("schema_version") != 2:
        raise RuntimeError("unsupported PERF004-A config schema")
    if cfg.get("perf_item") != "PERF004" or cfg.get("slice") != "PERF004-A2":
        raise RuntimeError("PERF004-A2 identity drift")
    if cfg.get("phase") != "cross-language-timing-harness-ready":
        raise RuntimeError("PERF004-A2 phase drift")
    if cfg.get("timing_claim") is not False:
        raise RuntimeError("PERF004-A2 must not publish a timing claim")
    if cfg.get("a1_revision") != "d8df6daf11015b0a074ed47456e946d985d111db":
        raise RuntimeError("PERF004-A1 provenance drift")
    if cfg.get("protos_revision") != "4a03efc15620b37b2e418b3df30b4a26486446ec":
        raise RuntimeError("PERF004-A2 Protos revision drift")
    if cfg.get("equivalence_source_revision") != "42b8264a36254dafbd97d80f5181790e28b9de12":
        raise RuntimeError("PERF004-A2 equivalence-source revision drift")
    if cfg.get("comparison_languages") != ["protos", "python", "javascript"]:
        raise RuntimeError("PERF004-A2 language-set drift")

    toolchain = cfg["toolchain"]
    if toolchain != {
        "graalvm_release": "25.3.4.1",
        "jdk_feature": 25,
        "jdk_version": "25.0.4.1",
        "graal_truffle_version": "25.3.4.1",
        "maven_version": "3.9.9",
        "java_stack": "128m",
        "graal_container_image": "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825",
    }:
        raise RuntimeError("PERF004-A2 toolchain drift")

    runtimes = cfg["comparison_runtimes"]
    if runtimes["python"]["base"] != "python:3.14.7-slim-bookworm":
        raise RuntimeError("PERF004-A2 Python runtime drift")
    if runtimes["javascript"]["base"] != "node:24.20.0-bookworm-slim":
        raise RuntimeError("PERF004-A2 JavaScript runtime drift")
    if int(runtimes["javascript"]["stack_kb"]) != 32768:
        raise RuntimeError("PERF004-A2 JavaScript stack drift")

    reused = cfg["protos_driver_reuse"]
    if reused["origin_slice"] != "PERF006-D2A":
        raise RuntimeError("PERF004-A2 Protos driver provenance drift")
    if reused["expected_runtime"] != EXPECTED_OPTIMIZER:
        raise RuntimeError("PERF004-A2 optimizer runtime identity drift")
    for path in (
        ROOT / reused["dockerfile"],
        ROOT / "docker/protos-perf006d/Perf006dPersistentDriver.java",
        ROOT / "docker/protos-perf006d/Perf006dStartupController.java",
        ROOT / "docker/protos-perf006d/Perf006dRuntimeProbe.java",
        ROOT / "docker/python-perf004a/Dockerfile",
        ROOT / "docker/python-perf004a/timing_driver.py",
        ROOT / "docker/node-perf004a/Dockerfile",
        ROOT / "docker/node-perf004a/timing_driver.mjs",
    ):
        if not path.is_file():
            raise RuntimeError(f"missing PERF004-A2 harness file: {path}")

    policy = cfg["measurement_contract"]
    if policy != {
        "startup_process_samples_per_language_workload": 10,
        "persistent_forks_per_language_workload": 5,
        "warmup_iterations_per_fork": 20,
        "steady_samples_per_fork": 20,
        "primary_statistic": "median",
        "dispersion": ["mad", "min", "max", "p95"],
        "correctness_before_timing": True,
        "heavy_diagnostics_separate": True,
        "network": "none",
        "cpu_affinity": "first CPU from current allowed cpuset",
        "startup_boundary": "fresh language process inside an already-running Docker container; Docker creation/start excluded",
        "persistent_boundary": "source/module load and runtime bootstrap outside timed iterations; one process per fork",
    }:
        raise RuntimeError("PERF004-A2 measurement contract drift")

    suite_cfg = suite()
    if suite_cfg.get("classification") != "algorithm-equivalent":
        raise RuntimeError("PERF004-A suite must remain algorithm-equivalent")
    if suite_cfg.get("protos_corpus_revision") != cfg["equivalence_source_revision"]:
        raise RuntimeError("PERF004-A suite equivalence revision drift")
    observed_ids = tuple(str(item["id"]) for item in suite_cfg["benchmarks"])
    if observed_ids != EXPECTED_IDS:
        raise RuntimeError(f"PERF004-A corpus drift: {observed_ids!r}")
    configured_ids = tuple(str(item["id"]) for item in cfg["workloads"])
    if configured_ids != EXPECTED_IDS:
        raise RuntimeError("PERF004-A source-blob pin set drift")
    for item in cfg["workloads"]:
        if not re.fullmatch(r"[0-9a-f]{40}", str(item["source_blob_sha"])):
            raise RuntimeError(f"invalid source blob pin: {item}")

    smoke = cfg["a2_smoke"]
    if smoke != {
        "workload": "micro/closure-call",
        "startup_samples_per_language": 1,
        "persistent_forks_per_language": 1,
        "warmup_iterations_per_fork": 2,
        "steady_samples_per_fork": 2,
        "retained": False,
    }:
        raise RuntimeError("PERF004-A2 smoke contract drift")

    runner_text = (ROOT / "runner/perf004a.py").read_text(encoding="utf-8")
    for forbidden in ("Trace" + "Compilation", "Dump" + "=Truffle"):
        if forbidden in runner_text:
            raise RuntimeError("heavy diagnostics leaked into PERF004-A2 timing runner")

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("perf004a-validate:", "perf004a-smoke:", "perf004a-reference:"):
        if target not in makefile:
            raise RuntimeError(f"missing Makefile target {target}")

    print("PERF004A2_CONFIG=PASS")
    print("PERF004A2_ALGORITHM_EQUIVALENT_CORPUS=PASS")
    print("PERF004A2_PROTOS_DRIVER_REUSE=PERF006_D2")
    print("PERF004A2_PROTOS_MODIFICATION=NONE")
    print("PERF004A2_TIMING_CLAIM=NO")
    print(f"PERF004A2_WORKLOADS={len(cfg['workloads'])}")
    return cfg


def first_allowed_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Cpus_allowed_list:\s*(.+)$", text, re.M)
    if not match:
        raise RuntimeError("cannot determine current Cpus_allowed_list")
    return match.group(1).strip().split(",")[0].split("-")[0]


def image_tags(cfg: dict[str, Any]) -> dict[str, str]:
    short = cfg["protos_revision"][:12]
    return {
        "protos": f"protos-benchmarks-perf004a-protos:{short}",
        "python": f"protos-benchmarks-perf004a-python:{short}",
        "javascript": f"protos-benchmarks-perf004a-node:{short}",
    }


def build_images(cfg: dict[str, Any]) -> dict[str, str]:
    tags = image_tags(cfg)
    print("PERF004A2_BUILD_BEGIN language=protos", flush=True)
    run(
        [
            "docker", "build", "--pull",
            "--build-arg", "GRAAL_BASE=" + cfg["toolchain"]["graal_container_image"],
            "--build-arg", "MAVEN_VERSION=" + cfg["toolchain"]["maven_version"],
            "--build-arg", "PROTOS_REPOSITORY=" + cfg["protos_repository"],
            "--build-arg", "PROTOS_REVISION=" + cfg["protos_revision"],
            "-t", tags["protos"],
            "-f", cfg["protos_driver_reuse"]["dockerfile"],
            ".",
        ]
    )
    print("PERF004A2_BUILD_PASS language=protos", flush=True)

    print("PERF004A2_BUILD_BEGIN language=python", flush=True)
    run(
        [
            "docker", "build", "--pull",
            "--build-arg", "PYTHON_BASE=" + cfg["comparison_runtimes"]["python"]["base"],
            "-t", tags["python"],
            "-f", "docker/python-perf004a/Dockerfile",
            ".",
        ]
    )
    print("PERF004A2_BUILD_PASS language=python", flush=True)

    print("PERF004A2_BUILD_BEGIN language=javascript", flush=True)
    run(
        [
            "docker", "build", "--pull",
            "--build-arg", "NODE_BASE=" + cfg["comparison_runtimes"]["javascript"]["base"],
            "-t", tags["javascript"],
            "-f", "docker/node-perf004a/Dockerfile",
            ".",
        ]
    )
    print("PERF004A2_BUILD_PASS language=javascript", flush=True)
    return tags


def docker_command(cpu: str, image: str, *args: str) -> list[str]:
    return [
        "docker", "run", "--rm",
        "--network", "none",
        "--cpuset-cpus", cpu,
        image,
        *args,
    ]


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


def image_identity(tag: str) -> dict[str, Any]:
    data = json.loads(output(["docker", "image", "inspect", tag]))[0]
    return {
        "tag": tag,
        "id": data.get("Id", ""),
        "repo_digests": data.get("RepoDigests") or [],
    }


def protos_runtime_probe(cfg: dict[str, Any], tag: str, cpu: str) -> str:
    reused = cfg["protos_driver_reuse"]
    completed = docker_java(
        tag,
        cpu,
        f"{reused['probe_dir']}:/opt/protos/lib/protos.jar:{reused['runtime_dir']}/*",
        reused["runtime_probe"],
        stack=False,
    )
    observed = ""
    for line in (completed.stdout or "").splitlines():
        if line.startswith("PERF006D_RUNTIME="):
            observed = line.split("=", 1)[1].strip()
    if observed != EXPECTED_OPTIMIZER:
        raise RuntimeError(
            f"Protos runtime mismatch expected={EXPECTED_OPTIMIZER!r} observed={observed!r}"
        )
    if FALLBACK_WARNING_RE.search(completed.stderr or ""):
        raise RuntimeError("optimizing Protos runtime emitted fallback warning")
    return observed


def host_workload_path(language: str, entry: dict[str, Any]) -> str:
    return f"/opt/benchmark/workloads/{entry[language]}"


def protos_source_path(cfg: dict[str, Any], entry: dict[str, Any]) -> str:
    return cfg["protos_driver_reuse"]["corpus_dir"] + "/" + entry["protos"]


def correctness_case(
    cfg: dict[str, Any],
    tags: dict[str, str],
    cpu: str,
    language: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    if language == "protos":
        payload, stderr = persistent_fork(
            cfg, tags, cpu, language, entry, warmup=0, steady=1
        )
        if FALLBACK_WARNING_RE.search(stderr):
            raise RuntimeError(f"optimizer correctness emitted fallback warning: {entry['id']}")
        return {
            "language": language,
            "workload": entry["id"],
            "expected": entry["expected"],
            "observed": entry["expected"],
            "runtime": payload["runtime"],
        }

    completed = run(
        docker_command(cpu, tags[language], host_workload_path(language, entry)),
        capture=True,
        check=False,
    )
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    observed = lines[-1] if lines else ""
    if completed.returncode != 0 or observed != entry["expected"]:
        raise RuntimeError(
            f"correctness failed language={language} workload={entry['id']} "
            f"exit={completed.returncode} expected={entry['expected']!r} observed={observed!r}\n"
            f"stderr:\n{(completed.stderr or '')[-4000:]}"
        )
    return {
        "language": language,
        "workload": entry["id"],
        "expected": entry["expected"],
        "observed": observed,
    }


def startup_series(
    cfg: dict[str, Any],
    tags: dict[str, str],
    cpu: str,
    language: str,
    entry: dict[str, Any],
    samples: int,
) -> tuple[dict[str, Any], str]:
    if language == "protos":
        reused = cfg["protos_driver_reuse"]
        completed = docker_java(
            tags["protos"],
            cpu,
            reused["timing_dir"],
            reused["startup_controller"],
            reused["runtime_dir"],
            EXPECTED_OPTIMIZER,
            protos_source_path(cfg, entry),
            entry["expected"],
            str(samples),
            "180",
            stack=False,
        )
        command = None
    elif language == "python":
        command = docker_command(
            cpu,
            tags["python"],
            "/opt/benchmark/timing_driver.py",
            "startup",
            host_workload_path(language, entry),
            entry["expected"],
            str(samples),
        )
    elif language == "javascript":
        command = docker_command(
            cpu,
            tags["javascript"],
            "/opt/benchmark/timing_driver.mjs",
            "startup",
            host_workload_path(language, entry),
            entry["expected"],
            str(samples),
        )
    else:
        raise ValueError("unknown language: " + language)

    if language != "protos":
        completed = run(command, capture=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"startup failed language={language} workload={entry['id']} "
                f"exit={completed.returncode}\nstdout:\n{(completed.stdout or '')[-6000:]}\n"
                f"stderr:\n{(completed.stderr or '')[-6000:]}"
            )
    payload = parse_json_last_line(completed.stdout or "", f"{language} startup")
    if payload.get("expected") != entry["expected"]:
        raise RuntimeError("startup expected-result identity mismatch")
    values = payload.get("startup_ns")
    if not isinstance(values, list) or len(values) != samples:
        raise RuntimeError("startup sample-count mismatch")
    if any(not isinstance(value, int) or value <= 0 for value in values):
        raise RuntimeError("startup contains non-positive sample")
    flag = "fresh_jvm_per_sample" if language == "protos" else "fresh_process_per_sample"
    if payload.get(flag) is not True or payload.get("docker_start_outside_timing") is not True:
        raise RuntimeError("startup boundary contract failed")
    if language == "protos":
        if payload.get("runtime") != EXPECTED_OPTIMIZER:
            raise RuntimeError("startup optimizer runtime identity mismatch")
        if FALLBACK_WARNING_RE.search(completed.stderr or ""):
            raise RuntimeError("optimizer startup emitted fallback warning")
    return payload, completed.stderr or ""


def persistent_fork(
    cfg: dict[str, Any],
    tags: dict[str, str],
    cpu: str,
    language: str,
    entry: dict[str, Any],
    *,
    warmup: int,
    steady: int,
) -> tuple[dict[str, Any], str]:
    if language == "protos":
        reused = cfg["protos_driver_reuse"]
        completed = docker_java(
            tags["protos"],
            cpu,
            f"{reused['timing_dir']}:/opt/protos/lib/protos.jar:{reused['runtime_dir']}/*",
            reused["persistent_driver"],
            protos_source_path(cfg, entry),
            entry["expected"],
            str(warmup),
            str(steady),
            stack=True,
        )
        command = None
    elif language == "python":
        command = docker_command(
            cpu,
            tags["python"],
            "/opt/benchmark/timing_driver.py",
            "execution",
            host_workload_path(language, entry),
            entry["expected"],
            str(warmup),
            str(steady),
        )
    elif language == "javascript":
        command = docker_command(
            cpu,
            tags["javascript"],
            "/opt/benchmark/timing_driver.mjs",
            "execution",
            host_workload_path(language, entry),
            entry["expected"],
            str(warmup),
            str(steady),
        )
    else:
        raise ValueError("unknown language: " + language)

    if language != "protos":
        completed = run(command, capture=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"persistent fork failed language={language} workload={entry['id']} "
                f"exit={completed.returncode}\nstdout:\n{(completed.stdout or '')[-6000:]}\n"
                f"stderr:\n{(completed.stderr or '')[-6000:]}"
            )
    payload = parse_json_last_line(completed.stdout or "", f"{language} persistent")
    if payload.get("expected") != entry["expected"]:
        raise RuntimeError("persistent expected-result identity mismatch")
    warmup_ns = payload.get("warmup_ns")
    steady_ns = payload.get("steady_ns")
    if not isinstance(warmup_ns, list) or len(warmup_ns) != warmup:
        raise RuntimeError("persistent warmup count mismatch")
    if not isinstance(steady_ns, list) or len(steady_ns) != steady:
        raise RuntimeError("persistent steady count mismatch")
    if any(
        not isinstance(value, int) or value <= 0
        for value in list(warmup_ns) + list(steady_ns)
    ):
        raise RuntimeError("persistent driver emitted non-positive sample")

    if language == "protos":
        if payload.get("runtime") != EXPECTED_OPTIMIZER:
            raise RuntimeError("persistent optimizer runtime identity mismatch")
        for flag in (
            "source_reused",
            "process_reused",
            "context_reused",
            "fresh_activation_per_iteration",
        ):
            if payload.get(flag) is not True:
                raise RuntimeError("Protos persistent hosting contract failed: " + flag)
        if FALLBACK_WARNING_RE.search(completed.stderr or ""):
            raise RuntimeError("optimizer persistent fork emitted fallback warning")
    else:
        for flag in ("module_reused", "run_binding_reused"):
            if payload.get(flag) is not True:
                raise RuntimeError(f"{language} persistent hosting contract failed: {flag}")
    return payload, completed.stderr or ""


def summary(values: list[int]) -> dict[str, float | int]:
    if not values:
        raise ValueError("cannot summarize an empty timing sample")
    if any(not isinstance(value, int) or value <= 0 for value in values):
        raise ValueError("timing samples must be positive integers")
    ordered = sorted(values)
    median = float(statistics.median(ordered))
    deviations = [abs(float(value) - median) for value in ordered]
    p95_index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return {
        "count": len(ordered),
        "median_ns": median,
        "mad_ns": float(statistics.median(deviations)),
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
    memory_bytes = None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                memory_bytes = int(line.split()[1]) * 1024
                break
    return {
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "cpu_model": cpu_model,
        "cpu_count": os.cpu_count() or 1,
        "memory_bytes": memory_bytes,
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
    tags = build_images(cfg)
    runtime = protos_runtime_probe(cfg, tags["protos"], cpu)
    entries = workload_entries(cfg)
    smoke_cfg = cfg["a2_smoke"]
    entry = next(item for item in entries if item["id"] == smoke_cfg["workload"])

    cases: dict[str, Any] = {}
    correctness: list[dict[str, Any]] = []
    for language in cfg["comparison_languages"]:
        correctness.append(correctness_case(cfg, tags, cpu, language, entry))
        startup, _ = startup_series(
            cfg,
            tags,
            cpu,
            language,
            entry,
            int(smoke_cfg["startup_samples_per_language"]),
        )
        forks = []
        for _fork in range(int(smoke_cfg["persistent_forks_per_language"])):
            persistent, _ = persistent_fork(
                cfg,
                tags,
                cpu,
                language,
                entry,
                warmup=int(smoke_cfg["warmup_iterations_per_fork"]),
                steady=int(smoke_cfg["steady_samples_per_fork"]),
            )
            forks.append(persistent)
        cases[language] = {"startup": startup, "persistent_forks": forks}

    work = ROOT / ".work"
    work.mkdir(parents=True, exist_ok=True)
    path = work / "perf004-a2-timing-smoke.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "perf_item": "PERF004",
                "slice": "PERF004-A2",
                "retained": False,
                "timing_claim": False,
                "protos_revision": cfg["protos_revision"],
                "cpu": cpu,
                "protos_runtime": runtime,
                "images": {name: image_identity(tag) for name, tag in tags.items()},
                "correctness": correctness,
                "workload": entry["id"],
                "cases": cases,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print("PERF004A2_RUNTIME_IDENTITY=PASS")
    print("PERF004A2_CORRECTNESS=PASS 3/3")
    print("PERF004A2_TIMING_SMOKE=PASS")
    print("PERF004A2_RETAINED_TIMING=NO")
    print("PERF004A2_TIMING_CLAIM=NO")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_summary_tsv(path: Path, summaries: list[dict[str, Any]]) -> None:
    columns = [
        "workload", "language", "phase", "count", "median_ns", "mad_ns",
        "p95_ns", "min_ns", "max_ns",
    ]
    lines = ["\t".join(columns)]
    for item in summaries:
        for phase in ("startup", "warmup", "steady"):
            value = item[phase]
            lines.append(
                "\t".join(
                    [
                        item["workload"],
                        item["language"],
                        phase,
                        str(value["count"]),
                        str(value["median_ns"]),
                        str(value["mad_ns"]),
                        str(value["p95_ns"]),
                        str(value["min_ns"]),
                        str(value["max_ns"]),
                    ]
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def reference(harness_revision: str, output_dir: Path) -> None:
    cfg = validate()
    require_clean_exact_harness(harness_revision)
    expected_output = Path(cfg["reference_output"])
    if output_dir != expected_output:
        raise RuntimeError(f"reference output must be {expected_output}, got {output_dir}")
    if output_dir.exists():
        raise RuntimeError("reference output already exists: " + str(output_dir))

    cpu = first_allowed_cpu()
    tags = build_images(cfg)
    runtime = protos_runtime_probe(cfg, tags["protos"], cpu)
    entries = workload_entries(cfg)

    correctness: list[dict[str, Any]] = []
    for entry in entries:
        for language in cfg["comparison_languages"]:
            correctness.append(correctness_case(cfg, tags, cpu, language, entry))
            print(f"CORRECTNESS PASS language={language} workload={entry['id']}", flush=True)

    policy = cfg["measurement_contract"]
    startup_count = int(policy["startup_process_samples_per_language_workload"])
    forks_count = int(policy["persistent_forks_per_language_workload"])
    warmup_count = int(policy["warmup_iterations_per_fork"])
    steady_count = int(policy["steady_samples_per_fork"])

    raw_cases: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    ratios: list[dict[str, Any]] = []

    for entry in entries:
        by_language: dict[str, dict[str, Any]] = {}
        for language in cfg["comparison_languages"]:
            print(
                f"MEASURE BEGIN language={language} workload={entry['id']} "
                f"startup={startup_count} forks={forks_count} "
                f"warmup={warmup_count} steady={steady_count}",
                flush=True,
            )
            startup, _ = startup_series(
                cfg, tags, cpu, language, entry, startup_count
            )
            warmup_forks: list[list[int]] = []
            steady_forks: list[list[int]] = []
            persistent_forks: list[dict[str, Any]] = []
            for fork in range(forks_count):
                payload, _ = persistent_fork(
                    cfg,
                    tags,
                    cpu,
                    language,
                    entry,
                    warmup=warmup_count,
                    steady=steady_count,
                )
                warm_values = [int(value) for value in payload["warmup_ns"]]
                steady_values = [int(value) for value in payload["steady_ns"]]
                warmup_forks.append(warm_values)
                steady_forks.append(steady_values)
                persistent_forks.append(
                    {
                        "fork": fork + 1,
                        "warmup_ns": warm_values,
                        "steady_ns": steady_values,
                    }
                )
                print(
                    f"MEASURE FORK PASS language={language} workload={entry['id']} "
                    f"fork={fork + 1}/{forks_count}",
                    flush=True,
                )

            startup_values = [int(value) for value in startup["startup_ns"]]
            warmup_values = [value for fork in warmup_forks for value in fork]
            steady_values = [value for fork in steady_forks for value in fork]
            item_summary = {
                "workload": entry["id"],
                "language": language,
                "startup": summary(startup_values),
                "warmup": summary(warmup_values),
                "steady": summary(steady_values),
                "warmup_iteration_median_ns": per_iteration_medians(warmup_forks),
                "steady_iteration_median_ns": per_iteration_medians(steady_forks),
            }
            summaries.append(item_summary)
            by_language[language] = item_summary
            raw_cases.append(
                {
                    "workload": entry["id"],
                    "language": language,
                    "expected": entry["expected"],
                    "source_blob_sha": entry["source_blob_sha"],
                    "equivalence": entry["equivalence"],
                    "startup_ns": startup_values,
                    "persistent_forks": persistent_forks,
                }
            )
            print(f"MEASURE PASS language={language} workload={entry['id']}", flush=True)

        protos = by_language["protos"]
        ratio_item: dict[str, Any] = {
            "workload": entry["id"],
            "ratio_definition": "protos_median_ns / comparison_median_ns",
            "comparisons": {},
        }
        for language in ("python", "javascript"):
            other = by_language[language]
            ratio_item["comparisons"][language] = {
                phase: protos[phase]["median_ns"] / other[phase]["median_ns"]
                for phase in ("startup", "warmup", "steady")
            }
        ratios.append(ratio_item)

    output_dir.mkdir(parents=True)

    metadata = {
        "schema_version": 1,
        "perf_item": "PERF004",
        "slice": "PERF004-A",
        "phase": "retained-cross-language-baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "protos_implementation_version": cfg["protos_implementation_version"],
        "equivalence_source_revision": cfg["equivalence_source_revision"],
        "toolchain": cfg["toolchain"],
        "comparison_runtimes": cfg["comparison_runtimes"],
        "protos_runtime": runtime,
        "host": host_inventory(cpu),
        "images": {name: image_identity(tag) for name, tag in tags.items()},
        "measurement_policy": policy,
        "correctness_cases": len(correctness),
        "timing_diagnostics": False,
    }
    raw_payload = {
        "schema_version": 1,
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "cases": raw_cases,
    }
    summary_payload = {
        "schema_version": 1,
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "primary_statistic": policy["primary_statistic"],
        "dispersion": policy["dispersion"],
        "summaries": summaries,
        "ratios": ratios,
        "interpretation_policy": {
            "ratio_definition": "protos_median_ns / comparison_median_ns",
            "ratio_above_1": "Protos median duration is larger for that exact workload and phase",
            "ratio_below_1": "Protos median duration is smaller for that exact workload and phase",
            "materiality_classification_deferred_to": "PERF004-B",
            "whole_language_generalization": False,
        },
    }

    metadata_path = output_dir / "run-metadata.json"
    raw_path = output_dir / "raw.json"
    summary_path = output_dir / "summary.json"
    tsv_path = output_dir / "summary.tsv"
    readme_path = output_dir / "README.md"

    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raw_path.write_text(json.dumps(raw_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary_tsv(tsv_path, summaries)

    readme_lines = [
        "# PERF004-A retained cross-language baseline",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision: `{cfg['protos_revision']}`",
        f"- Protos implementation: `{cfg['protos_implementation_version']}`",
        "- Languages: Protos, Python, JavaScript.",
        "- Classification: algorithm-equivalent.",
        f"- Correctness: PASS {len(correctness)}/{len(correctness)}.",
        f"- Startup: {startup_count} fresh language-process samples per language/workload.",
        f"- Persistent forks: {forks_count} per language/workload.",
        f"- Warmup: {warmup_count} iterations per fork.",
        f"- Steady state: {steady_count} samples per fork.",
        "- Docker creation/start is excluded from startup timing.",
        "- Heavy compiler diagnostics are excluded from reference timing.",
        "- Ratio definition in summary.json: Protos median duration / comparison median duration.",
        "- Material-gap classification is deferred to PERF004-B.",
        "- No row is generalized into a whole-language performance claim.",
        "",
        "Raw ordered samples are authoritative in `raw.json`; `summary.json` and",
        "`summary.tsv` are derived views.",
        "",
    ]
    readme_path.write_text("\n".join(readme_lines), encoding="utf-8")

    names = [
        "README.md",
        "raw.json",
        "run-metadata.json",
        "summary.json",
        "summary.tsv",
    ]
    (output_dir / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(output_dir / name)}  {name}\n" for name in sorted(names)),
        encoding="utf-8",
    )

    print("PERF004A_REFERENCE=PASS")
    print(f"PERF004A_CORRECTNESS_CASES={len(correctness)}")
    print(f"PERF004A_STARTUP_SAMPLES_PER_LANGUAGE_WORKLOAD={startup_count}")
    print(f"PERF004A_PERSISTENT_FORKS_PER_LANGUAGE_WORKLOAD={forks_count}")
    print(f"PERF004A_WARMUP_ITERATIONS_PER_FORK={warmup_count}")
    print(f"PERF004A_STEADY_SAMPLES_PER_FORK={steady_count}")
    print("PERF004A_OUTPUT=" + str(output_dir))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PERF004-A cross-language baseline benchmark harness"
    )
    parser.add_argument("command", choices=("validate", "smoke", "reference"))
    parser.add_argument("--harness-revision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    try:
        if args.command == "validate":
            validate()
            return 0
        if args.command == "smoke":
            timing_smoke()
            return 0
        if not args.harness_revision:
            parser.error("reference requires --harness-revision")
        if not args.output_dir:
            parser.error("reference requires --output-dir")
        reference(args.harness_revision, Path(args.output_dir))
        return 0
    except KeyboardInterrupt:
        print("PERF004-A interrupted", file=os.sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"PERF004-A error: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
