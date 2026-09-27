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

"""PERF014 / guillermomolina/protos#725 direct Closure-call final causal timing comparator.

Answers one question, and only one: how much does the final PERF014 direct Closure-call
implementation (a definition-keyed `fastDirect` second tier - `ProtosClosureValue.definition()` ->
`CanonicalClosure` -> entered `Context` -> Context-owned `RootCallTarget` - layered on top of the
first-tier receiver-identity-keyed mechanism, while preserving dynamic Closure semantic instance
identity and executing the D013 `call` authoritative selection on every hit) reduce the
steady-state cost of a guest Closure call, once the workload-control's own measured movement
between the two product revisions has been subtracted out? PERF014's structural product
validation (`DIRECT_CLOSURE_STABLE_SELECTION`, `DIRECT_CLOSURE_CONTEXT_OWNED_TARGET`,
`DIRECT_CLOSURE_DIRECT_CALL_NODE`, `DEFINITION_KEYED_SECOND_TIER`, `CALL_SHADOWING_PRESERVED`,
`GENERIC_FALLBACK_PRESERVED`, `OBSERVABLE_PROTOS_SEMANTIC_CHANGE=NO`,
`FINAL_REQUIRED_VALIDATION=PASS`) is already complete and is NOT re-validated by this module; this
module is the causal-attribution owner for the timing question only
(`config/perf014-direct-closure-call.json`'s `causal_question`).

Two revisions, both `VARIANT=baseline`, no patch ever applied to either image
(`docker/protos-perf010a/Dockerfile` only applies a patch when `VARIANT=ablation`, which this
module never requests):

  * CONTROL - PERF013 B2, `0af8960363a557dad1b87968cf8a632e4716ee8a` (`0.3.102-SNAPSHOT`). The
    exact baseline PERF014 was built against.
  * INTERVENTION - the final published PERF014 product revision,
    `bcf9eda164d840b0a0b4201753fe5289347afa8a` (`0.3.105-SNAPSHOT`).

Unlike `runner/perf010a_post_i072_fprime.py`'s intervention (which did not exist yet at that
module's authoring time and was therefore a run-time evidence identity supplied by the human), both
PERF014 revisions here are already published and known, so both are pinned constants in this module
and in `config/perf014-direct-closure-call.json`, matching `runner/perf010a.py`'s Phase 2 comparator
shape (`PHASE2_EXPECTED_CONTROL_REVISION`/`PHASE2_EXPECTED_INTERVENTION_REVISION`) instead.

Control and intervention are deliberately NOT described as a direct PERF014-only parent/child
commit pair: `eab6a367c16dea0136e1aabb13a7da681c4839b0` (`0.3.104-SNAPSHOT`, BUG010) sits in the
intervention's ancestry between the two and does not belong to PERF014 (it touches only Test
Tool/reporting surfaces and metadata - see `config/perf014-direct-closure-call.json`'s
`intervening_unrelated_revision.note`). This does not relax any identity check below: `validate`
still asserts the exact control/intervention revision and version pair, and
`_verify_workload_source_identity` still fails closed on any workload source drift between the two
built images, exactly as it would for any other two-revision comparator in this family.

This is its own self-contained module - like `runner/perf010a_post_i068_baseline.py`,
`runner/perf010a_context_materialization.py` and `runner/perf010a_post_i072_fprime.py` before it,
and unlike `runner/perf009a.py` - because every PERF010-family Makefile target invokes its runner as
`python3 runner/<module>.py ...`, which puts only `runner/` (not the repository root) on
`sys.path`; `from runner.perf010a_post_i072_fprime import ...` fails under that invocation
(`ModuleNotFoundError: No module named 'runner'`). The generic process/build/timing/stationarity
helpers this module needs are therefore ported here from `runner/perf010a_post_i072_fprime.py`
rather than imported, exactly like that module ports them from `runner/perf010a.py`. This module
reuses that discipline unmodified (counterbalanced A,B,A,B block order, canonical+workload-control
pairing, steady-state-only timing with no JFR/compiler-tracing/IGV/allocation/Test-Tool
instrumentation, and the same `paired_control_effect` causal formula) - it does not invent a new
statistical methodology - and it is a brand-new evidence namespace: it never reads from or writes to
`config/perf010a-post-i072-fprime.json`, `runner/perf010a_post_i072_fprime.py`, or
`results/perf010a-post-i072-fprime/`.

Workload classification: PERF014 changes only the direct Closure-call path, so `micro/closure-call`
is the sole PRIMARY causal workload; `micro/slot-read`, `micro/method-call` and
`runtime/monomorphic-dispatch` do not exercise a Closure call site and are retained as broader
negative coverage. The retained Evidence Unit still includes all four workloads unconditionally
(`config/perf014-direct-closure-call.json`'s `workload_coverage_note`). The closure-call result MUST
NOT be generalized to the other three workloads or to any whole-language performance claim.

Beyond the shared `paired_control_effect` causal formula, this module additionally computes a
PERF014-specific "guest-call increment" for `micro/closure-call` only
(`compute_guest_call_increment`/`summarize_guest_call_increment`): the canonical-minus-
workload-control gap for each role, which approximates the pure guest-call overhead over a
no-call baseline, and how much that gap shrinks from control to intervention. This is additional
to, and never a replacement for, `classify_block`'s `paired_control_effect`.

Before any timing, `_verify_workload_source_identity` reads back every workload's exact canonical
source text from both built images and fails closed (`WORKLOAD_SOURCE_IDENTITY_MISMATCH`) if their
SHA-256 digests differ - especially load-bearing here because control and intervention are not
related by PERF014 commits alone (see above).

`validate << smoke << reference`: `validate` is static/configuration-only (no Docker, no timing),
and self-tests `compute_guest_call_increment`'s NOT_APPLICABLE/positive-ratio branches with
synthetic inputs (the analogous fail-closed contract to
`runner/perf010a_post_i072_fprime.py`'s `require_intervention_identity` self-test, adapted to the
fact that this module has no run-time-supplied revision to validate - both revisions are already
pinned constants checked directly against the config). `smoke` builds and probes both exact images
and runs the full four-workload matrix at a tiny iteration count
(`SMOKE_WARMUP_ITERATIONS`/`SMOKE_STEADY_ITERATIONS`, identical to every other `*_smoke` in this
family) as a correctness/admission gate whose timing is never retained as evidence. `reference` is
the only command that uses the full `warmup_iterations`/`steady_iterations` (120/100) Evidence Unit
scale and the only command whose output is retained, under
`results/perf014-direct-closure-call/`. `reference` also accepts `--block-order`/`--workload`
overrides for a bounded, still full-warmup, still-real-timed-unit validation run before the full
matrix - mirroring `reference_phase2`/`reference`'s identical bounded-validation contract in
`runner/perf010a.py`/`runner/perf010a_post_i072_fprime.py` - which requires an explicit scratch
`--output-dir`, rejects `--harness-revision`, and is written out with
`evidence_status="VALIDATION_ONLY_NOT_RETAINED"`.

This module deliberately does not mechanically classify `PERF014_TIMING_CLASSIFICATION`/
`PERF014_CLEARLY_MULTIPLICATIVE`/`PERF015_AUTHORIZED`: `reference` prints and retains the raw
computed per-workload `paired_control_effect` statistics and the closure-call
`guest_call_increment_summary` (median/MAD/min/max, per-block series, order effect) but leaves
those three fields as explicit `NOT_CLASSIFIED`/`NOT_CLASSIFIED`/`NO` placeholders in `raw.json` and
`README.md` - no threshold (2x, 5x, 10x, ...) is hardcoded anywhere in this harness. The
classification is a later interpretation step performed against this Evidence Unit's raw retained
data, not part of this harness. See `config/perf014-direct-closure-call.json`'s
`timing_classification_note`.

This module does not select or implement a further production optimization
(`diagnostic_claim: false` because this is a causal two-revision comparator, not a diagnostic
ablation).
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
import sys
import tempfile
import threading
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf014-direct-closure-call.json"
B2D_CONFIG = ROOT / "config/perf004b2d.json"
POST_I072_FPRIME_CONFIG = ROOT / "config/perf010a-post-i072-fprime.json"
DOCKERFILE = ROOT / "docker/protos-perf010a/Dockerfile"
TIMING_DRIVER = ROOT / "docker/protos-perf010a/Perf010aTimingDriver.java"
UNUSED_PATCH = ROOT / "docker/protos-perf010a/noop.patch"
MAKEFILE = ROOT / "Makefile"

EXPECTED_SLICE = "PERF014_DIRECT_CLOSURE_CALL_CONTROLLED_TIMING"
EXPECTED_CONTROL_REVISION = "0af8960363a557dad1b87968cf8a632e4716ee8a"
EXPECTED_CONTROL_VERSION = "0.3.102-SNAPSHOT"
EXPECTED_INTERVENTION_REVISION = "bcf9eda164d840b0a0b4201753fe5289347afa8a"
EXPECTED_INTERVENTION_VERSION = "0.3.105-SNAPSHOT"
EXPECTED_INTERVENING_UNRELATED_REVISION = "eab6a367c16dea0136e1aabb13a7da681c4839b0"
EXPECTED_INTERVENING_UNRELATED_VERSION = "0.3.104-SNAPSHOT"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_TOOLCHAIN = {
    "graalvm_release": "25.3.4.1",
    "jdk_version": "25.0.4.1",
    "graal_truffle_version": "25.3.4.1",
    "maven_version": "3.9.9",
    "container_image": "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825",
    "python_package": "python3",
}
ROLES = ("control", "intervention")
BLOCK_ORDER = ("A", "B", "A", "B")
PRIMARY_WORKLOADS = ("micro/closure-call",)
NEGATIVE_COVERAGE_WORKLOADS = ("micro/slot-read", "micro/method-call", "runtime/monomorphic-dispatch")
OUTPUT_DIR = ROOT / "results/perf014-direct-closure-call"

# This harness never computes PERF014_TIMING_CLASSIFICATION/PERF014_CLEARLY_MULTIPLICATIVE/
# PERF015_AUTHORIZED from the data it collects - see this module's docstring and
# config/perf014-direct-closure-call.json's timing_classification_note. These are Python
# constants (not read from config) so that an edited config cannot smuggle in a computed
# classification; validate() cross-checks the config declares the same placeholders.
PERF014_TIMING_CLASSIFICATION_PLACEHOLDER = "NOT_CLASSIFIED"
PERF014_CLEARLY_MULTIPLICATIVE_PLACEHOLDER = "NOT_CLASSIFIED"
PERF015_AUTHORIZED_PLACEHOLDER = "NO"

# Deliberately far smaller than the Evidence Unit's own warmup=120/steady=100, matching every
# other `*_smoke` in this repository's PERF010-A/PERF014 family (SMOKE_WARMUP_ITERATIONS/
# SMOKE_STEADY_ITERATIONS in runner/perf010a.py and runner/perf010a_post_i072_fprime.py). Every
# steady iteration is still individually correctness-checked by Perf010aTimingDriver's
# requireCompletedInteger regardless of count, so this loses no correctness coverage; it only
# avoids collecting statistically meaningful timing.
SMOKE_WARMUP_ITERATIONS = 1
SMOKE_STEADY_ITERATIONS = 2


# --- generic process/config helpers (ported unmodified from runner/perf010a_post_i072_fprime.py -
#     see this module's docstring for why they are ported rather than imported) ---


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
    """Non-retained declared harness identity for `smoke` only; see
    `runner/perf010a_post_i072_fprime.py`'s identically-named helper for the full rationale."""
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


def image_identity(tag: str) -> dict[str, Any]:
    payload = json.loads(output(["docker", "image", "inspect", tag]))[0]
    return {"tag": tag, "id": payload.get("Id", ""), "repo_digests": payload.get("RepoDigests") or []}


def stationarity_diagnostics(steady_ns: list[int]) -> dict[str, Any]:
    """First-quarter vs. last-quarter stationarity diagnostic, defined only for exactly 100 steady
    samples (this Evidence Unit's own `steady_iterations`), ported unmodified from
    `runner/perf010a_post_i072_fprime.py`."""
    if len(steady_ns) != 100:
        raise RuntimeError(
            "stationarity diagnostics require exactly 100 steady samples, got "
            f"{len(steady_ns)}"
        )
    first_quarter = steady_ns[0:25]
    last_quarter = steady_ns[75:100]
    first_quarter_median = statistics.median(first_quarter)
    last_quarter_median = statistics.median(last_quarter)
    last_quarter_vs_first_quarter_percent = (
        100.0 * (last_quarter_median - first_quarter_median) / first_quarter_median
    )
    return {
        "steady_median_ns": statistics.median(steady_ns),
        "first_quarter_median_ns": first_quarter_median,
        "last_quarter_median_ns": last_quarter_median,
        "last_quarter_vs_first_quarter_percent": last_quarter_vs_first_quarter_percent,
    }


def _mirror_stream(stream, sink_lines: list[str], mirror_target) -> None:
    for line in iter(stream.readline, ""):
        sink_lines.append(line)
        if mirror_target is not None:
            mirror_target.write(line)
            mirror_target.flush()
    stream.close()


def run_visible(command: list[str], *, mirror_stdout: bool = False) -> subprocess.CompletedProcess:
    """Streams stderr (and, if `mirror_stdout` is set, stdout) live while the child runs, in
    addition to retaining the complete text/exit code, so a hang or crash is visible immediately.
    Ported unmodified from `runner/perf010a_post_i072_fprime.py`'s identically-named helper."""
    proc = subprocess.Popen(
        command, cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stdout_thread = threading.Thread(
        target=_mirror_stream,
        args=(proc.stdout, stdout_lines, sys.stdout if mirror_stdout else None),
    )
    stderr_thread = threading.Thread(
        target=_mirror_stream, args=(proc.stderr, stderr_lines, sys.stderr)
    )
    stdout_thread.start()
    stderr_thread.start()
    returncode = proc.wait()
    stdout_thread.join()
    stderr_thread.join()
    return subprocess.CompletedProcess(command, returncode, "".join(stdout_lines), "".join(stderr_lines))


def docker_entrypoint(cpu: str, tag: str, entrypoint: str, *args: str) -> subprocess.CompletedProcess:
    completed = run(
        [
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpu,
            "--entrypoint", entrypoint,
            tag,
            *args,
        ],
        capture=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"container probe failed tag={tag} entrypoint={entrypoint} rc={completed.returncode}\n"
            f"stdout:\n{(completed.stdout or '')[-4000:]}\nstderr:\n{(completed.stderr or '')[-4000:]}"
        )
    return completed


# --- PERF014-specific guest-call increment (the metric this module adds beyond the shared
#     paired_control_effect causal formula) ---


def compute_guest_call_increment(
    control_canonical_ns: float, control_workload_control_ns: float,
    intervention_canonical_ns: float, intervention_workload_control_ns: float,
) -> dict[str, Any]:
    """`config/perf014-direct-closure-call.json`'s `guest_call_increment_formula`. The increment
    approximates the pure guest-call overhead over a no-call baseline for one role; the ratio is
    NOT_APPLICABLE (never a fabricated/negative/divide-by-zero number) unless both increments are
    strictly positive."""
    control_increment_ns = control_canonical_ns - control_workload_control_ns
    intervention_increment_ns = intervention_canonical_ns - intervention_workload_control_ns
    reduction_ns = control_increment_ns - intervention_increment_ns
    if control_increment_ns > 0 and intervention_increment_ns > 0:
        ratio: float | str = control_increment_ns / intervention_increment_ns
    else:
        ratio = "NOT_APPLICABLE"
    return {
        "control_guest_call_increment_ns": control_increment_ns,
        "intervention_guest_call_increment_ns": intervention_increment_ns,
        "guest_call_increment_reduction_ns": reduction_ns,
        "guest_call_increment_ratio": ratio,
    }


def summarize_guest_call_increment(classified_closure_call_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate (median/MAD/min/max across the 4 retained blocks) AND per-block guest-call
    increment series, so the ratio/reduction's stability can be inspected rather than trusted from
    a single quotient of aggregated medians alone (`guest_call_increment_formula`)."""
    per_block = [b["guest_call_increment"] for b in classified_closure_call_blocks]
    control_values = [p["control_guest_call_increment_ns"] for p in per_block]
    intervention_values = [p["intervention_guest_call_increment_ns"] for p in per_block]
    reduction_values = [p["guest_call_increment_reduction_ns"] for p in per_block]
    per_block_ratios = [p["guest_call_increment_ratio"] for p in per_block]

    control_median = statistics.median(control_values)
    intervention_median = statistics.median(intervention_values)
    if control_median > 0 and intervention_median > 0:
        ratio_of_medians: float | str = control_median / intervention_median
    else:
        ratio_of_medians = "NOT_APPLICABLE"

    return {
        "samples": len(per_block),
        "control_guest_call_increment_median_ns": control_median,
        "control_guest_call_increment_mad_ns": statistics.median(
            [abs(v - control_median) for v in control_values]
        ),
        "control_guest_call_increment_min_ns": min(control_values),
        "control_guest_call_increment_max_ns": max(control_values),
        "intervention_guest_call_increment_median_ns": intervention_median,
        "intervention_guest_call_increment_mad_ns": statistics.median(
            [abs(v - intervention_median) for v in intervention_values]
        ),
        "intervention_guest_call_increment_min_ns": min(intervention_values),
        "intervention_guest_call_increment_max_ns": max(intervention_values),
        "guest_call_increment_reduction_median_ns": statistics.median(reduction_values),
        "guest_call_increment_reduction_min_ns": min(reduction_values),
        "guest_call_increment_reduction_max_ns": max(reduction_values),
        "guest_call_increment_ratio_of_medians": ratio_of_medians,
        "per_block_control_guest_call_increment_ns": control_values,
        "per_block_intervention_guest_call_increment_ns": intervention_values,
        "per_block_guest_call_increment_reduction_ns": reduction_values,
        "per_block_guest_call_increment_ratio": per_block_ratios,
    }


# --- validate: static/configuration only, no Docker, no timing ---


def validate() -> dict[str, Any]:
    cfg = load(CONFIG)

    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF014"
    assert cfg["parent_perf_item"] == "PERF010-B"
    assert cfg["slice"] == EXPECTED_SLICE
    assert cfg["causal_two_revision_comparator"] is True
    assert cfg["diagnostic_claim"] is False
    assert "ablation_patch" not in cfg, (
        "this comparator must never declare a product-level ablation_patch in its config; the "
        "only intended difference between the two images is the pinned protos_revision"
    )

    control = cfg["control"]
    assert control["role"] == "control"
    assert control["variant"] == "baseline"
    assert control["protos_revision"] == EXPECTED_CONTROL_REVISION, (
        f"control protos_revision mismatch: expected {EXPECTED_CONTROL_REVISION}, "
        f"got {control['protos_revision']}"
    )
    assert control["protos_version"] == EXPECTED_CONTROL_VERSION, (
        f"control protos_version mismatch: expected {EXPECTED_CONTROL_VERSION}, "
        f"got {control['protos_version']}"
    )

    intervention = cfg["intervention"]
    assert intervention["role"] == "intervention"
    assert intervention["variant"] == "baseline"
    assert intervention["protos_revision"] == EXPECTED_INTERVENTION_REVISION, (
        f"intervention protos_revision mismatch: expected {EXPECTED_INTERVENTION_REVISION}, "
        f"got {intervention['protos_revision']}"
    )
    assert intervention["protos_version"] == EXPECTED_INTERVENTION_VERSION, (
        f"intervention protos_version mismatch: expected {EXPECTED_INTERVENTION_VERSION}, "
        f"got {intervention['protos_version']}"
    )
    assert control["protos_revision"] != intervention["protos_revision"], (
        "PERF014_SAME_REVISION_REJECTED: control and intervention must pin two distinct Protos "
        "revisions"
    )

    intervening = cfg["intervening_unrelated_revision"]
    assert intervening["protos_revision"] == EXPECTED_INTERVENING_UNRELATED_REVISION
    assert intervening["protos_version"] == EXPECTED_INTERVENING_UNRELATED_VERSION
    assert "BUG010" in intervening["note"] and intervening["note"].strip(), (
        "the intervening BUG010 lineage note must be present and non-empty - it documents lineage "
        "honesty, it does not relax any identity check"
    )

    assert cfg["both_variants_baseline"] is True
    assert cfg["patches_applied"] == "none"

    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 120
    assert cfg["steady_iterations"] == 100

    b2d_cfg = load(B2D_CONFIG)
    assert cfg["controls"] == b2d_cfg["controls"], (
        "must reuse the exact PERF004-B2-D/PERF008/PERF010-A four-workload matrix unmodified"
    )
    all_workload_ids = {item["id"] for item in cfg["controls"]}
    assert set(cfg["primary_causal_workloads"]) == set(PRIMARY_WORKLOADS)
    assert set(cfg["negative_coverage_workloads"]) == set(NEGATIVE_COVERAGE_WORKLOADS)
    assert set(cfg["primary_causal_workloads"]) | set(cfg["negative_coverage_workloads"]) == (
        all_workload_ids
    )
    assert set(cfg["primary_causal_workloads"]) & set(cfg["negative_coverage_workloads"]) == set()
    assert cfg["primary_causal_workloads"] == ["micro/closure-call"], (
        "PERF014's sole PRIMARY causal workload must be micro/closure-call"
    )

    assert tuple(cfg["block_order"]) == BLOCK_ORDER
    assert len(cfg["block_order"]) >= 4
    assert set(cfg["block_order"]) == {"A", "B"}
    assert cfg["block_order"].count("A") >= 2 and cfg["block_order"].count("B") >= 2

    assert cfg["toolchain"] == EXPECTED_TOOLCHAIN, "toolchain drift"

    assert "WORKLOAD_SOURCE_IDENTITY_MISMATCH" in cfg["workload_identity_policy"]
    assert cfg["guest_call_increment_formula"].strip()
    assert "NOT_APPLICABLE" in cfg["guest_call_increment_formula"]

    assert cfg["output"] == "results/perf014-direct-closure-call"
    assert cfg["output"] not in {"results/perf010a-post-i072-fprime", "results/perf010a-phase2"}, (
        "PERF014 must use its own dedicated output namespace, never an existing retained one"
    )

    for path in (CONFIG, B2D_CONFIG, POST_I072_FPRIME_CONFIG, DOCKERFILE, TIMING_DRIVER, UNUSED_PATCH):
        assert path.is_file(), path

    dockerfile_text = DOCKERFILE.read_text(encoding="utf-8")
    for required in (
        "ARG PROTOS_REVISION",
        "ARG VARIANT=baseline",
        'test "$(git rev-parse HEAD)" = "$PROTOS_REVISION"',
        "toolchain.json",
        "/opt/protos-source",
        "/opt/perf010a/corpus",
    ):
        assert required in dockerfile_text, required

    timing_driver_text = TIMING_DRIVER.read_text(encoding="utf-8")
    assert "import jdk.jfr" not in timing_driver_text, "timing driver must never perturb timing with JFR"
    assert "steady_ns" in timing_driver_text

    makefile_text = MAKEFILE.read_text(encoding="utf-8")
    for target in ("perf014-validate:", "perf014-smoke:", "perf014-reference:"):
        assert target in makefile_text, "missing Makefile target: " + target[:-1]

    # This new evidence namespace must never have touched the accepted post-I072 F' comparator it
    # reuses discipline from - a defensive tripwire, not merely a docstring claim.
    post_i072_cfg = load(POST_I072_FPRIME_CONFIG)
    assert post_i072_cfg["slice"] == "PERF010A_POST_I072_FPRIME_CAUSAL_COMPARATOR"
    assert post_i072_cfg["control"]["protos_revision"] == "2d8f04a8a01ff8639e98e03fba9a176170d54936"
    assert post_i072_cfg["output"] == "results/perf010a-post-i072-fprime"

    # Self-test compute_guest_call_increment's fail-closed NOT_APPLICABLE contract with synthetic
    # inputs, so `validate` proves the guest-call-increment contract without needing Docker or a
    # real timing run - the analogous fail-closed self-test to
    # runner/perf010a_post_i072_fprime.py's require_intervention_identity self-test, adapted to
    # the fact that this module has no run-time-supplied revision to validate.
    _positive = compute_guest_call_increment(1000, 400, 500, 200)
    assert _positive["control_guest_call_increment_ns"] == 600
    assert _positive["intervention_guest_call_increment_ns"] == 300
    assert _positive["guest_call_increment_reduction_ns"] == 300
    assert _positive["guest_call_increment_ratio"] == 2.0

    _control_non_positive = compute_guest_call_increment(1000, 1200, 500, 200)
    assert _control_non_positive["control_guest_call_increment_ns"] == -200
    assert _control_non_positive["guest_call_increment_ratio"] == "NOT_APPLICABLE"

    _intervention_non_positive = compute_guest_call_increment(1000, 400, 500, 600)
    assert _intervention_non_positive["intervention_guest_call_increment_ns"] == -100
    assert _intervention_non_positive["guest_call_increment_ratio"] == "NOT_APPLICABLE"

    _both_zero = compute_guest_call_increment(1000, 1000, 500, 500)
    assert _both_zero["control_guest_call_increment_ns"] == 0
    assert _both_zero["guest_call_increment_ratio"] == "NOT_APPLICABLE", (
        "a zero increment must never be treated as strictly positive"
    )

    print("PERF014_CONFIG=PASS")
    print("PERF014_GUEST_CALL_INCREMENT_SELF_TEST=PASS")
    print("CONTROL_PRODUCT_REVISION=" + control["protos_revision"])
    print("CONTROL_PRODUCT_VERSION=" + control["protos_version"])
    print("INTERVENTION_PRODUCT_REVISION=" + intervention["protos_revision"])
    print("INTERVENTION_PRODUCT_VERSION=" + intervention["protos_version"])
    print("INTERVENING_BUG010_REVISION=" + intervening["protos_revision"])
    print("PERF014_BOTH_PRODUCT_VARIANTS_BASELINE=YES")
    print("PERF014_PATCHES_APPLIED=NO")
    print("PERF014_WARMUP=" + str(cfg["warmup_iterations"]))
    print("PERF014_STEADY=" + str(cfg["steady_iterations"]))
    print("PERF014_OPERATION_COUNT=" + str(cfg["operation_count"]))
    print("PERF014_BLOCK_ORDER=" + ",".join(cfg["block_order"]))
    print("PERF014_PRIMARY_CAUSAL_WORKLOAD=" + ",".join(cfg["primary_causal_workloads"]))
    print(
        "PERF014_NEGATIVE_COVERAGE_WORKLOADS=" + ",".join(cfg["negative_coverage_workloads"])
    )
    print("PERF014_OUTPUT_NAMESPACE=" + cfg["output"])
    print("PERF014_TIMING_CLASSIFICATION=" + PERF014_TIMING_CLASSIFICATION_PLACEHOLDER)
    print("PERF014_CLEARLY_MULTIPLICATIVE=" + PERF014_CLEARLY_MULTIPLICATIVE_PLACEHOLDER)
    print("PERF015_AUTHORIZED=" + PERF015_AUTHORIZED_PLACEHOLDER)
    return cfg


# --- build/probe (Docker, no timing) ---


def build_image(role: str, revision: str, toolchain: dict[str, Any], protos_repository: str, slice_label: str) -> str:
    tag = f"protos-benchmarks-perf014-{role}:{revision[:12]}"
    run([
        "docker", "build",
        "--build-arg", "GRAAL_BASE=" + toolchain["container_image"],
        "--build-arg", "PROTOS_REPOSITORY=" + protos_repository,
        "--build-arg", "PROTOS_REVISION=" + revision,
        "--build-arg", "VARIANT=baseline",
        "--build-arg", "ABLATION_PATCH=" + UNUSED_PATCH.name,
        "--build-arg", "ABLATION_SLICE=" + slice_label,
        "--build-arg", "EXPECTED_GRAALVM_RELEASE=" + toolchain["graalvm_release"],
        "--build-arg", "EXPECTED_JDK_VERSION=" + toolchain["jdk_version"],
        "--build-arg", "EXPECTED_CONTAINER_IMAGE=" + toolchain["container_image"],
        "--build-arg", "EXPECTED_GRAAL_COMPONENTS_VERSION=" + toolchain["graal_truffle_version"],
        "--build-arg", "EXPECTED_MAVEN_VERSION=" + toolchain["maven_version"],
        "--build-arg", "PYTHON_PACKAGE=" + toolchain["python_package"],
        "--label", "org.opencontainers.image.revision=" + revision,
        "--label", "org.protos-benchmarks.perf010a.variant=baseline",
        "--label", "org.protos-benchmarks.perf010a.ablation-slice=" + slice_label,
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
    completed = docker_entrypoint(cpu, tag, "java", "-version")
    return (completed.stderr or completed.stdout or "").strip()


def variant_probe(tag: str, cpu: str) -> str:
    return docker_entrypoint(cpu, tag, "cat", "/opt/perf010a/variant.txt").stdout.strip()


def ablation_slice_probe(tag: str, cpu: str) -> str:
    return docker_entrypoint(cpu, tag, "cat", "/opt/perf010a/ablation-slice.txt").stdout.strip()


def image_revision_label_probe(tag: str) -> str:
    payload = json.loads(output(["docker", "image", "inspect", tag]))[0]
    labels = ((payload.get("Config") or {}).get("Labels")) or {}
    return labels.get("org.opencontainers.image.revision", "")


def image_version_probe(tag: str, cpu: str) -> str:
    """Reads the built image's own `/opt/protos-source/pom.xml` `<version>` back from the
    artifact, exactly like `runner/perf010a_post_i072_fprime.py`'s identically-named helper."""
    import xml.etree.ElementTree as ET

    completed = docker_entrypoint(cpu, tag, "cat", "/opt/protos-source/pom.xml")
    root = ET.fromstring(completed.stdout or "")
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    version_el = root.find("m:version", ns)
    return version_el.text.strip() if version_el is not None and version_el.text else ""


def _verify_workload_source_identity(
    controls: list[dict[str, Any]], tags: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Both product revisions must execute materially identical benchmark programs
    (`config/perf014-direct-closure-call.json`'s `workload_identity_policy`) - especially
    load-bearing here because control and intervention are not related by PERF014 commits alone.
    Reads each workload's exact canonical source text back from both built images (a plain `docker
    run --entrypoint /bin/cat`, unaffected by CPU affinity) and fails closed on any digest
    mismatch, rather than silently comparing a changed program across revisions."""
    digests: dict[str, dict[str, str]] = {}
    for item in controls:
        source_path = "/opt/perf010a/corpus/" + item["source"]
        texts = {
            role: output(["docker", "run", "--rm", "--entrypoint", "/bin/cat", tags[role], source_path])
            for role in ROLES
        }
        role_digests = {
            role: hashlib.sha256(text.encode("utf-8")).hexdigest() for role, text in texts.items()
        }
        if texts["control"] != texts["intervention"]:
            raise RuntimeError(
                "WORKLOAD_SOURCE_IDENTITY_MISMATCH: workload="
                f"{item['id']} control_sha256={role_digests['control']} "
                f"intervention_sha256={role_digests['intervention']} - both product revisions must "
                "execute materially identical benchmark programs; see workload_identity_policy in "
                "config/perf014-direct-closure-call.json"
            )
        digests[item["id"]] = role_digests
    return digests


def _build_and_probe_images(cfg: dict[str, Any], cpu: str) -> dict[str, Any]:
    """Builds the control and intervention images (both VARIANT=baseline, from the two pinned
    protos_revision values already fixed in config) and fails closed before returning unless all
    of the following hold for BOTH roles: `/opt/perf010a/variant.txt` reads "baseline";
    `/opt/perf010a/ablation-slice.txt` reads "none"; the image's own
    `org.opencontainers.image.revision` LABEL matches that role's expected pinned protos_revision;
    and the image's own `pom.xml` version matches that role's expected protos_version. Also proves
    every workload's canonical source is byte-identical between the two images before returning.
    """
    role_revisions = {
        "control": cfg["control"]["protos_revision"],
        "intervention": cfg["intervention"]["protos_revision"],
    }
    role_versions = {
        "control": cfg["control"]["protos_version"],
        "intervention": cfg["intervention"]["protos_version"],
    }
    if role_revisions["control"] == role_revisions["intervention"]:
        raise RuntimeError(
            "PERF014_SAME_REVISION_REJECTED: control and intervention protos_revision must differ"
        )

    tags: dict[str, str] = {}
    identities: dict[str, Any] = {}
    for role in ROLES:
        role_revision = role_revisions[role]
        role_version = role_versions[role]
        slice_label = f"{cfg['slice']}__{role.upper()}"
        tag = build_image(role, role_revision, cfg["toolchain"], cfg["protos_repository"], slice_label)
        tags[role] = tag

        runtime_probe(tag, cpu)
        java_version_probe(tag, cpu)

        observed_variant = variant_probe(tag, cpu)
        if observed_variant != "baseline":
            raise RuntimeError(
                f"role={role} variant label mismatch: expected baseline, got {observed_variant!r}"
            )

        observed_slice = ablation_slice_probe(tag, cpu)
        if observed_slice != "none":
            raise RuntimeError(
                f"PERF014_PATCH_PATH_REJECTED: role={role} image reports "
                f"ablation-slice={observed_slice!r}, expected 'none' - a baseline-variant image "
                "must never have gone through the patch-apply path"
            )

        observed_revision = image_revision_label_probe(tag)
        if observed_revision != role_revision:
            raise RuntimeError(
                f"PERF014_REVISION_IDENTITY_MISMATCH: role={role} image's own "
                f"org.opencontainers.image.revision label reads {observed_revision!r}, expected "
                f"{role_revision!r}"
            )

        observed_version = image_version_probe(tag, cpu)
        if observed_version != role_version:
            raise RuntimeError(
                f"PERF014_VERSION_IDENTITY_MISMATCH: role={role} image's own pom.xml "
                f"version reads {observed_version!r}, expected {role_version!r}"
            )

        identities[role] = image_identity(tag)
        print(
            f"PERF014 IMAGE role={role} protos_revision={role_revision} "
            f"protos_version={role_version} tag={tag} id={identities[role]['id']} "
            f"repo_digests={identities[role]['repo_digests']}",
            flush=True,
        )

    workload_source_sha256 = _verify_workload_source_identity(cfg["controls"], tags)

    print("PERF014_CONTROL_INTERVENTION_REVISIONS_DISTINCT=PASS")
    print("PERF014_BOTH_IMAGES_VARIANT_BASELINE=PASS")
    print("PERF014_BOTH_IMAGES_ABLATION_SLICE_NONE=PASS")
    print("PERF014_BOTH_IMAGES_REVISION_LABEL_MATCH=PASS")
    print("PERF014_BOTH_IMAGES_VERSION_MATCH=PASS")
    print("PERF014_WORKLOAD_SOURCE_IDENTITY=PASS")
    return {"tags": tags, "image_identity": identities, "workload_source_sha256": workload_source_sha256}


# --- timing (Docker, per timed unit) ---


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


def timing_visible(
    tag: str, cpu: str, work: Path, logs_dir: Path,
    source_host: Path | None, source_container: str,
    expected: str, label: str, warmup: int, steady: int,
    *, collect_stationarity: bool = True,
) -> dict[str, Any]:
    """Steady/warmup timing for one (workload, mode, role) unit via `Perf010aTimingDriver`
    (JFR-free). stderr is streamed live while the timed unit runs; complete stdout/stderr are
    retained to per-timed-unit log files under `logs_dir` as well as returned in-memory. Ported
    unmodified from `runner/perf010a_post_i072_fprime.py`'s identically-named helper."""
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
    print(f"PERF014 TIMING BEGIN label={label} warmup={warmup} steady={steady}", flush=True)
    p = run_visible(command)

    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"{label}.stdout.log"
    stderr_path = logs_dir / f"{label}.stderr.log"
    stdout_path.write_text(p.stdout, encoding="utf-8")
    stderr_path.write_text(p.stderr, encoding="utf-8")

    if p.returncode != 0:
        print(
            f"PERF014 TIMING FAIL label={label} returncode={p.returncode} "
            f"stdout_log={stdout_path} stderr_log={stderr_path}",
            flush=True,
        )
        raise RuntimeError(
            f"timing failed {label} returncode={p.returncode}\n"
            f"stdout(tail):\n{p.stdout[-6000:]}\nstderr(tail):\n{p.stderr[-6000:]}"
        )

    lines = [line for line in p.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("empty timing output: " + label)
    payload = json.loads(lines[-1])
    warmup_ns = [int(v) for v in payload["warmup_ns"]]
    steady_ns = [int(v) for v in payload["steady_ns"]]
    if len(warmup_ns) != warmup:
        raise RuntimeError(
            f"unexpected warmup sample count in {label}: expected={warmup} observed={len(warmup_ns)}"
        )
    if len(steady_ns) != steady:
        raise RuntimeError(
            f"unexpected steady sample count in {label}: expected={steady} observed={len(steady_ns)}"
        )

    result: dict[str, Any] = {
        "raw": payload,
        "steady_summary": summarize_ns(steady_ns),
        "returncode": p.returncode,
        "stdout_log": stdout_path.name,
        "stderr_log": stderr_path.name,
        "stdout_sha256": hashlib.sha256(p.stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(p.stderr.encode("utf-8")).hexdigest(),
    }
    result["stationarity"] = stationarity_diagnostics(steady_ns) if collect_stationarity else None
    return result


def _block_role_order(block_label: str) -> tuple[str, str]:
    if block_label == "A":
        return ("control", "intervention")
    if block_label == "B":
        return ("intervention", "control")
    raise ValueError(f"unknown block label: {block_label!r}")


def run_blocks(
    cfg: dict[str, Any], tags: dict[str, str], cpu: str, work: Path, logs_dir: Path,
    block_order: tuple[str, ...], warmup: int, steady: int,
    controls: list[dict[str, Any]] | None = None,
    *, collect_stationarity: bool = True,
) -> list[dict[str, Any]]:
    """Counterbalanced block matrix - structurally identical to
    `runner/perf010a_post_i072_fprime.py`'s `run_blocks` (same `control_source`
    canonical/workload-control construction, same `timing_visible` per-timed-unit
    retention/stationarity), reused here under this module's own name/print-prefix so its records
    can never be confused with any other family member's records. `controls` defaults to
    `cfg["controls"]` (the full four-workload matrix); a caller may pass a subset only for a
    bounded validation run (see `reference`'s `workload_ids`), never for the retained reference
    run itself."""
    controls = cfg["controls"] if controls is None else controls
    blocks: list[dict[str, Any]] = []
    for block_index, block_label in enumerate(block_order):
        role_order = _block_role_order(block_label)
        for item in controls:
            workload = item["id"]
            slug = workload.replace("/", "__")
            by_role: dict[str, Any] = {}
            for role in role_order:
                tag = tags[role]
                canonical_source, control_host = control_source(tag, work, item)
                by_mode: dict[str, Any] = {}
                for mode, source_host, source_container in (
                    ("canonical", None, canonical_source),
                    ("control", control_host, "/work/source.protos"),
                ):
                    label = f"block{block_index}-{block_label}-{slug}-{role}-{mode}"
                    timing_result = timing_visible(
                        tag, cpu, work, logs_dir, source_host, source_container,
                        item["expected"], label, warmup, steady,
                        collect_stationarity=collect_stationarity,
                    )
                    stationarity_note = (
                        f" last_vs_first_pct="
                        f"{timing_result['stationarity']['last_quarter_vs_first_quarter_percent']:.4f}"
                        if timing_result["stationarity"] is not None
                        else ""
                    )
                    print(
                        f"PERF014 TIMING PASS block={block_index} order={block_label} "
                        f"workload={workload} role={role} mode={mode} "
                        f"median_ns={timing_result['steady_summary']['median_ns']}"
                        f"{stationarity_note}",
                        flush=True,
                    )
                    by_mode[mode] = timing_result
                by_role[role] = by_mode
            blocks.append({
                "block_index": block_index,
                "block_order": block_label,
                "role_sequence": list(role_order),
                "workload": workload,
                "roles": by_role,
            })
    return blocks


def classify_block(entry: dict[str, Any]) -> dict[str, Any]:
    """Causal formula fixed by `config/perf014-direct-closure-call.json`'s `causal_formula`
    (reused unchanged from `config/perf010a-post-i072-fprime.json`), before any data is collected:

        canonical_improvement  = control_canonical_median_ns - intervention_canonical_median_ns
        control_movement       = control_workload_control_median_ns
                                  - intervention_workload_control_median_ns
        paired_control_effect  = canonical_improvement - control_movement

    A positive `paired_control_effect` means INTERVENTION (the final PERF014 revision) is faster
    than CONTROL once the workload-control's own measured movement between the two revisions/
    images has been subtracted out. Expressed as a percentage of the control canonical median.
    This function does not classify PERF014_TIMING_CLASSIFICATION/PERF014_CLEARLY_MULTIPLICATIVE -
    see this module's docstring and config/perf014-direct-closure-call.json's
    timing_classification_note.

    Additionally computes the PERF014-specific `guest_call_increment` (see
    `compute_guest_call_increment`) for `micro/closure-call` only - `None` for every other
    workload, since the guest-call-increment metric is specific to this Evidence Unit's PRIMARY
    causal workload and is never generalized to the others.
    """
    control = entry["roles"]["control"]
    intervention = entry["roles"]["intervention"]
    control_canonical_ns = control["canonical"]["steady_summary"]["median_ns"]
    control_workload_control_ns = control["control"]["steady_summary"]["median_ns"]
    intervention_canonical_ns = intervention["canonical"]["steady_summary"]["median_ns"]
    intervention_workload_control_ns = intervention["control"]["steady_summary"]["median_ns"]

    canonical_improvement_ns = control_canonical_ns - intervention_canonical_ns
    control_movement_ns = control_workload_control_ns - intervention_workload_control_ns
    paired_control_effect_ns = canonical_improvement_ns - control_movement_ns
    paired_control_effect_percent = 100.0 * paired_control_effect_ns / control_canonical_ns

    guest_call_increment = (
        compute_guest_call_increment(
            control_canonical_ns, control_workload_control_ns,
            intervention_canonical_ns, intervention_workload_control_ns,
        )
        if entry["workload"] in PRIMARY_WORKLOADS
        else None
    )

    return {
        "block_index": entry["block_index"],
        "block_order": entry["block_order"],
        "workload": entry["workload"],
        "control_canonical_median_ns": control_canonical_ns,
        "control_workload_control_median_ns": control_workload_control_ns,
        "intervention_canonical_median_ns": intervention_canonical_ns,
        "intervention_workload_control_median_ns": intervention_workload_control_ns,
        "canonical_improvement_ns": canonical_improvement_ns,
        "control_movement_ns": control_movement_ns,
        "paired_control_effect_ns": paired_control_effect_ns,
        "paired_control_effect_percent": paired_control_effect_percent,
        "guest_call_increment": guest_call_increment,
    }


def summarize_workload(classified_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive envelope for one workload across all retained blocks - explicitly a
    DESCRIPTIVE_ENVELOPE, not a fabricated inferential confidence interval, matching
    `runner/perf010a_post_i072_fprime.py`'s `summarize_workload` discipline exactly."""
    values = [b["paired_control_effect_percent"] for b in classified_blocks]
    ordered = sorted(values)
    median = statistics.median(values)
    mad = statistics.median([abs(v - median) for v in values])

    a_values = [b["paired_control_effect_percent"] for b in classified_blocks if b["block_order"] == "A"]
    b_values = [b["paired_control_effect_percent"] for b in classified_blocks if b["block_order"] == "B"]
    if len(a_values) < 2 or len(b_values) < 2:
        order_effect = "INCONCLUSIVE"
    else:
        a_range = (min(a_values), max(a_values))
        b_range = (min(b_values), max(b_values))
        non_overlapping = a_range[1] < b_range[0] or b_range[1] < a_range[0]
        order_effect = "DETECTED" if non_overlapping else "NOT_DETECTED"

    return {
        "samples": len(values),
        "paired_control_effect_min_percent": min(ordered),
        "paired_control_effect_max_percent": max(ordered),
        "paired_control_effect_median_percent": median,
        "paired_control_effect_mad_percent": mad,
        "order_effect": order_effect,
        "a_order_values_percent": a_values,
        "b_order_values_percent": b_values,
    }


# --- smoke: admission/correctness gate, never retained as evidence ---


def smoke() -> None:
    cfg = validate()
    harness_revision = worktree_harness_revision()
    cpu = first_cpu()
    build_result = _build_and_probe_images(cfg, cpu)
    tags = build_result["tags"]

    with tempfile.TemporaryDirectory(prefix="perf014-direct-closure-call-smoke-") as tmp:
        work = Path(tmp)
        logs_dir = work / "logs"
        blocks = run_blocks(
            cfg, tags, cpu, work, logs_dir,
            block_order=("A", "B"),
            warmup=SMOKE_WARMUP_ITERATIONS, steady=SMOKE_STEADY_ITERATIONS,
            collect_stationarity=False,
        )

    print("PERF014_SMOKE_HARNESS_REVISION=" + harness_revision)
    print("CONTROL_PRODUCT_REVISION=" + cfg["control"]["protos_revision"])
    print("INTERVENTION_PRODUCT_REVISION=" + cfg["intervention"]["protos_revision"])
    print(
        f"PERF014_SMOKE_SCALE=warmup={SMOKE_WARMUP_ITERATIONS} "
        f"steady={SMOKE_STEADY_ITERATIONS} (Evidence Unit scale: "
        f"warmup={cfg['warmup_iterations']} steady={cfg['steady_iterations']})"
    )
    print("PERF014_SMOKE_BLOCKS=" + str(len({b['block_index'] for b in blocks})))
    print("PERF014_SMOKE_WORKLOADS=" + str(len(cfg["controls"])))
    print("PERF014_CORRECTNESS=PASS")
    print("PERF014_SMOKE=PASS")
    print("PERF014_SMOKE_RETAINED_PERFORMANCE_EVIDENCE=NO")


# --- reference: full retained Evidence Unit ---


def reference(
    harness_revision: str | None,
    output_dir: Path | None,
    *,
    block_order_override: tuple[str, ...] | None = None,
    workload_ids: tuple[str, ...] | None = None,
) -> None:
    """Full warmup=120/steady=100/operation_count=10000/block_order=A,B,A,B Evidence Unit, reusing
    this module's counterbalanced-block/paired-workload-control machinery with the
    `classify_block` causal formula plus the PERF014-specific `guest_call_increment_summary`.
    Deliberately does not classify PERF014_TIMING_CLASSIFICATION, PERF014_CLEARLY_MULTIPLICATIVE,
    or PERF015_AUTHORIZED - see this module's docstring.

    `block_order_override`/`workload_ids` exist only so a bounded, still full-warmup=120,
    still-real-timed-unit validation run can exercise a small subset of the matrix - including
    from the dirty working tree that contains the harness changes under validation, before they
    are committed - exactly mirroring `runner/perf010a_post_i072_fprime.py`'s `reference` bounded-
    validation contract:

      - requires an explicit scratch `--output-dir` (never defaults to OUTPUT_DIR, which is
        reserved for the retained run);
      - rejects an explicit `--harness-revision` (only the retained run pins one);
      - records `harness_revision` via `worktree_harness_revision()` instead; and
      - is written out with `evidence_status="VALIDATION_ONLY_NOT_RETAINED"` in `raw.json`, a
        printed evidence-status marker, and a top-of-README banner.
    """
    cfg = validate()
    is_bounded_run = block_order_override is not None or workload_ids is not None

    if is_bounded_run:
        if output_dir is None:
            raise RuntimeError(
                "a bounded reference validation run (--block-order/--workload) requires an "
                "explicit scratch --output-dir; it must never default to OUTPUT_DIR, which is "
                "reserved for the full-matrix retained Evidence Unit"
            )
        if harness_revision is not None:
            raise RuntimeError(
                "--harness-revision is not accepted for a bounded reference validation run; only "
                "the full retained Evidence Unit run (no --block-order/--workload) pins an exact "
                "harness revision"
            )
        harness_revision = worktree_harness_revision()
    else:
        harness_revision = resolved_harness_revision(harness_revision)
        if output(["git", "status", "--porcelain", "--untracked-files=all"]):
            raise RuntimeError("reference requires clean exact harness")

    output_dir = output_dir if output_dir is not None else OUTPUT_DIR

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise RuntimeError("output directory already contains evidence")
        output_dir.rmdir()

    controls = cfg["controls"]
    if workload_ids is not None:
        controls = [item for item in cfg["controls"] if item["id"] in workload_ids]
        if len(controls) != len(workload_ids):
            raise RuntimeError(f"unknown workload id(s) in {workload_ids}")

    block_order = block_order_override if block_order_override is not None else tuple(cfg["block_order"])
    for label in block_order:
        _block_role_order(label)  # raises on an unknown block label

    cpu = first_cpu()
    build_result = _build_and_probe_images(cfg, cpu)
    tags = build_result["tags"]
    image_identities = build_result["image_identity"]
    workload_source_sha256 = build_result["workload_source_sha256"]

    output_dir.mkdir(parents=True)
    logs_dir = output_dir / "logs"

    with tempfile.TemporaryDirectory(prefix="perf014-direct-closure-call-") as tmp:
        work = Path(tmp)
        blocks = run_blocks(
            cfg, tags, cpu, work, logs_dir,
            block_order=block_order,
            warmup=cfg["warmup_iterations"], steady=cfg["steady_iterations"],
            controls=controls,
        )

    classified = [classify_block(entry) for entry in blocks]
    by_workload: dict[str, list[dict[str, Any]]] = {}
    for c in classified:
        by_workload.setdefault(c["workload"], []).append(c)
    per_workload_summary = {
        workload: summarize_workload(blocks_for_workload)
        for workload, blocks_for_workload in by_workload.items()
    }

    guest_call_increment_summary = (
        summarize_guest_call_increment(by_workload["micro/closure-call"])
        if "micro/closure-call" in by_workload
        else None
    )

    stationarity_by_unit = [
        {
            "block_index": entry["block_index"],
            "block_order": entry["block_order"],
            "workload": entry["workload"],
            "role": role,
            "mode": mode,
            **entry["roles"][role][mode]["stationarity"],
        }
        for entry in blocks
        for role in entry["roles"]
        for mode in entry["roles"][role]
    ]

    is_full_matrix_run = not is_bounded_run
    evidence_status = "RETAINED" if is_full_matrix_run else "VALIDATION_ONLY_NOT_RETAINED"

    raw: dict[str, Any] = {
        "schema_version": 1,
        "perf_item": "PERF014",
        "parent_perf_item": "PERF010-B",
        "slice": cfg["slice"],
        "phase": cfg["phase"],
        "diagnostic_claim": False,
        "causal_two_revision_comparator": True,
        "full_matrix_evidence_unit": is_full_matrix_run,
        "evidence_status": evidence_status,
        "harness_revision": harness_revision,
        "control_protos_revision": cfg["control"]["protos_revision"],
        "control_protos_version": cfg["control"]["protos_version"],
        "intervention_protos_revision": cfg["intervention"]["protos_revision"],
        "intervention_protos_version": cfg["intervention"]["protos_version"],
        "intervening_unrelated_revision": cfg["intervening_unrelated_revision"],
        "both_product_variants_baseline": True,
        "patches_applied": "none",
        "toolchain": cfg["toolchain"],
        "built_image_identity": image_identities,
        "workload_source_sha256": workload_source_sha256,
        "host_identity": host_identity(),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "network": "none",
        "operation_count": cfg["operation_count"],
        "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"],
        "block_order": list(block_order),
        "primary_causal_workloads": list(cfg["primary_causal_workloads"]),
        "negative_coverage_workloads": list(cfg["negative_coverage_workloads"]),
        "blocks": blocks,
        "classified_blocks": classified,
        "per_timed_unit_stationarity": stationarity_by_unit,
        "per_workload_summary": per_workload_summary,
        "guest_call_increment_summary": guest_call_increment_summary,
        "perf014_timing_classification": PERF014_TIMING_CLASSIFICATION_PLACEHOLDER,
        "perf014_clearly_multiplicative": PERF014_CLEARLY_MULTIPLICATIVE_PLACEHOLDER,
        "perf015_authorized": PERF015_AUTHORIZED_PLACEHOLDER,
        "production_optimization_selected": False,
    }
    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    stationarity_rows = [
        "block_index\tblock_order\tworkload\trole\tmode\tsteady_median_ns\t"
        "first_quarter_median_ns\tlast_quarter_median_ns\tlast_quarter_vs_first_quarter_percent"
    ]
    for s in stationarity_by_unit:
        stationarity_rows.append("\t".join([
            str(s["block_index"]), s["block_order"], s["workload"], s["role"], s["mode"],
            str(s["steady_median_ns"]), str(s["first_quarter_median_ns"]),
            str(s["last_quarter_median_ns"]),
            f"{s['last_quarter_vs_first_quarter_percent']:.4f}",
        ]))
    (output_dir / "stationarity.tsv").write_text(
        "\n".join(stationarity_rows) + "\n", encoding="utf-8"
    )

    summary_rows = [
        "workload\tsamples\tpaired_control_effect_min_percent\tpaired_control_effect_max_percent\t"
        "paired_control_effect_median_percent\tpaired_control_effect_mad_percent\torder_effect"
    ]
    for workload, s in per_workload_summary.items():
        summary_rows.append("\t".join([
            workload, str(s["samples"]),
            f"{s['paired_control_effect_min_percent']:.4f}",
            f"{s['paired_control_effect_max_percent']:.4f}",
            f"{s['paired_control_effect_median_percent']:.4f}",
            f"{s['paired_control_effect_mad_percent']:.4f}",
            s["order_effect"],
        ]))
    (output_dir / "perf014-summary.tsv").write_text(
        "\n".join(summary_rows) + "\n", encoding="utf-8"
    )

    readme = [
        "# PERF014 direct Closure-call final causal timing Evidence Unit",
        "",
    ]
    if not is_full_matrix_run:
        readme += [
            "> **VALIDATION_ONLY_NOT_RETAINED** - this is a bounded run (`--block-order`/"
            "`--workload`) over a subset of the matrix, produced to validate the harness itself, "
            "not the retained Evidence Unit. It may have been executed from a dirty (uncommitted) "
            "working tree - see `harness_revision` below, which reads `WORKTREE_PRECOMMIT` when "
            "that is the case. It MUST NOT be cited as PERF014 evidence. The retained Evidence "
            "Unit is the full four-workload, full-block-order run with no overrides, executed "
            "from a clean exact harness revision, written to "
            "`results/perf014-direct-closure-call`.",
            "",
        ]
    readme += [
        cfg["causal_question"],
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Control Protos revision (VARIANT=baseline): `{cfg['control']['protos_revision']}` "
        f"(`{cfg['control']['protos_version']}`) - PERF013 B2.",
        f"- Intervention Protos revision (VARIANT=baseline): `{cfg['intervention']['protos_revision']}` "
        f"(`{cfg['intervention']['protos_version']}`) - final PERF014 product.",
        f"- Intervening unrelated revision in the intervention's ancestry (BUG010, not PERF014): "
        f"`{cfg['intervening_unrelated_revision']['protos_revision']}` "
        f"(`{cfg['intervening_unrelated_revision']['protos_version']}`).",
        "- Patches applied to either image: NONE (see `patches_applied` and "
        "`PERF014_BOTH_IMAGES_ABLATION_SLICE_NONE` in the run log).",
        f"- Built image identity: `{json.dumps(image_identities, sort_keys=True)}`",
        f"- Workload source SHA-256 identity (control == intervention for every workload): "
        f"`{json.dumps(workload_source_sha256, sort_keys=True)}`",
        f"- Block order: `{list(block_order)}` (A: control first; B: intervention first).",
        f"- N={cfg['operation_count']}. Warmup={cfg['warmup_iterations']}, "
        f"steady={cfg['steady_iterations']}.",
        f"- Full four-workload matrix: {'YES' if is_full_matrix_run else 'NO (bounded validation run)'}.",
        f"- Evidence status: `{evidence_status}`.",
        "",
        f"`{cfg['causal_formula']}`",
        "",
        "## Per-workload paired-control effect (descriptive only)",
        "",
        "| workload | classification | samples | min % | max % | median % | MAD % | order effect |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for workload, s in per_workload_summary.items():
        classification = (
            "PRIMARY" if workload in cfg["primary_causal_workloads"] else "NEGATIVE_COVERAGE"
        )
        readme.append(
            f"| {workload} | {classification} | {s['samples']} "
            f"| {s['paired_control_effect_min_percent']:.4f} "
            f"| {s['paired_control_effect_max_percent']:.4f} "
            f"| {s['paired_control_effect_median_percent']:.4f} "
            f"| {s['paired_control_effect_mad_percent']:.4f} "
            f"| {s['order_effect']} |"
        )

    readme += [
        "",
        "## Guest-call increment (`micro/closure-call` only, PERF014-specific)",
        "",
        f"`{cfg['guest_call_increment_formula']}`",
        "",
    ]
    if guest_call_increment_summary is not None:
        g = guest_call_increment_summary
        readme += [
            "| quantity | median | MAD | min | max |",
            "|---|---|---|---|---|",
            f"| control guest-call increment (ns) | {g['control_guest_call_increment_median_ns']:.1f} "
            f"| {g['control_guest_call_increment_mad_ns']:.1f} "
            f"| {g['control_guest_call_increment_min_ns']:.1f} "
            f"| {g['control_guest_call_increment_max_ns']:.1f} |",
            f"| intervention guest-call increment (ns) | "
            f"{g['intervention_guest_call_increment_median_ns']:.1f} "
            f"| {g['intervention_guest_call_increment_mad_ns']:.1f} "
            f"| {g['intervention_guest_call_increment_min_ns']:.1f} "
            f"| {g['intervention_guest_call_increment_max_ns']:.1f} |",
            f"| guest-call increment reduction (ns) | "
            f"{g['guest_call_increment_reduction_median_ns']:.1f} | - "
            f"| {g['guest_call_increment_reduction_min_ns']:.1f} "
            f"| {g['guest_call_increment_reduction_max_ns']:.1f} |",
            "",
            f"- Ratio of aggregate medians (control / intervention): "
            f"`{g['guest_call_increment_ratio_of_medians']}`.",
            f"- Per-block control increments (ns): `{g['per_block_control_guest_call_increment_ns']}`.",
            f"- Per-block intervention increments (ns): "
            f"`{g['per_block_intervention_guest_call_increment_ns']}`.",
            f"- Per-block reductions (ns): `{g['per_block_guest_call_increment_reduction_ns']}`.",
            f"- Per-block ratios: `{g['per_block_guest_call_increment_ratio']}`.",
            "",
        ]
    else:
        readme += ["`micro/closure-call` was not part of this run's workload subset.", ""]

    readme += [
        "## Stationarity (first-quarter vs. last-quarter of each 100-sample steady timed unit)",
        "",
        "See `stationarity.tsv` for the full per-timed-unit table (raw `raw.json` remains "
        "authoritative).",
        "",
        "## PERF014_TIMING_CLASSIFICATION = " + PERF014_TIMING_CLASSIFICATION_PLACEHOLDER,
        "## PERF014_CLEARLY_MULTIPLICATIVE = " + PERF014_CLEARLY_MULTIPLICATIVE_PLACEHOLDER,
        "## PERF015_AUTHORIZED = " + PERF015_AUTHORIZED_PLACEHOLDER,
        "",
        "This implementation slice deliberately does not classify the three fields above from the "
        "per-workload table or the guest-call increment summary - see AGENTS.work/PERFORMANCE.md "
        "and `config/perf014-direct-closure-call.json`'s `timing_classification_note`. No "
        "threshold (2x, 5x, 10x, ...) is hardcoded anywhere in this harness for that decision; the "
        "classification is a later interpretation step performed against this Evidence Unit's raw "
        "retained data, not part of this harness.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    manifest_names = ["README.md", "raw.json", "stationarity.tsv", "perf014-summary.tsv"]
    manifest_lines = [f"{sha256(output_dir / n)}  {n}" for n in manifest_names]
    if logs_dir.is_dir():
        for log_path in sorted(logs_dir.iterdir()):
            manifest_lines.append(f"{sha256(log_path)}  logs/{log_path.name}")
    (output_dir / "SHA256SUMS").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    print("PERF014_DIRECT_CLOSURE_CALL_COMPARATOR=PASS")
    print("PERF014_EVIDENCE_STATUS=" + evidence_status)
    print("PERF014_FULL_MATRIX_EVIDENCE_UNIT=" + ("YES" if is_full_matrix_run else "NO"))
    print("CONTROL_PRODUCT_REVISION=" + cfg["control"]["protos_revision"])
    print("CONTROL_PRODUCT_VERSION=" + cfg["control"]["protos_version"])
    print("INTERVENTION_PRODUCT_REVISION=" + cfg["intervention"]["protos_revision"])
    print("INTERVENTION_PRODUCT_VERSION=" + cfg["intervention"]["protos_version"])
    print("INTERVENING_BUG010_REVISION=" + cfg["intervening_unrelated_revision"]["protos_revision"])
    print("CPU_AFFINITY=" + cpu)
    print("PERF014_WARMUP=" + str(cfg["warmup_iterations"]))
    print("PERF014_STEADY=" + str(cfg["steady_iterations"]))
    print("PERF014_OPERATION_COUNT=" + str(cfg["operation_count"]))
    print("PERF014_BLOCK_ORDER=" + ",".join(block_order))
    print("WORKLOAD_SOURCE_IDENTITY=PASS")
    print("CORRECTNESS=PASS")

    friendly_names = {
        "micro/slot-read": "SLOT_READ",
        "micro/closure-call": "CLOSURE_CALL",
        "micro/method-call": "METHOD_CALL",
        "runtime/monomorphic-dispatch": "MONOMORPHIC_DISPATCH",
    }
    for workload, s in per_workload_summary.items():
        print(
            f"WORKLOAD={workload} "
            f"PAIRED_CONTROL_EFFECT_MEDIAN_PERCENT={s['paired_control_effect_median_percent']:.4f} "
            f"ORDER_EFFECT={s['order_effect']}"
        )
        name = friendly_names.get(workload)
        if name is not None:
            print(f"{name}_EFFECT={s['paired_control_effect_median_percent']:.4f}")
            print(f"{name}_MAD={s['paired_control_effect_mad_percent']:.4f}")
            if workload in cfg["primary_causal_workloads"]:
                print(f"{name}_MIN={s['paired_control_effect_min_percent']:.4f}")
                print(f"{name}_MAX={s['paired_control_effect_max_percent']:.4f}")
                print(f"{name}_ORDER_EFFECT={s['order_effect']}")

    if guest_call_increment_summary is not None:
        g = guest_call_increment_summary
        print(f"CONTROL_GUEST_CALL_INCREMENT_NS={g['control_guest_call_increment_median_ns']:.1f}")
        print(
            "INTERVENTION_GUEST_CALL_INCREMENT_NS="
            f"{g['intervention_guest_call_increment_median_ns']:.1f}"
        )
        print(
            "GUEST_CALL_INCREMENT_REDUCTION_NS="
            f"{g['guest_call_increment_reduction_median_ns']:.1f}"
        )
        print(f"GUEST_CALL_INCREMENT_RATIO={g['guest_call_increment_ratio_of_medians']}")
        print(
            "PER_BLOCK_GUEST_CALL_INCREMENTS="
            f"control={g['per_block_control_guest_call_increment_ns']} "
            f"intervention={g['per_block_intervention_guest_call_increment_ns']} "
            f"reduction={g['per_block_guest_call_increment_reduction_ns']} "
            f"ratio={g['per_block_guest_call_increment_ratio']}"
        )

    print(
        "STATIONARITY_MAX_ABS_LAST_VS_FIRST_QUARTER_PERCENT="
        f"{max(abs(s['last_quarter_vs_first_quarter_percent']) for s in stationarity_by_unit):.4f}"
    )
    print(
        "ORDER_EFFECT_BY_WORKLOAD="
        + json.dumps({w: s["order_effect"] for w, s in per_workload_summary.items()})
    )
    print("PERF014_TIMING_CLASSIFICATION=" + PERF014_TIMING_CLASSIFICATION_PLACEHOLDER)
    print("PERF014_CLEARLY_MULTIPLICATIVE=" + PERF014_CLEARLY_MULTIPLICATIVE_PLACEHOLDER)
    print("PERF015_AUTHORIZED=" + PERF015_AUTHORIZED_PLACEHOLDER)
    print("PRODUCTION_OPTIMIZATION_SELECTED=NO")
    print("PERF014_PROTOS_REPOSITORY_MODIFICATION=NONE")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("validate", "smoke", "reference"))
    ap.add_argument(
        "--harness-revision",
        help="optional explicit expected harness SHA; when omitted, current clean HEAD is used "
        "(reference only)",
    )
    ap.add_argument("--output-dir")
    ap.add_argument(
        "--block-order",
        help="reference only: comma-separated override of the block order (e.g. 'A' for a "
        "single-block bounded validation run); defaults to the full "
        "config/perf014-direct-closure-call.json block_order (A,B,A,B) and must be omitted for "
        "the retained Evidence Unit run",
    )
    ap.add_argument(
        "--workload",
        action="append",
        help="reference only: restrict to this workload id (repeatable, e.g. --workload "
        "micro/closure-call); defaults to all four workloads and must be omitted for the "
        "retained Evidence Unit run",
    )
    args = ap.parse_args()

    if args.command == "validate":
        validate()
        return

    if args.command == "smoke":
        smoke()
        return

    output_dir = Path(args.output_dir) if args.output_dir else None
    block_order_override = tuple(args.block_order.split(",")) if args.block_order else None
    workload_ids = tuple(args.workload) if args.workload else None
    reference(
        args.harness_revision, output_dir,
        block_order_override=block_order_override, workload_ids=workload_ids,
    )


if __name__ == "__main__":
    main()
