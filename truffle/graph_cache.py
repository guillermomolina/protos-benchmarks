#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Read-only historical graph evidence discovery and reference verification."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import measure_protos as mp


REFERENCE_NAME = "reuse.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _raw_gzip_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def complete_evidence(directory: Path, capture: dict, unit: dict) -> bool:
    """Admit only retained, stable and analyzed reference evidence."""
    try:
        if capture["capture_valid"] is not True:
            return False
        if capture["correctness"]["result"] != "PASS":
            return False
        if capture["stage"] != "reference":
            return False
        if capture["stabilization"]["status"] != "STABLE":
            return False
        if unit["evidence_valid"] is not True:
            return False
        if unit["stabilization"]["after_truffle_tier_confirmed"] is not True:
            return False
        if unit["selected_stable_tier"] != 2:
            return False
        if unit["language"] != capture["language"]:
            return False
        if unit["workload"] != capture["workload"]:
            return False
        if unit["workload_source_sha256"] != capture["workload_source_sha256"]:
            return False
        if unit["summary"]["graph_count"] != len(unit["units"]):
            return False
        if not unit["units"]:
            return False

        budgets = {run["budget"]: run for run in capture["runs"]}
        for budget in capture["stabilization"]["pair"]:
            run = budgets[budget]
            trace = directory / run["trace_log"]
            if not trace.is_file():
                return False
            if _raw_gzip_sha256(trace) != run["trace_log_sha256"]:
                return False

        for graph_unit in unit["units"]:
            bgv = directory / graph_unit["bgv"]
            analysis = directory / graph_unit["analysis"]
            if not bgv.is_file() or not analysis.is_file():
                return False
            if _raw_gzip_sha256(bgv) != graph_unit["bgv_sha256"]:
                return False
            if mp.sha256_file(analysis) != graph_unit["analysis_sha256"]:
                return False

        return True
    except (KeyError, TypeError, ValueError, OSError, EOFError):
        return False


def compatible(
    capture: dict,
    unit: dict,
    key: dict,
    adapter_hash: str,
    host: dict,
    peer_classpath_hash: str | None,
) -> bool:
    """The case ID is a stable contract; its source hash is not a cache key."""
    if any(
        capture.get(field) != key.get(field)
        for field in (
            "language", "surface", "workload",
            "stage", "expected_result", "selected_phase",
        )
    ):
        return False

    if capture.get("budget_policy") != key["budgets"]:
        return False
    if capture.get("graph_jvm_options") != key["graph_jvm_options"]:
        return False
    if capture.get("final_tier") != key["final_tier"]:
        return False
    if capture.get("adapter_source_sha256") != adapter_hash:
        return False
    if capture.get("java", {}).get("java.runtime.version") != key["java_runtime_version"]:
        return False

    previous_host = capture.get("host", {})
    for field in ("architecture", "cpu_model"):
        if not previous_host.get(field) or previous_host[field] != host.get(field):
            return False

    runtime = key["runtime"]
    if key["language"] == "protos":
        if capture.get("protos_revision") != runtime["revision"]:
            return False
        if (
            capture.get("product_before", {}).get("source_state_sha256")
            != runtime["source_state_sha256"]
        ):
            return False
    else:
        peer = capture.get("peer_runtime", {})
        if peer.get("graalvm_version") != runtime["graalvm_version"]:
            return False
        if not peer_classpath_hash:
            return False
        if peer.get("dependency_classpath_sha256") != peer_classpath_hash:
            return False

    return (
        unit.get("selected_phase") == key["selected_phase"]
        and unit.get("surface") == key["surface"]
        and unit.get("expected_result") == key["expected_result"]
    )


def historical_candidates(root: Path) -> list[Path]:
    return sorted((root / "results").rglob("capture.json"))


def find(
    root: Path,
    output: Path,
    candidates: list[Path],
    key: dict,
    adapter_hash: str,
    host: dict,
    peer_classpath_hash: str | None,
) -> tuple[Path, dict, dict] | None:
    matches = []
    results = (root / "results").resolve()

    for path in candidates:
        directory = path.parent.resolve()

        if directory.parent.name != key["workload"]:
            continue
        if directory.name != key["language"]:
            continue
        if not directory.is_relative_to(results):
            continue
        if directory.is_relative_to(output.resolve()):
            continue
        if ".staging" in directory.parts:
            continue

        try:
            capture = _json(path)
            unit = _json(directory / "unit.json")
            if not compatible(
                capture, unit, key, adapter_hash,
                host, peer_classpath_hash,
            ):
                continue
            if not complete_evidence(directory, capture, unit):
                continue
            matches.append((directory, capture, unit))
        except (ValueError, OSError, TypeError, KeyError):
            continue

    if not matches:
        return None

    # Detect conflicting stable measurements instead of silently choosing one.
    signatures = {
        json.dumps(
            item[2]["summary"],
            sort_keys=True,
        )
        for item in matches
    }
    if len(signatures) > 1:
        paths = ", ".join(str(item[0]) for item in matches)
        raise mp.UsageError("conflicting historical graph evidence: " + paths)

    matches.sort(
        key=lambda item: (
            item[1].get("capture_finished", ""),
            str(item[0]),
        ),
        reverse=True,
    )
    return matches[0]



def publishable_source(
    root: Path,
    directory: Path,
    capture: dict,
    unit: dict,
) -> Path:
    """Promote ignored local evidence without changing its original."""
    root = root.resolve()
    directory = directory.resolve()
    local = root / "results" / "local"

    if not directory.is_relative_to(local):
        return directory

    if not complete_evidence(directory, capture, unit):
        raise mp.UsageError(f"incomplete local evidence: {directory}")

    relative = directory.relative_to(root)
    capture_sha = mp.sha256_file(directory / "capture.json")
    unit_sha = mp.sha256_file(directory / "unit.json")

    identity = hashlib.sha256(
        f"{relative}\0{capture_sha}\0{unit_sha}".encode("utf-8")
    ).hexdigest()[:20]

    destination = (
        root / "results" / "graph-cache-imported"
        / identity / capture["workload"] / capture["language"]
    )

    if destination.exists():
        if (
            not (destination / "capture.json").is_file()
            or not (destination / "unit.json").is_file()
            or mp.sha256_file(destination / "capture.json") != capture_sha
            or mp.sha256_file(destination / "unit.json") != unit_sha
            or not complete_evidence(destination, capture, unit)
        ):
            raise mp.UsageError(
                f"existing imported evidence is invalid: {destination}"
            )
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".incomplete")

    if temporary.exists():
        raise mp.UsageError(
            f"incomplete import already exists: {temporary}"
        )

    try:
        shutil.copytree(directory, temporary)

        if (
            mp.sha256_file(temporary / "capture.json") != capture_sha
            or mp.sha256_file(temporary / "unit.json") != unit_sha
            or not complete_evidence(temporary, capture, unit)
        ):
            raise mp.UsageError(
                f"import verification failed: {relative}"
            )

        mp.write_json(
            temporary / "import-provenance.json",
            {
                "schema": 1,
                "original_path": str(relative),
                "capture_sha256": capture_sha,
                "unit_sha256": unit_sha,
                "original_protos_revision": capture["protos_revision"],
                "original_harness_git_head": capture["harness_git_head"],
            },
        )

        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return destination

def make_reference(
    root: Path, directory: Path, capture: dict, key: dict,
) -> dict:
    return {
        "schema": 1,
        "source": str(directory.resolve().relative_to(root.resolve())),
        "capture_sha256": mp.sha256_file(directory / "capture.json"),
        "unit_sha256": mp.sha256_file(directory / "unit.json"),
        "cache_key": key,
        "original_protos_revision": capture["protos_revision"],
        "original_harness_git_head": capture["harness_git_head"],
    }


def resolve_reference(root: Path, reference_file: Path) -> tuple[Path, dict, dict]:
    try:
        reference = _json(reference_file)
        if reference["schema"] != 1:
            raise ValueError("unknown reference schema")

        directory = (root / reference["source"]).resolve()
        results = (root / "results").resolve()

        if not directory.is_relative_to(results):
            raise ValueError("reference escapes results")

        capture_file = directory / "capture.json"
        unit_file = directory / "unit.json"

        if mp.sha256_file(capture_file) != reference["capture_sha256"]:
            raise ValueError("historical capture changed")
        if mp.sha256_file(unit_file) != reference["unit_sha256"]:
            raise ValueError("historical unit changed")

        capture = _json(capture_file)
        unit = _json(unit_file)

        if not complete_evidence(directory, capture, unit):
            raise ValueError("historical evidence incomplete")

        return directory, capture, unit
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise mp.UsageError(
            f"invalid historical reference {reference_file}: {exc}"
        ) from exc
