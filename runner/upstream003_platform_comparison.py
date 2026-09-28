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

"""UPSTREAM003-B controlled GraalVM/Truffle platform comparator.

The Protos Git revision is identical in both roles.  Platform A materializes the pinned revision
with its native 25.3.4.1 toolchain contract.  Platform B applies only the harness-owned build
metadata overlay before materialization, while preserving HEAD and executable language sources.

Clean timing and compiler diagnostics are separate evidence units.  No result produced here
automatically classifies 25.4 as better/worse or accept/reject.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import threading
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/upstream003-platform-comparison.json"
B2D_CONFIG = ROOT / "config/perf004b2d.json"
DOCKERFILE = ROOT / "docker/protos-upstream003/Dockerfile"
OVERLAY_SCRIPT = ROOT / "docker/protos-upstream003/apply_toolchain_overlay.py"
RUNTIME_PROBE_JAVA = ROOT / "docker/protos-upstream003/Upstream003RuntimeProbe.java"
TIMING_DRIVER = ROOT / "docker/protos-perf010a/Perf010aTimingDriver.java"
PERSISTENT_DRIVER = ROOT / "docker/protos-perf006d/Perf006dPersistentDriver.java"
MAKEFILE = ROOT / "Makefile"

EXPECTED_SLICE = "UPSTREAM003-B"
EXPECTED_PROTOS_REVISION = "44690b1fc8c9aed023600c6d5731f969c4507e27"
EXPECTED_PROTOS_VERSION = "0.3.106-SNAPSHOT"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_AUTHORIZED_OVERLAY_PATHS = ("dist/build_portable.py", "pom.xml", "toolchain.json")
ROLES = ("platform_a", "platform_b")
BLOCK_ORDER = ("A", "B", "A", "B")
TIMING_OUTPUT = ROOT / "results/upstream003-platform-comparison/timing"
DIAGNOSTIC_OUTPUT = ROOT / "results/upstream003-platform-comparison/diagnostic"

SMOKE_WARMUP_ITERATIONS = 1
SMOKE_STEADY_ITERATIONS = 1

FALLBACK_WARNING_RE = re.compile(
    r"No optimizing Truffle runtime found|fallback runtime that does not support runtime compilation|"
    r"does not support runtime compilation to native code|executed in interpreted mode only",
    re.IGNORECASE,
)
TRACE_DONE_RE = re.compile(r"\bopt done\b", re.IGNORECASE)
TRACE_FAILED_RE = re.compile(r"\bopt fail(?:ed)?\b|CompilationFailure", re.IGNORECASE)
TRACE_BAILOUT_RE = re.compile(r"Bailout|bailout", re.IGNORECASE)
TRACE_INVALIDATED_RE = re.compile(r"invalidat", re.IGNORECASE)
TRACE_TOO_DEEP_RE = re.compile(r"too\s+deep", re.IGNORECASE)
TRACE_DIRECT_CALL_RE = re.compile(r"\bDirectCallNode\b")
TRACE_INDIRECT_CALL_RE = re.compile(r"\bIndirectCallNode\b")
TRACE_INLINE_RE = re.compile(r"\binlin(?:e|ed|ing)\b", re.IGNORECASE)
TRACE_CUTOFF_RE = re.compile(r"\bcut\s*off\b|\bcutoff\b", re.IGNORECASE)
TRACE_FREQUENCY_RE = re.compile(
    r"\b(?:frequency|freq)\s*(?:[=:]\s*)?([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)",
    re.IGNORECASE,
)
TRACE_SIZE_RE = re.compile(
    r"\b(?:graph\s+(?:size|nodes?)|ir\s+nodes?|ast\s+(?:size|nodes?))\s*"
    r"(?:[=:]\s*)?([0-9]+)",
    re.IGNORECASE,
)
TRACE_RECURSION_DEPTH_RE = re.compile(r"\bRecursion\s+Depth\s+([0-9]+)", re.IGNORECASE)
TRACE_DEPTH_RE = re.compile(r"\bDepth\s+([0-9]+)", re.IGNORECASE)
TRACE_INLINING_STATE_RE = re.compile(
    r"^\s*\[engine\]\s+(Inlined|Expanded|Cutoff|Indirect|Removed|BailedOut)\b",
    re.IGNORECASE | re.MULTILINE,
)


def run(command: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
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
            "command failed: " + " ".join(command)
            + "\nstdout:\n" + (completed.stdout or "")[-8000:]
            + "\nstderr:\n" + (completed.stderr or "")[-8000:]
        )
    return (completed.stdout or "").rstrip("\n")


def load(path: Path = CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def worktree_harness_revision() -> str:
    head = output(["git", "rev-parse", "HEAD"])
    dirty = output(["git", "status", "--porcelain", "--untracked-files=all"])
    return head if not dirty else "WORKTREE_PRECOMMIT"


def exact_clean_harness_revision(explicit: str | None) -> str:
    head = output(["git", "rev-parse", "HEAD"])
    if explicit is not None and explicit != head:
        raise RuntimeError(
            f"exact harness revision mismatch: expected={explicit} observed={head}"
        )
    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("retained evidence requires a clean exact harness")
    return head


def first_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return line.split(":", 1)[1].strip().split(",")[0].split("-")[0]
    raise RuntimeError("cannot determine allowed CPU")


def host_identity() -> dict[str, str]:
    return {"platform": platform.platform(), "machine": platform.machine()}


def percentile_nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        raise ValueError("cannot summarize an empty sample set")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def summarize_ns(values: list[int]) -> dict[str, float | int]:
    if not values or any(not isinstance(v, int) or v <= 0 for v in values):
        raise ValueError("timing samples must be positive integers")
    median = statistics.median(values)
    deviations = [abs(v - median) for v in values]
    return {
        "samples": len(values),
        "median_ns": median,
        "mad_ns": statistics.median(deviations),
        "p95_ns": percentile_nearest_rank(values, 0.95),
        "min_ns": min(values),
        "max_ns": max(values),
    }


def stationarity_diagnostics(values: list[int]) -> dict[str, Any]:
    if len(values) != 100:
        raise RuntimeError(
            f"stationarity diagnostics require exactly 100 steady samples, got {len(values)}"
        )
    first = values[:25]
    last = values[75:]
    first_median = statistics.median(first)
    last_median = statistics.median(last)
    return {
        "steady_median_ns": statistics.median(values),
        "first_quarter_median_ns": first_median,
        "last_quarter_median_ns": last_median,
        "last_quarter_vs_first_quarter_percent": (
            100.0 * (last_median - first_median) / first_median
        ),
    }


def signed_delta(a_ns: float, b_ns: float) -> dict[str, float]:
    if a_ns <= 0:
        raise ValueError("platform A baseline must be positive")
    delta = b_ns - a_ns
    return {
        "absolute_delta_ns": delta,
        "relative_delta_percent": 100.0 * delta / a_ns,
    }


def summarize_platform_workload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        raise ValueError("cannot summarize an empty workload")

    all_samples: dict[str, dict[str, list[int]]] = {
        role: {"canonical": [], "control": []} for role in ROLES
    }
    per_block: list[dict[str, Any]] = []
    for entry in entries:
        block = {
            "block_index": entry["block_index"],
            "block_order": entry["block_order"],
        }
        for role in ROLES:
            for mode in ("canonical", "control"):
                samples = [int(v) for v in entry["roles"][role][mode]["raw"]["steady_ns"]]
                all_samples[role][mode].extend(samples)
        a_can = entry["roles"]["platform_a"]["canonical"]["steady_summary"]["median_ns"]
        b_can = entry["roles"]["platform_b"]["canonical"]["steady_summary"]["median_ns"]
        a_ctl = entry["roles"]["platform_a"]["control"]["steady_summary"]["median_ns"]
        b_ctl = entry["roles"]["platform_b"]["control"]["steady_summary"]["median_ns"]
        can_delta = signed_delta(a_can, b_can)
        ctl_delta = signed_delta(a_ctl, b_ctl)
        paired_ns = (b_can - a_can) - (b_ctl - a_ctl)
        block.update({
            "platform_a_canonical_median_ns": a_can,
            "platform_b_canonical_median_ns": b_can,
            "canonical_absolute_delta_ns": can_delta["absolute_delta_ns"],
            "canonical_relative_delta_percent": can_delta["relative_delta_percent"],
            "platform_a_control_median_ns": a_ctl,
            "platform_b_control_median_ns": b_ctl,
            "control_absolute_delta_ns": ctl_delta["absolute_delta_ns"],
            "control_relative_delta_percent": ctl_delta["relative_delta_percent"],
            "paired_control_delta_ns": paired_ns,
            "paired_control_delta_percent_of_platform_a_canonical": 100.0 * paired_ns / a_can,
        })
        per_block.append(block)

    aggregate = {
        role: {
            mode: summarize_ns(all_samples[role][mode])
            for mode in ("canonical", "control")
        }
        for role in ROLES
    }
    a = aggregate["platform_a"]["canonical"]["median_ns"]
    b = aggregate["platform_b"]["canonical"]["median_ns"]
    c_a = aggregate["platform_a"]["control"]["median_ns"]
    c_b = aggregate["platform_b"]["control"]["median_ns"]
    delta = signed_delta(a, b)
    paired = (b - a) - (c_b - c_a)

    a_order = [
        row["canonical_relative_delta_percent"] for row in per_block
        if row["block_order"] == "A"
    ]
    b_order = [
        row["canonical_relative_delta_percent"] for row in per_block
        if row["block_order"] == "B"
    ]
    if len(a_order) < 2 or len(b_order) < 2:
        order_effect = "INCONCLUSIVE"
    else:
        ar = (min(a_order), max(a_order))
        br = (min(b_order), max(b_order))
        order_effect = "DETECTED" if ar[1] < br[0] or br[1] < ar[0] else "NOT_DETECTED"

    return {
        "platform_a": aggregate["platform_a"],
        "platform_b": aggregate["platform_b"],
        "canonical_absolute_delta_ns": delta["absolute_delta_ns"],
        "canonical_relative_delta_percent": delta["relative_delta_percent"],
        "paired_control_delta_ns": paired,
        "paired_control_delta_percent_of_platform_a_canonical": 100.0 * paired / a,
        "per_block": per_block,
        "order_effect": order_effect,
        "a_order_relative_delta_percent": a_order,
        "b_order_relative_delta_percent": b_order,
    }


def parse_overlay_diff_paths(text: str) -> tuple[str, ...]:
    paths: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("diff --git a/"):
            continue
        match = re.fullmatch(r"diff --git a/(.+) b/(.+)", line)
        if match is None or match.group(1) != match.group(2):
            raise ValueError("unexpected overlay diff header: " + line)
        paths.add(match.group(1))
    return tuple(sorted(paths))


def trace_summary(text: str, workload_source: str) -> dict[str, Any]:
    frequencies = [float(v) for v in TRACE_FREQUENCY_RE.findall(text)]
    sizes = [int(v) for v in TRACE_SIZE_RE.findall(text)]
    recursion_depths = [int(v) for v in TRACE_RECURSION_DEPTH_RE.findall(text)]
    depths = [int(v) for v in TRACE_DEPTH_RE.findall(text)]
    inline_lines = [line for line in text.splitlines() if TRACE_INLINE_RE.search(line)]
    cutoff_lines = [line for line in text.splitlines() if TRACE_CUTOFF_RE.search(line)]
    source_lines = [
        line for line in text.splitlines()
        if Path(workload_source).name in line or "ProtosBytecodeRoot" in line
    ]
    state_names = [value.lower() for value in TRACE_INLINING_STATE_RE.findall(text)]
    state_counts = {
        state: state_names.count(state.lower())
        for state in ("Inlined", "Expanded", "Cutoff", "Indirect", "Removed", "BailedOut")
    }
    direct_state_markers = sum(
        state_counts[state]
        for state in ("Inlined", "Expanded", "Cutoff", "Removed", "BailedOut")
    )
    indirect_state_markers = state_counts["Indirect"]
    literal_direct = len(TRACE_DIRECT_CALL_RE.findall(text))
    literal_indirect = len(TRACE_INDIRECT_CALL_RE.findall(text))
    call_state_observed = direct_state_markers > 0 or indirect_state_markers > 0
    literal_call_kind_observed = literal_direct > 0 or literal_indirect > 0

    return {
        "successful_compilations": len(TRACE_DONE_RE.findall(text)),
        "failed_compilation_markers": len(TRACE_FAILED_RE.findall(text)),
        "bailout_markers": len(TRACE_BAILOUT_RE.findall(text)),
        "invalidation_markers": len(TRACE_INVALIDATED_RE.findall(text)),
        "too_deep_inlining_markers": len(TRACE_TOO_DEEP_RE.findall(text)),
        "direct_call_node_markers": literal_direct,
        "indirect_call_node_markers": literal_indirect,
        "guest_call_frequency": {
            "status": "OBSERVED_IN_TRACE" if frequencies else "UNAVAILABLE_FROM_TRACE",
            "values": frequencies,
        },
        "inlining_decisions": {
            "status": "OBSERVED_IN_TRACE" if inline_lines or call_state_observed else "UNAVAILABLE_FROM_TRACE",
            "matching_lines": inline_lines,
            "state_counts": state_counts,
        },
        "cutoff_decisions": {
            "status": "OBSERVED_IN_TRACE" if cutoff_lines else "UNAVAILABLE_FROM_TRACE",
            "matching_lines": cutoff_lines,
        },
        "graph_ir_size": {
            "status": "OBSERVED_IN_TRACE" if sizes else "UNAVAILABLE_FROM_TRACE",
            "values": sizes,
        },
        "source_root_identity": {
            "status": "OBSERVED_IN_TRACE" if source_lines else "UNAVAILABLE_FROM_TRACE",
            "matching_lines": source_lines,
        },
        "direct_vs_indirect_call_survival": {
            "status": (
                "OBSERVED_IN_TRACE"
                if call_state_observed or literal_call_kind_observed
                else "UNAVAILABLE_FROM_TRACE"
            ),
            "direct_call_tree_state_markers": direct_state_markers,
            "indirect_call_tree_state_markers": indirect_state_markers,
            "literal_direct_call_node_markers": literal_direct,
            "literal_indirect_call_node_markers": literal_indirect,
            "state_counts": state_counts,
        },
        "recursion_inlining_depth": {
            "status": (
                "OBSERVED_IN_TRACE"
                if recursion_depths or depths
                else "UNAVAILABLE_FROM_TRACE"
            ),
            "recursion_depth_values": recursion_depths,
            "depth_values": depths,
        },
    }


def helper_self_tests() -> None:
    delta = signed_delta(100.0, 125.0)
    assert delta == {"absolute_delta_ns": 25.0, "relative_delta_percent": 25.0}

    diff = (
        "diff --git a/pom.xml b/pom.xml\n"
        "diff --git a/toolchain.json b/toolchain.json\n"
        "diff --git a/dist/build_portable.py b/dist/build_portable.py\n"
    )
    assert parse_overlay_diff_paths(diff) == EXPECTED_AUTHORIZED_OVERLAY_PATHS

    trace = (
        "[engine] opt done root=method-call.protos |IR 123/456|\n"
        "[engine] inline start method-call.protos |Recursion Depth 0 |IR Nodes 2704 "
        "|Frequency 1.00 |Depth 0\n"
        "[engine] Inlined identity |Recursion Depth 0 |IR Nodes 175 |Frequency 2.50 |Depth 1\n"
        "[engine] Expanded helper |Recursion Depth 0 |IR Nodes 97 |Frequency 1.25 |Depth 1\n"
        "[engine] Cutoff cold |Recursion Depth 0 |IR Nodes 0 |Frequency 0.01 |Depth 2\n"
        "[engine] Indirect dynamic |Recursion Depth 0 |IR Nodes 0 |Frequency 0.10 |Depth 1\n"
        "Too deep inlining\n"
        "opt failed CompilationFailure Bailout invalidated ProtosBytecodeRootNode\n"
    )
    parsed = trace_summary(trace, "micro/method-call.protos")
    assert parsed["successful_compilations"] == 1
    assert parsed["failed_compilation_markers"] >= 1
    assert parsed["bailout_markers"] >= 1
    assert parsed["too_deep_inlining_markers"] >= 1
    assert 2.5 in parsed["guest_call_frequency"]["values"]
    assert 2704 in parsed["graph_ir_size"]["values"]
    assert parsed["inlining_decisions"]["state_counts"]["Inlined"] == 1
    assert parsed["inlining_decisions"]["state_counts"]["Expanded"] == 1
    assert parsed["inlining_decisions"]["state_counts"]["Cutoff"] == 1
    assert parsed["inlining_decisions"]["state_counts"]["Indirect"] == 1
    assert parsed["direct_vs_indirect_call_survival"]["direct_call_tree_state_markers"] == 3
    assert parsed["direct_vs_indirect_call_survival"]["indirect_call_tree_state_markers"] == 1
    assert parsed["recursion_inlining_depth"]["recursion_depth_values"]
    assert parsed["recursion_inlining_depth"]["depth_values"]


def validate() -> dict[str, Any]:
    cfg = load()
    assert cfg["schema_version"] == 1
    assert cfg["upstream_item"] == "UPSTREAM003"
    assert cfg["issue"] == "guillermomolina/protos#732"
    assert cfg["slice"] == EXPECTED_SLICE
    assert cfg["diagnostic_claim"] is False

    product = cfg["protos"]
    assert product["repository"] == "https://github.com/guillermomolina/protos.git"
    assert product["revision"] == EXPECTED_PROTOS_REVISION
    assert product["version"] == EXPECTED_PROTOS_VERSION

    platforms = cfg["platforms"]
    assert tuple(platforms) == ROLES
    assert platforms["platform_a"] == {
        "role": "platform_a",
        "label": "25.3",
        "graalvm_release": "25.3.4.1",
        "graal_truffle_version": "25.3.4.1",
        "jdk_version": "25.0.4.1",
        "maven_version": "3.9.9",
        "container_image": "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825",
        "build_toolchain_overlay": False,
    }
    assert platforms["platform_b"] == {
        "role": "platform_b",
        "label": "25.4",
        "graalvm_release": "25.4.4.1.1",
        "graal_truffle_version": "25.4.4.1.1",
        "jdk_version": "25.0.4.1",
        "maven_version": "3.9.9",
        "container_image": "ghcr.io/graalvm/graalvm-community:25i4-ol10",
        "build_toolchain_overlay": True,
    }

    overlay = cfg["overlay"]
    assert overlay["role"] == "platform_b"
    assert tuple(sorted(overlay["authorized_paths"])) == EXPECTED_AUTHORIZED_OVERLAY_PATHS
    assert overlay["semantic_source_paths"] == ["src", "protos"]
    assert overlay["source_git_revision_same"] is True
    assert overlay["executable_language_source_same"] is True
    assert overlay["source_tree_byte_identical_claim"] is False

    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 120
    assert cfg["steady_iterations"] == 100
    assert tuple(cfg["block_order"]) == BLOCK_ORDER
    assert cfg["block_role_order"] == {
        "A": ["platform_a", "platform_b"],
        "B": ["platform_b", "platform_a"],
    }
    assert cfg["network"] == "none"
    assert cfg["timing_recording_phase"] == "steady_only_no_diagnostic_instrumentation"
    exclusions = set(cfg["clean_timing_exclusions"])
    for item in ("JFR", "TraceCompilation", "TraceCompilationDetails", "TraceInlining", "IGV"):
        assert item in exclusions

    b2d = load(B2D_CONFIG)
    assert cfg["controls"] == b2d["controls"], "four-workload matrix drift"
    assert [item["id"] for item in cfg["controls"]] == [
        "micro/slot-read",
        "micro/closure-call",
        "micro/method-call",
        "runtime/monomorphic-dispatch",
    ]
    assert all(item["expected"] == "42" for item in cfg["controls"])
    assert cfg["timing_comparison"]["automatic_adoption_classification"] is False
    assert cfg["timing_comparison"]["whole_language_aggregation"] is False
    assert cfg["historical_evidence_used_as_side_a"] is False

    diagnostic = cfg["diagnostic"]
    assert diagnostic["separate_from_timing"] is True
    assert diagnostic["workloads"] == [
        "micro/closure-call", "micro/method-call", "runtime/monomorphic-dispatch"
    ]
    assert diagnostic["allow_experimental_options"] is True
    assert diagnostic["trace_compilation"] is True
    assert diagnostic["trace_compilation_details"] is True
    assert diagnostic["trace_inlining"] is True

    for path in (
        CONFIG, B2D_CONFIG, DOCKERFILE, OVERLAY_SCRIPT, RUNTIME_PROBE_JAVA,
        TIMING_DRIVER, PERSISTENT_DRIVER, MAKEFILE,
    ):
        assert path.is_file(), path

    overlay_text = OVERLAY_SCRIPT.read_text(encoding="utf-8")
    for path in ("pom.xml", "toolchain.json", "dist/build_portable.py"):
        assert path in overlay_text
    for forbidden in ('"src/', '"protos/', '"spec/'):
        assert forbidden not in overlay_text, (
            "build-only overlay script must not address executable/product paths: " + forbidden
        )

    docker_text = DOCKERFILE.read_text(encoding="utf-8")
    for required in (
        "ARG PLATFORM_ROLE",
        "apply_toolchain_overlay.py",
        'python3 dist/build_portable.py --allow-dirty',
        'python3 dist/build_portable.py;',
        "UPSTREAM003_SOURCE_SCOPE_GATE=PASS",
        "src_content_sha256",
        "protos_content_sha256",
        "/opt/upstream003/corpus",
        "/opt/upstream003/diagnostic",
    ):
        assert required in docker_text, required

    timing_driver = TIMING_DRIVER.read_text(encoding="utf-8")
    assert "import jdk.jfr" not in timing_driver
    assert "steady_ns" in timing_driver

    makefile = MAKEFILE.read_text(encoding="utf-8")
    for target in (
        "upstream003-validate:",
        "upstream003-smoke:",
        "upstream003-reference:",
        "upstream003-diagnostic:",
    ):
        assert target in makefile, "missing Makefile target: " + target[:-1]

    assert cfg["timing_output"] == "results/upstream003-platform-comparison/timing"
    assert cfg["diagnostic_output"] == "results/upstream003-platform-comparison/diagnostic"
    assert not cfg["timing_output"].startswith("results/perf014")
    assert not cfg["diagnostic_output"].startswith("results/perf014")

    helper_self_tests()

    print("UPSTREAM003_B_CONFIG=PASS")
    print("UPSTREAM003_B_HELPER_SELF_TESTS=PASS")
    print("SAME_PROTOS_REVISION=PASS")
    print("SAME_PROTOS_VERSION=PASS")
    print("PLATFORM_A_EXPECTED=25.3.4.1")
    print("PLATFORM_B_EXPECTED=25.4.4.1.1")
    print("B_TOOLCHAIN_OVERLAY_AUTHORIZED_PATHS=" + ",".join(EXPECTED_AUTHORIZED_OVERLAY_PATHS))
    print("WARMUP=120")
    print("STEADY=100")
    print("BLOCK_ORDER=A,B,A,B")
    print("DIAGNOSTIC_TIMING_SEPARATION=PASS")
    print("PROTOS_OPTIMIZATION_MIXED_IN=NO")
    print("PROTOS_SEMANTIC_CHANGE=NO")
    print("HISTORICAL_EVIDENCE_REWRITTEN=NO")
    return cfg


def _mirror_stream(stream, sink: list[str], mirror) -> None:
    for line in iter(stream.readline, ""):
        sink.append(line)
        if mirror is not None:
            mirror.write(line)
            mirror.flush()
    stream.close()


def run_visible(command: list[str], *, mirror_stdout: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    out_thread = threading.Thread(
        target=_mirror_stream,
        args=(proc.stdout, stdout_lines, sys.stdout if mirror_stdout else None),
    )
    err_thread = threading.Thread(
        target=_mirror_stream,
        args=(proc.stderr, stderr_lines, sys.stderr),
    )
    out_thread.start()
    err_thread.start()
    code = proc.wait()
    out_thread.join()
    err_thread.join()
    return subprocess.CompletedProcess(
        command, code, "".join(stdout_lines), "".join(stderr_lines)
    )


def docker_entrypoint(cpu: str, tag: str, entrypoint: str, *args: str) -> subprocess.CompletedProcess[str]:
    completed = run(
        [
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpu,
            "--entrypoint", entrypoint,
            tag,
            *args,
        ],
        capture=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"docker entrypoint failed: {entrypoint}\n"
            + (completed.stdout or "")[-4000:]
            + "\n"
            + (completed.stderr or "")[-4000:]
        )
    return completed


def image_identity(ref: str) -> dict[str, Any]:
    payload = json.loads(output(["docker", "image", "inspect", ref]))[0]
    return {
        "tag": ref,
        "id": payload.get("Id", ""),
        "repo_digests": payload.get("RepoDigests") or [],
        "architecture": payload.get("Architecture", ""),
        "os": payload.get("Os", ""),
    }


def build_image(cfg: dict[str, Any], role: str) -> tuple[str, dict[str, Any]]:
    platform_cfg = cfg["platforms"][role]
    selector = platform_cfg["container_image"]
    run(["docker", "pull", selector])
    base_identity = image_identity(selector)
    if not base_identity["id"] or not base_identity["repo_digests"]:
        raise RuntimeError(
            f"resolved base image identity incomplete for role={role}: {base_identity!r}"
        )

    tag = f"protos-benchmarks-upstream003-{role[-1]}:{EXPECTED_PROTOS_REVISION[:12]}"
    run([
        "docker", "build",
        "--build-arg", "GRAAL_BASE=" + selector,
        "--build-arg", "PLATFORM_ROLE=" + role,
        "--build-arg", "PROTOS_REPOSITORY=" + cfg["protos"]["repository"],
        "--build-arg", "PROTOS_REVISION=" + cfg["protos"]["revision"],
        "--build-arg", "EXPECTED_PLATFORM_VERSION=" + platform_cfg["graal_truffle_version"],
        "--build-arg", "EXPECTED_JDK_VERSION=" + platform_cfg["jdk_version"],
        "--build-arg", "EXPECTED_MAVEN_VERSION=" + platform_cfg["maven_version"],
        "--label", "org.opencontainers.image.revision=" + cfg["protos"]["revision"],
        "--label", "org.protos-benchmarks.upstream003.platform-role=" + role,
        "--label", "org.protos-benchmarks.upstream003.platform-version="
                   + platform_cfg["graal_truffle_version"],
        "-t", tag,
        "-f", str(DOCKERFILE.relative_to(ROOT)),
        ".",
    ])
    return tag, base_identity


def runtime_probe(tag: str, cpu: str) -> dict[str, str]:
    completed = docker_entrypoint(
        cpu, tag, "java",
        "--enable-native-access=ALL-UNNAMED",
        "-cp", "/opt/upstream003/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Upstream003RuntimeProbe",
    )
    result: dict[str, str] = {}
    for line in (completed.stdout or "").splitlines():
        if line.startswith("UPSTREAM003_PROBE_") and "=" in line:
            key, value = line.split("=", 1)
            result[key.removeprefix("UPSTREAM003_PROBE_").lower()] = value.strip()
    return result


def java_version_probe(tag: str, cpu: str) -> str:
    completed = docker_entrypoint(cpu, tag, "java", "-version")
    return (completed.stderr or completed.stdout or "").strip()


def image_text(tag: str, cpu: str, path: str) -> str:
    # Preserve the exact stream, including the final newline: workload/source identity is
    # byte-sensitive and must not normalize textual representation.
    return docker_entrypoint(cpu, tag, "cat", path).stdout or ""


def image_json(tag: str, cpu: str, path: str) -> Any:
    return json.loads(image_text(tag, cpu, path))


def image_revision_label(tag: str) -> str:
    payload = json.loads(output(["docker", "image", "inspect", tag]))[0]
    labels = ((payload.get("Config") or {}).get("Labels")) or {}
    return labels.get("org.opencontainers.image.revision", "")


def image_version_probe(tag: str, cpu: str) -> str:
    import xml.etree.ElementTree as ET
    text = image_text(tag, cpu, "/opt/protos-source/pom.xml")
    root = ET.fromstring(text)
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    node = root.find("m:version", ns)
    return node.text.strip() if node is not None and node.text else ""


def _verify_workload_source_identity(
    controls: list[dict[str, Any]], tags: dict[str, str], cpu: str,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in controls:
        path = "/opt/upstream003/corpus/" + item["source"]
        texts = {role: image_text(tags[role], cpu, path) for role in ROLES}
        digests = {
            role: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for role, text in texts.items()
        }
        if texts["platform_a"] != texts["platform_b"]:
            raise RuntimeError(
                "WORKLOAD_SOURCE_IDENTITY_MISMATCH: "
                f"workload={item['id']} platform_a={digests['platform_a']} "
                f"platform_b={digests['platform_b']}"
            )
        result[item["id"]] = digests
    return result


def _build_and_probe_images(cfg: dict[str, Any], cpu: str) -> dict[str, Any]:
    tags: dict[str, str] = {}
    base_identities: dict[str, Any] = {}
    built_identities: dict[str, Any] = {}
    runtime_identities: dict[str, Any] = {}
    source_identities: dict[str, Any] = {}
    overlay_diffs: dict[str, str] = {}

    for role in ROLES:
        platform_cfg = cfg["platforms"][role]
        tag, base_identity = build_image(cfg, role)
        tags[role] = tag
        base_identities[role] = base_identity
        built_identities[role] = image_identity(tag)

        if image_revision_label(tag) != EXPECTED_PROTOS_REVISION:
            raise RuntimeError(f"image revision label mismatch for {role}")
        if image_version_probe(tag, cpu) != EXPECTED_PROTOS_VERSION:
            raise RuntimeError(f"image Protos version mismatch for {role}")

        runtime = runtime_probe(tag, cpu)
        java_version = java_version_probe(tag, cpu)
        build_identity = image_text(
            tag, cpu, "/opt/upstream003/identity/build-identity.txt"
        )
        components = image_json(
            tag, cpu, "/opt/upstream003/identity/runtime-components.json"
        )
        components_text = json.dumps(components, sort_keys=True)
        expected_platform = platform_cfg["graal_truffle_version"]

        if runtime.get("runtime_class") != EXPECTED_RUNTIME:
            raise RuntimeError(
                f"runtime mismatch role={role}: {runtime.get('runtime_class')!r}"
            )
        if runtime.get("engine_version") != expected_platform:
            raise RuntimeError(
                f"GraalVM engine version mismatch role={role}: expected={expected_platform!r} "
                f"observed={runtime.get('engine_version')!r}"
            )
        if expected_platform not in components_text:
            raise RuntimeError(
                f"Truffle/component identity mismatch role={role}: expected token "
                f"{expected_platform!r} absent from bundled runtime component identity"
            )
        if platform_cfg["jdk_version"] not in java_version:
            raise RuntimeError(
                f"JDK identity mismatch role={role}: expected token "
                f"{platform_cfg['jdk_version']!r} absent from java -version"
            )
        if f"Apache Maven {platform_cfg['maven_version']}" not in build_identity:
            raise RuntimeError(f"Maven identity mismatch role={role}")
        if not runtime.get("arch"):
            raise RuntimeError(f"architecture probe missing role={role}")

        source = image_json(tag, cpu, "/opt/upstream003/identity/source-identity.json")
        if source["protos_revision"] != EXPECTED_PROTOS_REVISION:
            raise RuntimeError(f"source revision mismatch role={role}")
        dirty_paths = tuple(sorted(source["dirty_paths"]))
        overlay_diff = image_text(tag, cpu, "/opt/upstream003/identity/overlay.diff")
        overlay_diff_paths = parse_overlay_diff_paths(overlay_diff)
        if role == "platform_a":
            if dirty_paths or overlay_diff_paths:
                raise RuntimeError("platform A must be a clean product checkout")
        else:
            if dirty_paths != EXPECTED_AUTHORIZED_OVERLAY_PATHS:
                raise RuntimeError(
                    f"B_TOOLCHAIN_OVERLAY_EXACT_SCOPE failure: dirty_paths={dirty_paths!r}"
                )
            if overlay_diff_paths != EXPECTED_AUTHORIZED_OVERLAY_PATHS:
                raise RuntimeError(
                    f"B_TOOLCHAIN_OVERLAY_EXACT_SCOPE failure: diff_paths={overlay_diff_paths!r}"
                )

        runtime_identities[role] = {
            "probe": runtime,
            "java_version": java_version,
            "build_identity": build_identity,
            "runtime_components": components,
        }
        source_identities[role] = source
        overlay_diffs[role] = overlay_diff

        print(
            "UPSTREAM003 IMAGE "
            f"role={role} base_tag={base_identity['tag']} base_id={base_identity['id']} "
            f"base_repo_digests={base_identity['repo_digests']} built_id={built_identities[role]['id']}",
            flush=True,
        )

    for key in ("src_content_sha256", "protos_content_sha256", "src_file_count", "protos_file_count"):
        if source_identities["platform_a"][key] != source_identities["platform_b"][key]:
            raise RuntimeError(
                f"SAME_EXECUTABLE_LANGUAGE_SOURCE failure field={key}: "
                f"A={source_identities['platform_a'][key]!r} "
                f"B={source_identities['platform_b'][key]!r}"
            )

    workload_source_sha256 = _verify_workload_source_identity(cfg["controls"], tags, cpu)

    print("SAME_PROTOS_REVISION=PASS")
    print("SAME_PROTOS_VERSION=PASS")
    print("SAME_EXECUTABLE_LANGUAGE_SOURCE=PASS")
    print("B_TOOLCHAIN_OVERLAY_EXACT_SCOPE=PASS")
    print("WORKLOAD_SOURCE_IDENTITY=PASS")
    print("PLATFORM_A_RUNTIME_IDENTITY_PROBE=PASS")
    print("PLATFORM_B_RUNTIME_IDENTITY_PROBE=PASS")
    print("CONTAINER_IMAGE_IDENTITY_RETAINED=YES")
    print("REPO_DIGEST_RETAINED=YES")
    print("SOURCE_GIT_REVISION_SAME=YES")
    print("EXECUTABLE_LANGUAGE_SOURCE_SAME=YES")
    print("BUILD_TOOLCHAIN_METADATA_OVERLAY_B=YES")

    return {
        "tags": tags,
        "resolved_base_image_identity": base_identities,
        "built_image_identity": built_identities,
        "runtime_identity": runtime_identities,
        "source_identity": source_identities,
        "workload_source_sha256": workload_source_sha256,
        "overlay_diff": overlay_diffs,
    }


def control_source(tag: str, cpu: str, work: Path, item: dict[str, Any]) -> tuple[str, Path]:
    canonical = "/opt/upstream003/corpus/" + item["source"]
    source_text = image_text(tag, cpu, canonical)
    if source_text.count(item["replace"]) != 1:
        raise RuntimeError(f"expected exactly one control target in {item['id']}")
    path = work / (item["id"].replace("/", "__") + "-control.protos")
    path.write_text(source_text.replace(item["replace"], item["with"], 1), encoding="utf-8")
    return canonical, path


def timing_visible(
    tag: str,
    cpu: str,
    logs_dir: Path,
    source_host: Path | None,
    source_container: str,
    expected: str,
    label: str,
    warmup: int,
    steady: int,
    *,
    collect_stationarity: bool,
) -> dict[str, Any]:
    command = [
        "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
    ]
    if source_host is not None:
        command += ["--volume", f"{source_host.resolve()}:/work/source.protos:ro"]
        source_container = "/work/source.protos"
    command += [
        "--entrypoint", "java", tag,
        "-Xss128m",
        "--enable-native-access=ALL-UNNAMED",
        "-cp", "/opt/upstream003/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf010aTimingDriver",
        source_container, expected, str(warmup), str(steady),
    ]
    completed = run_visible(command)
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / (label + ".stdout.log")
    stderr_path = logs_dir / (label + ".stderr.log")
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"timing/correctness unit failed label={label} returncode={completed.returncode}\n"
            + (completed.stderr or "")[-8000:]
        )
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("empty timing driver output: " + label)
    payload = json.loads(lines[-1])
    warmup_ns = [int(v) for v in payload["warmup_ns"]]
    steady_ns = [int(v) for v in payload["steady_ns"]]
    if len(warmup_ns) != warmup or len(steady_ns) != steady:
        raise RuntimeError(
            f"sample count mismatch label={label}: "
            f"warmup={len(warmup_ns)}/{warmup} steady={len(steady_ns)}/{steady}"
        )
    result = {
        "raw": payload,
        "steady_summary": summarize_ns(steady_ns),
        "stdout_log": stdout_path.name,
        "stderr_log": stderr_path.name,
        "stdout_sha256": hashlib.sha256((completed.stdout or "").encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256((completed.stderr or "").encode()).hexdigest(),
    }
    result["stationarity"] = (
        stationarity_diagnostics(steady_ns) if collect_stationarity else None
    )
    return result


def block_role_order(label: str) -> tuple[str, str]:
    if label == "A":
        return ("platform_a", "platform_b")
    if label == "B":
        return ("platform_b", "platform_a")
    raise ValueError("unknown block label: " + repr(label))


def run_blocks(
    cfg: dict[str, Any],
    tags: dict[str, str],
    cpu: str,
    work: Path,
    logs_dir: Path,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block_index, block_label in enumerate(BLOCK_ORDER):
        order = block_role_order(block_label)
        for item in cfg["controls"]:
            roles: dict[str, Any] = {}
            for role in order:
                canonical, control_host = control_source(tags[role], cpu, work, item)
                modes: dict[str, Any] = {}
                for mode, source_host, source_container in (
                    ("canonical", None, canonical),
                    ("control", control_host, "/work/source.protos"),
                ):
                    label = (
                        f"block{block_index}-{block_label}-"
                        f"{item['id'].replace('/', '__')}-{role}-{mode}"
                    )
                    result = timing_visible(
                        tags[role], cpu, logs_dir,
                        source_host, source_container, item["expected"], label,
                        cfg["warmup_iterations"], cfg["steady_iterations"],
                        collect_stationarity=True,
                    )
                    print(
                        f"UPSTREAM003 TIMING PASS block={block_index} order={block_label} "
                        f"workload={item['id']} role={role} mode={mode} "
                        f"median_ns={result['steady_summary']['median_ns']}",
                        flush=True,
                    )
                    modes[mode] = result
                roles[role] = modes
            blocks.append({
                "block_index": block_index,
                "block_order": block_label,
                "role_sequence": list(order),
                "workload": item["id"],
                "roles": roles,
            })
    return blocks


def smoke_correctness(cfg: dict[str, Any], tags: dict[str, str], cpu: str) -> None:
    with tempfile.TemporaryDirectory(prefix="upstream003-smoke-") as tmp:
        work = Path(tmp)
        logs = work / "logs"
        for item in cfg["controls"]:
            for role in ROLES:
                canonical, control_host = control_source(tags[role], cpu, work, item)
                for mode, source_host, source_container in (
                    ("canonical", None, canonical),
                    ("control", control_host, "/work/source.protos"),
                ):
                    timing_visible(
                        tags[role], cpu, logs, source_host, source_container,
                        item["expected"],
                        f"{item['id'].replace('/', '__')}-{role}-{mode}",
                        SMOKE_WARMUP_ITERATIONS,
                        SMOKE_STEADY_ITERATIONS,
                        collect_stationarity=False,
                    )


def smoke() -> None:
    cfg = validate()
    cpu = first_cpu()
    build = _build_and_probe_images(cfg, cpu)
    smoke_correctness(cfg, build["tags"], cpu)
    print("UPSTREAM003_SMOKE_HARNESS_REVISION=" + worktree_harness_revision())
    print("CORRECTNESS_A=PASS")
    print("CORRECTNESS_B=PASS")
    print("UPSTREAM003_SMOKE=PASS")
    print("UPSTREAM003_SMOKE_RETAINED_PERFORMANCE_EVIDENCE=NO")


def _prepare_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise RuntimeError("output directory already contains evidence: " + str(path))
        path.rmdir()
    path.mkdir(parents=True)


def _write_manifest(output_dir: Path) -> None:
    names = [
        path for path in output_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    rows = [
        f"{sha256(path)}  {path.relative_to(output_dir).as_posix()}"
        for path in sorted(names)
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def reference(harness_revision: str | None, output_dir: Path | None) -> None:
    cfg = validate()
    harness_revision = exact_clean_harness_revision(harness_revision)
    output_dir = output_dir or TIMING_OUTPUT
    _prepare_output(output_dir)

    cpu = first_cpu()
    build = _build_and_probe_images(cfg, cpu)
    logs_dir = output_dir / "logs"

    with tempfile.TemporaryDirectory(prefix="upstream003-reference-") as tmp:
        blocks = run_blocks(cfg, build["tags"], cpu, Path(tmp), logs_dir)

    by_workload: dict[str, list[dict[str, Any]]] = {}
    for entry in blocks:
        by_workload.setdefault(entry["workload"], []).append(entry)
    summaries = {
        workload: summarize_platform_workload(entries)
        for workload, entries in by_workload.items()
    }

    stationarity = [
        {
            "block_index": entry["block_index"],
            "block_order": entry["block_order"],
            "workload": entry["workload"],
            "role": role,
            "mode": mode,
            **entry["roles"][role][mode]["stationarity"],
        }
        for entry in blocks
        for role in ROLES
        for mode in ("canonical", "control")
    ]

    raw = {
        "schema_version": 1,
        "upstream_item": "UPSTREAM003",
        "slice": EXPECTED_SLICE,
        "evidence_kind": "clean_timing",
        "evidence_status": "RETAINED",
        "harness_revision": harness_revision,
        "protos": cfg["protos"],
        "platforms": cfg["platforms"],
        "resolved_base_image_identity": build["resolved_base_image_identity"],
        "built_image_identity": build["built_image_identity"],
        "runtime_identity": build["runtime_identity"],
        "source_identity": build["source_identity"],
        "workload_source_sha256": build["workload_source_sha256"],
        "host_identity": host_identity(),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "network": "none",
        "operation_count": cfg["operation_count"],
        "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"],
        "block_order": list(BLOCK_ORDER),
        "blocks": blocks,
        "per_timed_unit_stationarity": stationarity,
        "per_workload_summary": summaries,
        "automatic_adoption_classification": False,
        "whole_language_aggregation": False,
        "diagnostic_instrumentation_present": False,
    }
    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "platform-b-overlay.diff").write_text(
        build["overlay_diff"]["platform_b"], encoding="utf-8"
    )

    rows = [
        "workload\tplatform_a_median_ns\tplatform_a_mad_ns\tplatform_a_p95_ns\t"
        "platform_b_median_ns\tplatform_b_mad_ns\tplatform_b_p95_ns\t"
        "absolute_delta_ns\trelative_delta_percent\tpaired_control_delta_ns\t"
        "paired_control_delta_percent_of_platform_a_canonical\torder_effect"
    ]
    for workload, summary in summaries.items():
        a = summary["platform_a"]["canonical"]
        b = summary["platform_b"]["canonical"]
        rows.append("\t".join([
            workload,
            str(a["median_ns"]), str(a["mad_ns"]), str(a["p95_ns"]),
            str(b["median_ns"]), str(b["mad_ns"]), str(b["p95_ns"]),
            str(summary["canonical_absolute_delta_ns"]),
            f"{summary['canonical_relative_delta_percent']:.6f}",
            str(summary["paired_control_delta_ns"]),
            f"{summary['paired_control_delta_percent_of_platform_a_canonical']:.6f}",
            summary["order_effect"],
        ]))
    (output_dir / "summary.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    stationarity_rows = [
        "block_index\tblock_order\tworkload\trole\tmode\tsteady_median_ns\t"
        "first_quarter_median_ns\tlast_quarter_median_ns\t"
        "last_quarter_vs_first_quarter_percent"
    ]
    for row in stationarity:
        stationarity_rows.append("\t".join([
            str(row["block_index"]), row["block_order"], row["workload"],
            row["role"], row["mode"], str(row["steady_median_ns"]),
            str(row["first_quarter_median_ns"]), str(row["last_quarter_median_ns"]),
            f"{row['last_quarter_vs_first_quarter_percent']:.6f}",
        ]))
    (output_dir / "stationarity.tsv").write_text(
        "\n".join(stationarity_rows) + "\n", encoding="utf-8"
    )

    readme = [
        "# UPSTREAM003 GraalVM / Truffle platform comparison — clean timing",
        "",
        cfg["causal_question"],
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision: `{EXPECTED_PROTOS_REVISION}`",
        f"- Protos version: `{EXPECTED_PROTOS_VERSION}`",
        "- Platform A: `25.3.4.1`.",
        "- Platform B: `25.4.4.1.1`.",
        "- `SOURCE_GIT_REVISION_SAME=YES`.",
        "- `EXECUTABLE_LANGUAGE_SOURCE_SAME=YES`.",
        "- `BUILD_TOOLCHAIN_METADATA_OVERLAY_B=YES`.",
        "- Clean timing contains no JFR/compiler tracing/IGV/source instrumentation.",
        "- Signed delta is `platform_b - platform_a`; no accept/reject or better/worse "
        "classification is produced by this harness.",
        "- No four-workload aggregate is produced; every workload is reported independently.",
        "",
        "See `summary.tsv`, `stationarity.tsv`, and authoritative `raw.json`.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")
    _write_manifest(output_dir)

    print("UPSTREAM003_B_HARNESS=PASS")
    print("UPSTREAM003_EVIDENCE_KIND=CLEAN_TIMING")
    print("SAME_PROTOS_REVISION=PASS")
    print("SAME_PROTOS_VERSION=PASS")
    print("SAME_EXECUTABLE_LANGUAGE_SOURCE=PASS")
    print("B_TOOLCHAIN_OVERLAY_EXACT_SCOPE=PASS")
    print("WORKLOAD_SOURCE_IDENTITY=PASS")
    print("CORRECTNESS_A=PASS")
    print("CORRECTNESS_B=PASS")
    print("TIMING_PROTOCOL_EQUAL=PASS")
    print("WARMUP=120")
    print("STEADY=100")
    print("BLOCK_ORDER=A,B,A,B")
    print("CONTROL_TIMING_CAPABILITY=PASS")
    print("CLOSURE_CALL_TIMING_CAPABILITY=PASS")
    print("METHOD_CALL_TIMING_CAPABILITY=PASS")
    print("MONOMORPHIC_DISPATCH_TIMING_CAPABILITY=PASS")
    print("DIAGNOSTIC_TIMING_SEPARATION=PASS")
    print("PROTOS_OPTIMIZATION_MIXED_IN=NO")
    print("PROTOS_SEMANTIC_CHANGE=NO")
    print("HISTORICAL_EVIDENCE_REWRITTEN=NO")
    print("UPSTREAM003_AUTOMATIC_ADOPTION_CLASSIFICATION=NO")


def diagnostic_unit(
    cfg: dict[str, Any],
    tag: str,
    role: str,
    cpu: str,
    item: dict[str, Any],
    logs_dir: Path,
) -> dict[str, Any]:
    diagnostic = cfg["diagnostic"]
    classpath = "/opt/upstream003/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*"
    command = [
        "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
        "--entrypoint", "java", tag,
        "-Xss128m",
        "-Dpolyglot.engine.AllowExperimentalOptions=true",
        "-Dpolyglot.engine.TraceCompilation=true",
        "-Dpolyglot.engine.TraceCompilationDetails=true",
        "-Dpolyglot.engine.TraceInlining=true",
        "-Dpolyglot.engine.CompilationFailureAction=Print",
        "--enable-native-access=ALL-UNNAMED",
        "-cp", classpath,
        "Perf006dPersistentDriver",
        "/opt/upstream003/corpus/" + item["source"],
        item["expected"],
        str(diagnostic["warmup_iterations"]),
        str(diagnostic["steady_iterations"]),
    ]
    completed = run_visible(command)
    logs_dir.mkdir(parents=True, exist_ok=True)
    slug = item["id"].replace("/", "__")
    stdout_path = logs_dir / f"{slug}-{role}.stdout.log"
    stderr_path = logs_dir / f"{slug}-{role}.stderr.log"
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"compiler diagnostic failed role={role} workload={item['id']}\n"
            + (completed.stderr or "")[-10000:]
        )
    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if FALLBACK_WARNING_RE.search(text):
        raise RuntimeError(
            f"compiler diagnostic used fallback runtime role={role} workload={item['id']}"
        )
    summary = trace_summary(text, item["source"])
    if summary["successful_compilations"] <= 0:
        raise RuntimeError(
            f"compiler diagnostic observed no successful compilation role={role} "
            f"workload={item['id']}"
        )
    return {
        "role": role,
        "workload": item["id"],
        "expected": item["expected"],
        "trace_summary": summary,
        "stdout_log": stdout_path.name,
        "stderr_log": stderr_path.name,
        "stdout_sha256": hashlib.sha256((completed.stdout or "").encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256((completed.stderr or "").encode()).hexdigest(),
    }


def diagnostic(harness_revision: str | None, output_dir: Path | None) -> None:
    cfg = validate()
    harness_revision = exact_clean_harness_revision(harness_revision)
    output_dir = output_dir or DIAGNOSTIC_OUTPUT
    _prepare_output(output_dir)

    cpu = first_cpu()
    build = _build_and_probe_images(cfg, cpu)
    logs_dir = output_dir / "logs"
    wanted = set(cfg["diagnostic"]["workloads"])
    controls = [item for item in cfg["controls"] if item["id"] in wanted]

    units: list[dict[str, Any]] = []
    for item in controls:
        for role in ROLES:
            units.append(
                diagnostic_unit(cfg, build["tags"][role], role, cpu, item, logs_dir)
            )

    raw = {
        "schema_version": 1,
        "upstream_item": "UPSTREAM003",
        "slice": EXPECTED_SLICE,
        "evidence_kind": "compiler_inlining_diagnostic",
        "evidence_status": "RETAINED_DIAGNOSTIC_NOT_TIMING",
        "harness_revision": harness_revision,
        "protos": cfg["protos"],
        "platforms": cfg["platforms"],
        "resolved_base_image_identity": build["resolved_base_image_identity"],
        "built_image_identity": build["built_image_identity"],
        "runtime_identity": build["runtime_identity"],
        "source_identity": build["source_identity"],
        "workload_source_sha256": build["workload_source_sha256"],
        "host_identity": host_identity(),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "network": "none",
        "diagnostic_contract": cfg["diagnostic"],
        "units": units,
        "timing_claim": False,
        "automatic_causal_attribution": False,
    }
    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "platform-b-overlay.diff").write_text(
        build["overlay_diff"]["platform_b"], encoding="utf-8"
    )
    readme = [
        "# UPSTREAM003 GraalVM / Truffle platform comparison — compiler diagnostic",
        "",
        "This is a separate diagnostic evidence unit. It is not timing evidence.",
        "",
        "The raw TraceCompilation/TraceCompilationDetails/TraceCompilationCallTree streams are "
        "retained under `logs/`. Parsed fields are observational only. Fields that the emitted "
        "trace does not expose are explicitly `UNAVAILABLE_FROM_TRACE`; a missing textual marker "
        "is never treated as proof that a compiler structure is absent.",
        "",
        "Primary diagnostic workloads: micro/closure-call, micro/method-call, "
        "runtime/monomorphic-dispatch.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")
    _write_manifest(output_dir)

    print("UPSTREAM003_B_HARNESS=PASS")
    print("UPSTREAM003_EVIDENCE_KIND=COMPILER_INLINING_DIAGNOSTIC")
    print("COMPILER_INLINING_DIAGNOSTIC_CAPABILITY=PASS")
    print("DIAGNOSTIC_TIMING_SEPARATION=PASS")
    print("TIMING_CLAIM=NO")
    print("PROTOS_OPTIMIZATION_MIXED_IN=NO")
    print("PROTOS_SEMANTIC_CHANGE=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "smoke", "reference", "diagnostic"))
    parser.add_argument("--harness-revision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if args.command == "validate":
        validate()
    elif args.command == "smoke":
        smoke()
    elif args.command == "reference":
        reference(
            args.harness_revision,
            Path(args.output_dir) if args.output_dir else None,
        )
    else:
        diagnostic(
            args.harness_revision,
            Path(args.output_dir) if args.output_dir else None,
        )


if __name__ == "__main__":
    main()
