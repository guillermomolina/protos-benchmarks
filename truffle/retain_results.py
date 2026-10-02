#!/usr/bin/env python3
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

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from workload_catalog import expected_result, source_for

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "results" / "local" / "truffle-cache"
RESULTS = ROOT / "results"

AB_V2_DEFINITION = "jvm-protos-session-ab-v2"
AB_V3_DEFINITION = "jvm-protos-session-ab-v3"
CURRENT_V3_DEFINITION = "jvm-cross-truffle-current-v3"

# PERF023 keeps its original unfiltered selection and class distribution.
# PERF025 selects only accepted ab-v3 reference observations produced by the
# exact clean producer revision.
RETENTION_PROFILES = {
    "perf023": {
        "expected_classes": {
            "jvm-ab-reference": 4,
            "jvm-reference": 6,
            "jvm-smoke": 6,
            "native-reference": 6,
            "native-smoke": 6,
        },
    },
    "perf025": {
        "expected_classes": {
            "jvm-ab-v3-reference": 12,
        },
    },
    # PERF024 re-baseline: accepted current-v3 reference observations only,
    # 3 workloads x 3 languages, from the exact clean producer revision.
    "perf024-rebaseline": {
        "expected_classes": {
            "jvm-cross-truffle-current-v3-reference": 9,
        },
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def cache_key(identity: dict[str, object]) -> str:
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(encoded).hexdigest()


def git_blob(
    revision: str,
    path: str,
) -> bytes:
    result = subprocess.run(
        [
            "git",
            "show",
            f"{revision}:{path}",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )

    return result.stdout


def require_revision(revision: str) -> None:
    if len(revision) != 40:
        raise RuntimeError(
            "producer revision must be a full 40-character SHA"
        )

    result = subprocess.run(
        [
            "git",
            "cat-file",
            "-e",
            f"{revision}^{{commit}}",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"producer revision not present: {revision}"
        )


def output_result(output: str) -> str:
    values = [
        line.split("=", 1)[1]
        for line in output.splitlines()
        if line.startswith("result=")
    ]

    if not values:
        raise RuntimeError(
            "cached JVM output has no result= line"
        )

    return values[-1]


def classify(
    identity: dict[str, object],
) -> str:
    measurement = identity.get(
        "measurement_definition"
    )

    if measurement == "jvm-protos-session-ab-v1":
        return "jvm-ab-reference"

    if measurement == CURRENT_V3_DEFINITION:
        profile = identity.get("profile")

        if profile == "benchmark":
            return "jvm-cross-truffle-current-v3-reference"

        raise RuntimeError(
            f"{measurement} profile is not retainable: {profile}"
        )

    if measurement in {AB_V2_DEFINITION, AB_V3_DEFINITION}:
        profile = identity.get("profile")

        if profile == "benchmark":
            version = (
                "v3"
                if measurement == AB_V3_DEFINITION
                else "v2"
            )
            return f"jvm-ab-{version}-reference"

        raise RuntimeError(
            f"{measurement} profile is not retainable: {profile}"
        )

    mode = identity.get("mode")

    if mode == "jvm":
        warmup = identity.get(
            "warmup_iterations"
        )
        steady = identity.get(
            "steady_iterations"
        )

        if (warmup, steady) == (2, 3):
            return "jvm-smoke"

        if (warmup, steady) == (5, 10):
            return "jvm-reference"

        raise RuntimeError(
            "unknown JVM measurement profile: "
            f"warmup={warmup} steady={steady}"
        )

    if mode == "native":
        calls = identity.get(
            "sustained_calls"
        )
        batches = identity.get(
            "sustained_batches"
        )

        if (calls, batches) == (2, 1):
            return "native-smoke"

        if (calls, batches) == (5, 3):
            return "native-reference"

        raise RuntimeError(
            "unknown Native measurement profile: "
            f"calls={calls} batches={batches}"
        )

    raise RuntimeError(
        f"unknown measurement identity: {identity}"
    )


def cached_result(
    payload: dict[str, object],
) -> str:
    if "observation" in payload:
        observation = payload["observation"]

        if not isinstance(observation, dict):
            raise RuntimeError(
                "observation must be an object"
            )

        result = observation.get("result")

        if result is None:
            raise RuntimeError(
                "observation has no result"
            )

        return str(result)

    output = payload.get("output")

    if not isinstance(output, str):
        raise RuntimeError(
            "cache entry has neither observation nor output"
        )

    return output_result(output)


def producer_source(
    producer_revision: str,
    workload: str,
    language: str,
) -> tuple[str, str]:
    current = source_for(
        workload,
        language,
    )

    relative = str(
        current.relative_to(ROOT)
    )

    data = git_blob(
        producer_revision,
        relative,
    )

    return relative, sha256_bytes(data)


def validate_cache_entry(
    path: Path,
    producer_revision: str,
    selected_workloads: set[str],
) -> dict[str, object] | None:
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    identity = payload.get("identity")

    if not isinstance(identity, dict):
        raise RuntimeError(
            f"{path}: missing identity object"
        )

    workload = identity.get("workload")

    if workload not in selected_workloads:
        return None

    expected_key = cache_key(identity)

    if path.stem != expected_key:
        raise RuntimeError(
            f"{path}: cache filename does not match identity"
        )

    language = str(
        identity.get("language")
    )

    if language not in {
        "protos",
        "js",
        "python",
    }:
        raise RuntimeError(
            f"{path}: unexpected language {language}"
        )

    source_path, producer_source_sha = (
        producer_source(
            producer_revision,
            str(workload),
            language,
        )
    )

    identity_source_sha = identity.get(
        "source_sha256"
    )

    if identity_source_sha != producer_source_sha:
        raise RuntimeError(
            f"{path}: source SHA does not match "
            f"{producer_revision}:{source_path}"
        )

    actual_result = cached_result(payload)
    expected = expected_result(
        str(workload)
    )

    if actual_result != expected:
        raise RuntimeError(
            f"{path}: expected result {expected}, "
            f"got {actual_result}"
        )

    measurement_class = classify(
        identity
    )

    entry: dict[str, object] = {
        "cache_key": expected_key,
        "raw_file": f"raw/{path.name}",
        "raw_sha256": sha256_file(path),
        "measurement_class": measurement_class,
        "mode": identity.get("mode"),
        "language": language,
        "workload": workload,
        "source_path": source_path,
        "source_sha256": identity_source_sha,
        "result": actual_result,
    }

    if (
        identity.get("measurement_definition")
        == "jvm-protos-session-ab-v1"
    ):
        entry["protos_revision"] = identity.get(
            "protos_revision"
        )
        entry["protos_version"] = identity.get(
            "protos_version"
        )

    if identity.get("measurement_definition") in {
        AB_V2_DEFINITION,
        AB_V3_DEFINITION,
    }:
        for key in (
            "harness_revision",
            "role",
            "run_mode",
            "protos_revision",
            "protos_version",
            "protos_core_sha256",
        ):
            entry[key] = identity.get(key)

    if identity.get("measurement_definition") == CURRENT_V3_DEFINITION:
        for key in (
            "harness_revision",
            "run_mode",
            "measurement_class",
            "sample_calls",
        ):
            entry[key] = identity.get(key)

        if language == "protos":
            for key in (
                "protos_revision",
                "protos_version",
                "protos_core_sha256",
            ):
                entry[key] = identity.get(key)

    return entry


def perf025_selected(
    path: Path,
    producer_revision: str,
) -> bool:
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )
    identity = payload.get("identity")

    if (
        not isinstance(identity, dict)
        or identity.get("measurement_definition")
        != AB_V3_DEFINITION
        or identity.get("profile") != "benchmark"
    ):
        return False

    if (
        identity.get("harness_revision")
        != producer_revision
        or identity.get("harness_dirty") is not False
    ):
        return False

    admission = payload.get("admission")

    if (
        not isinstance(admission, dict)
        or admission.get("status") != "PASS"
    ):
        raise RuntimeError(
            f"{path}: cached ab-v3 reference is not admitted"
        )

    return True


def perf024_rebaseline_selected(
    path: Path,
    producer_revision: str,
) -> bool:
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )
    identity = payload.get("identity")

    if (
        not isinstance(identity, dict)
        or identity.get("measurement_definition")
        != CURRENT_V3_DEFINITION
        or identity.get("profile") != "benchmark"
        or identity.get("harness_revision") != producer_revision
        or identity.get("harness_dirty") is not False
    ):
        return False

    admission = payload.get("admission")

    if (
        not isinstance(admission, dict)
        or admission.get("status") != "PASS"
    ):
        raise RuntimeError(
            f"{path}: cached current-v3 reference is not admitted"
        )

    return True


def require_perf024_rebaseline_matrix(
    entries: list[dict[str, object]],
    producer_revision: str,
) -> None:
    import perf024_rebaseline as experiment

    expected = {
        (language, workload)
        for workload in experiment.WORKLOADS
        for language in experiment.LANGUAGES
    }
    actual = [
        (entry.get("language"), entry.get("workload"))
        for entry in entries
    ]

    if sorted(actual) != sorted(expected):
        raise RuntimeError(
            "PERF024 re-baseline retained matrix mismatch: "
            f"{sorted(actual)}"
        )

    for entry in entries:
        workload = str(entry.get("workload"))
        kind = experiment.WORKLOADS[workload]

        if entry.get("harness_revision") != producer_revision:
            raise RuntimeError(
                "PERF024 entry harness revision mismatch"
            )

        if (
            entry.get("run_mode") != experiment.RUN_MODE
            or entry.get("measurement_class") != kind
            or entry.get("sample_calls")
            != experiment.SAMPLE_CALLS[(workload, entry.get("language"))]
        ):
            raise RuntimeError(
                f"PERF024 entry policy mismatch: {entry}"
            )

        if entry.get("language") == "protos" and (
            entry.get("protos_revision"),
            entry.get("protos_version"),
        ) != (
            experiment.CURRENT_REVISION,
            experiment.CURRENT_VERSION,
        ):
            raise RuntimeError(
                "PERF024 entry Protos identity mismatch"
            )


def require_perf025_matrix(
    entries: list[dict[str, object]],
    producer_revision: str,
) -> None:
    import perf025_ab

    expected = {
        (role, mode, workload)
        for role, _, _, mode in perf025_ab.POINTS
        for workload in perf025_ab.WORKLOADS
    }

    actual = [
        (
            entry.get("role"),
            entry.get("run_mode"),
            entry.get("workload"),
        )
        for entry in entries
    ]

    if sorted(actual) != sorted(expected):
        raise RuntimeError(
            "PERF025 retained matrix mismatch: "
            f"{sorted(actual)}"
        )

    revisions = {
        role: (revision, version)
        for role, revision, version, _ in perf025_ab.POINTS
    }

    for entry in entries:
        if entry.get("harness_revision") != producer_revision:
            raise RuntimeError(
                "PERF025 entry harness revision mismatch"
            )

        if (
            entry.get("protos_revision"),
            entry.get("protos_version"),
        ) != revisions[str(entry.get("role"))]:
            raise RuntimeError(
                "PERF025 entry Protos identity mismatch"
            )


def verify_retained(
    work_item: str,
) -> None:
    destination = (
        RESULTS
        / work_item.lower()
    )

    manifest_path = (
        destination
        / "manifest.json"
    )

    if not manifest_path.is_file():
        raise RuntimeError(
            f"manifest missing: {manifest_path}"
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    producer_revision = manifest.get(
        "producer_revision"
    )

    if not isinstance(
        producer_revision,
        str,
    ):
        raise RuntimeError(
            "manifest producer_revision missing"
        )

    require_revision(
        producer_revision
    )

    entries = manifest.get("entries")

    if not isinstance(entries, list):
        raise RuntimeError(
            "manifest entries missing"
        )

    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError(
                "manifest entry must be an object"
            )

        raw_file = destination / str(
            entry["raw_file"]
        )

        if not raw_file.is_file():
            raise RuntimeError(
                f"retained raw file missing: "
                f"{raw_file}"
            )

        actual_sha = sha256_file(
            raw_file
        )

        if (
            actual_sha
            != entry["raw_sha256"]
        ):
            raise RuntimeError(
                f"retained raw SHA mismatch: "
                f"{raw_file}"
            )

        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )

        identity = payload.get(
            "identity"
        )

        if not isinstance(
            identity,
            dict,
        ):
            raise RuntimeError(
                f"{raw_file}: identity missing"
            )

        if (
            cache_key(identity)
            != entry["cache_key"]
        ):
            raise RuntimeError(
                f"{raw_file}: identity/cache-key mismatch"
            )

        source_path = str(
            entry["source_path"]
        )

        source_sha = sha256_bytes(
            git_blob(
                producer_revision,
                source_path,
            )
        )

        if (
            source_sha
            != entry["source_sha256"]
        ):
            raise RuntimeError(
                f"{raw_file}: producer source mismatch"
            )

        actual_result = cached_result(
            payload
        )

        if (
            actual_result
            != entry["result"]
        ):
            raise RuntimeError(
                f"{raw_file}: retained result mismatch"
            )

    if manifest.get("retention_profile") == "perf025":
        require_perf025_matrix(
            entries,
            producer_revision,
        )

    if manifest.get("retention_profile") == "perf024-rebaseline":
        require_perf024_rebaseline_matrix(
            entries,
            producer_revision,
        )

    observed_counts = Counter(
        str(entry["measurement_class"])
        for entry in entries
    )

    manifest_counts = manifest.get(
        "measurement_class_counts"
    )

    if (
        dict(sorted(observed_counts.items()))
        != manifest_counts
    ):
        raise RuntimeError(
            "manifest measurement counts mismatch"
        )

    if (
        len(entries)
        != manifest.get(
            "retained_observation_count"
        )
    ):
        raise RuntimeError(
            "manifest observation count mismatch"
        )

    print(
        f"work_item={work_item}"
    )
    print(
        f"producer_revision={producer_revision}"
    )
    print(
        f"retained_observations={len(entries)}"
    )

    for name, count in sorted(
        observed_counts.items()
    ):
        print(
            f"{name}={count}"
        )

    print("retained_results=PASS")


def retain(
    work_item: str,
    producer_revision: str,
    workload_list: str,
    expected_count: int,
    profile: str = "perf023",
) -> None:
    require_revision(
        producer_revision
    )

    if profile not in RETENTION_PROFILES:
        raise RuntimeError(
            f"unknown retention profile: {profile}"
        )

    if not CACHE.is_dir():
        raise RuntimeError(
            f"local cache missing: {CACHE}"
        )

    selected_workloads = {
        item.strip()
        for item in workload_list.split(",")
        if item.strip()
    }

    if not selected_workloads:
        raise RuntimeError(
            "at least one workload is required"
        )

    destination = (
        RESULTS
        / work_item.lower()
    )

    if destination.exists():
        manifest = (
            destination
            / "manifest.json"
        )

        if manifest.is_file():
            print(
                f"retained_destination="
                f"{destination} action=reuse"
            )
            verify_retained(
                work_item
            )
            return

        raise RuntimeError(
            f"destination already exists "
            f"without manifest: {destination}"
        )

    entries: list[
        dict[str, object]
    ] = []

    selected_paths: list[Path] = []

    for path in sorted(
        CACHE.glob("*.json")
    ):
        if (
            profile == "perf025"
            and not perf025_selected(
                path,
                producer_revision,
            )
        ):
            continue

        if (
            profile == "perf024-rebaseline"
            and not perf024_rebaseline_selected(
                path,
                producer_revision,
            )
        ):
            continue

        entry = validate_cache_entry(
            path,
            producer_revision,
            selected_workloads,
        )

        if entry is None:
            continue

        entries.append(entry)
        selected_paths.append(path)

    if len(entries) != expected_count:
        raise RuntimeError(
            f"expected {expected_count} retained "
            f"observations, found {len(entries)}"
        )

    counts = Counter(
        str(entry["measurement_class"])
        for entry in entries
    )

    expected_classes = RETENTION_PROFILES[profile][
        "expected_classes"
    ]

    if dict(counts) != expected_classes:
        raise RuntimeError(
            f"unexpected {profile} measurement-class "
            f"distribution: {dict(counts)}"
        )

    if profile == "perf025":
        require_perf025_matrix(
            entries,
            producer_revision,
        )

    if profile == "perf024-rebaseline":
        require_perf024_rebaseline_matrix(
            entries,
            producer_revision,
        )

    temporary = (
        RESULTS
        / f".{work_item.lower()}.tmp"
    )

    if temporary.exists():
        shutil.rmtree(
            temporary
        )

    raw = temporary / "raw"
    raw.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in selected_paths:
        shutil.copyfile(
            path,
            raw / path.name,
        )

    manifest = {
        "schema": 1,
        "work_item": work_item,
        "producer_repository":
            "guillermomolina/protos-benchmarks",
        "producer_revision":
            producer_revision,
        "retention_policy":
            "raw-cache-payloads-byte-for-byte",
        "retained_observation_count":
            len(entries),
        "measurement_class_counts":
            dict(sorted(counts.items())),
        "workloads":
            sorted(selected_workloads),
        "entries":
            sorted(
                entries,
                key=lambda item:
                    str(item["cache_key"]),
            ),
    }

    if profile != "perf023":
        manifest["retention_profile"] = profile

    (
        temporary
        / "manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(
        destination
    )

    print(
        f"retained_destination={destination}"
    )

    verify_retained(
        work_item
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    retain_parser = sub.add_parser(
        "retain"
    )
    retain_parser.add_argument(
        "--work-item",
        required=True,
    )
    retain_parser.add_argument(
        "--producer-revision",
        required=True,
    )
    retain_parser.add_argument(
        "--workloads",
        required=True,
    )
    retain_parser.add_argument(
        "--expect",
        type=int,
        required=True,
    )
    retain_parser.add_argument(
        "--profile",
        choices=sorted(RETENTION_PROFILES),
        default="perf023",
    )

    verify_parser = sub.add_parser(
        "verify"
    )
    verify_parser.add_argument(
        "--work-item",
        required=True,
    )

    args = parser.parse_args()

    if args.command == "retain":
        retain(
            args.work_item,
            args.producer_revision,
            args.workloads,
            args.expect,
            args.profile,
        )
    else:
        verify_retained(
            args.work_item
        )


if __name__ == "__main__":
    main()
