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

"""PERF010-A / #691 post-I072 Candidate F' causal two-revision comparator.

Answers one question: what is the causal steady-state runtime effect of the complete I072
Candidate F' implementation (PLAT040: guarded stable semantic selection + exact lookup-stability
Assumption + direct/inlineable call target + compact frame-argument invocation ABI + conditional
guest Context/Array materialization + optional-state separation + exact generic fallback) on the
established common-path workloads? I072 Phases A-E landing structurally does not by itself
establish how much performance was recovered; this module is the causal-attribution owner for
that question (`config/perf010a-post-i072-fprime.json`'s `causal_question`).

This is a **new evidence namespace**, not a modification of the accepted PERF010-A Phase 2
comparator (`config/perf010a-phase2.json`, `runner/perf010a.py`'s `validate_phase2`/
`phase2_smoke`/`reference_phase2`). It deliberately reuses that comparator's discipline -
counterbalanced A,B,A,B block order, canonical+workload-control pairing, steady-state-only
timing with no JFR/compiler-tracing/IGV/allocation instrumentation, and the same
`paired_control_effect` causal formula - rather than inventing a new statistical methodology, but
is implemented as its own self-contained module: like `runner/perf010a_post_i068_baseline.py` and
`runner/perf010a_context_materialization.py` before it, and unlike `runner/perf009a.py` (which is
not driven through the Makefile in script mode), every PERF010-A Makefile target invokes its
runner as `python3 runner/<module>.py ...`, which puts only `runner/` (not the repository root) on
`sys.path`; `from runner.perf010a import ...` fails under that invocation
(`ModuleNotFoundError: No module named 'runner'`), so the small set of shared helpers this module
needs from `runner/perf010a.py` (timing/build/probe/stationarity machinery) are ported here rather
than imported, exactly like those two prior modules already do.

Two revisions, both `VARIANT=baseline`, no patch ever applied to either image
(`docker/protos-perf010a/Dockerfile` only applies a patch when `VARIANT=ablation`, which this
module never requests):

  * CONTROL - fixed, frozen in `config/perf010a-post-i072-fprime.json`:
    `2d8f04a8a01ff8639e98e03fba9a176170d54936` (`0.3.89-SNAPSHOT`). Deliberately not the PLAT040
    ratification revision: i069 (native guest runtime compilation) landed between PLAT040
    ratification and the start of I072 and changed PE-visible runtime source, so comparing final
    I072 against the ratification revision would confound I072 with i069. This is the exact I072
    Phase A base and must not change without a new Evidence Unit - see the config's
    `control.protos_revision_note`.
  * INTERVENTION - the final published I072 Phase E product revision. This is a run-time evidence
    identity supplied by the human executing `smoke`/`reference` (`--intervention-revision`/
    `--intervention-version`, or `INTERVENTION_REVISION`/`INTERVENTION_VERSION` on the Makefile
    targets), never a harness-authoring-time constant and never discovered by this module from
    GitHub or another checkout. `require_intervention_identity` fails closed when the revision is
    missing, is not exactly 40 lowercase hexadecimal characters (rejecting a floating branch
    name), equals the pinned control revision, or when the version is missing; `smoke`/`reference`
    additionally fail closed if the built intervention image's own
    `org.opencontainers.image.revision` LABEL or `pom.xml` version does not match what was
    requested (`_build_and_probe_images`), so drift is caught from the artifact itself, not merely
    from the Python-side value that was passed in.

Workload classification differs from Phase 2's 2x2 split because the causal question differs:
I072 F' primarily changes call/dispatch/invocation architecture, so `micro/closure-call`,
`micro/method-call` and `runtime/monomorphic-dispatch` (whose hot loop is a call/dispatch site)
are PRIMARY; `micro/slot-read` does not exercise a call/dispatch site and is retained as
negative/broader-common-path coverage - it discriminates a real I072 call-path effect from generic
whole-runtime movement. The retained Evidence Unit still includes all four workloads
unconditionally (see `config/perf010a-post-i072-fprime.json`'s `workload_coverage_note`).

Before any timing, `_verify_workload_source_identity` reads back every workload's exact canonical
source text from both built images and fails closed (`WORKLOAD_SOURCE_IDENTITY_MISMATCH`) if their
SHA-256 digests differ, so the two revisions are never silently compared on a changed program.

`validate << smoke << reference`, matching every other command in this repository's PERF010-A
family: `validate` is static/configuration-only (no Docker, no timing, and self-tests
`require_intervention_identity`'s fail-closed contract with synthetic inputs); `smoke` builds and
probes both exact images and runs the full four-workload matrix at a tiny iteration count
(`SMOKE_WARMUP_ITERATIONS`/`SMOKE_STEADY_ITERATIONS`) as a correctness/admission gate whose timing
is never retained as evidence; `reference` is the only command that uses the full
`warmup_iterations`/`steady_iterations` (120/100) Evidence Unit scale and the only command whose
output is retained, under `results/perf010a-post-i072-fprime/`. `reference` also accepts
`--block-order`/`--workload` overrides for a bounded, still full-warmup, still-real-timed-unit
validation run before the full matrix - mirroring `reference_phase2`'s identical bounded-validation
contract in `runner/perf010a.py` - which requires an explicit scratch `--output-dir`, rejects
`--harness-revision`, and is written out with `evidence_status="VALIDATION_ONLY_NOT_RETAINED"`.

This module deliberately does not mechanically classify `I072_FPRIME_CAUSAL_EFFECT`/
`I072_FPRIME_BIG_COST`/`PERF010A_DOMINANT_CAUSE`/`ATTRIBUTABLE_FRACTION`/`NEXT_CAUSAL_BOUNDARY`:
`reference` prints and retains the raw computed per-workload `paired_control_effect` statistics
(median/MAD/min/max, order effect) but leaves those fields as explicit `NOT_CLASSIFIED`/
`NOT_ESTABLISHED` placeholders in `raw.json` and `README.md`, matching `reference_phase2`'s
identical discipline for its own analogous unclassified fields - the scale classification requires
human judgment against the retained data (a crisp threshold such as exactly 5x is not to be forced
if the data does not support one) and is a later interpretation step, not part of this harness. See
`config/perf010a-post-i072-fprime.json`'s `scale_classification_note`.

This module does not select or implement a PERF010 production optimization
(`diagnostic_claim: false` because this is a causal two-revision comparator, not a diagnostic
ablation - but exactly like Phase 2, `causal_runtime_speedup`-shaped conclusions belong to a later
investigation slice reading this Evidence Unit's raw retained data).
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
CONFIG = ROOT / "config/perf010a-post-i072-fprime.json"
B2D_CONFIG = ROOT / "config/perf004b2d.json"
PHASE2_CONFIG = ROOT / "config/perf010a-phase2.json"
DOCKERFILE = ROOT / "docker/protos-perf010a/Dockerfile"
TIMING_DRIVER = ROOT / "docker/protos-perf010a/Perf010aTimingDriver.java"
UNUSED_PATCH = ROOT / "docker/protos-perf010a/noop.patch"
MAKEFILE = ROOT / "Makefile"

EXPECTED_SLICE = "PERF010A_POST_I072_FPRIME_CAUSAL_COMPARATOR"
EXPECTED_CONTROL_REVISION = "2d8f04a8a01ff8639e98e03fba9a176170d54936"
EXPECTED_CONTROL_VERSION = "0.3.89-SNAPSHOT"
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
PRIMARY_WORKLOADS = ("micro/closure-call", "micro/method-call", "runtime/monomorphic-dispatch")
NEGATIVE_COVERAGE_WORKLOADS = ("micro/slot-read",)
OUTPUT_DIR = ROOT / "results/perf010a-post-i072-fprime"

# Deliberately far smaller than the Evidence Unit's own warmup=120/steady=100, matching every
# other `*_smoke` in this repository's PERF010-A family (runner/perf010a.py's identically-valued
# SMOKE_WARMUP_ITERATIONS/SMOKE_STEADY_ITERATIONS). Every steady iteration is still individually
# correctness-checked by Perf010aTimingDriver's requireCompletedInteger regardless of count, so
# this loses no correctness coverage; it only avoids collecting statistically meaningful timing.
SMOKE_WARMUP_ITERATIONS = 1
SMOKE_STEADY_ITERATIONS = 2

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


# --- generic process/config helpers (ported unmodified from runner/perf010a.py - see this
#     module's docstring for why they are ported rather than imported) ---


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
    """Non-retained declared harness identity for `smoke` only; see `runner/perf010a.py`'s
    identically-named helper for the full rationale."""
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
    `runner/perf010a.py`."""
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
    Ported unmodified from `runner/perf010a.py`'s identically-named helper."""
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


# --- intervention identity (the one contract this module adds beyond Phase 2's shape) ---


def require_intervention_identity(revision: str | None, version: str | None) -> tuple[str, str]:
    """Fails closed exactly as `config/perf010a-post-i072-fprime.json`'s
    `intervention_input_contract` declares. The intervention protos_revision/protos_version are
    run-time evidence identity supplied by the human, never harness constants; this function is
    the single place that enforces their shape before any Docker build is attempted."""
    if not revision:
        raise RuntimeError(
            "INTERVENTION_REVISION_MISSING: --intervention-revision (the exact 40-lowercase-hex "
            "final I072 Phase E Protos SHA) is required; it is a run-time evidence identity "
            "supplied by the human, never a harness constant"
        )
    if not SHA_RE.fullmatch(revision):
        raise RuntimeError(
            "INTERVENTION_REVISION_INVALID: expected exactly 40 lowercase hexadecimal characters "
            f"(a floating branch name is forbidden), got {revision!r}"
        )
    if revision == EXPECTED_CONTROL_REVISION:
        raise RuntimeError(
            "INTERVENTION_REVISION_EQUALS_CONTROL: intervention must differ from the pinned "
            f"control revision {EXPECTED_CONTROL_REVISION}"
        )
    if version is None or not version.strip():
        raise RuntimeError("INTERVENTION_VERSION_MISSING: --intervention-version is required")
    return revision, version.strip()


# --- validate: static/configuration only, no Docker, no timing ---


def validate() -> dict[str, Any]:
    cfg = load(CONFIG)

    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF010-A"
    assert cfg["parent_perf_item"] == "PERF010"
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
    assert intervention["protos_revision"] is None, (
        "intervention protos_revision must stay unpinned in config - it is supplied at run time"
    )
    assert intervention["protos_version"] is None, (
        "intervention protos_version must stay unpinned in config - it is supplied at run time"
    )

    contract = cfg["intervention_input_contract"]
    assert contract["supplied_by"] == "human_at_execution_time"
    assert set(contract["cli_flags"]) == {"--intervention-revision", "--intervention-version"}
    assert contract["floating_branch_forbidden"] is True
    assert contract["must_differ_from_control_revision"] is True

    assert cfg["both_variants_baseline"] is True
    assert cfg["patches_applied"] == "none"

    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 120
    assert cfg["steady_iterations"] == 100

    b2d_cfg = load(B2D_CONFIG)
    assert cfg["controls"] == b2d_cfg["controls"], (
        "must reuse the exact PERF004-B2-D/PERF008 four-workload matrix unmodified"
    )
    all_workload_ids = {item["id"] for item in cfg["controls"]}
    assert set(cfg["primary_causal_workloads"]) == set(PRIMARY_WORKLOADS)
    assert set(cfg["negative_coverage_workloads"]) == set(NEGATIVE_COVERAGE_WORKLOADS)
    assert set(cfg["primary_causal_workloads"]) | set(cfg["negative_coverage_workloads"]) == (
        all_workload_ids
    )
    assert set(cfg["primary_causal_workloads"]) & set(cfg["negative_coverage_workloads"]) == set()

    assert tuple(cfg["block_order"]) == BLOCK_ORDER
    assert len(cfg["block_order"]) >= 4
    assert set(cfg["block_order"]) == {"A", "B"}
    assert cfg["block_order"].count("A") >= 2 and cfg["block_order"].count("B") >= 2

    assert cfg["toolchain"] == EXPECTED_TOOLCHAIN, "toolchain drift"

    assert cfg["output"] == "results/perf010a-post-i072-fprime"

    for path in (
        CONFIG, B2D_CONFIG, DOCKERFILE, TIMING_DRIVER, UNUSED_PATCH,
        ROOT / "docker/protos-perf006d/Perf006dRuntimeProbe.java",
    ):
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
    for target in (
        "perf010a-post-i072-validate:",
        "perf010a-post-i072-smoke:",
        "perf010a-post-i072-reference:",
    ):
        assert target in makefile_text, "missing Makefile target: " + target[:-1]

    # Self-test require_intervention_identity's fail-closed contract with synthetic inputs, so
    # `validate` proves the intervention-input contract without needing Docker or a real
    # intervention revision (which does not exist yet at validation time).
    _EXAMPLE_OTHER_REVISION = "1111111111111111111111111111111111111111"
    for bad_revision, bad_version, reason in (
        (None, "0.3.99-SNAPSHOT", "missing revision"),
        ("", "0.3.99-SNAPSHOT", "empty revision"),
        ("not-a-sha", "0.3.99-SNAPSHOT", "malformed revision"),
        ("deadbeef", "0.3.99-SNAPSHOT", "short revision"),
        ("DEADBEEF00000000000000000000000000000000".lower()[:39] + "G", "0.3.99-SNAPSHOT",
         "non-hex revision"),
        (EXPECTED_CONTROL_REVISION, "0.3.99-SNAPSHOT", "revision equals control"),
        (_EXAMPLE_OTHER_REVISION, None, "missing version"),
        (_EXAMPLE_OTHER_REVISION, "   ", "blank version"),
    ):
        try:
            require_intervention_identity(bad_revision, bad_version)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"require_intervention_identity accepted invalid input: {reason}")
    accepted_revision, accepted_version = require_intervention_identity(
        _EXAMPLE_OTHER_REVISION, "  0.3.99-SNAPSHOT  "
    )
    assert accepted_revision == _EXAMPLE_OTHER_REVISION
    assert accepted_version == "0.3.99-SNAPSHOT", "must strip surrounding whitespace"

    # Historical PERF010-A Phase 2 contract remains untouched by this new evidence namespace.
    phase2_cfg = load(PHASE2_CONFIG)
    assert phase2_cfg["slice"] == "PERF010A_PHASE2_CAUSAL_TWO_REVISION_COMPARATOR"
    assert phase2_cfg["control"]["protos_revision"] == "2b3a88389da7228caed231a90b14091cf2841115"
    assert phase2_cfg["intervention"]["protos_revision"] == "3e8e6b565c95eb5098c2168d241536ba13ad19e9"
    assert phase2_cfg["output"] == "results/perf010a-phase2"

    print("PERF010A_POST_I072_FPRIME_CONFIG=PASS")
    print("PERF010A_POST_I072_FPRIME_INTERVENTION_INPUT_CONTRACT=PASS")
    print("PERF010A_POST_I072_FPRIME_HISTORICAL_PHASE2_CONTRACT_UNTOUCHED=PASS")
    print("CONTROL_PRODUCT_REVISION=" + control["protos_revision"])
    print("CONTROL_PRODUCT_VERSION=" + control["protos_version"])
    print("INTERVENTION_PRODUCT_REVISION=EXACT_SHA_REQUIRED")
    print("INTERVENTION_PRODUCT_VERSION=EXACT_VERSION_REQUIRED")
    print("PERF010A_POST_I072_FPRIME_BOTH_PRODUCT_VARIANTS_BASELINE=YES")
    print("PERF010A_POST_I072_FPRIME_PATCHES_APPLIED=NO")
    print("PERF010A_POST_I072_FPRIME_WARMUP=" + str(cfg["warmup_iterations"]))
    print("PERF010A_POST_I072_FPRIME_STEADY=" + str(cfg["steady_iterations"]))
    print("PERF010A_POST_I072_FPRIME_OPERATION_COUNT=" + str(cfg["operation_count"]))
    print("PERF010A_POST_I072_FPRIME_BLOCK_ORDER=" + ",".join(cfg["block_order"]))
    print("PERF010A_POST_I072_FPRIME_PRIMARY_WORKLOADS=" + ",".join(cfg["primary_causal_workloads"]))
    print(
        "PERF010A_POST_I072_FPRIME_NEGATIVE_COVERAGE_WORKLOADS="
        + ",".join(cfg["negative_coverage_workloads"])
    )
    print("I072_FPRIME_CAUSAL_EFFECT=NOT_MEASURED")
    print("PERF010A_DOMINANT_CAUSE=NOT_ESTABLISHED")
    print("ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED")
    print("PRODUCTION_OPTIMIZATION_SELECTED=NO")
    return cfg


# --- build/probe (Docker, no timing) ---


def build_image(role: str, revision: str, toolchain: dict[str, Any], protos_repository: str, slice_label: str) -> str:
    tag = f"protos-benchmarks-perf010a-post-i072-fprime-{role}:{revision[:12]}"
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
    artifact, exactly like `runner/perf010a_post_i068_baseline.py`'s `product_version_probe`."""
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
    (`config/perf010a-post-i072-fprime.json`'s `workload_identity_policy`). Reads each workload's
    exact canonical source text back from both built images (a plain `docker run --entrypoint
    /bin/cat`, unaffected by CPU affinity - matching `control_source`'s identical precedent) and
    fails closed on any digest mismatch, rather than silently comparing a changed program across
    revisions."""
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
                "config/perf010a-post-i072-fprime.json"
            )
        digests[item["id"]] = role_digests
    return digests


def _build_and_probe_images(
    cfg: dict[str, Any], intervention_revision: str, intervention_version: str, cpu: str,
) -> dict[str, Any]:
    """Builds the control and intervention images (both VARIANT=baseline, from two different
    pinned protos_revision values) and fails closed before returning unless all of the following
    hold for BOTH roles: `/opt/perf010a/variant.txt` reads "baseline";
    `/opt/perf010a/ablation-slice.txt` reads "none"; the image's own
    `org.opencontainers.image.revision` LABEL matches that role's expected pinned protos_revision;
    and the image's own `pom.xml` version matches that role's expected protos_version. Also proves
    every workload's canonical source is byte-identical between the two images before returning.
    """
    role_revisions = {
        "control": cfg["control"]["protos_revision"],
        "intervention": intervention_revision,
    }
    role_versions = {
        "control": cfg["control"]["protos_version"],
        "intervention": intervention_version,
    }
    if role_revisions["control"] == role_revisions["intervention"]:
        raise RuntimeError(
            "INTERVENTION_REVISION_EQUALS_CONTROL: control and intervention protos_revision must differ"
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
                f"POST_I072_FPRIME_PATCH_PATH_REJECTED: role={role} image reports "
                f"ablation-slice={observed_slice!r}, expected 'none' - a baseline-variant image "
                "must never have gone through the patch-apply path"
            )

        observed_revision = image_revision_label_probe(tag)
        if observed_revision != role_revision:
            raise RuntimeError(
                f"POST_I072_FPRIME_REVISION_IDENTITY_MISMATCH: role={role} image's own "
                f"org.opencontainers.image.revision label reads {observed_revision!r}, expected "
                f"{role_revision!r}"
            )

        observed_version = image_version_probe(tag, cpu)
        if observed_version != role_version:
            raise RuntimeError(
                f"POST_I072_FPRIME_VERSION_IDENTITY_MISMATCH: role={role} image's own pom.xml "
                f"version reads {observed_version!r}, expected {role_version!r}"
            )

        identities[role] = image_identity(tag)
        print(
            f"POST_I072_FPRIME IMAGE role={role} protos_revision={role_revision} "
            f"protos_version={role_version} tag={tag} id={identities[role]['id']} "
            f"repo_digests={identities[role]['repo_digests']}",
            flush=True,
        )

    workload_source_sha256 = _verify_workload_source_identity(cfg["controls"], tags)

    print("POST_I072_FPRIME_CONTROL_INTERVENTION_REVISIONS_DISTINCT=PASS")
    print("POST_I072_FPRIME_BOTH_IMAGES_VARIANT_BASELINE=PASS")
    print("POST_I072_FPRIME_BOTH_IMAGES_ABLATION_SLICE_NONE=PASS")
    print("POST_I072_FPRIME_BOTH_IMAGES_REVISION_LABEL_MATCH=PASS")
    print("POST_I072_FPRIME_BOTH_IMAGES_VERSION_MATCH=PASS")
    print("POST_I072_FPRIME_WORKLOAD_SOURCE_IDENTITY=PASS")
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
    unmodified from `runner/perf010a.py`'s identically-named helper (already used by the accepted
    Phase 1/Phase 2 Evidence Units)."""
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
    print(f"POST_I072_FPRIME TIMING BEGIN label={label} warmup={warmup} steady={steady}", flush=True)
    p = run_visible(command)

    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"{label}.stdout.log"
    stderr_path = logs_dir / f"{label}.stderr.log"
    stdout_path.write_text(p.stdout, encoding="utf-8")
    stderr_path.write_text(p.stderr, encoding="utf-8")

    if p.returncode != 0:
        print(
            f"POST_I072_FPRIME TIMING FAIL label={label} returncode={p.returncode} "
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
    """Counterbalanced block matrix - structurally identical to `runner/perf010a.py`'s
    `run_phase2_blocks` (same `control_source` canonical/workload-control construction, same
    `timing_visible` per-timed-unit retention/stationarity), reused here under this module's own
    name/print-prefix so its records can never be confused with Phase 1/Phase 2/discrimination
    records. `controls` defaults to `cfg["controls"]` (the full four-workload matrix); a caller may
    pass a subset only for a bounded validation run (see `reference`'s `workload_ids`), never for
    the retained reference run itself."""
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
                        f"POST_I072_FPRIME TIMING PASS block={block_index} order={block_label} "
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
    """Causal formula fixed by `config/perf010a-post-i072-fprime.json`'s `causal_formula`
    (reused unchanged from `config/perf010a-phase2.json`), before any data is collected:

        canonical_improvement  = control_canonical_median_ns - intervention_canonical_median_ns
        control_movement       = control_workload_control_median_ns
                                  - intervention_workload_control_median_ns
        paired_control_effect  = canonical_improvement - control_movement

    A positive `paired_control_effect` means INTERVENTION (the final I072 Phase E revision) is
    faster than CONTROL once the workload-control's own measured movement between the two
    revisions/images has been subtracted out. Expressed as a percentage of the control canonical
    median. This function does not classify LARGE_MULTI_X/MATERIAL_PERCENT_SCALE/NEAR_ZERO/
    REGRESSION/DOMINANT_GAP_CAUSE/ATTRIBUTABLE_FRACTION - see this module's docstring and
    `config/perf010a-post-i072-fprime.json`'s `scale_classification_note`."""
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
    }


def summarize_workload(classified_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive envelope for one workload across all retained blocks - explicitly a
    DESCRIPTIVE_ENVELOPE, not a fabricated inferential confidence interval, matching
    `runner/perf010a.py`'s `summarize_phase2_workload` discipline exactly."""
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


def smoke(intervention_revision: str | None, intervention_version: str | None) -> None:
    cfg = validate()
    intervention_revision, intervention_version = require_intervention_identity(
        intervention_revision, intervention_version
    )
    harness_revision = worktree_harness_revision()
    cpu = first_cpu()
    build_result = _build_and_probe_images(cfg, intervention_revision, intervention_version, cpu)
    tags = build_result["tags"]

    with tempfile.TemporaryDirectory(prefix="perf010a-post-i072-fprime-smoke-") as tmp:
        work = Path(tmp)
        logs_dir = work / "logs"
        blocks = run_blocks(
            cfg, tags, cpu, work, logs_dir,
            block_order=("A", "B"),
            warmup=SMOKE_WARMUP_ITERATIONS, steady=SMOKE_STEADY_ITERATIONS,
            collect_stationarity=False,
        )

    print("PERF010A_POST_I072_FPRIME_SMOKE_HARNESS_REVISION=" + harness_revision)
    print("CONTROL_PRODUCT_REVISION=" + cfg["control"]["protos_revision"])
    print("INTERVENTION_PRODUCT_REVISION=" + intervention_revision)
    print(
        f"PERF010A_POST_I072_FPRIME_SMOKE_SCALE=warmup={SMOKE_WARMUP_ITERATIONS} "
        f"steady={SMOKE_STEADY_ITERATIONS} (Evidence Unit scale: "
        f"warmup={cfg['warmup_iterations']} steady={cfg['steady_iterations']})"
    )
    print("PERF010A_POST_I072_FPRIME_SMOKE_BLOCKS=" + str(len({b['block_index'] for b in blocks})))
    print("PERF010A_POST_I072_FPRIME_SMOKE_WORKLOADS=" + str(len(cfg["controls"])))
    print("PERF010A_POST_I072_FPRIME_CORRECTNESS=PASS")
    print("PERF010A_POST_I072_FPRIME_SMOKE=PASS")
    print("PERF010A_POST_I072_FPRIME_SMOKE_RETAINED_PERFORMANCE_EVIDENCE=NO")


# --- reference: full retained Evidence Unit ---


def reference(
    harness_revision: str | None,
    output_dir: Path | None,
    intervention_revision: str | None,
    intervention_version: str | None,
    *,
    block_order_override: tuple[str, ...] | None = None,
    workload_ids: tuple[str, ...] | None = None,
) -> None:
    """Full warmup=120/steady=100/operation_count=10000/block_order=A,B,A,B Evidence Unit,
    reusing this module's counterbalanced-block/paired-workload-control machinery with the
    `classify_block` causal formula. Deliberately does not classify I072_FPRIME_CAUSAL_EFFECT,
    I072_FPRIME_BIG_COST, PERF010A_DOMINANT_CAUSE, or ATTRIBUTABLE_FRACTION - see this module's
    docstring.

    `block_order_override`/`workload_ids` exist only so a bounded, still full-warmup=120,
    still-real-timed-unit validation run can exercise a small subset of the matrix - including
    from the dirty working tree that contains the harness changes under validation, before they
    are committed - exactly mirroring `runner/perf010a.py`'s `reference_phase2` bounded-validation
    contract:

      - requires an explicit scratch `--output-dir` (never defaults to OUTPUT_DIR, which is
        reserved for the retained run);
      - rejects an explicit `--harness-revision` (only the retained run pins one);
      - records `harness_revision` via `worktree_harness_revision()` instead; and
      - is written out with `evidence_status="VALIDATION_ONLY_NOT_RETAINED"` in `raw.json`, a
        printed evidence-status marker, and a top-of-README banner.
    """
    cfg = validate()
    intervention_revision, intervention_version = require_intervention_identity(
        intervention_revision, intervention_version
    )
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
    build_result = _build_and_probe_images(cfg, intervention_revision, intervention_version, cpu)
    tags = build_result["tags"]
    image_identities = build_result["image_identity"]
    workload_source_sha256 = build_result["workload_source_sha256"]

    output_dir.mkdir(parents=True)
    logs_dir = output_dir / "logs"

    with tempfile.TemporaryDirectory(prefix="perf010a-post-i072-fprime-") as tmp:
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
        "perf_item": "PERF010-A",
        "parent_perf_item": "PERF010",
        "slice": cfg["slice"],
        "phase": cfg["phase"],
        "diagnostic_claim": False,
        "causal_two_revision_comparator": True,
        "full_matrix_evidence_unit": is_full_matrix_run,
        "evidence_status": evidence_status,
        "harness_revision": harness_revision,
        "control_protos_revision": cfg["control"]["protos_revision"],
        "control_protos_version": cfg["control"]["protos_version"],
        "intervention_protos_revision": intervention_revision,
        "intervention_protos_version": intervention_version,
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
        "i072_fprime_causal_effect": "NOT_CLASSIFIED",
        "i072_fprime_big_cost": "NOT_CLASSIFIED",
        "dominant_gap_cause": "NOT_ESTABLISHED",
        "attributable_fraction": "NOT_ESTABLISHED",
        "next_causal_boundary": "NOT_ESTABLISHED",
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
    (output_dir / "post-i072-fprime-summary.tsv").write_text(
        "\n".join(summary_rows) + "\n", encoding="utf-8"
    )

    readme = [
        "# PERF010-A post-I072 Candidate F' causal two-revision comparator Evidence Unit",
        "",
    ]
    if not is_full_matrix_run:
        readme += [
            "> **VALIDATION_ONLY_NOT_RETAINED** - this is a bounded run (`--block-order`/"
            "`--workload`) over a subset of the matrix, produced to validate the harness itself, "
            "not the retained Evidence Unit. It may have been executed from a dirty (uncommitted) "
            "working tree - see `harness_revision` below, which reads `WORKTREE_PRECOMMIT` when "
            "that is the case. It MUST NOT be cited as PERF010-A post-I072 evidence. The retained "
            "Evidence Unit is the full four-workload, full-block-order run with no overrides, "
            "executed from a clean exact harness revision, written to "
            "`results/perf010a-post-i072-fprime`.",
            "",
        ]
    readme += [
        cfg["causal_question"],
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Control Protos revision (VARIANT=baseline): `{cfg['control']['protos_revision']}` "
        f"(`{cfg['control']['protos_version']}`)",
        f"- Intervention Protos revision (VARIANT=baseline): `{intervention_revision}` "
        f"(`{intervention_version}`)",
        "- Patches applied to either image: NONE (see `patches_applied` and "
        "`POST_I072_FPRIME_BOTH_IMAGES_ABLATION_SLICE_NONE` in the run log).",
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
        "## Stationarity (first-quarter vs. last-quarter of each 100-sample steady timed unit)",
        "",
        "See `stationarity.tsv` for the full per-timed-unit table (raw `raw.json` remains "
        "authoritative).",
        "",
        "## I072_FPRIME_CAUSAL_EFFECT = NOT_CLASSIFIED",
        "## I072_FPRIME_BIG_COST = NOT_CLASSIFIED",
        "## PERF010A_DOMINANT_CAUSE = NOT_ESTABLISHED",
        "## ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED",
        "## NEXT_CAUSAL_BOUNDARY = NOT_ESTABLISHED",
        "## PRODUCTION_OPTIMIZATION_SELECTED = NO",
        "",
        "This implementation slice deliberately does not classify the six fields above from the "
        "per-workload table - see AGENTS.work/PERFORMANCE.md and "
        "`config/perf010a-post-i072-fprime.json`'s `scale_classification_note`. The scale "
        "classification (LARGE_MULTI_X / MATERIAL_PERCENT_SCALE / SMALL_PERCENT_SCALE / "
        "NEAR_ZERO / REGRESSION / INCONCLUSIVE) is a later interpretation step performed against "
        "this Evidence Unit's raw retained data, not part of this harness.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    manifest_names = ["README.md", "raw.json", "stationarity.tsv", "post-i072-fprime-summary.tsv"]
    manifest_lines = [f"{sha256(output_dir / n)}  {n}" for n in manifest_names]
    if logs_dir.is_dir():
        for log_path in sorted(logs_dir.iterdir()):
            manifest_lines.append(f"{sha256(log_path)}  logs/{log_path.name}")
    (output_dir / "SHA256SUMS").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    print("PERF010A_POST_I072_FPRIME_COMPARATOR=PASS")
    print("PERF010A_POST_I072_FPRIME_EVIDENCE_STATUS=" + evidence_status)
    print("PERF010A_POST_I072_FPRIME_FULL_MATRIX_EVIDENCE_UNIT=" + ("YES" if is_full_matrix_run else "NO"))
    print("CONTROL_PRODUCT_REVISION=" + cfg["control"]["protos_revision"])
    print("CONTROL_PRODUCT_VERSION=" + cfg["control"]["protos_version"])
    print("INTERVENTION_PRODUCT_REVISION=" + intervention_revision)
    print("INTERVENTION_PRODUCT_VERSION=" + intervention_version)
    print("PERF010A_POST_I072_FPRIME_WARMUP=" + str(cfg["warmup_iterations"]))
    print("PERF010A_POST_I072_FPRIME_STEADY=" + str(cfg["steady_iterations"]))
    for workload, s in per_workload_summary.items():
        print(
            f"WORKLOAD={workload} "
            f"PAIRED_CONTROL_EFFECT_MEDIAN_PERCENT={s['paired_control_effect_median_percent']:.4f} "
            f"ORDER_EFFECT={s['order_effect']}"
        )
    print("I072_FPRIME_CAUSAL_EFFECT=NOT_CLASSIFIED")
    print("I072_FPRIME_BIG_COST=NOT_CLASSIFIED")
    print("PERF010A_DOMINANT_CAUSE=NOT_ESTABLISHED")
    print("ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED")
    print("NEXT_CAUSAL_BOUNDARY=NOT_ESTABLISHED")
    print("PRODUCTION_OPTIMIZATION_SELECTED=NO")
    print("PERF010A_PROTOS_REPOSITORY_MODIFICATION=NONE")


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
        "--intervention-revision",
        help="required for smoke/reference: exact 40-lowercase-hex final I072 Phase E Protos SHA "
        "(a run-time evidence identity supplied by the human, never a harness constant)",
    )
    ap.add_argument(
        "--intervention-version",
        help="required for smoke/reference: exact final I072 Phase E Protos version string",
    )
    ap.add_argument(
        "--block-order",
        help="reference only: comma-separated override of the block order (e.g. 'A' for a "
        "single-block bounded validation run); defaults to the full "
        "config/perf010a-post-i072-fprime.json block_order (A,B,A,B) and must be omitted for the "
        "retained Evidence Unit run",
    )
    ap.add_argument(
        "--workload",
        action="append",
        help="reference only: restrict to this workload id (repeatable, e.g. --workload "
        "micro/method-call); defaults to all four workloads and must be omitted for the retained "
        "Evidence Unit run",
    )
    args = ap.parse_args()

    if args.command == "validate":
        validate()
        return

    if args.command == "smoke":
        smoke(args.intervention_revision, args.intervention_version)
        return

    output_dir = Path(args.output_dir) if args.output_dir else None
    block_order_override = tuple(args.block_order.split(",")) if args.block_order else None
    workload_ids = tuple(args.workload) if args.workload else None
    reference(
        args.harness_revision, output_dir, args.intervention_revision, args.intervention_version,
        block_order_override=block_order_override, workload_ids=workload_ids,
    )


if __name__ == "__main__":
    main()
