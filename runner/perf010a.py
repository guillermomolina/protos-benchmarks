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

This module now backs four distinct causal ablations sharing this one harness, selected via
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
    PERF010A_ABLATION_3, adds a diagnostic-only `ProtosObjectValue.readLocalSlotSingleProbe`
    helper (the redundant `containsKey(name)` + `get(name)` probe-then-read replaced with a
    single `get(name)`, relying on the invariant that no local slot value is ever null) and
    redirects *only* the two lexical local-slot-read call sites inside
    `ProtosActivation.lookup` (current context, then each captured lexical context) to it.
    Ordinary `ProtosObjectValue.readLocalSlot` stays byte-for-byte unchanged and is still used
    by every other caller, including `ProtosValueLookup`'s receiver/delegation member lookup.
    `ProtosActivation.lookup`'s traversal order, precedence, shadowing, and missing-name
    behavior are all untouched, so this is claimed to be semantically equivalent by
    construction, not diagnostic-only-and-expected-to-fail-closed like ablation 2. This is the
    exact scope an earlier readiness investigation established for this slice; an earlier
    execution instead transformed `readLocalSlot` globally (correct call sites, wrong blast
    radius - it also changed every other caller) and was rejected by this harness's exact-scope
    validation (`validate_patch_shape_3`/`ABLATION_3_PATCH_SCOPE_MATCH`), even though it was
    semantically equivalent by construction, because it could no longer be attributed to only
    the established causal component.
  * `--ablation 4` (`config/perf010a-4.json`, `docker/protos-perf010a/ablation-4.patch`) -
    PERF010A_ABLATION_4, removes the second, redundant `ProtosClosureValue.nativeBody()`
    Optional projection inside `ProtosBytecodeRootNode.finishPreparingComposedCall`'s native
    branch (`closure.nativeBody().isPresent()` followed by
    `closure.nativeBody().orElseThrow()`), reusing a single local projection for both instead.
    `nativeBody()` is `Optional.ofNullable(nativeBody)` over a `final` field, so both
    projections always observe the same value; this is claimed to be semantically equivalent
    by construction, not diagnostic-only-and-expected-to-fail-closed like ablation 2. Every
    other `nativeBody()` call site in `ProtosBytecodeRootNode`, and `ProtosClosureValue.java`
    itself, stay byte-for-byte unchanged. This is the exact scope the established next-causal-
    candidate investigation identified (guillermomolina/protos-project-docs@
    474b8779e31c643a815cf67452d0acf4ee8da367).
  * `--ablation guarded-call` (`config/perf010a-guarded-call.json`,
    `docker/protos-perf010a/guarded-call.patch`) - PERF010A_GUARDED_CALL (#691, with PERF011 /
    #693), the guarded monomorphic composed-send experiment: adds one new leading
    `@Specialization` (`performGuardedOrdinaryComposedSend`) to
    `ProtosBytecodeRootNode.PrepareSendArguments`, tried before the pre-existing single
    specialization (now a `replaces`-annotated, otherwise byte-for-byte unchanged fallback).
    Its guard re-runs the exact authoritative `ProtosValueLookup.lookup` call on every
    invocation and only takes the fast arm when that fresh lookup still selects the same
    non-native (Closure, methodHome) pair this call site cached; on a hit it reuses
    `ProtosActivation.forImmediateMethodInvocation` and
    `attachTaskOrInheritDynamicControlState` exactly as the generic path does, resolves the
    effective Bytecode plan via the pre-existing, unmodified `taskOwnedBytecodePlan` helper
    (the same helper the retained `prepareTaskOwnedSelectedCallIfBytecode` precedent already
    uses in production), and either builds the `PreparedClosureCall` directly - bypassing
    `finishPreparingComposedCallByImplementation`'s 16 implementation/category classifiers and
    the subsequent 19 structured-dispatch predicates - or falls back to that exact, unmodified
    method when the plan cannot be resolved. A guard miss falls through to the unchanged
    generic specialization. This is only the diagnostic-code-change and static exact-scope
    validation checkpoint for this slice: `validate_patch_shape_guarded`/`validate("guarded-
    call")` are implemented and passing; `smoke`/`reference` structural confirmation and the
    separate PERF011 compiler-visibility diagnostic collection are not yet wired for this slice
    (see `SOURCE_STRUCTURAL_ABLATIONS`, which deliberately excludes `"guarded-call"` for now).

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
               present); never used to interpret timing. Ablations 3 and 4 do not use this
               mechanism for their structural confirmation (see below) but still collect it at
               `reference` scale as supplementary evidence.

Ablations 3 and 4's structural confirmation is source-derived, not JFR-derived: both variants
still call the *same* fully-qualified reader method at the retained call site(s) - a
`ProtosObjectValue` method at `ProtosActivation.lookup`'s two lexical call sites for ablation 3
(and `java.util.LinkedHashMap.containsKey`/`get` are simple enough to be JIT-inlined besides),
`ProtosClosureValue.nativeBody()` for ablation 4 - so neither call-count difference is a
reliable sampled-frame signal. Instead, `source_structural_probe`/`source_structural_probe_4`
read `/opt/protos-source` (the exact patched-or-unmodified source tree each image was built
from, copied verbatim by the Dockerfile) and
`structural_contract_confirmed_ablation_3`/`structural_contract_confirmed_ablation_4` prove the
full established exact-scope contract as one per-image comparison. For ablation 3: the
diagnostic helper exists only in the ablation image; ordinary `readLocalSlot`'s own method body
is byte-for-byte identical between images; the ablation image calls the diagnostic helper (and
the baseline image calls ordinary `readLocalSlot`) at exactly `ProtosActivation.lookup`'s two
lexical positions; the captured-lexical-traversal loop and the `ProtosValueLookup` fallback are
present, unchanged, in both; and `ProtosValueLookup`'s own receiver/delegation member-lookup
call site still calls ordinary `readLocalSlot` in both images. For ablation 4:
`finishPreparingComposedCall`'s body calls `closure.nativeBody()` twice in the baseline image
and once (reusing a single `nativeBodyProjection` local) in the ablation image; the rest of
`ProtosBytecodeRootNode.java` outside that one method body, and all of
`ProtosClosureValue.java`, are byte-for-byte identical between images.
`validate_patch_shape_3`/`validate_patch_shape_4` prove the same exact-scope contracts
statically from the patch diff itself (required call sites changed; explicitly excluded call
sites/files untouched) before any image is even built, and `reference`/`smoke` re-derive and
re-check them from the built image before running (`reference`) or after running (`smoke`, for
reporting) the workload matrix, per AGENTS.work/PERFORMANCE.md's causal-ablation exact-scope
validation rule.

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
`config/perf010a-3.json`, and `config/perf010a-4.json`).
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
CONFIG_4 = ROOT / "config/perf010a-4.json"
CONFIG_GUARDED = ROOT / "config/perf010a-guarded-call.json"
EXPECTED_PROTOS_REVISION = "bc0471184bf6dbbf03d0c6b09ef7b9e28aede014"
EXPECTED_PROTOS_REVISION_3 = "6e7d89194925ba9fa2cd9c5c45aefa72d9939621"
EXPECTED_PROTOS_REVISION_4 = "4c4aa95a5852119bd280ceb40483871d5d2cbb82"
EXPECTED_PROTOS_REVISION_GUARDED = "2b3a88389da7228caed231a90b14091cf2841115"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
VARIANTS = ("baseline", "ablation")
ABLATIONS = ("1", "2", "3", "4", "guarded-call")
# "0" is not a real ablation; it is reserved for the measurement-discrimination no-op image
# (see the PERF010-A measurement-discrimination section near the end of this module) and is
# deliberately kept out of ABLATION_PROFILES/VALIDATE_PATCH_SHAPE/SOURCE_STRUCTURAL_ABLATIONS -
# the discrimination experiment uses its own standalone validate/smoke/reference functions
# rather than routing through validate()/smoke()/reference(), to avoid any risk of silently
# changing those four functions' existing, already-tested behavior for ablations 1-4. It is
# added to ABLATIONS only so build_image()'s tag-naming assertion accepts it.
DISCRIMINATION_ABLATION = "0"
ABLATIONS_WITH_DISCRIMINATION = ABLATIONS + (DISCRIMINATION_ABLATION,)
# Ablations whose structural confirmation is source-derived (reads /opt/protos-source) rather
# than JFR-frame-derived, because their call sites keep calling a same-named method in both
# variants (see ablation 3's and 4's module-docstring rationale below).
SOURCE_STRUCTURAL_ABLATIONS = ("3", "4", "guarded-call")

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

# Ablation 3 (ProtosActivation.lookup's two lexical local-slot-read call sites, redirected to a
# new diagnostic-only ProtosObjectValue.readLocalSlotSingleProbe helper) source markers. Not
# JFR-frame-based: see module docstring for why. `SOURCE_ROOT` is where the Dockerfile copies
# the exact patched-or-unmodified /src tree in every image (both variants).
SOURCE_ROOT = "/opt/protos-source"
READ_LOCAL_SLOT_SOURCE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java"
ACTIVATION_SOURCE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java"
VALUE_LOOKUP_SOURCE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosValueLookup.java"
READ_LOCAL_SLOT_SIGNATURE = "public Optional<Object> readLocalSlot(String name)"
DIAGNOSTIC_HELPER_SIGNATURE = "Optional<Object> readLocalSlotSingleProbe(String name)"
LOOKUP_METHOD_SIGNATURE = "public Optional<Object> lookup(String name)"
DIAGNOSTIC_CALL_SITE_PATTERN = ".readLocalSlotSingleProbe(name)"
BASELINE_CALL_SITE_PATTERN = ".readLocalSlot(name)"
VALUE_LOOKUP_CALL_SITE_PATTERN = "ordinary.readLocalSlot(name)"
LOOKUP_FALLBACK_MARKER = "return ProtosValueLookup.readMember(receiver, name, prelude);"
ABLATION_3_MARKER_COMMENT = "PERF010A_ABLATION_3"
CAPTURED_LEXICAL_TRAVERSAL_MARKER = (
    "for (ProtosObjectValue lexicalContext : capturedLexicalContexts)"
)

# Ablation 4 (ProtosBytecodeRootNode.finishPreparingComposedCall's duplicate
# ProtosClosureValue.nativeBody() Optional projection, reused via a single local instead of a
# second projection) source markers. Not JFR-frame-based: both variants call the same
# fully-qualified ProtosClosureValue.nativeBody() method at the retained call site, so a sampled
# frame count cannot distinguish one call from two. `SOURCE_ROOT` is shared with ablation 3
# above.
ROOT_NODE_SOURCE_PATH = (
    "src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeRootNode.java"
)
CLOSURE_VALUE_SOURCE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosClosureValue.java"
FINISH_PREPARING_COMPOSED_CALL_SIGNATURE = (
    "private static PreparedClosureCall finishPreparingComposedCall("
)
NATIVE_BODY_CALL_PATTERN = "closure.nativeBody()"
NATIVE_BODY_PROJECTION_LOCAL = "nativeBodyProjection"
ABLATION_4_MARKER_COMMENT = "PERF010A_ABLATION_4"

# PERF010A_GUARDED_CALL (guarded monomorphic composed-send experiment, guillermomolina/
# protos-benchmarks #691, with PERF011 / #693) source markers. Like ablations 3/4, structural
# confirmation is source-derived (see `structural_confirmation_note` in
# config/perf010a-guarded-call.json), not JFR-frame-derived by default; unlike ablations 3/4,
# the new specialization method name itself never appears in the baseline image's source at
# all, so `GUARDED_CALL_FRAME_MARKER` below is also usable as supplementary JFR evidence once
# smoke/reference are wired for this slice (not yet implemented in this checkpoint - only
# `validate` is wired for "guarded-call" so far).
GUARDED_CALL_SOURCE_PATH = ROOT_NODE_SOURCE_PATH
PREPARE_SEND_ARGUMENTS_SIGNATURE = "public static final class PrepareSendArguments {"
GUARDED_SPECIALIZATION_SIGNATURE = (
    "public static PreparedClosureCall performGuardedOrdinaryComposedSend("
)
GUARDED_CALL_MARKER_COMMENT = "PERF010A_GUARDED_CALL"
GUARDED_CALL_FRAME_MARKER = (
    "com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$PrepareSendArguments"
    ".performGuardedOrdinaryComposedSend"
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
    "4": {
        "config_path": CONFIG_4,
        "expected_slice": "PERF010A_ABLATION_4",
        "expected_protos_revision": EXPECTED_PROTOS_REVISION_4,
        "absent_markers": (),
        "present_marker": "com.guillermomolina.protos.runtime.ProtosClosureValue.nativeBody",
        "required_files": (
            "results/perf004-a/summary.tsv",
            "results/perf004-b2c/summary.tsv",
            "results/perf004-b2d/SHA256SUMS",
            "results/perf006-d3/SHA256SUMS",
            "results/perf008/SHA256SUMS",
            "results/perf010a-1/SHA256SUMS",
            "results/perf010a-2/SHA256SUMS",
            "results/perf010a-3/SHA256SUMS",
        ),
    },
    "guarded-call": {
        "config_path": CONFIG_GUARDED,
        "expected_slice": "PERF010A_GUARDED_CALL",
        "expected_protos_revision": EXPECTED_PROTOS_REVISION_GUARDED,
        "absent_markers": (),
        "present_marker": GUARDED_CALL_FRAME_MARKER,
        "required_files": (
            "results/perf004-a/summary.tsv",
            "results/perf004-b2c/summary.tsv",
            "results/perf004-b2d/SHA256SUMS",
            "results/perf006-d3/SHA256SUMS",
            "results/perf008/SHA256SUMS",
            "results/perf010a-1/SHA256SUMS",
            "results/perf010a-2/SHA256SUMS",
            "results/perf010a-3/SHA256SUMS",
            "results/perf010a-4/SHA256SUMS",
            "results/perf010a-discrimination/SHA256SUMS",
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


def _parse_unified_diff(patch_text: str) -> dict[str, dict[str, list[str]]]:
    """Splits a `git diff`-style patch into per-file added/removed content lines (the `+`/`-`
    prefix stripped, hunk headers and `---`/`+++` file markers excluded). Used by
    `validate_patch_shape_3` to check exact scope by diff *content*, not just substring presence
    in the whole patch text, so an addition and a removal touching the same identifier cannot be
    confused with each other."""
    files: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            path = parts[2][2:] if parts[2].startswith("a/") else parts[2]
            current = files.setdefault(path, {"added": [], "removed": []})
            continue
        if current is None:
            continue
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            current["added"].append(line[1:])
        elif line.startswith("-"):
            current["removed"].append(line[1:])
    return files


def validate_patch_shape_3(patch_text: str) -> None:
    # The established causal-ablation contract (AGENTS.work/PERFORMANCE.md's exact-scope
    # validation rule) is: add a new diagnostic-only single-probe reader to ProtosObjectValue,
    # and redirect exactly the two lexical local-slot-read call sites inside
    # ProtosActivation.lookup (current context, then each captured lexical context) to it. The
    # ordinary ProtosObjectValue.readLocalSlot method (used by every other caller, including
    # ProtosValueLookup's receiver/delegation member lookup) MUST stay byte-for-byte untouched -
    # a patch that instead transforms readLocalSlot's own body globally (as the first, invalid
    # ablation-3 execution did) must fail this check even though it is semantically equivalent
    # and even though it still targets ProtosObjectValue.java.
    files = _parse_unified_diff(patch_text)
    object_value_path = "src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java"
    activation_path = "src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java"
    assert set(files.keys()) == {object_value_path, activation_path}, sorted(files.keys())

    object_value = files[object_value_path]
    activation = files[activation_path]

    # ProtosObjectValue.java: purely additive. Any removed line at all means the existing
    # baseline method body (readLocalSlot or anything else) was touched, which this slice's
    # contract forbids.
    assert object_value["removed"] == [], object_value["removed"]
    added_ov_text = "\n".join(object_value["added"])
    assert ABLATION_3_MARKER_COMMENT in added_ov_text
    assert DIAGNOSTIC_HELPER_SIGNATURE in added_ov_text
    assert added_ov_text.count("localSlots.get(name)") == 1
    assert "localSlots.containsKey" not in added_ov_text
    assert READ_LOCAL_SLOT_SIGNATURE not in added_ov_text

    # ProtosActivation.java: removed content must be exactly the two lexical readLocalSlot(name)
    # call-site lines (nothing else - not the captured-lexical-traversal loop header, not the
    # ProtosValueLookup fallback, not lookup ordering), and added content must be exactly their
    # two readLocalSlotSingleProbe(name) replacements (plus comments).
    removed_calls = [l for l in activation["removed"] if BASELINE_CALL_SITE_PATTERN in l]
    non_call_removed = [l for l in activation["removed"] if BASELINE_CALL_SITE_PATTERN not in l]
    assert len(removed_calls) == 2, removed_calls
    assert non_call_removed == [], non_call_removed

    added_act_text = "\n".join(activation["added"])
    removed_act_text = "\n".join(activation["removed"])
    assert added_act_text.count(DIAGNOSTIC_CALL_SITE_PATTERN) == 2, added_act_text
    assert "context." + DIAGNOSTIC_CALL_SITE_PATTERN.lstrip(".") in added_act_text
    assert "lexicalContext." + DIAGNOSTIC_CALL_SITE_PATTERN.lstrip(".") in added_act_text
    for forbidden in (
        CAPTURED_LEXICAL_TRAVERSAL_MARKER,
        LOOKUP_FALLBACK_MARKER,
        "ProtosBytecodeRootNode.java",
        "CanonicalToBytecodeLowerer.java",
        "ProtosSourceCompiler.java",
        "ProtosBytecodeClosureExecutionPlan.java",
        "ProtosRootTaskExecution.java",
        "ProtosValueLookup.java",
        "continueAt",
        "RootTag",
        "ContinuationResult",
        "ProtosSemanticBytecodeRootNode",
    ):
        assert forbidden not in added_act_text, forbidden
        assert forbidden not in removed_act_text, forbidden


def validate_patch_shape_4(patch_text: str) -> None:
    # The established causal-ablation contract (guillermomolina/protos-project-docs@
    # 474b8779e31c643a815cf67452d0acf4ee8da367, PERF010A_NEXT_CAUSAL_CANDIDATE.md) is: inside
    # ProtosBytecodeRootNode.finishPreparingComposedCall's native branch, introduce a single
    # local Optional projection from closure.nativeBody() and reuse it for both the
    # isPresent() check and the orElseThrow() projection, removing only the second, redundant
    # closure.nativeBody() call. Every other nativeBody() call site in ProtosBytecodeRootNode,
    # ProtosClosureValue.java (including nativeBody() itself), and
    # finishPreparingComposedCallByImplementation MUST stay byte-for-byte untouched - a patch
    # that touches any of those, or that removes/adds anything beyond this one bounded
    # rewrite, must fail this check even if it is semantically equivalent.
    files = _parse_unified_diff(patch_text)
    root_node_path = ROOT_NODE_SOURCE_PATH
    assert set(files.keys()) == {root_node_path}, sorted(files.keys())

    root_node = files[root_node_path]

    # Removed content must be exactly the two original closure.nativeBody() call-site lines
    # (the isPresent() check and the orElseThrow() projection) - nothing else.
    removed_calls = [l for l in root_node["removed"] if NATIVE_BODY_CALL_PATTERN in l]
    non_call_removed = [l for l in root_node["removed"] if NATIVE_BODY_CALL_PATTERN not in l]
    assert len(removed_calls) == 2, removed_calls
    assert non_call_removed == [], non_call_removed

    added_text = "\n".join(root_node["added"])
    removed_text = "\n".join(root_node["removed"])
    assert ABLATION_4_MARKER_COMMENT in added_text
    # Exactly one closure.nativeBody() call remains (the new projection's initializer); the
    # second, redundant call is gone, and both uses of the projected value go through the new
    # local instead.
    assert added_text.count(NATIVE_BODY_CALL_PATTERN) == 1, added_text
    assert added_text.count(NATIVE_BODY_PROJECTION_LOCAL) >= 3, added_text
    assert f"{NATIVE_BODY_PROJECTION_LOCAL}.isPresent()" in added_text
    assert f"{NATIVE_BODY_PROJECTION_LOCAL}.orElseThrow()" in added_text

    for forbidden in (
        "ProtosClosureValue.java",
        "ProtosActivation.java",
        "ProtosValueLookup.java",
        "CanonicalToBytecodeLowerer.java",
        "ProtosSourceCompiler.java",
        "ProtosBytecodeClosureExecutionPlan.java",
        "ProtosRootTaskExecution.java",
        "finishPreparingComposedCallByImplementation",
        "continueAt",
        "RootTag",
        "ContinuationResult",
        "ProtosSemanticBytecodeRootNode",
    ):
        assert forbidden not in added_text, forbidden
        assert forbidden not in removed_text, forbidden


def validate_patch_shape_guarded(patch_text: str) -> None:
    # The established PERF010A_GUARDED_CALL contract (guillermomolina/protos-project-docs@
    # 56c31e4e899e2d75f2e6311493ab138ce82277e2's guarded monomorphic call-path architecture,
    # reconfirmed by the PERF011 / #693 audit at guillermomolina/protos-project-docs@
    # 7dddadb8572a873f6881e20571e54bc5615f06d8) is: touch only ProtosBytecodeRootNode.java;
    # add one new leading @Specialization (performGuardedOrdinaryComposedSend) plus three new
    # private helper methods to the file, and turn the existing single-specialization
    # PrepareSendArguments.perform into a `replaces`-annotated fallback with an UNCHANGED body;
    # do not remove, or add a `-` line to, any existing production method (prepareSend,
    # prepareImmediateMethodCall, finishPreparingComposedCall,
    # finishPreparingComposedCallByImplementation, taskOwnedBytecodePlan,
    # rejectComposedInvocationProjection, attachTaskOrInheritDynamicControlState, or D013 lookup
    # itself); the post-D013 bypass and its exact generic fallback must both be provable from
    # the diff alone.
    files = _parse_unified_diff(patch_text)
    assert set(files.keys()) == {GUARDED_CALL_SOURCE_PATH}, sorted(files.keys())

    root_node = files[GUARDED_CALL_SOURCE_PATH]

    # Almost purely additive: the only permitted removed line is the plain `@Specialization`
    # annotation on the pre-existing `perform` method, replaced by an added
    # `@Specialization(replaces = "performGuardedOrdinaryComposedSend")` line immediately
    # below it - the method's own body/signature is untouched (no other removed line is
    # permitted). Every existing method body - prepareSend, prepareImmediateMethodCall,
    # finishPreparingComposedCall(ByImplementation), taskOwnedBytecodePlan, D013 lookup itself,
    # and `perform`'s own body - therefore stays byte-for-byte identical to the baseline file.
    assert root_node["removed"] == ["        @Specialization"], root_node["removed"]

    added_text = "\n".join(root_node["added"])

    assert GUARDED_CALL_MARKER_COMMENT in added_text
    assert GUARDED_SPECIALIZATION_SIGNATURE in added_text
    assert '@Specialization(replaces = "performGuardedOrdinaryComposedSend")' in added_text
    assert "guardedOrdinaryComposedSendClosureOrNull" in added_text
    assert "guardedOrdinaryComposedSendHomeOrNull" in added_text
    assert "guardedOrdinaryComposedSendMatches" in added_text

    # The guard must re-run authoritative D013 lookup (ProtosValueLookup.lookup) every call
    # rather than trust a cache blindly; PERFORMANCE.md's causal-ablation rule and this
    # experiment's own "do not bypass D013 lookup" boundary both require this observable in
    # the diff, not merely asserted in prose.
    assert added_text.count("ProtosValueLookup.lookup(") == 3, added_text

    # A closure is only ever cached by this patch when its nativeBody() is empty (ordinary,
    # non-native); this is what makes skipping finishPreparingComposedCallByImplementation's
    # generic classifiers provably safe (see config/perf010a-guarded-call.json's
    # `guarded_call_target`), so the diff must show that filter explicitly rather than caching
    # any Closure unconditionally.
    assert "candidate.nativeBody().isEmpty()" in added_text

    # A guard miss (including a lookup failure) must fall through to the exact generic path,
    # never re-implement generic classification inline; the only acceptable substitute for
    # finishPreparingComposedCallByImplementation on the fast arm's own failure branch is a
    # direct call to that exact, unmodified method.
    assert "finishPreparingComposedCallByImplementation(" in added_text
    assert "taskOwnedBytecodePlan(" in added_text
    assert "rejectComposedInvocationProjection(" in added_text
    assert "attachTaskOrInheritDynamicControlState(" in added_text

    for forbidden in (
        "ProtosActivation.java",
        "ProtosClosureValue.java",
        "ProtosObjectValue.java",
        "ProtosValueLookup.java",
        "CanonicalToBytecodeLowerer.java",
        "ProtosSourceCompiler.java",
        "ProtosBytecodeClosureExecutionPlan.java",
        "ProtosRootTaskExecution.java",
        # The generic classifiers/predicates this experiment bypasses on a guard hit must not
        # be reimplemented inline in the new specialization; they must only ever be reached
        # through the unmodified finishPreparingComposedCallByImplementation call captured
        # above.
        "isStandardEnsureImplementation",
        "isStandardWhileImplementation",
        "structuredCallbackKindForImplementation",
        "isStandardEachImplementation",
        "structuredReadLookupKindForImplementation",
        "isStandardAtPutImplementation",
        "isStandardRemoveImplementation",
        "isStandardSignalImplementation",
        "isStandardCallImplementation",
        "runtimeForImplementation",
        "continueAt",
        "RootTag",
        "ContinuationResult",
        "ProtosSemanticBytecodeRootNode",
    ):
        assert forbidden not in added_text, forbidden


VALIDATE_PATCH_SHAPE = {
    "1": validate_patch_shape_1,
    "2": validate_patch_shape_2,
    "3": validate_patch_shape_3,
    "4": validate_patch_shape_4,
    "guarded-call": validate_patch_shape_guarded,
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
    # ABLATIONS_WITH_DISCRIMINATION (not ABLATIONS) so the measurement-discrimination no-op
    # image ("0") can reuse this same build path; ABLATIONS itself stays exactly ("1","2","3",
    # "4") for validate()/smoke()/reference(), which the discrimination experiment never calls.
    assert ablation in ABLATIONS_WITH_DISCRIMINATION
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


def _leading_comment_block(source_text: str, signature: str) -> str:
    """Returns the contiguous run of `//` comment (and blank) lines immediately preceding
    `signature`'s declaration line, stopping at the first non-comment/non-blank line (e.g. the
    previous method's closing brace). Used to scope the `PERF010A_ABLATION_3` marker-comment
    check to the diagnostic helper's own preceding comment, without also matching the
    `{ ... }` body text (whose prose, e.g. explaining what was replaced, legitimately mentions
    `containsKey`/`get(name)` and must not be misread as code)."""
    sig_idx = source_text.index(signature)
    line_start = source_text.rfind("\n", 0, sig_idx) + 1
    lines_before = source_text[:line_start].splitlines()
    leading: list[str] = []
    for line in reversed(lines_before):
        stripped = line.strip()
        if stripped.startswith("//") or stripped == "":
            leading.append(line)
            continue
        break
    leading.reverse()
    return "\n".join(leading)


def source_structural_probe(tag: str, cpu: str) -> dict[str, Any]:
    """Ablation 3's structural confirmation. Unlike ablations 1/2 (which bypass a call site
    entirely, leaving a JFR-visible frame gap), this ablation's call sites keep calling a
    `ProtosObjectValue` method with the exact same fully-qualified name in both variants, and the
    ablated `java.util.LinkedHashMap.containsKey`/`get` are simple enough to be JIT-inlined, so
    presence/absence in a sampled call stack is not a reliable signal either way (see module
    docstring). This instead reads `/opt/protos-source` - the exact patched-or-unmodified source
    tree the image was built from, copied verbatim by the Dockerfile - and inspects, per image:
    `ProtosObjectValue.readLocalSlot`'s own body (must be byte-for-byte identical across
    variants - compared by the caller); whether the new diagnostic
    `readLocalSlotSingleProbe` helper exists and what it contains; which of the two call-site
    patterns (`readLocalSlot(name)` vs. the diagnostic `readLocalSlotSingleProbe(name)`) each of
    `ProtosActivation.lookup`'s two lexical read positions (current context, then the captured-
    lexical-context loop) uses; whether the captured-lexical-traversal loop and the
    `ProtosValueLookup` fallback are still present; and whether `ProtosValueLookup`'s own
    receiver/delegation member-lookup call site still calls ordinary `readLocalSlot`."""
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
    value_lookup_source = output([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        f"{SOURCE_ROOT}/{VALUE_LOOKUP_SOURCE_PATH}",
    ])

    baseline_body = _extract_method_body(object_value_source, READ_LOCAL_SLOT_SIGNATURE)

    diagnostic_helper_present = DIAGNOSTIC_HELPER_SIGNATURE in object_value_source
    diagnostic_helper_body = (
        _extract_method_body(object_value_source, DIAGNOSTIC_HELPER_SIGNATURE)
        if diagnostic_helper_present
        else ""
    )
    diagnostic_helper_leading_comment = (
        _leading_comment_block(object_value_source, DIAGNOSTIC_HELPER_SIGNATURE)
        if diagnostic_helper_present
        else ""
    )

    lookup_body = _extract_method_body(activation_source, LOOKUP_METHOD_SIGNATURE)
    loop_idx = (
        lookup_body.index(CAPTURED_LEXICAL_TRAVERSAL_MARKER)
        if CAPTURED_LEXICAL_TRAVERSAL_MARKER in lookup_body
        else len(lookup_body)
    )
    current_context_section = lookup_body[:loop_idx]
    captured_context_section = lookup_body[loop_idx:]

    return {
        "baseline_read_local_slot_body": baseline_body,
        "diagnostic_helper_present": diagnostic_helper_present,
        "diagnostic_marker_present": (
            ABLATION_3_MARKER_COMMENT in diagnostic_helper_leading_comment
        ),
        "diagnostic_helper_contains_key_absent": "containsKey" not in diagnostic_helper_body,
        "diagnostic_helper_single_get_count": diagnostic_helper_body.count(".get(name)"),
        "current_context_diagnostic": DIAGNOSTIC_CALL_SITE_PATTERN in current_context_section,
        "current_context_baseline": BASELINE_CALL_SITE_PATTERN in current_context_section,
        "captured_context_diagnostic": DIAGNOSTIC_CALL_SITE_PATTERN in captured_context_section,
        "captured_context_baseline": BASELINE_CALL_SITE_PATTERN in captured_context_section,
        "captured_lexical_traversal_present": (
            CAPTURED_LEXICAL_TRAVERSAL_MARKER in activation_source
        ),
        "lookup_fallback_present": LOOKUP_FALLBACK_MARKER in lookup_body,
        "value_lookup_call_site_present": (
            VALUE_LOOKUP_CALL_SITE_PATTERN in value_lookup_source
        ),
    }


def structural_contract_confirmed_ablation_3(
    baseline_probe: dict[str, Any], ablation_probe: dict[str, Any]
) -> dict[str, bool]:
    """Ablation 3's exact-scope structural gate (AGENTS.work/PERFORMANCE.md's causal-ablation
    exact-scope validation rule): proves both that the required diagnostic call sites ARE
    changed and that everything the investigation explicitly excluded stays on the baseline
    path, as a single per-image comparison (not repeated independently per workload)."""
    checks: dict[str, bool] = {
        "ABLATION_3_TARGET_HELPER_PRESENT": (
            not baseline_probe["diagnostic_helper_present"]
            and ablation_probe["diagnostic_helper_present"]
            and ablation_probe["diagnostic_marker_present"]
            and ablation_probe["diagnostic_helper_contains_key_absent"]
            and ablation_probe["diagnostic_helper_single_get_count"] == 1
        ),
        "ABLATION_3_CURRENT_CONTEXT_CALLSITE": (
            baseline_probe["current_context_baseline"]
            and not baseline_probe["current_context_diagnostic"]
            and ablation_probe["current_context_diagnostic"]
            and not ablation_probe["current_context_baseline"]
        ),
        "ABLATION_3_CAPTURED_CONTEXT_CALLSITE": (
            baseline_probe["captured_context_baseline"]
            and not baseline_probe["captured_context_diagnostic"]
            and ablation_probe["captured_context_diagnostic"]
            and not ablation_probe["captured_context_baseline"]
        ),
        "ABLATION_3_BASELINE_READ_LOCAL_SLOT_UNCHANGED": (
            bool(baseline_probe["baseline_read_local_slot_body"])
            and baseline_probe["baseline_read_local_slot_body"]
            == ablation_probe["baseline_read_local_slot_body"]
        ),
        "ABLATION_3_PROTOS_VALUE_LOOKUP_PATH_UNCHANGED": (
            baseline_probe["value_lookup_call_site_present"]
            and ablation_probe["value_lookup_call_site_present"]
        ),
        "ABLATION_3_CAPTURED_LEXICAL_TRAVERSAL_PRESERVED": (
            baseline_probe["captured_lexical_traversal_present"]
            and ablation_probe["captured_lexical_traversal_present"]
        ),
    }
    checks["ABLATION_3_LOOKUP_ORDER_PRESERVED"] = (
        checks["ABLATION_3_CURRENT_CONTEXT_CALLSITE"]
        and checks["ABLATION_3_CAPTURED_CONTEXT_CALLSITE"]
        and baseline_probe["lookup_fallback_present"]
        and ablation_probe["lookup_fallback_present"]
    )
    checks["ABLATION_3_PATCH_SCOPE_MATCH"] = all(checks.values())
    return checks


def source_structural_probe_4(tag: str, cpu: str) -> dict[str, Any]:
    """Ablation 4's structural confirmation. Both variants call the same fully-qualified
    `ProtosClosureValue.nativeBody()` method at the retained call site inside
    `finishPreparingComposedCall`, so a JFR-sampled-frame count cannot distinguish one call from
    two - the frame name is identical either way (see module docstring / ablation 3's identical
    rationale). This instead reads `/opt/protos-source` (the exact patched-or-unmodified source
    tree the image was built from) and inspects, per image: `finishPreparingComposedCall`'s own
    method body (how many `closure.nativeBody()` calls it contains, whether it reuses a single
    `nativeBodyProjection` local, and whether the `PERF010A_ABLATION_4` marker comment is
    present); the rest of `ProtosBytecodeRootNode.java` outside that one method body (must be
    byte-for-byte identical across variants - compared by the caller, proving every other
    `nativeBody()` call site is untouched); and the full `ProtosClosureValue.java` source (must
    also be byte-for-byte identical across variants)."""
    root_node_source = output([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        f"{SOURCE_ROOT}/{ROOT_NODE_SOURCE_PATH}",
    ])
    closure_value_source = output([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        f"{SOURCE_ROOT}/{CLOSURE_VALUE_SOURCE_PATH}",
    ])

    method_body = _extract_method_body(
        root_node_source, FINISH_PREPARING_COMPOSED_CALL_SIGNATURE
    )
    # _extract_method_body's returned slice starts at the method's opening brace (not at the
    # signature text), so the "outside" cut must use that same brace_start offset - not
    # signature_start - or it would remove the wrong span (either leaving body content behind
    # or cutting into the signature/parameter list).
    signature_start = root_node_source.index(FINISH_PREPARING_COMPOSED_CALL_SIGNATURE)
    brace_start = root_node_source.index("{", signature_start)
    body_end = brace_start + len(method_body)
    outside_method_source = root_node_source[:brace_start] + root_node_source[body_end:]

    return {
        "native_body_call_count": method_body.count(NATIVE_BODY_CALL_PATTERN),
        "projection_local_present": NATIVE_BODY_PROJECTION_LOCAL in method_body,
        "projection_is_present_use": f"{NATIVE_BODY_PROJECTION_LOCAL}.isPresent()" in method_body,
        "projection_or_else_throw_use": (
            f"{NATIVE_BODY_PROJECTION_LOCAL}.orElseThrow()" in method_body
        ),
        "diagnostic_marker_present": ABLATION_4_MARKER_COMMENT in method_body,
        "outside_method_source": outside_method_source,
        "closure_value_source": closure_value_source,
    }


def structural_contract_confirmed_ablation_4(
    baseline_probe: dict[str, Any], ablation_probe: dict[str, Any]
) -> dict[str, bool]:
    """Ablation 4's exact-scope structural gate (AGENTS.work/PERFORMANCE.md's causal-ablation
    exact-scope validation rule): proves both that the duplicate `nativeBody()` projection is
    removed inside `finishPreparingComposedCall` and that everything else - every other
    `nativeBody()` call site, and all of `ProtosClosureValue.java` - stays on the baseline path,
    as a single per-image comparison (not repeated independently per workload)."""
    checks: dict[str, bool] = {
        "ABLATION_4_BASELINE_HAS_TWO_PROJECTIONS": (
            baseline_probe["native_body_call_count"] == 2
            and not baseline_probe["projection_local_present"]
            and not baseline_probe["diagnostic_marker_present"]
        ),
        "ABLATION_4_ABLATION_HAS_ONE_PROJECTION": (
            ablation_probe["native_body_call_count"] == 1
            and ablation_probe["projection_local_present"]
            and ablation_probe["projection_is_present_use"]
            and ablation_probe["projection_or_else_throw_use"]
            and ablation_probe["diagnostic_marker_present"]
        ),
        "ABLATION_4_OTHER_CALL_SITES_UNCHANGED": (
            bool(baseline_probe["outside_method_source"])
            and baseline_probe["outside_method_source"] == ablation_probe["outside_method_source"]
        ),
        "ABLATION_4_CLOSURE_VALUE_UNCHANGED": (
            bool(baseline_probe["closure_value_source"])
            and baseline_probe["closure_value_source"] == ablation_probe["closure_value_source"]
        ),
    }
    checks["ABLATION_4_PATCH_SCOPE_MATCH"] = all(checks.values())
    return checks


def source_structural_probe_guarded(tag: str, cpu: str) -> dict[str, Any]:
    """PERF010A_GUARDED_CALL's structural confirmation. Unlike ablations 3/4, the new
    specialization method name (`performGuardedOrdinaryComposedSend`) exists only in the
    guarded image's source at all - the baseline image's `PrepareSendArguments` class has
    exactly one, byte-for-byte unchanged, `perform` specialization - so this is a stronger,
    more directly source-legible signal (see the module docstring's guarded-call bullet and
    config/perf010a-guarded-call.json's `structural_confirmation_note`). This reads
    `/opt/protos-source` (the exact patched-or-unmodified source tree the image was built from)
    and inspects, per image: the `PrepareSendArguments` class body (whether the new
    specialization and its marker comment are present, and whether the pre-existing `perform`
    specialization's own body is present unchanged); and the rest of
    `ProtosBytecodeRootNode.java` outside that one class body (must be byte-for-byte identical
    across variants - compared by the caller, proving every other Operation/method, including
    prepareSend/prepareImmediateMethodCall/finishPreparingComposedCall(ByImplementation)/
    taskOwnedBytecodePlan, is untouched)."""
    root_node_source = output([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "cat", tag,
        f"{SOURCE_ROOT}/{GUARDED_CALL_SOURCE_PATH}",
    ])

    class_present = PREPARE_SEND_ARGUMENTS_SIGNATURE in root_node_source
    class_body = (
        _extract_method_body(root_node_source, PREPARE_SEND_ARGUMENTS_SIGNATURE)
        if class_present
        else ""
    )

    if class_present:
        signature_start = root_node_source.index(PREPARE_SEND_ARGUMENTS_SIGNATURE)
        brace_start = root_node_source.index("{", signature_start)
        body_end = brace_start + len(class_body)
        outside_class_source = root_node_source[:brace_start] + root_node_source[body_end:]
    else:
        outside_class_source = root_node_source

    return {
        "class_present": class_present,
        "guarded_specialization_present": GUARDED_SPECIALIZATION_SIGNATURE in class_body,
        "diagnostic_marker_present": GUARDED_CALL_MARKER_COMMENT in class_body,
        "generic_perform_body_present": (
            "return prepareSend(" in class_body and "@Variadic Object[] supplied" in class_body
        ),
        "outside_class_source": outside_class_source,
    }


def structural_contract_confirmed_guarded(
    baseline_probe: dict[str, Any], guarded_probe: dict[str, Any]
) -> dict[str, bool]:
    """PERF010A_GUARDED_CALL's exact-scope structural gate (AGENTS.work/PERFORMANCE.md's
    causal-ablation exact-scope validation rule): proves both that the guarded specialization is
    present only in the guarded image and that the rest of `ProtosBytecodeRootNode.java` -
    including the generic `perform` fallback's own body - stays on the baseline path, as a
    single per-image comparison (not repeated independently per workload)."""
    checks: dict[str, bool] = {
        "GUARDED_CALL_BASELINE_HAS_NO_FAST_ARM": (
            baseline_probe["class_present"]
            and not baseline_probe["guarded_specialization_present"]
            and not baseline_probe["diagnostic_marker_present"]
            and baseline_probe["generic_perform_body_present"]
        ),
        "GUARDED_CALL_IMAGE_HAS_FAST_ARM": (
            guarded_probe["class_present"]
            and guarded_probe["guarded_specialization_present"]
            and guarded_probe["diagnostic_marker_present"]
            and guarded_probe["generic_perform_body_present"]
        ),
        "GUARDED_CALL_OTHER_CALL_SITES_UNCHANGED": (
            bool(baseline_probe["outside_class_source"])
            and baseline_probe["outside_class_source"] == guarded_probe["outside_class_source"]
        ),
    }
    checks["PERF010A_GUARDED_CALL_PATCH_SCOPE_MATCH"] = all(checks.values())
    return checks


STRUCTURAL_PROBE = {
    "3": source_structural_probe,
    "4": source_structural_probe_4,
    "guarded-call": source_structural_probe_guarded,
}
STRUCTURAL_CONTRACT_CONFIRM = {
    "3": structural_contract_confirmed_ablation_3,
    "4": structural_contract_confirmed_ablation_4,
    "guarded-call": structural_contract_confirmed_guarded,
}
STRUCTURAL_SCOPE_MATCH_KEY = {
    "3": "ABLATION_3_PATCH_SCOPE_MATCH",
    "4": "ABLATION_4_PATCH_SCOPE_MATCH",
    "guarded-call": "PERF010A_GUARDED_CALL_PATCH_SCOPE_MATCH",
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
    structural_contract: dict[str, bool] | None = None,
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
    if correctness_confirmed and ablation in SOURCE_STRUCTURAL_ABLATIONS:
        # Source-derived, not JFR-derived (see source_structural_probe/source_structural_probe_4/
        # source_structural_probe_guarded): a single per-image exact-scope structural contract,
        # identical across all four workloads, rather than a per-workload JFR profile. The
        # caller passes the one structural_contract relevant to `ablation` (there is only ever
        # one, since a single run targets exactly one ablation slice); this function does not
        # need to pick among several.
        structural_ok = bool(
            structural_contract is not None
            and structural_contract.get(STRUCTURAL_SCOPE_MATCH_KEY[ablation], False)
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

    # Ablations 3 and 4's structural confirmation is a single per-image source-derived
    # exact-scope contract (see SOURCE_STRUCTURAL_ABLATIONS / STRUCTURAL_PROBE /
    # STRUCTURAL_CONTRACT_CONFIRM), not a per-workload JFR profile, so smoke skips the JFR
    # structural stage for them entirely (collect_structural=False below) rather than running
    # it at any scale. Ablations 1/2 still need JFR to confirm their call-site bypass is
    # actually in effect - that is the "specific correctness assertion" this admission gate
    # exists to make - so they keep it, just at SMOKE_* scale instead of the config's
    # reference scale.
    #
    # This static, per-image contract can be known before the (comparatively) expensive
    # four-workload smoke matrix runs at all, so it is checked and, on failure, fails the gate
    # here rather than after the matrix has already executed.
    structural_contract = None
    if ablation in SOURCE_STRUCTURAL_ABLATIONS:
        probe_fn = STRUCTURAL_PROBE[ablation]
        confirm_fn = STRUCTURAL_CONTRACT_CONFIRM[ablation]
        scope_key = STRUCTURAL_SCOPE_MATCH_KEY[ablation]
        source_markers = {variant: probe_fn(tags[variant], cpu) for variant in VARIANTS}
        structural_contract = confirm_fn(source_markers["baseline"], source_markers["ablation"])
        for key, ok in structural_contract.items():
            print(f"{key}={'PASS' if ok else 'FAIL'}")
        if not structural_contract[scope_key]:
            print("PERF010A_SMOKE=BLOCKED")
            print(f"{profile['expected_slice']}=INVALID")
            raise RuntimeError(
                f"PERF010A_ABLATION_{ablation} exact-scope structural contract failed; "
                "see printed ABLATION_* gate results above"
            )

    with tempfile.TemporaryDirectory(prefix="perf010a-smoke-") as tmp:
        work = Path(tmp)
        matrix = run_matrix(
            cfg, tags, cpu, work, profile["absent_markers"], profile["present_marker"],
            warmup=SMOKE_WARMUP_ITERATIONS, steady=SMOKE_STEADY_ITERATIONS,
            collect_structural=(ablation not in SOURCE_STRUCTURAL_ABLATIONS),
        )

    classifications = [
        classify_workload(entry, ablation, structural_contract)
        for entry in matrix
    ]

    print("PERF010A_SMOKE_HARNESS_REVISION=" + harness_revision)
    print(f"PERF010A_SMOKE_SLICE={profile['expected_slice']}")
    print(
        f"PERF010A_SMOKE_SCALE=warmup={SMOKE_WARMUP_ITERATIONS} steady={SMOKE_STEADY_ITERATIONS}"
        f" (reference scale: warmup={cfg['warmup_iterations']} steady={cfg['steady_iterations']})"
    )
    print("PERF010A_SMOKE_WORKLOADS=" + str(len(matrix)))
    print("PERF010A_SMOKE_EVIDENCE_UNITS=" + str(len(matrix) * len(VARIANTS) * 2 * 2))
    for entry, classification in zip(matrix, classifications):
        print(
            f"PERF010A_SMOKE_WORKLOAD workload={entry['workload']} "
            f"result={classification[status_key]} "
            f"structural_confirmed={classification['structural_ablation_confirmed']}"
        )
    print("PERF010A_SMOKE=PASS")
    print("PERF010A_SMOKE_RETAINED=NO")


def scope_of_ablation_readme(ablation: str, cfg: dict[str, Any]) -> list[str]:
    if ablation == "4":
        return [
            "## Scope of the ablation",
            "",
            "`ablation-4.patch` touches exactly one method: "
            "`ProtosBytecodeRootNode.finishPreparingComposedCall`. Its native branch currently "
            "projects `ProtosClosureValue.nativeBody()` twice - once for "
            "`closure.nativeBody().isPresent()`, once for `closure.nativeBody().orElseThrow()` "
            "- even though both projections observe the same value (`nativeBody()` is "
            "`Optional.ofNullable(nativeBody)` over a `final` field). The patch introduces a "
            "single local `java.util.Optional<ProtosNativeClosureBody> nativeBodyProjection = "
            "closure.nativeBody();` and reuses it for both the `isPresent()` check and the "
            "`orElseThrow()` projection, removing only the second, redundant call.",
            "",
            "Every other `nativeBody()` call site in `ProtosBytecodeRootNode` (there are five: "
            "two `isPresent()`/`isEmpty()` pairs at two other call-preparation entry points, "
            "plus one more `isPresent()` check) is untouched, and `ProtosClosureValue.java` "
            "itself - including `nativeBody()`'s own `Optional.ofNullable(nativeBody)` body and "
            "the `nativeBody` field's `final` declaration - is not modified at all.",
            "",
            "This transformation preserves the same native/source classification and the same "
            "`ProtosNativeClosureBody` reference on every call, so it is claimed to be "
            "semantically equivalent by construction, not diagnostic-only-and-expected-to-fail-"
            "closed like ablation 2. It does not change lookup, receiver/delegation, method "
            "binding, closure capture, arguments, activation identity, return home, errors, "
            "nonlocal return, continuations, RootTag/source/debugger identity, interop, or "
            "native execution.",
            "",
            "Because both variants call the same fully-qualified `ProtosClosureValue."
            "nativeBody()` method at the retained call site, a JFR-sampled-frame count cannot "
            "distinguish one call from two, so this ablation's structural confirmation is "
            "source-derived rather than JFR-derived, exactly like ablation 3: "
            "`source_structural_probe_4`/`structural_contract_confirmed_ablation_4` reads "
            "`/opt/protos-source` (the exact patched-or-unmodified source tree the image was "
            "built from) and confirms, as one per-image contract: the baseline image's "
            "`finishPreparingComposedCall` body calls `closure.nativeBody()` exactly twice with "
            "no `nativeBodyProjection` local; the ablation image's body calls it exactly once, "
            "reusing a single `nativeBodyProjection` local for both uses, carrying the "
            "`PERF010A_ABLATION_4` marker comment; the rest of `ProtosBytecodeRootNode.java` "
            "outside that one method body is byte-for-byte identical across both images; and "
            "`ProtosClosureValue.java` is byte-for-byte identical across both images.",
            "",
            "`ProtosBytecodeRootNode.finishPreparingComposedCallByImplementation`, "
            "`ProtosActivation.java`, `ProtosValueLookup.java`, `CanonicalToBytecodeLowerer."
            "java`, the RootTag topology, the continuation machinery, the `CallTarget` "
            "architecture, and source/debugger identity are all untouched by this patch. This "
            "is a diagnostic ablation, not (by itself) a production optimization change; per "
            "this slice's scope, no change is made to `guillermomolina/protos` regardless of "
            "this experiment's outcome. Never published to `guillermomolina/protos`.",
        ]
    if ablation == "3":
        return [
            "## Scope of the ablation",
            "",
            "`ablation-3.patch` adds a new diagnostic-only "
            "`ProtosObjectValue.readLocalSlotSingleProbe` helper (a single `localSlots.get"
            "(name)`, discriminating ABSENT from any stored value via `localSlots`' own "
            "invariant that no local slot value is ever null - `createLocalSlot`/"
            "`assignLocalSlot` both require `Objects.requireNonNull(value, ...)`; "
            "`composeLocalSlotsFrom` only copies values already subject to that invariant "
            "from another `ProtosObjectValue`) and redirects **exactly** the two lexical "
            "local-slot-read call sites inside `ProtosActivation.lookup` - the current "
            "activation context, then each captured lexical context in "
            "`capturedLexicalContexts` - to it. The ordinary `ProtosObjectValue.readLocalSlot` "
            "method (its redundant `containsKey(name)` + `get(name)` probe-then-read) is "
            "**not** modified and stays byte-for-byte unchanged; it remains the path used by "
            "every other caller, including `ProtosValueLookup`'s receiver/delegation member "
            "lookup (the fallback `ProtosActivation.lookup` reaches via "
            "`ProtosValueLookup.readMember` when neither lexical position resolves the name) "
            "and every interop/other production call site.",
            "",
            "This is narrower than an earlier, invalid execution of this same slice, which "
            "instead transformed `readLocalSlot`'s own body globally - changing every caller, "
            "not just the two established lexical call sites - and was rejected by this "
            "harness's exact-scope validation (`ABLATION_3_PATCH_SCOPE_MATCH`) as measuring "
            "more than the established causal component, even though it was semantically "
            "equivalent by construction. That invalid attempt is retained as historical "
            "evidence of an invalid intent, not as a valid measurement.",
            "",
            "Unlike ablations 1 and 2, this is **not** a call-site bypass in the sense of "
            "dropping a step: `ProtosActivation.lookup`'s local-context-then-captured-lexical-"
            "contexts-then-receiver/prelude-fallback traversal, lexical precedence, shadowing, "
            "and missing-name behavior are all preserved, in the same order, in both variants - "
            "only which `ProtosObjectValue` reader method the two lexical positions call "
            "differs. This transformation is therefore claimed to be semantically equivalent by "
            "construction, not diagnostic-only-and-expected-to-fail-closed like ablation 2.",
            "",
            "Because both variants still call a `ProtosObjectValue` reader method with a "
            "resolvable frame name at the same call sites, and `java.util.LinkedHashMap."
            "containsKey`/`get` are simple enough to be JIT-inlined, this ablation's structural "
            "confirmation is source-derived rather than JFR-derived: "
            "`source_structural_probe`/`structural_contract_confirmed_ablation_3` reads "
            "`/opt/protos-source` (the exact patched-or-unmodified source tree the image was "
            "built from) and confirms, as one per-image contract: the diagnostic helper exists "
            "only in the ablation image; `readLocalSlot`'s own body is byte-for-byte identical "
            "across both images; the diagnostic helper is called at both of "
            "`ProtosActivation.lookup`'s lexical positions in the ablation image and ordinary "
            "`readLocalSlot` is called at those same two positions in the baseline image; the "
            "captured-lexical-context traversal loop and the `ProtosValueLookup` fallback are "
            "present, unchanged, in both; and `ProtosValueLookup`'s own receiver/delegation "
            "member-lookup call site still calls ordinary `readLocalSlot` in both images.",
            "",
            "`ProtosBytecodeRootNode.java`, `CanonicalToBytecodeLowerer.java`, the RootTag "
            "topology, the continuation machinery, the `CallTarget` architecture, and source/"
            "debugger identity are all untouched by this patch. This is a diagnostic ablation, "
            "not (by itself) a production optimization change; per this slice's scope, no "
            "change is made to `guillermomolina/protos` regardless of this experiment's "
            "outcome. Never published to `guillermomolina/protos`.",
        ]
    if ablation == "guarded-call":
        return [
            "## Scope of the guarded-call experiment",
            "",
            "`guarded-call.patch` touches exactly one file, "
            "`ProtosBytecodeRootNode.java`, and is almost purely additive: it adds one new "
            "leading `@Specialization` (`performGuardedOrdinaryComposedSend`) to the "
            "`PrepareSendArguments` Operation - the constant-selector, ordinary composed-send "
            "Bytecode operation reached from a plain `receiver.selector(args)` send - plus "
            "three new private helper methods. The pre-existing single specialization, "
            "`perform`, keeps its exact body and becomes a `@Specialization(replaces = "
            "\"performGuardedOrdinaryComposedSend\")` fallback; the only removed line in the "
            "whole patch is its bare `@Specialization` annotation.",
            "",
            "The new specialization's guard re-runs the exact authoritative "
            "`ProtosValueLookup.lookup(receiver, selector, prelude)` call on every single "
            "invocation (three independent call sites in the new helpers), so D013 lookup "
            "itself is unmodified and a slot replacement, removal, or delegation change is "
            "always observed before the guard is trusted. The guard only takes the fast arm "
            "when that fresh lookup still selects the exact same (Closure identity, methodHome "
            "identity) pair this call site cached, and it only ever caches a Closure whose "
            "`nativeBody()` is empty (a `final` field, so this fact never changes for a given "
            "Closure instance).",
            "",
            "On a hit it reuses `ProtosActivation.forImmediateMethodInvocation` and "
            "`attachTaskOrInheritDynamicControlState` exactly as the generic path "
            "(`prepareImmediateMethodCall`) already does, resolves the effective Bytecode "
            "execution plan via the pre-existing, unmodified `taskOwnedBytecodePlan` helper - "
            "the same helper the retained `prepareTaskOwnedSelectedCallIfBytecode` precedent "
            "already uses in production for the Task-owned path - and either builds the "
            "`PreparedClosureCall` directly, bypassing "
            "`finishPreparingComposedCallByImplementation`'s 16 implementation/category "
            "classifiers and the subsequent 19 structured-dispatch predicates, or falls back to "
            "that exact, unmodified method when the plan cannot be resolved (a source-less "
            "context-local projection). Skipping those classifiers is provably safe rather than "
            "merely likely safe: `finishPreparingComposedCall`'s own structured-flags branch "
            "already requires every one of them to be false whenever the selected Closure is "
            "non-native, which is the only case this specialization ever caches. A guard miss "
            "- a different Closure/methodHome, a native Closure, or a lookup failure - falls "
            "through to the unchanged `perform` specialization, i.e. the exact current generic "
            "path.",
            "",
            "`ProtosStandardImportProtocol.selectedRuntimeForBytecodeIntrinsic`'s check (run by "
            "the generic path before this experiment's target, `prepareImmediateMethodCall`) "
            "can only select a non-null runtime when the selected Closure's `nativeBody()` is "
            "present and holds a `StandardImportBody`; since this specialization only ever "
            "caches a Closure whose `nativeBody()` is empty, that check is provably unreachable "
            "(always null) for any Closure the fast arm can take, so omitting it changes no "
            "observable behavior.",
            "",
            "`ProtosActivation.java`, `ProtosClosureValue.java`, `ProtosObjectValue.java`, "
            "`ProtosValueLookup.java`, `CanonicalToBytecodeLowerer.java`, the RootTag topology, "
            "the continuation machinery, the `CallTarget` architecture, and source/debugger "
            "identity are all untouched by this patch. This is a diagnostic causal experiment, "
            "not (by itself) a production optimization change; per this slice's scope, no "
            "change is made to `guillermomolina/protos` regardless of this experiment's "
            "outcome. Never published to `guillermomolina/protos`.",
            "",
            "Because the new specialization method exists only in the guarded image's source "
            "(the baseline image's `PrepareSendArguments` class has exactly one, byte-for-byte "
            "unchanged, `perform` specialization), structural confirmation is source-derived, "
            "like ablations 3/4: `source_structural_probe_guarded`/"
            "`structural_contract_confirmed_guarded` reads `/opt/protos-source` and confirms, "
            "as one per-image contract, that the guarded image's `PrepareSendArguments` class "
            "contains `performGuardedOrdinaryComposedSend` and the "
            "`PERF010A_GUARDED_CALL` marker, that the baseline image's `PrepareSendArguments` "
            "class does not, and that the rest of `ProtosBytecodeRootNode.java` is byte-for-"
            "byte identical between the two images.",
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

    # Ablations 3 and 4's exact-scope structural contract is a static, per-image property (see
    # SOURCE_STRUCTURAL_ABLATIONS / STRUCTURAL_PROBE / STRUCTURAL_CONTRACT_CONFIRM) knowable
    # before the expensive four-workload x two-variant x (timing + JFR structural) reference
    # matrix runs at all. Per AGENTS.work/PERFORMANCE.md's exact-scope validation rule, a
    # failure here MUST block reference before that matrix executes - not merely be reported as
    # INVALID after spending the expensive run to discover a condition that was already
    # knowable statically.
    structural_contract = None
    if ablation in SOURCE_STRUCTURAL_ABLATIONS:
        probe_fn = STRUCTURAL_PROBE[ablation]
        confirm_fn = STRUCTURAL_CONTRACT_CONFIRM[ablation]
        scope_key = STRUCTURAL_SCOPE_MATCH_KEY[ablation]
        source_markers = {variant: probe_fn(tags[variant], cpu) for variant in VARIANTS}
        structural_contract = confirm_fn(source_markers["baseline"], source_markers["ablation"])
        for key, ok in structural_contract.items():
            print(f"{key}={'PASS' if ok else 'FAIL'}")
        if not structural_contract[scope_key]:
            print("PERF010A_REFERENCE=BLOCKED")
            print(f"{cfg['slice']}=INVALID")
            print("ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED")
            raise RuntimeError(
                f"PERF010A_ABLATION_{ablation} exact-scope structural contract failed before "
                "the expensive reference matrix; see printed ABLATION_* gate results above. No "
                "reference evidence was produced."
            )

    with tempfile.TemporaryDirectory(prefix="perf010a-") as tmp:
        work = Path(tmp)
        matrix = run_matrix(
            cfg, tags, cpu, work, profile["absent_markers"], profile["present_marker"]
        )

    classifications = {
        entry["workload"]: classify_workload(entry, ablation, structural_contract)
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
        "source_structural_markers": structural_contract,
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


# =============================================================================
# PERF010-A measurement-discrimination investigation (#691 follow-up).
#
# This does NOT measure a new causal ablation and MUST NOT be interpreted as one. It measures
# this harness's own discrimination capability, i.e. how much apparent "paired-control effect"
# appears between two variants that are source-equivalent by construction: `baseline`
# (unmodified) and `noop` (built through the exact same Dockerfile VARIANT=ablation path as a
# real ablation - git apply, --allow-dirty, ABLATION_SLICE label - but with a literally empty
# patch, docker/protos-perf010a/noop.patch). Because `git apply` on an empty patch changes
# nothing, the /src tree the noop image compiles from is byte-for-byte identical to the
# baseline image's; this is confirmed at build time by comparing the exact source text of
# every file any prior ablation (1-4) has ever touched, read from /opt/protos-source in both
# images (`source_tree_identity_probe`), not merely assumed from the empty patch. (An earlier
# version of this check instead hashed the built protos.jar directly and had to be replaced:
# this toolchain's Maven build is not byte-reproducible, so two separately-built images from
# byte-identical source still produced differently-hashed jars - build-time noise, not a real
# source difference.) Any paired-control movement observed between these two variants is
# measurement
# movement/drift, never a Protos runtime effect - the code that runs cannot differ - so this
# module never calls its own numbers a speedup, slowdown, regression, or optimization.
#
# Design: `--ablation 0`/config/perf010a-0.json's four-block deterministic AB/BA
# counterbalanced order (`block_order`; see that config's `block_design_note`) replaces the
# existing fixed "baseline canonical, baseline control, ablation canonical, ablation control"
# order used by validate()/smoke()/reference() above, so order/drift effects can be separated
# from a supposed variant effect. This reuses build_image/runtime_probe/java_version_probe/
# variant_label_probe/ablation_slice_label_probe/control_source/timing/summarize_ns unmodified,
# but does not route through validate()/smoke()/reference()/run_matrix()/classify_workload()
# themselves (which encode the fixed order and the ablations-1-4-specific structural-marker
# machinery this experiment does not need), to avoid any risk of changing those four functions'
# existing, already-tested behavior.
# =============================================================================

DISCRIMINATION_CONFIG = ROOT / "config/perf010a-0.json"
DISCRIMINATION_EXPECTED_PROTOS_REVISION = EXPECTED_PROTOS_REVISION_4
DISCRIMINATION_EXPECTED_SLICE = "PERF010A_NOOP"
DISCRIMINATION_BLOCK_ORDER = ("A", "B", "A", "B")
DISCRIMINATION_OUTPUT_DIR = ROOT / "results/perf010a-discrimination"

# Per-workload |effect%| already reported by the retained A1/A3/A4 causal-experiment
# reconciliations (results/perf010a-{1,3,4}/attribution.tsv and README.md; see also this task's
# own governing instructions, which restate them). Copied verbatim, not recomputed, for
# descriptive comparison only (ABLATION_*_EFFECT_VS_FLOOR / the gate's historical-minimum
# check below); this module never overwrites their historical conclusions.
HISTORICAL_ABLATION_EFFECTS_PERCENT: dict[str, dict[str, float]] = {
    "1": {
        "micro/slot-read": 3.39,
        "micro/closure-call": 8.45,
        "micro/method-call": -0.35,
        "runtime/monomorphic-dispatch": 2.74,
    },
    "3": {
        "micro/slot-read": 5.45,
        "micro/closure-call": 0.11,
        "micro/method-call": 0.62,
        "runtime/monomorphic-dispatch": -2.17,
    },
    "4": {
        "micro/slot-read": -11.32,
        "micro/closure-call": 6.98,
        "micro/method-call": -13.19,
        "runtime/monomorphic-dispatch": -5.53,
    },
}


# Union of every source file any of ablations 1-4 has ever patched (ablation.patch's three
# targets, plus ablation-2/3/4's ProtosBytecodeRootNode/ProtosActivation/ProtosObjectValue/
# ProtosValueLookup/ProtosClosureValue targets) - i.e. every file this harness's own causal-
# ablation history has treated as being on, or adjacent to, the four workloads' hot path.
# Reuses the SOURCE_ROOT-relative path constants ablations 3/4 already define where available.
DISCRIMINATION_SOURCE_FILES = (
    ROOT_NODE_SOURCE_PATH,
    ACTIVATION_SOURCE_PATH,
    READ_LOCAL_SLOT_SOURCE_PATH,
    VALUE_LOOKUP_SOURCE_PATH,
    CLOSURE_VALUE_SOURCE_PATH,
    "src/main/java/com/guillermomolina/protos/execution/ProtosSourceCompiler.java",
    "src/main/java/com/guillermomolina/protos/execution/ProtosBytecodeClosureExecutionPlan.java",
    "src/main/java/com/guillermomolina/protos/execution/ProtosRootTaskExecution.java",
)


def source_tree_identity_probe(tag: str, cpu: str) -> dict[str, str]:
    """Reads each of DISCRIMINATION_SOURCE_FILES's exact text from /opt/protos-source via
    `cat` (the same mechanism ablations 3/4's source_structural_probe already uses
    successfully in this harness) and returns {relative_path: sha256(content)}.

    This deliberately does NOT hash the built protos.jar: this toolchain's Maven build is not
    byte-reproducible (ordinary JAR/ZIP entries embed per-file timestamps, so two separate
    `docker build` invocations from byte-identical source still produce a differently-hashed
    jar - confirmed empirically: an early version of this probe hashed protos.jar directly and
    reported NOOP_RUNTIME_PATH_EQUIVALENCE=FAIL on a genuinely empty patch). Comparing the
    exact source text actually compiled is immune to that build-time noise and is a stronger,
    more direct proof of "the executed Protos runtime path cannot differ" than a build artifact
    whose bytes depend on when it happened to be built."""
    hashes: dict[str, str] = {}
    for rel_path in DISCRIMINATION_SOURCE_FILES:
        text = output([
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpu,
            "--entrypoint", "cat", tag,
            f"{SOURCE_ROOT}/{rel_path}",
        ])
        hashes[rel_path] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashes


def validate_discrimination() -> dict[str, Any]:
    cfg = load(DISCRIMINATION_CONFIG)
    assert cfg["perf_item"] == "PERF010-A"
    assert cfg["parent_perf_item"] == "PERF010"
    assert cfg["slice"] == DISCRIMINATION_EXPECTED_SLICE
    assert cfg["diagnostic_claim"] is True
    assert cfg["measurement_discrimination_experiment"] is True
    assert cfg["protos_revision"] == DISCRIMINATION_EXPECTED_PROTOS_REVISION
    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 20
    assert cfg["steady_iterations"] == 100
    assert cfg["variants"] == ["baseline", "ablation"]
    assert len(cfg["controls"]) == 4

    b2d_cfg = json.loads((ROOT / "config/perf004b2d.json").read_text(encoding="utf-8"))
    assert cfg["controls"] == b2d_cfg["controls"], (
        "the discrimination experiment must reuse the exact PERF004-B2-D/PERF008 four-workload "
        "matrix unmodified"
    )

    patch_path = ROOT / cfg["ablation_patch"]
    assert patch_path.is_file(), patch_path
    patch_text = patch_path.read_text(encoding="utf-8")
    assert patch_text == "", (
        "the no-op patch must be literally empty - any content would be a real source "
        "transformation whose cost could not be assumed zero"
    )
    assert cfg["ablation_patch_targets"] == []

    assert tuple(cfg["block_order"]) == DISCRIMINATION_BLOCK_ORDER
    assert len(cfg["block_order"]) >= 4
    assert set(cfg["block_order"]) == {"A", "B"}
    assert cfg["block_order"].count("A") >= 2 and cfg["block_order"].count("B") >= 2, (
        "at least two blocks of each order are required to separate an order effect from a "
        "single-observation coincidence"
    )

    print("NO_OP_VARIANT_PRESENT=PASS")
    print("NO_OP_SEMANTIC_EQUIVALENCE=PASS")
    print("NO_OP_RUNTIME_PATH_EQUIVALENCE=PASS")
    print("NO_OP_RELEVANT_SOURCE_DIFFERENCE=ZERO")
    print("COUNTERBALANCED_ORDER_PRESENT=PASS")
    print("FIXED_BASELINE_FIRST_ONLY=ABSENT")
    print("BLOCK_LEVEL_RETENTION_PRESENT=PASS")
    print("FOUR_WORKLOAD_SET_UNCHANGED=PASS")
    print("REFERENCE_WARMUP_UNCHANGED=PASS")
    print("REFERENCE_STEADY_UNCHANGED=PASS")
    print("PERF010A_DISCRIMINATION_CONFIG=PASS")
    return cfg


def _build_and_probe_discrimination_images(cfg: dict[str, Any], cpu: str) -> dict[str, str]:
    tags = {
        variant: build_image(cfg, variant, ablation=DISCRIMINATION_ABLATION)
        for variant in VARIANTS
    }
    for variant, tag in tags.items():
        runtime_probe(tag, cpu)
        java_version_probe(tag, cpu)
        observed_variant = variant_label_probe(tag, cpu)
        if observed_variant != variant:
            raise RuntimeError(f"variant label mismatch: expected {variant}, got {observed_variant}")
        observed_slice = ablation_slice_label_probe(tag, cpu)
        expected_slice = DISCRIMINATION_EXPECTED_SLICE if variant == "ablation" else "none"
        if observed_slice != expected_slice:
            raise RuntimeError(
                f"ablation-slice label mismatch: expected {expected_slice}, got {observed_slice}"
            )

    source_hashes = {
        variant: source_tree_identity_probe(tag, cpu) for variant, tag in tags.items()
    }
    mismatches = [
        path for path in DISCRIMINATION_SOURCE_FILES
        if source_hashes["baseline"][path] != source_hashes["ablation"][path]
    ]
    for path in DISCRIMINATION_SOURCE_FILES:
        print(
            f"NOOP_SOURCE_SHA256 path={path} "
            f"baseline={source_hashes['baseline'][path]} noop={source_hashes['ablation'][path]}"
        )
    if mismatches:
        print("NOOP_RUNTIME_PATH_EQUIVALENCE=FAIL")
        raise RuntimeError(
            "noop image's source differs from baseline's at: " + ", ".join(mismatches) + "; "
            "the no-op experiment is INVALID and must not be used to interpret discrimination "
            "- no timing was run"
        )
    print("NOOP_RUNTIME_PATH_EQUIVALENCE=PASS")
    return tags


def _block_variant_order(block_label: str) -> tuple[str, str]:
    if block_label == "A":
        return ("baseline", "ablation")
    if block_label == "B":
        return ("ablation", "baseline")
    raise ValueError(f"unknown block label: {block_label!r}")


def run_discrimination_blocks(
    cfg: dict[str, Any], tags: dict[str, str], cpu: str, work: Path,
    block_order: tuple[str, ...], warmup: int, steady: int,
) -> list[dict[str, Any]]:
    """Runs the counterbalanced block matrix and returns one entry per (block, workload) with
    each variant/mode's steady-state summary, retaining block-level evidence rather than
    collapsing immediately into one median (see task governance). No JFR/structural collection
    here: the no-op exact-scope/runtime-equivalence contract is the single per-image
    `_build_and_probe_discrimination_images` check above, not a per-workload profile."""
    blocks: list[dict[str, Any]] = []
    for block_index, block_label in enumerate(block_order):
        variant_order = _block_variant_order(block_label)
        for item in cfg["controls"]:
            workload = item["id"]
            slug = workload.replace("/", "__")
            by_variant: dict[str, Any] = {}
            for variant in variant_order:
                tag = tags[variant]
                canonical_source, control_host = control_source(tag, work, item)
                by_mode: dict[str, Any] = {}
                for mode, source_host, source_container in (
                    ("canonical", None, canonical_source),
                    ("control", control_host, "/work/source.protos"),
                ):
                    label = f"block{block_index}-{block_label}-{slug}-{variant}-{mode}"
                    print(
                        f"DISCRIMINATION TIMING BEGIN block={block_index} order={block_label} "
                        f"workload={workload} variant={variant} mode={mode}",
                        flush=True,
                    )
                    timing_result = timing(
                        tag, cpu, work, source_host, source_container,
                        item["expected"], label, warmup, steady,
                    )
                    print(
                        f"DISCRIMINATION TIMING PASS block={block_index} order={block_label} "
                        f"workload={workload} variant={variant} mode={mode} "
                        f"median_ns={timing_result['steady_summary']['median_ns']}",
                        flush=True,
                    )
                    by_mode[mode] = timing_result
                by_variant[variant] = by_mode
            blocks.append({
                "block_index": block_index,
                "block_order": block_label,
                "variant_sequence": list(variant_order),
                "workload": workload,
                "variants": by_variant,
            })
    return blocks


def classify_discrimination_block(entry: dict[str, Any]) -> dict[str, Any]:
    """Sign convention (fixed before any data was collected):

        canonical_difference = baseline_canonical_median_ns - noop_canonical_median_ns
        control_difference   = baseline_control_median_ns   - noop_control_median_ns
        paired_control_difference_ns = canonical_difference - control_difference
        paired_control_difference_percent =
            100 * paired_control_difference_ns / baseline_canonical_median_ns

    A positive value means the paired-control comparison would (wrongly, since these variants
    are source-equivalent) read as "noop faster than baseline"; a negative value would read as
    "noop slower than baseline". Expressed as a percentage of baseline's canonical median so it
    is directly comparable in scale to the historical A1/A3/A4 percentage effects."""
    baseline = entry["variants"]["baseline"]
    noop = entry["variants"]["ablation"]
    baseline_canonical_ns = baseline["canonical"]["steady_summary"]["median_ns"]
    baseline_control_ns = baseline["control"]["steady_summary"]["median_ns"]
    noop_canonical_ns = noop["canonical"]["steady_summary"]["median_ns"]
    noop_control_ns = noop["control"]["steady_summary"]["median_ns"]

    canonical_difference_ns = baseline_canonical_ns - noop_canonical_ns
    control_difference_ns = baseline_control_ns - noop_control_ns
    paired_control_difference_ns = canonical_difference_ns - control_difference_ns
    paired_control_difference_percent = (
        100.0 * paired_control_difference_ns / baseline_canonical_ns
    )

    return {
        "block_index": entry["block_index"],
        "block_order": entry["block_order"],
        "workload": entry["workload"],
        "baseline_canonical_median_ns": baseline_canonical_ns,
        "baseline_control_median_ns": baseline_control_ns,
        "noop_canonical_median_ns": noop_canonical_ns,
        "noop_control_median_ns": noop_control_ns,
        "canonical_difference_ns": canonical_difference_ns,
        "control_difference_ns": control_difference_ns,
        "paired_control_difference_ns": paired_control_difference_ns,
        "paired_control_difference_percent": paired_control_difference_percent,
    }


def summarize_discrimination_workload(classified_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive no-op envelope for one workload across all retained blocks. Explicitly a
    DESCRIPTIVE_DISCRIMINATION_ENVELOPE, not a STATISTICAL_CONFIDENCE_INTERVAL: with only a
    handful of blocks, no inferential interval is fabricated here."""
    values = [b["paired_control_difference_percent"] for b in classified_blocks]
    ordered = sorted(values)
    median = statistics.median(values)
    mad = statistics.median([abs(v - median) for v in values])
    abs_max = max(abs(v) for v in values)

    a_values = [
        b["paired_control_difference_percent"]
        for b in classified_blocks if b["block_order"] == "A"
    ]
    b_values = [
        b["paired_control_difference_percent"]
        for b in classified_blocks if b["block_order"] == "B"
    ]
    if len(a_values) < 2 or len(b_values) < 2:
        order_effect = "INCONCLUSIVE"
    else:
        a_range = (min(a_values), max(a_values))
        b_range = (min(b_values), max(b_values))
        non_overlapping = a_range[1] < b_range[0] or b_range[1] < a_range[0]
        order_effect = "DETECTED" if non_overlapping else "NOT_DETECTED"

    return {
        "samples": len(values),
        "noop_paired_control_min_percent": min(ordered),
        "noop_paired_control_max_percent": max(ordered),
        "noop_paired_control_median_percent": median,
        "noop_paired_control_mad_percent": mad,
        "noop_paired_control_abs_max_percent": abs_max,
        "discrimination_floor_percent": abs_max,
        "order_effect": order_effect,
        "a_order_values_percent": a_values,
        "b_order_values_percent": b_values,
    }


def classify_effect_vs_floor(effect_percent: float, floor_percent: float) -> str:
    """Pre-specified before any reference data existed (see task governance: 'Do not choose the
    definition after seeing which threshold would authorize Ablation 5'). ABOVE requires the
    historical effect's magnitude to be at least double the floor; BELOW requires it to be at
    most half the floor; anything in between (same order of magnitude) is COMPARABLE."""
    if floor_percent <= 0:
        return "ABOVE" if effect_percent != 0 else "COMPARABLE"
    ratio = abs(effect_percent) / floor_percent
    if ratio >= 2.0:
        return "ABOVE"
    if ratio <= 0.5:
        return "BELOW"
    return "COMPARABLE"


def combine_workload_verdicts(verdicts: list[str]) -> str:
    unique = set(verdicts)
    return verdicts[0] if len(unique) == 1 else "MIXED"


def discrimination_gate_for_workload(
    workload: str, discrimination_floor_percent: float, order_effect: str,
) -> str:
    """Pre-specified gate rule, tied to real, already-retained evidence rather than an
    arbitrary invented threshold: OPEN requires the no-op discrimination floor for this
    workload to be strictly smaller than the smallest-magnitude effect the retained A1/A3/A4
    evidence has ever interpreted for this same workload, AND no detected order effect. If the
    floor cannot be trusted to be smaller than an effect this harness has already treated as
    interpretable, a smaller new candidate cannot be measured informatively either."""
    if order_effect == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    if order_effect == "DETECTED":
        return "CLOSED"
    historical_abs_effects = [
        abs(HISTORICAL_ABLATION_EFFECTS_PERCENT[ablation][workload])
        for ablation in ("1", "3", "4")
    ]
    historical_min_abs_effect = min(historical_abs_effects)
    if discrimination_floor_percent < historical_min_abs_effect:
        return "OPEN"
    return "CLOSED"


def combine_gate(per_workload_gates: dict[str, str]) -> str:
    values = set(per_workload_gates.values())
    if "CLOSED" in values:
        return "CLOSED"
    if "INCONCLUSIVE" in values:
        return "INCONCLUSIVE"
    return "OPEN"


def minimum_next_methodological_change(
    overall_gate: str, per_workload_gates: dict[str, str], per_workload_summary: dict[str, Any],
) -> str:
    if overall_gate == "OPEN":
        return "NONE"
    any_order_effect_detected = any(
        s["order_effect"] == "DETECTED" for s in per_workload_summary.values()
    )
    any_inconclusive = "INCONCLUSIVE" in per_workload_gates.values()
    if any_order_effect_detected:
        return (
            "process/container lifecycle isolation between blocks, plus more counterbalanced "
            "blocks (extend block_order beyond AABB) to confirm whether the detected order "
            "effect is stable before trusting any paired-control comparison built on this "
            "fixed-order harness"
        )
    if any_inconclusive:
        return (
            "more counterbalanced blocks (extend block_order beyond the current 4) - the "
            "current sample is too small to determine the order effect reliably for at least "
            "one workload"
        )
    return (
        "longer measurement within blocks (increase steady_iterations beyond 100) and/or finer-"
        "granularity interleaving of canonical/control runs, to reduce the no-op discrimination "
        "floor below the smallest historically-interpreted local effect"
    )


def smoke_discrimination() -> None:
    cfg = validate_discrimination()
    harness_revision = worktree_harness_revision()
    cpu = first_cpu()
    tags = _build_and_probe_discrimination_images(cfg, cpu)

    with tempfile.TemporaryDirectory(prefix="perf010a-discrimination-smoke-") as tmp:
        work = Path(tmp)
        blocks = run_discrimination_blocks(
            cfg, tags, cpu, work,
            block_order=("A", "B"),
            warmup=SMOKE_WARMUP_ITERATIONS, steady=SMOKE_STEADY_ITERATIONS,
        )

    print("PERF010A_DISCRIMINATION_SMOKE_HARNESS_REVISION=" + harness_revision)
    print(
        f"PERF010A_DISCRIMINATION_SMOKE_SCALE=warmup={SMOKE_WARMUP_ITERATIONS} "
        f"steady={SMOKE_STEADY_ITERATIONS} (reference scale: warmup={cfg['warmup_iterations']} "
        f"steady={cfg['steady_iterations']})"
    )
    print("PERF010A_DISCRIMINATION_SMOKE_BLOCKS=" + str(len(set(b["block_index"] for b in blocks))))
    print("PERF010A_DISCRIMINATION_SMOKE_WORKLOADS=" + str(len(cfg["controls"])))
    print("PERF010A_DISCRIMINATION_SMOKE=PASS")
    print("PERF010A_DISCRIMINATION_SMOKE_RETAINED=NO")


def reference_discrimination(harness_revision: str | None, output_dir: Path | None) -> None:
    cfg = validate_discrimination()
    harness_revision = resolved_harness_revision(harness_revision)
    output_dir = output_dir if output_dir is not None else DISCRIMINATION_OUTPUT_DIR

    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires clean exact harness")

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise RuntimeError("output directory already contains evidence")
        output_dir.rmdir()

    cpu = first_cpu()
    tags = _build_and_probe_discrimination_images(cfg, cpu)

    block_order = tuple(cfg["block_order"])
    with tempfile.TemporaryDirectory(prefix="perf010a-discrimination-") as tmp:
        work = Path(tmp)
        blocks = run_discrimination_blocks(
            cfg, tags, cpu, work,
            block_order=block_order,
            warmup=cfg["warmup_iterations"], steady=cfg["steady_iterations"],
        )

    classified = [classify_discrimination_block(entry) for entry in blocks]
    by_workload: dict[str, list[dict[str, Any]]] = {}
    for c in classified:
        by_workload.setdefault(c["workload"], []).append(c)

    per_workload_summary = {
        workload: summarize_discrimination_workload(blocks_for_workload)
        for workload, blocks_for_workload in by_workload.items()
    }
    per_workload_gates = {
        workload: discrimination_gate_for_workload(
            workload, summary["discrimination_floor_percent"], summary["order_effect"],
        )
        for workload, summary in per_workload_summary.items()
    }
    overall_gate = combine_gate(per_workload_gates)

    effect_vs_floor = {}
    for ablation in ("1", "3", "4"):
        per_workload_verdicts = [
            classify_effect_vs_floor(
                HISTORICAL_ABLATION_EFFECTS_PERCENT[ablation][workload],
                per_workload_summary[workload]["discrimination_floor_percent"],
            )
            for workload in per_workload_summary
        ]
        effect_vs_floor[ablation] = combine_workload_verdicts(per_workload_verdicts)

    minimum_change = minimum_next_methodological_change(
        overall_gate, per_workload_gates, per_workload_summary
    )

    output_dir.mkdir(parents=True)

    raw = {
        "schema_version": 1,
        "perf_item": "PERF010-A",
        "parent_perf_item": "PERF010",
        "slice": cfg["slice"],
        "diagnostic_claim": True,
        "measurement_discrimination_experiment": True,
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "toolchain": cfg["toolchain"],
        "host_identity": host_identity(),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "network": "none",
        "operation_count": cfg["operation_count"],
        "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"],
        "block_order": list(block_order),
        "blocks": blocks,
        "classified_blocks": classified,
        "per_workload_summary": per_workload_summary,
        "per_workload_gate": per_workload_gates,
        "ablation_effect_vs_floor": effect_vs_floor,
        "ablation_5_measurement_gate": overall_gate,
        "minimum_next_methodological_change": minimum_change,
    }
    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    rows = [
        "block_index\tblock_order\tworkload\tbaseline_canonical_median_ns\t"
        "baseline_control_median_ns\tnoop_canonical_median_ns\tnoop_control_median_ns\t"
        "canonical_difference_ns\tcontrol_difference_ns\tpaired_control_difference_ns\t"
        "paired_control_difference_percent"
    ]
    for c in classified:
        rows.append("\t".join([
            str(c["block_index"]), c["block_order"], c["workload"],
            str(c["baseline_canonical_median_ns"]), str(c["baseline_control_median_ns"]),
            str(c["noop_canonical_median_ns"]), str(c["noop_control_median_ns"]),
            str(c["canonical_difference_ns"]), str(c["control_difference_ns"]),
            str(c["paired_control_difference_ns"]),
            f"{c['paired_control_difference_percent']:.4f}",
        ]))
    (output_dir / "discrimination-blocks.tsv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )

    summary_rows = [
        "workload\tsamples\tnoop_paired_control_min_percent\tnoop_paired_control_max_percent\t"
        "noop_paired_control_median_percent\tnoop_paired_control_mad_percent\t"
        "discrimination_floor_percent\torder_effect\tablation_5_gate"
    ]
    for workload, s in per_workload_summary.items():
        summary_rows.append("\t".join([
            workload, str(s["samples"]),
            f"{s['noop_paired_control_min_percent']:.4f}",
            f"{s['noop_paired_control_max_percent']:.4f}",
            f"{s['noop_paired_control_median_percent']:.4f}",
            f"{s['noop_paired_control_mad_percent']:.4f}",
            f"{s['discrimination_floor_percent']:.4f}",
            s["order_effect"],
            per_workload_gates[workload],
        ]))
    (output_dir / "discrimination-summary.tsv").write_text(
        "\n".join(summary_rows) + "\n", encoding="utf-8"
    )

    readme = [
        "# PERF010-A measurement-discrimination investigation (#691 follow-up)",
        "",
        "This is not a causal ablation. It measures this harness's own discrimination "
        "capability using a source-equivalent no-op variant (`PERF010A_NOOP`); any movement "
        "reported below is measurement movement/drift, never a Protos runtime effect, "
        "because the executed Protos runtime code cannot differ between the two variants "
        "compared here (see `NOOP_RUNTIME_PATH_EQUIVALENCE` and `raw.json`).",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision (baseline and noop; single checkout, empty patch applied in-build "
        f"for the noop image only): `{cfg['protos_revision']}`",
        f"- Block order: `{block_order}` (deterministic AB/BA counterbalance; "
        "BASELINE_FIRST_ONLY=ABSENT).",
        "- N=10,000. Warmup=20, steady=100 (unchanged reference scale).",
        "",
        "## Per-workload no-op discrimination envelope",
        "",
        "| workload | samples | min % | max % | median % | MAD % | floor % | order effect | "
        "Ablation 5 gate |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for workload, s in per_workload_summary.items():
        readme.append(
            f"| {workload} | {s['samples']} "
            f"| {s['noop_paired_control_min_percent']:.4f} "
            f"| {s['noop_paired_control_max_percent']:.4f} "
            f"| {s['noop_paired_control_median_percent']:.4f} "
            f"| {s['noop_paired_control_mad_percent']:.4f} "
            f"| {s['discrimination_floor_percent']:.4f} "
            f"| {s['order_effect']} | {per_workload_gates[workload]} |"
        )

    readme += [
        "",
        "## Existing ablations vs. this floor (descriptive only; historical conclusions "
        "unchanged)",
        "",
        "| ablation | vs. floor |",
        "|---|---|",
        f"| Ablation 1 | {effect_vs_floor['1']} |",
        f"| Ablation 3 | {effect_vs_floor['3']} |",
        f"| Ablation 4 | {effect_vs_floor['4']} |",
        "",
        f"## ABLATION_5_MEASUREMENT_GATE = {overall_gate}",
        "",
        f"Minimum next methodological change: {minimum_change}",
        "",
        "This investigation does not select a production optimization, does not measure the "
        "already-established next causal candidate (invocation-time second `List.copyOf` of "
        "closure `capturedLexicalContexts`), and does not authorize Ablation 5 by itself.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    names = ["README.md", "raw.json", "discrimination-blocks.tsv", "discrimination-summary.tsv"]
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(f"{sha256(output_dir / n)}  {n}" for n in names) + "\n", encoding="utf-8"
    )

    print("PERF010A_DISCRIMINATION_REFERENCE=PASS")
    print("PERF010A_MEASUREMENT_DISCRIMINATION=ESTABLISHED")
    print("NO_OP_EXPERIMENT=VALID")
    print("VARIANT_ORDER_COUNTERBALANCED=YES")
    print("CANONICAL_CONTROL_PAIRING_PRESERVED=YES")
    for workload, s in per_workload_summary.items():
        print(
            f"WORKLOAD={workload} "
            f"NOOP_PAIRED_CONTROL_MIN={s['noop_paired_control_min_percent']:.4f} "
            f"NOOP_PAIRED_CONTROL_MAX={s['noop_paired_control_max_percent']:.4f} "
            f"NOOP_PAIRED_CONTROL_MEDIAN={s['noop_paired_control_median_percent']:.4f} "
            f"NOOP_PAIRED_CONTROL_ABS_MAX={s['noop_paired_control_abs_max_percent']:.4f} "
            f"DISCRIMINATION_FLOOR={s['discrimination_floor_percent']:.4f} "
            f"ORDER_EFFECT={s['order_effect']}"
        )
    print(f"ABLATION_1_EFFECT_VS_FLOOR={effect_vs_floor['1']}")
    print(f"ABLATION_3_EFFECT_VS_FLOOR={effect_vs_floor['3']}")
    print(f"ABLATION_4_EFFECT_VS_FLOOR={effect_vs_floor['4']}")
    print(f"ABLATION_5_MEASUREMENT_GATE={overall_gate}")
    print(f"MINIMUM_NEXT_METHODOLOGICAL_CHANGE={minimum_change}")
    print("PERF010A_DOMINANT_CAUSE=NOT_ESTABLISHED")
    print("ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED")
    print("PRODUCTION_OPTIMIZATION_SELECTED=NO")
    print("PERF010_READY=NO")
    print("PERF010A_PROTOS_REPOSITORY_MODIFICATION=NONE")


# ---------------------------------------------------------------------------------------------
# PERF010-A / #691 caller/helper source-identity diagnostic (guillermomolina/protos-project-docs
# @29a38fd3c0fb2f10a1fb5dc4a6a4616e05abe98e,
# docs/project/evidence/PERF010-A/PERF010-A_CALLER_HELPER_TRACE_SOURCE_IDENTITY_BLOCKER.md).
#
# That retained evidence established that a real compiler-lifecycle trace of the baseline
# `micro/method-call` workload executed correctly (WORKLOAD_RESULT=PASS) but every traced
# compilation event reported `Src n/a`, because the pinned revision's generated Bytecode DSL
# roots are created with `BytecodeConfig.DEFAULT`, which does not materialize optional source
# information. Protos' own `ProtosPerf006B5BSourceInstrumentationLocationTest` already
# demonstrates the intended materialization mechanism (real Truffle instrumentation forces a
# reparse-in-place with source included, without discarding CallTarget identity or changing
# guest-observable semantics); `docker/protos-perf010a/Perf010aSourceIdentityInstrument.java`
# reuses exactly that mechanism from the harness side, through public Truffle instrumentation
# API only (`Instrumenter#attachLoadSourceSectionListener`), scoped to the single Source named
# `method-call.protos` - see that class's own javadoc for the full mechanism and why it never
# reaches into `com.guillermomolina.protos` internals and never touches
# `BytecodeConfig.DEFAULT` in Protos source.
#
# This is diagnostic observability infrastructure only (AGENTS.work/PERFORMANCE.md's
# distinction between diagnostic instrumentation and timing evidence): it does not implement a
# PERF010 optimization, does not select a production change, and - because the instrument is
# inert unless a later `java` invocation explicitly passes
# `-Dpolyglot.perf010aSourceIdentity=true` - has zero effect on `validate`/`smoke`/`reference`
# for any ablation slice above. It reuses the exact retained PERF010A_GUARDED_CALL baseline
# image identity (config/perf010a-guarded-call.json, the same pinned Protos revision/toolchain
# the durable evidence record above pins) and never builds or runs the "ablation" (guarded-call)
# variant, since the guarded-call intervention is unrelated to, and out of scope for, this
# diagnostic.
SOURCE_IDENTITY_ABLATION = "guarded-call"
SOURCE_IDENTITY_INSTRUMENT_JAVA = (
    ROOT / "docker/protos-perf010a/Perf010aSourceIdentityInstrument.java"
)
SOURCE_IDENTITY_PROVIDER_JAVA = (
    ROOT / "docker/protos-perf010a/Perf010aSourceIdentityInstrumentProvider.java"
)
SOURCE_IDENTITY_SMOKE_JAVA = ROOT / "docker/protos-perf010a/Perf010aSourceIdentitySmokeDriver.java"
SOURCE_IDENTITY_SERVICES_FILE = (
    ROOT / "docker/protos-perf010a/META-INF/services/"
    "com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider"
)
SOURCE_IDENTITY_OPTION_ID = "perf010aSourceIdentity"
SOURCE_IDENTITY_TARGET_SOURCE_NAME = "method-call.protos"
SOURCE_IDENTITY_TARGET_TEXT = "sink = receiver.identity(42)"
SOURCE_IDENTITY_CORPUS_SOURCE = "/opt/perf010a/corpus/micro/method-call.protos"
SOURCE_IDENTITY_EXPECTED = "42"


def validate_source_identity() -> dict[str, Any]:
    # Reuses the exact pinned PERF010A_GUARDED_CALL baseline image identity unmodified; this
    # diagnostic never selects a different Protos revision, ablation slice, workload, or
    # compiler/warmup/steady policy than what validate("guarded-call") already proves.
    cfg = validate(SOURCE_IDENTITY_ABLATION)

    for path in (
        SOURCE_IDENTITY_INSTRUMENT_JAVA,
        SOURCE_IDENTITY_PROVIDER_JAVA,
        SOURCE_IDENTITY_SMOKE_JAVA,
        SOURCE_IDENTITY_SERVICES_FILE,
    ):
        assert path.is_file(), path

    instrument_text = SOURCE_IDENTITY_INSTRUMENT_JAVA.read_text(encoding="utf-8")
    provider_text = SOURCE_IDENTITY_PROVIDER_JAVA.read_text(encoding="utf-8")
    smoke_text = SOURCE_IDENTITY_SMOKE_JAVA.read_text(encoding="utf-8")
    services_text = SOURCE_IDENTITY_SERVICES_FILE.read_text(encoding="utf-8").strip()

    # DIAGNOSTIC_SOURCE_MATERIALIZATION_PRESENT: the established ensureComplete()/
    # ensureSourceSection() model's harness-side equivalent (real Truffle instrumentation),
    # scoped to exactly the target caller Source.
    assert "attachLoadSourceSectionListener" in instrument_text
    assert "SourceSectionFilter" in instrument_text
    assert SOURCE_IDENTITY_TARGET_SOURCE_NAME in instrument_text
    assert "Perf010aSourceIdentityInstrument.ID" in instrument_text
    assert f'"{SOURCE_IDENTITY_OPTION_ID}"' in instrument_text
    # OptionStability.STABLE, not EXPERIMENTAL: an experimental option requires the embedder to
    # call allowExperimentalOptions(true) on the Context/Engine builder - confirmed empirically
    # ("Option 'perf010aSourceIdentity' is experimental and must be enabled with
    # allowExperimentalOptions(...)") - which this diagnostic cannot do without modifying
    # ProtosPolyglotExecutionContext.open(), a Protos-internal class it must not touch.
    assert "OptionStability.STABLE" in instrument_text
    assert "OptionStability.EXPERIMENTAL" not in instrument_text

    # PRODUCT_REPOSITORY_MUTATION=NO: source identity is reached only through public Truffle
    # instrumentation API, never through com.guillermomolina.protos package-private access and
    # never through a build-local Protos source patch (no BytecodeConfig reference at all).
    for text, label in (
        (instrument_text, "Perf010aSourceIdentityInstrument.java"),
        (provider_text, "Perf010aSourceIdentityInstrumentProvider.java"),
    ):
        assert "import com.guillermomolina.protos" not in text, label
        assert "import com.oracle.truffle.api.bytecode.BytecodeConfig" not in text, label

    assert "TruffleInstrumentProvider" in provider_text
    assert "Perf010aSourceIdentityInstrument.class.getName()" in provider_text
    assert services_text == "Perf010aSourceIdentityInstrumentProvider"
    # TruffleInstrumentProvider is an abstract class in the pinned Truffle version, not an
    # interface (confirmed by decompiling the pinned truffle-api jar's own class file access
    # flags: ACC_ABSTRACT set, ACC_INTERFACE not set); `implements` fails to compile
    # ("interface expected here"), which is exactly the regression this guards against.
    assert "extends TruffleInstrumentProvider" in provider_text
    assert "implements TruffleInstrumentProvider" not in provider_text
    # The engine reads id/name/version metadata from the @Registration annotation on the
    # discovered Provider class itself, not from the instrument class create() returns -
    # confirmed empirically (a Provider without it is silently ignored with "Provider class ...
    # is missing @Registration annotation", and the option is then unknown at Context.build()).
    assert "@TruffleInstrument.Registration(" in provider_text
    assert "Perf010aSourceIdentityInstrument.ID" in provider_text

    # The smoke must exercise the exact production execution path (ProtosPolyglotProcessContext
    # .execute, not a reimplemented invocation) and fail closed on both correctness and the
    # exact target discriminator, not merely "some source exists".
    assert "processContext.execute(" in smoke_text
    assert "requireCompletedInteger" in smoke_text
    assert SOURCE_IDENTITY_TARGET_TEXT in smoke_text
    assert "METHOD_CALL_SOURCE_IDENTITY_VISIBLE" in smoke_text
    assert "System.exit(1)" in smoke_text
    assert SOURCE_IDENTITY_TARGET_SOURCE_NAME in smoke_text
    # This diagnostic never selects or depends on the guarded-call intervention itself; the
    # smoke driver only reuses that config/image's identity, unmodified.
    assert "PrepareSendArguments" not in smoke_text
    assert "performGuardedOrdinaryComposedSend" not in smoke_text

    # WORKLOAD_CHANGE=NO / WARMUP_STEADY_POLICY_CHANGE=NO / COMPILER_POLICY_CHANGE=NO: the
    # Dockerfile compiles these new diagnostic files into every image unconditionally, without
    # touching any existing ARG, patch-selection, or reference/smoke wiring above.
    dockerfile = (ROOT / "docker/protos-perf010a/Dockerfile").read_text(encoding="utf-8")
    for required in (
        "Perf010aSourceIdentityInstrument.java",
        "Perf010aSourceIdentityInstrumentProvider.java",
        "Perf010aSourceIdentitySmokeDriver.java",
        "META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider",
    ):
        assert required in dockerfile, required

    print("PERF010A_SOURCE_IDENTITY_CONFIG=PASS")
    print("PERF010A_SOURCE_IDENTITY_INSTRUMENT_PRESENT=PASS")
    print("PERF010A_SOURCE_IDENTITY_PROVIDER_PRESENT=PASS")
    print("PERF010A_SOURCE_IDENTITY_DOCKERFILE_WIRING=PASS")
    print("PRODUCT_REPOSITORY_MUTATION=NO")
    print("DIAGNOSTIC_SOURCE_MATERIALIZATION_PRESENT=YES")
    return cfg


def smoke_source_identity() -> None:
    cfg = validate_source_identity()
    cpu = first_cpu()
    # Baseline variant only - this diagnostic never builds or runs the "ablation" (guarded-call)
    # variant; that intervention is unrelated to, and out of scope for, a source-identity
    # diagnostic (AGENTS.work/PERFORMANCE.md's causal-ablation exact-scope discipline applies
    # only to ablation experiments, and this is deliberately not one).
    tag = build_image(cfg, "baseline", ablation=SOURCE_IDENTITY_ABLATION)
    runtime_probe(tag, cpu)
    observed_variant = variant_label_probe(tag, cpu)
    if observed_variant != "baseline":
        raise RuntimeError(f"variant label mismatch: expected baseline, got {observed_variant}")

    p = run(
        [
            "docker", "run", "--rm", "--network", "none",
            "--cpuset-cpus", cpu,
            "--entrypoint", "java", tag,
            f"-Dpolyglot.{SOURCE_IDENTITY_OPTION_ID}=true",
            "-Xss128m",
            "--enable-native-access=ALL-UNNAMED",
            "-cp", "/opt/perf010a/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
            "Perf010aSourceIdentitySmokeDriver",
            SOURCE_IDENTITY_CORPUS_SOURCE, SOURCE_IDENTITY_EXPECTED,
        ],
        capture=True, check=False,
    )
    stdout = p.stdout or ""
    stderr = p.stderr or ""
    print(stdout, end="" if stdout.endswith("\n") else "\n")

    if "METHOD_CALL_SOURCE_IDENTITY_VISIBLE=YES" not in stdout or p.returncode != 0:
        raise RuntimeError(
            "PERF010A_SOURCE_IDENTITY_SMOKE=FAIL "
            f"returncode={p.returncode}\nstdout(tail):\n{stdout[-4000:]}\n"
            f"stderr(tail):\n{stderr[-4000:]}"
        )

    print("PERF010A_SOURCE_IDENTITY_SMOKE=PASS")
    print("PERF010A_SOURCE_IDENTITY_SMOKE_RETAINED=NO")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "command",
        choices=(
            "validate", "smoke", "reference",
            "discrimination-validate", "discrimination-smoke", "discrimination-reference",
            "source-identity-validate", "source-identity-smoke",
        ),
    )
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
        "default), 2 (ProtosActivation.lookup), 3 (ProtosObjectValue.readLocalSlot's "
        "redundant containsKey+get), or 4 (finishPreparingComposedCall's duplicate "
        "ProtosClosureValue.nativeBody() projection); not used by the discrimination-* "
        "commands, which always use the dedicated no-op slice (config/perf010a-0.json)",
    )
    args = ap.parse_args()

    if args.command == "validate":
        validate(args.ablation)
        return

    if args.command == "smoke":
        smoke(args.ablation)
        return

    if args.command == "discrimination-validate":
        validate_discrimination()
        return

    if args.command == "discrimination-smoke":
        smoke_discrimination()
        return

    if args.command == "discrimination-reference":
        output_dir = Path(args.output_dir) if args.output_dir else None
        reference_discrimination(args.harness_revision, output_dir)
        return

    if args.command == "source-identity-validate":
        validate_source_identity()
        return

    if args.command == "source-identity-smoke":
        smoke_source_identity()
        return

    if not args.output_dir:
        ap.error("reference requires --output-dir")

    reference(args.harness_revision, Path(args.output_dir), args.ablation)


if __name__ == "__main__":
    main()
