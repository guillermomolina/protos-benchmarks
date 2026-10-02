#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""PERF025 exact-revision dynamic/prepared reusable-call A/B.

Entered through ``jvm_protos_ab.py perf025 <stage>``. Stability admission,
CPU selection, harness identity, and rejected-evidence handling are reused
from jvm_matrix.py; exact checkout and variant preparation are reused from
prepare.py.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import statistics
import subprocess
from pathlib import Path

import jvm_matrix
import prepare
from workload_catalog import (
    catalog,
    expected_result,
    jvm_sample_calls,
    source_for,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
AB_ROOT = ROOT / ".work" / "protos-ab"
PREPARED_CLASSES = AB_ROOT / "prepared-runner"
STATE = ROOT / ".work" / "truffle-prepare"
RESULTS = ROOT / "results"

MEASUREMENT_DEFINITION = "jvm-protos-session-ab-v2"
EXPERIMENT = "PERF025"
GRAALVM_VERSION = "25.4.4.1.1"
RETAINED_DESTINATION = "perf025-d3"

PACKAGE = "com.guillermomolina.protos.benchmarks.truffle"
PACKAGE_PATH = PACKAGE.replace(".", "/")
DYNAMIC_CLASS = f"{PACKAGE}.ProtosJvmVariantRunner"
PREPARED_CLASS = f"{PACKAGE}.ProtosPreparedVariantRunner"

DYNAMIC_SOURCE = (
    TRUFFLE / "src/main/java" / PACKAGE_PATH / "ProtosJvmVariantRunner.java"
)
PREPARED_SOURCE = (
    TRUFFLE
    / "src/prepared/java"
    / PACKAGE_PATH
    / "ProtosPreparedVariantRunner.java"
)
HARNESS_CLASSES = TRUFFLE / "target" / "classes"

PREPARED_API_CLASS = (
    "com/guillermomolina/protos/execution/"
    "ProtosStandaloneHostedSession$PreparedTopLevel.class"
)

# role, Protos revision, Protos version, run mode
POINTS = (
    (
        "PRE_A",
        "f3c44554ddfb9004c43dbde5197b9805990f8a4a",
        "0.3.129-SNAPSHOT",
        "dynamic",
    ),
    (
        "A",
        "d0045353d834257b5fb80581846b32aebd43c7e6",
        "0.3.130-SNAPSHOT",
        "dynamic",
    ),
    (
        "B",
        "6811d0cef3735d39ffd3801b3bae6ef48318bb66",
        "0.3.131-SNAPSHOT",
        "prepared",
    ),
    (
        "FINAL",
        "19d7426a5b8f0e3b93d36f56aee33377a4ee9985",
        "0.3.143-SNAPSHOT",
        "prepared",
    ),
)

EXPECTED_MODES = {
    "PRE_A": "dynamic",
    "A": "dynamic",
    "B": "prepared",
    "FINAL": "prepared",
}

WORKLOADS = (
    "primitive-return-literal",
    "primitive-closure-call",
    "primitive-method-call",
)

CATALOG_SAMPLE_CALLS = 100

# Smoke remains a cheap wiring/correctness gate. Reference uses much larger
# batches so sparse scheduler/JIT stalls do not dominate a tiny timing sample.
SMOKE_SAMPLE_CALLS = CATALOG_SAMPLE_CALLS
SMOKE_WARMUP = 2
SMOKE_STEADY = 3

REFERENCE_SAMPLE_CALLS = 10_000
REFERENCE_WARMUP = 20
REFERENCE_STEADY = 10

EXPECTED_OBSERVATIONS = len(POINTS) * len(WORKLOADS)

# name, baseline role, candidate role.
# The first three retain the PERF025 A/B acceptance evidence. The final entry
# is the primary accumulated result and deliberately does not attribute the
# improvement to any individual PERF025 slice.
DELTAS = (
    ("A_DELTA", "PRE_A", "A"),
    ("B_DELTA", "A", "B"),
    ("COMBINED_PRE_A_TO_POST_B_DELTA", "PRE_A", "B"),
    ("TOTAL_ACCUMULATED_DELTA", "PRE_A", "FINAL"),
)

SIGN_CONVENTION = (
    "delta_pct=(candidate_steady_amortized_p50/"
    "baseline_steady_amortized_p50-1)*100; "
    "negative=candidate-lower-time"
)


def checkout_name(role: str) -> str:
    return f"perf025-{role.lower().replace('_', '-')}"


def checkout(role: str) -> Path:
    return AB_ROOT / checkout_name(role)


def stamp_path(role: str) -> Path:
    return STATE / f"perf025-{role.lower()}.json"


def capture(*command: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout.strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# --------------------------------------------------------------------------
# Structural bytecode checks
# --------------------------------------------------------------------------

REFLECTION_MARKERS = (
    "java/lang/reflect/",
    "java/lang/Class.forName",
    "java/lang/Class.getMethod",
    "java/lang/Class.getDeclaredMethod",
    "java/lang/invoke/MethodHandles$Lookup.find",
    "java/lang/invoke/MethodHandle.invoke",
)

PREPARE_CALL = re.compile(
    r"ProtosStandaloneHostedSession\.prepareTopLevel:"
)
PREPARED_INVOKE_CALL = re.compile(
    r"ProtosStandaloneHostedSession\$PreparedTopLevel\.invoke:\(\)"
)
DYNAMIC_CALL = re.compile(
    r"ProtosStandaloneHostedSession\.invokeTopLevel:"
)
MEASURE_CALL = re.compile(r"ProtosJvmVariantRunner\.measure:")
METHOD_HEADER = re.compile(r"^  \S.*;$")


def javap(class_file: Path) -> str:
    return capture("javap", "-c", "-p", "-v", str(class_file))


def methods(disassembly: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current: str | None = None

    for line in disassembly.splitlines():
        if METHOD_HEADER.match(line):
            current = line.strip()
            result[current] = []
        elif line and not line[0].isspace():
            # Class-level attributes (BootstrapMethods, InnerClasses, ...)
            # follow the last method and belong to no method body.
            current = None
        elif current is not None:
            result[current].append(line)

    return result


def calling(
    table: dict[str, list[str]],
    pattern: re.Pattern[str],
) -> dict[str, int]:
    return {
        name: count
        for name, body in table.items()
        if (count := sum(1 for line in body if pattern.search(line)))
    }


def require_no_reflection(name: str, disassembly: str) -> None:
    for marker in REFLECTION_MARKERS:
        if marker in disassembly:
            raise RuntimeError(f"{name}: reflection marker {marker}")


def check_dynamic_runner() -> None:
    files = sorted(
        (HARNESS_CLASSES / PACKAGE_PATH).glob("ProtosJvmVariantRunner*.class")
    )

    if not files:
        raise RuntimeError("compiled ProtosJvmVariantRunner missing")

    dynamic_calls: dict[str, int] = {}

    for path in files:
        text = javap(path)
        require_no_reflection(path.name, text)

        if "PreparedTopLevel" in text or "prepareTopLevel" in text:
            raise RuntimeError(
                f"{path.name}: references prepared API"
            )

        for method, count in calling(methods(text), DYNAMIC_CALL).items():
            dynamic_calls[f"{path.name}:{method}"] = count

    if len(dynamic_calls) != 1 or list(dynamic_calls.values()) != [1]:
        raise RuntimeError(
            f"dynamic runner invokeTopLevel sites: {dynamic_calls}"
        )

    (site,) = dynamic_calls

    if "lambda$" not in site:
        raise RuntimeError(
            f"dynamic invokeTopLevel outside invocation lambda: {site}"
        )

    print("pre_b_runner_prepared_api_dependency=NO")
    print("dynamic_runner_reflection=NO")
    print("dynamic_timed_invocation=session.invokeTopLevel(run)")


def check_prepared_runner(class_dir: Path) -> None:
    files = sorted(
        (class_dir / PACKAGE_PATH).glob("ProtosPreparedVariantRunner*.class")
    )

    if not files:
        raise RuntimeError(f"prepared runner classes missing: {class_dir}")

    prepare_sites: dict[str, int] = {}
    invoke_sites: dict[str, int] = {}
    main_body: list[str] = []

    for path in files:
        text = javap(path)
        require_no_reflection(path.name, text)

        if DYNAMIC_CALL.search(text):
            raise RuntimeError(
                f"{path.name}: prepared runner uses invokeTopLevel"
            )

        table = methods(text)
        prepare_sites.update(calling(table, PREPARE_CALL))
        invoke_sites.update(calling(table, PREPARED_INVOKE_CALL))

        for name, body in table.items():
            if " main(java.lang.String[])" in name:
                main_body = body

    if (
        len(prepare_sites) != 1
        or list(prepare_sites.values()) != [1]
        or " main(" not in next(iter(prepare_sites))
    ):
        raise RuntimeError(
            f"prepareTopLevel must be called once in main: {prepare_sites}"
        )

    if (
        len(invoke_sites) != 1
        or list(invoke_sites.values()) != [1]
        or "lambda$" not in next(iter(invoke_sites))
    ):
        raise RuntimeError(
            "PreparedTopLevel.invoke must be called directly once in the "
            f"invocation lambda: {invoke_sites}"
        )

    prepare_index = next(
        i for i, line in enumerate(main_body) if PREPARE_CALL.search(line)
    )
    measure_indexes = [
        i for i, line in enumerate(main_body) if MEASURE_CALL.search(line)
    ]

    if len(measure_indexes) != 1 or measure_indexes[0] < prepare_index:
        raise RuntimeError(
            "prepareTopLevel must precede the single measure call"
        )

    print("prepared_runner_direct_api=PreparedTopLevel.invoke")
    print("prepared_runner_reflection=NO")
    print("prepared_preparation_outside_timed_region=YES")


# --------------------------------------------------------------------------
# Variant identity
# --------------------------------------------------------------------------


def point(role: str) -> tuple[str, str, str, str]:
    for item in POINTS:
        if item[0] == role:
            return item

    raise KeyError(role)


def graalvm_version(classpath: str) -> str:
    versions = {
        Path(entry).parent.name
        for entry in classpath.split(":")
        if "/org/graalvm/" in entry
    }

    if versions != {GRAALVM_VERSION}:
        raise RuntimeError(
            f"GraalVM dependency versions {sorted(versions)} "
            f"!= {GRAALVM_VERSION}"
        )

    return GRAALVM_VERSION


def verify_checkout(role: str) -> dict[str, object]:
    _, revision, version, run_mode = point(role)
    repo = checkout(role)

    if not (repo / ".git").exists():
        raise RuntimeError(
            f"{role}: managed checkout missing: {repo}; "
            "run make perf025-d2-prepare"
        )

    dirty = capture(
        "git", "status", "--porcelain", "--untracked-files=no", cwd=repo
    )

    if dirty:
        raise RuntimeError(f"{role}: checkout has tracked changes\n{dirty}")

    actual_revision = capture("git", "rev-parse", "HEAD", cwd=repo)

    if actual_revision != revision:
        raise RuntimeError(
            f"{role}: revision {actual_revision} != {revision}"
        )

    actual_version = prepare.project_version(repo)

    if actual_version != version:
        raise RuntimeError(f"{role}: version {actual_version} != {version}")

    classes = repo / "target" / "classes"
    has_prepared_api = (classes / PREPARED_API_CLASS).is_file()

    if has_prepared_api != (run_mode == "prepared"):
        raise RuntimeError(
            f"{role}: prepared API presence {has_prepared_api} "
            f"inconsistent with run_mode={run_mode}"
        )

    classpath_file = AB_ROOT / "classpath" / f"{revision}.txt"
    dependency_cp = classpath_file.read_text(encoding="utf-8").strip()

    if not dependency_cp:
        raise RuntimeError(f"{role}: empty dependency classpath")

    entries = [str(classes), dependency_cp]
    prepared_class_dir = PREPARED_CLASSES / revision

    if run_mode == "prepared":
        entries.insert(0, str(prepared_class_dir))

    return {
        "role": role,
        "run_mode": run_mode,
        "repo": repo,
        "revision": revision,
        "version": version,
        "core": repo / "protos" / "lib" / "core",
        "core_sha256": prepare.sha256_tree(repo / "protos" / "lib" / "core"),
        "dependency_classpath_sha256": sha256_text(dependency_cp),
        "graalvm_version": graalvm_version(dependency_cp),
        "prepared_class_dir": prepared_class_dir,
        "classpath": ":".join([str(HARNESS_CLASSES), *entries]),
    }


def require_stamp(item: dict[str, object]) -> None:
    path = stamp_path(str(item["role"]))

    if not path.is_file():
        raise RuntimeError(
            f"{item['role']}: prepare stamp missing; "
            "run make perf025-d2-prepare"
        )

    state = json.loads(path.read_text(encoding="utf-8"))

    for key in (
        "revision",
        "version",
        "run_mode",
        "core_sha256",
        "dependency_classpath_sha256",
    ):
        if state.get(key) != item[key]:
            raise RuntimeError(
                f"{item['role']}: prepared {key} changed since prepare"
            )

    if item["run_mode"] == "prepared":
        class_file = (
            Path(str(item["prepared_class_dir"]))
            / PACKAGE_PATH
            / "ProtosPreparedVariantRunner.class"
        )

        if (
            not class_file.is_file()
            or state.get("prepared_runner_source_sha256")
            != prepare.sha256_file(PREPARED_SOURCE)
        ):
            raise RuntimeError(
                f"{item['role']}: prepared runner stale; "
                "run make perf025-d2-prepare"
            )


def harness_classes_sha256() -> str:
    return prepare.sha256_tree(HARNESS_CLASSES / PACKAGE_PATH)


def identity(
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
    source = source_for(workload, "protos")

    data: dict[str, object] = {
        "schema": 2,
        "measurement_definition": MEASUREMENT_DEFINITION,
        "experiment": EXPERIMENT,
        "mode": "jvm",
        "profile": profile,
        "language": "protos",
        "role": item["role"],
        "run_mode": item["run_mode"],
        "workload": workload,
        "source_sha256": prepare.sha256_file(source),
        "harness_revision": jvm_matrix.benchmark_revision(),
        "harness_dirty": jvm_matrix.benchmark_dirty(),
        "ab_sha256": prepare.sha256_file(Path(__file__)),
        "matrix_sha256": prepare.sha256_file(TRUFFLE / "jvm_matrix.py"),
        "catalog_sha256": prepare.sha256_file(
            TRUFFLE / "workloads" / "catalog.json"
        ),
        "runner_sha256": prepare.sha256_file(DYNAMIC_SOURCE),
        "runner_classes_sha256": toolchain["runner_classes_sha256"],
        "protos_revision": item["revision"],
        "protos_version": item["version"],
        "protos_core_sha256": item["core_sha256"],
        "protos_dependency_classpath_sha256":
            item["dependency_classpath_sha256"],
        "graalvm_version": item["graalvm_version"],
        "java_version": toolchain["java_version"],
        "cpu": cpu,
        "cpu_siblings": siblings,
        "cpu_model": jvm_matrix.cpu_model(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "warmup_iterations": warmup,
        "steady_iterations": steady,
        "sample_calls": sample_calls,
    }

    if item["run_mode"] == "prepared":
        data["prepared_runner_sha256"] = prepare.sha256_file(
            PREPARED_SOURCE
        )
        data["prepared_runner_classes_sha256"] = prepare.sha256_tree(
            Path(str(item["prepared_class_dir"]))
        )
        data["javac_version"] = toolchain["javac_version"]

    if profile == "benchmark":
        data["steady_state_admission"] = {
            "window": jvm_matrix.STABILITY_WINDOW,
            "median_drift_pct_max": jvm_matrix.STABILITY_MEDIAN_DRIFT_PCT,
            "mad_pct_max": jvm_matrix.STABILITY_MAD_PCT,
            "max_internal_gap_pct":
                jvm_matrix.STABILITY_MAX_INTERNAL_GAP_PCT,
            "min_gap_cluster_size":
                jvm_matrix.STABILITY_MIN_GAP_CLUSTER_SIZE,
        }
    else:
        data["steady_state_admission"] = "none-smoke"

    return data


def toolchain_identity() -> dict[str, str]:
    return {
        "java_version": capture("java", "-version"),
        "javac_version": capture("javac", "-version"),
        "runner_classes_sha256": harness_classes_sha256(),
    }


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------


def compile_harness() -> None:
    subprocess.run(
        ["mvn", "-q", "-f", str(TRUFFLE / "pom.xml"), "compile"],
        cwd=ROOT,
        check=True,
    )
    print("pre_b_compile_compatibility=PASS pinned_maven_protos="
          + jvm_matrix.protos_maven_version())


def check_contract() -> None:
    roles = tuple(item[0] for item in POINTS)

    if roles != ("PRE_A", "A", "B", "FINAL"):
        raise RuntimeError(f"unexpected PERF025 roles: {roles}")

    for role, revision, version, run_mode in POINTS:
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise RuntimeError(f"{role}: revision is not a full SHA")

        if run_mode != EXPECTED_MODES[role]:
            raise RuntimeError(f"{role}: run_mode {run_mode}")

        if not version.endswith("-SNAPSHOT"):
            raise RuntimeError(f"{role}: version {version}")

        print(f"{role.lower()}_mode={run_mode}")

    if len(set(item[1] for item in POINTS)) != len(POINTS):
        raise RuntimeError("PERF025 revisions are not distinct")

    if len(WORKLOADS) != 3 or len(set(WORKLOADS)) != 3:
        raise RuntimeError("PERF025 workload selection must be exactly 3")

    for workload in WORKLOADS:
        if workload not in catalog():
            raise RuntimeError(f"{workload}: not in workload catalog")

        if jvm_sample_calls(workload) != CATALOG_SAMPLE_CALLS:
            raise RuntimeError(
                f"{workload}: catalog sample_calls != "
                f"{CATALOG_SAMPLE_CALLS}"
            )

        expected_result(workload)

    print("selected_workloads=" + ",".join(WORKLOADS))
    print(f"catalog_sample_calls={CATALOG_SAMPLE_CALLS}")
    print(f"smoke_sample_calls={SMOKE_SAMPLE_CALLS}")
    print(f"reference_sample_calls={REFERENCE_SAMPLE_CALLS}")

    minimum_admission_samples = jvm_matrix.STABILITY_WINDOW * 2

    if (
        REFERENCE_WARMUP < minimum_admission_samples
        or REFERENCE_STEADY < minimum_admission_samples
    ):
        raise RuntimeError(
            "PERF025 reference sample counts are too small for "
            "the reused stability window"
        )

    print(
        f"reference_warmup={REFERENCE_WARMUP} "
        f"reference_steady={REFERENCE_STEADY}"
    )

    if EXPECTED_OBSERVATIONS != 12:
        raise RuntimeError("expected reference observations != 12")

    print(f"expected_reference_observations={EXPECTED_OBSERVATIONS}")

    stable = jvm_matrix.reference_admission(
        [1000] * REFERENCE_WARMUP,
        [1000] * REFERENCE_STEADY,
    )
    bimodal = jvm_matrix.reference_admission(
        [1000] * REFERENCE_WARMUP,
        [1000] * jvm_matrix.STABILITY_WINDOW
        + [2000] * jvm_matrix.STABILITY_WINDOW,
    )

    if stable["status"] != "PASS" or bimodal["status"] != "NOT_STABLE":
        raise RuntimeError("reused stability admission self-test failed")

    print("stability_admission=jvm_matrix.reference_admission self_test=PASS")


def check_identity_contract() -> None:
    toolchain = {
        "java_version": "x",
        "javac_version": "x",
        "runner_classes_sha256": "x",
    }
    items = {
        mode: {
            "role": "X",
            "run_mode": mode,
            "revision": "0" * 40,
            "version": "v",
            "core_sha256": "c",
            "dependency_classpath_sha256": "d",
            "graalvm_version": GRAALVM_VERSION,
            "prepared_class_dir": HARNESS_CLASSES,
        }
        for mode in ("dynamic", "prepared")
    }
    identities = {
        mode: identity(
            item,
            WORKLOADS[0],
            0,
            [0],
            "benchmark",
            REFERENCE_WARMUP,
            REFERENCE_STEADY,
            REFERENCE_SAMPLE_CALLS,
            toolchain,
        )
        for mode, item in items.items()
    }

    for mode, data in identities.items():
        for key in (
            "run_mode",
            "sample_calls",
            "harness_revision",
            "harness_dirty",
            "protos_revision",
            "protos_version",
            "protos_core_sha256",
            "source_sha256",
            "steady_state_admission",
        ):
            if key not in data:
                raise RuntimeError(f"identity missing {key}")

        if data["run_mode"] != mode:
            raise RuntimeError("identity run_mode mismatch")

    if jvm_matrix.cache_key(identities["dynamic"]) == jvm_matrix.cache_key(
        identities["prepared"]
    ):
        raise RuntimeError("dynamic and prepared cache keys collide")

    print("run_mode_in_identity=YES run_mode_in_cache_key=YES")
    print("sample_calls_in_identity=YES")
    print("harness_revision_in_identity=YES")


def check_results_untouched() -> None:
    changed = capture(
        "git",
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        "results",
        cwd=ROOT,
    )

    if changed:
        raise RuntimeError(f"results/ has local changes:\n{changed}")

    print("historical_results_mutated=NO")

    import retain_results

    retain_results.verify_retained("PERF023")

    destination = RESULTS / RETAINED_DESTINATION

    if destination.exists():
        retain_results.verify_retained(RETAINED_DESTINATION)
    else:
        print(f"{RETAINED_DESTINATION}=ABSENT")


def stage_validate() -> None:
    check_contract()
    check_identity_contract()
    compile_harness()
    check_dynamic_runner()
    check_results_untouched()
    print("perf025_validate=PASS")


def compile_prepared_runner(
    item: dict[str, object],
) -> None:
    target = Path(str(item["prepared_class_dir"]))

    if target.exists():
        shutil.rmtree(target)

    target.mkdir(parents=True)

    subprocess.run(
        [
            "javac",
            "-proc:none",
            "-d",
            str(target),
            "-cp",
            str(item["classpath"]),
            str(PREPARED_SOURCE),
        ],
        cwd=ROOT,
        check=True,
    )


def stage_prepare() -> None:
    prepare.require_tools()

    for tool in ("javac", "javap"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"missing required tool: {tool}")

    print("java=" + capture("java", "-version").splitlines()[0])
    print("javac=" + capture("javac", "-version"))

    compile_harness()
    check_dynamic_runner()
    STATE.mkdir(parents=True, exist_ok=True)

    for role, revision, version, run_mode in POINTS:
        repo = prepare.ensure_checkout(checkout_name(role), revision, version)
        prepare.ensure_ab_variant(repo, revision)

        item = verify_checkout(role)

        if run_mode == "prepared":
            compile_prepared_runner(item)
            check_prepared_runner(Path(str(item["prepared_class_dir"])))

        state = {
            key: item[key]
            for key in (
                "role",
                "run_mode",
                "revision",
                "version",
                "core_sha256",
                "dependency_classpath_sha256",
                "graalvm_version",
            )
        }

        if run_mode == "prepared":
            state["prepared_runner_source_sha256"] = prepare.sha256_file(
                PREPARED_SOURCE
            )

        stamp_path(role).write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        print(
            f"variant={role} revision={revision} version={version} "
            f"run_mode={run_mode} core_sha256={item['core_sha256']} "
            f"graalvm={item['graalvm_version']} status=READY"
        )

    print("perf025_prepare=PASS")


def execute(
    item: dict[str, object],
    workload: str,
    cpu: int,
    warmup: int,
    steady: int,
    sample_calls: int,
) -> str:
    main_class = (
        PREPARED_CLASS if item["run_mode"] == "prepared" else DYNAMIC_CLASS
    )

    result = subprocess.run(
        [
            "taskset",
            "-c",
            str(cpu),
            "java",
            "-cp",
            str(item["classpath"]),
            main_class,
            str(item["core"]),
            str(source_for(workload, "protos")),
            str(warmup),
            str(steady),
            str(sample_calls),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.returncode != 0:
        print(result.stdout, end="")
        raise RuntimeError(
            f"{item['role']}/{item['run_mode']}/{workload}: execution failed"
        )

    return result.stdout


def require_output_contract(
    item: dict[str, object],
    workload: str,
    output: str,
    warmup: int,
    steady: int,
    sample_calls: int,
) -> dict[str, object]:
    parsed = jvm_matrix.parse_output(output)
    label = f"{item['role']}/{item['run_mode']}/{workload}"

    if parsed is None:
        raise RuntimeError(f"{label}: cannot parse output")

    lines = set(output.splitlines())

    if f"run_mode={item['run_mode']}" not in lines:
        raise RuntimeError(f"{label}: run_mode marker missing")

    has_prepare = any(line.startswith("prepare_ns=") for line in lines)

    if has_prepare != (item["run_mode"] == "prepared"):
        raise RuntimeError(f"{label}: prepare_ns marker inconsistent")

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


def stage_measure(profile: str) -> None:
    if profile == "benchmark":
        jvm_matrix.require_clean_reference_harness()
        revision = jvm_matrix.benchmark_revision()

        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise RuntimeError("harness revision is not a full SHA")

        warmup = REFERENCE_WARMUP
        steady = REFERENCE_STEADY
        sample_calls = REFERENCE_SAMPLE_CALLS
    else:
        warmup, steady = SMOKE_WARMUP, SMOKE_STEADY
        sample_calls = SMOKE_SAMPLE_CALLS

    check_contract()
    compile_harness()
    check_dynamic_runner()

    items = [verify_checkout(role) for role, *_ in POINTS]

    for item in items:
        require_stamp(item)

        if item["run_mode"] == "prepared":
            check_prepared_runner(Path(str(item["prepared_class_dir"])))

    toolchain = toolchain_identity()
    cpu, siblings = jvm_matrix.choose_cpu()

    print(f"mode=jvm-protos-ab experiment={EXPERIMENT} profile={profile}")
    print(f"cpu={cpu}")
    print(f"cpu_siblings={','.join(map(str, siblings))}")
    print(f"sample_calls={sample_calls}")

    accepted: dict[tuple[str, str], float] = {}
    not_stable: list[str] = []
    passed = 0

    for item in items:
        for workload in WORKLOADS:
            ident = identity(
                item,
                workload,
                cpu,
                siblings,
                profile,
                warmup,
                steady,
                sample_calls,
                toolchain,
            )
            key = jvm_matrix.cache_key(ident)
            cache_file = jvm_matrix.CACHE / f"{key}.json"
            label = f"{item['role']}/{item['run_mode']}/{workload}"

            print()
            print(f"=== {label} {str(item['revision'])[:12]} ===")

            if profile == "benchmark" and cache_file.is_file():
                print("cache=hit")
                output = json.loads(cache_file.read_text(encoding="utf-8"))[
                    "output"
                ]
            else:
                if profile == "benchmark":
                    print("cache=miss")
                else:
                    print("cache=not-used-smoke")

                output = execute(
                    item,
                    workload,
                    cpu,
                    warmup,
                    steady,
                    sample_calls,
                )

            parsed = require_output_contract(
                item,
                workload,
                output,
                warmup,
                steady,
                sample_calls,
            )
            _, admission = jvm_matrix.summarize_output(output, profile)
            passed += 1

            if profile != "benchmark":
                continue

            if admission is None or admission["status"] != "PASS":
                if cache_file.is_file():
                    raise RuntimeError(
                        f"{label}: cached reference is not admitted"
                    )

                rejected = jvm_matrix.write_rejected_observation(
                    key, ident, admission, output
                )
                print("rejected_raw=" + str(rejected.relative_to(ROOT)))
                not_stable.append(label)
                continue

            if not cache_file.is_file():
                jvm_matrix.CACHE.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(
                    json.dumps(
                        {
                            "identity": ident,
                            "admission": admission,
                            "output": output,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            accepted[(str(item["role"]), workload)] = amortized_p50(parsed)

    print()
    print(f"cases_passed_correctness={passed}/{EXPECTED_OBSERVATIONS}")

    if passed != EXPECTED_OBSERVATIONS:
        raise RuntimeError("PERF025 matrix incomplete")

    if profile != "benchmark":
        print("timing_interpretation=NONE-smoke")
        print("perf025_smoke=PASS")
        return

    print("=== PERF025 INTERPRETATION ===")
    print(f"sign_convention={SIGN_CONVENTION}")

    for workload in WORKLOADS:
        print(f"workload={workload}")

        for role, *_ in POINTS:
            value = accepted.get((role, workload))
            shown = "NOT_ADMITTED" if value is None else f"{value:.1f}"
            print(
                f"  {role}/{EXPECTED_MODES[role]} "
                f"steady_amortized_p50_ns={shown}"
            )

        for name, baseline, candidate in DELTAS:
            base = accepted.get((baseline, workload))
            cand = accepted.get((candidate, workload))

            if base is None or cand is None:
                print(f"  {name}=NOT_AVAILABLE")
            else:
                print(
                    f"  {name}={(cand / base - 1.0) * 100.0:+.2f}% "
                    f"({candidate}/{EXPECTED_MODES[candidate]} vs "
                    f"{baseline}/{EXPECTED_MODES[baseline]})"
                )

        print(
            "  FINAL_CURRENT_STATE="
            "primary-accumulated-comparison-without-slice-attribution"
        )

    if not_stable:
        raise RuntimeError(
            "reference_admission=NOT_STABLE for: "
            + ", ".join(not_stable)
            + "; retained as rejected local raw, not cached"
        )

    print(f"accepted_reference_observations={len(accepted)}")
    print("perf025_reference=PASS")


def main(stage: str) -> None:
    if stage == "validate":
        stage_validate()
    elif stage == "prepare":
        stage_prepare()
    elif stage in {"smoke", "benchmark"}:
        stage_measure(stage)
    else:
        raise SystemExit(
            "usage: jvm_protos_ab.py perf025 "
            "<validate|prepare|smoke|benchmark>"
        )
