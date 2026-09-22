# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
# THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
# "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

"""PERF010-A / #691 causal semantic/helper-dispatch ablation harness.

Builds two images from the exact same pinned Protos revision - `baseline` (unmodified) and
`ablation` (`docker/protos-perf010a/ablation.patch` applied during the Docker build only,
never published to `guillermomolina/protos`) - and runs the identical PERF004-B2-D/PERF008
four-workload canonical/control matrix (slot-read, closure-call, method-call,
monomorphic-dispatch; N=10,000; warmup=20; steady=100) against both.

Two separate run types are collected per (workload, mode, variant) combination, matching
`AGENTS.work/REPRODUCIBILITY.md` ("Diagnostic instrumentation ... SHOULD be kept separate from
timing when it materially perturbs execution."):

  * TIMING   - `Perf010aTimingDriver` (no JFR); steady per-iteration wall-clock nanoseconds,
               reduced to median/MAD/p95/min/max by this module (raw samples retained).
  * STRUCTURAL - `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (steady-state-only,
               full-bounded-stack JFR), reused unmodified from `docker/protos-perf006d3`.
               Used only to confirm the ablation actually removed the semantic/helper wrapper
               from the sampled call paths (`ProtosSemanticBytecodeRootNodeGen` /
               `InvokeSemanticHelper`) while the helper `continueAt`
               (`ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt`) remains present in
               both variants; never used to interpret timing.

This module does not select or implement a PERF010 optimization. It is a diagnostic ablation
experiment only (`diagnostic_claim: true` in `config/perf010a.json`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf010a.json"
EXPECTED_PROTOS_REVISION = "bc0471184bf6dbbf03d0c6b09ef7b9e28aede014"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
VARIANTS = ("baseline", "ablation")
SEMANTIC_MARKERS = ("ProtosSemanticBytecodeRootNodeGen", "InvokeSemanticHelper.perform")
HELPER_MARKER = "ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt"


def run(command: list[str], *, capture=False, check=True):
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )


def output(command: list[str]) -> str:
    p = run(command, capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed: " + " ".join(command)
            + "\nstdout:\n" + (p.stdout or "")[-5000:]
            + "\nstderr:\n" + (p.stderr or "")[-5000:]
        )
    return (p.stdout or "").rstrip("\n")


def load() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def worktree_harness_revision() -> str:
    """Non-retained declared harness identity for `smoke` only; see `runner/perf008.py`'s
    identically-named helper for the full rationale (mirrors `runner/perf001f.harness_revision`).
    """
    head = output(["git", "rev-parse", "HEAD"])
    dirty = output(["git", "status", "--porcelain", "--untracked-files=all"])
    return head if not dirty else "WORKTREE_PRECOMMIT"


def resolved_harness_revision(explicit: str | None) -> str:
    head = output(["git", "rev-parse", "HEAD"])
    if explicit is None:
        return head
    if explicit != head:
        raise RuntimeError("exact harness revision mismatch")
    return explicit


def validate() -> dict[str, Any]:
    cfg = load()

    assert cfg["perf_item"] == "PERF010-A"
    assert cfg["parent_perf_item"] == "PERF010"
    assert cfg["slice"] == "PERF010A_ABLATION_1"
    assert cfg["diagnostic_claim"] is True
    assert cfg["protos_revision"] == EXPECTED_PROTOS_REVISION
    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 20
    assert cfg["steady_iterations"] == 100
    assert cfg["execution_sample_period"] == "10 ms"
    assert cfg["stack_depth_limit"] == 32
    assert cfg["jfr_recording_phase"] == "steady_only"
    assert cfg["timing_recording_phase"] == "steady_only_no_jfr"
    assert cfg["variants"] == ["baseline", "ablation"]
    assert len(cfg["controls"]) == 4
    assert cfg["external_baseline"]["same_run_as_protos_measurement"] is False

    b2d_cfg = json.loads((ROOT / "config/perf004b2d.json").read_text(encoding="utf-8"))
    assert cfg["controls"] == b2d_cfg["controls"], (
        "PERF010-A must reuse the exact PERF004-B2-D/PERF008 workload matrix unmodified"
    )

    for p in (
        "results/perf004-a/summary.tsv",
        "results/perf004-b2c/summary.tsv",
        "results/perf004-b2d/SHA256SUMS",
        "results/perf006-d3/SHA256SUMS",
        "results/perf008/SHA256SUMS",
    ):
        assert (ROOT / p).is_file(), p

    patch_path = ROOT / cfg["ablation_patch"]
    assert patch_path.is_file(), patch_path
    patch_text = patch_path.read_text(encoding="utf-8")
    for target in cfg["ablation_patch_targets"]:
        assert f"--- a/{target}" in patch_text, target
        assert f"+++ b/{target}" in patch_text, target
    # The patch must remove exactly the semantic wrapper call sites, not touch the lowering
    # or the helper Bytecode interpreter itself.
    assert "ProtosBytecodeRootNode.java" not in patch_text
    assert "CanonicalToBytecodeLowerer.java" not in patch_text
    assert "return helper.getCallTarget();" in patch_text
    assert "this.activationTarget = activationRoot.getCallTarget();" in patch_text
    assert "instanceof ProtosBytecodeRootNode" in patch_text

    dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
    for required in (
        "ARG VARIANT=baseline",
        "ablation.patch",
        "Perf010aTimingDriver.java",
        "Perf008SteadyStateDriver.java",
        "EXPECTED_CONTAINER_IMAGE",
        'if [ "$VARIANT" = "ablation" ]',
    ):
        assert required in dockerfile, required

    timing_driver = (
        ROOT / "docker/protos-perf010a/Perf010aTimingDriver.java"
    ).read_text(encoding="utf-8")
    assert "import jdk.jfr" not in timing_driver, (
        "timing driver must never perturb timing with JFR"
    )
    assert "steady_ns" in timing_driver

    print("PERF010A_CONFIG=PASS")
    print("PERF010A_EXPERIMENT_MATRIX_MATCHES_PERF008=PASS")
    print("PERF010A_PATCH_SHAPE=PASS")
    print("PERF010A_DOCKERFILE_SHAPE=PASS")
    print("PERF010A_TIMING_DRIVER_JFR_FREE=PASS")
    print("PERF010A_PROTOS_REPOSITORY_MODIFICATION=NONE")
    print("PERF010A_WORKLOADS=4")
    return cfg


def first_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return line.split(":", 1)[1].strip().split(",")[0].split("-")[0]
    raise RuntimeError("cannot determine allowed CPU")


def host_identity() -> dict[str, Any]:
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


def build_image(cfg: dict[str, Any], variant: str) -> str:
    assert variant in VARIANTS
    toolchain = cfg["toolchain"]
    tag = f"protos-benchmarks-perf010a-{variant}:" + cfg["protos_revision"][:12]
    run([
        "docker", "build",
        "--build-arg", "GRAAL_BASE=" + toolchain["container_image"],
        "--build-arg", "PROTOS_REPOSITORY=" + cfg["protos_repository"],
        "--build-arg", "PROTOS_REVISION=" + cfg["protos_revision"],
        "--build-arg", "VARIANT=" + variant,
        "--build-arg", "EXPECTED_GRAALVM_RELEASE=" + toolchain["graalvm_release"],
        "--build-arg", "EXPECTED_JDK_VERSION=" + toolchain["jdk_version"],
        "--build-arg", "EXPECTED_CONTAINER_IMAGE=" + toolchain["container_image"],
        "--build-arg", "EXPECTED_GRAAL_COMPONENTS_VERSION=" + toolchain["graal_truffle_version"],
        "--build-arg", "EXPECTED_MAVEN_VERSION=" + toolchain["maven_version"],
        "--build-arg", "PYTHON_PACKAGE=" + toolchain["python_package"],
        "--label", "org.opencontainers.image.revision=" + cfg["protos_revision"],
        "--label", "org.protos-benchmarks.perf010a.variant=" + variant,
        "-t", tag,
        "-f", "docker/protos-perf010a/Dockerfile", ".",
    ])
    return tag


def runtime_probe(tag: str, cpu: str) -> str:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "java", tag,
        "--enable-native-access=ALL-UNNAMED",
        "-cp", "/opt/perf010a/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf006dRuntimeProbe",
    ], capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "")[-4000:])
    observed = next(
        (
            line.split("=", 1)[1].strip()
            for line in (p.stdout or "").splitlines()
            if line.startswith("PERF006D_RUNTIME=")
        ),
        "",
    )
    if observed != EXPECTED_RUNTIME:
        raise RuntimeError(f"runtime mismatch: {observed!r}")
    return observed


def java_version_probe(tag: str, cpu: str) -> str:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "java", tag,
        "-version",
    ], capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("java -version probe failed: " + (p.stderr or "")[-2000:])
    return (p.stderr or p.stdout or "").strip()


def variant_label_probe(tag: str, cpu: str) -> str:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        "/opt/perf010a/variant.txt",
    ], capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("variant probe failed: " + (p.stderr or "")[-2000:])
    return (p.stdout or "").strip()


def control_source(tag: str, work: Path, item: dict[str, Any]) -> tuple[str, Path]:
    canonical_source = "/opt/perf010a/corpus/" + item["source"]
    source_text = output([
        "docker", "run", "--rm",
        "--entrypoint", "/bin/cat", tag,
        canonical_source,
    ])
    if source_text.count(item["replace"]) != 1:
        raise RuntimeError(f"expected exactly one control target in {item['id']}")
    control_text = source_text.replace(item["replace"], item["with"], 1)
    slug = item["id"].replace("/", "__")
    control_host = work / f"{slug}-control.protos"
    control_host.write_text(control_text, encoding="utf-8")
    return canonical_source, control_host


def timing(
    tag: str, cpu: str, work: Path,
    source_host: Path | None, source_container: str,
    expected: str, label: str, warmup: int, steady: int,
) -> dict[str, Any]:
    command = [
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
    ]
    if source_host is not None:
        command += ["--volume", f"{source_host.resolve()}:/work/source.protos:ro"]
        source_container = "/work/source.protos"
    command += ["--entrypoint", "java", tag]
    command += [
        "-Xss128m",
        "--enable-native-access=ALL-UNNAMED",
        "-cp", "/opt/perf010a/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf010aTimingDriver",
        source_container, expected, str(warmup), str(steady),
    ]
    p = run(command, capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            f"timing failed {label} returncode={p.returncode}\n"
            f"stdout:\n{(p.stdout or '')[-6000:]}\nstderr:\n{(p.stderr or '')[-6000:]}"
        )
    lines = [line for line in (p.stdout or "").splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("empty timing output: " + label)
    payload = json.loads(lines[-1])
    steady_ns = [int(v) for v in payload["steady_ns"]]
    if len(steady_ns) != steady:
        raise RuntimeError(f"unexpected steady sample count in {label}: {len(steady_ns)}")
    return {
        "raw": payload,
        "steady_summary": summarize_ns(steady_ns),
    }


def analyze(tag: str, work: Path, jfr: Path, analysis: Path) -> dict[str, Any]:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--volume", f"{work.resolve()}:/work",
        "--entrypoint", "java", tag,
        "--add-modules", "jdk.jfr",
        "-cp", "/opt/perf010a/analyzer",
        "Perf006d3JfrAnalyzer",
        "/work/" + jfr.name,
        "/work/" + analysis.name,
    ], capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            f"JFR analysis failed\nstdout:\n{(p.stdout or '')[-4000:]}\n"
            f"stderr:\n{(p.stderr or '')[-4000:]}"
        )
    return json.loads(analysis.read_text(encoding="utf-8"))


def structural(
    tag: str, cpu: str, work: Path,
    source_host: Path | None, source_container: str,
    expected: str, label: str, warmup: int, steady: int,
) -> dict[str, Any]:
    jfr = work / f"{label}.jfr"
    analysis = work / f"{label}.json"

    command = ["docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu]
    if source_host is not None:
        command += ["--volume", f"{source_host.resolve()}:/work/source.protos:ro"]
        source_container = "/work/source.protos"
    command += ["--volume", f"{work.resolve()}:/work"]
    command += [
        "--entrypoint", "java", tag,
        "-Xss128m",
        "--add-modules", "jdk.jfr",
        "--enable-native-access=ALL-UNNAMED",
        "-cp", "/opt/perf010a/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf008SteadyStateDriver",
        source_container, expected, str(warmup), str(steady),
        "/opt/perf010a/perf010a.jfc",
        "/work/" + jfr.name,
    ]
    p = run(command, capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            f"structural profile failed {label} returncode={p.returncode}\n"
            f"stdout:\n{(p.stdout or '')[-6000:]}\nstderr:\n{(p.stderr or '')[-6000:]}"
        )
    if not jfr.is_file() or jfr.stat().st_size == 0:
        raise RuntimeError("missing JFR: " + label)

    payload = analyze(tag, work, jfr, analysis)
    if payload["execution_samples"]["total"] <= 0:
        raise RuntimeError("no execution samples: " + label)

    markers = marker_presence(payload)
    return {
        "profile": payload,
        "markers": markers,
        "jfr_identity": {
            "sha256": sha256(jfr),
            "size_bytes": jfr.stat().st_size,
            "retained_in_git": False,
        },
    }


def marker_presence(payload: dict[str, Any]) -> dict[str, Any]:
    """Structural-ablation check: substring-matches fully-qualified frame names retained by
    `Perf006d3JfrAnalyzer` (`top_frames`, `call_paths`, `continue_at.callers/callees/stacks`)
    for the semantic-wrapper markers and the helper `continueAt` marker, without modifying the
    analyzer (which aggregates all `*CachedBytecodeNode.continueAt` frames generically)."""
    names: list[str] = []
    names.extend(e["name"] for e in payload["execution_samples"]["top_frames"])
    names.extend(e["name"] for e in payload["execution_samples"]["call_paths"])
    names.extend(e["name"] for e in payload["continue_at"]["callers"])
    names.extend(e["name"] for e in payload["continue_at"]["callees"])
    names.extend(e["name"] for e in payload["continue_at"]["stacks"])
    joined = "\n".join(names)
    semantic_present = {marker: marker in joined for marker in SEMANTIC_MARKERS}
    return {
        "semantic_markers_present": semantic_present,
        "any_semantic_marker_present": any(semantic_present.values()),
        "helper_continue_at_present": HELPER_MARKER in joined,
    }


def run_matrix(cfg: dict[str, Any], tags: dict[str, str], cpu: str, work: Path) -> list[dict[str, Any]]:
    results = []
    for item in cfg["controls"]:
        workload = item["id"]
        slug = workload.replace("/", "__")
        by_variant: dict[str, Any] = {}
        for variant in VARIANTS:
            tag = tags[variant]
            canonical_source, control_host = control_source(tag, work, item)

            by_mode: dict[str, Any] = {}
            for mode, source_host, source_container in (
                ("canonical", None, canonical_source),
                ("control", control_host, "/work/source.protos"),
            ):
                label = f"{slug}-{variant}-{mode}"
                print(f"TIMING BEGIN workload={workload} variant={variant} mode={mode}", flush=True)
                timing_result = timing(
                    tag, cpu, work, source_host, source_container,
                    item["expected"], label, cfg["warmup_iterations"], cfg["steady_iterations"],
                )
                print(
                    f"TIMING PASS workload={workload} variant={variant} mode={mode} "
                    f"median_ns={timing_result['steady_summary']['median_ns']}",
                    flush=True,
                )

                print(f"STRUCTURAL BEGIN workload={workload} variant={variant} mode={mode}", flush=True)
                structural_result = structural(
                    tag, cpu, work, source_host, source_container,
                    item["expected"], label, cfg["warmup_iterations"], cfg["steady_iterations"],
                )
                print(
                    f"STRUCTURAL PASS workload={workload} variant={variant} mode={mode} "
                    f"any_semantic_marker_present={structural_result['markers']['any_semantic_marker_present']} "
                    f"helper_continue_at_present={structural_result['markers']['helper_continue_at_present']}",
                    flush=True,
                )

                by_mode[mode] = {"timing": timing_result, "structural": structural_result}
            by_variant[variant] = by_mode
        results.append({"workload": workload, "variants": by_variant})
    return results


def classify_workload(entry: dict[str, Any]) -> dict[str, Any]:
    baseline = entry["variants"]["baseline"]
    ablation = entry["variants"]["ablation"]

    structural_ok = True
    for mode in ("canonical", "control"):
        b_markers = baseline[mode]["structural"]["markers"]
        a_markers = ablation[mode]["structural"]["markers"]
        if not b_markers["any_semantic_marker_present"]:
            structural_ok = False
        if a_markers["any_semantic_marker_present"]:
            structural_ok = False
        if not (b_markers["helper_continue_at_present"] and a_markers["helper_continue_at_present"]):
            structural_ok = False

    canonical_baseline_ns = baseline["canonical"]["timing"]["steady_summary"]["median_ns"]
    canonical_ablation_ns = ablation["canonical"]["timing"]["steady_summary"]["median_ns"]
    removed_ns = canonical_baseline_ns - canonical_ablation_ns
    removed_fraction_of_baseline = removed_ns / canonical_baseline_ns if canonical_baseline_ns else None

    status = "VALID" if structural_ok else "INVALID"

    return {
        "structural_ablation_confirmed": structural_ok,
        "protos_baseline_steady_median_ns": canonical_baseline_ns,
        "protos_ablation_steady_median_ns": canonical_ablation_ns,
        "removed_ns": removed_ns,
        "removed_fraction_of_baseline": removed_fraction_of_baseline,
        "perf010a_ablation_1": status,
    }


def smoke() -> None:
    cfg = validate()
    harness_revision = worktree_harness_revision()
    cpu = first_cpu()
    tags = {variant: build_image(cfg, variant) for variant in VARIANTS}
    for variant, tag in tags.items():
        runtime = runtime_probe(tag, cpu)
        java_version_probe(tag, cpu)
        observed_variant = variant_label_probe(tag, cpu)
        if observed_variant != variant:
            raise RuntimeError(f"variant label mismatch: expected {variant}, got {observed_variant}")

    with tempfile.TemporaryDirectory(prefix="perf010a-smoke-") as tmp:
        work = Path(tmp)
        matrix = run_matrix(cfg, tags, cpu, work)

    classifications = [classify_workload(entry) for entry in matrix]

    print("PERF010A_SMOKE_HARNESS_REVISION=" + harness_revision)
    print("PERF010A_SMOKE_WORKLOADS=" + str(len(matrix)))
    print("PERF010A_SMOKE_EVIDENCE_UNITS=" + str(len(matrix) * len(VARIANTS) * 2 * 2))
    for entry, classification in zip(matrix, classifications):
        print(
            f"PERF010A_SMOKE_WORKLOAD workload={entry['workload']} "
            f"result={classification['perf010a_ablation_1']} "
            f"structural_confirmed={classification['structural_ablation_confirmed']}"
        )
    print("PERF010A_SMOKE=PASS")
    print("PERF010A_SMOKE_RETAINED=NO")


def reference(harness_revision: str | None, output_dir: Path) -> None:
    cfg = validate()
    harness_revision = resolved_harness_revision(harness_revision)

    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires clean exact harness")

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise RuntimeError("output directory already contains evidence")
        output_dir.rmdir()

    cpu = first_cpu()
    tags = {variant: build_image(cfg, variant) for variant in VARIANTS}
    runtimes = {}
    java_versions = {}
    for variant, tag in tags.items():
        runtimes[variant] = runtime_probe(tag, cpu)
        java_versions[variant] = java_version_probe(tag, cpu)
        observed_variant = variant_label_probe(tag, cpu)
        if observed_variant != variant:
            raise RuntimeError(f"variant label mismatch: expected {variant}, got {observed_variant}")

    with tempfile.TemporaryDirectory(prefix="perf010a-") as tmp:
        work = Path(tmp)
        matrix = run_matrix(cfg, tags, cpu, work)

    classifications = {entry["workload"]: classify_workload(entry) for entry in matrix}
    overall_valid = all(c["perf010a_ablation_1"] == "VALID" for c in classifications.values())

    output_dir.mkdir(parents=True)

    raw = {
        "schema_version": 1,
        "perf_item": "PERF010-A",
        "parent_perf_item": "PERF010",
        "slice": cfg["slice"],
        "diagnostic_claim": True,
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "ablation_patch_sha256": sha256(ROOT / cfg["ablation_patch"]),
        "runtimes": runtimes,
        "java_version_probes": java_versions,
        "toolchain": cfg["toolchain"],
        "host_identity": host_identity(),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "resource_limits": {
            "memory": "no explicit --memory limit set; host default applies",
            "cpu": "no CPU quota/period limit; pinned to one CPU via --cpuset-cpus",
            "network": "none (--network none)",
        },
        "operation_count": cfg["operation_count"],
        "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"],
        "execution_sample_period": cfg["execution_sample_period"],
        "stack_depth_limit": cfg["stack_depth_limit"],
        "jfr_recording_phase": cfg["jfr_recording_phase"],
        "timing_recording_phase": cfg["timing_recording_phase"],
        "external_baseline": cfg["external_baseline"],
        "matrix": matrix,
        "classifications": classifications,
        "overall_result": "VALID" if overall_valid else "INVALID",
    }

    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    rows = [
        "workload\tvariant\tmode\tsteady_median_ns\tsteady_mad_ns\tsteady_p95_ns\t"
        "steady_min_ns\tsteady_max_ns\tany_semantic_marker_present\thelper_continue_at_present"
    ]
    for entry in matrix:
        for variant in VARIANTS:
            for mode in ("canonical", "control"):
                cell = entry["variants"][variant][mode]
                s = cell["timing"]["steady_summary"]
                m = cell["structural"]["markers"]
                rows.append("\t".join([
                    entry["workload"], variant, mode,
                    str(s["median_ns"]), str(s["mad_ns"]), str(s["p95_ns"]),
                    str(s["min_ns"]), str(s["max_ns"]),
                    str(m["any_semantic_marker_present"]), str(m["helper_continue_at_present"]),
                ]))
    (output_dir / "summary.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    attribution_rows = [
        "workload\tPERF010A_ABLATION_1\tstructural_ablation_confirmed\t"
        "protos_baseline_steady_median_ns\tprotos_ablation_steady_median_ns\t"
        "removed_ns\tremoved_fraction_of_baseline"
    ]
    for workload, c in classifications.items():
        attribution_rows.append("\t".join([
            workload, c["perf010a_ablation_1"], str(c["structural_ablation_confirmed"]),
            str(c["protos_baseline_steady_median_ns"]), str(c["protos_ablation_steady_median_ns"]),
            str(c["removed_ns"]), str(c["removed_fraction_of_baseline"]),
        ]))
    (output_dir / "attribution.tsv").write_text(
        "\n".join(attribution_rows) + "\n", encoding="utf-8"
    )

    readme = [
        "# PERF010-A causal semantic/helper-dispatch ablation",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision (baseline and ablation; single checkout, patched in-build for "
        f"the ablation image only): `{cfg['protos_revision']}`",
        f"- Ablation patch: `{cfg['ablation_patch']}` (SHA256 `{raw['ablation_patch_sha256']}`); "
        "never applied to or published in `guillermomolina/protos`.",
        f"- Runtime (baseline): `{runtimes['baseline']}`",
        f"- Runtime (ablation): `{runtimes['ablation']}`",
        f"- GraalVM release: `{cfg['toolchain']['graalvm_release']}`",
        f"- Container image: `{cfg['toolchain']['container_image']}`",
        f"- CPU policy: cpuset-cpus=`{cpu}`; network disabled; no explicit memory limit.",
        "- N=10,000. Warmup=20, steady=100.",
        "- TIMING run: `Perf010aTimingDriver`, no JFR (steady-state wall-clock nanoseconds; "
        "median/MAD/p95/min/max derived from the retained raw per-iteration samples).",
        "- STRUCTURAL run: `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (reused "
        "unmodified from `docker/protos-perf006d3`), steady-state-only JFR, bounded "
        "full call stacks (depth <= 32).",
        "",
        f"## Result",
        "",
        f"PERF010A_ABLATION_1 = {raw['overall_result']}"
        + (
            ""
            if overall_valid
            else " (see per-workload results below; at least one workload's structural "
            "ablation was not confirmed, so its timing is not interpreted as attributable "
            "to the semantic/helper wrapper)"
        ),
        "",
        "Per workload:",
        "",
        "| workload | PERF010A_ABLATION_1 | structural confirmed | baseline steady median (ns) "
        "| ablation steady median (ns) | removed (ns) | removed fraction of baseline |",
        "|---|---|---|---|---|---|---|",
    ]
    for workload, c in classifications.items():
        readme.append(
            f"| {workload} | {c['perf010a_ablation_1']} | {c['structural_ablation_confirmed']} "
            f"| {c['protos_baseline_steady_median_ns']:.0f} "
            f"| {c['protos_ablation_steady_median_ns']:.0f} "
            f"| {c['removed_ns']:.0f} "
            f"| {c['removed_fraction_of_baseline']:.4f} |"
        )

    readme += [
        "",
        "## EXTERNAL_BASELINE_COST",
        "",
        "`results/perf004-a` retains a same-workload cross-language (Python/JavaScript) "
        "steady-state baseline, but at a different Protos revision "
        "(`4a03efc15620b37b2e418b3df30b4a26486446ec`) and a different container base image "
        "(`ol8`, not this harness's `ol10`). Per `AGENTS.work/REPRODUCIBILITY.md`'s revision-"
        "pinning discipline, it is retained here only as a labelled historical reference and "
        "is **not** combined with this Evidence Unit's PROTOS_BASELINE_COST/"
        "PROTOS_ABLATION_COST into EXCESS_COST or ATTRIBUTABLE_FRACTION.",
        "",
        "```",
        "ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED",
        "```",
        "",
        "REMOVED_COST / baseline speedup per workload is reported above and does not require "
        "the external baseline. Establishing ATTRIBUTABLE_FRACTION requires a current-"
        "revision, current-host external (Python/JavaScript) measurement under this same "
        "Evidence Unit, which this reference run does not include.",
        "",
        "## Continuations",
        "",
        "None of the four workloads (`micro/slot-read`, `micro/closure-call`, "
        "`micro/method-call`, `runtime/monomorphic-dispatch`) suspend: they contain no I/O, "
        "actor messaging, or other operation that produces a `ContinuationResult`. "
        "`ProtosBytecodeTaskExecution`'s continuation-forwarding logic is generic over any "
        "`ContinuationResult`-returning `CallTarget` and does not itself branch on "
        "`ProtosSemanticBytecodeRootNode` vs. the bare helper root, so the ablation does not "
        "change observable continuation behavior for this measured experiment.",
        "",
        "## Scope of the ablation",
        "",
        "The semantic/helper wrapper (`ProtosSemanticBytecodeRootNode.wrap(...)`) is created "
        "at two call sites, both bypassed by `ablation.patch`:",
        "",
        "1. `ProtosSourceCompiler.compileBytecode` - the top-level module/program root "
        "(executed once per process in these workloads).",
        "2. `ProtosBytecodeClosureExecutionPlan`'s constructor - the activation root for "
        "every closure and method value (`repeat`, `operation`, `identity`, "
        "`receiver.identity`, `receiver.run`), which is what the 10,000-iteration hot loop "
        "actually calls repeatedly in all four workloads. Ablating only the top-level "
        "compiler entry point would leave this call site - and therefore the measured hot "
        "path - unchanged; both were confirmed present in the pinned revision before the "
        "patch was written (see `docker/protos-perf010a/ablation.patch` inline comments).",
        "",
        "`ProtosRootTaskExecution.isProductionBytecodeRoot` is widened to accept the bare "
        "helper `ProtosBytecodeRootNode` in addition to the semantic wrapper; without this, "
        "every root-task execution in the ablation build throws `IllegalArgumentException` "
        "before producing any result, since compiled roots stop being "
        "`ProtosSemanticBytecodeRootNode` instances. `ProtosBytecodeRootNode` and "
        "`CanonicalToBytecodeLowerer` themselves are untouched.",
        "",
        "This is a diagnostic ablation, not a production optimization candidate; it is "
        "acceptable (and expected) that the ablation build loses the RootTag the semantic "
        "shell provides. Never published to `guillermomolina/protos`.",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    names = ["README.md", "raw.json", "summary.tsv", "attribution.tsv"]
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(f"{sha256(output_dir / n)}  {n}" for n in names) + "\n", encoding="utf-8"
    )

    print("PERF010A_REFERENCE=PASS")
    print("PERF010A_WORKLOADS=" + str(len(matrix)))
    print("PERF010A_EVIDENCE_UNITS=" + str(len(matrix) * len(VARIANTS) * 2 * 2))
    print("PERF010A_ABLATION_1=" + raw["overall_result"])
    print("PERF010A_PROTOS_REPOSITORY_MODIFICATION=NONE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("validate", "smoke", "reference"))
    ap.add_argument(
        "--harness-revision",
        help="optional explicit expected harness SHA; when omitted, current clean HEAD is used",
    )
    ap.add_argument("--output-dir")
    args = ap.parse_args()

    if args.command == "validate":
        validate()
        return

    if args.command == "smoke":
        smoke()
        return

    if not args.output_dir:
        ap.error("reference requires --output-dir")

    reference(args.harness_revision, Path(args.output_dir))


if __name__ == "__main__":
    main()
