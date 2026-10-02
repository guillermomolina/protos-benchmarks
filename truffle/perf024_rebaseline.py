#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""PERF024 post-PERF025/PERF026 current-runtime cross-Truffle re-baseline.

Measures one exact CURRENT Protos endpoint through the prepared embedding API
(``session.prepareTopLevel("run")`` outside timing, ``prepared.invoke()``
timed) against the pinned GraalJS/GraalPy peers through a prepared executable
polyglot ``Value`` (``run.execute()`` timed). All three languages are launched
the same way: one plain ``java -cp`` process per observation pinned with
``taskset`` to one logical CPU.

Stability admission, CPU selection, harness identity and rejected-evidence
handling are reused from jvm_matrix.py; exact checkout and variant
preparation from prepare.py; prepared-runner compilation and bytecode checks
from perf025_ab.py. The historical ``jvm-cross-truffle-v2`` definition is not
used or changed.
"""

from __future__ import annotations

import ast
import json
import platform
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import jvm_matrix
import perf025_ab
import prepare
from workload_catalog import catalog, expected_result, source_for

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
WORK = ROOT / ".work" / "perf024-rebaseline"
PREPARED_CLASSES = WORK / "prepared-runner"
HARNESS_CLASSPATH_FILE = WORK / "harness-classpath.txt"
STAMP = ROOT / ".work" / "truffle-prepare" / "perf024-rebaseline.json"
RESULTS = ROOT / "results"

# v1 sized every language's sample with Protos' per-call cost, so the
# peers' samples were ~1 ms and dominated by ms-scale background compiler
# stalls on the single pinned CPU (v1 reference at ca34b345: 5/9 NOT_STABLE).
# v2 declares sample_calls per (workload, language) for ~50 ms samples.
MEASUREMENT_DEFINITION = "jvm-cross-truffle-current-v2"
SUPERSEDED_DEFINITION = "jvm-cross-truffle-current-v1"
HISTORICAL_DEFINITION = "jvm-cross-truffle-v2"
EXPERIMENT = "PERF024"
WORK_ITEM = "PERF024-REBASELINE"
RETAINED_DESTINATION = "perf024-rebaseline"
HISTORICAL_DESTINATIONS = ("PERF023", "PERF025-D3")

CURRENT_ROLE = "CURRENT"
CURRENT_REVISION = "19d7426a5b8f0e3b93d36f56aee33377a4ee9985"
CURRENT_VERSION = "0.3.143-SNAPSHOT"
CURRENT_RUN_MODE = "prepared"
CHECKOUT_NAME = "perf024-current"

GRAALVM_VERSION = "25.4.4.1.1"
JDK_VERSION = "25.0.4.1.1"

LANGUAGES = ("protos", "js", "python")
RUN_MODE = "prepared"

EMBEDDING_FLOOR = "EMBEDDING_FLOOR"
GUEST_DOMINATED = "GUEST_DOMINATED_CURRENT_STATE"

# workload -> measurement class. The historical loop workloads (integer-loop,
# method-call) are excluded: they use the standard selector `while`, which
# D180 renamed to `whileTrue` without a compatibility alias, so they fail on
# CURRENT; historical workload sources are not rewritten.
WORKLOADS = {
    "primitive-return-literal": EMBEDDING_FLOOR,
    "fibonacci": GUEST_DOMINATED,
    "factorial": GUEST_DOMINATED,
}

EVIDENCE_UNIT = {
    EMBEDDING_FLOOR:
        "ns per reusable prepared host->guest invocation "
        "(guest work almost empty)",
    GUEST_DOMINATED:
        "ns per complete top-level run() invocation "
        "(one full workload execution inside one guest invocation)",
}

QUESTION = {
    EMBEDDING_FLOOR:
        "what fixed reusable-hosting cost is visible when guest work is "
        "almost empty?",
    GUEST_DOMINATED:
        "after amortizing that boundary, what current per-workload "
        "relationship is observed among Protos, GraalJS and GraalPy?",
}

# measurement class -> (warmup, steady)
REFERENCE_ITERATIONS = {
    EMBEDDING_FLOOR: (50, 10),
    GUEST_DOMINATED: (50, 10),
}
SMOKE_ITERATIONS = (1, 2)

# (workload, language) -> sample_calls, fixed and declared; identical for
# smoke and reference. Sized for roughly 50 ms per steady sample.
SAMPLE_CALLS = {
    ("primitive-return-literal", "protos"): 10_000,
    ("primitive-return-literal", "js"): 500_000,
    ("primitive-return-literal", "python"): 500_000,
    ("fibonacci", "protos"): 10,
    ("fibonacci", "js"): 500,
    ("fibonacci", "python"): 500,
    ("factorial", "protos"): 20,
    ("factorial", "js"): 3_000,
    ("factorial", "python"): 3_000,
}

# Smoke gate: every steady smoke sample of every language must last at least
# this long, so a sample size that cannot amortize ms-scale stalls fails in
# smoke instead of in the reference.
MIN_SMOKE_SAMPLE_NS = 20_000_000
REFERENCE_ADMISSION_SCOPE = "steady-only"

EXPECTED_OBSERVATIONS = len(WORKLOADS) * len(LANGUAGES)

RATIO_CONVENTION = (
    "ratio=protos_steady_amortized_p50/peer_steady_amortized_p50; "
    ">1=protos-higher-time; <1=protos-lower-time"
)

TRUFFLE_RUNNER_SOURCE = (
    TRUFFLE / "src/main/java" / perf025_ab.PACKAGE_PATH
    / "TruffleJvmRunner.java"
)
TRUFFLE_RUNNER_CLASS = f"{perf025_ab.PACKAGE}.TruffleJvmRunner"


def capture(*command: str, cwd: Path | None = None) -> str:
    return perf025_ab.capture(*command, cwd=cwd)


# --------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------


def policy(
    profile: str,
    workload: str,
    language: str,
) -> tuple[int, int, int]:
    if profile == "benchmark":
        warmup, steady = REFERENCE_ITERATIONS[WORKLOADS[workload]]
    else:
        warmup, steady = SMOKE_ITERATIONS

    return warmup, steady, SAMPLE_CALLS[(workload, language)]


def check_contract() -> None:
    if (
        CURRENT_REVISION != perf025_ab.point("FINAL")[1]
        or CURRENT_VERSION != perf025_ab.point("FINAL")[2]
        or CURRENT_RUN_MODE != perf025_ab.point("FINAL")[3]
    ):
        raise RuntimeError("CURRENT endpoint differs from PERF025 FINAL")

    if not re.fullmatch(r"[0-9a-f]{40}", CURRENT_REVISION):
        raise RuntimeError("CURRENT revision is not a full SHA")

    if CURRENT_RUN_MODE != "prepared":
        raise RuntimeError("CURRENT run mode must be prepared")

    print(f"current_revision={CURRENT_REVISION}")
    print(f"current_version={CURRENT_VERSION}")
    print(f"current_run_mode={CURRENT_RUN_MODE}")

    if MEASUREMENT_DEFINITION in {
        HISTORICAL_DEFINITION,
        SUPERSEDED_DEFINITION,
        perf025_ab.MEASUREMENT_DEFINITION,
        "jvm-protos-session-ab-v1",
        "jvm-protos-session-ab-v2",
    }:
        raise RuntimeError("measurement definition is not new")

    print(f"measurement_definition={MEASUREMENT_DEFINITION} new=YES")

    expected_workloads = {
        "primitive-return-literal": EMBEDDING_FLOOR,
        "fibonacci": GUEST_DOMINATED,
        "factorial": GUEST_DOMINATED,
    }

    if WORKLOADS != expected_workloads:
        raise RuntimeError(f"workload set mismatch: {WORKLOADS}")

    for workload in WORKLOADS:
        if workload not in catalog():
            raise RuntimeError(f"{workload}: not in workload catalog")

        for language in LANGUAGES:
            source_for(workload, language)

        print(f"workload={workload} expected={expected_result(workload)} "
              f"class={WORKLOADS[workload]}")

    if (
        REFERENCE_ITERATIONS != {
            EMBEDDING_FLOOR: (50, 10),
            GUEST_DOMINATED: (50, 10),
        }
        or SMOKE_ITERATIONS != (1, 2)
        or SAMPLE_CALLS != {
            ("primitive-return-literal", "protos"): 10_000,
            ("primitive-return-literal", "js"): 500_000,
            ("primitive-return-literal", "python"): 500_000,
            ("fibonacci", "protos"): 10,
            ("fibonacci", "js"): 500,
            ("fibonacci", "python"): 500,
            ("factorial", "protos"): 20,
            ("factorial", "js"): 3_000,
            ("factorial", "python"): 3_000,
        }
        or MIN_SMOKE_SAMPLE_NS != 20_000_000
    ):
        raise RuntimeError("sample policy mismatch")

    for profile in ("smoke", "benchmark"):
        for workload in WORKLOADS:
            for language in LANGUAGES:
                warmup, steady, calls = policy(profile, workload, language)
                print(f"policy profile={profile} workload={workload} "
                      f"language={language} warmup={warmup} "
                      f"steady={steady} sample_calls={calls}")

    print(f"smoke_min_steady_sample_ms={MIN_SMOKE_SAMPLE_NS / 1e6:.0f}")

    minimum = jvm_matrix.STABILITY_WINDOW * 2

    for warmup, steady in REFERENCE_ITERATIONS.values():
        if warmup < minimum or steady < minimum:
            raise RuntimeError("reference counts below stability window")

    thresholds = (
        jvm_matrix.STABILITY_WINDOW,
        jvm_matrix.STABILITY_MEDIAN_DRIFT_PCT,
        jvm_matrix.STABILITY_MAD_PCT,
        jvm_matrix.STABILITY_MAX_INTERNAL_GAP_PCT,
        jvm_matrix.STABILITY_MIN_GAP_CLUSTER_SIZE,
    )

    if thresholds != (5, 15.0, 20.0, 20.0, 3):
        raise RuntimeError(f"stability thresholds changed: {thresholds}")

    if REFERENCE_ADMISSION_SCOPE != "steady-only":
        raise RuntimeError("admission scope must be steady-only")

    stable = jvm_matrix.stability_window([1000] * 10)
    bimodal = jvm_matrix.stability_window([1000] * 5 + [2000] * 5)

    if stable["status"] != "PASS" or bimodal["status"] != "NOT_STABLE":
        raise RuntimeError("reused stability self-test failed")

    print(
        "stability_thresholds=window:5,median_drift:15,mad:20,"
        "internal_gap:20,min_gap_cluster:3 unchanged=YES"
    )
    print(f"admission_scope={REFERENCE_ADMISSION_SCOPE} self_test=PASS")

    if EXPECTED_OBSERVATIONS != 9:
        raise RuntimeError("expected observations != 9")

    print(f"expected_observations={EXPECTED_OBSERVATIONS}")


def check_no_retry_or_profiling() -> None:
    """Statically prove one execution per case and no diagnostic flags."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))

    loops = [node for node in ast.walk(tree) if isinstance(node, ast.While)]

    if loops:
        raise RuntimeError("perf024_rebaseline.py contains a while loop")

    execute_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute"
    ]

    if len(execute_calls) != 1:
        raise RuntimeError(
            f"execute() must have exactly one call site: {len(execute_calls)}"
        )

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    if "jvm_diagnostic" in imported:
        raise RuntimeError("diagnostic module imported")

    item = {"classpath": "CP", "core": Path("CORE")}

    for workload in WORKLOADS:
        for language in LANGUAGES:
            for profile in ("smoke", "benchmark"):
                counts = [
                    str(value)
                    for value in policy(profile, workload, language)
                ]
                command = command_for(
                    language, item, "HCP", workload, 0,
                    *policy(profile, workload, language),
                )
                source = str(source_for(workload, language))

                if language == "protos":
                    expected = [
                        "CP", perf025_ab.PREPARED_CLASS, "CORE", source,
                    ]
                else:
                    expected = [
                        "HCP", TRUFFLE_RUNNER_CLASS, "measure", language,
                        source,
                    ]

                # Exact shape: no JVM option, agent or diagnostic flag can
                # be present anywhere in a measured command.
                if command != [
                    "taskset", "-c", "0", "java", "-cp", *expected, *counts,
                ]:
                    raise RuntimeError(
                        f"{language}/{workload}: unexpected command {command}"
                    )

    print("automatic_retry=NO calibration_loop=NO execute_call_sites=1")
    print("reference_profiling=NONE jfr=NO igv=NO compiler_tracing=NO")


def check_prepared_runner_source() -> None:
    text = perf025_ab.PREPARED_SOURCE.read_text(encoding="utf-8")
    prepare_at = text.find('session.prepareTopLevel("run")')
    measure_at = text.find("ProtosJvmVariantRunner.measure(")
    invoke_at = text.find("() -> prepared.invoke()")

    if (
        text.count('prepareTopLevel("run")') != 1
        or text.count("invokeTopLevel") != 0
        or not 0 <= prepare_at < measure_at < invoke_at
    ):
        raise RuntimeError("prepared runner source contract violated")

    print("prepared_runner_source=prepareTopLevel(run)-before-measure "
          "timed=PreparedTopLevel.invoke")


EXECUTE_CALL = re.compile(
    r"org/graalvm/polyglot/Value\.execute:\(\[Ljava/lang/Object;\)"
)
GET_MEMBER_TRUFFLE_RUN = re.compile(r"String truffleRun")


def check_peer_runner() -> None:
    """JS/Python: prepared executable Value, execute() inside the timed lambda."""
    files = sorted(
        (perf025_ab.HARNESS_CLASSES / perf025_ab.PACKAGE_PATH)
        .glob("TruffleJvmRunner*.class")
    )

    if not files:
        raise RuntimeError("compiled TruffleJvmRunner missing")

    lambda_execute: dict[str, int] = {}
    executable_check = False

    for path in files:
        text = perf025_ab.javap(path)
        perf025_ab.require_no_reflection(path.name, text)
        table = perf025_ab.methods(text)

        for name, count in perf025_ab.calling(table, EXECUTE_CALL).items():
            if "lambda$" in name:
                lambda_execute[name] = count

        for name, body in table.items():
            if " executableRun(" in name:
                joined = "\n".join(body)
                executable_check = (
                    "Value.getMember" in joined
                    and "Value.canExecute" in joined
                    and GET_MEMBER_TRUFFLE_RUN.search(joined) is not None
                )

    if len(lambda_execute) != 1 or list(lambda_execute.values()) != [1]:
        raise RuntimeError(
            f"peer timed Value.execute sites: {lambda_execute}"
        )

    if not executable_check:
        raise RuntimeError("peer executableRun contract missing")

    print("peer_prepared_surface=executable-Value(truffleRun) "
          "timed=Value.execute")


def check_results_untouched() -> None:
    changed = capture(
        "git", "status", "--porcelain", "--untracked-files=all",
        "--", "results", cwd=ROOT,
    )

    if changed:
        raise RuntimeError(f"results/ has local changes:\n{changed}")

    print("historical_results_mutated=NO")

    import retain_results

    for work_item in HISTORICAL_DESTINATIONS:
        retain_results.verify_retained(work_item)

    if (RESULTS / RETAINED_DESTINATION).exists():
        retain_results.verify_retained(WORK_ITEM)
    else:
        print(f"{RETAINED_DESTINATION}=ABSENT")


def check_retention_profile() -> None:
    import retain_results

    classes = retain_results.RETENTION_PROFILES[RETAINED_DESTINATION][
        "expected_classes"
    ]

    if classes != {"jvm-cross-truffle-current-v2-reference": 9}:
        raise RuntimeError(f"retention profile count: {classes}")

    if retain_results.RETENTION_PROFILES["perf025"]["expected_classes"] != {
        "jvm-ab-v3-reference": 12,
    }:
        raise RuntimeError("historical perf025 profile changed")

    print(f"retention_profile={RETAINED_DESTINATION} expected=9")


def check_identity_contract() -> None:
    toolchain = {
        "java_version": "x",
        "javac_version": "x",
        "runner_classes_sha256": "x",
        "harness_classpath_sha256": "h",
    }
    item = {
        "core_sha256": "c",
        "dependency_classpath_sha256": "d",
        "prepared_class_dir": perf025_ab.HARNESS_CLASSES,
    }
    keys = set()

    for workload in WORKLOADS:
        for language in LANGUAGES:
            data = identity(
                language, item, workload, 0, [0], "benchmark",
                *policy("benchmark", workload, language), toolchain,
            )

            for key in (
                "measurement_definition", "experiment", "profile",
                "language", "workload", "run_mode", "harness_revision",
                "harness_dirty", "source_sha256", "runner_sha256",
                "catalog_sha256", "graalvm_version", "java_version",
                "cpu", "cpu_siblings", "cpu_model", "architecture",
                "kernel", "warmup_iterations", "steady_iterations",
                "sample_calls", "steady_state_admission",
            ):
                if key not in data:
                    raise RuntimeError(f"identity missing {key}")

            if language == "protos":
                for key in (
                    "protos_revision", "protos_version",
                    "protos_core_sha256", "prepared_runner_sha256",
                ):
                    if key not in data:
                        raise RuntimeError(f"protos identity missing {key}")

            if data["sample_calls"] != SAMPLE_CALLS[(workload, language)]:
                raise RuntimeError("identity sample_calls mismatch")

            keys.add(jvm_matrix.cache_key(data))

    if len(keys) != EXPECTED_OBSERVATIONS:
        raise RuntimeError("identity cache keys collide")

    print(
        "identity_fields=complete cache_keys_distinct="
        f"{EXPECTED_OBSERVATIONS}"
    )


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


def current_checkout() -> Path:
    return prepare.AB_ROOT / CHECKOUT_NAME


def prepared_class_dir() -> Path:
    return PREPARED_CLASSES / CURRENT_REVISION


def verify_current() -> dict[str, object]:
    repo = current_checkout()

    if not (repo / ".git").exists():
        raise RuntimeError(
            f"CURRENT checkout missing: {repo}; "
            "run make perf024-rebaseline-prepare"
        )

    dirty = capture(
        "git", "status", "--porcelain", "--untracked-files=no", cwd=repo
    )

    if dirty:
        raise RuntimeError(f"CURRENT checkout has tracked changes\n{dirty}")

    if capture("git", "rev-parse", "HEAD", cwd=repo) != CURRENT_REVISION:
        raise RuntimeError("CURRENT checkout revision mismatch")

    if prepare.project_version(repo) != CURRENT_VERSION:
        raise RuntimeError("CURRENT checkout version mismatch")

    classes = repo / "target" / "classes"

    if not (classes / perf025_ab.PREPARED_API_CLASS).is_file():
        raise RuntimeError("CURRENT classes lack the prepared API")

    dependency_cp = (
        prepare.AB_ROOT / "classpath" / f"{CURRENT_REVISION}.txt"
    ).read_text(encoding="utf-8").strip()

    if not dependency_cp:
        raise RuntimeError("CURRENT dependency classpath empty")

    core = repo / "protos" / "lib" / "core"

    return {
        "role": CURRENT_ROLE,
        "run_mode": CURRENT_RUN_MODE,
        "revision": CURRENT_REVISION,
        "version": CURRENT_VERSION,
        "core": core,
        "core_sha256": prepare.sha256_tree(core),
        "dependency_classpath_sha256":
            perf025_ab.sha256_text(dependency_cp),
        "graalvm_version": perf025_ab.graalvm_version(dependency_cp),
        "prepared_class_dir": prepared_class_dir(),
        "classpath": ":".join([
            str(perf025_ab.HARNESS_CLASSES),
            str(prepared_class_dir()),
            str(classes),
            dependency_cp,
        ]),
    }


def harness_classpath() -> str:
    if not HARNESS_CLASSPATH_FILE.is_file():
        raise RuntimeError(
            "harness classpath missing; run make perf024-rebaseline-prepare"
        )

    dependency_cp = HARNESS_CLASSPATH_FILE.read_text(encoding="utf-8").strip()

    if not dependency_cp:
        raise RuntimeError("harness dependency classpath empty")

    perf025_ab.graalvm_version(dependency_cp)
    return ":".join([str(perf025_ab.HARNESS_CLASSES), dependency_cp])


def toolchain_identity() -> dict[str, str]:
    java_version = capture("java", "-version")
    javac_version = capture("javac", "-version")

    if JDK_VERSION not in java_version or GRAALVM_VERSION not in java_version:
        raise RuntimeError(f"java identity mismatch:\n{java_version}")

    if javac_version != f"javac {JDK_VERSION}":
        raise RuntimeError(f"javac identity mismatch: {javac_version}")

    return {
        "java_version": java_version,
        "javac_version": javac_version,
        "runner_classes_sha256": perf025_ab.harness_classes_sha256(),
        "harness_classpath_sha256": perf025_ab.sha256_text(
            HARNESS_CLASSPATH_FILE.read_text(encoding="utf-8").strip()
        ),
    }


def identity(
    language: str,
    item: dict[str, object],
    workload: str,
    cpu: int,
    siblings: list[int],
    profile: str,
    warmup: int,
    steady: int,
    sample_calls: int,
    toolchain: dict[str, str],
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema": 1,
        "measurement_definition": MEASUREMENT_DEFINITION,
        "experiment": EXPERIMENT,
        "mode": "jvm",
        "profile": profile,
        "language": language,
        "workload": workload,
        "measurement_class": WORKLOADS[workload],
        "evidence_unit": EVIDENCE_UNIT[WORKLOADS[workload]],
        "run_mode": RUN_MODE,
        "source_sha256": prepare.sha256_file(source_for(workload, language)),
        "harness_revision": jvm_matrix.benchmark_revision(),
        "harness_dirty": jvm_matrix.benchmark_dirty(),
        "orchestrator_sha256": prepare.sha256_file(Path(__file__)),
        "matrix_sha256": prepare.sha256_file(TRUFFLE / "jvm_matrix.py"),
        "catalog_sha256": prepare.sha256_file(
            TRUFFLE / "workloads" / "catalog.json"
        ),
        "pom_sha256": prepare.sha256_file(TRUFFLE / "pom.xml"),
        "runner_classes_sha256": toolchain["runner_classes_sha256"],
        "graalvm_version": GRAALVM_VERSION,
        "java_version": toolchain["java_version"],
        "javac_version": toolchain["javac_version"],
        "cpu": cpu,
        "cpu_siblings": siblings,
        "cpu_model": jvm_matrix.cpu_model(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "warmup_iterations": warmup,
        "steady_iterations": steady,
        "sample_calls": sample_calls,
    }

    if language == "protos":
        data.update({
            "runner_sha256": prepare.sha256_file(perf025_ab.DYNAMIC_SOURCE),
            "prepared_runner_sha256":
                prepare.sha256_file(perf025_ab.PREPARED_SOURCE),
            "prepared_runner_classes_sha256": prepare.sha256_tree(
                Path(str(item["prepared_class_dir"]))
            ),
            "protos_role": CURRENT_ROLE,
            "protos_revision": CURRENT_REVISION,
            "protos_version": CURRENT_VERSION,
            "protos_core_sha256": item["core_sha256"],
            "protos_dependency_classpath_sha256":
                item["dependency_classpath_sha256"],
        })
    else:
        data.update({
            "runner_sha256": prepare.sha256_file(TRUFFLE_RUNNER_SOURCE),
            "harness_classpath_sha256":
                toolchain["harness_classpath_sha256"],
        })

    if profile == "benchmark":
        data["steady_state_admission"] = {
            "scope": REFERENCE_ADMISSION_SCOPE,
            "window": jvm_matrix.STABILITY_WINDOW,
            "median_drift_pct_max": jvm_matrix.STABILITY_MEDIAN_DRIFT_PCT,
            "mad_pct_max": jvm_matrix.STABILITY_MAD_PCT,
            "max_internal_gap_pct": jvm_matrix.STABILITY_MAX_INTERNAL_GAP_PCT,
            "min_gap_cluster_size": jvm_matrix.STABILITY_MIN_GAP_CLUSTER_SIZE,
        }
    else:
        data["steady_state_admission"] = "none-smoke"

    return data


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------


def compile_harness() -> None:
    subprocess.run(
        ["mvn", "-q", "-f", str(TRUFFLE / "pom.xml"), "compile"],
        cwd=ROOT,
        check=True,
    )


def stage_validate() -> None:
    check_contract()
    check_no_retry_or_profiling()
    check_prepared_runner_source()
    compile_harness()
    check_identity_contract()
    perf025_ab.check_dynamic_runner()
    check_peer_runner()

    if (prepared_class_dir() / perf025_ab.PACKAGE_PATH).is_dir():
        perf025_ab.check_prepared_runner(prepared_class_dir())
    else:
        print("prepared_runner_bytecode=DEFERRED-to-prepare")

    check_retention_profile()
    check_results_untouched()
    print("perf024_rebaseline_validate=PASS")


def stage_prepare() -> None:
    prepare.require_tools()

    for tool in ("javac", "javap"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"missing required tool: {tool}")

    compile_harness()
    WORK.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "mvn", "-q", "-f", str(TRUFFLE / "pom.xml"),
            "dependency:build-classpath",
            f"-Dmdep.outputFile={HARNESS_CLASSPATH_FILE}",
        ],
        cwd=ROOT,
        check=True,
    )
    harness_classpath()

    repo = prepare.ensure_checkout(
        CHECKOUT_NAME, CURRENT_REVISION, CURRENT_VERSION
    )
    prepare.ensure_ab_variant(repo, CURRENT_REVISION)

    item = verify_current()
    perf025_ab.compile_prepared_runner(item)
    perf025_ab.check_prepared_runner(prepared_class_dir())
    toolchain = toolchain_identity()

    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(
        json.dumps(
            {
                "revision": CURRENT_REVISION,
                "version": CURRENT_VERSION,
                "run_mode": CURRENT_RUN_MODE,
                "core_sha256": item["core_sha256"],
                "dependency_classpath_sha256":
                    item["dependency_classpath_sha256"],
                "harness_classpath_sha256":
                    toolchain["harness_classpath_sha256"],
                "prepared_runner_source_sha256":
                    prepare.sha256_file(perf025_ab.PREPARED_SOURCE),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"current revision={CURRENT_REVISION} version={CURRENT_VERSION} "
        f"run_mode={CURRENT_RUN_MODE} core_sha256={item['core_sha256']} "
        f"graalvm={item['graalvm_version']} status=READY"
    )
    print("perf024_rebaseline_prepare=PASS")


def require_stamp(item: dict[str, object], toolchain: dict[str, str]) -> None:
    if not STAMP.is_file():
        raise RuntimeError(
            "prepare stamp missing; run make perf024-rebaseline-prepare"
        )

    state = json.loads(STAMP.read_text(encoding="utf-8"))
    actual = {
        "revision": item["revision"],
        "version": item["version"],
        "run_mode": item["run_mode"],
        "core_sha256": item["core_sha256"],
        "dependency_classpath_sha256": item["dependency_classpath_sha256"],
        "harness_classpath_sha256": toolchain["harness_classpath_sha256"],
        "prepared_runner_source_sha256":
            prepare.sha256_file(perf025_ab.PREPARED_SOURCE),
    }

    for key, value in actual.items():
        if state.get(key) != value:
            raise RuntimeError(
                f"{key} changed since prepare; "
                "run make perf024-rebaseline-prepare"
            )


def command_for(
    language: str,
    item: dict[str, object],
    peer_classpath: str,
    workload: str,
    cpu: int,
    warmup: int,
    steady: int,
    sample_calls: int,
) -> list[str]:
    source = str(source_for(workload, language))
    launcher = ["taskset", "-c", str(cpu), "java", "-cp"]
    counts = [str(warmup), str(steady), str(sample_calls)]

    if language == "protos":
        return [
            *launcher, str(item["classpath"]), perf025_ab.PREPARED_CLASS,
            str(item["core"]), source, *counts,
        ]

    return [
        *launcher, peer_classpath, TRUFFLE_RUNNER_CLASS,
        "measure", language, source, *counts,
    ]


def execute(command: list[str], label: str) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.returncode != 0:
        print(result.stdout, end="")
        raise RuntimeError(f"{label}: execution failed")

    return result.stdout


def require_output_contract(
    language: str,
    workload: str,
    output: str,
    warmup: int,
    steady: int,
    sample_calls: int,
) -> dict[str, object]:
    label = f"{language}/{workload}"
    parsed = jvm_matrix.parse_output(output)

    if parsed is None:
        raise RuntimeError(f"{label}: cannot parse output")

    lines = set(output.splitlines())

    if f"language={language}" not in lines:
        raise RuntimeError(f"{label}: language marker missing")

    if language == "protos" and (
        "run_mode=prepared" not in lines
        or not any(line.startswith("prepare_ns=") for line in lines)
    ):
        raise RuntimeError(f"{label}: prepared Protos markers missing")

    if (
        parsed["sample_calls"] != sample_calls
        or len(parsed["warmup_ns"]) != warmup
        or len(parsed["steady_ns"]) != steady
    ):
        raise RuntimeError(f"{label}: sample shape mismatch")

    jvm_matrix.require_expected(workload, str(parsed["result"]))
    return parsed


def amortized_p50(parsed: dict[str, object]) -> float:
    steady = [int(value) for value in parsed["steady_ns"]]
    return float(statistics.median(steady)) / int(parsed["sample_calls"])


def ratio(accepted: dict, workload: str, peer: str) -> str:
    protos = accepted.get(("protos", workload))
    other = accepted.get((peer, workload))

    if protos is None or other is None:
        return "NOT_AVAILABLE"

    return f"{protos / other:.3f}x"


def report(accepted: dict[tuple[str, str], float]) -> None:
    print()
    print(f"=== {EXPERIMENT} CURRENT CROSS-TRUFFLE RE-BASELINE ===")
    print(f"measurement_definition={MEASUREMENT_DEFINITION}")
    print(f"ratio_convention={RATIO_CONVENTION}")
    print("aggregate_score=NONE per-workload-observations-only")

    labels = {
        "protos": "protos/current/prepared",
        "js": "js/prepared",
        "python": "python/prepared",
    }

    for section in (EMBEDDING_FLOOR, GUEST_DOMINATED):
        print()
        print(f"[{section}]")
        print(f"question={QUESTION[section]}")
        print(f"evidence_unit={EVIDENCE_UNIT[section]}")

        for workload, kind in WORKLOADS.items():
            if kind != section:
                continue

            print()
            print(f"workload={workload}")

            for language in LANGUAGES:
                value = accepted.get((language, workload))
                shown = "NOT_ADMITTED" if value is None else f"{value:.1f}"
                print(f"{labels[language]:<24}"
                      f"steady_amortized_p50_ns={shown} "
                      f"sample_calls={SAMPLE_CALLS[(workload, language)]}")

            print(f"PROTOS_VS_JS_RATIO={ratio(accepted, workload, 'js')}")
            print("PROTOS_VS_PYTHON_RATIO="
                  + ratio(accepted, workload, "python"))

    print()
    print(
        "interpretation_limits=embedding-floor-not-subtracted;"
        "no-pure-guest-cost;no-method-send-cost-by-subtraction;"
        "no-whole-language-ranking"
    )


def stage_measure(profile: str) -> None:
    if profile == "benchmark":
        jvm_matrix.require_clean_reference_harness()

        if not re.fullmatch(r"[0-9a-f]{40}", jvm_matrix.benchmark_revision()):
            raise RuntimeError("harness revision is not a full SHA")

    check_contract()
    check_no_retry_or_profiling()
    check_prepared_runner_source()
    compile_harness()
    check_peer_runner()

    item = verify_current()
    perf025_ab.check_prepared_runner(prepared_class_dir())
    peer_classpath = harness_classpath()
    toolchain = toolchain_identity()
    require_stamp(item, toolchain)

    if profile == "benchmark" and jvm_matrix.benchmark_dirty():
        raise RuntimeError("harness became dirty during preparation")

    cpu, siblings = jvm_matrix.choose_cpu()

    print(f"mode=jvm-cross-truffle-current experiment={EXPERIMENT} "
          f"profile={profile}")
    print(f"measurement_definition={MEASUREMENT_DEFINITION}")
    print(f"cpu={cpu}")
    print(f"cpu_siblings={','.join(map(str, siblings))}")
    print(f"cpu_model={jvm_matrix.cpu_model()}")
    print(f"architecture={platform.machine()}")
    print(f"kernel={platform.release()}")
    print("java=" + toolchain["java_version"].splitlines()[0])
    print(f"graalvm={GRAALVM_VERSION}")
    print(f"harness_revision={jvm_matrix.benchmark_revision()} "
          f"harness_dirty={jvm_matrix.benchmark_dirty()}")

    cases = []

    for workload in WORKLOADS:
        for language in LANGUAGES:
            counts = policy(profile, workload, language)
            ident = identity(
                language, item, workload, cpu, siblings, profile,
                *counts, toolchain,
            )
            cases.append((language, workload, counts, ident))

    if profile == "benchmark":
        print(f"reference_admission_scope={REFERENCE_ADMISSION_SCOPE}")

        # A previously rejected identity is never re-measured: that would be
        # a retry to obtain PASS.
        prior = [
            f"{language}/{workload}"
            for language, workload, _, ident in cases
            if (jvm_matrix.REJECTED
                / f"{jvm_matrix.cache_key(ident)}.json").is_file()
        ]

        if prior:
            raise RuntimeError(
                "rejected NOT_STABLE observation already exists for this "
                "identity; retry is not permitted: " + ", ".join(prior)
            )

    accepted: dict[tuple[str, str], float] = {}
    not_stable: list[str] = []
    too_short: list[str] = []
    passed = 0

    for language, workload, (warmup, steady, sample_calls), ident in cases:
        key = jvm_matrix.cache_key(ident)
        cache_file = jvm_matrix.CACHE / f"{key}.json"
        label = f"{language}/{RUN_MODE}/{workload}"

        print()
        print(f"=== {label} class={WORKLOADS[workload]} "
              f"warmup={warmup} steady={steady} "
              f"sample_calls={sample_calls} ===")

        if profile == "benchmark" and cache_file.is_file():
            print("cache=hit")
            output = json.loads(cache_file.read_text(encoding="utf-8"))[
                "output"
            ]
        else:
            print("cache=miss" if profile == "benchmark"
                  else "cache=not-used-smoke")
            output = execute(
                command_for(
                    language, item, peer_classpath, workload, cpu,
                    warmup, steady, sample_calls,
                ),
                label,
            )

        parsed = require_output_contract(
            language, workload, output, warmup, steady, sample_calls
        )
        _, admission = jvm_matrix.summarize_output(
            output,
            profile,
            admission_scope=REFERENCE_ADMISSION_SCOPE,
        )
        passed += 1
        print(f"correctness=PASS result={parsed['result']}")

        if profile != "benchmark":
            shortest = min(int(value) for value in parsed["steady_ns"])
            print(f"smoke_min_steady_sample_ms={shortest / 1e6:.3f}")

            if shortest < MIN_SMOKE_SAMPLE_NS:
                too_short.append(f"{label}={shortest / 1e6:.3f}ms")

            continue

        if admission is None or admission["status"] != "PASS":
            if cache_file.is_file():
                raise RuntimeError(f"{label}: cached reference not admitted")

            rejected = jvm_matrix.write_rejected_observation(
                key, ident, admission, output
            )
            print("status=NOT_STABLE")
            print("rejected_raw=" + str(rejected.relative_to(ROOT)))
            not_stable.append(label)
            continue

        if not cache_file.is_file():
            jvm_matrix.CACHE.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(
                    {"identity": ident, "admission": admission,
                     "output": output},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

        accepted[(language, workload)] = amortized_p50(parsed)

    print()
    print(f"cases_passed_correctness={passed}/{EXPECTED_OBSERVATIONS}")

    if passed != EXPECTED_OBSERVATIONS:
        raise RuntimeError("PERF024 re-baseline matrix incomplete")

    if profile != "benchmark":
        print("timing_interpretation=NONE-smoke")

        if too_short:
            raise RuntimeError(
                "smoke sample-size gate failed (steady sample < "
                f"{MIN_SMOKE_SAMPLE_NS / 1e6:.0f} ms): " + ", ".join(too_short)
            )

        print("smoke_sample_size_gate=PASS")
        print("perf024_rebaseline_smoke=PASS")
        return

    report(accepted)

    if not_stable:
        raise RuntimeError(
            "reference_admission=NOT_STABLE for: "
            + ", ".join(not_stable)
            + "; retained as rejected local raw, not cached, "
            "excluded from ratios"
        )

    print(f"accepted_reference_observations={len(accepted)}")
    print("perf024_rebaseline_reference=PASS")


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) == 2 else ""

    if stage == "validate":
        stage_validate()
    elif stage == "prepare":
        stage_prepare()
    elif stage in {"smoke", "benchmark"}:
        stage_measure(stage)
    else:
        raise SystemExit(
            "usage: perf024_rebaseline.py "
            "<validate|prepare|smoke|benchmark>"
        )


if __name__ == "__main__":
    main()
