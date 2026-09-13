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
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf006d3.json"
D2_EVIDENCE = "7e3c2a9554d7ac48d30e74572460e14aaecb8fec"
D2_HARNESS = "1a752e92569b4ed42d3f9f55f67d1a7447eae308"
EXPECTED_PROTOS_REVISION = "4a03efc15620b37b2e418b3df30b4a26486446ec"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
FALLBACK_WARNING_RE = re.compile(
    r"No optimizing Truffle runtime found|fallback runtime that does not support runtime compilation|"
    r"does not support runtime compilation to native code|executed in interpreted mode only",
    re.IGNORECASE,
)
TRACE_DONE_RE = re.compile(r"\bopt done\b", re.IGNORECASE)
TRACE_FAILED_RE = re.compile(r"\bopt fail(?:ed)?\b|CompilationFailure", re.IGNORECASE)
TRACE_BAILOUT_RE = re.compile(r"Bailout|bailout", re.IGNORECASE)
TRACE_INVALIDATED_RE = re.compile(r"invalidat", re.IGNORECASE)


def run(command: list[str], *, cwd: Path = ROOT, capture: bool = False, check: bool = True,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=env,
    )


def checked(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    completed = run(command, cwd=cwd, capture=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "command failed: " + " ".join(command)
            + "\nstdout:\n" + (completed.stdout or "")[-8000:]
            + "\nstderr:\n" + (completed.stderr or "")[-8000:]
        )
    return completed


def output(command: list[str], *, cwd: Path = ROOT) -> str:
    return (checked(command, cwd=cwd).stdout or "").strip()


def config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    cfg = config()
    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF006"
    assert cfg["slice"] == "PERF006-D3A"
    assert cfg["phase"] == "structural-diagnostics-harness-ready"
    assert cfg["diagnostic_claim"] is False
    assert cfg["d2_evidence_revision"] == D2_EVIDENCE
    assert cfg["d2_harness_revision"] == D2_HARNESS
    assert cfg["protos_revision"] == EXPECTED_PROTOS_REVISION
    assert cfg["protos_implementation_version"] == "0.2.492-SNAPSHOT"

    historical = cfg["historical_pre_c_prime"]
    assert historical["classification"] == "historical_pre_C_prime_not_absolute_performance_comparator"
    assert historical["wall_seconds_approx"] == 471.985
    assert historical["execution_samples"] == 44568
    assert historical["hashmap_keyiterator_next_samples"] == 41092
    assert historical["hashmap_keyiterator_next_percent"] == 92.201
    assert historical["main_thread_samples"] == 43913
    assert historical["main_thread_percent"] == 98.530
    assert historical["jdk_deoptimization_events"] == 1824883
    assert historical["truffle_deoptimization_events"] == 1824544
    assert historical["hotspot"] == "ProtosEvaluatorContinuation.compactCompletedChildExecution"
    assert historical["hotspot_operation"] == "invocationActivations.keySet().removeIf(...)"

    current = cfg["current_diagnostic_contract"]
    assert current["real_workload"] == "bin/protos test --jobs 2"
    assert current["execution_sample_period"] == "10 ms"
    assert current["standard_deoptimization_event"] == "jdk.Deoptimization"
    assert current["truffle_deoptimization_event"] == "jdk.graal.compiler.truffle.Deoptimization"
    assert current["bounded_trace_workload"] == "micro/method-call.protos"
    assert current["bounded_trace_expected"] == "42"
    assert current["bounded_trace_warmup"] == 20
    assert current["bounded_trace_steady"] == 20
    assert current["trace_compilation"] is True
    assert current["trace_compilation_details"] is False
    assert current["compilation_failure_action"] == "Print"
    assert current["reference_timing_changed"] is False
    assert current["production_optimization_allowed"] is False
    assert current["igv24_analyzer_used"] is False

    smoke = cfg["d3a_smoke"]
    assert smoke["jfr_workload"] == "micro/method-call.protos"
    assert smoke["jfr_expected"] == "42"
    assert smoke["jfr_warmup"] == 20
    assert smoke["jfr_steady"] == 20
    assert smoke["retained"] is False
    assert smoke["diagnostic_claim"] is False
    assert cfg["d3b_output"] == "results/perf006-d3"

    dockerfile = (ROOT / "docker/protos-perf006d3/Dockerfile").read_text(encoding="utf-8")
    for required in (
        "jdk.ExecutionSample#period=10ms",
        "jdk.Deoptimization#enabled=true",
        "+jdk.graal.compiler.truffle.Deoptimization#enabled=true",
        "/opt/protos-source",
        "Perf006d3JfrAnalyzer.java",
    ):
        assert required in dockerfile

    wrapper = (ROOT / "docker/protos-perf006d3/jfr-java").read_text(encoding="utf-8")
    assert "StartFlightRecording" in wrapper
    assert "PERF006D3_JFR_FILE" in wrapper
    assert "perf006d3.jfc" in wrapper

    analyzer = (ROOT / "docker/protos-perf006d3/Perf006d3JfrAnalyzer.java").read_text(
        encoding="utf-8"
    )
    for required in (
        "jdk.ExecutionSample",
        "jdk.Deoptimization",
        "jdk.graal.compiler.truffle.Deoptimization",
        "java.util.HashMap$KeyIterator.next",
        "RecordingFile",
    ):
        assert required in analyzer

    d2_summary = json.loads((ROOT / "results/perf006-d2/summary.json").read_text(encoding="utf-8"))
    assert d2_summary["harness_revision"] == D2_HARNESS
    assert d2_summary["protos_revision"] == EXPECTED_PROTOS_REVISION
    assert d2_summary["interpretation_policy"]["full_suite_20_to_8_minute_observation_used_as_claim"] is False

    print("PERF006D3A_CONFIG=PASS")
    print("PERF006D3A_D2_PREREQUISITE=PASS")
    print("PERF006D3A_HISTORICAL_BASELINE_CLASSIFICATION=PASS")
    print("PERF006D3A_CURRENT_TOOLCHAIN_PROFILE=PASS")
    print("PERF006D3A_DIAGNOSTIC_CLAIM=NO")
    print("PERF006D3A_IGV24_ANALYZER_USED=NO")
    return cfg


def image_tag(cfg: dict[str, Any]) -> str:
    return "protos-benchmarks-perf006d3:" + cfg["protos_revision"][:12]


def build_image(cfg: dict[str, Any]) -> str:
    tag = image_tag(cfg)
    print("PERF006D3_IMAGE_BUILD_BEGIN")
    run(
        [
            "docker", "build",
            "--build-arg", "GRAAL_BASE=" + cfg["toolchain"]["container_image"],
            "--build-arg", "MAVEN_VERSION=" + cfg["toolchain"]["maven_version"],
            "--build-arg", "PROTOS_REPOSITORY=" + cfg["protos_repository"],
            "--build-arg", "PROTOS_REVISION=" + cfg["protos_revision"],
            "--label", "org.opencontainers.image.revision=" + cfg["protos_revision"],
            "-t", tag,
            "-f", "docker/protos-perf006d3/Dockerfile",
            ".",
        ]
    )
    print("PERF006D3_IMAGE_BUILD=PASS")
    return tag


def parse_cpu_list(text: str) -> list[int]:
    result: set[int] = set()
    for item in text.strip().split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start, end = item.split("-", 1)
            result.update(range(int(start), int(end) + 1))
        else:
            result.add(int(item))
    return sorted(result)


def allowed_cpus() -> list[int]:
    status = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Cpus_allowed_list:\s*(.+)$", status, re.M)
    if not match:
        raise RuntimeError("cannot determine Cpus_allowed_list")
    return parse_cpu_list(match.group(1))


def physical_core_cpuset(width: int) -> str:
    allowed = set(allowed_cpus())
    representatives: dict[tuple[int, int], int] = {}
    for cpu in sorted(allowed):
        topology = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        package = int((topology / "physical_package_id").read_text().strip())
        core = int((topology / "core_id").read_text().strip())
        representatives.setdefault((package, core), cpu)
    ordered = [cpu for _, cpu in sorted(representatives.items())]
    if len(ordered) < width:
        raise RuntimeError(f"need {width} distinct physical cores, found {len(ordered)}")
    return ",".join(str(cpu) for cpu in ordered[:width])


def runtime_probe(tag: str, cpuset: str) -> str:
    completed = checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpuset,
            "--entrypoint", "java", tag,
            "--enable-native-access=ALL-UNNAMED",
            "-cp", "/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
            "Perf006dRuntimeProbe",
        ]
    )
    observed = ""
    for line in (completed.stdout or "").splitlines():
        if line.startswith("PERF006D_RUNTIME="):
            observed = line.split("=", 1)[1].strip()
            break
    if observed != EXPECTED_RUNTIME:
        raise RuntimeError(f"runtime mismatch: expected={EXPECTED_RUNTIME} observed={observed}")
    if FALLBACK_WARNING_RE.search(completed.stderr or ""):
        raise RuntimeError("optimizer runtime probe emitted fallback warning")
    return observed


def run_persistent_jfr_smoke(tag: str, cpuset: str, cfg: dict[str, Any], work: Path) -> dict[str, Any]:
    smoke = cfg["d3a_smoke"]
    recording = work / "smoke.jfr"
    analysis = work / "smoke-analysis.json"
    classpath = "/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*"
    jfr_arg = (
        "-XX:StartFlightRecording=filename=/work/smoke.jfr,"
        "settings=/opt/perf006d3/perf006d3.jfc,dumponexit=true"
    )
    completed = checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpuset,
            "--volume", f"{work.resolve()}:/work",
            "--entrypoint", "java", tag,
            "-Xss128m",
            jfr_arg,
            "--enable-native-access=ALL-UNNAMED",
            "-cp", classpath,
            "Perf006dPersistentDriver",
            "/opt/perf006d3/corpus/" + smoke["jfr_workload"],
            smoke["jfr_expected"],
            str(smoke["jfr_warmup"]),
            str(smoke["jfr_steady"]),
        ]
    )
    if FALLBACK_WARNING_RE.search(completed.stderr or ""):
        raise RuntimeError("JFR smoke emitted fallback warning")
    if not recording.is_file() or recording.stat().st_size <= 0:
        raise RuntimeError("JFR smoke did not produce a recording")

    checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--volume", f"{work.resolve()}:/work",
            "--entrypoint", "java", tag,
            "--add-modules", "jdk.jfr",
            "-cp", "/opt/perf006d3/analyzer",
            "Perf006d3JfrAnalyzer",
            "/work/smoke.jfr",
            "/work/smoke-analysis.json",
        ]
    )
    payload = json.loads(analysis.read_text(encoding="utf-8"))
    if payload["execution_samples"]["total"] <= 0:
        raise RuntimeError("JFR smoke recorded no execution samples")
    if payload["event_type_available"]["jdk.ExecutionSample"] is not True:
        raise RuntimeError("JFR smoke lacks jdk.ExecutionSample event type")
    if payload["event_type_available"]["jdk.Deoptimization"] is not True:
        raise RuntimeError("JFR smoke lacks jdk.Deoptimization event type")
    return payload


def trace_compilation_smoke(tag: str, cpuset: str, cfg: dict[str, Any]) -> dict[str, Any]:
    current = cfg["current_diagnostic_contract"]
    classpath = "/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*"
    completed = checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpuset,
            "--entrypoint", "java", tag,
            "-Xss128m",
            "-Dpolyglot.engine.TraceCompilation=true",
            "-Dpolyglot.engine.CompilationFailureAction=Print",
            "--enable-native-access=ALL-UNNAMED",
            "-cp", classpath,
            "Perf006dPersistentDriver",
            "/opt/perf006d3/corpus/" + current["bounded_trace_workload"],
            current["bounded_trace_expected"],
            str(current["bounded_trace_warmup"]),
            str(current["bounded_trace_steady"]),
        ]
    )
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if FALLBACK_WARNING_RE.search(text):
        raise RuntimeError("TraceCompilation smoke emitted fallback warning")
    done = len(TRACE_DONE_RE.findall(text))
    failed = len(TRACE_FAILED_RE.findall(text))
    bailouts = len(TRACE_BAILOUT_RE.findall(text))
    invalidated = len(TRACE_INVALIDATED_RE.findall(text))
    if done <= 0:
        raise RuntimeError(
            "TraceCompilation smoke observed no successful compilation; "
            "do not publish D3A without proving compilation on the bounded workload"
        )
    return {
        "successful_compilations": done,
        "failed_compilation_markers": failed,
        "bailout_markers": bailouts,
        "invalidation_markers": invalidated,
    }


def smoke() -> None:
    cfg = validate()
    tag = build_image(cfg)
    cpuset = physical_core_cpuset(1)
    runtime = runtime_probe(tag, cpuset)
    with tempfile.TemporaryDirectory(prefix="perf006-d3a-smoke-") as tmp:
        work = Path(tmp)
        jfr = run_persistent_jfr_smoke(tag, cpuset, cfg, work)
        trace = trace_compilation_smoke(tag, cpuset, cfg)

    print("PERF006D3A_OPTIMIZING_RUNTIME=" + runtime)
    print("PERF006D3A_JFR_EXECUTION_SAMPLES=" + str(jfr["execution_samples"]["total"]))
    print(
        "PERF006D3A_TRUFFLE_DEOPT_EVENT_AVAILABLE="
        + str(jfr["event_type_available"]["jdk.graal.compiler.truffle.Deoptimization"]).upper()
    )
    print("PERF006D3A_TRACE_SUCCESSFUL_COMPILATIONS=" + str(trace["successful_compilations"]))
    print("PERF006D3A_JFR_SMOKE=PASS")
    print("PERF006D3A_TRACE_COMPILATION_SMOKE=PASS")
    print("PERF006D3A_SMOKE_RETAINED=NO")
    print("PERF006D3A_DIAGNOSTIC_CLAIM=NO")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def static_replay_audit(tag: str) -> dict[str, Any]:
    script = r"""
set -eu
cd /opt/protos-source
compact=$(git grep -n -F 'compactCompletedChildExecution' -- . || true)
removeif=$(git grep -n -F 'invocationActivations.keySet().removeIf' -- . || true)
printf 'COMPACT<<EOF\n%s\nEOF\n' "$compact"
printf 'REMOVEIF<<EOF\n%s\nEOF\n' "$removeif"
"""
    completed = checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--entrypoint", "/bin/sh", tag, "-c", script,
        ]
    )
    text = completed.stdout or ""
    compact = text.split("COMPACT<<EOF\n", 1)[1].split("\nEOF\n", 1)[0].strip()
    removeif = text.split("REMOVEIF<<EOF\n", 1)[1].split("\nEOF\n", 1)[0].strip()
    return {
        "compactCompletedChildExecution_present": bool(compact),
        "compactCompletedChildExecution_matches": compact.splitlines() if compact else [],
        "invocationActivations_keySet_removeIf_present": bool(removeif),
        "invocationActivations_keySet_removeIf_matches": removeif.splitlines() if removeif else [],
    }


def full_reference(harness_revision: str, output_dir: Path) -> None:
    cfg = validate()
    head = output(["git", "rev-parse", "HEAD"])
    if head != harness_revision:
        raise RuntimeError(f"D3 reference requires exact harness HEAD={harness_revision}, got {head}")
    dirty = output(["git", "status", "--porcelain", "--untracked-files=all"])
    if dirty:
        raise RuntimeError("D3 reference requires a clean exact harness worktree")
    expected_output = Path(cfg["d3b_output"])
    if output_dir != expected_output:
        raise RuntimeError(f"D3 output must be {expected_output}, got {output_dir}")
    if output_dir.exists():
        raise RuntimeError("D3 output already exists: " + str(output_dir))

    tag = build_image(cfg)
    cpuset = physical_core_cpuset(2)
    runtime = runtime_probe(tag, cpuset.split(",")[0])
    if runtime != EXPECTED_RUNTIME:
        raise RuntimeError("D3 reference runtime identity failure")

    output_dir.mkdir(parents=True)
    recording = output_dir / "test-tool-current.jfr"
    stdout_path = output_dir / "test-tool.stdout"
    stderr_path = output_dir / "test-tool.stderr"

    command = [
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpuset,
        "--volume", f"{output_dir.resolve()}:/work",
        "--env", "PROTOS_JAVA=/opt/perf006d3/jfr-java",
        "--env", "PERF006D3_JFR_FILE=/work/test-tool-current.jfr",
        "--entrypoint", "/opt/protos/bin/protos",
        tag,
        "test", "--jobs", "2",
    ]
    started = time.monotonic_ns()
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        completed = subprocess.run(command, cwd=ROOT, text=True, stdout=out, stderr=err)
    wall_ns = time.monotonic_ns() - started
    if completed.returncode != 0:
        raise RuntimeError(
            "current Test Tool diagnostic run failed exit="
            + str(completed.returncode)
            + "\nstderr:\n"
            + stderr_path.read_text(encoding="utf-8", errors="replace")[-10000:]
        )
    if not recording.is_file() or recording.stat().st_size <= 0:
        raise RuntimeError("current Test Tool diagnostic run produced no JFR recording")

    current_profile = output_dir / "current-profile.json"
    checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--volume", f"{output_dir.resolve()}:/work",
            "--entrypoint", "java", tag,
            "--add-modules", "jdk.jfr",
            "-cp", "/opt/perf006d3/analyzer",
            "Perf006d3JfrAnalyzer",
            "/work/test-tool-current.jfr",
            "/work/current-profile.json",
        ]
    )
    profile = json.loads(current_profile.read_text(encoding="utf-8"))
    if profile["execution_samples"]["total"] <= 0:
        raise RuntimeError("full D3 JFR contains no execution samples")

    jfr_summary = checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--volume", f"{output_dir.resolve()}:/work",
            "--entrypoint", "jfr", tag,
            "summary", "/work/test-tool-current.jfr",
        ]
    )
    (output_dir / "jfr-summary.txt").write_text(jfr_summary.stdout or "", encoding="utf-8")

    static_audit = static_replay_audit(tag)

    current = cfg["current_diagnostic_contract"]
    classpath = "/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*"
    trace_completed = checked(
        [
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpuset.split(",")[0],
            "--entrypoint", "java", tag,
            "-Xss128m",
            "-Dpolyglot.engine.TraceCompilation=true",
            "-Dpolyglot.engine.CompilationFailureAction=Print",
            "--enable-native-access=ALL-UNNAMED",
            "-cp", classpath,
            "Perf006dPersistentDriver",
            "/opt/perf006d3/corpus/" + current["bounded_trace_workload"],
            current["bounded_trace_expected"],
            str(current["bounded_trace_warmup"]),
            str(current["bounded_trace_steady"]),
        ]
    )
    trace_text = (trace_completed.stdout or "") + "\n" + (trace_completed.stderr or "")
    if FALLBACK_WARNING_RE.search(trace_text):
        raise RuntimeError("D3 bounded TraceCompilation run emitted fallback warning")
    trace_path = output_dir / "trace-compilation.log"
    trace_path.write_text(trace_text, encoding="utf-8")
    trace = {
        "workload": current["bounded_trace_workload"],
        "expected": current["bounded_trace_expected"],
        "successful_compilations": len(TRACE_DONE_RE.findall(trace_text)),
        "failed_compilation_markers": len(TRACE_FAILED_RE.findall(trace_text)),
        "bailout_markers": len(TRACE_BAILOUT_RE.findall(trace_text)),
        "invalidation_markers": len(TRACE_INVALIDATED_RE.findall(trace_text)),
    }
    if trace["successful_compilations"] <= 0:
        raise RuntimeError("D3 bounded trace shows no successful guest compilation")

    # Binary JFR is analyzed before removal. Retain its identity and textual summary,
    # not the potentially large binary recording itself.
    jfr_identity = {
        "sha256": sha256(recording),
        "size_bytes": recording.stat().st_size,
        "retained_in_git": False,
        "retention_reason": "binary JFR omitted; derived structural JSON, event summary, exact harness and SHA retained",
    }

    historical = cfg["historical_pre_c_prime"]
    threads = profile["execution_samples"]["threads"]
    frames = profile["execution_samples"]["top_frames"]
    main = next((x for x in threads if x["name"] == "main"), {"count": 0, "percent": 0.0})
    historical_frame = profile["execution_samples"]["historical_hashmap_keyiterator_next"]
    top_frame = frames[0] if frames else {"name": "<none>", "count": 0, "percent": 0.0}
    top_thread = threads[0] if threads else {"name": "<none>", "count": 0, "percent": 0.0}

    result = {
        "schema_version": 1,
        "perf_item": "PERF006",
        "slice": "PERF006-D3",
        "harness_revision": harness_revision,
        "d2_evidence_revision": D2_EVIDENCE,
        "protos_revision": EXPECTED_PROTOS_REVISION,
        "protos_implementation_version": cfg["protos_implementation_version"],
        "runtime": runtime,
        "cpuset": cpuset,
        "real_workload": current["real_workload"],
        "wall_seconds_diagnostic_only": wall_ns / 1_000_000_000.0,
        "historical_absolute_performance_comparison_allowed": False,
        "historical_pre_c_prime": historical,
        "current_jfr": profile,
        "current_main_thread": main,
        "current_top_thread": top_thread,
        "current_top_frame": top_frame,
        "current_historical_hashmap_symbol": historical_frame,
        "static_replay_audit": static_audit,
        "bounded_trace_compilation": trace,
        "jfr_binary_identity": jfr_identity,
        "igv24_analyzer_used": False,
        "production_optimization_applied": False,
    }
    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Keep bounded excerpts from real-workload output, not unbounded logs.
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    (output_dir / "test-tool-output-tail.txt").write_text(
        "=== stdout tail ===\n"
        + stdout_text[-12000:]
        + "\n=== stderr tail ===\n"
        + stderr_text[-12000:],
        encoding="utf-8",
    )
    stdout_path.unlink()
    stderr_path.unlink()
    recording.unlink()

    readme = f"""# PERF006-D3 current structural diagnostics

- exact diagnostic harness: `{harness_revision}`
- Protos revision: `{EXPECTED_PROTOS_REVISION}`
- runtime: `{runtime}`
- real workload: `bin/protos test --jobs 2`
- CPU set: `{cpuset}`
- diagnostic wall time: `{wall_ns / 1_000_000_000.0:.3f} s`
- historical absolute performance comparison: **not allowed**
- production optimization applied: **no**
- IGV-24 analyzer used: **no**

The recovered pre-C′ profile is retained as historical structural context, not
as an absolute timing comparator. D3 records current CPU/thread concentration,
the exact historical `java.util.HashMap$KeyIterator.next` symbol share,
standard and Truffle deoptimization counts where available, a static audit for
the retired replay cleanup path, and bounded current-toolchain TraceCompilation
evidence.

Current headline observations are machine-readable in `result.json`. D4 owns the
final causal interpretation and any decision to open a separate PERF item for a
new dominant hotspot.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    manifest_names = [
        "README.md", "current-profile.json", "jfr-summary.txt", "result.json",
        "test-tool-output-tail.txt", "trace-compilation.log",
    ]
    manifest = "".join(f"{sha256(output_dir / name)}  {name}\n" for name in manifest_names)
    (output_dir / "SHA256SUMS").write_text(manifest, encoding="utf-8")

    print("PERF006D3_REFERENCE=PASS")
    print("PERF006D3_REAL_WORKLOAD=bin/protos test --jobs 2")
    print("PERF006D3_CPUSET=" + cpuset)
    print("PERF006D3_WALL_SECONDS_DIAGNOSTIC_ONLY=%.3f" % (wall_ns / 1_000_000_000.0))
    print("PERF006D3_EXECUTION_SAMPLES=" + str(profile["execution_samples"]["total"]))
    print("PERF006D3_MAIN_THREAD_PERCENT=" + str(main["percent"]))
    print("PERF006D3_TOP_FRAME=" + str(top_frame["name"]))
    print("PERF006D3_TOP_FRAME_PERCENT=" + str(top_frame["percent"]))
    print("PERF006D3_HASHMAP_KEYITERATOR_PERCENT=" + str(historical_frame["percent"]))
    print("PERF006D3_JDK_DEOPTIMIZATIONS=" + str(profile["deoptimizations"]["jdk_total"]))
    print("PERF006D3_TRUFFLE_DEOPTIMIZATIONS=" + str(profile["deoptimizations"]["truffle_total"]))
    print(
        "PERF006D3_TRUFFLE_DEOPT_EVENT_AVAILABLE="
        + str(profile["event_type_available"]["jdk.graal.compiler.truffle.Deoptimization"]).upper()
    )
    print("PERF006D3_COMPACT_COMPLETED_CHILD_PRESENT=" + str(static_audit["compactCompletedChildExecution_present"]).upper())
    print("PERF006D3_INVOCATION_ACTIVATIONS_REMOVEIF_PRESENT=" + str(static_audit["invocationActivations_keySet_removeIf_present"]).upper())
    print("PERF006D3_TRACE_SUCCESSFUL_COMPILATIONS=" + str(trace["successful_compilations"]))
    print("PERF006D3_TRACE_FAILED_MARKERS=" + str(trace["failed_compilation_markers"]))
    print("PERF006D3_TRACE_BAILOUT_MARKERS=" + str(trace["bailout_markers"]))
    print("PERF006D3_HISTORICAL_ABSOLUTE_PERFORMANCE_COMPARISON=NO")
    print("PERF006D3_PRODUCTION_OPTIMIZATION_APPLIED=NO")
    print("PERF006D3_OUTPUT=" + str(output_dir))


def main() -> int:
    parser = argparse.ArgumentParser(description="PERF006-D3 structural diagnostics")
    parser.add_argument("command", choices=("validate", "smoke", "reference"))
    parser.add_argument("--harness-revision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    if args.command == "validate":
        validate()
        return 0
    if args.command == "smoke":
        smoke()
        return 0
    if not args.harness_revision or not args.output_dir:
        parser.error("reference requires --harness-revision and --output-dir")
    full_reference(args.harness_revision, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
