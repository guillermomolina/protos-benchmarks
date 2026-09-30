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

"""PERF016 / guillermomolina/protos#727 post-Step-3 controlled timing harness.

Measures the combined timing effect of PERF015 + PERF016 by building two real, published,
unpatched baseline Protos products and timing the same four workloads on both under the canonical
post-adoption GraalVM 25.4.4.1.1 toolchain:

  * CONTROL      - 2e3f56fae3a500d3e4193e3345d8a82c35e4590e (0.3.117-SNAPSHOT), pre-PERF015.
  * INTERVENTION - 696b0f9797ebc8ced80009fb583027513852f55c (0.3.119-SNAPSHOT), post-PERF016.

That exactly the two PERF015/PERF016 commits separate the endpoints is supplied task input recorded
in config/perf016-post-step3.json; this harness cannot re-derive product lineage and does not
inspect the product repository. What it does verify, per built image, is the exact revision label,
the exact pom version, the canonical toolchain/runtime identity and, for every workload, that the
canonical and generated workload-control sources are byte-identical between the two images.

Infrastructure reuse. The image, the runtime probe and the timing/correctness driver are the
DIST006-D ones (docker/protos-dist006d/*), reached through runner/dist006d_baseline.py, which this
module loads by file path exactly as runner/perf004b2b.py loads perf004b. That works both for
`python3 runner/perf016_post_step3.py ...` (only runner/ on sys.path) and for tests that load runner
modules by path. Nothing in DIST006-D, PERF014 or any retained result namespace is modified; PERF014
contributes measurement discipline only (counterbalanced blocks, canonical + workload-control
pairing, stationarity diagnostics, the bounded order-effect method).

Three views are retained per block and aggregated per workload, never merged across workloads:

  1. control_variant_effect - direct revision effect on the retained common driver (PRIMARY).
  2. canonical_effect       - direct revision effect on each canonical workload.
  3. paired_control_effect  - the established PERF014 residual (SECONDARY discriminator).

Every effect is CONTROL minus INTERVENTION, so positive means the INTERVENTION is faster.

This module deliberately does not classify Step 3: STEP_3_TIMING_CLASS and STEP3_NEXT_ROUTING are
emitted as NOT_CLASSIFIED and no numeric classification threshold exists anywhere in it.

validate << smoke << reference. `validate` is static (no Docker, no timing) and self-tests the
fail-closed contract and the analysis with synthetic data. `smoke` builds and probes both products
and runs the correctness/admission matrix; it retains nothing. `reference` requires the exact clean
published harness SHA, runs the full A,B,A,B matrix at warmup=120/steady=100 and is the only command
that writes retained evidence (results/perf016-post-step3/).
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
from typing import Any, Callable
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf016-post-step3.json"
DIST006D_RUNNER = ROOT / "runner/dist006d_baseline.py"
MAKEFILE = ROOT / "Makefile"


def load_dist006d() -> Any:
    spec = importlib.util.spec_from_file_location("dist006d_baseline", DIST006D_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the DIST006-D runner: " + str(DIST006D_RUNNER))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dist006d = load_dist006d()

# Symbols this module relies on. The Maven pair marks the DIST008-B2 reconciliation: a checkout
# that predates it (or shared infrastructure that has since been changed) must fail closed here
# instead of running against a toolchain contract this harness was not written for.
REQUIRED_DIST006D_SYMBOLS = (
    "MAVEN_MINIMUM_VERSION",
    "MAVEN_SUPPORTED_MAJOR",
    "CANONICAL_TOOLCHAIN_JSON",
    "EXPECTED_ENGINE_VERSION",
    "EXPECTED_JDK_VERSION",
    "EXPECTED_JVMCI",
    "EXPECTED_RUNTIME",
    "EXPECTED_CONTAINER_IMAGE",
    "build_and_probe",
    "docker_entrypoint",
    "driver_correctness",
    "exact_published_harness_revision",
    "first_cpu",
    "host_identity",
    "image_text",
    "load",
    "output",
    "require_exact_sha",
    "summarize_ns",
    "validate",
    "validate_config_payload",
    "validate_dockerfile_contract",
    "validate_toolchain_contract",
    "worktree_harness_state",
    "write_manifest",
)


def require_dist006d_contract() -> None:
    missing = [name for name in REQUIRED_DIST006D_SYMBOLS if not hasattr(dist006d, name)]
    if missing:
        raise RuntimeError(
            "PERF016_REUSED_INFRASTRUCTURE_MISSING: runner/dist006d_baseline.py does not define "
            + ", ".join(missing)
            + "; PERF016 reuses the DIST006-D infrastructure as reconciled by DIST008-B2 (Maven "
            "minimum_version/supported_major contract), so the checkout is stale or the shared "
            "infrastructure was changed"
        )


require_dist006d_contract()

EXPECTED_WORK_ITEM = "PERF016"
EXPECTED_ISSUE = "guillermomolina/protos#727"
EXPECTED_PARENT_WORK_ITEM = "PERF010-B"
EXPECTED_PARENT_ISSUE = "guillermomolina/protos#722"
EXPECTED_SLICE = "POST_STEP3_CONTROLLED_TIMING"
PROTOS_REPOSITORY = "https://github.com/guillermomolina/protos.git"

EXPECTED_CONTROL_REVISION = "2e3f56fae3a500d3e4193e3345d8a82c35e4590e"
EXPECTED_CONTROL_VERSION = "0.3.117-SNAPSHOT"
EXPECTED_INTERVENTION_REVISION = "696b0f9797ebc8ced80009fb583027513852f55c"
EXPECTED_INTERVENTION_VERSION = "0.3.119-SNAPSHOT"
EXPECTED_PRODUCT_COMMITS = (
    {
        "revision": "453f2b00ae2bd0af1cd2761474549e85ff1cb8b6",
        "subject": "PERF015: admit canonical Boolean to guarded structured selection",
    },
    {
        "revision": "696b0f9797ebc8ced80009fb583027513852f55c",
        "subject": "PERF016: admit semantic Integer family to guarded represented selection",
    },
)
LINEAGE_VERIFICATION = "externally-verified-supplied-task-input-not-re-derived-by-harness"

# Evidence-unit identity pins. The authoritative toolchain contract stays single-sourced in the
# reused DIST006-D infrastructure; these literals only make a silent toolchain drift there fail
# closed instead of silently changing what this Evidence Unit measures.
EXPECTED_GRAALVM_RELEASE = "25.4.4.1.1"
EXPECTED_JDK_VERSION = "25.0.4.1.1"
EXPECTED_JVMCI = "25.4-b23"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_CONTAINER_IMAGE = (
    "ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@"
    "sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5"
)
EXPECTED_MAVEN_MINIMUM_VERSION = "3.9.9"
EXPECTED_MAVEN_SUPPORTED_MAJOR = 3

EXPECTED_WORKLOADS = (
    {
        "id": "micro/slot-read",
        "source": "micro/slot-read.protos",
        "expected": "42",
        "replace": "sink = holder.value",
        "with": "sink = 42",
    },
    {
        "id": "micro/closure-call",
        "source": "micro/closure-call.protos",
        "expected": "42",
        "replace": "sink = identity(42)",
        "with": "sink = 42",
    },
    {
        "id": "micro/method-call",
        "source": "micro/method-call.protos",
        "expected": "42",
        "replace": "sink = receiver.identity(42)",
        "with": "sink = 42",
    },
    {
        "id": "runtime/monomorphic-dispatch",
        "source": "runtime/monomorphic-dispatch.protos",
        "expected": "42",
        "replace": "sink = receiver.run()",
        "with": "sink = 42",
    },
)

ROLES = ("control", "intervention")
VARIANTS = ("canonical", "workload_control")
BLOCK_ORDER = ("A", "B", "A", "B")
SMOKE_BLOCK_ORDER = ("A", "B")
OPERATION_COUNT = 10000
WARMUP_ITERATIONS = 120
STEADY_ITERATIONS = 100
SMOKE_WARMUP_ITERATIONS = 1
SMOKE_STEADY_ITERATIONS = 2
TIMING_RECORDING_PHASE = "warmup_and_steady_recorded_separately_no_diagnostic_instrumentation"
CLEAN_TIMING_EXCLUSIONS = (
    "JFR",
    "TraceCompilation",
    "TraceCompilationDetails",
    "TraceInlining",
    "IGV",
    "allocation profiling",
    "source instrumentation",
    "Test Tool diagnostics",
)

OUTPUT_NAMESPACE = "results/perf016-post-step3"
HISTORICAL_OUTPUT_NAMESPACES = (
    "results/perf014-direct-closure-call",
    "results/dist006d-baseline",
    "results/upstream003-platform-comparison",
)
PROTECTED_HISTORICAL_PATHS = (
    "results/perf014-direct-closure-call/**",
    "results/dist006d-baseline/**",
)
RETAINED_ARTIFACTS = (
    "raw.json",
    "summary.tsv",
    "blocks.tsv",
    "stationarity.tsv",
    "README.md",
    "SHA256SUMS",
    "logs/",
)

# These two values are never computed from data: the harness collects and summarizes objective
# measurements and a later interpretation slice classifies them. They are constants (not read from
# config) so an edited config cannot smuggle in a classification; validation cross-checks the config.
STEP_3_TIMING_CLASS_PLACEHOLDER = "NOT_CLASSIFIED"
STEP3_NEXT_ROUTING_PLACEHOLDER = "NOT_CLASSIFIED"
LATER_INTERPRETATION_CLASSES = (
    "MATERIAL_LARGE_FACTOR_IMPROVEMENT",
    "MATERIAL_PARTIAL_IMPROVEMENT",
    "ESSENTIALLY_UNCHANGED",
)
THRESHOLD_MARKER_KEY = "numeric_classification_thresholds_defined"

VIEWS = ("control_variant_effect", "canonical_effect", "paired_control_effect")
VIEW_EVIDENCE_INPUT = {
    "control_variant_effect": "SHARED_DRIVER_TIMING_EFFECT",
    "canonical_effect": "COMMON_WORKLOAD_TIMING_EFFECTS",
    "paired_control_effect": "SECONDARY_PAIRED_CONTROL_DISCRIMINATOR",
}
VIEW_WEIGHT = {
    "control_variant_effect": "PRIMARY_FOR_COMMON_DRIVER",
    "canonical_effect": "COMMON_WORKLOAD_EFFECTS",
    "paired_control_effect": "SECONDARY",
}
VIEW_TITLES = {
    "control_variant_effect": (
        "Shared-driver / workload-control effect (SHARED_DRIVER_TIMING_EFFECT, PRIMARY for the "
        "common driver)"
    ),
    "canonical_effect": "Canonical common-workload effect (COMMON_WORKLOAD_TIMING_EFFECTS)",
    "paired_control_effect": "Paired-control residual (SECONDARY discriminator)",
}

CORPUS_DIR = "/opt/dist006d/corpus"
CONTROL_SOURCE_MOUNT = "/work/source.protos"
DRIVER_CLASSPATH = "/opt/dist006d/driver:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*"
PRODUCT_POM = "/opt/protos-source/pom.xml"
POM_NAMESPACE = "{http://maven.apache.org/POM/4.0.0}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def load(config_path: Path = CONFIG) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def fmt_ns(value: float) -> str:
    return f"{value:.1f}"


def fmt_pct(value: float) -> str:
    return f"{value:.4f}"


# --- static configuration contract (no Docker, no timing) ---


def find_threshold_keys(node: Any, path: str = "") -> list[str]:
    """Paths of every mapping key that names a threshold. The only permitted one is the explicit
    `numeric_classification_thresholds_defined: false` marker."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}/{key}"
            if "threshold" in str(key).lower() and key != THRESHOLD_MARKER_KEY:
                found.append(here)
            found.extend(find_threshold_keys(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(find_threshold_keys(value, f"{path}[{index}]"))
    return found


def require_independent_output_namespace(output: Any) -> None:
    require(
        isinstance(output, str) and bool(output),
        "PERF016_OUTPUT_NAMESPACE_MISMATCH: reference output must be a non-empty relative path",
    )
    for historical in HISTORICAL_OUTPUT_NAMESPACES:
        related = (
            output == historical
            or output.startswith(historical + "/")
            or historical.startswith(output.rstrip("/") + "/")
        )
        require(
            not related,
            f"PERF016_OUTPUT_NAMESPACE_COLLISION: {output!r} collides with historical evidence "
            f"namespace {historical!r}",
        )
    require(
        output == OUTPUT_NAMESPACE,
        f"PERF016_OUTPUT_NAMESPACE_MISMATCH: expected {OUTPUT_NAMESPACE!r}, got {output!r}",
    )


def validate_endpoints(cfg: dict[str, Any]) -> None:
    control = cfg.get("control")
    intervention = cfg.get("intervention")
    require(
        isinstance(control, dict) and isinstance(intervention, dict),
        "PERF016_ENDPOINT_MISSING: config must declare both a control and an intervention",
    )
    require(
        control.get("revision") != intervention.get("revision"),
        "PERF016_SAME_REVISION_REJECTED: control and intervention must pin two distinct Protos "
        "revisions",
    )
    require(
        control.get("version") != intervention.get("version"),
        "PERF016_SAME_VERSION_REJECTED: control and intervention must declare two distinct "
        "product versions",
    )
    for role, endpoint, revision, version in (
        ("control", control, EXPECTED_CONTROL_REVISION, EXPECTED_CONTROL_VERSION),
        (
            "intervention",
            intervention,
            EXPECTED_INTERVENTION_REVISION,
            EXPECTED_INTERVENTION_VERSION,
        ),
    ):
        upper = role.upper()
        require(endpoint.get("role") == role, f"PERF016_{upper}_ROLE_MISMATCH: {endpoint!r}")
        require(
            endpoint.get("variant") == "baseline",
            f"PERF016_{upper}_VARIANT_NOT_BASELINE: both roles must be ordinary baseline products",
        )
        require(
            endpoint.get("revision") == revision,
            f"PERF016_{upper}_REVISION_MISMATCH: expected {revision}, got "
            f"{endpoint.get('revision')!r}",
        )
        require(
            endpoint.get("version") == version,
            f"PERF016_{upper}_VERSION_MISMATCH: expected {version}, got {endpoint.get('version')!r}",
        )


def validate_product_lineage(cfg: dict[str, Any]) -> None:
    lineage = cfg.get("product_lineage")
    require(isinstance(lineage, dict), "PERF016_PRODUCT_LINEAGE_MISMATCH: lineage block missing")
    require(
        lineage.get("commit_count_between_endpoints") == 2,
        "PERF016_PRODUCT_LINEAGE_MISMATCH: exactly two product commits must separate the endpoints",
    )
    require(
        lineage.get("commits_between_endpoints") == list(EXPECTED_PRODUCT_COMMITS),
        "PERF016_PRODUCT_LINEAGE_MISMATCH: the two separating commits must be exactly PERF015 and "
        "PERF016",
    )
    require(
        lineage.get("unrelated_product_commit_between_endpoints") is False,
        "PERF016_PRODUCT_LINEAGE_MISMATCH: no unrelated product commit may separate the endpoints",
    )
    require(
        lineage.get("verification") == LINEAGE_VERIFICATION,
        "PERF016_PRODUCT_LINEAGE_MISMATCH: lineage must be declared as supplied, not re-derived",
    )
    require(
        lineage["commits_between_endpoints"][-1]["revision"] == EXPECTED_INTERVENTION_REVISION,
        "PERF016_PRODUCT_LINEAGE_MISMATCH: the last separating commit must be the intervention",
    )


def validate_toolchain_block(block: Any) -> None:
    require(isinstance(block, dict), "PERF016_TOOLCHAIN_GENERATION_MISMATCH: toolchain missing")
    graalvm = block.get("graalvm")
    components = block.get("graal_components")
    maven = block.get("maven")
    require(
        isinstance(graalvm, dict) and isinstance(components, dict) and isinstance(maven, dict),
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH: incomplete toolchain block",
    )
    generation_fields = {
        "graalvm.release": graalvm.get("release"),
        "graalvm.container_image": graalvm.get("container_image"),
        "graal_components.version": components.get("version"),
        "jvmci": block.get("jvmci"),
    }
    for label, value in generation_fields.items():
        text = str(value)
        require(
            "25.3" not in text and "25i3" not in text,
            f"PERF016_25_3_TOOLCHAIN_REJECTED: {label}={text!r} selects the historical 25.3 "
            "generation; PERF016 measures only the canonical 25.4 toolchain",
        )
    require(
        block.get("schema") == "protos-toolchain-v2",
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH: toolchain schema must be protos-toolchain-v2",
    )
    require(
        graalvm.get("release") == EXPECTED_GRAALVM_RELEASE
        and components.get("version") == EXPECTED_GRAALVM_RELEASE,
        f"PERF016_TOOLCHAIN_GENERATION_MISMATCH: GraalVM/Graal/Truffle must be "
        f"{EXPECTED_GRAALVM_RELEASE}",
    )
    require(
        graalvm.get("jdk_version") == EXPECTED_JDK_VERSION,
        f"PERF016_TOOLCHAIN_GENERATION_MISMATCH: JDK must be {EXPECTED_JDK_VERSION}",
    )
    require(
        graalvm.get("container_image") == EXPECTED_CONTAINER_IMAGE,
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH: container image must be the canonical 25.4 image",
    )
    require(
        block.get("jvmci") == EXPECTED_JVMCI,
        f"PERF016_TOOLCHAIN_GENERATION_MISMATCH: JVMCI must be {EXPECTED_JVMCI}",
    )
    require(
        block.get("expected_runtime") == EXPECTED_RUNTIME,
        f"PERF016_TOOLCHAIN_GENERATION_MISMATCH: runtime must be {EXPECTED_RUNTIME}",
    )
    require(
        maven
        == {
            "minimum_version": EXPECTED_MAVEN_MINIMUM_VERSION,
            "supported_major": EXPECTED_MAVEN_SUPPORTED_MAJOR,
        },
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH: Maven compatibility contract drift",
    )
    expected_keys = set(dist006d.CANONICAL_TOOLCHAIN_JSON) | {"jvmci", "expected_runtime"}
    require(
        set(block) == expected_keys,
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH: unexpected toolchain keys "
        + repr(sorted(set(block) ^ expected_keys)),
    )
    # Exact equality with the reused DIST006-D canonical contract (raises RuntimeError itself).
    dist006d.validate_toolchain_contract(
        {key: block[key] for key in dist006d.CANONICAL_TOOLCHAIN_JSON}
    )


def validate_measurement_policy(cfg: dict[str, Any]) -> None:
    require(
        cfg.get("operation_count") == OPERATION_COUNT,
        f"PERF016_OPERATION_COUNT_MISMATCH: expected {OPERATION_COUNT}, got "
        f"{cfg.get('operation_count')!r}",
    )
    require(
        cfg.get("warmup_iterations") == WARMUP_ITERATIONS,
        f"PERF016_WARMUP_POLICY_MISMATCH: expected {WARMUP_ITERATIONS}, got "
        f"{cfg.get('warmup_iterations')!r}",
    )
    require(
        cfg.get("steady_iterations") == STEADY_ITERATIONS,
        f"PERF016_STEADY_POLICY_MISMATCH: expected {STEADY_ITERATIONS}, got "
        f"{cfg.get('steady_iterations')!r}",
    )
    require(
        cfg.get("network") == "none",
        "PERF016_NETWORK_MISMATCH: timed units must run with networking disabled",
    )
    affinity = cfg.get("cpu_affinity")
    require(
        isinstance(affinity, dict)
        and affinity.get("mechanism") == "cpuset-cpus"
        and affinity.get("cpus") == 1,
        "PERF016_CPU_POLICY_MISMATCH: exactly one CPU pinned through cpuset-cpus",
    )
    require(
        cfg.get("timing_recording_phase") == TIMING_RECORDING_PHASE,
        "PERF016_MEASUREMENT_PHASE_MISMATCH: warmup and steady must be recorded separately",
    )
    exclusions = cfg.get("clean_timing_exclusions")
    require(
        isinstance(exclusions, list) and sorted(exclusions) == sorted(CLEAN_TIMING_EXCLUSIONS),
        "PERF016_DIAGNOSTIC_EXCLUSION_MISMATCH: timing must exclude exactly "
        + ", ".join(CLEAN_TIMING_EXCLUSIONS),
    )


def validate_workloads(cfg: dict[str, Any]) -> None:
    workloads = cfg.get("workloads")
    require(isinstance(workloads, list), "PERF016_WORKLOAD_SET_MISMATCH: workloads missing")
    ids = [item.get("id") if isinstance(item, dict) else None for item in workloads]
    require(
        ids == [item["id"] for item in EXPECTED_WORKLOADS],
        f"PERF016_WORKLOAD_SET_MISMATCH: expected exactly {[i['id'] for i in EXPECTED_WORKLOADS]}, "
        f"got {ids}",
    )
    require(
        workloads == list(EXPECTED_WORKLOADS),
        "PERF016_WORKLOAD_CONTROL_TRANSFORM_MISMATCH: the established PERF010 canonical/"
        "workload-control transformations and expected results must be unchanged",
    )


def validate_block_order(cfg: dict[str, Any]) -> None:
    require(
        cfg.get("block_order") == list(BLOCK_ORDER),
        f"PERF016_BLOCK_ORDER_MISMATCH: expected {list(BLOCK_ORDER)}, got "
        f"{cfg.get('block_order')!r}",
    )


def validate_measurement_views(cfg: dict[str, Any]) -> None:
    views = cfg.get("measurement_views")
    require(
        isinstance(views, dict) and set(views) == set(VIEWS),
        f"PERF016_MEASUREMENT_VIEW_MISMATCH: exactly the views {list(VIEWS)} are required",
    )
    for view in VIEWS:
        definition = views[view]
        require(
            isinstance(definition, dict),
            f"PERF016_MEASUREMENT_VIEW_MISMATCH: {view} definition missing",
        )
        require(
            definition.get("evidence_input") == VIEW_EVIDENCE_INPUT[view],
            f"PERF016_MEASUREMENT_VIEW_MISMATCH: {view} evidence input drift",
        )
        require(
            definition.get("weight") == VIEW_WEIGHT[view],
            f"PERF016_MEASUREMENT_VIEW_MISMATCH: {view} weight must be {VIEW_WEIGHT[view]}",
        )
        require(
            definition.get("positive_means") == "INTERVENTION_FASTER",
            f"PERF016_MEASUREMENT_VIEW_MISMATCH: {view} sign convention must be "
            "INTERVENTION_FASTER",
        )
        require(
            isinstance(definition.get("formula"), str) and bool(definition["formula"].strip()),
            f"PERF016_MEASUREMENT_VIEW_MISMATCH: {view} formula missing",
        )


def validate_classification(cfg: dict[str, Any]) -> None:
    classification = cfg.get("classification")
    require(
        isinstance(classification, dict),
        "PERF016_AUTOMATIC_CLASSIFICATION_REJECTED: classification block missing",
    )
    require(
        classification.get("step_3_timing_class") == STEP_3_TIMING_CLASS_PLACEHOLDER
        and classification.get("step3_next_routing") == STEP3_NEXT_ROUTING_PLACEHOLDER,
        "PERF016_AUTOMATIC_CLASSIFICATION_REJECTED: STEP_3_TIMING_CLASS and STEP3_NEXT_ROUTING "
        "must remain NOT_CLASSIFIED; classification is a later interpretation step",
    )
    require(
        classification.get("later_interpretation_vocabulary") == list(LATER_INTERPRETATION_CLASSES),
        "PERF016_AUTOMATIC_CLASSIFICATION_REJECTED: later-interpretation vocabulary drift",
    )
    require(
        classification.get(THRESHOLD_MARKER_KEY) is False,
        "PERF016_THRESHOLD_REJECTED: the harness must not define numeric classification thresholds",
    )
    thresholds = find_threshold_keys(cfg)
    require(
        not thresholds,
        "PERF016_THRESHOLD_REJECTED: threshold keys are forbidden in the config: "
        + ", ".join(thresholds),
    )


def validate_stages(cfg: dict[str, Any]) -> None:
    smoke_cfg = cfg.get("smoke")
    require(isinstance(smoke_cfg, dict), "PERF016_SMOKE_POLICY_MISMATCH: smoke block missing")
    require(
        smoke_cfg.get("retained_performance_evidence") is False
        and smoke_cfg.get("timing_evidence") is False
        and smoke_cfg.get("reference_evidence") is False,
        "PERF016_SMOKE_POLICY_MISMATCH: smoke must not produce retained, timing or reference "
        "evidence",
    )
    require(
        smoke_cfg.get("warmup_iterations") == SMOKE_WARMUP_ITERATIONS
        and smoke_cfg.get("steady_iterations") == SMOKE_STEADY_ITERATIONS,
        "PERF016_SMOKE_POLICY_MISMATCH: smoke must stay at its tiny fixed scale",
    )
    require(
        smoke_cfg.get("block_order") == list(SMOKE_BLOCK_ORDER)
        and smoke_cfg.get("correctness_gate") is True,
        "PERF016_SMOKE_POLICY_MISMATCH: smoke block order/correctness gate drift",
    )
    reference_cfg = cfg.get("reference")
    require(
        isinstance(reference_cfg, dict), "PERF016_REFERENCE_POLICY_MISMATCH: reference missing"
    )
    require_independent_output_namespace(reference_cfg.get("output"))
    require(
        reference_cfg.get("requires_exact_clean_published_harness_revision") is True,
        "PERF016_REFERENCE_POLICY_MISMATCH: reference must require the exact clean published "
        "harness revision",
    )
    require(
        reference_cfg.get("bounded_runs_supported") is False,
        "PERF016_REFERENCE_POLICY_MISMATCH: only the full matrix may produce retained evidence",
    )
    require(
        reference_cfg.get("retained_artifacts") == list(RETAINED_ARTIFACTS),
        "PERF016_REFERENCE_POLICY_MISMATCH: retained artifact set drift",
    )


def validate_reuse_and_boundary(cfg: dict[str, Any]) -> None:
    reuse = cfg.get("reused_infrastructure")
    require(
        isinstance(reuse, dict)
        and reuse.get("owner") == "DIST006-D"
        and reuse.get("modified_by_this_comparator") is False
        and reuse.get("retained_dist006d_baseline_is_not_the_control_measurement") is True,
        "PERF016_REUSED_INFRASTRUCTURE_MISMATCH: DIST006-D must be reused unmodified and its "
        "retained baseline must not be treated as the control measurement",
    )
    boundary = cfg.get("historical_boundary")
    require(
        isinstance(boundary, list) and set(PROTECTED_HISTORICAL_PATHS) <= set(boundary),
        "PERF016_HISTORICAL_BOUNDARY_MISMATCH: PERF014 and DIST006-D retained evidence must stay "
        "protected",
    )


def validate_config_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    require(cfg.get("schema_version") == 1, "PERF016_CONFIG_SCHEMA_MISMATCH: unsupported schema")
    require(
        cfg.get("work_item") == EXPECTED_WORK_ITEM
        and cfg.get("issue") == EXPECTED_ISSUE
        and cfg.get("parent_work_item") == EXPECTED_PARENT_WORK_ITEM
        and cfg.get("parent_issue") == EXPECTED_PARENT_ISSUE,
        "PERF016_AUTHORITY_MISMATCH: PERF016 / guillermomolina/protos#727 under PERF010-B / #722",
    )
    require(cfg.get("slice") == EXPECTED_SLICE, "PERF016_SLICE_MISMATCH")
    require(
        cfg.get("diagnostic_claim") is False and cfg.get("two_revision_comparator") is True,
        "PERF016_COMPARATOR_KIND_MISMATCH: a clean two-revision timing comparator, not a diagnostic",
    )
    protos = cfg.get("protos")
    require(
        isinstance(protos, dict) and protos.get("repository") == PROTOS_REPOSITORY,
        "PERF016_PROTOS_REPOSITORY_MISMATCH",
    )
    validate_endpoints(cfg)
    validate_product_lineage(cfg)
    require(
        cfg.get("both_variants_baseline") is True
        and cfg.get("patches_applied") == "none"
        and "ablation_patch" not in cfg,
        "PERF016_PATCH_REJECTED: both products must be unpatched baselines",
    )
    validate_toolchain_block(cfg.get("toolchain"))
    validate_measurement_policy(cfg)
    validate_workloads(cfg)
    validate_block_order(cfg)
    validate_measurement_views(cfg)
    validate_classification(cfg)
    validate_stages(cfg)
    validate_reuse_and_boundary(cfg)
    return cfg


def set_value(*path: Any, value: Any) -> Callable[[dict[str, Any]], None]:
    def mutator(cfg: dict[str, Any]) -> None:
        node: Any = cfg
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mutator


# (key, expected rejection tag, mutation of a copy of the valid config). Every mutation must be
# rejected, and rejected for the intended reason, by validate_config_payload.
CONFIG_REJECTION_CASES: tuple[tuple[str, str, Callable[[dict[str, Any]], None]], ...] = (
    (
        "wrong_control_revision",
        "PERF016_CONTROL_REVISION_MISMATCH",
        set_value("control", "revision", value="0" * 40),
    ),
    (
        "wrong_control_version",
        "PERF016_CONTROL_VERSION_MISMATCH",
        set_value("control", "version", value="0.3.118-SNAPSHOT"),
    ),
    (
        "wrong_intervention_revision",
        "PERF016_INTERVENTION_REVISION_MISMATCH",
        set_value("intervention", "revision", value="f" * 40),
    ),
    (
        "wrong_intervention_version",
        "PERF016_INTERVENTION_VERSION_MISMATCH",
        set_value("intervention", "version", value="0.3.120-SNAPSHOT"),
    ),
    (
        "control_equals_intervention_revision",
        "PERF016_SAME_REVISION_REJECTED",
        lambda c: c["intervention"].__setitem__("revision", c["control"]["revision"]),
    ),
    (
        "control_equals_intervention_version",
        "PERF016_SAME_VERSION_REJECTED",
        lambda c: c["intervention"].__setitem__("version", c["control"]["version"]),
    ),
    (
        "control_not_baseline",
        "PERF016_CONTROL_VARIANT_NOT_BASELINE",
        set_value("control", "variant", value="ablation"),
    ),
    (
        "intervention_not_baseline",
        "PERF016_INTERVENTION_VARIANT_NOT_BASELINE",
        set_value("intervention", "variant", value="ablation"),
    ),
    ("patch_applied", "PERF016_PATCH_REJECTED", set_value("patches_applied", value="ablation.patch")),
    (
        "product_lineage_commit_count",
        "PERF016_PRODUCT_LINEAGE_MISMATCH",
        set_value("product_lineage", "commit_count_between_endpoints", value=3),
    ),
    (
        "product_lineage_unrelated_commit",
        "PERF016_PRODUCT_LINEAGE_MISMATCH",
        set_value("product_lineage", "unrelated_product_commit_between_endpoints", value=True),
    ),
    (
        "toolchain_release_25_3",
        "PERF016_25_3_TOOLCHAIN_REJECTED",
        set_value("toolchain", "graalvm", "release", value="25.3.4.1"),
    ),
    (
        "toolchain_components_25_3",
        "PERF016_25_3_TOOLCHAIN_REJECTED",
        set_value("toolchain", "graal_components", "version", value="25.3.4.1"),
    ),
    (
        "container_25_3_selected",
        "PERF016_25_3_TOOLCHAIN_REJECTED",
        set_value(
            "toolchain",
            "graalvm",
            "container_image",
            value="ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825",
        ),
    ),
    (
        "wrong_jdk_version",
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH",
        set_value("toolchain", "graalvm", "jdk_version", value="25.0.4.1"),
    ),
    (
        "wrong_jvmci",
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH",
        set_value("toolchain", "jvmci", value="25.4-b99"),
    ),
    (
        "wrong_runtime",
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH",
        set_value(
            "toolchain",
            "expected_runtime",
            value="com.oracle.truffle.api.impl.DefaultTruffleRuntime",
        ),
    ),
    (
        "legacy_toolchain_schema",
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH",
        set_value("toolchain", "schema", value="protos-toolchain-v1"),
    ),
    (
        "maven_contract_drift",
        "PERF016_TOOLCHAIN_GENERATION_MISMATCH",
        set_value("toolchain", "maven", "minimum_version", value="3.9.8"),
    ),
    ("missing_workload", "PERF016_WORKLOAD_SET_MISMATCH", lambda c: c["workloads"].pop()),
    (
        "extra_workload",
        "PERF016_WORKLOAD_SET_MISMATCH",
        lambda c: c["workloads"].append({**c["workloads"][0], "id": "micro/extra"}),
    ),
    (
        "changed_control_replacement",
        "PERF016_WORKLOAD_CONTROL_TRANSFORM_MISMATCH",
        set_value("workloads", 0, "with", value="sink = 0"),
    ),
    (
        "changed_control_target",
        "PERF016_WORKLOAD_CONTROL_TRANSFORM_MISMATCH",
        set_value("workloads", 1, "replace", value="sink = identity(41)"),
    ),
    (
        "changed_expected_result",
        "PERF016_WORKLOAD_CONTROL_TRANSFORM_MISMATCH",
        set_value("workloads", 2, "expected", value="41"),
    ),
    (
        "wrong_operation_count",
        "PERF016_OPERATION_COUNT_MISMATCH",
        set_value("operation_count", value=1000),
    ),
    (
        "wrong_warmup_policy",
        "PERF016_WARMUP_POLICY_MISMATCH",
        set_value("warmup_iterations", value=20),
    ),
    (
        "wrong_steady_policy",
        "PERF016_STEADY_POLICY_MISMATCH",
        set_value("steady_iterations", value=50),
    ),
    ("network_enabled", "PERF016_NETWORK_MISMATCH", set_value("network", value="bridge")),
    (
        "diagnostic_exclusion_removed",
        "PERF016_DIAGNOSTIC_EXCLUSION_MISMATCH",
        lambda c: c["clean_timing_exclusions"].remove("JFR"),
    ),
    (
        "block_order_grouped",
        "PERF016_BLOCK_ORDER_MISMATCH",
        set_value("block_order", value=["A", "A", "B", "B"]),
    ),
    (
        "block_order_short",
        "PERF016_BLOCK_ORDER_MISMATCH",
        set_value("block_order", value=["A", "B"]),
    ),
    (
        "block_order_reversed",
        "PERF016_BLOCK_ORDER_MISMATCH",
        set_value("block_order", value=["B", "A", "B", "A"]),
    ),
    (
        "sign_convention_inverted",
        "PERF016_MEASUREMENT_VIEW_MISMATCH",
        set_value(
            "measurement_views", "control_variant_effect", "positive_means", value="INTERVENTION_SLOWER"
        ),
    ),
    (
        "shared_driver_demoted",
        "PERF016_MEASUREMENT_VIEW_MISMATCH",
        set_value("measurement_views", "control_variant_effect", "weight", value="SECONDARY"),
    ),
    (
        "paired_control_promoted",
        "PERF016_MEASUREMENT_VIEW_MISMATCH",
        set_value(
            "measurement_views", "paired_control_effect", "weight", value="PRIMARY_FOR_COMMON_DRIVER"
        ),
    ),
    (
        "automatic_step3_class",
        "PERF016_AUTOMATIC_CLASSIFICATION_REJECTED",
        set_value("classification", "step_3_timing_class", value="MATERIAL_PARTIAL_IMPROVEMENT"),
    ),
    (
        "automatic_step3_routing",
        "PERF016_AUTOMATIC_CLASSIFICATION_REJECTED",
        set_value("classification", "step3_next_routing", value="STEP4"),
    ),
    (
        "classification_threshold_introduced",
        "PERF016_THRESHOLD_REJECTED",
        set_value("classification", "material_improvement_threshold_percent", value=5),
    ),
    (
        "smoke_declared_retained",
        "PERF016_SMOKE_POLICY_MISMATCH",
        set_value("smoke", "retained_performance_evidence", value=True),
    ),
    (
        "output_collides_perf014",
        "PERF016_OUTPUT_NAMESPACE_COLLISION",
        set_value("reference", "output", value="results/perf014-direct-closure-call"),
    ),
    (
        "output_collides_dist006d",
        "PERF016_OUTPUT_NAMESPACE_COLLISION",
        set_value("reference", "output", value="results/dist006d-baseline"),
    ),
    (
        "output_nested_in_historical",
        "PERF016_OUTPUT_NAMESPACE_COLLISION",
        set_value(
            "reference", "output", value="results/perf014-direct-closure-call/perf016-post-step3"
        ),
    ),
    (
        "output_not_dedicated",
        "PERF016_OUTPUT_NAMESPACE_MISMATCH",
        set_value("reference", "output", value="results/perf016"),
    ),
    (
        "reference_without_exact_harness_sha",
        "PERF016_REFERENCE_POLICY_MISMATCH",
        set_value("reference", "requires_exact_clean_published_harness_revision", value=False),
    ),
    (
        "reused_infrastructure_modified",
        "PERF016_REUSED_INFRASTRUCTURE_MISMATCH",
        set_value("reused_infrastructure", "modified_by_this_comparator", value=True),
    ),
    (
        "historical_boundary_dropped",
        "PERF016_HISTORICAL_BOUNDARY_MISMATCH",
        lambda c: c["historical_boundary"].remove("results/perf014-direct-closure-call/**"),
    ),
)


def run_rejection_self_test(cfg: dict[str, Any]) -> int:
    for key, tag, mutate in CONFIG_REJECTION_CASES:
        mutated = copy.deepcopy(cfg)
        mutate(mutated)
        try:
            validate_config_payload(mutated)
        except RuntimeError as error:
            require(
                tag in str(error),
                f"PERF016_SELF_TEST_FAILED: {key} was rejected for the wrong reason: {error}",
            )
            continue
        raise RuntimeError(f"PERF016_SELF_TEST_FAILED: mutation was not rejected: {key}")
    return len(CONFIG_REJECTION_CASES)


MALFORMED_HARNESS_REVISIONS = (None, "", "main", "a" * 39, "a" * 41, "A" * 40, "g" * 40)


def run_harness_revision_self_test() -> int:
    """`reference` must refuse to run without an exact 40-hex published harness SHA. Malformed
    values are rejected before any git command runs, so this needs neither git nor Docker."""
    for value in MALFORMED_HARNESS_REVISIONS:
        try:
            dist006d.exact_published_harness_revision(value)
        except RuntimeError:
            continue
        raise RuntimeError(f"PERF016_SELF_TEST_FAILED: harness revision accepted: {value!r}")
    return len(MALFORMED_HARNESS_REVISIONS)


def require_unclassified(payload: dict[str, Any]) -> None:
    """Refuse any evidence that carries an automatic Step 3 classification or routing."""
    require(
        payload.get("STEP_3_TIMING_CLASS") == STEP_3_TIMING_CLASS_PLACEHOLDER
        and payload.get("STEP3_NEXT_ROUTING") == STEP3_NEXT_ROUTING_PLACEHOLDER
        and payload.get(THRESHOLD_MARKER_KEY) is False,
        "PERF016_AUTOMATIC_CLASSIFICATION_REJECTED: STEP_3_TIMING_CLASS and STEP3_NEXT_ROUTING "
        "must be NOT_CLASSIFIED and no numeric threshold may exist",
    )


# --- analysis (pure functions of the measured samples) ---


def block_role_order(label: str) -> tuple[str, str]:
    if label == "A":
        return ("control", "intervention")
    if label == "B":
        return ("intervention", "control")
    raise ValueError(f"unknown block label: {label!r}")


def direct_revision_effect(control_ns: float, intervention_ns: float) -> dict[str, float]:
    """CONTROL minus INTERVENTION and that difference as a percentage of CONTROL. Positive means
    the INTERVENTION is faster."""
    if control_ns <= 0:
        raise ValueError("the CONTROL median must be positive")
    effect_ns = control_ns - intervention_ns
    return {"effect_ns": effect_ns, "effect_percent": 100.0 * effect_ns / control_ns}


def paired_control_residual(
    control_canonical_ns: float,
    control_workload_control_ns: float,
    intervention_canonical_ns: float,
    intervention_workload_control_ns: float,
) -> dict[str, float]:
    """The established PERF014 residual. Positive means the canonical workload improved beyond the
    movement already explained by its common driver/workload-control variant."""
    canonical_improvement_ns = control_canonical_ns - intervention_canonical_ns
    control_movement_ns = control_workload_control_ns - intervention_workload_control_ns
    paired_control_effect_ns = canonical_improvement_ns - control_movement_ns
    return {
        "canonical_improvement_ns": canonical_improvement_ns,
        "control_movement_ns": control_movement_ns,
        "paired_control_effect_ns": paired_control_effect_ns,
        "paired_control_effect_percent": 100.0 * paired_control_effect_ns / control_canonical_ns,
    }


def classify_block(entry: dict[str, Any]) -> dict[str, Any]:
    """The three retained views for one (block, workload) entry."""
    median = {
        (role, variant): entry["roles"][role][variant]["steady_summary"]["median_ns"]
        for role in ROLES
        for variant in VARIANTS
    }
    control_canonical = median[("control", "canonical")]
    control_workload_control = median[("control", "workload_control")]
    intervention_canonical = median[("intervention", "canonical")]
    intervention_workload_control = median[("intervention", "workload_control")]

    control_variant = direct_revision_effect(control_workload_control, intervention_workload_control)
    canonical = direct_revision_effect(control_canonical, intervention_canonical)
    paired = paired_control_residual(
        control_canonical,
        control_workload_control,
        intervention_canonical,
        intervention_workload_control,
    )
    return {
        "block_index": entry["block_index"],
        "block_order": entry["block_order"],
        "workload": entry["workload"],
        "control_canonical_median_ns": control_canonical,
        "control_workload_control_median_ns": control_workload_control,
        "intervention_canonical_median_ns": intervention_canonical,
        "intervention_workload_control_median_ns": intervention_workload_control,
        "control_variant_effect_ns": control_variant["effect_ns"],
        "control_variant_effect_percent": control_variant["effect_percent"],
        "canonical_effect_ns": canonical["effect_ns"],
        "canonical_effect_percent": canonical["effect_percent"],
        **paired,
    }


def order_effect(a_values: list[float], b_values: list[float]) -> str:
    """The established PERF014 bounded method: DETECTED when the A-order and B-order ranges do
    not overlap, INCONCLUSIVE when either order has fewer than two blocks."""
    if len(a_values) < 2 or len(b_values) < 2:
        return "INCONCLUSIVE"
    a_range = (min(a_values), max(a_values))
    b_range = (min(b_values), max(b_values))
    non_overlapping = a_range[1] < b_range[0] or b_range[1] < a_range[0]
    return "DETECTED" if non_overlapping else "NOT_DETECTED"


def summarize_series(values: list[float]) -> dict[str, float]:
    median = statistics.median(values)
    return {
        "median": median,
        "mad": statistics.median([abs(value - median) for value in values]),
        "min": min(values),
        "max": max(values),
    }


def summarize_workload(classified: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive envelope over the retained blocks of one workload; a DESCRIPTIVE_ENVELOPE, not an
    inferential interval. The four workload-controls are never merged."""
    views: dict[str, Any] = {}
    for view in VIEWS:
        series_ns = [block[f"{view}_ns"] for block in classified]
        series_percent = [block[f"{view}_percent"] for block in classified]
        a_percent = [b[f"{view}_percent"] for b in classified if b["block_order"] == "A"]
        b_percent = [b[f"{view}_percent"] for b in classified if b["block_order"] == "B"]
        views[view] = {
            "evidence_input": VIEW_EVIDENCE_INPUT[view],
            "ns": summarize_series(series_ns),
            "percent": summarize_series(series_percent),
            "per_block_ns": series_ns,
            "per_block_percent": series_percent,
            "a_order_percent": a_percent,
            "b_order_percent": b_percent,
            "order_effect": order_effect(a_percent, b_percent),
        }
    levels: dict[str, Any] = {}
    for role in ROLES:
        for variant in VARIANTS:
            levels[f"{role}_{variant}"] = summarize_series(
                [block[f"{role}_{variant}_median_ns"] for block in classified]
            )
    return {"blocks": len(classified), "views": views, "level_medians_ns": levels}


def stationarity_diagnostics(steady_ns: list[int]) -> dict[str, Any]:
    """First-quarter versus last-quarter stationarity of one 100-sample steady timed unit, ported
    from the PERF014 comparator. Reported only; no threshold is derived from it."""
    if len(steady_ns) != STEADY_ITERATIONS:
        raise RuntimeError(
            f"stationarity diagnostics require exactly {STEADY_ITERATIONS} steady samples, got "
            f"{len(steady_ns)}"
        )
    quarter = STEADY_ITERATIONS // 4
    first_median = statistics.median(steady_ns[:quarter])
    last_median = statistics.median(steady_ns[-quarter:])
    return {
        "steady_median_ns": statistics.median(steady_ns),
        "first_quarter_median_ns": first_median,
        "last_quarter_median_ns": last_median,
        "last_quarter_vs_first_quarter_percent": 100.0
        * (last_median - first_median)
        / first_median,
    }


def stationarity_rows(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in blocks:
        for role in entry["role_sequence"]:
            for variant in VARIANTS:
                stationarity = entry["roles"][role][variant]["stationarity"]
                if stationarity is None:
                    raise RuntimeError("PERF016 reference units must carry stationarity diagnostics")
                rows.append(
                    {
                        "block_index": entry["block_index"],
                        "block_order": entry["block_order"],
                        "workload": entry["workload"],
                        "role": role,
                        "variant": variant,
                        **stationarity,
                    }
                )
    return rows


def analyze_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    classified = [classify_block(entry) for entry in blocks]
    workload_order: list[str] = []
    for block in classified:
        if block["workload"] not in workload_order:
            workload_order.append(block["workload"])
    return {
        "classified_blocks": classified,
        "per_workload_summary": {
            workload: summarize_workload([b for b in classified if b["workload"] == workload])
            for workload in workload_order
        },
        "per_timed_unit_stationarity": stationarity_rows(blocks),
    }


# --- derived human-readable views (pure functions of raw.json) ---


def tsv(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(row) for row in rows) + "\n"


def render_summary_tsv(raw: dict[str, Any]) -> str:
    rows = [
        [
            "workload",
            "view",
            "evidence_input",
            "blocks",
            "median_ns",
            "mad_ns",
            "min_ns",
            "max_ns",
            "median_percent",
            "mad_percent",
            "min_percent",
            "max_percent",
            "order_effect",
        ]
    ]
    for workload in raw["workload_ids"]:
        summary = raw["per_workload_summary"][workload]
        for view in VIEWS:
            data = summary["views"][view]
            rows.append(
                [
                    workload,
                    view,
                    data["evidence_input"],
                    str(summary["blocks"]),
                    fmt_ns(data["ns"]["median"]),
                    fmt_ns(data["ns"]["mad"]),
                    fmt_ns(data["ns"]["min"]),
                    fmt_ns(data["ns"]["max"]),
                    fmt_pct(data["percent"]["median"]),
                    fmt_pct(data["percent"]["mad"]),
                    fmt_pct(data["percent"]["min"]),
                    fmt_pct(data["percent"]["max"]),
                    data["order_effect"],
                ]
            )
    return tsv(rows)


def render_blocks_tsv(raw: dict[str, Any]) -> str:
    rows = [
        [
            "block_index",
            "block_order",
            "workload",
            "control_canonical_median_ns",
            "control_workload_control_median_ns",
            "intervention_canonical_median_ns",
            "intervention_workload_control_median_ns",
            "control_variant_effect_ns",
            "control_variant_effect_percent",
            "canonical_effect_ns",
            "canonical_effect_percent",
            "paired_control_effect_ns",
            "paired_control_effect_percent",
        ]
    ]
    for block in raw["classified_blocks"]:
        rows.append(
            [
                str(block["block_index"]),
                block["block_order"],
                block["workload"],
                fmt_ns(block["control_canonical_median_ns"]),
                fmt_ns(block["control_workload_control_median_ns"]),
                fmt_ns(block["intervention_canonical_median_ns"]),
                fmt_ns(block["intervention_workload_control_median_ns"]),
                fmt_ns(block["control_variant_effect_ns"]),
                fmt_pct(block["control_variant_effect_percent"]),
                fmt_ns(block["canonical_effect_ns"]),
                fmt_pct(block["canonical_effect_percent"]),
                fmt_ns(block["paired_control_effect_ns"]),
                fmt_pct(block["paired_control_effect_percent"]),
            ]
        )
    return tsv(rows)


def render_stationarity_tsv(raw: dict[str, Any]) -> str:
    rows = [
        [
            "block_index",
            "block_order",
            "workload",
            "role",
            "variant",
            "steady_median_ns",
            "first_quarter_median_ns",
            "last_quarter_median_ns",
            "last_quarter_vs_first_quarter_percent",
        ]
    ]
    for unit in raw["per_timed_unit_stationarity"]:
        rows.append(
            [
                str(unit["block_index"]),
                unit["block_order"],
                unit["workload"],
                unit["role"],
                unit["variant"],
                fmt_ns(unit["steady_median_ns"]),
                fmt_ns(unit["first_quarter_median_ns"]),
                fmt_ns(unit["last_quarter_median_ns"]),
                fmt_pct(unit["last_quarter_vs_first_quarter_percent"]),
            ]
        )
    return tsv(rows)


def render_readme(raw: dict[str, Any]) -> str:
    built = raw["built_image_identity"]
    commits = "; ".join(
        f"`{commit['revision']}` {commit['subject']}"
        for commit in raw["product_commits_between_endpoints"]
    )
    lines = [
        "# PERF016 post-Step-3 controlled timing Evidence Unit",
        "",
        raw["causal_question"],
        "",
        f"- Work item: `{raw['work_item']}` / `{raw['issue']}` (parent `{raw['parent_work_item']}` / "
        f"`{raw['parent_issue']}`), slice `{raw['slice']}`.",
        f"- Harness revision: `{raw['harness_revision']}`.",
        f"- CONTROL Protos revision (baseline, no patch): `{raw['control_revision']}` "
        f"(`{raw['control_version']}`).",
        f"- INTERVENTION Protos revision (baseline, no patch): `{raw['intervention_revision']}` "
        f"(`{raw['intervention_version']}`).",
        f"- Product commits between the endpoints (supplied input, not re-derived by the harness): "
        f"{commits}.",
        f"- Toolchain: GraalVM/Graal/Truffle `{raw['toolchain']['graalvm']['release']}`, JDK "
        f"`{raw['toolchain']['graalvm']['jdk_version']}`, JVMCI `{raw['jvmci_contract']}`; runtime "
        f"`{raw['runtime_identity']['control']['runtime_class']}`.",
        f"- Container base image: `{raw['base_image_identity']['selector']}` (image id "
        f"`{raw['base_image_identity']['id']}`).",
        f"- Built image ids: control `{built['control']['id']}`, intervention "
        f"`{built['intervention']['id']}`.",
        f"- Host: `{raw['host_identity']['platform']}`, CPU `{raw['host_identity'].get('cpu_model', '')}`.",
        f"- CPU affinity: `--cpuset-cpus {raw['cpu_policy']['cpuset']}` (allowed set "
        f"`{raw['cpu_policy']['allowed_cpus']}`); network `{raw['network']}`.",
        f"- Operation count `{raw['operation_count']}`; warmup `{raw['warmup_iterations']}`; steady "
        f"`{raw['steady_iterations']}`.",
        "- Block order `"
        + ",".join(raw["block_order"])
        + "` (A: CONTROL first, INTERVENTION second; B: INTERVENTION first, CONTROL second).",
        "- Workload source identity `" + raw["workload_source_identity"] + "`: canonical and "
        "generated workload-control sources are byte-identical between the two images "
        "(`workload_source_sha256` in `raw.json`).",
        f"- Correctness gate `{raw['correctness_gate']['result']}` for every role, workload and "
        "variant before any timing.",
        "- Timing contains no JFR, compiler tracing, IGV, allocation profiling, source "
        "instrumentation or Test Tool diagnostics.",
        "",
        "`raw.json` is authoritative. `summary.tsv`, `blocks.tsv`, `stationarity.tsv` and this file "
        "are derived from it. Every effect below is CONTROL minus INTERVENTION, so a positive value "
        "means the INTERVENTION is faster.",
    ]
    for view in VIEWS:
        lines += [
            "",
            "## " + VIEW_TITLES[view],
            "",
            "Formula: `" + raw["measurement_views"][view]["formula"] + "`",
            "",
            "| workload | blocks | median ns | MAD ns | min ns | max ns | median % | MAD % | min % "
            "| max % | order effect |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for workload in raw["workload_ids"]:
            summary = raw["per_workload_summary"][workload]
            data = summary["views"][view]
            lines.append(
                "| "
                + " | ".join(
                    [
                        workload,
                        str(summary["blocks"]),
                        fmt_ns(data["ns"]["median"]),
                        fmt_ns(data["ns"]["mad"]),
                        fmt_ns(data["ns"]["min"]),
                        fmt_ns(data["ns"]["max"]),
                        fmt_pct(data["percent"]["median"]),
                        fmt_pct(data["percent"]["mad"]),
                        fmt_pct(data["percent"]["min"]),
                        fmt_pct(data["percent"]["max"]),
                        data["order_effect"],
                    ]
                )
                + " |"
            )
    lines += [
        "",
        "## Per-block effects (percent of CONTROL; positive = INTERVENTION faster)",
        "",
        "| block | order | workload | shared-driver % | canonical % | paired-control % |",
        "|---|---|---|---|---|---|",
    ]
    for block in raw["classified_blocks"]:
        lines.append(
            f"| {block['block_index']} | {block['block_order']} | {block['workload']} "
            f"| {fmt_pct(block['control_variant_effect_percent'])} "
            f"| {fmt_pct(block['canonical_effect_percent'])} "
            f"| {fmt_pct(block['paired_control_effect_percent'])} |"
        )
    worst = max(
        abs(unit["last_quarter_vs_first_quarter_percent"])
        for unit in raw["per_timed_unit_stationarity"]
    )
    lines += [
        "",
        "## Stationarity",
        "",
        f"Largest absolute last-quarter-versus-first-quarter change over "
        f"{len(raw['per_timed_unit_stationarity'])} steady timed units: `{fmt_pct(worst)}` %. See "
        "`stationarity.tsv` for every unit. This is reported only: no threshold is applied and no "
        "block is discarded.",
        "",
        "## STEP_3_TIMING_CLASS = " + raw["STEP_3_TIMING_CLASS"],
        "## STEP3_NEXT_ROUTING = " + raw["STEP3_NEXT_ROUTING"],
        "",
        "This Evidence Unit deliberately does not classify Step 3. No threshold for "
        + ", ".join(LATER_INTERPRETATION_CLASSES)
        + " exists in this harness; classification is a later interpretation step performed against "
        "the retained raw evidence. A near-zero paired-control effect is not evidence that Step 3 had "
        "no effect, and no microbenchmark here supports a whole-language claim.",
        "",
    ]
    return "\n".join(lines)


def render_derived_views(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "summary.tsv": render_summary_tsv(raw),
        "blocks.tsv": render_blocks_tsv(raw),
        "stationarity.tsv": render_stationarity_tsv(raw),
        "README.md": render_readme(raw),
    }


# --- raw evidence ---


def build_raw(
    cfg: dict[str, Any],
    *,
    harness_revision: str,
    host: dict[str, Any],
    cpu_policy: dict[str, Any],
    admission: dict[str, Any],
    correctness: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    builds = admission["builds"]
    raw: dict[str, Any] = {
        "schema_version": 1,
        "work_item": cfg["work_item"],
        "issue": cfg["issue"],
        "parent_work_item": cfg["parent_work_item"],
        "parent_issue": cfg["parent_issue"],
        "slice": cfg["slice"],
        "evidence_kind": "post-step3-two-revision-controlled-timing",
        "evidence_status": "RETAINED",
        "causal_question": cfg["causal_question"],
        "control_revision": cfg["control"]["revision"],
        "control_version": cfg["control"]["version"],
        "intervention_revision": cfg["intervention"]["revision"],
        "intervention_version": cfg["intervention"]["version"],
        "product_commits_between_endpoints": cfg["product_lineage"]["commits_between_endpoints"],
        "product_lineage_verification": cfg["product_lineage"]["verification"],
        "unrelated_product_commit_between_endpoints": False,
        "both_product_variants_baseline": True,
        "patches_applied": "none",
        "harness_revision": harness_revision,
        "harness_worktree_clean": True,
        "host_identity": host,
        "cpu_policy": cpu_policy,
        "network": cfg["network"],
        "toolchain": builds["control"]["toolchain"],
        "jvmci_contract": cfg["toolchain"]["jvmci"],
        "runtime_identity": {role: builds[role]["runtime"] for role in ROLES},
        "base_image_identity": builds["control"]["base_image_identity"],
        "built_image_identity": {role: builds[role]["built_image_identity"] for role in ROLES},
        "build_identity": {role: builds[role]["build_identity"] for role in ROLES},
        "runtime_components": {role: builds[role]["runtime_components"] for role in ROLES},
        "operation_count": cfg["operation_count"],
        "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"],
        "block_order": list(cfg["block_order"]),
        "timing_recording_phase": cfg["timing_recording_phase"],
        "clean_timing_exclusions": list(cfg["clean_timing_exclusions"]),
        "workload_ids": [item["id"] for item in cfg["workloads"]],
        "workloads": cfg["workloads"],
        "workload_source_sha256": admission["workload_source_sha256"],
        "workload_source_identity": "PASS",
        "correctness_gate": correctness,
        "measurement_views": cfg["measurement_views"],
        "order_effect_method": cfg["order_effect_method"],
        "blocks": blocks,
        "diagnostic_instrumentation_present": False,
        "STEP_3_TIMING_CLASS": STEP_3_TIMING_CLASS_PLACEHOLDER,
        "STEP3_NEXT_ROUTING": STEP3_NEXT_ROUTING_PLACEHOLDER,
        THRESHOLD_MARKER_KEY: False,
    }
    raw.update(analyze_blocks(blocks))
    return raw


def verify_raw_identity(raw: dict[str, Any]) -> None:
    """The retained evidence itself must carry every exact identity this Evidence Unit requires."""
    require(raw.get("work_item") == EXPECTED_WORK_ITEM, "PERF016_RAW_IDENTITY_MISMATCH: work item")
    require(raw.get("slice") == EXPECTED_SLICE, "PERF016_RAW_IDENTITY_MISMATCH: slice")
    require(
        (
            raw.get("control_revision"),
            raw.get("control_version"),
            raw.get("intervention_revision"),
            raw.get("intervention_version"),
        )
        == (
            EXPECTED_CONTROL_REVISION,
            EXPECTED_CONTROL_VERSION,
            EXPECTED_INTERVENTION_REVISION,
            EXPECTED_INTERVENTION_VERSION,
        ),
        "PERF016_RAW_IDENTITY_MISMATCH: product revision/version",
    )
    dist006d.require_exact_sha(raw.get("harness_revision"), "harness revision")
    require(raw.get("network") == "none", "PERF016_RAW_IDENTITY_MISMATCH: network")
    require(
        (raw.get("operation_count"), raw.get("warmup_iterations"), raw.get("steady_iterations"))
        == (OPERATION_COUNT, WARMUP_ITERATIONS, STEADY_ITERATIONS),
        "PERF016_RAW_IDENTITY_MISMATCH: measurement policy",
    )
    require(raw.get("block_order") == list(BLOCK_ORDER), "PERF016_RAW_IDENTITY_MISMATCH: blocks")
    require(
        raw.get("diagnostic_instrumentation_present") is False,
        "PERF016_RAW_IDENTITY_MISMATCH: diagnostic instrumentation present",
    )
    require(
        raw["toolchain"]["graalvm"]["release"] == EXPECTED_GRAALVM_RELEASE
        and raw["toolchain"]["graalvm"]["jdk_version"] == EXPECTED_JDK_VERSION
        and raw.get("jvmci_contract") == EXPECTED_JVMCI,
        "PERF016_RAW_IDENTITY_MISMATCH: toolchain generation",
    )
    for role in ROLES:
        runtime = raw["runtime_identity"][role]
        require(
            runtime.get("runtime_class") == EXPECTED_RUNTIME
            and runtime.get("engine_version") == EXPECTED_GRAALVM_RELEASE
            and runtime.get("java_version") == EXPECTED_JDK_VERSION,
            f"PERF016_RAW_IDENTITY_MISMATCH: {role} runtime identity",
        )
        require_jvmci(runtime, EXPECTED_JVMCI, role)
    require(
        raw["built_image_identity"]["control"]["id"]
        != raw["built_image_identity"]["intervention"]["id"],
        "PERF016_RAW_IDENTITY_MISMATCH: control and intervention images are not distinct",
    )
    require(
        raw.get("workload_source_identity") == "PASS"
        and sorted(raw["workload_source_sha256"]) == sorted(raw["workload_ids"])
        and all(
            identity["canonical"]["control"] == identity["canonical"]["intervention"]
            and identity["workload_control"]["control"]
            == identity["workload_control"]["intervention"]
            for identity in raw["workload_source_sha256"].values()
        ),
        "PERF016_RAW_IDENTITY_MISMATCH: workload source identity",
    )


def verify_raw_correctness(raw: dict[str, Any]) -> None:
    """Correctness must have passed for every role, workload and variant that was timed."""
    gate = raw["correctness_gate"]
    wanted = {
        (role, workload, variant)
        for role in ROLES
        for workload in raw["workload_ids"]
        for variant in VARIANTS
    }
    cases = gate.get("cases", [])
    require(
        gate.get("result") == "PASS"
        and len(cases) == len(wanted)
        and {(case["role"], case["workload"], case["variant"]) for case in cases} == wanted
        and all(case["observed"] == case["expected"] for case in cases),
        "PERF016_RAW_IDENTITY_MISMATCH: correctness gate did not pass for every timed variant",
    )


def verify_raw(raw: dict[str, Any]) -> None:
    """Every identity, correctness result and derived number in raw.json must be reproducible from
    the raw samples it retains."""
    verify_raw_identity(raw)
    verify_raw_correctness(raw)
    require_unclassified(raw)
    blocks = raw["blocks"]
    require(
        len(blocks) == len(raw["block_order"]) * len(raw["workload_ids"]),
        "PERF016_RAW_IDENTITY_MISMATCH: block/workload matrix is incomplete",
    )
    for entry in blocks:
        require(
            entry["role_sequence"] == list(block_role_order(entry["block_order"])),
            "PERF016_RAW_IDENTITY_MISMATCH: block role sequence",
        )
        for role in ROLES:
            for variant in VARIANTS:
                unit = entry["roles"][role][variant]
                payload = unit["raw"]
                require(
                    len(payload["warmup_ns"]) == raw["warmup_iterations"]
                    and len(payload["steady_ns"]) == raw["steady_iterations"],
                    "PERF016_RAW_IDENTITY_MISMATCH: sample count",
                )
                require(
                    payload["diagnostic_instrumentation_present"] is False,
                    "PERF016_RAW_IDENTITY_MISMATCH: unit reports diagnostic instrumentation",
                )
                require(
                    unit["steady_summary"] == dist006d.summarize_ns(payload["steady_ns"]),
                    "PERF016_DERIVED_ANALYSIS_NOT_REPRODUCIBLE: steady_summary",
                )
                require(
                    unit["stationarity"] == stationarity_diagnostics(payload["steady_ns"]),
                    "PERF016_DERIVED_ANALYSIS_NOT_REPRODUCIBLE: stationarity",
                )
    derived = analyze_blocks(blocks)
    for key in ("classified_blocks", "per_workload_summary", "per_timed_unit_stationarity"):
        require(
            raw.get(key) == derived[key],
            f"PERF016_DERIVED_ANALYSIS_NOT_REPRODUCIBLE: {key}",
        )


# --- synthetic data for the validate self-tests (no Docker, no timing) ---

SYNTHETIC_LEVEL_NS = {
    ("control", "canonical"): 10000,
    ("control", "workload_control"): 4000,
    ("intervention", "canonical"): 8000,
    ("intervention", "workload_control"): 2000,
}
# Added to the INTERVENTION canonical level in B-order blocks only, to create a known order effect
# in the canonical and paired-control views but not in the shared-driver view.
SYNTHETIC_B_ORDER_PENALTY_NS = 500


def synthetic_unit(level_ns: int) -> dict[str, Any]:
    steady = [level_ns + (index % 5) - 2 for index in range(STEADY_ITERATIONS)]
    warmup = [level_ns * 3 + index for index in range(WARMUP_ITERATIONS)]
    payload = {
        "schema_version": 1,
        "mode": "timing",
        "expected": "42",
        "runtime": EXPECTED_RUNTIME,
        "source_reused": True,
        "process_reused": True,
        "context_reused": True,
        "fresh_activation_per_iteration": True,
        "diagnostic_instrumentation_present": False,
        "warmup_ns": warmup,
        "steady_ns": steady,
    }
    return {
        "raw": payload,
        "steady_summary": dist006d.summarize_ns(steady),
        "stationarity": stationarity_diagnostics(steady),
        "returncode": 0,
        "stdout_log": "synthetic.stdout.log",
        "stderr_log": "synthetic.stderr.log",
        "stdout_sha256": "0" * 64,
        "stderr_sha256": "0" * 64,
    }


def synthetic_blocks() -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block_index, label in enumerate(BLOCK_ORDER):
        sequence = block_role_order(label)
        for workload_index, item in enumerate(EXPECTED_WORKLOADS):
            scale = workload_index + 1
            roles: dict[str, Any] = {}
            for role in sequence:
                roles[role] = {}
                for variant in VARIANTS:
                    level = SYNTHETIC_LEVEL_NS[(role, variant)] * scale
                    if label == "B" and role == "intervention" and variant == "canonical":
                        level += SYNTHETIC_B_ORDER_PENALTY_NS * scale
                    roles[role][variant] = synthetic_unit(level)
            blocks.append(
                {
                    "block_index": block_index,
                    "block_order": label,
                    "workload": item["id"],
                    "role_sequence": list(sequence),
                    "roles": roles,
                }
            )
    return blocks


def synthetic_admission(cfg: dict[str, Any]) -> dict[str, Any]:
    base = {
        "selector": EXPECTED_CONTAINER_IMAGE,
        "id": "sha256:" + "b" * 64,
        "repo_digests": [
            "ghcr.io/graalvm/graalvm-community@sha256:"
            "a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5"
        ],
        "architecture": "amd64",
        "os": "linux",
    }
    runtime = {
        "runtime_class": EXPECTED_RUNTIME,
        "engine_version": EXPECTED_GRAALVM_RELEASE,
        "java_version": EXPECTED_JDK_VERSION,
        "java_runtime_version": EXPECTED_JDK_VERSION + "+1-jvmci-" + EXPECTED_JVMCI,
        "java_vm_version": EXPECTED_JDK_VERSION + "+1-jvmci-" + EXPECTED_JVMCI,
    }
    builds: dict[str, Any] = {}
    for role, marker in (("control", "c"), ("intervention", "d")):
        builds[role] = {
            "tag": "protos-benchmarks-dist006d:synthetic-" + role,
            "base_image_identity": base,
            "built_image_identity": {
                "selector": "protos-benchmarks-dist006d:synthetic-" + role,
                "id": "sha256:" + marker * 64,
                "repo_digests": [],
                "architecture": "amd64",
                "os": "linux",
            },
            "toolchain": copy.deepcopy(dist006d.CANONICAL_TOOLCHAIN_JSON),
            "runtime": dict(runtime),
            "build_identity": "synthetic",
            "runtime_components": [],
        }
    return {
        "builds": builds,
        "workload_source_sha256": {
            item["id"]: {
                "source": item["source"],
                "transform": {"replace": item["replace"], "with": item["with"]},
                "canonical": {"control": "e" * 64, "intervention": "e" * 64},
                "workload_control": {"control": "f" * 64, "intervention": "f" * 64},
            }
            for item in cfg["workloads"]
        },
    }


def synthetic_correctness(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "result": "PASS",
        "cases": [
            {
                "role": role,
                "workload": item["id"],
                "variant": variant,
                "expected": item["expected"],
                "observed": item["expected"],
                "runtime": EXPECTED_RUNTIME,
            }
            for role in ROLES
            for item in cfg["workloads"]
            for variant in VARIANTS
        ],
    }


def synthetic_raw(cfg: dict[str, Any]) -> dict[str, Any]:
    return build_raw(
        cfg,
        harness_revision="a" * 40,
        host={"platform": "synthetic", "machine": "synthetic", "kernel": "synthetic"},
        cpu_policy={"mechanism": "cpuset-cpus", "cpuset": "0", "allowed_cpus": "0"},
        admission=synthetic_admission(cfg),
        correctness=synthetic_correctness(cfg),
        blocks=synthetic_blocks(),
    )


def run_sign_convention_self_test() -> None:
    """Pin the sign of every effect with synthetic numbers so a later edit cannot silently invert
    it: CONTROL minus INTERVENTION, positive means the INTERVENTION is faster."""
    faster = direct_revision_effect(1000, 400)
    require(
        faster == {"effect_ns": 600, "effect_percent": 60.0},
        "PERF016_SIGN_SELF_TEST_FAILED: an INTERVENTION faster than CONTROL must be positive",
    )
    slower = direct_revision_effect(400, 1000)
    require(
        slower == {"effect_ns": -600, "effect_percent": -150.0},
        "PERF016_SIGN_SELF_TEST_FAILED: an INTERVENTION slower than CONTROL must be negative",
    )
    require(
        direct_revision_effect(700, 700) == {"effect_ns": 0, "effect_percent": 0.0},
        "PERF016_SIGN_SELF_TEST_FAILED: identical medians must give a zero effect",
    )
    # (control canonical, control workload-control, intervention canonical, intervention
    # workload-control) -> (canonical improvement, control movement, residual ns, residual %).
    residual_cases = (
        ((1000, 400, 500, 200), (500, 200, 300, 30.0)),
        # Step 3 improves the shared driver equally in both variants: the residual is intentionally 0.
        ((1000, 400, 800, 200), (200, 200, 0, 0.0)),
        ((1000, 400, 900, 200), (100, 200, -100, -10.0)),
        ((1000, 400, 1100, 600), (-100, -200, 100, 10.0)),
        ((1000, 400, 1000, 400), (0, 0, 0, 0.0)),
    )
    for inputs, expected in residual_cases:
        observed = paired_control_residual(*inputs)
        require(
            (
                observed["canonical_improvement_ns"],
                observed["control_movement_ns"],
                observed["paired_control_effect_ns"],
                observed["paired_control_effect_percent"],
            )
            == expected,
            f"PERF016_SIGN_SELF_TEST_FAILED: paired-control residual {inputs} -> {observed}",
        )


def run_analysis_self_test(cfg: dict[str, Any]) -> None:
    """Exercise the whole derived-analysis and rendering pipeline on synthetic units whose exact
    effects are known by construction (see synthetic_blocks)."""
    raw = synthetic_raw(cfg)
    verify_raw(raw)
    retained = json.loads(json.dumps(raw, sort_keys=True))
    verify_raw(retained)
    require(
        render_derived_views(raw) == render_derived_views(retained),
        "PERF016_DERIVED_VIEWS_NOT_REPRODUCIBLE: views differ between in-memory and retained raw",
    )

    first_a = raw["classified_blocks"][0]
    first_b = raw["classified_blocks"][len(EXPECTED_WORKLOADS)]
    require(
        (
            first_a["block_order"],
            first_a["control_variant_effect_ns"],
            first_a["control_variant_effect_percent"],
            first_a["canonical_effect_ns"],
            first_a["canonical_effect_percent"],
            first_a["paired_control_effect_ns"],
            first_a["paired_control_effect_percent"],
        )
        == ("A", 2000, 50.0, 2000, 20.0, 0, 0.0),
        f"PERF016_ANALYSIS_SELF_TEST_FAILED: A-order block {first_a}",
    )
    require(
        (
            first_b["block_order"],
            first_b["canonical_effect_ns"],
            first_b["canonical_effect_percent"],
            first_b["paired_control_effect_ns"],
            first_b["paired_control_effect_percent"],
        )
        == ("B", 1500, 15.0, -500, -5.0),
        f"PERF016_ANALYSIS_SELF_TEST_FAILED: B-order block {first_b}",
    )
    summary = raw["per_workload_summary"][EXPECTED_WORKLOADS[0]["id"]]["views"]
    require(
        summary["control_variant_effect"]["percent"]["median"] == 50.0
        and summary["control_variant_effect"]["order_effect"] == "NOT_DETECTED"
        and summary["canonical_effect"]["percent"]["median"] == 17.5
        and summary["canonical_effect"]["order_effect"] == "DETECTED"
        and summary["paired_control_effect"]["percent"]["median"] == -2.5
        and summary["paired_control_effect"]["order_effect"] == "DETECTED",
        f"PERF016_ANALYSIS_SELF_TEST_FAILED: aggregate summary {summary}",
    )
    require(
        len(raw["classified_blocks"]) == len(BLOCK_ORDER) * len(EXPECTED_WORKLOADS)
        and len(raw["per_timed_unit_stationarity"])
        == len(BLOCK_ORDER) * len(EXPECTED_WORKLOADS) * len(ROLES) * len(VARIANTS)
        and all(
            unit["last_quarter_vs_first_quarter_percent"] == 0.0
            for unit in raw["per_timed_unit_stationarity"]
        ),
        "PERF016_ANALYSIS_SELF_TEST_FAILED: block/stationarity matrix",
    )
    require(
        order_effect([1.0, 2.0], [3.0, 4.0]) == "DETECTED"
        and order_effect([1.0, 3.0], [2.0, 4.0]) == "NOT_DETECTED"
        and order_effect([1.0], [3.0, 4.0]) == "INCONCLUSIVE",
        "PERF016_ANALYSIS_SELF_TEST_FAILED: order-effect method",
    )
    classified = copy.deepcopy(raw)
    classified["STEP_3_TIMING_CLASS"] = "MATERIAL_LARGE_FACTOR_IMPROVEMENT"
    try:
        require_unclassified(classified)
    except RuntimeError:
        return
    raise RuntimeError("PERF016_SELF_TEST_FAILED: an automatic Step 3 classification was accepted")


def validate_reused_infrastructure(cfg: dict[str, Any]) -> None:
    reuse = cfg["reused_infrastructure"]
    for key in ("runner", "config", "dockerfile", "driver", "runtime_probe"):
        path = ROOT / reuse[key]
        require(path.is_file(), f"PERF016_REUSED_INFRASTRUCTURE_MISSING: {path}")
    for label, observed, expected in (
        ("EXPECTED_ENGINE_VERSION", dist006d.EXPECTED_ENGINE_VERSION, EXPECTED_GRAALVM_RELEASE),
        ("EXPECTED_JDK_VERSION", dist006d.EXPECTED_JDK_VERSION, EXPECTED_JDK_VERSION),
        ("EXPECTED_JVMCI", dist006d.EXPECTED_JVMCI, EXPECTED_JVMCI),
        ("EXPECTED_RUNTIME", dist006d.EXPECTED_RUNTIME, EXPECTED_RUNTIME),
        ("EXPECTED_CONTAINER_IMAGE", dist006d.EXPECTED_CONTAINER_IMAGE, EXPECTED_CONTAINER_IMAGE),
        (
            "MAVEN_MINIMUM_VERSION",
            dist006d.MAVEN_MINIMUM_VERSION,
            EXPECTED_MAVEN_MINIMUM_VERSION,
        ),
        (
            "MAVEN_SUPPORTED_MAJOR",
            dist006d.MAVEN_SUPPORTED_MAJOR,
            EXPECTED_MAVEN_SUPPORTED_MAJOR,
        ),
    ):
        require(
            observed == expected,
            f"PERF016_TOOLCHAIN_GENERATION_MISMATCH: reused DIST006-D {label}={observed!r}, "
            f"PERF016 pins {expected!r}",
        )
    require(
        cfg["toolchain"] == dist006d.load()["toolchain"],
        "PERF016_TOOLCHAIN_FORKED: the PERF016 toolchain block must equal the DIST006-D one",
    )
    # The reused infrastructure's own static contract (config, Dockerfile, driver, Makefile).
    with contextlib.redirect_stdout(io.StringIO()):
        dist006d.validate()


def validate() -> dict[str, Any]:
    cfg = validate_config_payload(load())
    validate_reused_infrastructure(cfg)
    run_sign_convention_self_test()
    run_analysis_self_test(cfg)
    rejected = run_rejection_self_test(cfg)
    malformed = run_harness_revision_self_test()

    makefile = MAKEFILE.read_text(encoding="utf-8")
    for target in (
        "perf016-post-step3-validate:",
        "perf016-post-step3-smoke:",
        "perf016-post-step3-reference:",
    ):
        require(target in makefile, "PERF016_MAKEFILE_TARGET_MISSING: " + target[:-1])

    print("PERF016_POST_STEP3_CONFIG=PASS")
    print("CONTROL_REVISION=" + cfg["control"]["revision"])
    print("CONTROL_VERSION=" + cfg["control"]["version"])
    print("INTERVENTION_REVISION=" + cfg["intervention"]["revision"])
    print("INTERVENTION_VERSION=" + cfg["intervention"]["version"])
    print(
        "PRODUCT_COMMITS_BETWEEN_ENDPOINTS="
        + str(cfg["product_lineage"]["commit_count_between_endpoints"])
    )
    print("PERF016_POST_STEP3_PRODUCT_LINEAGE=SUPPLIED_INPUT_NOT_RE_DERIVED")
    print("PERF016_POST_STEP3_TOOLCHAIN_CONTRACT=PASS")
    print("TOOLCHAIN=" + cfg["toolchain"]["graalvm"]["release"])
    print("JDK=" + cfg["toolchain"]["graalvm"]["jdk_version"])
    print("JVMCI=" + cfg["toolchain"]["jvmci"])
    print("PERF016_POST_STEP3_REUSED_INFRASTRUCTURE=PASS")
    print("WORKLOAD_SET=PASS")
    print("WORKLOAD_CONTROL_POLICY=PASS")
    print("COUNTERBALANCE=" + ",".join(cfg["block_order"]))
    print("PERF016_POST_STEP3_SIGN_CONVENTION_SELF_TEST=PASS")
    print("PERF016_POST_STEP3_ANALYSIS_SELF_TEST=PASS")
    print(f"PERF016_POST_STEP3_REJECTION_SELF_TEST=PASS cases={rejected}")
    print(f"PERF016_POST_STEP3_HARNESS_SHA_SELF_TEST=PASS cases={malformed}")
    print("PERF016_POST_STEP3_OUTPUT_NAMESPACE=" + cfg["reference"]["output"])
    print("STEP_3_TIMING_CLASS=" + STEP_3_TIMING_CLASS_PLACEHOLDER)
    print("STEP3_NEXT_ROUTING=" + STEP3_NEXT_ROUTING_PLACEHOLDER)
    print("PERF016_POST_STEP3_STATIC_VALIDATION=PASS")
    return cfg


# --- admission (Docker, no timing) ---


def image_bytes(tag: str, cpu: str, path: str) -> bytes:
    """Exact bytes of a file inside a built image; read as bytes so source identity is a true
    SHA-256 of the file and cannot be masked by newline translation."""
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
            "cat",
            tag,
            path,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"cannot read {path} from image {tag}: "
            + completed.stderr.decode("utf-8", errors="replace")[-2000:]
        )
    return completed.stdout


def image_product_version(tag: str, cpu: str) -> str:
    """The built image's own pom.xml version, read back from the artifact."""
    root = ET.fromstring(dist006d.image_text(tag, cpu, PRODUCT_POM))
    element = root.find(POM_NAMESPACE + "version")
    return element.text.strip() if element is not None and element.text else ""


def require_jvmci(runtime: dict[str, str], jvmci: str, role: str) -> None:
    needle = "jvmci-" + jvmci
    for field in ("java_runtime_version", "java_vm_version"):
        observed = runtime.get(field, "")
        require(
            needle in observed,
            f"PERF016_JVMCI_IDENTITY_MISMATCH: role={role} {field}={observed!r} does not contain "
            f"{needle!r}",
        )


def require_same_toolchain_identity(builds: dict[str, dict[str, Any]]) -> None:
    """Both images must prove the same toolchain/runtime, and must be two distinct images."""
    control, intervention = builds["control"], builds["intervention"]
    for key in ("toolchain", "runtime", "runtime_components", "base_image_identity"):
        require(
            control[key] == intervention[key],
            f"PERF016_TOOLCHAIN_IDENTITY_MISMATCH: {key} differs between the control and "
            "intervention images",
        )
    require(
        control["built_image_identity"]["id"] != intervention["built_image_identity"]["id"],
        "PERF016_IMAGES_NOT_DISTINCT: control and intervention resolved to the same image id",
    )


def workload_control_source(canonical: bytes, item: dict[str, Any]) -> bytes:
    try:
        text = canonical.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError(f"workload source {item['id']} is not valid UTF-8") from error
    count = text.count(item["replace"])
    if count != 1:
        raise RuntimeError(
            f"expected exactly one workload-control target in {item['id']}, found {count}"
        )
    return text.replace(item["replace"], item["with"], 1).encode("utf-8")


def verify_workload_source_identity(
    cfg: dict[str, Any], canonical: dict[str, dict[str, bytes]]
) -> tuple[dict[str, Any], dict[str, dict[str, bytes]]]:
    """Fail closed unless every measured workload is byte-identical between the two images, for
    both the canonical source and the generated workload-control source. Never inferred from Git."""
    identity: dict[str, Any] = {}
    generated: dict[str, dict[str, bytes]] = {role: {} for role in ROLES}
    for item in cfg["workloads"]:
        digests = {role: sha256_bytes(canonical[role][item["id"]]) for role in ROLES}
        if digests["control"] != digests["intervention"]:
            raise RuntimeError(
                f"WORKLOAD_SOURCE_IDENTITY_MISMATCH: workload={item['id']} "
                f"control_sha256={digests['control']} intervention_sha256={digests['intervention']}"
                " - both product revisions must execute byte-identical benchmark programs"
            )
        for role in ROLES:
            generated[role][item["id"]] = workload_control_source(canonical[role][item["id"]], item)
        control_digests = {role: sha256_bytes(generated[role][item["id"]]) for role in ROLES}
        if control_digests["control"] != control_digests["intervention"]:
            raise RuntimeError(
                f"WORKLOAD_SOURCE_IDENTITY_MISMATCH: workload={item['id']} generated workload-"
                f"control control_sha256={control_digests['control']} "
                f"intervention_sha256={control_digests['intervention']}"
            )
        identity[item["id"]] = {
            "source": item["source"],
            "transform": {"replace": item["replace"], "with": item["with"]},
            "canonical": digests,
            "workload_control": control_digests,
        }
    return identity, generated


def read_canonical_sources(
    cfg: dict[str, Any],
    tags: dict[str, str],
    cpu: str,
    reader: Callable[[str, str, str], bytes] = image_bytes,
) -> dict[str, dict[str, bytes]]:
    return {
        role: {
            item["id"]: reader(tags[role], cpu, f"{CORPUS_DIR}/{item['source']}")
            for item in cfg["workloads"]
        }
        for role in ROLES
    }


def write_control_sources(
    generated: dict[str, dict[str, bytes]], work: Path
) -> dict[str, dict[str, Path]]:
    paths: dict[str, dict[str, Path]] = {}
    for role in ROLES:
        role_dir = work / role
        role_dir.mkdir(parents=True, exist_ok=True)
        paths[role] = {}
        for workload, data in generated[role].items():
            path = role_dir / (workload.replace("/", "__") + "-workload-control.protos")
            path.write_bytes(data)
            paths[role][workload] = path
    return paths


def admit_products(cfg: dict[str, Any], cpu: str) -> dict[str, Any]:
    """Build and probe both exact products through the reused DIST006-D infrastructure and fail
    closed before any timing unless both prove the same canonical 25.4 toolchain/runtime, their own
    pinned revision and version, and byte-identical workload sources."""
    builds: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        endpoint = cfg[role]
        build = dist006d.build_and_probe(cfg, endpoint["revision"], cpu)
        require_jvmci(build["runtime"], cfg["toolchain"]["jvmci"], role)
        observed_version = image_product_version(build["tag"], cpu)
        require(
            observed_version == endpoint["version"],
            f"PERF016_VERSION_IDENTITY_MISMATCH: role={role} image pom version "
            f"{observed_version!r}, expected {endpoint['version']!r}",
        )
        builds[role] = build
        print(
            f"PERF016 IMAGE role={role} revision={endpoint['revision']} version={observed_version} "
            f"tag={build['tag']} id={build['built_image_identity']['id']}",
            flush=True,
        )
    require_same_toolchain_identity(builds)

    tags = {role: builds[role]["tag"] for role in ROLES}
    canonical = read_canonical_sources(cfg, tags, cpu)
    source_identity, generated = verify_workload_source_identity(cfg, canonical)

    print("PERF016_BOTH_IMAGES_REVISION_LABEL_MATCH=PASS")
    print("PERF016_BOTH_IMAGES_VERSION_MATCH=PASS")
    print("PERF016_BOTH_IMAGES_TOOLCHAIN_IDENTITY=PASS")
    print("WORKLOAD_SOURCE_IDENTITY=PASS")
    return {
        "builds": builds,
        "workload_source_sha256": source_identity,
        "workload_control_bytes": generated,
    }


def correctness_gate(
    cfg: dict[str, Any],
    admission: dict[str, Any],
    cpu: str,
    control_sources: dict[str, dict[str, Path]],
) -> dict[str, Any]:
    """Correctness PASS for the very variant, workload and role about to be timed. Any failure is
    fatal: a wrong result is not a performance result."""
    cases: list[dict[str, str]] = []
    for role in ROLES:
        tag = admission["builds"][role]["tag"]
        for item in cfg["workloads"]:
            results = (
                (
                    "canonical",
                    dist006d.driver_correctness(
                        tag, cpu, f"{CORPUS_DIR}/{item['source']}", item["expected"]
                    ),
                ),
                (
                    "workload_control",
                    dist006d.driver_correctness(
                        tag,
                        cpu,
                        "",
                        item["expected"],
                        source_host=control_sources[role][item["id"]],
                    ),
                ),
            )
            for variant, result in results:
                cases.append(
                    {
                        "role": role,
                        "workload": item["id"],
                        "variant": variant,
                        "expected": item["expected"],
                        "observed": result["observed"],
                        "runtime": result["runtime"],
                    }
                )
                print(
                    f"PERF016 CORRECTNESS PASS role={role} workload={item['id']} "
                    f"variant={variant} observed={result['observed']}",
                    flush=True,
                )
    return {"result": "PASS", "cases": cases}


# --- timing (Docker) ---


def driver_java_args(*mode_args: str) -> list[str]:
    return [
        "-Xss128m",
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        DRIVER_CLASSPATH,
        "Dist006dDriver",
        *mode_args,
    ]


def validate_timing_payload(
    payload: dict[str, Any], expected: str, warmup: int, steady: int, label: str
) -> None:
    require(
        payload.get("mode") == "timing" and payload.get("runtime") == EXPECTED_RUNTIME,
        f"PERF016_TIMING_IDENTITY_MISMATCH: {label}",
    )
    require(payload.get("expected") == expected, f"PERF016_TIMING_RESULT_MISMATCH: {label}")
    warmup_ns = payload.get("warmup_ns")
    steady_ns = payload.get("steady_ns")
    require(
        isinstance(warmup_ns, list) and len(warmup_ns) == warmup,
        f"PERF016_TIMING_SAMPLE_COUNT_MISMATCH: {label} warmup expected={warmup}",
    )
    require(
        isinstance(steady_ns, list) and len(steady_ns) == steady,
        f"PERF016_TIMING_SAMPLE_COUNT_MISMATCH: {label} steady expected={steady}",
    )
    require(
        all(type(value) is int and value > 0 for value in warmup_ns + steady_ns),
        f"PERF016_TIMING_SAMPLE_INVALID: {label} samples must be positive integers",
    )
    require(
        payload.get("diagnostic_instrumentation_present") is False,
        f"PERF016_DIAGNOSTIC_INSTRUMENTATION_PRESENT: {label}",
    )


def timing_unit(
    tag: str,
    cpu: str,
    item: dict[str, Any],
    variant: str,
    control_source: Path,
    label: str,
    warmup: int,
    steady: int,
    *,
    collect_stationarity: bool,
) -> tuple[dict[str, Any], str, str]:
    """One timed unit: a fresh JVM in a fresh container, pinned to one CPU with networking off,
    running the reused DIST006-D driver. Returns the unit record and its stdout/stderr text."""
    if variant == "canonical":
        source_container = f"{CORPUS_DIR}/{item['source']}"
        volume = None
    else:
        source_container = CONTROL_SOURCE_MOUNT
        volume = (control_source, CONTROL_SOURCE_MOUNT)
    completed = dist006d.docker_entrypoint(
        cpu,
        tag,
        "java",
        *driver_java_args("timing", source_container, item["expected"], str(warmup), str(steady)),
        volume=volume,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    lines = [line for line in stdout.splitlines() if line.strip()]
    require(bool(lines), f"PERF016_TIMING_OUTPUT_EMPTY: {label}")
    payload = json.loads(lines[-1])
    validate_timing_payload(payload, item["expected"], warmup, steady, label)
    steady_ns = [int(value) for value in payload["steady_ns"]]
    unit = {
        "raw": payload,
        "steady_summary": dist006d.summarize_ns(steady_ns),
        "stationarity": stationarity_diagnostics(steady_ns) if collect_stationarity else None,
        "returncode": completed.returncode,
        "stdout_log": f"{label}.stdout.log",
        "stderr_log": f"{label}.stderr.log",
        "stdout_sha256": sha256_text(stdout),
        "stderr_sha256": sha256_text(stderr),
    }
    return unit, stdout, stderr


def run_blocks(
    cfg: dict[str, Any],
    admission: dict[str, Any],
    cpu: str,
    control_sources: dict[str, dict[str, Path]],
    block_order: tuple[str, ...],
    warmup: int,
    steady: int,
    *,
    collect_stationarity: bool,
    show_timing: bool,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The counterbalanced block matrix. Within a block, each workload times its roles in the
    block's role order and, within a role, the canonical variant then its workload-control variant.
    Returns the block records and every unit's stdout/stderr log text."""
    tags = {role: admission["builds"][role]["tag"] for role in ROLES}
    total = len(block_order) * len(cfg["workloads"]) * len(ROLES) * len(VARIANTS)
    done = 0
    blocks: list[dict[str, Any]] = []
    logs: dict[str, str] = {}
    for block_index, block_label in enumerate(block_order):
        sequence = block_role_order(block_label)
        for item in cfg["workloads"]:
            slug = item["id"].replace("/", "__")
            by_role: dict[str, Any] = {}
            for role in sequence:
                by_variant: dict[str, Any] = {}
                for variant in VARIANTS:
                    label = f"block{block_index}-{block_label}-{slug}-{role}-{variant}"
                    done += 1
                    print(
                        f"PERF016 TIMING BEGIN unit={done}/{total} label={label} warmup={warmup} "
                        f"steady={steady}",
                        flush=True,
                    )
                    unit, stdout, stderr = timing_unit(
                        tags[role],
                        cpu,
                        item,
                        variant,
                        control_sources[role][item["id"]],
                        label,
                        warmup,
                        steady,
                        collect_stationarity=collect_stationarity,
                    )
                    logs[unit["stdout_log"]] = stdout
                    logs[unit["stderr_log"]] = stderr
                    detail = (
                        f" median_ns={unit['steady_summary']['median_ns']}" if show_timing else ""
                    )
                    print(f"PERF016 TIMING PASS unit={done}/{total} label={label}{detail}", flush=True)
                    by_variant[variant] = unit
                by_role[role] = by_variant
            blocks.append(
                {
                    "block_index": block_index,
                    "block_order": block_label,
                    "workload": item["id"],
                    "role_sequence": list(sequence),
                    "roles": by_role,
                }
            )
    return blocks, logs


# --- host identity and evidence output ---


def cpu_model() -> str:
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return ""


def allowed_cpus() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("cannot determine current allowed CPU set")


def host_identity() -> dict[str, Any]:
    return {**dist006d.host_identity(), "cpu_model": cpu_model()}


def cpu_policy(cpu: str) -> dict[str, str]:
    return {"mechanism": "cpuset-cpus", "cpuset": cpu, "allowed_cpus": allowed_cpus()}


def require_unpopulated_output(path: Path) -> None:
    if path.exists():
        require(
            path.is_dir() and not any(path.iterdir()),
            f"PERF016_OUTPUT_ALREADY_POPULATED: {path} already contains evidence; retained "
            "evidence is never overwritten",
        )


def require_harness_unchanged(harness: str) -> None:
    head = dist006d.output(["git", "rev-parse", "HEAD"])
    require(
        head == harness,
        f"PERF016_HARNESS_CHANGED_DURING_RUN: HEAD moved from {harness} to {head}",
    )
    require(
        not dist006d.output(["git", "status", "--porcelain", "--untracked-files=all"]),
        "PERF016_HARNESS_CHANGED_DURING_RUN: the harness worktree became dirty during the run",
    )


def write_evidence(out: Path, raw: dict[str, Any], logs: dict[str, str]) -> None:
    """Write the whole evidence directory in a scratch location under the ignored .work/ tree and
    move it into place only once complete, so a failed run never leaves partial retained evidence."""
    scratch = ROOT / ".work"
    scratch.mkdir(exist_ok=True)
    staging = scratch / f"perf016-post-step3-evidence-{os.getpid()}"
    staging.mkdir()
    (staging / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Everything derived is rendered from the raw.json just written, never from in-memory state.
    retained = json.loads((staging / "raw.json").read_text(encoding="utf-8"))
    verify_raw(retained)
    for name, text in render_derived_views(retained).items():
        (staging / name).write_text(text, encoding="utf-8")
    logs_dir = staging / "logs"
    logs_dir.mkdir()
    for name, text in sorted(logs.items()):
        (logs_dir / name).write_text(text, encoding="utf-8")
    dist006d.write_manifest(staging)

    require_unpopulated_output(out)
    if out.exists():
        out.rmdir()
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staging), str(out))


# --- stages ---


def smoke() -> None:
    cfg = validate()
    cpu = dist006d.first_cpu()
    harness = dist006d.worktree_harness_state()
    admission = admit_products(cfg, cpu)

    with tempfile.TemporaryDirectory(prefix="perf016-post-step3-smoke-") as tmp:
        control_sources = write_control_sources(admission["workload_control_bytes"], Path(tmp))
        correctness = correctness_gate(cfg, admission, cpu, control_sources)
        blocks, _logs = run_blocks(
            cfg,
            admission,
            cpu,
            control_sources,
            tuple(cfg["smoke"]["block_order"]),
            cfg["smoke"]["warmup_iterations"],
            cfg["smoke"]["steady_iterations"],
            collect_stationarity=False,
            show_timing=False,
        )

    builds = admission["builds"]
    identity = {
        "harness": harness,
        "control": {
            "revision": cfg["control"]["revision"],
            "version": cfg["control"]["version"],
            "image_id": builds["control"]["built_image_identity"]["id"],
        },
        "intervention": {
            "revision": cfg["intervention"]["revision"],
            "version": cfg["intervention"]["version"],
            "image_id": builds["intervention"]["built_image_identity"]["id"],
        },
        "base_image_identity": builds["control"]["base_image_identity"],
        "cpu_policy": cpu_policy(cpu),
        "network": cfg["network"],
        "runtime": builds["control"]["runtime"],
        "workload_source_sha256": admission["workload_source_sha256"],
        "correctness_cases": len(correctness["cases"]),
        "smoke_timed_units": len(blocks) * len(ROLES) * len(VARIANTS),
        "retained_performance_evidence": False,
        "timing_evidence": False,
        "reference_evidence": False,
    }
    print("PERF016_SMOKE_IDENTITY=" + json.dumps(identity, sort_keys=True))
    print("SOURCE_IDENTITY_GATE=PASS")
    print("PERF016_POST_STEP3_SMOKE_CORRECTNESS=PASS")
    print(
        f"PERF016_POST_STEP3_SMOKE_SCALE=warmup={cfg['smoke']['warmup_iterations']} "
        f"steady={cfg['smoke']['steady_iterations']} (reference scale: "
        f"warmup={cfg['warmup_iterations']} steady={cfg['steady_iterations']})"
    )
    print("SMOKE_RETAINED_TIMING_EVIDENCE=NO")
    print("TIMING_EVIDENCE=NO")
    print("REFERENCE_EVIDENCE=NO")
    print("PERF016_POST_STEP3_SMOKE=PASS")


def reference(harness_revision: str | None) -> None:
    cfg = validate()
    harness = dist006d.exact_published_harness_revision(harness_revision)
    out = ROOT / cfg["reference"]["output"]
    require_unpopulated_output(out)

    cpu = dist006d.first_cpu()
    host = host_identity()
    policy = cpu_policy(cpu)
    admission = admit_products(cfg, cpu)

    with tempfile.TemporaryDirectory(prefix="perf016-post-step3-reference-") as tmp:
        control_sources = write_control_sources(admission["workload_control_bytes"], Path(tmp))
        correctness = correctness_gate(cfg, admission, cpu, control_sources)
        blocks, logs = run_blocks(
            cfg,
            admission,
            cpu,
            control_sources,
            tuple(cfg["block_order"]),
            cfg["warmup_iterations"],
            cfg["steady_iterations"],
            collect_stationarity=True,
            show_timing=True,
        )

    raw = build_raw(
        cfg,
        harness_revision=harness,
        host=host,
        cpu_policy=policy,
        admission=admission,
        correctness=correctness,
        blocks=blocks,
    )
    require_unclassified(raw)
    require_harness_unchanged(harness)
    write_evidence(out, raw, logs)

    print("PERF016_POST_STEP3_REFERENCE=PASS")
    print("PERF016_POST_STEP3_EVIDENCE_STATUS=RETAINED")
    print("PERF016_POST_STEP3_OUTPUT=" + cfg["reference"]["output"])
    print("HARNESS_REVISION=" + harness)
    print("CONTROL_REVISION=" + cfg["control"]["revision"])
    print("CONTROL_VERSION=" + cfg["control"]["version"])
    print("INTERVENTION_REVISION=" + cfg["intervention"]["revision"])
    print("INTERVENTION_VERSION=" + cfg["intervention"]["version"])
    print("TOOLCHAIN=" + cfg["toolchain"]["graalvm"]["release"])
    print("CPU_AFFINITY=" + cpu)
    print("COUNTERBALANCE=" + ",".join(cfg["block_order"]))
    print("WORKLOAD_SOURCE_IDENTITY=PASS")
    print("CORRECTNESS=PASS")
    for workload in raw["workload_ids"]:
        views = raw["per_workload_summary"][workload]["views"]
        print(
            f"WORKLOAD={workload} "
            "SHARED_DRIVER_EFFECT_MEDIAN_PERCENT="
            f"{fmt_pct(views['control_variant_effect']['percent']['median'])} "
            "CANONICAL_EFFECT_MEDIAN_PERCENT="
            f"{fmt_pct(views['canonical_effect']['percent']['median'])} "
            "PAIRED_CONTROL_EFFECT_MEDIAN_PERCENT="
            f"{fmt_pct(views['paired_control_effect']['percent']['median'])}"
        )
    print(
        "ORDER_EFFECT_BY_WORKLOAD="
        + json.dumps(
            {
                workload: {
                    view: raw["per_workload_summary"][workload]["views"][view]["order_effect"]
                    for view in VIEWS
                }
                for workload in raw["workload_ids"]
            },
            sort_keys=True,
        )
    )
    print(
        "STATIONARITY_MAX_ABS_LAST_VS_FIRST_QUARTER_PERCENT="
        + fmt_pct(
            max(
                abs(unit["last_quarter_vs_first_quarter_percent"])
                for unit in raw["per_timed_unit_stationarity"]
            )
        )
    )
    print("STEP_3_TIMING_CLASS=" + raw["STEP_3_TIMING_CLASS"])
    print("STEP3_NEXT_ROUTING=" + raw["STEP3_NEXT_ROUTING"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("validate", "smoke", "reference"))
    parser.add_argument(
        "--harness-revision",
        help="reference only: the exact 40-lowercase-hex published harness SHA",
    )
    args = parser.parse_args()

    if args.command != "reference" and args.harness_revision is not None:
        parser.error("--harness-revision is only accepted by the reference command")

    if args.command == "validate":
        validate()
    elif args.command == "smoke":
        smoke()
    else:
        reference(args.harness_revision)


if __name__ == "__main__":
    main()
