#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""PERF025-E3 exact-revision prepared-call carrier-transport A/B.

Isolates PERF025-E2 (guest carrier transport cleanup) by comparing E2 against
its exact parent, both through the unchanged ProtosPreparedVariantRunner.
Structural bytecode checks, prepared-runner compilation, output contract and
amortization are reused from perf025_ab.py; exact checkout and variant
preparation from prepare.py; CPU selection, harness identity, stability
admission and rejected-evidence handling from jvm_matrix.py. The historical
PERF025-D3 matrix (jvm-protos-session-ab-v3) is not modified.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import jvm_matrix
import perf025_ab
import prepare
from workload_catalog import (
    catalog,
    expected_result,
    jvm_sample_calls,
    source_for,
)

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
AB_ROOT = perf025_ab.AB_ROOT
WORK = ROOT / ".work" / "perf025-e3"
PREPARED_CLASSES = WORK / "prepared-runner"
STATE = ROOT / ".work" / "truffle-prepare"
RESULTS = ROOT / "results"

MEASUREMENT_DEFINITION = "jvm-protos-carrier-e2-ab-v1"
FORBIDDEN_DEFINITIONS = (
    "jvm-protos-session-ab-v1",
    "jvm-protos-session-ab-v2",
    "jvm-protos-session-ab-v3",
    "jvm-cross-truffle-current-v1",
    "jvm-cross-truffle-current-v2",
    "jvm-cross-truffle-current-v3",
)
EXPERIMENT = "PERF025-E3"
WORK_ITEM = "PERF025-E3"
RETENTION_PROFILE = "perf025-e3"
RETAINED_DESTINATION = "perf025-e3"
RETAINED_CLASS = "jvm-carrier-e2-ab-v1-reference"
HISTORICAL_WORK_ITEMS = ("PERF023", "PERF025-D3", "PERF024-REBASELINE")

GRAALVM_VERSION = "25.4.4.1.1"
RUN_MODE = "prepared"

# role, Protos revision, Protos version. PRE_E2 is E2's exact parent, so the
# unrelated BUG014 commit is present in both comparison points.
POINTS = (
    (
        "PRE_E2",
        "c1eb2c2e1a811d70fcf09f5526217c1aaf14d141",
        "0.3.144-SNAPSHOT",
    ),
    (
        "E2",
        "ff618f0dd8ef680f7884c9145552f77912f040a2",
        "0.3.145-SNAPSHOT",
    ),
)

WORKLOADS = (
    "primitive-return-literal",
    "primitive-closure-call",
    "primitive-method-call",
)

# Reused unchanged from the final PERF025-D3 reference policy.
CATALOG_SAMPLE_CALLS = perf025_ab.CATALOG_SAMPLE_CALLS
SMOKE_SAMPLE_CALLS = perf025_ab.SMOKE_SAMPLE_CALLS
SMOKE_WARMUP = perf025_ab.SMOKE_WARMUP
SMOKE_STEADY = perf025_ab.SMOKE_STEADY
REFERENCE_SAMPLE_CALLS = perf025_ab.REFERENCE_SAMPLE_CALLS
REFERENCE_WARMUP = perf025_ab.REFERENCE_WARMUP
REFERENCE_STEADY = perf025_ab.REFERENCE_STEADY
REFERENCE_ADMISSION_SCOPE = perf025_ab.REFERENCE_ADMISSION_SCOPE
SIGN_CONVENTION = perf025_ab.SIGN_CONVENTION

EXPECTED_OBSERVATIONS = len(POINTS) * len(WORKLOADS)

DELTA = ("E2_DELTA", "PRE_E2", "E2")

capture = perf025_ab.capture


def checkout_name(role: str) -> str:
    return f"perf025-e3-{role.lower().replace('_', '-')}"


def stamp_path(role: str) -> Path:
    return STATE / f"perf025-e3-{role.lower()}.json"


def point(role: str) -> tuple[str, str, str]:
    for item in POINTS:
        if item[0] == role:
            return item

    raise KeyError(role)


# --------------------------------------------------------------------------
# Contract checks
# --------------------------------------------------------------------------


def check_contract() -> None:
    if MEASUREMENT_DEFINITION in FORBIDDEN_DEFINITIONS:
        raise RuntimeError("measurement definition collides")

    if MEASUREMENT_DEFINITION == perf025_ab.MEASUREMENT_DEFINITION:
        raise RuntimeError("measurement definition collides with PERF025-D3")

    if tuple(item[0] for item in POINTS) != ("PRE_E2", "E2"):
        raise RuntimeError("unexpected PERF025-E3 roles")

    if POINTS != (
        (
            "PRE_E2",
            "c1eb2c2e1a811d70fcf09f5526217c1aaf14d141",
            "0.3.144-SNAPSHOT",
        ),
        (
            "E2",
            "ff618f0dd8ef680f7884c9145552f77912f040a2",
            "0.3.145-SNAPSHOT",
        ),
    ):
        raise RuntimeError("PERF025-E3 revision/version pin changed")

    for role, revision, version in POINTS:
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise RuntimeError(f"{role}: revision is not a full SHA")

        if revision in {item[1] for item in perf025_ab.POINTS}:
            raise RuntimeError(f"{role}: reuses a PERF025-D3 revision")

        print(f"{role}_REVISION={revision}")
        print(f"{role}_VERSION={version}")
        print(f"{role}_RUN_MODE={RUN_MODE}")

    if WORKLOADS != perf025_ab.WORKLOADS:
        raise RuntimeError("PERF025-E3 workloads differ from PERF025-D3")

    for workload in WORKLOADS:
        if workload not in catalog():
            raise RuntimeError(f"{workload}: not in workload catalog")

        if jvm_sample_calls(workload) != CATALOG_SAMPLE_CALLS:
            raise RuntimeError(f"{workload}: catalog sample_calls changed")

        expected_result(workload)

    if (
        REFERENCE_SAMPLE_CALLS,
        REFERENCE_WARMUP,
        REFERENCE_STEADY,
        REFERENCE_ADMISSION_SCOPE,
    ) != (10_000, 50, 10, "steady-only"):
        raise RuntimeError("PERF025-E3 reference policy changed")

    if (
        jvm_matrix.STABILITY_WINDOW,
        jvm_matrix.STABILITY_MEDIAN_DRIFT_PCT,
        jvm_matrix.STABILITY_MAD_PCT,
        jvm_matrix.STABILITY_MAX_INTERNAL_GAP_PCT,
        jvm_matrix.STABILITY_MIN_GAP_CLUSTER_SIZE,
    ) != (5, 15, 20, 20, 3):
        raise RuntimeError("reused stability thresholds changed")

    if EXPECTED_OBSERVATIONS != 6:
        raise RuntimeError("expected reference observations != 6")

    stable = jvm_matrix.stability_window([1000] * REFERENCE_STEADY)
    bimodal = jvm_matrix.stability_window(
        [1000] * jvm_matrix.STABILITY_WINDOW
        + [2000] * jvm_matrix.STABILITY_WINDOW
    )

    if stable["status"] != "PASS" or bimodal["status"] != "NOT_STABLE":
        raise RuntimeError("reused steady stability self-test failed")

    print(f"measurement_definition={MEASUREMENT_DEFINITION}")
    print("selected_workloads=" + ",".join(WORKLOADS))
    print(f"graalvm_version={GRAALVM_VERSION}")
    print(
        f"reference_sample_calls={REFERENCE_SAMPLE_CALLS} "
        f"reference_warmup={REFERENCE_WARMUP} "
        f"reference_steady={REFERENCE_STEADY} "
        f"reference_admission_scope={REFERENCE_ADMISSION_SCOPE}"
    )
    print(f"expected_reference_observations={EXPECTED_OBSERVATIONS}")
    print("stability_admission=jvm_matrix.stability_window self_test=PASS")


def check_historical_d3() -> None:
    import retain_results

    if (
        perf025_ab.MEASUREMENT_DEFINITION != "jvm-protos-session-ab-v3"
        or perf025_ab.EXPECTED_OBSERVATIONS != 12
        or perf025_ab.RETAINED_DESTINATION != "perf025-d3"
        or perf025_ab.GRAALVM_VERSION != GRAALVM_VERSION
    ):
        raise RuntimeError("historical PERF025-D3 harness contract drifted")

    profiles = retain_results.RETENTION_PROFILES

    if profiles.get("perf025", {}).get("expected_classes") != {
        "jvm-ab-v3-reference": 12,
    }:
        raise RuntimeError("historical perf025 retention profile changed")

    if profiles.get(RETENTION_PROFILE, {}).get("expected_classes") != {
        RETAINED_CLASS: EXPECTED_OBSERVATIONS,
    }:
        raise RuntimeError(f"{RETENTION_PROFILE} retention profile mismatch")

    if retain_results.CARRIER_E2_DEFINITION != MEASUREMENT_DEFINITION:
        raise RuntimeError("retention measurement definition mismatch")

    print("historical_d3_contract=UNCHANGED")
    print(
        f"retention_profile={RETENTION_PROFILE} "
        f"{RETAINED_CLASS}={EXPECTED_OBSERVATIONS}"
    )


def check_results_untouched() -> None:
    changed = capture(
        "git", "status", "--porcelain", "--untracked-files=all",
        "--", "results", cwd=ROOT,
    )

    if changed:
        raise RuntimeError(f"results/ has local changes:\n{changed}")

    print("historical_results_mutated=NO")

    import retain_results

    for work_item in HISTORICAL_WORK_ITEMS:
        if (RESULTS / work_item.lower()).exists():
            retain_results.verify_retained(work_item)
        elif work_item in ("PERF023", "PERF025-D3"):
            raise RuntimeError(f"historical evidence missing: {work_item}")

    if (RESULTS / RETAINED_DESTINATION).exists():
        retain_results.verify_retained(WORK_ITEM)
    else:
        print(f"{RETAINED_DESTINATION}=ABSENT")


def check_runner_source() -> None:
    text = perf025_ab.PREPARED_SOURCE.read_text(encoding="utf-8")

    if text.count('prepareTopLevel("run")') != 1:
        raise RuntimeError("prepared runner must prepare run exactly once")

    if "prepared.invoke()" not in text or "invokeTopLevel" in text:
        raise RuntimeError("prepared runner timed operation changed")

    if "java.lang.reflect" in text or "MethodHandle" in text:
        raise RuntimeError("prepared runner uses reflection")

    print("prepared_runner_source=ProtosPreparedVariantRunner unchanged-role")


# --------------------------------------------------------------------------
# Variant identity
# --------------------------------------------------------------------------


def verify_checkout(role: str) -> dict[str, object]:
    _, revision, version = point(role)
    repo = AB_ROOT / checkout_name(role)

    if not (repo / ".git").exists():
        raise RuntimeError(
            f"{role}: managed checkout missing: {repo}; "
            "run make perf025-e3-prepare"
        )

    dirty = capture(
        "git", "status", "--porcelain", "--untracked-files=no", cwd=repo
    )

    if dirty:
        raise RuntimeError(f"{role}: checkout has tracked changes\n{dirty}")

    actual_revision = capture("git", "rev-parse", "HEAD", cwd=repo)

    if actual_revision != revision:
        raise RuntimeError(f"{role}: revision {actual_revision} != {revision}")

    actual_version = prepare.project_version(repo)

    if actual_version != version:
        raise RuntimeError(f"{role}: version {actual_version} != {version}")

    classes = repo / "target" / "classes"

    if not (classes / perf025_ab.PREPARED_API_CLASS).is_file():
        raise RuntimeError(f"{role}: PreparedTopLevel API missing")

    classpath_file = AB_ROOT / "classpath" / f"{revision}.txt"

    if not classpath_file.is_file():
        raise RuntimeError(f"{role}: dependency classpath missing")

    dependency_cp = classpath_file.read_text(encoding="utf-8").strip()

    if not dependency_cp:
        raise RuntimeError(f"{role}: empty dependency classpath")

    prepared_class_dir = PREPARED_CLASSES / revision
    core = repo / "protos" / "lib" / "core"

    return {
        "role": role,
        "run_mode": RUN_MODE,
        "repo": repo,
        "revision": revision,
        "version": version,
        "core": core,
        "core_sha256": prepare.sha256_tree(core),
        "dependency_classpath_sha256": perf025_ab.sha256_text(dependency_cp),
        "graalvm_version": perf025_ab.graalvm_version(dependency_cp),
        "prepared_class_dir": prepared_class_dir,
        "classpath": ":".join(
            [
                str(prepared_class_dir),
                str(perf025_ab.HARNESS_CLASSES),
                str(classes),
                dependency_cp,
            ]
        ),
    }


def require_stamp(item: dict[str, object]) -> None:
    path = stamp_path(str(item["role"]))

    if not path.is_file():
        raise RuntimeError(
            f"{item['role']}: prepare stamp missing; "
            "run make perf025-e3-prepare"
        )

    state = json.loads(path.read_text(encoding="utf-8"))

    for key in (
        "revision",
        "version",
        "run_mode",
        "core_sha256",
        "dependency_classpath_sha256",
        "graalvm_version",
    ):
        if state.get(key) != item[key]:
            raise RuntimeError(
                f"{item['role']}: prepared {key} changed since prepare"
            )

    class_file = (
        Path(str(item["prepared_class_dir"]))
        / perf025_ab.PACKAGE_PATH
        / "ProtosPreparedVariantRunner.class"
    )

    if (
        not class_file.is_file()
        or state.get("prepared_runner_source_sha256")
        != prepare.sha256_file(perf025_ab.PREPARED_SOURCE)
    ):
        raise RuntimeError(
            f"{item['role']}: prepared runner stale; "
            "run make perf025-e3-prepare"
        )


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
    data: dict[str, object] = {
        "schema": 1,
        "measurement_definition": MEASUREMENT_DEFINITION,
        "experiment": EXPERIMENT,
        "mode": "jvm",
        "profile": profile,
        "language": "protos",
        "role": item["role"],
        "run_mode": item["run_mode"],
        "workload": workload,
        "source_sha256": prepare.sha256_file(source_for(workload, "protos")),
        "harness_revision": jvm_matrix.benchmark_revision(),
        "harness_dirty": jvm_matrix.benchmark_dirty(),
        "e3_sha256": prepare.sha256_file(Path(__file__)),
        "ab_sha256": prepare.sha256_file(Path(perf025_ab.__file__)),
        "matrix_sha256": prepare.sha256_file(TRUFFLE / "jvm_matrix.py"),
        "catalog_sha256": prepare.sha256_file(
            TRUFFLE / "workloads" / "catalog.json"
        ),
        "runner_sha256": prepare.sha256_file(perf025_ab.DYNAMIC_SOURCE),
        "runner_classes_sha256": toolchain["runner_classes_sha256"],
        "prepared_runner_sha256": prepare.sha256_file(
            perf025_ab.PREPARED_SOURCE
        ),
        "prepared_runner_classes_sha256": prepare.sha256_tree(
            Path(str(item["prepared_class_dir"]))
        ),
        "protos_revision": item["revision"],
        "protos_version": item["version"],
        "protos_core_sha256": item["core_sha256"],
        "protos_dependency_classpath_sha256":
            item["dependency_classpath_sha256"],
        "graalvm_version": item["graalvm_version"],
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

    if profile == "benchmark":
        data["steady_state_admission"] = {
            "scope": REFERENCE_ADMISSION_SCOPE,
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


def check_identity_contract() -> None:
    toolchain = {
        "java_version": "x",
        "javac_version": "x",
        "runner_classes_sha256": "x",
    }
    keys = set()

    for role, revision, version in POINTS:
        item = {
            "role": role,
            "run_mode": RUN_MODE,
            "revision": revision,
            "version": version,
            "core_sha256": "c",
            "dependency_classpath_sha256": "d",
            "graalvm_version": GRAALVM_VERSION,
            "prepared_class_dir": perf025_ab.HARNESS_CLASSES,
        }

        for workload in WORKLOADS:
            data = identity(
                item, workload, 0, [0], "benchmark",
                REFERENCE_WARMUP, REFERENCE_STEADY,
                REFERENCE_SAMPLE_CALLS, toolchain,
            )

            for key in (
                "measurement_definition", "profile", "role", "run_mode",
                "workload", "source_sha256", "harness_revision",
                "harness_dirty", "protos_revision", "protos_version",
                "protos_core_sha256", "graalvm_version", "java_version",
                "javac_version", "prepared_runner_sha256", "cpu",
                "cpu_siblings", "sample_calls", "steady_state_admission",
            ):
                if key not in data:
                    raise RuntimeError(f"identity missing {key}")

            if data["measurement_definition"] != MEASUREMENT_DEFINITION:
                raise RuntimeError("identity measurement definition mismatch")

            keys.add(jvm_matrix.cache_key(data))

    if len(keys) != EXPECTED_OBSERVATIONS:
        raise RuntimeError("identity cache keys collide")

    print(
        "identity_fields=complete cache_keys_distinct="
        f"{EXPECTED_OBSERVATIONS}"
    )


def toolchain_identity() -> dict[str, str]:
    return perf025_ab.toolchain_identity()


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------


def compile_harness() -> None:
    subprocess.run(
        ["mvn", "-q", "-f", str(TRUFFLE / "pom.xml"), "compile"],
        cwd=ROOT,
        check=True,
    )
    print("harness_compile=PASS")


def stage_validate() -> None:
    check_contract()
    check_runner_source()
    check_identity_contract()
    check_historical_d3()
    check_results_untouched()
    print("perf025_e3_validate=PASS")


def stage_prepare() -> None:
    prepare.require_tools()

    for tool in ("javac", "javap"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"missing required tool: {tool}")

    print("java=" + capture("java", "-version").splitlines()[0])
    print("javac=" + capture("javac", "-version"))

    check_contract()
    check_runner_source()
    compile_harness()
    STATE.mkdir(parents=True, exist_ok=True)

    for role, revision, version in POINTS:
        repo = prepare.ensure_checkout(checkout_name(role), revision, version)
        prepare.ensure_ab_variant(repo, revision)

        item = verify_checkout(role)
        perf025_ab.compile_prepared_runner(item)
        perf025_ab.check_prepared_runner(Path(str(item["prepared_class_dir"])))

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
        state["prepared_runner_source_sha256"] = prepare.sha256_file(
            perf025_ab.PREPARED_SOURCE
        )

        stamp_path(role).write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        print(
            f"variant={role} revision={revision} version={version} "
            f"run_mode={RUN_MODE} core_sha256={item['core_sha256']} "
            f"graalvm={item['graalvm_version']} status=READY"
        )

    print("perf025_e3_prepare=PASS")


def stage_measure(profile: str) -> None:
    if profile == "benchmark":
        jvm_matrix.require_clean_reference_harness()
        revision = jvm_matrix.benchmark_revision()

        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise RuntimeError("harness revision is not a full SHA")

        if jvm_matrix.benchmark_dirty():
            raise RuntimeError("reference requires harness_dirty=false")

        print(f"harness_revision={revision} harness_dirty=false")

        warmup = REFERENCE_WARMUP
        steady = REFERENCE_STEADY
        sample_calls = REFERENCE_SAMPLE_CALLS
    else:
        warmup, steady = SMOKE_WARMUP, SMOKE_STEADY
        sample_calls = SMOKE_SAMPLE_CALLS

    check_contract()
    check_runner_source()
    check_historical_d3()
    compile_harness()

    items = [verify_checkout(role) for role, *_ in POINTS]

    for item in items:
        require_stamp(item)
        perf025_ab.check_prepared_runner(Path(str(item["prepared_class_dir"])))

    toolchain = toolchain_identity()
    cpu, siblings = jvm_matrix.choose_cpu()

    print(f"mode=jvm-protos-ab experiment={EXPERIMENT} profile={profile}")
    print(f"cpu={cpu}")
    print(f"cpu_siblings={','.join(map(str, siblings))}")
    print(f"sample_calls={sample_calls}")

    if profile == "benchmark":
        print(f"reference_admission_scope={REFERENCE_ADMISSION_SCOPE}")

    accepted: dict[tuple[str, str], float] = {}
    not_stable: list[str] = []
    passed = 0

    for item in items:
        for workload in WORKLOADS:
            ident = identity(
                item, workload, cpu, siblings, profile,
                warmup, steady, sample_calls, toolchain,
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
                print(
                    "cache=miss" if profile == "benchmark"
                    else "cache=not-used-smoke"
                )
                output = perf025_ab.execute(
                    item, workload, cpu, warmup, steady, sample_calls
                )

            parsed = perf025_ab.require_output_contract(
                item, workload, output, warmup, steady, sample_calls
            )
            _, admission = jvm_matrix.summarize_output(
                output,
                profile,
                admission_scope=(
                    REFERENCE_ADMISSION_SCOPE
                    if profile == "benchmark"
                    else "warmup-and-steady"
                ),
            )
            passed += 1
            print("correctness=PASS")

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
                            "correctness": "PASS",
                            "admission": admission,
                            "output": output,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            accepted[(str(item["role"]), workload)] = (
                perf025_ab.amortized_p50(parsed)
            )

    print()

    for role, revision, version in POINTS:
        print(f"{role}_REVISION={revision}")
        print(f"{role}_VERSION={version}")
        print(f"{role}_RUN_MODE={RUN_MODE}")

    print(f"cases_passed_correctness={passed}/{EXPECTED_OBSERVATIONS}")

    if passed != EXPECTED_OBSERVATIONS:
        raise RuntimeError("PERF025-E3 matrix incomplete")

    if profile != "benchmark":
        print("timing_interpretation=NONE-smoke")
        print("perf025_e3_smoke=PASS")
        return

    name, baseline, candidate = DELTA

    print("=== PERF025-E3 INTERPRETATION ===")
    print(f"sign_convention={SIGN_CONVENTION}")

    for workload in WORKLOADS:
        print(f"workload={workload}")

        for role, *_ in POINTS:
            value = accepted.get((role, workload))
            shown = "NOT_ADMITTED" if value is None else f"{value:.1f}"
            print(f"  {role}/{RUN_MODE} steady_amortized_p50_ns={shown}")

        base = accepted.get((baseline, workload))
        cand = accepted.get((candidate, workload))

        if base is None or cand is None:
            print(f"  {name}=NOT_AVAILABLE")
        else:
            print(
                f"  {name}={(cand / base - 1.0) * 100.0:+.2f}% "
                f"({candidate}/{RUN_MODE} vs {baseline}/{RUN_MODE})"
            )

    if not_stable:
        raise RuntimeError(
            "reference_admission=NOT_STABLE for: "
            + ", ".join(not_stable)
            + "; retained as rejected local raw, not cached"
        )

    print(f"accepted_reference_observations={len(accepted)}")
    print("perf025_e3_reference=PASS")


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
            "usage: perf025_e3.py <validate|prepare|smoke|benchmark>"
        )


if __name__ == "__main__":
    main()
