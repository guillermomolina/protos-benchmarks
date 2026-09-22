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

"""PERF010-A / #691 causal ablation harness.

Builds two images from the exact same pinned Protos revision - `baseline` (unmodified) and
`ablation` (a diagnostic patch applied during the Docker build only, never published to
`guillermomolina/protos`) - and runs the identical PERF004-B2-D/PERF008 four-workload
canonical/control matrix (slot-read, closure-call, method-call, monomorphic-dispatch;
N=10,000; warmup=20; steady=100) against both.

This module now backs three distinct causal ablations sharing this one harness, selected via
`--ablation` (default `1`, preserving every prior invocation's exact behavior):

  * `--ablation 1` (`config/perf010a.json`, `docker/protos-perf010a/ablation.patch`) -
    PERF010A_ABLATION_1, bypasses the semantic/helper Bytecode dispatch wrapper.
  * `--ablation 2` (`config/perf010a-2.json`, `docker/protos-perf010a/ablation-2.patch`) -
    PERF010A_ABLATION_2, bypasses `ProtosActivation.lookup(name)` with
    `activation.context().readLocalSlot(name)` (`ProtosBytecodeRootNode.Lookup.perform`).
    Diagnostic only; not claimed to be semantically equivalent to `lookup` in the general
    language, and expected to fail closed (correctness FAIL) for any workload whose
    unqualified-name lookups are not resolved by the activation's own local context.
  * `--ablation 3` (`config/perf010a-3.json`, `docker/protos-perf010a/ablation-3.patch`) -
    PERF010A_ABLATION_3, replaces the redundant `containsKey(name)` + `get(name)`
    probe-then-read inside `ProtosObjectValue.readLocalSlot` with a single `get(name)`,
    relying on the invariant that no local slot value is ever null. Unlike ablations 1/2,
    this does not bypass a call site - `ProtosActivation.lookup`'s local/captured-lexical
    traversal, precedence, shadowing, and missing-name behavior are all untouched - so it is
    claimed to be semantically equivalent by construction, not diagnostic-only-and-expected-
    to-fail-closed.

Two separate run types are collected per (workload, mode, variant) combination, matching
`AGENTS.work/REPRODUCIBILITY.md` ("Diagnostic instrumentation ... SHOULD be kept separate from
timing when it materially perturbs execution."):

  * TIMING   - `Perf010aTimingDriver` (no JFR); steady per-iteration wall-clock nanoseconds,
               reduced to median/MAD/p95/min/max by this module (raw samples retained).
  * STRUCTURAL - `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (steady-state-only,
               full-bounded-stack JFR), reused unmodified from `docker/protos-perf006d3`.
               Used only to confirm the ablation actually removed its targeted mechanism from
               the sampled call paths while its counterpart marker remains present in both
               variants (ablation 1: `ProtosSemanticBytecodeRootNodeGen`/
               `InvokeSemanticHelper` absent, `*CachedBytecodeNode.continueAt` present;
               ablation 2: `ProtosActivation.lookup` absent, `ProtosObjectValue.readLocalSlot`
               present); never used to interpret timing. Ablation 3 does not use this
               mechanism for its structural confirmation (see below) but still collects it at
               `reference` scale as supplementary evidence.

Ablation 3's structural confirmation is source-derived, not JFR-derived: `readLocalSlot` is
still called from the exact same call sites with the exact same fully-qualified frame name in
both variants, and `java.util.LinkedHashMap.containsKey`/`get` are simple enough to be
JIT-inlined, so their absence/presence is not a reliable sampled-frame signal. Instead,
`source_structural_probe` reads `/opt/protos-source` (the exact patched-or-unmodified source
tree each image was built from, copied verbatim by the Dockerfile) and inspects
`ProtosObjectValue.readLocalSlot`'s method body directly, scoped to that one method so other
legitimate `containsKey` call sites elsewhere in the file cannot produce a false positive.

`smoke` is an admission/correctness gate, not a reduced reference run: it exercises all four
workloads at a small fixed iteration count (`SMOKE_WARMUP_ITERATIONS`/
`SMOKE_STEADY_ITERATIONS`), independent of each config's `warmup_iterations`/
`steady_iterations` (which stay reference-scale and are never used by `smoke`), and every
steady iteration is still individually correctness-checked by the driver
(`requireCompletedInteger` in `Perf010aTimingDriver`/`Perf008SteadyStateDriver`) regardless of
sample count, so this loses no correctness coverage. `reference` is the only command that uses
each config's full `warmup_iterations`/`steady_iterations` and is the only command whose
output is retained as evidence.

This module does not select or implement a PERF010 optimization. It is a diagnostic ablation
experiment only (`diagnostic_claim: true` in `config/perf010a.json`, `config/perf010a-2.json`,
and `config/perf010a-3.json`).
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
CONFIG_2 = ROOT / "config/perf010a-2.json"
CONFIG_3 = ROOT / "config/perf010a-3.json"
EXPECTED_PROTOS_REVISION = "bc0471184bf6dbbf03d0c6b09ef7b9e28aede014"
EXPECTED_PROTOS_REVISION_3 = "6e7d89194925ba9fa2cd9c5c45aefa72d9939621"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
VARIANTS = ("baseline", "ablation")
ABLATIONS = ("1", "2", "3")

# `smoke` admission/correctness-gate scale: deliberately far smaller than any config's
# reference-scale `warmup_iterations`/`steady_iterations` (20/100). Every steady iteration is
# still individually correctness-checked by the driver regardless of count
# (`requireCompletedInteger` in `Perf010aTimingDriver`/`Perf008SteadyStateDriver`), so this
# does not weaken the correctness assertion `smoke` exists to make; it only avoids collecting
# statistically meaningful timing or reference-scale JFR structural evidence. Historical
# workload steady medians (results/perf010a-1, results/perf010a-2) are tens of milliseconds
# per iteration, comfortably longer than `execution_sample_period` (10 ms), so even this small
# a steady count still yields JFR execution samples for ablations 1/2's structural check.
SMOKE_WARMUP_ITERATIONS = 1
SMOKE_STEADY_ITERATIONS = 2

# Ablation 1 (semantic/helper Bytecode dispatch wrapper) markers.
SEMANTIC_MARKERS = ("ProtosSemanticBytecodeRootNodeGen", "InvokeSemanticHelper.perform")
HELPER_MARKER = "ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt"

# Ablation 2 (ProtosActivation.lookup) markers.
LOOKUP_MARKERS = ("com.guillermomolina.protos.runtime.ProtosActivation.lookup",)
READ_LOCAL_SLOT_MARKER = "com.guillermomolina.protos.runtime.ProtosObjectValue.readLocalSlot"

# Ablation 3 (ProtosObjectValue.readLocalSlot's redundant containsKey+get) source markers.
# Not JFR-frame-based: see module docstring for why. `SOURCE_ROOT` is where the Dockerfile
# copies the exact patched-or-unmodified /src tree in every image (both variants).
SOURCE_ROOT = "/opt/protos-source"
READ_LOCAL_SLOT_SOURCE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java"
ACTIVATION_SOURCE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java"
READ_LOCAL_SLOT_SIGNATURE = "public Optional<Object> readLocalSlot(String name)"
ABLATION_3_MARKER_COMMENT = "PERF010A_ABLATION_3"
CAPTURED_LEXICAL_TRAVERSAL_MARKER = (
    "for (ProtosObjectValue lexicalContext : capturedLexicalContexts)"
)

# Per-ablation config path, expected slice, expected pinned Protos revision, structural-marker
# pair (markers expected absent from a correctly-ablated call path, marker expected present in
# both variants; unused by ablation 3, whose structural confirmation is source-derived - see
# `source_structural_probe`), and the required historical-evidence files `validate()` checks
# for that slice.
ABLATION_PROFILES = {
    "1": {
        "config_path": CONFIG,
        "expected_slice": "PERF010A_ABLATION_1",
        "expected_protos_revision": EXPECTED_PROTOS_REVISION,
        "absent_markers": SEMANTIC_MARKERS,
        "present_marker": HELPER_MARKER,
        "required_files": (
            "results/perf004-a/summary.tsv",
            "results/perf004-b2c/summary.tsv",
            "results/perf004-b2d/SHA256SUMS",
            "results/perf006-d3/SHA256SUMS",
            "results/perf008/SHA256SUMS",
        ),
    },
    "2": {
        "config_path": CONFIG_2,
        "expected_slice": "PERF010A_ABLATION_2",
        "expected_protos_revision": EXPECTED_PROTOS_REVISION,
        "absent_markers": LOOKUP_MARKERS,
        "present_marker": READ_LOCAL_SLOT_MARKER,
        "required_files": (
            "results/perf004-a/summary.tsv",
            "results/perf004-b2c/summary.tsv",
            "results/perf004-b2d/SHA256SUMS",
            "results/perf006-d3/SHA256SUMS",
            "results/perf008/SHA256SUMS",
            "results/perf010a-1/SHA256SUMS",
        ),
    },
    "3": {
        "config_path": CONFIG_3,
        "expected_slice": "PERF010A_ABLATION_3",
        "expected_protos_revision": EXPECTED_PROTOS_REVISION_3,
        "absent_markers": (),
        "present_marker": READ_LOCAL_SLOT_MARKER,
        "required_files": (
            "results/perf004-a/summary.tsv",
            "results/perf004-b2c/summary.tsv",
            "results/perf004-b2d/SHA256SUMS",
            "results/perf006-d3/SHA256SUMS",
            "results/perf008/SHA256SUMS",
            "results/perf010a-1/SHA256SUMS",
            "results/perf010a-2/SHA256SUMS",
        ),
    },
}


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


def load(config_path: Path = CONFIG) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


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


def validate_patch_shape_1(patch_text: str) -> None:
    # The patch must remove exactly the semantic wrapper call sites, not touch the lowering
    # or the helper Bytecode interpreter itself.
    assert "ProtosBytecodeRootNode.java" not in patch_text
    assert "CanonicalToBytecodeLowerer.java" not in patch_text
    assert "return helper.getCallTarget();" in patch_text
    assert "this.activationTarget = activationRoot.getCallTarget();" in patch_text
    assert "instanceof ProtosBytecodeRootNode" in patch_text


def validate_patch_shape_2(patch_text: str) -> None:
    # The patch must touch only ProtosBytecodeRootNode.java's Lookup.perform, replacing
    # activation.lookup(name) with activation.context().readLocalSlot(name), and must not
    # touch any other production mechanism (lowering, RootTag topology, continuation
    # machinery, CallTarget architecture, source/debugger identity).
    assert patch_text.count("--- a/") == 1
    assert "activation.context().readLocalSlot(name)" in patch_text
    for forbidden in (
        "CanonicalToBytecodeLowerer.java",
        "ProtosSourceCompiler.java",
        "ProtosBytecodeClosureExecutionPlan.java",
        "ProtosRootTaskExecution.java",
        "continueAt",
        "RootTag",
        "ContinuationResult",
        "ProtosSemanticBytecodeRootNode",
    ):
        assert forbidden not in patch_text, forbidden


def validate_patch_shape_3(patch_text: str) -> None:
    # The patch must touch only ProtosObjectValue.java, replacing the redundant
    # containsKey(name)+get(name) probe-then-read inside readLocalSlot with a single
    # get(name) plus a null discrimination, and must not touch ProtosActivation.java (the
    # local/captured-lexical traversal, precedence, shadowing, and missing-name behavior all
    # live there and must stay byte-for-byte untouched) or any other production mechanism.
    assert patch_text.count("--- a/") == 1
    assert "--- a/src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java" in patch_text
    assert ABLATION_3_MARKER_COMMENT in patch_text
    assert "localSlots.get(name)" in patch_text
    assert "value != null" in patch_text
    for forbidden in (
        "ProtosActivation.java",
        "ProtosBytecodeRootNode.java",
        "CanonicalToBytecodeLowerer.java",
        "ProtosSourceCompiler.java",
        "ProtosBytecodeClosureExecutionPlan.java",
        "ProtosRootTaskExecution.java",
        "capturedLexicalContexts",
        "continueAt",
        "RootTag",
        "ContinuationResult",
        "ProtosSemanticBytecodeRootNode",
    ):
        assert forbidden not in patch_text, forbidden


VALIDATE_PATCH_SHAPE = {
    "1": validate_patch_shape_1,
    "2": validate_patch_shape_2,
    "3": validate_patch_shape_3,
}


def validate(ablation: str = "1") -> dict[str, Any]:
    assert ablation in ABLATIONS, ablation
    profile = ABLATION_PROFILES[ablation]
    cfg = load(profile["config_path"])

    assert cfg["perf_item"] == "PERF010-A"
    assert cfg["parent_perf_item"] == "PERF010"
    assert cfg["slice"] == profile["expected_slice"]
    assert cfg["diagnostic_claim"] is True
    assert cfg["protos_revision"] == profile["expected_protos_revision"]
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

    for p in profile["required_files"]:
        assert (ROOT / p).is_file(), p

    patch_path = ROOT / cfg["ablation_patch"]
    assert patch_path.is_file(), patch_path
    patch_text = patch_path.read_text(encoding="utf-8")
    for target in cfg["ablation_patch_targets"]:
        assert f"--- a/{target}" in patch_text, target
        assert f"+++ b/{target}" in patch_text, target
    VALIDATE_PATCH_SHAPE[ablation](patch_text)

    dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
    for required in (
        "ARG VARIANT=baseline",
        "ARG ABLATION_PATCH=ablation.patch",
        "${ABLATION_PATCH}",
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
    print(f"PERF010A_ABLATION_SELECTED={profile['expected_slice']}")
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


def build_image(cfg: dict[str, Any], variant: str, ablation: str = "1") -> str:
    assert variant in VARIANTS
    assert ablation in ABLATIONS
    toolchain = cfg["toolchain"]
    ablation_patch_name = Path(cfg["ablation_patch"]).name
    tag = (
        f"protos-benchmarks-perf010a-ablation{ablation}-{variant}:"
        + cfg["protos_revision"][:12]
    )
    run([
        "docker", "build",
        "--build-arg", "GRAAL_BASE=" + toolchain["container_image"],
        "--build-arg", "PROTOS_REPOSITORY=" + cfg["protos_repository"],
        "--build-arg", "PROTOS_REVISION=" + cfg["protos_revision"],
        "--build-arg", "VARIANT=" + variant,
        "--build-arg", "ABLATION_PATCH=" + ablation_patch_name,
        "--build-arg", "ABLATION_SLICE=" + cfg["slice"],
        "--build-arg", "EXPECTED_GRAALVM_RELEASE=" + toolchain["graalvm_release"],
        "--build-arg", "EXPECTED_JDK_VERSION=" + toolchain["jdk_version"],
        "--build-arg", "EXPECTED_CONTAINER_IMAGE=" + toolchain["container_image"],
        "--build-arg", "EXPECTED_GRAAL_COMPONENTS_VERSION=" + toolchain["graal_truffle_version"],
        "--build-arg", "EXPECTED_MAVEN_VERSION=" + toolchain["maven_version"],
        "--build-arg", "PYTHON_PACKAGE=" + toolchain["python_package"],
        "--label", "org.opencontainers.image.revision=" + cfg["protos_revision"],
        "--label", "org.protos-benchmarks.perf010a.variant=" + variant,
        "--label", "org.protos-benchmarks.perf010a.ablation-slice=" + cfg["slice"],
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


def ablation_slice_label_probe(tag: str, cpu: str) -> str:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        "/opt/perf010a/ablation-slice.txt",
    ], capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("ablation-slice probe failed: " + (p.stderr or "")[-2000:])
    return (p.stdout or "").strip()


def _extract_method_body(source_text: str, signature: str) -> str:
    """Returns the exact `{ ... }` body of the method whose declaration line contains
    `signature`, by brace-depth counting from the first `{` after it. Used to scope ablation
    3's structural markers to the single target method, so other legitimate `containsKey`
    call sites elsewhere in the same file cannot produce a false positive."""
    start = source_text.index(signature)
    brace_start = source_text.index("{", start)
    depth = 0
    i = brace_start
    while True:
        ch = source_text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source_text[brace_start : i + 1]
        i += 1


def source_structural_probe(tag: str, cpu: str) -> dict[str, bool]:
    """Ablation 3's structural confirmation. `ProtosObjectValue.readLocalSlot` is called from
    the exact same call sites with the exact same fully-qualified frame name in both variants
    (unlike ablations 1/2, which bypass a call site entirely), and the ablated
    `java.util.LinkedHashMap.containsKey`/`get` are simple enough to be JIT-inlined, so their
    absence/presence is not a reliable JFR-sampled-frame signal (see module docstring). This
    instead reads `/opt/protos-source` - the exact patched-or-unmodified source tree the image
    was built from, copied verbatim by the Dockerfile - and inspects `readLocalSlot`'s method
    body directly."""
    object_value_source = output([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        f"{SOURCE_ROOT}/{READ_LOCAL_SLOT_SOURCE_PATH}",
    ])
    activation_source = output([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        f"{SOURCE_ROOT}/{ACTIVATION_SOURCE_PATH}",
    ])
    method_body = _extract_method_body(object_value_source, READ_LOCAL_SLOT_SIGNATURE)
    return {
        "marker_present": ABLATION_3_MARKER_COMMENT in method_body,
        "contains_key_absent": "containsKey" not in method_body,
        "single_get_present": method_body.count(".get(name)") == 1,
        "captured_lexical_traversal_present": (
            CAPTURED_LEXICAL_TRAVERSAL_MARKER in activation_source
        ),
    }


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
    absent_markers: tuple[str, ...] = SEMANTIC_MARKERS,
    present_marker: str = HELPER_MARKER,
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

    markers = marker_presence(payload, absent_markers, present_marker)
    return {
        "profile": payload,
        "markers": markers,
        "jfr_identity": {
            "sha256": sha256(jfr),
            "size_bytes": jfr.stat().st_size,
            "retained_in_git": False,
        },
    }


def marker_presence(
    payload: dict[str, Any],
    absent_markers: tuple[str, ...] = SEMANTIC_MARKERS,
    present_marker: str = HELPER_MARKER,
) -> dict[str, Any]:
    """Structural-ablation check: substring-matches fully-qualified frame names retained by
    `Perf006d3JfrAnalyzer` (`top_frames`, `call_paths`, `continue_at.callers/callees/stacks`)
    against `absent_markers` (expected gone from a correctly-ablated call path - the
    semantic-wrapper markers for ablation 1, `ProtosActivation.lookup` for ablation 2) and
    `present_marker` (expected present in both variants - the helper `continueAt` marker for
    ablation 1, `ProtosObjectValue.readLocalSlot` for ablation 2), without modifying the
    analyzer (which aggregates all `*CachedBytecodeNode.continueAt` frames generically). Field
    names are kept generic across both ablations' call sites."""
    names: list[str] = []
    names.extend(e["name"] for e in payload["execution_samples"]["top_frames"])
    names.extend(e["name"] for e in payload["execution_samples"]["call_paths"])
    names.extend(e["name"] for e in payload["continue_at"]["callers"])
    names.extend(e["name"] for e in payload["continue_at"]["callees"])
    names.extend(e["name"] for e in payload["continue_at"]["stacks"])
    joined = "\n".join(names)
    semantic_present = {marker: marker in joined for marker in absent_markers}
    return {
        "semantic_markers_present": semantic_present,
        "any_semantic_marker_present": any(semantic_present.values()),
        "helper_continue_at_present": present_marker in joined,
    }


def run_matrix(
    cfg: dict[str, Any], tags: dict[str, str], cpu: str, work: Path,
    absent_markers: tuple[str, ...] = SEMANTIC_MARKERS,
    present_marker: str = HELPER_MARKER,
    *,
    warmup: int | None = None,
    steady: int | None = None,
    collect_structural: bool = True,
) -> list[dict[str, Any]]:
    # `warmup`/`steady` default to the config's reference-scale values (used by `reference`);
    # `smoke` passes SMOKE_WARMUP_ITERATIONS/SMOKE_STEADY_ITERATIONS explicitly instead, since
    # it is an admission/correctness gate, not a reduced reference run (see module docstring).
    warmup = cfg["warmup_iterations"] if warmup is None else warmup
    steady = cfg["steady_iterations"] if steady is None else steady
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

                # A baseline execution failure is a harness/infrastructure problem (the
                # unmodified Protos build is expected to always complete) and aborts hard, as
                # before. An ablation execution failure is itself possible evidence (the
                # diagnostic bypass fails closed) and is captured instead of aborting the
                # whole run, so the other workloads/modes still get attempted and the exact
                # failure is retained per this slice's correctness-before-timing contract.
                timing_result = None
                structural_result = None
                execution_failure = None
                print(f"TIMING BEGIN workload={workload} variant={variant} mode={mode}", flush=True)
                try:
                    timing_result = timing(
                        tag, cpu, work, source_host, source_container,
                        item["expected"], label, warmup, steady,
                    )
                    print(
                        f"TIMING PASS workload={workload} variant={variant} mode={mode} "
                        f"median_ns={timing_result['steady_summary']['median_ns']}",
                        flush=True,
                    )
                except RuntimeError as exc:
                    if variant != "ablation":
                        raise
                    execution_failure = {"stage": "timing", "detail": str(exc)[:6000]}
                    print(
                        f"TIMING FAIL workload={workload} variant={variant} mode={mode} "
                        f"detail={execution_failure['detail'][:200]!r}",
                        flush=True,
                    )

                if execution_failure is None and collect_structural:
                    print(f"STRUCTURAL BEGIN workload={workload} variant={variant} mode={mode}", flush=True)
                    try:
                        structural_result = structural(
                            tag, cpu, work, source_host, source_container,
                            item["expected"], label, warmup, steady,
                            absent_markers, present_marker,
                        )
                        print(
                            f"STRUCTURAL PASS workload={workload} variant={variant} mode={mode} "
                            f"any_semantic_marker_present={structural_result['markers']['any_semantic_marker_present']} "
                            f"helper_continue_at_present={structural_result['markers']['helper_continue_at_present']}",
                            flush=True,
                        )
                    except RuntimeError as exc:
                        if variant != "ablation":
                            raise
                        execution_failure = {"stage": "structural", "detail": str(exc)[:6000]}
                        print(
                            f"STRUCTURAL FAIL workload={workload} variant={variant} mode={mode} "
                            f"detail={execution_failure['detail'][:200]!r}",
                            flush=True,
                        )
                elif execution_failure is None:
                    print(
                        f"STRUCTURAL SKIPPED workload={workload} variant={variant} mode={mode} "
                        "(source-marker structural mode; see source_structural_probe)",
                        flush=True,
                    )

                by_mode[mode] = {
                    "timing": timing_result,
                    "structural": structural_result,
                    "execution_failure": execution_failure,
                }
            by_variant[variant] = by_mode
        results.append({"workload": workload, "variants": by_variant})
    return results


def classify_workload(
    entry: dict[str, Any],
    ablation: str = "1",
    source_markers: dict[str, dict[str, bool]] | None = None,
) -> dict[str, Any]:
    baseline = entry["variants"]["baseline"]
    ablation_variant = entry["variants"]["ablation"]

    execution_failures = {
        mode: ablation_variant[mode]["execution_failure"]
        for mode in ("canonical", "control")
        if ablation_variant[mode]["execution_failure"] is not None
    }
    correctness_confirmed = not execution_failures

    structural_ok = correctness_confirmed
    if correctness_confirmed and ablation == "3":
        # Source-derived, not JFR-derived (see source_structural_probe): a single per-image
        # check, identical across all four workloads, rather than a per-workload JFR profile.
        if source_markers is None:
            structural_ok = False
        else:
            b_src = source_markers["baseline"]
            a_src = source_markers["ablation"]
            structural_ok = (
                a_src["marker_present"]
                and a_src["contains_key_absent"]
                and a_src["single_get_present"]
                and a_src["captured_lexical_traversal_present"]
                and b_src["captured_lexical_traversal_present"]
                and not b_src["marker_present"]
                and not b_src["contains_key_absent"]
            )
    elif correctness_confirmed:
        for mode in ("canonical", "control"):
            b_markers = baseline[mode]["structural"]["markers"]
            a_markers = ablation_variant[mode]["structural"]["markers"]
            if not b_markers["any_semantic_marker_present"]:
                structural_ok = False
            if a_markers["any_semantic_marker_present"]:
                structural_ok = False
            if not (b_markers["helper_continue_at_present"] and a_markers["helper_continue_at_present"]):
                structural_ok = False

    canonical_baseline_ns = baseline["canonical"]["timing"]["steady_summary"]["median_ns"]
    canonical_ablation_ns = (
        ablation_variant["canonical"]["timing"]["steady_summary"]["median_ns"]
        if correctness_confirmed
        else None
    )
    removed_ns = (
        canonical_baseline_ns - canonical_ablation_ns
        if canonical_ablation_ns is not None
        else None
    )
    removed_fraction_of_baseline = (
        removed_ns / canonical_baseline_ns
        if removed_ns is not None and canonical_baseline_ns
        else None
    )

    status = "VALID" if structural_ok else "INVALID"

    return {
        "correctness_confirmed": correctness_confirmed,
        "execution_failures": execution_failures,
        "structural_ablation_confirmed": structural_ok,
        "protos_baseline_steady_median_ns": canonical_baseline_ns,
        "protos_ablation_steady_median_ns": canonical_ablation_ns,
        "removed_ns": removed_ns,
        "removed_fraction_of_baseline": removed_fraction_of_baseline,
        f"perf010a_ablation_{ablation}": status,
    }


def smoke(ablation: str = "1") -> None:
    assert ablation in ABLATIONS
    profile = ABLATION_PROFILES[ablation]
    status_key = f"perf010a_ablation_{ablation}"
    cfg = validate(ablation)
    harness_revision = worktree_harness_revision()
    cpu = first_cpu()
    tags = {variant: build_image(cfg, variant, ablation) for variant in VARIANTS}
    for variant, tag in tags.items():
        runtime = runtime_probe(tag, cpu)
        java_version_probe(tag, cpu)
        observed_variant = variant_label_probe(tag, cpu)
        if observed_variant != variant:
            raise RuntimeError(f"variant label mismatch: expected {variant}, got {observed_variant}")
        observed_slice = ablation_slice_label_probe(tag, cpu)
        expected_slice = profile["expected_slice"] if variant == "ablation" else "none"
        if observed_slice != expected_slice:
            raise RuntimeError(
                f"ablation-slice label mismatch: expected {expected_slice}, got {observed_slice}"
            )

    # Ablation 3's structural confirmation is a single per-image source-marker check (see
    # source_structural_probe), not a per-workload JFR profile, so smoke skips the JFR
    # structural stage for it entirely (collect_structural=False below) rather than running it
    # at any scale. Ablations 1/2 still need JFR to confirm their call-site bypass is actually
    # in effect - that is the "specific correctness assertion" this admission gate exists to
    # make - so they keep it, just at SMOKE_* scale instead of the config's reference scale.
    source_markers = (
        {variant: source_structural_probe(tags[variant], cpu) for variant in VARIANTS}
        if ablation == "3"
        else None
    )

    with tempfile.TemporaryDirectory(prefix="perf010a-smoke-") as tmp:
        work = Path(tmp)
        matrix = run_matrix(
            cfg, tags, cpu, work, profile["absent_markers"], profile["present_marker"],
            warmup=SMOKE_WARMUP_ITERATIONS, steady=SMOKE_STEADY_ITERATIONS,
            collect_structural=(ablation != "3"),
        )

    classifications = [
        classify_workload(entry, ablation, source_markers) for entry in matrix
    ]

    print("PERF010A_SMOKE_HARNESS_REVISION=" + harness_revision)
    print(f"PERF010A_SMOKE_SLICE={profile['expected_slice']}")
    print(
        f"PERF010A_SMOKE_SCALE=warmup={SMOKE_WARMUP_ITERATIONS} steady={SMOKE_STEADY_ITERATIONS}"
        f" (reference scale: warmup={cfg['warmup_iterations']} steady={cfg['steady_iterations']})"
    )
    print("PERF010A_SMOKE_WORKLOADS=" + str(len(matrix)))
    print("PERF010A_SMOKE_EVIDENCE_UNITS=" + str(len(matrix) * len(VARIANTS) * 2 * 2))
    if source_markers is not None:
        print("PERF010A_SMOKE_SOURCE_MARKERS_BASELINE=" + json.dumps(source_markers["baseline"]))
        print("PERF010A_SMOKE_SOURCE_MARKERS_ABLATION=" + json.dumps(source_markers["ablation"]))
    for entry, classification in zip(matrix, classifications):
        print(
            f"PERF010A_SMOKE_WORKLOAD workload={entry['workload']} "
            f"result={classification[status_key]} "
            f"structural_confirmed={classification['structural_ablation_confirmed']}"
        )
    print("PERF010A_SMOKE=PASS")
    print("PERF010A_SMOKE_RETAINED=NO")


def scope_of_ablation_readme(ablation: str, cfg: dict[str, Any]) -> list[str]:
    if ablation == "3":
        return [
            "## Scope of the ablation",
            "",
            "`ProtosObjectValue.readLocalSlot` (called from `ProtosActivation.lookup`'s own "
            "local context and captured-lexical-context walk, and from many other production "
            "call sites throughout the codebase) is the single method transformed by "
            "`ablation-3.patch`: the redundant `localSlots.containsKey(name)` probe followed "
            "by a second `localSlots.get(name)` read is replaced with a single "
            "`localSlots.get(name)`, discriminating ABSENT from any stored value via "
            "`localSlots`' own invariant that no local slot value is ever null "
            "(`createLocalSlot`/`assignLocalSlot` both require `Objects.requireNonNull(value, "
            "...)`; `composeLocalSlotsFrom` only copies values already subject to that "
            "invariant from another `ProtosObjectValue`).",
            "",
            "Unlike ablations 1 and 2, this is **not** a call-site bypass: `readLocalSlot` is "
            "called from exactly the same sites, in exactly the same order, with exactly the "
            "same fully-qualified name, in both variants. `ProtosActivation.lookup`'s local-"
            "context-then-captured-lexical-contexts-then-receiver/prelude-fallback traversal, "
            "lexical precedence, shadowing, and missing-name behavior are all untouched by "
            "this patch (`ProtosActivation.java` is not one of `ablation-3.patch`'s targets). "
            "This transformation is therefore claimed to be semantically equivalent by "
            "construction, not diagnostic-only-and-expected-to-fail-closed like ablation 2.",
            "",
            "Because `readLocalSlot`'s call sites and frame name are unchanged, this "
            "ablation's structural confirmation is source-derived rather than JFR-derived: "
            "`java.util.LinkedHashMap.containsKey`/`get` are simple enough to be JIT-inlined "
            "and are not a reliable sampled-frame signal either way. `source_structural_probe` "
            "reads `/opt/protos-source` (the exact patched-or-unmodified source tree the image "
            "was built from) and confirms, scoped to `readLocalSlot`'s own method body: the "
            "diagnostic marker comment is present, the redundant `containsKey` probe is "
            "absent, the single `get(name)` read is present (ablation variant only), and "
            "`ProtosActivation.lookup`'s captured-lexical-context traversal loop is present, "
            "byte-for-byte unchanged, in both variants.",
            "",
            "`ProtosActivation.java`, `ProtosBytecodeRootNode.java`, "
            "`CanonicalToBytecodeLowerer.java`, the RootTag topology, the continuation "
            "machinery, the `CallTarget` architecture, and source/debugger identity are all "
            "untouched by this patch. This is a diagnostic ablation, not (by itself) a "
            "production optimization change; per this slice's scope, no change is made to "
            "`guillermomolina/protos` regardless of this experiment's outcome. Never "
            "published to `guillermomolina/protos`.",
        ]
    if ablation == "1":
        return [
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
    return [
        "## Scope of the ablation",
        "",
        "`ProtosBytecodeRootNode.Lookup.perform` (the unqualified-name-lookup Bytecode "
        "operation) is the single call site bypassed by `ablation-2.patch`: "
        "`activation.lookup(name)` (activation's own local context, then captured lexical "
        "contexts, then the receiver/prelude member fallback - "
        "`ProtosActivation.lookup(String)`) is replaced with "
        "`activation.context().readLocalSlot(name)` (`ProtosObjectValue.readLocalSlot`), "
        "reading only the activation's own local context slot directly.",
        "",
        "This diagnostic bypass is **not** claimed to be semantically equivalent to "
        "`activation.lookup(name)` in the general language: it silently drops the captured-"
        "lexical-context walk and the receiver/prelude member fallback that `lookup` performs "
        "for any name not bound as a direct local slot of the activation's own context. It is "
        "expected to fail closed (a `ProtosSignalException` from the unchanged "
        "`orElseThrow(...)` below the bypass, surfacing as a non-`COMPLETED` execution outcome "
        "and a driver-level correctness failure) for any workload whose unqualified-name "
        "lookups are not resolved by the activation's own local context - which is the case "
        "for all four PERF010-A workloads' hot-path references to their top-level module "
        "bindings (`repeat`, `sink`, `holder`, `identity`, `receiver`), captured into each "
        "closure's `capturedLexicalContexts` rather than its own fresh, per-invocation "
        "`context`. Per `AGENTS.work/PERFORMANCE.md`'s and this slice's own correctness-"
        "before-timing rule, a workload that fails this way contributes no timing evidence "
        "and is reported `INVALID`, not adjusted to pass.",
        "",
        "`ProtosBytecodeRootNode`, `CanonicalToBytecodeLowerer`, the RootTag topology, the "
        "continuation machinery, the `CallTarget` architecture, and source/debugger identity "
        "are all untouched by this patch. This is a diagnostic ablation, not a production "
        "optimization candidate. Never published to `guillermomolina/protos`.",
    ]


def reference(harness_revision: str | None, output_dir: Path, ablation: str = "1") -> None:
    assert ablation in ABLATIONS
    profile = ABLATION_PROFILES[ablation]
    status_key = f"perf010a_ablation_{ablation}"
    cfg = validate(ablation)
    harness_revision = resolved_harness_revision(harness_revision)

    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires clean exact harness")

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise RuntimeError("output directory already contains evidence")
        output_dir.rmdir()

    cpu = first_cpu()
    tags = {variant: build_image(cfg, variant, ablation) for variant in VARIANTS}
    runtimes = {}
    java_versions = {}
    for variant, tag in tags.items():
        runtimes[variant] = runtime_probe(tag, cpu)
        java_versions[variant] = java_version_probe(tag, cpu)
        observed_variant = variant_label_probe(tag, cpu)
        if observed_variant != variant:
            raise RuntimeError(f"variant label mismatch: expected {variant}, got {observed_variant}")
        observed_slice = ablation_slice_label_probe(tag, cpu)
        expected_slice = profile["expected_slice"] if variant == "ablation" else "none"
        if observed_slice != expected_slice:
            raise RuntimeError(
                f"ablation-slice label mismatch: expected {expected_slice}, got {observed_slice}"
            )

    source_markers = (
        {variant: source_structural_probe(tags[variant], cpu) for variant in VARIANTS}
        if ablation == "3"
        else None
    )

    with tempfile.TemporaryDirectory(prefix="perf010a-") as tmp:
        work = Path(tmp)
        matrix = run_matrix(
            cfg, tags, cpu, work, profile["absent_markers"], profile["present_marker"]
        )

    classifications = {
        entry["workload"]: classify_workload(entry, ablation, source_markers)
        for entry in matrix
    }
    overall_valid = all(c[status_key] == "VALID" for c in classifications.values())

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
        "source_structural_markers": source_markers,
        "matrix": matrix,
        "classifications": classifications,
        "overall_result": "VALID" if overall_valid else "INVALID",
    }

    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    rows = [
        "workload\tvariant\tmode\tsteady_median_ns\tsteady_mad_ns\tsteady_p95_ns\t"
        "steady_min_ns\tsteady_max_ns\tany_semantic_marker_present\thelper_continue_at_present\t"
        "execution_failure_stage"
    ]
    for entry in matrix:
        for variant in VARIANTS:
            for mode in ("canonical", "control"):
                cell = entry["variants"][variant][mode]
                failure = cell["execution_failure"]
                if failure is not None:
                    rows.append("\t".join([
                        entry["workload"], variant, mode,
                        "NA", "NA", "NA", "NA", "NA", "NA", "NA", failure["stage"],
                    ]))
                    continue
                s = cell["timing"]["steady_summary"]
                m = cell["structural"]["markers"]
                rows.append("\t".join([
                    entry["workload"], variant, mode,
                    str(s["median_ns"]), str(s["mad_ns"]), str(s["p95_ns"]),
                    str(s["min_ns"]), str(s["max_ns"]),
                    str(m["any_semantic_marker_present"]), str(m["helper_continue_at_present"]),
                    "",
                ]))
    (output_dir / "summary.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    attribution_rows = [
        f"workload\t{cfg['slice']}\tstructural_ablation_confirmed\t"
        "protos_baseline_steady_median_ns\tprotos_ablation_steady_median_ns\t"
        "removed_ns\tremoved_fraction_of_baseline"
    ]
    for workload, c in classifications.items():
        attribution_rows.append("\t".join([
            workload, c[status_key], str(c["structural_ablation_confirmed"]),
            str(c["protos_baseline_steady_median_ns"]), str(c["protos_ablation_steady_median_ns"]),
            str(c["removed_ns"]), str(c["removed_fraction_of_baseline"]),
        ]))
    (output_dir / "attribution.tsv").write_text(
        "\n".join(attribution_rows) + "\n", encoding="utf-8"
    )

    readme = [
        f"# PERF010-A causal ablation ({cfg['slice']}, {cfg['phase']})",
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
        f"{cfg['slice']} = {raw['overall_result']}"
        + (
            ""
            if overall_valid
            else " (see per-workload results below; at least one workload's structural "
            "ablation was not confirmed and/or failed correctness, so its timing is not "
            "interpreted as attributable to the ablated mechanism)"
        ),
        "",
        "Per workload:",
        "",
        f"| workload | {cfg['slice']} | structural confirmed | baseline steady median (ns) "
        "| ablation steady median (ns) | removed (ns) | removed fraction of baseline |",
        "|---|---|---|---|---|---|---|",
    ]
    def fmt(value: float | None, spec: str) -> str:
        return format(value, spec) if value is not None else "NA (correctness FAIL)"

    for workload, c in classifications.items():
        readme.append(
            f"| {workload} | {c[status_key]} | {c['structural_ablation_confirmed']} "
            f"| {fmt(c['protos_baseline_steady_median_ns'], '.0f')} "
            f"| {fmt(c['protos_ablation_steady_median_ns'], '.0f')} "
            f"| {fmt(c['removed_ns'], '.0f')} "
            f"| {fmt(c['removed_fraction_of_baseline'], '.4f')} |"
        )

    any_correctness_failure = any(
        not c["correctness_confirmed"] for c in classifications.values()
    )
    if any_correctness_failure:
        readme += [
            "",
            "## Correctness failures",
            "",
            "Per this slice's fail-closed contract, the diagnostic bypass was not adjusted to "
            "make any of the following pass; each is recorded here exactly as observed "
            "(`raw.json`'s `matrix[].variants.ablation[mode].execution_failure` carries the "
            "full, untruncated detail) and its workload is reported `INVALID` above with no "
            "timing claimed for the ablation variant.",
            "",
        ]
        for workload, c in classifications.items():
            for mode, failure in c["execution_failures"].items():
                readme += [
                    f"- `{workload}` ({mode}, {failure['stage']} stage):",
                    "  ```",
                    *(f"  {line}" for line in failure["detail"].splitlines()[:40]),
                    "  ```",
                ]

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
    ]
    readme += scope_of_ablation_readme(ablation, cfg)
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    names = ["README.md", "raw.json", "summary.tsv", "attribution.tsv"]
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(f"{sha256(output_dir / n)}  {n}" for n in names) + "\n", encoding="utf-8"
    )

    print("PERF010A_REFERENCE=PASS")
    print("PERF010A_WORKLOADS=" + str(len(matrix)))
    print("PERF010A_EVIDENCE_UNITS=" + str(len(matrix) * len(VARIANTS) * 2 * 2))
    print(f"{cfg['slice']}=" + raw["overall_result"])
    print("PERF010A_PROTOS_REPOSITORY_MODIFICATION=NONE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("validate", "smoke", "reference"))
    ap.add_argument(
        "--harness-revision",
        help="optional explicit expected harness SHA; when omitted, current clean HEAD is used",
    )
    ap.add_argument("--output-dir")
    ap.add_argument(
        "--ablation",
        choices=ABLATIONS,
        default="1",
        help="which causal ablation slice to run: 1 (semantic/helper Bytecode dispatch, "
        "default), 2 (ProtosActivation.lookup), or 3 (ProtosObjectValue.readLocalSlot's "
        "redundant containsKey+get)",
    )
    args = ap.parse_args()

    if args.command == "validate":
        validate(args.ablation)
        return

    if args.command == "smoke":
        smoke(args.ablation)
        return

    if not args.output_dir:
        ap.error("reference requires --output-dir")

    reference(args.harness_revision, Path(args.output_dir), args.ablation)


if __name__ == "__main__":
    main()
