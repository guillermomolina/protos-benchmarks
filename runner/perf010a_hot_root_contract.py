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

"""Static contract of the PERF010-A hot-root lifecycle / compiled-shape harness (no Docker).

Everything `make perf010a-hot-root-validate` proves lives here: the configuration is fail-closed
against the pinned product, toolchain, workload matrix and boundaries; the reused DIST006-D and
historical source-identity infrastructure are the ones this harness was written for; the overlay
Dockerfile and the Java diagnostics have the exact structure the design requires and no product
patch; and the parser, identity, correlation, manifest and shape logic behave as specified on
synthetic fixtures (runner/perf010a_hot_root_fixtures.py), so no expensive compiler run is needed to
prove a parser branch. It never selects a causal class: that is a later interpretation of a real
measurement.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import re
import tempfile
from typing import Any
import importlib.util
import sys


def _sibling(name: str) -> Any:
    key = "pb_" + name
    module = sys.modules.get(key)
    if module is not None:
        return module
    path = Path(__file__).resolve().with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load sibling runner module: " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


exact_product = _sibling("exact_product")
trace = _sibling("compiler_trace")
lifecycle_mod = _sibling("compiler_lifecycle")
identity = _sibling("perf010a_hot_root_identity")
shape = _sibling("perf010a_hot_root_shape")
fixtures = _sibling("perf010a_hot_root_fixtures")

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf010a-hot-root-lifecycle.json"
DIST006D_RUNNER = ROOT / "runner/dist006d_baseline.py"
HOT_ROOT_DIR = ROOT / "docker/protos-perf010a-hot-root"
OVERLAY_DOCKERFILE = HOT_ROOT_DIR / "Dockerfile"
INSTRUMENT_JAVA = HOT_ROOT_DIR / "Perf010aHotRootIdentityInstrument.java"
PROVIDER_JAVA = HOT_ROOT_DIR / "Perf010aHotRootIdentityInstrumentProvider.java"
DRIVER_JAVA = HOT_ROOT_DIR / "Perf010aHotRootDriver.java"
SERVICES_FILE = HOT_ROOT_DIR / "META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider"
DIST006D_DRIVER_JAVA = ROOT / "docker/protos-dist006d/Dist006dDriver.java"
MAKEFILE = ROOT / "Makefile"
SCANNED_MODULES = (
    "compiler_lifecycle.py",
    "perf010a_hot_root_identity.py",
    "perf010a_hot_root_shape.py",
    "perf010a_hot_root_contract.py",
    "perf010a_hot_root.py",
)

EXPECTED_WORK_ITEM = "PERF010-A"
EXPECTED_ISSUE = "guillermomolina/protos#691"
EXPECTED_PARENT_WORK_ITEM = "PERF010"
EXPECTED_PARENT_ISSUE = "guillermomolina/protos#680"
EXPECTED_SLICE = "CURRENT_25_4_HOT_ROOT_LIFECYCLE_AND_COMPILED_SHAPE_HARNESS"
PROTOS_REPOSITORY = "https://github.com/guillermomolina/protos.git"
EXPECTED_PROTOS_REVISION = "b72778ca446b602f33af5027a0ed28ab788b39ce"
EXPECTED_PROTOS_VERSION = "0.3.119-SNAPSHOT"
EXPECTED_GRAALVM_RELEASE = "25.4.4.1.1"
EXPECTED_JDK_VERSION = "25.0.4.1.1"
EXPECTED_JVMCI = "25.4-b23"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_WORKLOAD_IDS = ("micro/closure-call", "micro/method-call", "runtime/monomorphic-dispatch")
VARIANTS = ("canonical", "workload_control")
RUN_KINDS = ("lifecycle", "graph")
REQUIRED_PHASES = ("startup", "warmup", "steady", "closing", "end")
BASE_ROLE_IDS = ("repeat", "control_block", "callback")
WORKLOAD_ROLE_ID = {
    "micro/closure-call": "closure_call",
    "micro/method-call": "method_call",
    "runtime/monomorphic-dispatch": "monomorphic_dispatch",
}
FAMILY_IDS = (
    "activation_creation",
    "execution_context_materialization",
    "argument_transport",
    "return_home_control_state",
    "captured_environment",
    "semantic_wrapper_to_helper",
    "generic_selection_classification",
    "context_local_plan_cache",
    "host_map_optional_string",
    "bytecode_continuation",
)
LIFECYCLE_OPTION_NAMES = (
    "polyglot.engine.TraceCompilation",
    "polyglot.engine.TraceCompilationDetails",
    "polyglot.engine.CompilationFailureAction",
    "polyglot.engine.TraceAssumptions",
    "polyglot.engine.TraceCompilationPolymorphism",
    "polyglot.engine.TraceInlining",
    "polyglot.engine.TraceInliningDetails",
    "polyglot.engine.TracePerformanceWarnings",
    "polyglot.engine.NodeSourcePositions",
    "polyglot.perf010aHotRootIdentity",
)
GRAPH_OPTION_NAMES = ("jdk.graal.Dump", "jdk.graal.DumpPath", "jdk.graal.PrintGraph", "jdk.graal.ShowDumpFiles")
TUNING_OPTION_SEGMENTS = frozenset(
    {
        "InliningExpansionBudget",
        "InliningInliningBudget",
        "InliningRecursionDepth",
        "BackgroundCompilation",
        "Compilation",
        "Mode",
        "CompileImmediately",
        "FirstTierCompilationThreshold",
        "LastTierCompilationThreshold",
        "SingleTierCompilationThreshold",
        "MultiTier",
        "OSR",
    }
)
REQUIRED_BOUNDARIES = {
    "product_patch": False,
    "product_repository_mutation": False,
    "semantic_change": False,
    "perf020_implemented": False,
    "authoritative_discriminator_executed": False,
    "timing_evidence": False,
    "normal_vs_compilation_false_required": False,
    "causal_class_in_harness": "NOT_CLASSIFIED",
    "product_intervention_selected": False,
    "control_revision": "NOT_YET_SELECTABLE",
    "control_version": "NOT_YET_SELECTABLE",
    "perf011_reactivate_after_this_slice": False,
    "perf010_b_reopened": False,
    "perf010_b_step4_authorized": False,
    "historical_evidence_mutation": False,
}
SHA1_RE = re.compile(r"[0-9a-f]{40}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load(path: Path = CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_dist006d() -> Any:
    return exact_product.load_module("dist006d_baseline", DIST006D_RUNNER)


# --- units and artifact layout -------------------------------------------------------------------


def units(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """The required workload matrix as deterministic units: workload x variant."""
    out = []
    for workload in cfg["workloads"]:
        for variant in cfg["variants"]:
            out.append(
                {
                    "id": f"{workload['id']}#{variant}",
                    "workload": workload["id"],
                    "variant": variant,
                    "slug": workload["id"].replace("/", "__") + "." + variant,
                    "source": workload["source"],
                    "source_name": Path(workload["source"]).name,
                    "expected": workload["expected"],
                }
            )
    return out


def unit_dump_dir(dump_root: Path, run_id: str, unit: dict[str, Any], kind: str) -> Path:
    """Deterministic, isolated, per-unit and per-run-kind dump directory: no two JVMs ever share a
    writable output directory."""
    return dump_root / run_id / unit["slug"] / kind


def unit_evidence_dir(out_dir: Path, unit: dict[str, Any]) -> Path:
    return out_dir / "units" / unit["slug"]


# --- configuration -------------------------------------------------------------------------------


def validate_options(options: list[dict[str, Any]], required: tuple[str, ...], label: str) -> None:
    names = [option["name"] for option in options]
    require(len(names) == len(set(names)), f"{label}: duplicate option names")
    for name in required:
        require(name in names, f"{label}: missing required diagnostic option {name}")
    for option in options:
        require(
            all(isinstance(option.get(k), str) and option[k] for k in ("name", "value", "purpose")),
            f"{label}: option needs name, value and purpose",
        )
        require(
            option["name"].rsplit(".", 1)[-1] not in TUNING_OPTION_SEGMENTS,
            f"{label}: {option['name']} is a tuning option; the diagnostic must not change compilation policy",
        )


def validate_config_payload(cfg: dict[str, Any], dist006d: Any | None = None) -> dict[str, Any]:
    dist006d = dist006d or load_dist006d()
    base = dist006d.load()
    require(cfg.get("schema_version") == 1, "unsupported config schema")
    for key, expected in (
        ("work_item", EXPECTED_WORK_ITEM),
        ("issue", EXPECTED_ISSUE),
        ("parent_work_item", EXPECTED_PARENT_WORK_ITEM),
        ("parent_issue", EXPECTED_PARENT_ISSUE),
        ("slice", EXPECTED_SLICE),
        ("type", "IMPLEMENTATION"),
    ):
        require(cfg.get(key) == expected, f"{key} authority mismatch")
    require(cfg.get("timing_evidence") is False, "this harness must not produce timing evidence")

    protos = cfg.get("protos", {})
    require(protos.get("repository") == PROTOS_REPOSITORY, "unexpected Protos repository")
    require(
        protos.get("revision") == EXPECTED_PROTOS_REVISION and SHA1_RE.fullmatch(str(protos.get("revision"))),
        "PRODUCT_REVISION_PIN_MISMATCH: the exact product revision is pinned, not floating",
    )
    require(protos.get("version") == EXPECTED_PROTOS_VERSION, "PRODUCT_VERSION_PIN_MISMATCH")
    require(protos.get("floating_branch_forbidden") is True, "floating product revision must be forbidden")
    require(protos.get("product_patch") is False, "a product patch is not allowed")

    toolchain = cfg.get("toolchain", {})
    require(toolchain == base["toolchain"], "TOOLCHAIN_FORKED: the toolchain block must equal the DIST006-D one")
    dist006d.validate_toolchain_contract({k: toolchain.get(k) for k in ("schema", "java", "graalvm", "graal_components", "maven", "policy")})
    require(toolchain.get("jvmci") == EXPECTED_JVMCI, "JVMCI identity mismatch")
    require(toolchain.get("expected_runtime") == EXPECTED_RUNTIME, "optimizing runtime identity mismatch")
    require(toolchain["graalvm"]["release"] == EXPECTED_GRAALVM_RELEASE, "GraalVM release mismatch")
    require(toolchain["graalvm"]["jdk_version"] == EXPECTED_JDK_VERSION, "JDK version mismatch")

    workloads = cfg.get("workloads", [])
    require(tuple(w.get("id") for w in workloads) == EXPECTED_WORKLOAD_IDS, "REQUIRED_WORKLOAD_MATRIX: exact three-workload set required")
    require(tuple(cfg.get("variants", ())) == VARIANTS, "REQUIRED_WORKLOAD_MATRIX: canonical and workload_control variants required")
    base_by_id = {w["id"]: w for w in base["workloads"]}
    for workload in workloads:
        origin = base_by_id[workload["id"]]
        require(workload["source"] == origin["source"], f"{workload['id']}: source differs from DIST006-D")
        require(workload["target_text"] == origin["replace"] and workload["control_text"] == origin["with"], f"{workload['id']}: target/control text differs from DIST006-D")
        require(workload["expected"] == "42", "every workload result must be 42")
        role_ids = [r["id"] for r in workload["roles"]]
        require(len(role_ids) == len(set(role_ids)), f"{workload['id']}: duplicate role ids")
        for needed in (*BASE_ROLE_IDS, WORKLOAD_ROLE_ID[workload["id"]]):
            require(needed in role_ids, f"{workload['id']}: role {needed} missing")
        for role in workload["roles"]:
            require(role["match"] in ("equals", "contains"), "unknown role match mode")
            require(set(role["variants"]) <= set(VARIANTS) and role["variants"], "role variants invalid")
            for variant in role["variants"]:
                require(bool(identity.role_anchor(role, variant)), f"{workload['id']}: role {role['id']} has no anchor for {variant}")
    require(set(cfg.get("root_kind_markers", {})) == {"semantic", "helper"}, "root kind markers missing")

    diagnostic = cfg.get("diagnostic", {})
    require(all(isinstance(diagnostic.get(k), int) and diagnostic[k] >= 0 for k in ("operation_count", "warmup_iterations", "steady_iterations")), "iteration policy invalid")
    require(diagnostic["operation_count"] == 10000, "operation count drift")
    smoke = diagnostic.get("smoke", {})
    require(smoke.get("retained_evidence") is False and smoke.get("timing_evidence") is False, "smoke must not retain evidence")
    require(all(u in [f"{w}#{v}" for w in EXPECTED_WORKLOAD_IDS for v in VARIANTS] for u in smoke.get("units", [])) and smoke.get("units"), "smoke units invalid")
    require(diagnostic.get("tier_model") == {"first_tier": 1, "final_tier": 2}, "tier model drift")
    require(tuple(diagnostic.get("required_phase_sequence", ())) == REQUIRED_PHASES, "phase sequence drift")
    require(tuple(diagnostic.get("run_kinds", {})) == RUN_KINDS, "run kinds drift")
    require(diagnostic.get("network") == "none", "networking must be disabled")
    require(diagnostic.get("no_tuning_option_is_set") is True, "no tuning option may be set")
    require(
        diagnostic.get("engine_builder_allow_experimental_options") is True,
        "experimental diagnostic options must be admitted by Engine.Builder",
    )
    lifecycle_options = diagnostic["run_kinds"]["lifecycle"]["options"]
    graph_kind = diagnostic["run_kinds"]["graph"]
    validate_options(lifecycle_options, LIFECYCLE_OPTION_NAMES, "lifecycle")
    validate_options(graph_kind["options"], GRAPH_OPTION_NAMES, "graph")
    require(graph_kind.get("extends") == "lifecycle", "the graph run must keep the lifecycle options for CompId correlation")
    require(diagnostic["optional_channels"]["expansion"]["enabled"] is False, "expansion channel is off until admitted")

    for pattern in cfg.get("lifecycle", {}).get("replacement_reason_patterns", []):
        re.compile(pattern)
    families = cfg.get("shape", {}).get("families", [])
    require(tuple(f.get("id") for f in families) == FAMILY_IDS, "candidate family set drift")
    require(all(f.get("markers") and f.get("description") for f in families), "family markers missing")
    require(cfg["shape"]["facts_schema"] == shape.FACTS_SCHEMA and cfg["shape"]["other_family"]["id"], "shape schema drift")

    require(cfg.get("boundaries") == REQUIRED_BOUNDARIES, "BOUNDARIES: a non-goal flag drifted")
    require(cfg.get("causal_classes") == {"A": "COMPILATION_FAILURE", "B": "COMPILATION_LIFECYCLE_INSTABILITY", "C": "COMPILED_BUT_EXPENSIVE_SURVIVING_MACHINERY", "D": "MATURE_COMPILED_FORM_WITH_RESIDUAL_SEMANTIC_COST"}, "causal class definitions drift")
    require(cfg["retention"]["requires_exact_clean_published_harness_revision"] is True, "diagnostic must require the exact clean published harness")

    reuse = cfg["reused_infrastructure"]["source_identity_mechanism"]
    require(reuse["reused_unchanged"] is True and reuse["stale_25_3_docker_contract_reused"] is False, "reuse contract drift")
    for rel, digest in reuse["files"].items():
        path = ROOT / rel
        require(path.is_file(), f"reused source-identity file missing: {rel}")
        require(exact_product.sha256_file(path) == digest, f"HISTORICAL_MECHANISM_CHANGED: {rel} no longer matches its pinned SHA-256")
    return cfg


def validate_reused_infrastructure(cfg: dict[str, Any], dist006d: Any) -> None:
    for name in ("build_and_probe", "image_identity", "image_revision_label", "require_exact_sha", "first_cpu", "host_identity", "validate", "validate_toolchain_contract", "load", "driver_correctness", "exact_published_harness_revision", "worktree_harness_state", "prepare_output"):
        require(hasattr(dist006d, name), f"REUSED_INFRASTRUCTURE_MISSING: DIST006-D lacks {name}")
    require(dist006d.EXPECTED_CONTAINER_IMAGE == cfg["toolchain"]["graalvm"]["container_image"], "TOOLCHAIN_GENERATION_MISMATCH")
    require(dist006d.EXPECTED_ENGINE_VERSION == EXPECTED_GRAALVM_RELEASE and dist006d.EXPECTED_JDK_VERSION == EXPECTED_JDK_VERSION, "TOOLCHAIN_GENERATION_MISMATCH")
    require(dist006d.EXPECTED_JVMCI == EXPECTED_JVMCI and dist006d.EXPECTED_RUNTIME == EXPECTED_RUNTIME, "TOOLCHAIN_GENERATION_MISMATCH")
    with contextlib.redirect_stdout(io.StringIO()):
        dist006d.validate()
    for rel in ("dockerfile", "driver", "runtime_probe"):
        require((ROOT / cfg["reused_infrastructure"][rel]).is_file(), "reused DIST006-D file missing: " + rel)


# --- static structure of the overlay image and the Java diagnostics ---------------------------------


def validate_overlay_dockerfile(text: str) -> None:
    for label, marker in {
        "overlay base argument": "ARG BASE_IMAGE",
        "overlay FROM the admitted DIST006-D image": "FROM ${BASE_IMAGE}",
        "JDK identity assertion": 'grep -Fq "java.version = ${EXPECTED_JDK_VERSION}"',
        "GraalVM vendor assertion": 'grep -Fq "java.vm.vendor = GraalVM Community"',
        "pinned javac feature assertion": 'JAVAC_FEATURE="${EXPECTED_JDK_VERSION%%.*}"',
        "compilation by the pinned JDK javac": '"$JAVA_HOME/bin/javac" -cp',
        "product jars on the compile classpath": "/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "historical instrument reused": "COPY docker/protos-perf010a/Perf010aSourceIdentityInstrument.java",
        "historical provider reused": "COPY docker/protos-perf010a/Perf010aSourceIdentityInstrumentProvider.java",
        "historical smoke driver reused": "COPY docker/protos-perf010a/Perf010aSourceIdentitySmokeDriver.java",
        "root instrument": "COPY docker/protos-perf010a-hot-root/Perf010aHotRootIdentityInstrument.java",
        "root instrument provider": "COPY docker/protos-perf010a-hot-root/Perf010aHotRootIdentityInstrumentProvider.java",
        "driver": "COPY docker/protos-perf010a-hot-root/Perf010aHotRootDriver.java",
        "service registration": "META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider",
        "harness source hash evidence": "harness-sources.sha256",
    }.items():
        require(marker in text, f"overlay Dockerfile structural contract missing {label}: {marker}")
    for forbidden in ("git apply", "patch ", ".patch", "microdnf", "git clone", "git fetch", "apply_toolchain_overlay", "25i3", "25.3", "ubuntu", "eclipse-temurin", "python39", "EXPECTED_MAVEN_VERSION", "sed -i"):
        require(forbidden not in text, f"NO_PRODUCT_PATCH: overlay Dockerfile contains forbidden {forbidden!r}")


def _imports(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if line.startswith("import com.guillermomolina.protos")}


def validate_java_sources() -> None:
    instrument = INSTRUMENT_JAVA.read_text(encoding="utf-8")
    provider = PROVIDER_JAVA.read_text(encoding="utf-8")
    driver = DRIVER_JAVA.read_text(encoding="utf-8")
    for marker in ("attachLoadSourceSectionListener", "SourceSectionFilter", "extends TruffleInstrument", "OptionStability.STABLE", "Perf010aHotRootIdentityInstrument.ID", '"perf010aHotRootIdentity"'):
        require(marker in instrument, f"root instrument lacks {marker}")
    require("OptionStability.EXPERIMENTAL" not in instrument, "the instrument option must be STABLE")
    for word in ("CompilationThreshold", "TieredCompilation", "OSR", "Inlining", "CompileImmediately", "BackgroundCompilation"):
        require(word not in instrument, f"NO_PRODUCT_PATCH: the instrument must not reference compilation policy ({word})")
    for text, label in ((instrument, "instrument"), (provider, "provider")):
        require("import com.guillermomolina.protos" not in text, f"{label} must use public Truffle API only")
    require("extends TruffleInstrumentProvider" in provider and "implements TruffleInstrumentProvider" not in provider, "provider must extend the abstract class")
    require("@TruffleInstrument.Registration(" in provider and "Perf010aHotRootIdentityInstrument.ID" in provider, "the Registration annotation must sit on the provider")
    services = [line.strip() for line in SERVICES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(services == ["Perf010aSourceIdentityInstrumentProvider", "Perf010aHotRootIdentityInstrumentProvider"], "service registration drift")
    for marker in ("processContext.execute(", "requireCompletedInteger", "PERF010A_HOTROOT_MARK phase=", 'mark("startup")', 'mark("warmup")', 'mark("steady")', 'mark("closing")', 'mark("end")', "perf010a-hot-root-identity-v1"):
        require(marker in driver, f"driver lacks {marker}")
    require("nanoTime" not in driver and "currentTimeMillis" not in driver, "the diagnostic driver must not time anything")
    extra = _imports(driver) - _imports(DIST006D_DRIVER_JAVA.read_text(encoding="utf-8"))
    require(not extra, f"NO_OBSERVABLE_PROTOS_SEMANTIC_CHANGE: driver uses Protos API beyond the DIST006-D driver: {sorted(extra)}")
    require(not list(HOT_ROOT_DIR.rglob("*.patch")), "NO_PRODUCT_PATCH: no patch file may exist in the harness image directory")


def validate_no_hard_coded_root_numbers(cfg: dict[str, Any]) -> None:
    pair = re.compile("(?:" + "engine" + r"=\d|\b" + "id" + r"=\d)")
    for name in SCANNED_MODULES:
        text = (ROOT / "runner" / name).read_text(encoding="utf-8")
        require(pair.search(text) is None, f"NO_HARD_CODED_ROOT_NUMBERS: {name} contains a literal compiler id")
    config_text = json.dumps(cfg)
    require(re.search(r'"(?:root_?id|comp_?id|compilable_?id|engine)"\s*:\s*\d', config_text) is None, "NO_HARD_CODED_ROOT_NUMBERS: config contains a numeric root selector")
    require("perf020" not in "".join(p.name for p in HOT_ROOT_DIR.iterdir()).lower(), "PERF020 must not be implemented here")


def validate_makefile() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    for target in ("perf010a-hot-root-validate:", "perf010a-hot-root-smoke:", "perf010a-hot-root-diagnostic:"):
        require(target in text, "missing Makefile target: " + target[:-1])


# --- product identity, verified independently of the shared admission helper ------------------------


def verify_admitted_build(cfg: dict[str, Any], build: dict[str, Any]) -> None:
    """Second, independent check of an admitted build record against every pin. `build` carries
    `revision_label`, `source_head`, `product_version`, `toolchain` and `runtime`."""
    protos = cfg["protos"]
    require(build.get("revision_label") == protos["revision"], f"PRODUCT_REVISION_MISMATCH: image label {build.get('revision_label')!r}")
    require(build.get("source_head") == protos["revision"], f"PRODUCT_REVISION_MISMATCH: source head {build.get('source_head')!r}")
    require(build.get("product_version") == protos["version"], f"PRODUCT_VERSION_MISMATCH: {build.get('product_version')!r}")
    observed_toolchain = build.get("toolchain")
    require(
        isinstance(observed_toolchain, dict),
        "TOOLCHAIN_MISMATCH: admitted build lacks toolchain.json",
    )
    try:
        load_dist006d().validate_toolchain_contract(
            observed_toolchain
        )
    except RuntimeError as error:
        raise RuntimeError(
            "TOOLCHAIN_MISMATCH: " + str(error)
        ) from error
    runtime = build.get("runtime", {})
    require(runtime.get("runtime_class") == EXPECTED_RUNTIME, f"RUNTIME_IDENTITY_MISMATCH: {runtime.get('runtime_class')!r}")
    require(runtime.get("engine_version") == EXPECTED_GRAALVM_RELEASE, f"RUNTIME_IDENTITY_MISMATCH: engine {runtime.get('engine_version')!r}")
    require(runtime.get("java_version") == EXPECTED_JDK_VERSION, f"RUNTIME_IDENTITY_MISMATCH: JDK {runtime.get('java_version')!r}")
    exact_product.require_jvmci(runtime, cfg["toolchain"]["jvmci"], "admitted build")


# --- synthetic self-tests (no Docker, no compiler) -------------------------------------------------


def expect_error(action: Any, label: str) -> None:
    try:
        action()
    except RuntimeError:
        return
    raise RuntimeError(f"SELF_TEST_FAILED: {label} was accepted but must fail closed")


def normalize(cfg: dict[str, Any], text: str, *, completed: bool = True) -> tuple[list[Any], dict[str, Any]]:
    diagnostic = cfg["diagnostic"]
    records = trace.split_records(text)
    result = lifecycle_mod.normalize_lifecycle(
        records,
        first_tier=diagnostic["tier_model"]["first_tier"],
        final_tier=diagnostic["tier_model"]["final_tier"],
        replacement_patterns=cfg["lifecycle"]["replacement_reason_patterns"],
        required_phases=tuple(diagnostic["required_phase_sequence"]),
        process_completed=completed,
    )
    return records, result


def root_by_label(result: dict[str, Any], label: str) -> dict[str, Any]:
    return result["roots"][result["label_index"][label][0]]


def check_expected(actual: dict[str, Any], expected: dict[str, Any], where: str) -> None:
    for key, value in expected.items():
        if key == "classes":
            for name, flag in value.items():
                require(actual["classes"][name] is flag, f"{where}: class {name} expected {flag}")
        else:
            require(actual[key] == value, f"{where}: {key} expected {value!r}, observed {actual[key]!r}")


SCENARIO_FLAGS = {
    "never_compiled": "LIFECYCLE_PARSER_NEVER_COMPILED",
    "first_tier_only": "LIFECYCLE_PARSER_FIRST_TIER_ONLY",
    "final_tier_done": "LIFECYCLE_PARSER_FINAL_TIER_DONE",
    "permanent_failure": "LIFECYCLE_PARSER_PERMANENT_FAILURE",
    "temporary_failure_retry": "LIFECYCLE_PARSER_TEMPORARY_FAILURE_RETRY",
    "invalidate": "LIFECYCLE_PARSER_INVALIDATE",
    "recompile_success": "LIFECYCLE_PARSER_RECOMPILE_SUCCESS",
    "generic_replacement": "LIFECYCLE_PARSER_GENERIC_REPLACEMENT",
    "stable_final_state": "LIFECYCLE_PARSER_STABLE_FINAL_STATE",
}


def self_test_lifecycle(cfg: dict[str, Any]) -> dict[str, str]:
    flags: dict[str, str] = {}
    for name, (body, expected) in fixtures.LIFECYCLE_SCENARIOS.items():
        text = fixtures.run(body)
        records, result = normalize(cfg, text)
        check_expected(root_by_label(result, fixtures.A), expected, name)
        require("\n".join(r.raw for r in records) + "\n" == text, f"{name}: record splitting is not lossless")
        lifecycle_records = [r.seq for r in records if r.kind in trace.LIFECYCLE_KINDS]
        events = [e["seq"] for root in result["roots"].values() for e in root["events"]]
        require(sorted(events) == lifecycle_records, f"LIFECYCLE_RAW_EVENTS_RETAINED: {name} dropped or invented events")
        for root in result["roots"].values():
            seqs = [e["seq"] for e in root["events"]]
            require(seqs == sorted(set(seqs)), f"LIFECYCLE_ORDER_PRESERVED: {name} reordered events")
        if name in SCENARIO_FLAGS:
            flags[SCENARIO_FLAGS[name]] = "PASS"
    storm = root_by_label(normalize(cfg, fixtures.run(fixtures.LIFECYCLE_SCENARIOS["invalidate"][0]))[1], fixtures.A)
    require(len(storm["invalidation_episodes"]) == 1 and storm["invalidation_episodes"][0]["frame_deopts"] == 5000, "a deopt storm must be one invalidation episode with every frame deopt counted")
    body = fixtures.LIFECYCLE_SCENARIOS["final_tier_done"][0]
    _, cut = normalize(cfg, fixtures.run(body, phases=fixtures.PHASES[:4]))
    require(root_by_label(cut, fixtures.A)["STABLE_FINAL_OPTIMIZED_STATE"] == "INCONCLUSIVE", "a run without proof of termination must never be STABLE=YES")
    _, killed = normalize(cfg, fixtures.run(body), completed=False)
    require(root_by_label(killed, fixtures.A)["STABLE_FINAL_OPTIMIZED_STATE"] == "INCONCLUSIVE", "a run whose process did not complete must never be STABLE=YES")
    flags["LIFECYCLE_RAW_EVENTS_RETAINED"] = "PASS"
    flags["LIFECYCLE_ORDER_PRESERVED"] = "PASS"
    return flags


def synthetic_inventory(cfg: dict[str, Any], workload: dict[str, Any], variant: str, *, seed: int, source_sha: str = "a" * 64) -> dict[str, Any]:
    """An inventory as the driver would write it, with run-local labels derived from `seed` only."""
    roots = []
    for index, role in enumerate([r for r in workload["roles"] if variant in r["variants"]]):
        anchor = identity.role_anchor(role, variant)
        start = 100 * (index + 1)
        section = {"startOffset": start, "endOffset": start + 60, "length": 60, "line": index + 2, "column": 1, "text": "closure " + role["id"]}
        node = {"section": {"startOffset": start + 5, "endOffset": start + 5 + len(anchor), "length": len(anchor), "line": index + 2, "column": 9, "text": anchor}, "nodeClassName": "com.oracle.truffle.api.bytecode.TagTreeNode"}
        for simple, nodes in (("ProtosBytecodeRootNodeGen", [node]), ("ProtosSemanticBytecodeRootNodeGen", [])):
            suffix = f"{seed:04x}{len(roots):04x}"
            roots.append({"rootNodeClassName": "com.guillermomolina.protos.execution." + simple, "simpleName": simple, "identityHash": suffix, "label": f"{simple}@{suffix}", "toString": f"{simple}@{suffix}", "rootSection": section, "nodes": nodes})
    return {"schema": identity.IDENTITY_SCHEMA, "source_name": Path(workload["source"]).name, "source_sha256": source_sha, "source_bytes": 1, "runtime_class": EXPECTED_RUNTIME, "roots": roots}


def self_test_identity(cfg: dict[str, Any]) -> dict[str, str]:
    markers = cfg["root_kind_markers"]
    durable: list[dict[str, Any]] = []
    labels: list[set[str]] = []
    for workload in cfg["workloads"]:
        for variant in VARIANTS:
            for seed in (1, 2):
                doc = synthetic_inventory(cfg, workload, variant, seed=seed)
                identity.validate_identity_document(doc, expected_source_name=Path(workload["source"]).name, expected_source_sha256="a" * 64)
                resolution = identity.resolve_roles(doc, workload["roles"], variant, markers)
                identity.require_roles_resolved(resolution)
                durable.append({role: sorted((m["kind"], m["identity"]["durableId"]) for m in e["members"]) for role, e in resolution["roles"].items()})
                labels.append({r["label"] for r in doc["roots"]})
    for first in range(0, len(durable), 2):
        require(durable[first] == durable[first + 1], "SOURCE_IDENTITY_STABLE_WITHOUT_ROOT_NUMBERS: durable identity changed with run-local labels")
        require(labels[first].isdisjoint(labels[first + 1]), "self-test inventories must differ in every run-local label")
    workload = cfg["workloads"][0]
    other = identity.resolve_roles(synthetic_inventory(cfg, workload, "canonical", seed=1, source_sha="b" * 64), workload["roles"], "canonical", markers)
    require(other["roles"]["callback"]["members"][0]["identity"]["durableId"] != durable[0]["callback"][0][1], "durable identity must depend on the source bytes")

    good = synthetic_inventory(cfg, workload, "canonical", seed=1)

    def resolve(doc: dict[str, Any]) -> None:
        identity.require_roles_resolved(identity.resolve_roles(doc, workload["roles"], "canonical", markers))

    missing = copy.deepcopy(good)
    missing["roots"][2]["nodes"][0]["section"]["text"] = "something else"
    expect_error(lambda: resolve(missing), "a role whose anchor text is not observed")
    ambiguous = copy.deepcopy(good)
    ambiguous["roots"].append(copy.deepcopy(good["roots"][2]))
    ambiguous["roots"][-1]["rootSection"] = dict(good["roots"][0]["rootSection"], startOffset=9000, endOffset=9060)
    ambiguous["roots"][-1]["label"] = "ProtosBytecodeRootNodeGen@9999"
    expect_error(lambda: resolve(ambiguous), "a role anchored in two root groups")
    unpaired = copy.deepcopy(good)
    unpaired["roots"] = [r for r in unpaired["roots"] if "Semantic" not in r["simpleName"]]
    expect_error(lambda: resolve(unpaired), "a role without its semantic member")
    expect_error(lambda: identity.validate_identity_document(good, expected_source_name="other.protos", expected_source_sha256="a" * 64), "an inventory of another source")
    expect_error(lambda: identity.validate_identity_document(dict(good, roots=[]), expected_source_name=good["source_name"], expected_source_sha256="a" * 64), "an empty inventory")
    return {"SOURCE_IDENTITY_STABLE_WITHOUT_ROOT_NUMBERS": "PASS"}


def self_test_correlation_and_shape(cfg: dict[str, Any]) -> dict[str, str]:
    workload = cfg["workloads"][0]
    role = next(r for r in workload["roles"] if r["id"] == "callback")
    anchor = identity.role_anchor(role, "canonical")
    section = {"startOffset": 10, "endOffset": 70, "length": 60, "line": 3, "column": 1, "text": "closure callback"}
    node = {"section": {"startOffset": 15, "endOffset": 15 + len(anchor), "length": len(anchor), "line": 3, "column": 9, "text": anchor}, "nodeClassName": "x.Node"}
    doc = {"schema": identity.IDENTITY_SCHEMA, "source_name": "s.protos", "source_sha256": "c" * 64, "source_bytes": 1, "runtime_class": EXPECTED_RUNTIME, "roots": []}
    for simple, name, nodes in (("ProtosBytecodeRootNodeGen", fixtures.A, [node]), ("ProtosSemanticBytecodeRootNodeGen", fixtures.B, [])):
        doc["roots"].append({"rootNodeClassName": "com.guillermomolina.protos.execution." + simple, "simpleName": simple, "identityHash": "0", "label": name, "toString": name, "rootSection": section, "nodes": nodes})
    resolution = identity.resolve_roles(doc, [role], "canonical", cfg["root_kind_markers"])
    identity.require_roles_resolved(resolution)

    def body(b: Any) -> None:
        for ident, name, comp in ((1, fixtures.A, 2585), (2, fixtures.B, 2586)):
            b.queued(ident, name).start(ident, name).done(ident, name, 1, comp).dump(comp, name)
            b.queued(ident, name, 2).start(ident, name, 2)
            if ident == 1:
                b.perf_warn(name, "Map.put(Object, Object)", ["java.util.HashMap.put(HashMap.java:619)", "com.guillermomolina.protos.runtime.ProtosObjectValue.createLocalSlot(ProtosObjectValue.java:208)"])
            b.done(ident, name, 2, comp + 100).dump(comp + 100, name)

    records, result = normalize(cfg, fixtures.run(body))
    rows = identity.correlate_roles(resolution, result)
    require(len(rows) == 2 and all(r["correlation"] == "LABEL" and r["STABLE_FINAL_OPTIMIZED_STATE"] == "YES" for r in rows), "correlation of required roots to the trace failed")
    absent = identity.correlate_roles(resolution, normalize(cfg, fixtures.run(lambda b: None))[1])
    require(all(r["OPTIMIZATION_STATE"] == "NOT_TRIGGERED" and r["correlation"] == "NOT_IN_TRACE" for r in absent), "a required root missing from a complete trace must be NOT_TRIGGERED")

    with tempfile.TemporaryDirectory(prefix="perf010a-hot-root-selftest-") as tmp:
        dump_dir = Path(tmp) / "graal_dumps"
        dump_dir.mkdir()
        for comp, name in ((2585, fixtures.A), (2685, fixtures.A), (2586, fixtures.B), (2686, fixtures.B)):
            (dump_dir / f"TruffleHotSpotCompilation-{comp}[{name}].bgv").write_bytes(b"BIGV" + bytes([comp % 251]))
        (dump_dir / "stray.bgv").write_bytes(b"BIGV")
        manifest = shape.dump_manifest(dump_dir, result, records)
        by_path = {f["path"]: f for f in manifest["files"]}
        require(all(f["correlation"] == "COMP_ID" for p, f in by_path.items() if p != "stray.bgv"), "GRAPH_MANIFEST_ROOT_CORRELATION: dump not correlated by CompId")
        require(by_path["stray.bgv"]["correlation"] == "UNCORRELATED" and manifest["uncorrelated_files"] == ["stray.bgv"], "an uncorrelated dump must be reported")
        require(manifest["compilations_without_dump"] == [], "unexpected compilation without a dump")
        require(sorted(d["comp_id"] for d in shape.member_dumps(rows[0], manifest)) == [2585, 2685], "per-root dump correlation failed")
        (dump_dir / f"TruffleHotSpotCompilation-2685[{fixtures.A}].bgv").unlink()
        require(len(shape.dump_manifest(dump_dir, result, records)["compilations_without_dump"]) == 1, "a compilation without a dump must be reported")

    dirs = {str(unit_dump_dir(Path("dumps"), "run", u, kind)) for u in units(cfg) for kind in RUN_KINDS}
    require(len(dirs) == len(units(cfg)) * len(RUN_KINDS) == 12, "GRAPH_CAPTURE_ISOLATED_PER_WORKLOAD: unit/run-kind dump directories collide")
    require(not any(a != b and (a + "/").startswith(b + "/") for a in dirs for b in dirs), "dump directories must not be nested")
    require(unit_dump_dir(Path("d"), "r", units(cfg)[0], "graph") == unit_dump_dir(Path("d"), "r", units(cfg)[0], "graph"), "dump directories must be deterministic")

    partial = shape.partial_pe_views(rows, records, result, 2)
    helper = next(r for r in rows if r["kind"] == "helper")
    frames = ["com.guillermomolina.protos.runtime.ProtosActivation.<init>(ProtosActivation.java:1)"]
    facts = {
        "schema": shape.FACTS_SCHEMA,
        "durable_id": helper["durable_id"],
        "comp_id": 2685,
        "views": {
            "pe": {"graph_name": "After PE Tier", "complete": True, "node_source_positions": True, "nodes": [{"kind": "allocation", "class": "com.guillermomolina.protos.runtime.ProtosActivation", "frames": frames, "count": 2}]},
            "late": {"graph_name": "After phase PartialEscape", "complete": True, "node_source_positions": True, "nodes": [{"kind": "invoke", "target": "Map.put(Object, Object)", "frames": ["java.util.HashMap.put(HashMap.java:619)"], "count": 1}]},
        },
    }
    shape.validate_shape_facts(facts)
    expect_error(lambda: shape.validate_shape_facts(dict(facts, comp_id="x")), "shape facts without a compilation id")
    classified = shape.classify_shape(rows, {helper["durable_id"]: facts}, partial, families=cfg["shape"]["families"], other_family=cfg["shape"]["other_family"], final_tier=2, min_count=cfg["shape"]["min_count_for_yes"])
    member = next(m for m in classified["members"] if m["durable_id"] == helper["durable_id"])["families"]
    require(member["activation_creation"]["SURVIVES_AFTER_PARTIAL_EVALUATION"] == "YES" and member["activation_creation"]["SURVIVES_OPTIMIZED_GRAPH"] == "NO" and member["activation_creation"]["removed_after_partial_evaluation"] is True, "an allocation removed by later optimization must not count as surviving")
    require(member["host_map_optional_string"]["SURVIVES_OPTIMIZED_GRAPH"] == "YES", "a surviving invoke must be YES")
    semantic = next(m for m in classified["members"] if m["kind"] == "semantic")["families"]
    seen = {v["SURVIVES_OPTIMIZED_GRAPH"] for fam in (member, semantic) for v in fam.values()}
    require(seen == {"YES", "NO", "INCONCLUSIVE"}, "the compiled-shape result must support YES, NO and INCONCLUSIVE")
    incomplete = copy.deepcopy(facts)
    incomplete["views"]["late"]["complete"] = False
    partial_only = shape.classify_shape(rows, {helper["durable_id"]: incomplete}, {}, families=cfg["shape"]["families"], other_family=cfg["shape"]["other_family"], final_tier=2, min_count=1)
    require(next(m for m in partial_only["members"] if m["durable_id"] == helper["durable_id"])["families"]["bytecode_continuation"]["SURVIVES_OPTIMIZED_GRAPH"] == "INCONCLUSIVE", "an incomplete late view must never produce NO")
    unstable = [dict(r, STABLE_FINAL_OPTIMIZED_STATE="NO") for r in rows]
    require(shape.classify_shape(unstable, {}, {}, families=cfg["shape"]["families"], other_family=cfg["shape"]["other_family"], final_tier=2, min_count=1)["applicable_members"] == 0, "roots that did not stably compile must not be shape-classified")
    return {
        "GRAPH_CAPTURE_ISOLATED_PER_WORKLOAD": "PASS",
        "GRAPH_MANIFEST_ROOT_CORRELATION": "PASS",
        "COMPILED_SHAPE_RESULT_SUPPORTS_YES_NO_INCONCLUSIVE": "PASS",
    }


def self_test_product_identity(cfg: dict[str, Any]) -> dict[str, str]:
    protos = cfg["protos"]
    good = {
        "revision_label": protos["revision"],
        "source_head": protos["revision"],
        "product_version": protos["version"],
        "toolchain": {k: cfg["toolchain"][k] for k in ("schema", "java", "graalvm", "graal_components", "maven", "policy")},
        "runtime": {
            "runtime_class": EXPECTED_RUNTIME,
            "engine_version": EXPECTED_GRAALVM_RELEASE,
            "java_version": EXPECTED_JDK_VERSION,
            "java_runtime_version": "25.0.4.1.1+7-jvmci-" + EXPECTED_JVMCI,
            "java_vm_version": "25.0.4.1.1+7-jvmci-" + EXPECTED_JVMCI,
        },
    }
    verify_admitted_build(cfg, good)

    def mutated(path: tuple[str, ...], value: Any) -> dict[str, Any]:
        build = copy.deepcopy(good)
        target = build
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return build

    other = "c" * 40
    for label, build in (
        ("a wrong image revision label", mutated(("revision_label",), other)),
        ("a wrong source tree HEAD", mutated(("source_head",), other)),
        ("a wrong product version", mutated(("product_version",), "0.3.118-SNAPSHOT")),
        ("a wrong toolchain JDK", mutated(("toolchain", "graalvm", "jdk_version"), "25.0.4.1")),
        ("a fallback runtime", mutated(("runtime", "runtime_class"), "com.oracle.truffle.api.impl.DefaultTruffleRuntime")),
        ("a wrong engine version", mutated(("runtime", "engine_version"), "25.3.4.1")),
        ("a wrong JDK version", mutated(("runtime", "java_version"), "25.0.4.1")),
        ("a wrong JVMCI", mutated(("runtime", "java_vm_version"), "25.0.4.1.1+7-jvmci-25.3-b1")),
    ):
        expect_error(lambda build=build: verify_admitted_build(cfg, build), label)
    return {
        "HARNESS_PRODUCT_REVISION_FAIL_CLOSED": "PASS",
        "HARNESS_PRODUCT_VERSION_FAIL_CLOSED": "PASS",
        "HARNESS_TOOLCHAIN_FAIL_CLOSED": "PASS",
        "HARNESS_RUNTIME_IDENTITY_FAIL_CLOSED": "PASS",
    }


def self_test_config_rejections(cfg: dict[str, Any], dist006d: Any) -> dict[str, str]:
    def reject(label: str, mutate: Any) -> None:
        payload = copy.deepcopy(cfg)
        mutate(payload)
        expect_error(lambda: validate_config_payload(payload, dist006d), label)

    reject("a floating product revision", lambda c: c["protos"].__setitem__("revision", "main"))
    reject("another product revision", lambda c: c["protos"].__setitem__("revision", "d" * 40))
    reject("another product version", lambda c: c["protos"].__setitem__("version", "0.3.118-SNAPSHOT"))
    reject("a product patch", lambda c: c["protos"].__setitem__("product_patch", True))
    reject("a forked toolchain", lambda c: c["toolchain"]["graalvm"].__setitem__("jdk_version", "25.0.4.1"))
    reject("a missing workload", lambda c: c["workloads"].pop())
    reject("a missing variant", lambda c: c["variants"].pop())
    reject("a missing base role", lambda c: c["workloads"][0]["roles"].pop(0))
    reject("a changed target text", lambda c: c["workloads"][1].__setitem__("target_text", "sink = 1"))
    reject("a tuning option", lambda c: c["diagnostic"]["run_kinds"]["lifecycle"]["options"].append({"name": "polyglot.engine.BackgroundCompilation", "value": "false", "purpose": "x"}))
    reject("a missing lifecycle option", lambda c: c["diagnostic"]["run_kinds"]["lifecycle"]["options"].pop(1))
    reject("a missing graph option", lambda c: c["diagnostic"]["run_kinds"]["graph"]["options"].pop(0))
    reject("a missing candidate family", lambda c: c["shape"]["families"].pop())
    reject("a drifted boundary", lambda c: c["boundaries"].__setitem__("perf020_implemented", True))
    reject("an in-harness classification", lambda c: c["boundaries"].__setitem__("causal_class_in_harness", "A"))
    reject("timing evidence", lambda c: c.__setitem__("timing_evidence", True))
    reject("a drifted historical mechanism pin", lambda c: c["reused_infrastructure"]["source_identity_mechanism"]["files"].__setitem__("docker/protos-perf010a/Perf010aSourceIdentityInstrument.java", "0" * 64))
    return {}


def validate() -> dict[str, Any]:
    dist006d = load_dist006d()
    cfg = validate_config_payload(load(), dist006d)
    validate_reused_infrastructure(cfg, dist006d)
    validate_overlay_dockerfile(OVERLAY_DOCKERFILE.read_text(encoding="utf-8"))
    validate_java_sources()
    validate_no_hard_coded_root_numbers(cfg)
    validate_makefile()
    flags: dict[str, str] = {"REQUIRED_WORKLOAD_MATRIX_PRESENT": "PASS", "NO_PRODUCT_PATCH": "PASS", "NO_OBSERVABLE_PROTOS_SEMANTIC_CHANGE": "PASS", "NO_HARD_CODED_ROOT_NUMBERS": "PASS"}
    require(len(units(cfg)) == 6, "the required matrix is three workloads times two variants")
    self_test_config_rejections(cfg, dist006d)
    for test in (self_test_product_identity, self_test_lifecycle, self_test_identity, self_test_correlation_and_shape):
        flags.update(test(cfg))
    print("PERF010A_HOT_ROOT_CONFIG=PASS")
    print("PROTOS_REVISION=" + cfg["protos"]["revision"])
    print("PROTOS_VERSION=" + cfg["protos"]["version"])
    for name in sorted(flags):
        print(f"{name}={flags[name]}")
    print("PERF020_IMPLEMENTED=NO")
    print("AUTHORITATIVE_DISCRIMINATOR_EXECUTED=NO")
    print("PRODUCT_REPOSITORY_MUTATION=NO")
    print("CAUSAL_CLASS=" + cfg["boundaries"]["causal_class_in_harness"])
    print("PERF010A_HOT_ROOT_STATIC_VALIDATION=PASS")
    return cfg
