#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Cross-Truffle compiled-graph structural parity driver.

Reuses the revision-independent measurement surfaces of ``measure_protos.py``
(same product identity, adapters, classpaths and timed call) and records, per
workload and language, the structure of the relevant compiled graphs of one
steady prepared ``Value.execute()`` operation. It never produces timing.

Three steps, so that capture and BGV analysis can run on different hosts:

    capture    (needs the product/peer JVM; no Podman)
        correctness PASS on the measured surface
          -> natural-warmup budgets from harness/policy/graphs.json, one fresh
             JVM per budget with TraceCompilation + TraceInlining +
             TraceNodeExpansion + Dump=Truffle:1
          -> stop at the first two consecutive budgets with an identical
             trace-side signature (tier, graph count, per-unit structure)
          -> retain gzipped trace logs and the selected units' BGVs (gzipped);
             every other BGV is recorded by name/size/sha256 and discarded
    analyze    (needs Podman: harness/igv_analyzer.sh, the published
                Graal 25.4.4.1.1 IgvUtility image; no second analyzer)
        IgvUtility filter of each retained BGV -> gzipped JSON next to it
    verify     producer hashes of every case vs working tree / HEAD
    summarize  (pure Python)
        After-TruffleTier selection, exact node counts, BGV-side stabilization
        confirmation, per-case evidence units and the rung matrix

Policy (phase, options, budgets, root identity, ladder) is data in
``harness/policy/graphs.json``; graph logic is ``graph_evidence.py``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import graph_evidence as ge
import bytecode_size_runtime as bsr
import measure_protos as mp
import workload_catalog

ROOT = mp.ROOT
HARNESS_DIR = mp.HARNESS_DIR
POLICY = HARNESS_DIR / "policy" / "graphs.json"
ANALYZER = HARNESS_DIR / "igv_analyzer.sh"
SCHEMA_VERSION = 1
LANGUAGES = ("protos", "js", "python")
OUTPUT_MARKER = ".measure-graphs-output"
EVIDENCE_UNIT_DEFINITION = (
    "One (protos revision, harness producer, language, surface, workload) case: "
    "correctness on the measured surface, the natural-warmup budget runs up to "
    "the first stable pair, the selected relevant language-owned compilation "
    "units of the later budget of that pair, their After-TruffleTier graphs "
    "from the retained BGVs, and the derived metrics."
)

GRAPH_PRODUCER_FILES = (
    HARNESS_DIR / "measure_graphs.py",
    HARNESS_DIR / "graph_evidence.py",
    POLICY,
    HARNESS_DIR / "compiler_trace.py",
    ANALYZER,
)


def load_policy() -> dict[str, Any]:
    data = json.loads(POLICY.read_text(encoding="utf-8"))

    if data.get("schema") != 1:
        raise mp.UsageError(f"unsupported graph policy schema in {POLICY}")

    return data


def ladder(policy: dict[str, Any], name: str = "primitive") -> list[dict[str, str]]:
    return list(policy["ladders"][name])


def select_workloads(policy: dict[str, Any], selector: str) -> list[str]:
    if selector == "ladder":
        return [rung["workload"] for rung in ladder(policy)]

    try:
        workload_catalog.select_workloads(selector)
    except ValueError as exc:
        raise mp.UsageError(str(exc)) from exc

    if selector == "all":
        return list(workload_catalog.workload_ids())

    return [selector]


def select_languages(selector: str) -> list[str]:
    if selector == "all":
        return list(LANGUAGES)
    if selector not in LANGUAGES:
        raise mp.UsageError(f"unknown language {selector!r}")
    return [selector]



def graph_capture_key(
    policy: dict[str, Any],
    product: dict[str, Any],
    language: str,
    surface: str,
    workload: str,
    stage: str,
    java: dict[str, str],
) -> dict[str, Any]:
    """Language-owned capture identity.

    Workload IDs are stable benchmark contracts. The source SHA-256 is
    retained in capture evidence but does not invalidate the cache.
    """
    if language == "protos":
        runtime = {
            "revision": product["revision"],
            "source_state_sha256": product["source_state_sha256"],
        }
    else:
        version = mp.jvm_runtime.harness_graalvm_version()
        runtime = {
            "graalvm_version": version,
            "peer_dependencies_sha256": mp.sha256_bytes(
                mp.jvm_runtime.peer_pom(version).encode("utf-8")
            ),
        }

    return {
        "language": language,
        "runtime": runtime,
        "java_runtime_version": java.get("java.runtime.version"),
        "surface": surface,
        "workload": workload,
        "stage": stage,
        "expected_result": workload_catalog.expected_result(workload),
        "budgets": list(policy["budgets"][stage]),
        "graph_jvm_options": policy["jvm_options"],
        "selected_phase": policy["selected_phase"],
        "final_tier": policy["final_tier"],
    }


def case_dir(output: Path, workload: str, language: str) -> Path:
    return output / workload / language


def gzip_file(source: Path, destination: Path) -> None:
    with source.open("rb") as raw, gzip.open(destination, "wb", compresslevel=9) as packed:
        shutil.copyfileobj(raw, packed)


def read_gzip_text(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return stream.read()


def prepare_output(output: Path) -> None:
    marker = output / OUTPUT_MARKER

    if output.exists() and any(output.iterdir()) and not marker.is_file():
        raise mp.UsageError(
            f"--output exists, is not empty and was not created by measure_graphs.py: {output}"
        )

    output.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "Created by harness/measure_graphs.py. "
        "<workload>/<language>/capture.json and unit.json are authoritative.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# capture


def capture_case(
    args: argparse.Namespace,
    policy: dict[str, Any],
    cases: dict[str, Any],
    workload: str,
    language: str,
    output: Path,
) -> dict[str, Any]:
    language_policy = policy["languages"][language]
    surface = language_policy["surface"]
    surface_def = mp.surface_definition(cases, surface)
    product_dir = args.dir.expanduser().resolve()
    expected = workload_catalog.expected_result(workload)
    source = workload_catalog.source_for(workload, language)
    budgets = list(policy["budgets"][args.stage])
    destination = case_dir(output, workload, language)

    product_before = mp.product_identity(product_dir)

    if not product_before["clean"] and not args.allow_dirty_product:
        raise mp.UsageError(
            "Protos checkout is dirty; retained graph evidence requires a clean "
            "checkout (use --allow-dirty-product only for diagnostics)"
        )

    files = sorted(
        set(mp.producer_files(cases, surface_def, workload, language))
        | {path.resolve() for path in GRAPH_PRODUCER_FILES}
    )
    harness_before = mp.harness_identity(files)
    java = mp.java_identity()
    key = graph_capture_key(
        policy, product_before, language, surface, workload,
        args.stage, java,
    )

    existing = destination / "capture.json"

    if existing.is_file() and not args.remeasure:
        previous = json.loads(existing.read_text(encoding="utf-8"))
        if previous.get("capture_key") == key and previous.get("capture_valid"):
            mp.emit("CASE", f"{workload}/{language} EXISTS")
            return previous

    if destination.exists() and any(destination.iterdir()) and not args.remeasure:
        raise mp.UsageError(
            f"case destination already contains different evidence: {destination}"
        )

    staging = output / ".staging" / f"{workload}--{language}"
    shutil.rmtree(staging, ignore_errors=True)
    raw = staging / "raw"
    raw.mkdir(parents=True)
    cpu, siblings, allowed = mp.choose_cpu(args.cpu)
    started = mp.utc_now()
    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_unit_definition": EVIDENCE_UNIT_DEFINITION,
        "capture_valid": False,
        "capture_key": key,
        "capture_started": started.isoformat(),
        "protos_revision": product_before["revision"],
        "product_before": product_before,
        "language": language,
        "surface": surface,
        "surface_timed_call": surface_def["timed_call"],
        "workload": workload,
        "workload_source": mp.producer_name(source),
        "workload_source_sha256": mp.sha256_file(source),
        "expected_result": expected,
        "stage": args.stage,
        "selected_phase": policy["selected_phase"],
        "final_tier": policy["final_tier"],
        "graph_jvm_options": policy["jvm_options"],
        "budget_policy": budgets,
        "harness": harness_before,
        "harness_git_head": harness_before["git_head"],
        "harness_dirty": harness_before["dirty"],
        "java": java,
        "host": mp.host_identity(cpu, siblings, allowed),
        "timing_evidence": "NONE (graph instrumentation is never a timing run)",
    }

    try:
        runtime = mp.prepare_surface_runtime(
            cases, surface, surface_def, language, product_dir, product_before, metadata, raw
        )

        code, out = mp.run_logged(
            mp.java_command(
                runtime["runtime_cp"],
                runtime["main_class"],
                runtime["system_properties"],
                [],
                ["correctness", runtime["core_arg"], str(source)],
                None,
            ),
            raw / "correctness.log",
        )
        actual = mp.output_result(out) if code == 0 else None
        correctness = "PASS" if actual == expected else "FAIL"
        metadata["correctness"] = {"result": correctness, "actual": actual, "exit_code": code}
        mp.emit("CORRECTNESS", f"{workload}/{language} {correctness}")

        if correctness != "PASS":
            raise mp.InvalidMeasurement("CORRECTNESS_FAILED", f"expected {expected}, got {actual!r}")

        runs: list[dict[str, Any]] = []
        stabilization = {"status": ge.GRAPH_NOT_STABLE, "pair": None}

        for budget in budgets:
            run = capture_budget(
                policy, language_policy, runtime, source, expected, budget, raw, cpu
            )
            runs.append(run)
            mp.emit(
                "BUDGET",
                f"{workload}/{language} {budget} {run['assessment']['status']} "
                f"units={len(run['resolution']['units']) if run['resolution'] else '-'} "
                f"problems={','.join(run['assessment']['problems']) or '-'}",
            )

            if args.stage == "smoke":
                stabilization = {
                    "status": "SMOKE_NOT_EVALUATED",
                    "pair": None,
                    "admitted": run["assessment"]["status"] == ge.STABLE_CANDIDATE,
                }
                break

            stabilization = ge.stabilize(runs)

            if stabilization["status"] == ge.STABLE:
                break

        metadata["stabilization"] = stabilization
        retain_runs(runs, stabilization, staging)
        metadata["runs"] = [
            {key_: value for key_, value in run.items() if key_ not in ("parsed", "workdir")}
            for run in runs
        ]

        product_after = mp.product_identity(product_dir)
        metadata["product_after"] = product_after
        changed = mp.compare_product(product_before, product_after)

        if changed:
            raise mp.InvalidMeasurement("PRODUCT_CHANGED_DURING_CAPTURE", ",".join(changed))

        harness_after = mp.producer_hashes(files)

        if harness_after != harness_before["source_sha256"]:
            raise mp.InvalidMeasurement("HARNESS_CHANGED_DURING_CAPTURE")

        if args.stage == "smoke" and not stabilization.get("admitted"):
            raise mp.InvalidMeasurement("SMOKE_NOT_ADMITTED", runs[-1]["assessment"]["problems"])

        metadata["capture_valid"] = True
    except mp.InvalidMeasurement as exc:
        metadata["capture_valid"] = False
        metadata["invalid_reason"] = exc.reason
        metadata["invalid_detail"] = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
        mp.emit("CAPTURE_INVALID", f"{workload}/{language} {exc.reason} {exc.detail}")

    metadata["capture_finished"] = mp.utc_now().isoformat()
    mp.write_json(staging / "capture.json", metadata)
    shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(destination)
    mp.emit(
        "CAPTURE",
        f"{workload}/{language} valid={'YES' if metadata['capture_valid'] else 'NO'} "
        f"stabilization={metadata.get('stabilization', {}).get('status', '-')} "
        f"pair={metadata.get('stabilization', {}).get('pair')}",
    )
    return metadata


def capture_budget(
    policy: dict[str, Any],
    language_policy: dict[str, Any],
    runtime: dict[str, Any],
    source: Path,
    expected: str,
    budget: int,
    raw: Path,
    cpu: int,
) -> dict[str, Any]:
    """One fresh JVM: ``budget`` steady calls of the surface's timed call
    (engine ``measure`` with 0 warmup, 1 steady iteration of ``budget``
    calls; every call is result-checked by the engine)."""
    workdir = raw / f"budget-{budget}"
    dumps = workdir / "dumps"
    dumps.mkdir(parents=True)
    options = [*policy["jvm_options"], policy["dump_path_option"] + str(dumps)]
    log = workdir / "trace.log"
    code, out = mp.run_logged(
        mp.java_command(
            runtime["runtime_cp"],
            runtime["main_class"],
            runtime["system_properties"],
            options,
            ["measure", runtime["core_arg"], str(source), "0", "1", str(budget), "-"],
            cpu,
        ),
        log,
    )
    result = mp.output_result(out) if code == 0 else None

    if result != expected:
        raise mp.InvalidMeasurement(
            "GRAPH_RUN_CORRECTNESS_FAILED", f"budget {budget}: expected {expected}, got {result!r}"
        )

    parsed = ge.parse_trace(out)
    resolution = None
    error = None

    try:
        resolution = ge.resolve_units(parsed, policy, language_policy, str(source))
    except ge.EvidenceError as exc:
        error = exc

    assessment = ge.assess_run(parsed, resolution, policy["final_tier"], error)
    names = sorted(path.name for path in dumps.glob("*.bgv"))

    if resolution is not None:
        for unit in resolution["units"]:
            unit["bgv"] = ge.dumps_for(unit["comp_id"], names)
            if len(unit["bgv"]) != 1:
                assessment["problems"].append("BGV_MISSING" if not unit["bgv"] else "BGV_AMBIGUOUS")
                assessment["status"] = ge.NOT_STABLE
            unit["attribution"] = ge.expansion_attribution(parsed, unit["comp_id"])

    return {
        "budget": budget,
        "calls": budget + 1,
        "result": result,
        "exit_code": code,
        "trace_log_sha256": mp.sha256_file(log),
        "error": {"reason": error.reason, "detail": error.detail} if error else None,
        "resolution": resolution,
        "assessment": assessment,
        "compilation_count": len(parsed["compilations"]),
        "failure_count": len(parsed["failures"]),
        "invalidation_count": len(parsed["invalidations"]),
        "dump_inventory": [
            {"name": name, "bytes": (dumps / name).stat().st_size, "sha256": mp.sha256_file(dumps / name)}
            for name in names
        ],
        "workdir": workdir,
        "parsed": parsed,
    }


def retain_runs(runs: list[dict[str, Any]], stabilization: dict[str, Any], staging: Path) -> None:
    """Gzipped trace logs of every budget; gzipped BGVs of the selected units
    of the stable pair (or of the last two runs when not stable, as
    diagnostic evidence). Other BGVs remain only in ``dump_inventory``."""
    keep = set(stabilization.get("pair") or [r["budget"] for r in runs[-2:]])

    for run in runs:
        workdir: Path = run["workdir"]
        target = staging / f"budget-{run['budget']}"
        target.mkdir(parents=True, exist_ok=True)
        gzip_file(workdir / "trace.log", target / "trace.log.gz")
        run["trace_log"] = str((target / "trace.log.gz").relative_to(staging))
        run["retained_bgv"] = []

        if run["budget"] in keep and run["resolution"]:
            for unit in run["resolution"]["units"]:
                for name in unit.get("bgv", []):
                    packed = target / "bgv" / (name + ".gz")
                    packed.parent.mkdir(exist_ok=True)
                    gzip_file(workdir / "dumps" / name, packed)
                    run["retained_bgv"].append(str(packed.relative_to(staging)))

        shutil.rmtree(workdir)


def capture(args: argparse.Namespace) -> int:
    if args.dir is None or args.output is None:
        raise mp.UsageError("--dir and --output are required")

    policy = load_policy()
    cases = mp.load_cases()
    output = args.output.expanduser().resolve()
    prepare_output(output)
    invalid = 0

    for workload in select_workloads(policy, args.workload):
        for language in select_languages(args.language):
            metadata = capture_case(args, policy, cases, workload, language, output)
            invalid += not metadata.get("capture_valid")

    staging = output / ".staging"
    if staging.is_dir() and not any(staging.iterdir()):
        staging.rmdir()

    mp.emit("CAPTURE_INVALID_CASES", invalid)
    return mp.EXIT_OK if invalid == 0 else mp.EXIT_INVALID


# ---------------------------------------------------------------------------
# analyze (Podman host)


def iter_cases(output: Path):
    for directory in sorted(output.glob("*/*")):
        if not directory.is_dir():
            continue

        capture_file = directory / "capture.json"

        if capture_file.is_file():
            yield directory, json.loads(
                capture_file.read_text(encoding="utf-8")
            )


def require_analysis_container_runtime() -> None:
    """Require host-side Podman without installing or pulling anything."""
    binary = os.environ.get("PODMAN", "").strip() or "podman"

    if shutil.which(binary) is None:
        raise mp.UsageError(
            f"CONTAINER_RUNTIME_NOT_FOUND: {binary} is unavailable. "
            "Run graph analysis on the Linux host with Podman installed. "
            "Capture, summarize and verify do not need Podman."
        )


def analyze(args: argparse.Namespace) -> int:
    """IgvUtility ``filter`` (through harness/igv_analyzer.sh only) of every
    retained BGV that has no analysis yet."""
    output = args.output.expanduser().resolve()
    failures = 0
    runtime_checked = False

    for directory, metadata in iter_cases(output):
        if not directory.is_relative_to(output):
            mp.emit("ANALYZE_REUSED", f"{metadata['workload']}/{metadata['language']}")
            continue
        for run in metadata.get("runs", []):
            for relative in run.get("retained_bgv", []):
                packed = directory / relative
                result = packed.with_name(packed.name[: -len(".bgv.gz")] + ".filter.json.gz")

                if result.is_file() and not args.reanalyze:
                    continue

                if not runtime_checked:
                    require_analysis_container_runtime()
                    runtime_checked = True

                with tempfile.TemporaryDirectory(prefix="graph-analyze-") as tmp:
                    bgv = Path(tmp) / "input.bgv"
                    with gzip.open(packed, "rb") as source, bgv.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    completed = subprocess.run(
                        [str(ANALYZER), "filter", "input.bgv"],
                        cwd=tmp,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                if completed.returncode != 0 or not completed.stdout.strip():
                    failures += 1
                    mp.emit("ANALYZE_FAILED", f"{relative} {completed.stderr.decode(errors='replace').strip()[:300]}")
                    continue

                try:
                    json.loads(completed.stdout)
                except json.JSONDecodeError:
                    failures += 1
                    mp.emit("ANALYZE_INVALID_JSON", relative)
                    continue

                with gzip.open(result, "wb", compresslevel=9) as stream:
                    stream.write(completed.stdout)
                mp.emit("ANALYZED", f"{directory.relative_to(output)}/{relative}")

    mp.emit("ANALYZE_FAILURES", failures)
    return mp.EXIT_OK if failures == 0 else mp.EXIT_INVALID


# ---------------------------------------------------------------------------
# summarize


def analyzer_identity() -> dict[str, str]:
    text = ANALYZER.read_text(encoding="utf-8")
    version = next(
        (
            line.split("=", 1)[1]
            for line in text.splitlines()
            if line.startswith("ANALYZER_GRAAL_VERSION=")
        ),
        "UNKNOWN",
    )
    return {
        "script": "harness/igv_analyzer.sh",
        "script_sha256": mp.sha256_file(ANALYZER),
        "graal_version": version,
        "image": os.environ.get(
            "PROTOS_IGV_ANALYZER_IMAGE",
            f"ghcr.io/guillermomolina/protos-benchmarks/igv-analyzer:graal-{version}",
        ),
        "command": "filter",
    }


def unit_graphs(directory: Path, run: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    units = []

    for unit in run["resolution"]["units"]:
        name = unit["bgv"][0]
        packed = directory / f"budget-{run['budget']}" / "bgv" / (name + ".gz")
        analysis = packed.with_name(name[: -len(".bgv")] + ".filter.json.gz")

        if not packed.is_file():
            raise ge.EvidenceError("BGV_NOT_RETAINED", str(packed.relative_to(directory)))

        if not analysis.is_file():
            raise ge.EvidenceError("BGV_NOT_ANALYZED", str(packed.relative_to(directory)))

        graph = ge.select_unit_graph(json.loads(read_gzip_text(analysis)), phase)
        units.append(
            {
                **{k: unit[k] for k in ("role", "label", "via", "edge", "tier", "comp_id", "src",
                                        "superseded_comp_ids", "ir_after_truffle_tier",
                                        "expansion_truffle_tier", "inlined", "attribution")},
                **{
                    key: unit[key]
                    for key in (
                        "target",
                        "normalized_label",
                        "cross_run_identity",
                    )
                    if key in unit
                },
                "bgv": str(packed.relative_to(directory)),
                "bgv_sha256": next(
                    item["sha256"] for item in run["dump_inventory"] if item["name"] == name
                ),
                "analysis": str(analysis.relative_to(directory)),
                "analysis_sha256": mp.sha256_file(analysis),
                "graph": graph,
            }
        )

    return units


def structural_key(units: list[dict[str, Any]]) -> list[Any]:
    return [
        [u["role"], ge.normalize_label(u["label"]), u["tier"], u["graph"]["node_count"],
         u["graph"]["node_class_histogram"]]
        for u in units
    ]


def summarize_case(directory: Path, metadata: dict[str, Any], phase: str) -> dict[str, Any]:
    unit: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_unit_definition": EVIDENCE_UNIT_DEFINITION,
        "protos_revision": metadata["protos_revision"],
        "harness_git_head": metadata["harness_git_head"],
        "harness_dirty": metadata["harness_dirty"],
        "harness_source_sha256": metadata["harness"]["source_sha256"],
        "language": metadata["language"],
        "surface": metadata["surface"],
        "surface_timed_call": metadata["surface_timed_call"],
        "workload": metadata["workload"],
        "workload_source_sha256": metadata["workload_source_sha256"],
        "expected_result": metadata["expected_result"],
        "correctness": metadata.get("correctness"),
        "java": metadata["java"],
        "host": metadata["host"],
        "graph_jvm_options": metadata["graph_jvm_options"],
        "budget_policy": metadata["budget_policy"],
        "budgets_run": [run["budget"] for run in metadata.get("runs", [])],
        "selected_phase": phase,
        "analyzer": analyzer_identity(),
        "stage": metadata.get("stage"),
        "stabilization": metadata.get("stabilization"),
        "evidence_valid": False,
    }

    try:
        if not metadata.get("capture_valid"):
            raise ge.EvidenceError("CAPTURE_INVALID", metadata.get("invalid_reason", ""))

        stabilization = metadata["stabilization"]
        runs = {run["budget"]: run for run in metadata["runs"]}

        if metadata.get("stage") == "smoke" and stabilization.get("admitted"):
            # Pipeline admission only: one budget, no stabilization claim.
            first = second = metadata["runs"][-1]
        elif stabilization["status"] != ge.STABLE:
            raise ge.EvidenceError(ge.GRAPH_NOT_STABLE, stabilization["status"])
        else:
            first, second = (runs[b] for b in stabilization["pair"])
        first_units = unit_graphs(directory, first, phase)
        second_units = unit_graphs(directory, second, phase)

        if structural_key(first_units) != structural_key(second_units):
            unit["stabilization"] = {**stabilization, "status": ge.GRAPH_NOT_STABLE,
                                     "reason": "AFTER_TRUFFLE_TIER_DIFFERS_IN_PAIR"}
            raise ge.EvidenceError(ge.GRAPH_NOT_STABLE, "AFTER_TRUFFLE_TIER_DIFFERS_IN_PAIR")

        unit["stabilization"] = {**stabilization, "after_truffle_tier_confirmed": True}
        unit["selected_budget"] = second["budget"]
        unit["selected_stable_tier"] = second_units[0]["tier"]
        unit["units"] = second_units
        unit["trace_log"] = second["trace_log"]
        unit["unattributed_language_targets"] = second["resolution"]["unattributed_language_targets"]
        unit["framework_targets"] = second["resolution"]["framework_targets"]
        unit["summary"] = ge.case_summary(second_units)
        unit["evidence_valid"] = True
    except ge.EvidenceError as exc:
        unit["invalid_reason"] = exc.reason
        unit["invalid_detail"] = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)

    mp.write_json(directory / "unit.json", unit)
    return unit


def unstable_protos_evidence(policy: dict[str, Any], directory: Path) -> dict[str, Any]:
    """Instability facts of the last (highest) budget, re-derived from its
    retained raw trace log."""
    capture = json.loads((directory / "capture.json").read_text(encoding="utf-8"))
    last = (capture.get("runs") or [{}])[-1]
    problems = list((last.get("assessment") or {}).get("problems") or [ge.GRAPH_NOT_STABLE])
    resolution = last.get("resolution") or {}
    evidence: dict[str, Any] = {"budget": last.get("budget"), "trace_log": last.get("trace_log")}

    if resolution.get("primary_label") and last.get("trace_log"):
        parsed = ge.parse_trace(read_gzip_text(directory / last["trace_log"]))
        evidence.update(ge.instability_evidence(parsed, policy, resolution["primary_label"]))

    return {"problems": problems, "evidence": evidence}


def summarize(args: argparse.Namespace) -> int:
    policy = load_policy()
    output = args.output.expanduser().resolve()
    phase = policy["selected_phase"]
    units: dict[tuple[str, str], dict[str, Any]] = {}
    evidence_paths: dict[tuple[str, str], str] = {}

    for directory, metadata in iter_cases(output):
        evidence_paths[
            (metadata["workload"], metadata["language"])
        ] = os.path.relpath(directory / "unit.json", output)
        if directory.is_relative_to(output):
            unit = summarize_case(directory, metadata, phase)
        else:
            unit = json.loads(
                (directory / "unit.json").read_text(encoding="utf-8")
            )
        units[(metadata["workload"], metadata["language"])] = unit
        mp.emit(
            "UNIT",
            f"{metadata['workload']}/{metadata['language']} valid={'YES' if unit['evidence_valid'] else 'NO'} "
            + (
                f"total={unit['summary']['relevant_graph_nodes_total_after_truffle_tier']} "
                f"graphs={unit['summary']['graph_count']}"
                if unit["evidence_valid"]
                else f"reason={unit.get('invalid_reason')}"
            ),
        )

    rungs = []

    original_ladder = ladder(policy)
    original_ids = {item["workload"] for item in original_ladder}
    complete_ladder = [
        *original_ladder,
        *(
            {"workload": workload, "mechanism": f"catalogued workload: {workload}"}
            for workload in workload_catalog.workload_ids()
            if workload not in original_ids
        ),
    ]

    for rung in complete_ladder:
        present = {lang: units.get((rung["workload"], lang)) for lang in LANGUAGES}

        if not any(present.values()):
            continue

        summaries = {
            lang: (u["summary"] if u and u["evidence_valid"] else None) for lang, u in present.items()
        }
        protos_unit = present.get("protos")
        instability = None
        if protos_unit and protos_unit.get("invalid_reason") == ge.GRAPH_NOT_STABLE:
            instability = unstable_protos_evidence(policy, output / rung["workload"] / "protos")
        result = ge.compare_rung(rung["workload"], rung["mechanism"], summaries, instability)
        result["evidence"] = {
            lang: (
                {"valid": u["evidence_valid"], "reason": u.get("invalid_reason"),
                 "stabilization": (u.get("stabilization") or {}).get("status"),
                 "unit": evidence_paths[(rung["workload"], lang)]}
                if u else None
            )
            for lang, u in present.items()
        }
        rungs.append(result)
        mp.emit(
            "RUNG",
            f"{rung['workload']} protos={result['protos_total']} js={result['js_total']} "
            f"python={result['python_total']} peer={result['peer_reference']} "
            f"protos_stabilization={result['protos_stabilization']} "
            f"protos_status={result['protos_status']} node_comparison={result['peer_node_comparison']} "
            f"final_state={result['final_compilation_state'] or '-'} "
            f"signals={','.join(result['protos_signals']) or '-'}",
        )

    divergent = ge.first_divergent(rungs)
    revisions = sorted({u["protos_revision"] for u in units.values()})
    heads = sorted({u["harness_git_head"] for u in units.values()})
    matrix = {
        "schema_version": SCHEMA_VERSION,
        "selected_phase": phase,
        "primary_metric": "relevant_graph_nodes_total_after_truffle_tier",
        "stages": sorted({str(u.get("stage")) for u in units.values()}),
        "protos_revisions": revisions,
        "harness_git_heads": heads,
        "harness_dirty": sorted({u["harness_dirty"] for u in units.values()}),
        "analyzer": analyzer_identity(),
        "rungs": rungs,
        "first_divergent_rung": divergent,
        "rungs_before_first_divergence_not_converged": [
            r["workload"]
            for r in rungs[: next((i for i, r in enumerate(rungs) if divergent and r["workload"] == divergent["workload"]), len(rungs))]
            if r["protos_status"] != ge.STRUCTURALLY_CONVERGED
        ],
    }
    mp.write_json(output / "matrix.json", matrix)
    mp.emit("FIRST_DIVERGENT_RUNG", divergent["workload"] if divergent else "NONE")
    mp.emit("MATRIX", output / "matrix.json")
    invalid = sum(not u["evidence_valid"] for u in units.values())
    mp.emit("INVALID_UNITS", invalid)
    return mp.EXIT_OK if invalid == 0 else mp.EXIT_INVALID


# ---------------------------------------------------------------------------


def verify(args: argparse.Namespace) -> int:
    """Before publication: every case's recorded producer source hashes must
    match the working tree (and, after the commit, HEAD)."""
    output = args.output.expanduser().resolve()
    working_mismatch: set[str] = set()
    head_mismatch: set[str] = set()
    cases = 0

    historical_references = 0
    for directory, metadata in iter_cases(output):
        cases += 1
        if not directory.is_relative_to(output):
            historical_references += 1
            continue
        for relative, expected in metadata["harness"]["source_sha256"].items():
            path = ROOT / relative
            if not path.is_file() or mp.sha256_file(path) != expected:
                working_mismatch.add(relative)
            try:
                blob = mp.git(ROOT, "show", f"HEAD:{relative}", binary=True)
            except subprocess.CalledProcessError:
                head_mismatch.add(relative)
                continue
            if mp.sha256_bytes(blob) != expected:
                head_mismatch.add(relative)

    mp.emit("CASES", cases)
    mp.emit("HISTORICAL_REFERENCES_VERIFIED", historical_references)
    mp.emit("WORKING_TREE_MATCHES_PRODUCER", "NO" if working_mismatch else "YES")
    for relative in sorted(working_mismatch):
        mp.emit("WORKING_TREE_MISMATCH", relative)
    mp.emit("HEAD_MATCHES_PRODUCER", "NO" if head_mismatch else "YES")
    for relative in sorted(head_mismatch):
        mp.emit("HEAD_MISMATCH", relative)
    return mp.EXIT_OK if cases and not working_mismatch else mp.EXIT_INVALID



def bytecode_histogram_options() -> list[str]:
    """Options for a dedicated diagnostic JVM, never a timing JVM."""
    return [
        "-Dpolyglot.engine.AllowExperimentalOptions=true",
        "-Dpolyglot.engine.BytecodeHistogram=language,root",
    ]


def run_bytecode_diagnostic(
    runtime: dict[str, Any],
    source: Path,
    expected: str,
    calls: int,
    cpu: int,
    log: Path,
) -> dict[str, Any]:
    """Collect per-root executed opcodes without admitting timing."""
    if type(calls) is not int or not 1 <= calls <= 1000000:
        raise mp.UsageError("Invalid bytecode diagnostic call count")

    instrument = None
    unavailable_reason = None
    runtime_cp = runtime["runtime_cp"]
    jvm_options = bytecode_histogram_options()

    try:
        instrument = bsr.compile_instrument(runtime_cp)
    except bsr.InstrumentError as error:
        reason = str(error)

        if reason.startswith("TRUFFLE_API_VERSION_UNRESOLVED"):
            unavailable_reason = reason
        else:
            raise mp.InvalidMeasurement(
                "BYTECODE_SIZE_INSTRUMENT_FAILED",
                reason,
            ) from error

    if instrument is not None:
        runtime_cp = os.pathsep.join([
            str(instrument["classes"]),
            runtime_cp,
        ])
        jvm_options = [
            *jvm_options,
            "-Dpolyglot.bench-bytecode-size=true",
        ]

    command = mp.java_command(
        runtime_cp,
        runtime["main_class"],
        runtime["system_properties"],
        jvm_options,
        [
            "measure",
            runtime["core_arg"],
            str(source),
            "0",
            "1",
            str(calls),
            "-",
        ],
        cpu,
    )

    code, output = mp.run_logged(command, log)
    actual = mp.output_result(output)

    if code != 0 or actual != expected:
        raise mp.InvalidMeasurement(
            "BYTECODE_DIAGNOSTIC_FAILED",
            f"exit_code={code}, expected={expected}, actual={actual!r}",
        )

    histogram = ge.parse_bytecode_histogram(output)

    if instrument is None:
        size_evidence = {
            "status": "UNAVAILABLE",
            "reason": (
                unavailable_reason
                or "BYTECODE_INSTRUMENT_NOT_AVAILABLE"
            ),
            "observations": [],
        }
        instrument_evidence = {
            "status": "UNAVAILABLE",
            "reason": unavailable_reason,
        }
    else:
        size_evidence = ge.parse_bytecode_size_trace(output)
        instrument_evidence = {
            "status": "AVAILABLE",
            "version": instrument["version"],
            "cache_key": instrument["cache_key"],
            "processor_sha256": instrument["processor_sha256"],
            "source_sha256": bsr.sha256_file(bsr.SOURCE),
        }

    return {
        "status": histogram["status"],
        "histogram": histogram,
        "size": size_evidence,
        "size_instrument": instrument_evidence,
        "raw_log": "raw/bytecode-histogram.log",
        "raw_log_sha256": mp.sha256_file(log),
        "jvm_options": jvm_options,
        "calls": calls,
        "execution": "dedicated-fresh-jvm",
        "timing_evidence": "NONE",
    }


def bytecode_capture(args: argparse.Namespace) -> int:
    """Capture all reported Bytecode DSL roots independently."""
    policy = load_policy()
    cases = mp.load_cases()

    if args.workload not in workload_catalog.workload_ids():
        raise mp.UsageError(f"Unknown workload: {args.workload}")

    if args.language not in LANGUAGES:
        raise mp.UsageError(f"Unknown language: {args.language}")

    if not 1 <= args.calls <= 1000000:
        raise mp.UsageError("Invalid diagnostic call count")

    product_dir = (
        args.dir.expanduser().resolve()
        if args.dir is not None
        else None
    )

    if args.language == "protos" and product_dir is None:
        raise mp.UsageError("Protos requires --dir")

    if args.language != "protos":
        product_dir = None

    product_before = (
        mp.product_identity(product_dir)
        if product_dir is not None
        else None
    )

    if product_before is not None:
        if not product_before["clean"]:
            raise mp.UsageError("Protos checkout must be clean")

        if (
            args.version is not None
            and args.version != product_before["version"]
        ):
            raise mp.UsageError(
                "Requested Protos version differs from checkout"
            )

    output = args.output.expanduser().resolve()
    prepare_output(output)

    destination = case_dir(
        output, args.workload, args.language
    )

    if destination.exists():
        raise mp.UsageError(
            f"Evidence already exists: {destination}"
        )

    language_policy = policy["languages"][args.language]
    surface = language_policy["surface"]
    surface_def = mp.surface_definition(cases, surface)

    workload_source = workload_catalog.source_for(
        args.workload, args.language
    )

    expected_result = workload_catalog.expected_result(
        args.workload
    )

    files = sorted(
        set(
            mp.producer_files(
                cases,
                surface_def,
                args.workload,
                args.language,
            )
        )
        | {
            item.resolve()
            for item in GRAPH_PRODUCER_FILES
        }
    )

    files.extend([
        bsr.SOURCE.resolve(),
        Path(bsr.__file__).resolve(),
    ])
    files = sorted(set(files))

    harness_before = mp.harness_identity(files)
    java = mp.java_identity()
    cpu, siblings, allowed = mp.choose_cpu(args.cpu)

    staging_root = output / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)

    staging = Path(
        tempfile.mkdtemp(
            prefix="bytecode-",
            dir=staging_root,
        )
    )

    raw = staging / "raw"
    raw.mkdir()

    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "bytecode-diagnostic",
        "capture_valid": False,
        "capture_started": mp.utc_now().isoformat(),
        "language": args.language,
        "workload": args.workload,
        "surface": surface,
        "expected_result": expected_result,
        "source_sha256": mp.sha256_file(workload_source),
        "product_before": product_before,
        "harness": harness_before,
        "java": java,
        "host": mp.host_identity(cpu, siblings, allowed),
        "capture_key": {
            "mode": "executed-bytecode-histogram-v1",
            "language": args.language,
            "workload": args.workload,
            "surface": surface,
            "source_sha256": mp.sha256_file(workload_source),
            "producer_source_sha256": harness_before["source_sha256"],
            "product_revision": (
                product_before["revision"]
                if product_before is not None else None
            ),
            "product_source_state_sha256": (
                product_before["source_state_sha256"]
                if product_before is not None else None
            ),
            "requested_version": args.version,
            "java_runtime_version": java.get("java.runtime.version"),
            "calls": args.calls,
            "jvm_options": bytecode_histogram_options(),
        },
        "timing_evidence": "NONE",
        "graph_evidence": "NONE",
        "reference_eligible": False,
    }

    try:
        runtime = mp.prepare_surface_runtime(
            cases,
            surface,
            surface_def,
            args.language,
            product_dir,
            product_before,
            metadata,
            raw,
            requested_peer_version=(
                args.version if args.language != "protos" else None
            ),
        )

        if args.language != "protos":
            metadata["capture_key"]["peer_runtime"] = (
                metadata["peer_runtime"]
            )

        metadata["bytecode"] = run_bytecode_diagnostic(
            runtime,
            workload_source,
            expected_result,
            args.calls,
            cpu,
            raw / "bytecode-histogram.log",
        )
        metadata["capture_key"]["jvm_options"] = metadata['bytecode']["jvm_options"]

        if product_dir is not None:
            product_after = mp.product_identity(product_dir)
            metadata["product_after"] = product_after

            changed = mp.compare_product(
                product_before, product_after
            )

            if changed:
                raise mp.InvalidMeasurement(
                    "PRODUCT_CHANGED_DURING_CAPTURE",
                    ",".join(changed),
                )

        after_hashes = mp.producer_hashes(files)
        metadata["harness_after_source_sha256"] = after_hashes

        if after_hashes != harness_before["source_sha256"]:
            raise mp.InvalidMeasurement(
                "HARNESS_CHANGED_DURING_CAPTURE"
            )

        metadata["capture_valid"] = True

    except (mp.InvalidMeasurement, ge.EvidenceError) as exc:
        metadata["capture_valid"] = False
        metadata["invalid_reason"] = exc.reason
        metadata["invalid_detail"] = exc.detail

    metadata["capture_finished"] = mp.utc_now().isoformat()
    mp.write_json(staging / "capture.json", metadata)

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(destination)

    mp.emit(
        "BYTECODE_CAPTURE_VALID",
        "YES" if metadata["capture_valid"] else "NO",
    )
    mp.emit("BYTECODE_CAPTURE", destination)

    if not metadata["capture_valid"]:
        mp.emit("INVALID_REASON", metadata["invalid_reason"])
        return mp.EXIT_INVALID

    mp.emit(
        "BYTECODE_HISTOGRAM",
        metadata["bytecode"]["status"],
    )
    return mp.EXIT_OK


def cold_capture(args: argparse.Namespace) -> int:
    """One selected compilation in a fresh JVM, never a timing reference."""
    policy = load_policy()
    cases = mp.load_cases()

    if args.workload not in workload_catalog.workload_ids():
        raise mp.UsageError(f"unknown workload: {args.workload}")

    if args.language not in LANGUAGES:
        raise mp.UsageError(f"unknown language: {args.language}")

    product_dir = args.dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    prepare_output(output)

    destination = case_dir(output, args.workload, args.language)

    if destination.exists():
        raise mp.UsageError(
            f"cold capture already exists: {destination}. "
            "Choose another output directory; existing evidence is preserved."
        )

    language_policy = policy["languages"][args.language]
    surface = language_policy["surface"]
    surface_def = mp.surface_definition(cases, surface)
    source = workload_catalog.source_for(
        args.workload, args.language
    )
    expected = workload_catalog.expected_result(args.workload)

    product_before = mp.product_identity(product_dir)
    if not product_before["clean"]:
        raise mp.UsageError(
            "cold compilation requires a clean Protos checkout"
        )

    files = sorted(
        set(mp.producer_files(
            cases, surface_def, args.workload, args.language
        ))
        | {path.resolve() for path in GRAPH_PRODUCER_FILES}
    )

    harness_before = mp.harness_identity(files)
    java = mp.java_identity()
    cpu, siblings, allowed = mp.choose_cpu(args.cpu)

    staging_root = output / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(
        prefix="cold-capture-", dir=staging_root
    ))
    raw = staging / "raw"
    raw.mkdir()

    key = {
        **graph_capture_key(
            policy,
            product_before,
            args.language,
            surface,
            args.workload,
            "smoke",
            java,
        ),
        "capture_mode": "cold-single-compilation-v1",
        "requested_tier": args.tier,
        "requested_root": args.root,
        "warmup_calls": args.warmup_calls,
        "invocations": args.invocations,
        "first_tier_threshold": args.first_threshold,
        "last_tier_threshold": args.last_threshold,
        "extra_jvm_options": list(args.jvm_option),
    }

    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "cold-compilation",
        "capture_valid": False,
        "capture_key": key,
        "capture_started": mp.utc_now().isoformat(),
        "language": args.language,
        "workload": args.workload,
        "surface": surface,
        "expected_result": expected,
        "protos_revision": product_before["revision"],
        "product_before": product_before,
        "harness": harness_before,
        "java": java,
        "host": mp.host_identity(cpu, siblings, allowed),
        "selected_phase": policy["selected_phase"],
        "requested_tier": args.tier,
        "requested_root": args.root,
        "timing_evidence": "NONE",
        "timing_explanation": (
            "Compilation instrumentation changes execution cost; "
            "sample timings are not benchmark measurements."
        ),
    }

    try:
        runtime = mp.prepare_surface_runtime(
            cases,
            surface,
            surface_def,
            args.language,
            product_dir,
            product_before,
            metadata,
            raw,
        )

        correctness_command = mp.java_command(
            runtime["runtime_cp"],
            runtime["main_class"],
            runtime["system_properties"],
            [],
            [
                "correctness",
                runtime["core_arg"],
                str(source),
            ],
            None,
        )

        correctness_code, correctness_output = mp.run_logged(
            correctness_command,
            raw / "correctness.log",
        )

        actual = (
            mp.output_result(correctness_output)
            if correctness_code == 0 else None
        )

        metadata["correctness"] = {
            "result": "PASS" if actual == expected else "FAIL",
            "actual": actual,
            "exit_code": correctness_code,
        }

        if actual != expected:
            raise mp.InvalidMeasurement(
                "CORRECTNESS_FAILED",
                f"expected {expected}, got {actual!r}",
            )

        workdir = raw / "cold-jvm"
        dumps = workdir / "dumps"
        dumps.mkdir(parents=True)

        options = cold_jvm_options(
            policy,
            args.tier,
            args.first_threshold,
            args.last_threshold,
            dumps,
            tuple(args.jvm_option),
        )

        invocation_args, sequence = cold_invocation_arguments(
            runtime["core_arg"],
            source,
            args.warmup_calls,
            args.invocations,
        )

        metadata["invocation_sequence"] = sequence
        metadata["graph_jvm_options"] = options
        metadata["fresh_jvm"] = True
        metadata["correctness_uses_separate_jvm"] = True

        command = mp.java_command(
            runtime["runtime_cp"],
            runtime["main_class"],
            runtime["system_properties"],
            options,
            invocation_args,
            cpu,
        )

        trace_log = workdir / "trace.log"
        code, output_text = mp.run_logged(command, trace_log)

        if code != 0 or mp.output_result(output_text) != expected:
            raise mp.InvalidMeasurement(
                "COLD_JVM_RUN_FAILED",
                f"exit_code={code}",
            )

        parsed = ge.parse_trace(output_text)

        resolution = None
        if args.root == "primary":
            resolution = ge.resolve_units(
                parsed, policy, language_policy, str(source)
            )


        root_identity = {}
        unavailable_roots = []

        if args.root == "all":
            inventory = ge.observed_compilation_roots(
                parsed, args.tier
            )

            metadata["root_inventory"] = {
                "scope": inventory["scope"],
                "requested_tier": inventory["requested_tier"],
                "interpreted_roots_coverage": inventory[
                    "interpreted_roots_coverage"
                ],
                "roots": [
                    {
                        key: value
                        for key, value in entry.items()
                        if key != "selected"
                    }
                    for entry in inventory["roots"]
                ],
            }

            unavailable_roots = [
                {
                    key: value
                    for key, value in entry.items()
                    if key != "selected"
                }
                for entry in inventory["roots"]
                if entry["status"] != "AVAILABLE"
            ]

            selections = [
                entry["selected"]
                for entry in inventory["roots"]
                if entry["status"] == "AVAILABLE"
            ]

            root_identity = {
                entry["target"]: entry["cross_run_identity"]
                for entry in inventory["roots"]
            }

        else:
            selected = ge.select_tier_compilation(
                parsed,
                args.tier,
                args.root,
                resolution,
            )
            selections = [selected]

        bgv_names = sorted(
            path.name for path in dumps.glob("*.bgv")
        )

        units = []
        retained_selections = []

        for selected in selections:
            matched = ge.dumps_for(
                selected["comp_id"], bgv_names
            )

            if len(matched) != 1:
                if args.root != "all":
                    raise ge.EvidenceError(
                        "BGV_NOT_UNIQUE_FOR_COMPILATION",
                        {
                            "comp_id": selected["comp_id"],
                            "matching_bgv": matched,
                        },
                    )

                unavailable_roots.append({
                    "target": selected["target"],
                    "label": selected["label"],
                    "normalized_label": ge.normalize_label(
                        selected["label"]
                    ),
                    "requested_tier": args.tier,
                    "status": "UNAVAILABLE",
                    "reason": "BGV_NOT_UNIQUE_FOR_COMPILATION",
                    "matching_bgv": matched,
                })
                continue

            unit = {
                "role": (
                    "primary" if args.root == "primary"
                    else "selected"
                ),
                "target": selected["target"],
                "label": selected["label"],
                "via": None,
                "edge": None,
                "tier": selected["tier"],
                "comp_id": selected["comp_id"],
                "src": selected.get("src"),
                "superseded_comp_ids": [],
                "other_compilation_ids": selected["other_compilation_ids"],
                "ir_after_truffle_tier": selected["ir_after_truffle_tier"],
                "ir_final": selected["ir_final"],
                "compilation_time_ms": selected["compilation_time_ms"],
                "truffle_compilation_ms": selected["truffle_compilation_ms"],
                "graal_compilation_ms": selected["graal_compilation_ms"],
                "machine_code_bytes": selected["machine_code_bytes"],
                "ast_nodes": selected["ast_nodes"],
                "inlined": [
                    item["label"]
                    for item in selected.get("inline_tree") or []
                    if item["verb"] == "Inlined"
                ],
                "expansion_truffle_tier": (
                    selected.get("expansion") or {}
                ).get("root"),
                "attribution": ge.expansion_attribution(
                    parsed, selected["comp_id"]
                ),
                "bgv": matched,
            }


            unit["normalized_label"] = ge.normalize_label(
                selected["label"]
            )
            unit["target"] = selected["target"]
            unit["cross_run_identity"] = root_identity.get(
                selected["target"], "UNIQUE"
            )

            units.append(unit)
            retained_selections.append({
                **selected,
                "bgv": matched[0],
            })

        metadata["unavailable_roots"] = unavailable_roots

        if not units:
            raise ge.EvidenceError(
                "NO_REQUESTED_TIER_BGV_AVAILABLE",
                {
                    "tier": args.tier,
                    "root": args.root,
                    "unavailable": unavailable_roots,
                },
            )

        run = {
            "budget": args.invocations,
            "calls": sequence["total_measured_invocations"],
            "result": expected,
            "exit_code": code,
            "trace_log_sha256": mp.sha256_file(trace_log),
            "resolution": {"units": units},
            "compilation_count": len(parsed["compilations"]),
            "failure_count": len(parsed["failures"]),
            "invalidation_count": len(parsed["invalidations"]),
            "dump_inventory": [
                {
                    "name": name,
                    "bytes": (dumps / name).stat().st_size,
                    "sha256": mp.sha256_file(dumps / name),
                }
                for name in bgv_names
            ],
            "workdir": workdir,
        }

        retain_runs(
            [run],
            {"pair": [args.invocations]},
            staging,
        )

        metadata["runs"] = [{
            key_: value
            for key_, value in run.items()
            if key_ != "workdir"
        }]


        if args.root == "all":
            metadata["selected_compilations"] = [
                {
                    "root": item["root"],
                    "normalized_root": ge.normalize_label(
                        item["root"]
                    ),
                    "tier": item["observed_tier"],
                    "comp_id": item["comp_id"],
                    "ir_initial": item["ir_after_truffle_tier"],
                    "ir_final": item["ir_final"],
                    "machine_code_bytes": item["machine_code_bytes"],
                    "bgv": item["bgv"],
                }
                for item in retained_selections
            ]
        else:
            metadata["selected_compilation"] = {
                "root": selected["root"],
                "tier": selected["observed_tier"],
                "comp_id": selected["comp_id"],
                "compilation_time_ms": selected["compilation_time_ms"],
                "ir_initial": selected["ir_after_truffle_tier"],
                "ir_final": selected["ir_final"],
                "machine_code_bytes": selected["machine_code_bytes"],
                "bgv": matched[0],
            }

        product_after = mp.product_identity(product_dir)
        metadata["product_after"] = product_after

        changed = mp.compare_product(
            product_before, product_after
        )

        if changed:
            raise mp.InvalidMeasurement(
                "PRODUCT_CHANGED_DURING_CAPTURE",
                ",".join(changed),
            )

        harness_after = mp.producer_hashes(files)
        metadata["harness_after_source_sha256"] = harness_after

        if harness_after != harness_before["source_sha256"]:
            raise mp.InvalidMeasurement(
                "HARNESS_CHANGED_DURING_CAPTURE"
            )

        metadata["capture_valid"] = True

    except (mp.InvalidMeasurement, ge.EvidenceError) as exc:
        metadata["capture_valid"] = False
        metadata["invalid_reason"] = exc.reason
        detail = exc.detail
        metadata["invalid_detail"] = (
            detail if isinstance(detail, str)
            else json.dumps(detail)
        )

    metadata["capture_finished"] = mp.utc_now().isoformat()
    mp.write_json(staging / "capture.json", metadata)

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(destination)

    mp.emit(
        "COLD_CAPTURE_VALID",
        "YES" if metadata["capture_valid"] else "NO",
    )
    mp.emit("COLD_CAPTURE", destination)

    if metadata["capture_valid"]:
        if args.root == "all":
            mp.emit(
                "COMPILED_ROOTS_CAPTURED",
                len(metadata["selected_compilations"]),
            )
            mp.emit(
                "COMPILED_ROOTS_UNAVAILABLE",
                len(metadata["unavailable_roots"]),
            )
            return mp.EXIT_OK

        mp.emit(
            "OBSERVED_TIER",
            metadata["selected_compilation"]["tier"],
        )
        mp.emit(
            "COMP_ID",
            metadata["selected_compilation"]["comp_id"],
        )
        return mp.EXIT_OK

    mp.emit("INVALID_REASON", metadata["invalid_reason"])
    return mp.EXIT_INVALID


def cold_summarize(args: argparse.Namespace) -> int:
    """Summarize exactly one selected BGV phase per compilation."""
    output = args.output.expanduser().resolve()
    failures = 0
    completed = 0

    for directory, metadata in iter_cases(output):
        if metadata.get("mode") != "cold-compilation":
            continue

        if not metadata.get("capture_valid"):
            failures += 1
            mp.emit("COLD_SUMMARY_INVALID", directory)
            continue

        try:
            runs = metadata["runs"]
            if len(runs) != 1:
                raise ge.EvidenceError(
                    "COLD_RUN_COUNT_INVALID"
                )

            units = unit_graphs(
                directory,
                runs[0],
                metadata["selected_phase"],
            )

            if metadata.get("requested_root") == "all":
                summary = {
                    "schema": 1,
                    "mode": "cold-all-compiled-roots",
                    "scope": "observed-compiled-call-targets-only",
                    "language": metadata["language"],
                    "workload": metadata["workload"],
                    "requested_tier": metadata["requested_tier"],
                    "phase": metadata["selected_phase"],
                    "units": units,
                    "unavailable_roots": metadata.get(
                        "unavailable_roots", []
                    ),
                    "root_inventory": metadata.get(
                        "root_inventory"
                    ),
                    "interpreted_roots_coverage": "NOT_ESTABLISHED",
                    "invocation_sequence": metadata[
                        "invocation_sequence"
                    ],
                    "timing_evidence": "NONE",
                }

                mp.write_json(
                    directory / "cold-summary.json",
                    summary,
                )
                completed += 1
                continue

            if len(units) != 1:
                raise ge.EvidenceError(
                    "COLD_ROOT_COUNT_INVALID"
                )

            unit = units[0]
            summary = {
                "schema": 1,
                "mode": "cold-single-compilation",
                "language": metadata["language"],
                "workload": metadata["workload"],
                "root": unit["label"],
                "tier": unit["tier"],
                "comp_id": unit["comp_id"],
                "phase": metadata["selected_phase"],
                "compilation": metadata["selected_compilation"],
                "invocation_sequence": metadata["invocation_sequence"],
                "graph": unit["graph"],
                "bgv": unit["bgv"],
                "analysis": unit["analysis"],
                "timing_evidence": "NONE",
            }

            mp.write_json(
                directory / "cold-summary.json",
                summary,
            )
            completed += 1

        except (KeyError, IndexError, ge.EvidenceError) as exc:
            failures += 1
            mp.emit("COLD_SUMMARY_FAILED", str(exc))

    mp.emit("COLD_SUMMARIZED", completed)
    mp.emit("COLD_SUMMARY_FAILURES", failures)

    return mp.EXIT_OK if failures == 0 else mp.EXIT_INVALID



def structural_artifact(
    directory: Path,
    relative: str,
) -> Path:
    """Resolve one retained artifact without escaping its capture."""
    if not isinstance(relative, str) or not relative:
        raise ge.EvidenceError("INVALID_ARTIFACT_PATH")

    path = (directory / relative).resolve()

    if not path.is_relative_to(directory.resolve()):
        raise ge.EvidenceError("ARTIFACT_OUTSIDE_CAPTURE")

    if not path.is_file():
        raise ge.EvidenceError("ARTIFACT_NOT_FOUND", relative)

    return path


def structural_bgv_digest(path: Path) -> str:
    """Hash the original BGV bytes retained inside its gzip file."""
    digest = hashlib.sha256()

    with gzip.open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)

    return digest.hexdigest()


def read_structural_input(
    directory: Path,
    workload: str,
    language: str,
    tier: int,
) -> tuple[dict | None, dict | None, dict]:
    """Load and verify existing capture evidence, without modifying it."""
    capture_path = directory / "capture.json"
    summary_path = directory / "cold-summary.json"

    details = {
        "capture": str(capture_path),
        "summary": str(summary_path),
        "status": "MISSING",
        "reason": "CAPTURE_NOT_FOUND",
    }

    if not capture_path.is_file():
        return None, None, details

    try:
        capture = json.loads(
            capture_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        return None, None, {
            **details,
            "status": "INVALID",
            "reason": "CAPTURE_NOT_READABLE",
            "detail": str(exc),
        }

    if not isinstance(capture, dict):
        return None, None, {
            **details,
            "status": "INVALID",
            "reason": "CAPTURE_NOT_OBJECT",
        }

    expected = {
        "mode": "cold-compilation",
        "workload": workload,
        "language": language,
        "requested_tier": tier,
        "requested_root": "all",
    }

    for field, value in expected.items():
        if capture.get(field) != value:
            return capture, None, {
                **details,
                "status": "INVALID",
                "reason": "CAPTURE_IDENTITY_MISMATCH",
                "field": field,
            }

    if not capture.get("capture_valid"):
        return capture, None, {
            **details,
            "status": "INVALID",
            "reason": capture.get(
                "invalid_reason", "CAPTURE_INVALID"
            ),
        }

    if (
        capture.get("harness_after_source_sha256")
        != (capture.get("harness") or {}).get(
            "source_sha256"
        )
    ):
        return capture, None, {
            **details,
            "status": "INVALID",
            "reason": "CAPTURE_PRODUCER_CHANGED",
        }

    if not summary_path.is_file():
        return capture, None, {
            **details,
            "status": "UNAVAILABLE",
            "reason": "SUMMARY_NOT_FOUND",
        }

    try:
        summary = json.loads(
            summary_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        return capture, None, {
            **details,
            "status": "INVALID",
            "reason": "SUMMARY_NOT_READABLE",
            "detail": str(exc),
        }

    if not isinstance(summary, dict):
        return capture, None, {
            **details,
            "status": "INVALID",
            "reason": "SUMMARY_NOT_OBJECT",
        }

    if (
        summary.get("mode") != "cold-all-compiled-roots"
        or summary.get("workload") != workload
        or summary.get("language") != language
        or summary.get("requested_tier") != tier
        or summary.get("phase") != capture.get(
            "selected_phase"
        )
    ):
        return capture, None, {
            **details,
            "status": "INVALID",
            "reason": "SUMMARY_IDENTITY_MISMATCH",
        }

    units = summary.get("units")

    if not isinstance(units, list):
        return capture, None, {
            **details,
            "status": "INVALID",
            "reason": "SUMMARY_UNITS_NOT_LIST",
        }

    try:
        for unit in units:
            if not isinstance(unit, dict):
                raise ge.EvidenceError(
                    "SUMMARY_UNIT_NOT_OBJECT"
                )

            bgv = structural_artifact(
                directory, unit.get("bgv")
            )
            analysis = structural_artifact(
                directory, unit.get("analysis")
            )

            if (
                not bgv.name.endswith(".bgv.gz")
                or not analysis.name.endswith(
                    ".filter.json.gz"
                )
            ):
                raise ge.EvidenceError(
                    "UNEXPECTED_ARTIFACT_FORMAT"
                )

            expected_bgv = unit.get("bgv_sha256")

            if (
                not isinstance(expected_bgv, str)
                or structural_bgv_digest(bgv)
                != expected_bgv
            ):
                raise ge.EvidenceError(
                    "BGV_SHA256_MISMATCH"
                )

            expected_analysis = unit.get(
                "analysis_sha256"
            )

            if (
                not isinstance(expected_analysis, str)
                or mp.sha256_file(analysis)
                != expected_analysis
            ):
                raise ge.EvidenceError(
                    "ANALYSIS_SHA256_MISMATCH"
                )

            actual_graph = ge.select_unit_graph(
                json.loads(read_gzip_text(analysis)),
                summary["phase"],
            )

            if actual_graph != unit.get("graph"):
                raise ge.EvidenceError(
                    "SUMMARY_GRAPH_DIFFERS_FROM_ANALYSIS"
                )

    except (
        ge.EvidenceError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        EOFError,
    ) as exc:
        reason = (
            exc.reason
            if isinstance(exc, ge.EvidenceError)
            else "RETAINED_ARTIFACT_INVALID"
        )
        return capture, None, {
            **details,
            "status": "INVALID",
            "reason": reason,
            "detail": str(exc),
        }

    return capture, summary, {
        **details,
        "status": "AVAILABLE",
        "reason": None,
        "capture_sha256": mp.sha256_file(
            capture_path
        ),
        "summary_sha256": mp.sha256_file(
            summary_path
        ),
        "verified_graphs": len(units),
    }



def compatible_bytecode_harness_hashes(
    graph_hashes: object,
    bytecode_hashes: object,
    *,
    require_size_instrument: bool = False,
) -> bool:
    """Verify common producer files and allow only diagnostic extras.

    Graph capture never needs the diagnostic Java instrument or its
    offline compiler. All shared producer hashes must still match.
    """
    if (
        not isinstance(graph_hashes, dict)
        or not isinstance(bytecode_hashes, dict)
        or not graph_hashes
        or not bytecode_hashes
    ):
        return False

    graph_files = set(graph_hashes)
    bytecode_files = set(bytecode_hashes)

    allowed_extras = {
        "harness/bytecode_size_runtime.py",
        "harness/instruments/BytecodeSizeInstrument.java",
    }

    if graph_files - bytecode_files:
        return False

    extras = bytecode_files - graph_files

    if not extras.issubset(allowed_extras):
        return False

    if (
        require_size_instrument
        and not allowed_extras.issubset(bytecode_files)
    ):
        return False

    return all(
        isinstance(graph_hashes[name], str)
        and graph_hashes[name]
        and graph_hashes[name] == bytecode_hashes[name]
        for name in graph_files
    )


def read_structural_bytecode(
    directory: Path,
    workload: str,
    language: str,
    graph_captures: tuple[dict | None, dict | None],
) -> dict[str, Any]:
    """Verify a retained Bytecode DSL diagnostic without executing it."""
    capture_path = directory / "capture.json"

    result: dict[str, Any] = {
        "status": "UNAVAILABLE",
        "reason": "BYTECODE_CAPTURE_NOT_FOUND",
        "capture": str(capture_path),
        "groups": [],
        "total_executed_instructions": None,
        "size_evidence": {
            "status": "UNAVAILABLE",
            "reason": "BYTECODE_SIZE_NOT_CAPTURED",
            "observations": [],
        },
        "timing_evidence": "NONE",
    }

    if not capture_path.is_file():
        return result

    try:
        capture = json.loads(
            capture_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        return {
            **result,
            "status": "INVALID",
            "reason": "BYTECODE_CAPTURE_NOT_READABLE",
            "detail": str(exc),
        }

    if not isinstance(capture, dict):
        return {
            **result,
            "status": "INVALID",
            "reason": "BYTECODE_CAPTURE_NOT_OBJECT",
        }

    if (
        capture.get("mode") != "bytecode-diagnostic"
        or capture.get("workload") != workload
        or capture.get("language") != language
    ):
        return {
            **result,
            "status": "INVALID",
            "reason": "BYTECODE_CAPTURE_IDENTITY_MISMATCH",
        }

    if not capture.get("capture_valid"):
        return {
            **result,
            "status": "INVALID",
            "reason": capture.get(
                "invalid_reason",
                "BYTECODE_CAPTURE_INVALID",
            ),
        }

    diagnostic = capture.get("bytecode")

    if not isinstance(diagnostic, dict):
        return {
            **result,
            "status": "INVALID",
            "reason": "BYTECODE_DIAGNOSTIC_NOT_FOUND",
        }

    stored_histogram = diagnostic.get("histogram")

    if not isinstance(stored_histogram, dict):
        return {
            **result,
            "status": "INVALID",
            "reason": "BYTECODE_HISTOGRAM_NOT_OBJECT",
        }

    try:
        raw = structural_artifact(
            directory,
            diagnostic.get("raw_log"),
        )

        actual_sha256 = mp.sha256_file(raw)

        if actual_sha256 != diagnostic.get(
            "raw_log_sha256"
        ):
            raise ge.EvidenceError(
                "BYTECODE_RAW_LOG_SHA256_MISMATCH"
            )

        raw_text = raw.read_text(encoding="utf-8")
        parsed_histogram = ge.parse_bytecode_histogram(
            raw_text
        )

        if parsed_histogram != stored_histogram:
            raise ge.EvidenceError(
                "BYTECODE_HISTOGRAM_DIFFERS_FROM_RAW_LOG"
            )

        if diagnostic.get("status") != (
            parsed_histogram.get("status")
        ):
            raise ge.EvidenceError(
                "BYTECODE_DIAGNOSTIC_STATUS_MISMATCH"
            )

        # Sizes and execution histograms are independent measurements
        # in the same retained diagnostic log.
        parsed_size = ge.parse_bytecode_size_trace(
            raw_text
        )
        stored_size = diagnostic.get("size")

        if stored_size is None:
            if parsed_size.get("status") == "AVAILABLE":
                raise ge.EvidenceError(
                    "BYTECODE_SIZE_MISSING_FROM_CAPTURE"
                )

            size_evidence = {
                "status": "UNAVAILABLE",
                "reason": "BYTECODE_SIZE_NOT_CAPTURED",
                "observations": [],
            }

        elif not isinstance(stored_size, dict):
            raise ge.EvidenceError(
                "BYTECODE_SIZE_NOT_OBJECT"
            )

        elif stored_size.get("status") == "AVAILABLE":
            if parsed_size != stored_size:
                raise ge.EvidenceError(
                    "BYTECODE_SIZE_DIFFERS_FROM_RAW_LOG"
                )

            instrument = diagnostic.get(
                "size_instrument"
            )

            if (
                not isinstance(instrument, dict)
                or instrument.get("status") != "AVAILABLE"
            ):
                raise ge.EvidenceError(
                    "BYTECODE_SIZE_INSTRUMENT_IDENTITY_MISSING"
                )

            size_evidence = parsed_size

        elif stored_size.get("status") == "UNAVAILABLE":
            if (
                parsed_size.get("status") != "UNAVAILABLE"
                or stored_size.get("observations") != []
            ):
                raise ge.EvidenceError(
                    "BYTECODE_SIZE_UNAVAILABLE_CONFLICT"
                )

            size_evidence = stored_size

        else:
            raise ge.EvidenceError(
                "BYTECODE_SIZE_STATUS_INVALID"
            )

    except (
        ge.EvidenceError,
        OSError,
        ValueError,
        TypeError,
    ) as exc:
        return {
            **result,
            "status": "INVALID",
            "reason": (
                exc.reason
                if isinstance(exc, ge.EvidenceError)
                else "BYTECODE_RAW_EVIDENCE_INVALID"
            ),
            "detail": str(exc),
        }

    groups = parsed_histogram.get("groups")

    if not isinstance(groups, list):
        return {
            **result,
            "status": "INVALID",
            "reason": "BYTECODE_GROUPS_NOT_LIST",
        }

    result.update({
        "capture_sha256": mp.sha256_file(
            capture_path
        ),
        "raw_log": str(raw),
        "raw_log_sha256": actual_sha256,
        "size_evidence": size_evidence,
        "size_instrument": diagnostic.get(
            "size_instrument"
        ),
        "groups": groups,
        "total_executed_instructions": (
            parsed_histogram.get(
                "total_executed_instructions"
            )
        ),
        "diagnostic_calls": diagnostic.get("calls"),
        "capture_status": (
            parsed_histogram.get("status")
        ),
    })

    if parsed_histogram.get("status") != "AVAILABLE":
        return {
            **result,
            "status": "UNAVAILABLE",
            "reason": parsed_histogram.get(
                "reason",
                "BYTECODE_HISTOGRAM_UNAVAILABLE",
            ),
        }

    available_graphs = [
        graph for graph in graph_captures
        if isinstance(graph, dict)
        and graph.get("capture_valid")
    ]

    if not available_graphs:
        return {
            **result,
            "status": "UNATTRIBUTABLE",
            "reason": "NO_VALID_GRAPH_PRODUCER",
        }

    for graph in available_graphs:
        if (
            graph.get("language") != language
            or graph.get("workload") != workload
            or graph.get("surface")
            != capture.get("surface")
            or graph.get("expected_result")
            != capture.get("expected_result")
        ):
            return {
                **result,
                "status": "INCOMPATIBLE",
                "reason": "WORKLOAD_PRODUCER_MISMATCH",
            }

        graph_harness = (
            graph.get("harness") or {}
        ).get("source_sha256")

        bytecode_harness = (
            capture.get("harness") or {}
        ).get("source_sha256")

        if not compatible_bytecode_harness_hashes(
            graph_harness,
            bytecode_harness,
            require_size_instrument=(
                size_evidence.get("status") == "AVAILABLE"
            ),
        ):
            return {
                **result,
                "status": "INCOMPATIBLE",
                "reason": "HARNESS_PRODUCER_MISMATCH",
            }

        graph_java = (
            graph.get("java") or {}
        ).get("java.runtime.version")

        bytecode_java = (
            capture.get("java") or {}
        ).get("java.runtime.version")

        if (
            not graph_java
            or graph_java != bytecode_java
        ):
            return {
                **result,
                "status": "INCOMPATIBLE",
                "reason": "JAVA_RUNTIME_MISMATCH",
            }

        if language == "protos":
            first_product = (
                graph.get("product_before") or {}
            )
            second_product = (
                capture.get("product_before") or {}
            )

            for field in (
                "revision",
                "source_state_sha256",
            ):
                if (
                    not first_product.get(field)
                    or first_product.get(field)
                    != second_product.get(field)
                ):
                    return {
                        **result,
                        "status": "INCOMPATIBLE",
                        "reason": (
                            "PROTOS_PRODUCER_MISMATCH"
                        ),
                    }

        else:
            if graph.get("peer_runtime") != (
                capture.get("peer_runtime")
            ):
                return {
                    **result,
                    "status": "INCOMPATIBLE",
                    "reason": "PEER_RUNTIME_MISMATCH",
                }

    return {
        **result,
        "status": "AVAILABLE",
        "reason": None,
    }


def attribute_bytecode_groups(
    pairing: dict[str, Any],
    bytecode: dict[str, Any],
) -> dict[str, Any]:
    """Associate only unique normalized Bytecode roots."""
    outcome: dict[str, Any] = {
        "status": "UNAVAILABLE",
        "reason": None,
        "per_compiled_root": [],
        "unattributed_groups": bytecode.get(
            "groups", []
        ),
        "bytecode_size_bytes": None,
        "bytecode_size_status": (
            "NOT_MEASURED_BY_EXECUTION_HISTOGRAM"
        ),
    }

    if bytecode.get("status") != "AVAILABLE":
        return {
            **outcome,
            "reason": bytecode.get(
                "reason", "BYTECODE_EVIDENCE_UNAVAILABLE"
            ),
        }

    if pairing.get(
        "producer_identity_compatible"
    ) is not True:
        return {
            **outcome,
            "reason": "GRAPH_TIERS_NOT_COMPATIBLE",
        }

    roots = pairing.get("roots")

    if not isinstance(roots, list):
        return {
            **outcome,
            "reason": "PAIRED_ROOT_INVENTORY_UNAVAILABLE",
        }

    groups = bytecode["groups"]

    grouped: dict[str, list[dict]] = {}

    for group in groups:
        if not isinstance(group, dict):
            return {
                **outcome,
                "status": "INVALID",
                "reason": "BYTECODE_GROUP_NOT_OBJECT",
            }

        normalized = group.get(
            "normalized_root"
        )

        if not isinstance(normalized, str):
            return {
                **outcome,
                "status": "INVALID",
                "reason": "BYTECODE_ROOT_IDENTITY_MISSING",
            }

        grouped.setdefault(
            normalized, []
        ).append(group)

    root_names = []

    for row in roots:
        if not isinstance(row, dict):
            root_names.append(None)
            continue

        normalized = (
            row.get("normalized_root")
            or row.get("normalized_label")
        )

        if normalized is None:
            original = (
                row.get("root")
                or row.get("label")
            )
            if isinstance(original, str):
                normalized = ge.normalize_label(
                    original
                )

        root_names.append(normalized)

    entries = []
    used = set()

    for normalized in root_names:
        matching = (
            grouped.get(normalized, [])
            if isinstance(normalized, str)
            else []
        )

        if not isinstance(normalized, str):
            entries.append({
                "normalized_root": None,
                "status": "UNAVAILABLE",
                "reason": "COMPILED_ROOT_IDENTITY_MISSING",
                "groups": [],
            })
            continue

        if root_names.count(normalized) != 1:
            entries.append({
                "normalized_root": normalized,
                "status": "AMBIGUOUS",
                "reason": (
                    "COMPILED_ROOT_IDENTITY_COLLISION"
                ),
                "groups": [],
            })
            continue

        if len(matching) > 1:
            entries.append({
                "normalized_root": normalized,
                "status": "AMBIGUOUS",
                "reason": (
                    "BYTECODE_ROOT_IDENTITY_COLLISION"
                ),
                "groups": [],
            })
            continue

        if not matching:
            entries.append({
                "normalized_root": normalized,
                "status": "UNAVAILABLE",
                "reason": "BYTECODE_ROOT_NOT_OBSERVED",
                "groups": [],
            })
            continue

        used.add(id(matching[0]))

        entries.append({
            "normalized_root": normalized,
            "status": "AVAILABLE",
            "reason": None,
            "groups": matching,
        })

    unavailable = [
        group for group in groups
        if id(group) not in used
    ]

    return {
        **outcome,
        "status": (
            "COMPLETE"
            if entries
            and all(
                entry["status"] == "AVAILABLE"
                for entry in entries
            )
            else "PARTIAL"
        ),
        "reason": None,
        "per_compiled_root": entries,
        "unattributed_groups": unavailable,
    }




def attribute_physical_bytecode_roots(
    bytecode: dict[str, Any],
) -> dict[str, Any]:
    """Join histogram counts and exact sizes within one diagnostic JVM.

    Physical @hex identities must never be carried across JVM processes
    or interpreted as equivalent to compiler Tier 1 / Tier 2 identities.
    """
    evidence = bytecode.get("size_evidence")

    outcome: dict[str, Any] = {
        "status": "UNAVAILABLE",
        "reason": None,
        "attribution_basis": (
            "EXACT_PHYSICAL_ROOT_LABEL_WITHIN_DIAGNOSTIC_JVM"
        ),
        "compiler_tier_equivalence": "NONE",
        "compiled_root_identity": "NOT_ESTABLISHED",
        "per_histogram_root": [],
        "unattributed_size_observations": [],
    }

    if bytecode.get("capture_status") != "AVAILABLE":
        return {
            **outcome,
            "reason": "BYTECODE_HISTOGRAM_NOT_VERIFIED",
        }

    if not isinstance(evidence, dict):
        return {
            **outcome,
            "reason": "BYTECODE_SIZE_EVIDENCE_MISSING",
        }

    if evidence.get("status") != "AVAILABLE":
        return {
            **outcome,
            "reason": evidence.get(
                "reason",
                "BYTECODE_SIZE_UNAVAILABLE",
            ),
        }

    groups = bytecode.get("groups")
    observations = evidence.get("observations")

    if not isinstance(groups, list) or not isinstance(
        observations, list
    ):
        return {
            **outcome,
            "status": "INVALID",
            "reason": "INVALID_PHYSICAL_ROOT_EVIDENCE",
        }

    if not groups or not observations:
        return {
            **outcome,
            "reason": "PHYSICAL_ROOT_EVIDENCE_EMPTY",
        }

    histogram = {}

    for group in groups:
        if not isinstance(group, dict):
            return {
                **outcome,
                "status": "INVALID",
                "reason": "BYTECODE_HISTOGRAM_GROUP_INVALID",
            }

        label = group.get("root")

        if not isinstance(label, str) or not label:
            return {
                **outcome,
                "status": "INVALID",
                "reason": "HISTOGRAM_PHYSICAL_ROOT_MISSING",
            }

        if label in histogram:
            return {
                **outcome,
                "status": "INVALID",
                "reason": "DUPLICATE_HISTOGRAM_PHYSICAL_ROOT",
            }

        histogram[label] = group

    sizes = {}
    instances = {}

    for observation in observations:
        if not isinstance(observation, dict):
            return {
                **outcome,
                "status": "INVALID",
                "reason": "BYTECODE_SIZE_OBSERVATION_INVALID",
            }

        label = observation.get("physical_root_label")
        instance = observation.get("root_instance")

        if (
            not isinstance(label, str)
            or not label
            or type(instance) is not int
            or instance < 1
        ):
            return {
                **outcome,
                "status": "INVALID",
                "reason": "BYTECODE_SIZE_PHYSICAL_IDENTITY_MISSING",
            }

        if label in instances and instances[label] != instance:
            return {
                **outcome,
                "status": "INVALID",
                "reason": "BYTECODE_SIZE_PHYSICAL_IDENTITY_COLLISION",
            }

        instances[label] = instance
        sizes.setdefault(label, []).append(observation)

    entries = []

    for label, group in histogram.items():
        snapshots = sizes.get(label, [])
        states = {}

        for state in ("UNCACHED", "CACHED"):
            selected = [
                item for item in snapshots
                if item.get("bytecode_tier") == state
            ]

            if not selected:
                states[state] = {
                    "status": "UNAVAILABLE",
                    "reason": "BYTECODE_STATE_NOT_OBSERVED",
                    "bytecode_bytes": None,
                    "instruction_count": None,
                    "snapshots": [],
                }
                continue

            signatures = {
                (
                    item.get("instruction_count"),
                    item.get("bytecode_bytes"),
                    item.get("first_bci"),
                    item.get("last_end_bci"),
                )
                for item in selected
            }

            stable = len(signatures) == 1

            states[state] = {
                "status": "AVAILABLE" if stable else "VARIABLE",
                "reason": (
                    None if stable else "BYTECODE_SNAPSHOTS_DIFFER"
                ),
                "bytecode_bytes": (
                    selected[0]["bytecode_bytes"] if stable else None
                ),
                "instruction_count": (
                    selected[0]["instruction_count"] if stable else None
                ),
                "snapshots": selected,
            }

        entries.append({
            "physical_root_label": label,
            "status": (
                "MATCHED" if snapshots else "UNAVAILABLE"
            ),
            "reason": (
                None if snapshots else "BYTECODE_SIZE_ROOT_NOT_OBSERVED"
            ),
            "root_instance": instances.get(label),
            "histogram_group": group,
            "interpreter_states": states,
            "size_observations": snapshots,
        })

    unused = [
        item for item in observations
        if item["physical_root_label"] not in histogram
    ]

    complete = (
        bool(entries)
        and all(entry["status"] == "MATCHED" for entry in entries)
        and not unused
    )

    return {
        **outcome,
        "status": "COMPLETE" if complete else "PARTIAL",
        "reason": None,
        "matched_roots": sum(
            entry["status"] == "MATCHED" for entry in entries
        ),
        "histogram_roots": len(entries),
        "size_roots": len(sizes),
        "per_histogram_root": entries,
        "unattributed_size_observations": unused,
    }


def attribute_bytecode_sizes(
    pairing: dict[str, Any],
    bytecode: dict[str, Any],
) -> dict[str, Any]:
    """Attribute verified bytecode snapshots to unique compiled roots.

    This is a normalized-name correlation, not proof that every
    interpreted root has a corresponding compiled root. Interpreter
    states UNCACHED/CACHED are independent of compiler tiers 1/2.
    """
    evidence = bytecode.get("size_evidence")

    observations = (
        evidence.get("observations", [])
        if isinstance(evidence, dict)
        else []
    )

    outcome: dict[str, Any] = {
        "status": "UNAVAILABLE",
        "reason": None,
        "source": "TRUFFLE_INSTRUCTION_LENGTH",
        "unit": "bytes",
        "scope": "OBSERVED_INSTRUMENTED_ROOTS",
        "attribution_basis": "NORMALIZED_ROOT_NAME_ONLY",
        "compiler_tier_equivalence": "NONE",
        "interpreted_roots_coverage": "NOT_ESTABLISHED",
        "per_compiled_root": [],
        "unattributed_observations": (
            observations
            if isinstance(observations, list)
            else []
        ),
    }

    if bytecode.get("status") != "AVAILABLE":
        return {
            **outcome,
            "reason": bytecode.get(
                "reason",
                "BYTECODE_EVIDENCE_UNAVAILABLE",
            ),
        }

    if not isinstance(evidence, dict):
        return {
            **outcome,
            "reason": "BYTECODE_SIZE_EVIDENCE_MISSING",
        }

    if evidence.get("status") != "AVAILABLE":
        return {
            **outcome,
            "reason": evidence.get(
                "reason",
                "BYTECODE_SIZE_UNAVAILABLE",
            ),
        }

    if (
        evidence.get("unit") != "bytes"
        or not isinstance(observations, list)
        or not observations
    ):
        return {
            **outcome,
            "status": "INVALID",
            "reason": "INVALID_BYTECODE_SIZE_EVIDENCE",
        }

    if pairing.get("producer_identity_compatible") is not True:
        return {
            **outcome,
            "reason": "GRAPH_TIERS_NOT_COMPATIBLE",
        }

    roots = pairing.get("roots")

    if not isinstance(roots, list):
        return {
            **outcome,
            "reason": "PAIRED_ROOT_INVENTORY_UNAVAILABLE",
        }

    grouped: dict[str, list[dict]] = {}

    for observation in observations:
        if not isinstance(observation, dict):
            return {
                **outcome,
                "status": "INVALID",
                "reason": "BYTECODE_SIZE_OBSERVATION_NOT_OBJECT",
            }

        name = observation.get("root_name")
        instance = observation.get("root_instance")
        state = observation.get("bytecode_tier")
        size = observation.get("bytecode_bytes")
        count = observation.get("instruction_count")
        first = observation.get("first_bci")
        last = observation.get("last_end_bci")

        if (
            not isinstance(name, str)
            or not name
            or type(instance) is not int
            or instance < 1
            or state not in ("UNCACHED", "CACHED")
            or type(size) is not int
            or size < 1
            or type(count) is not int
            or count < 1
            or type(first) is not int
            or type(last) is not int
            or first < 0
            or last - first != size
        ):
            return {
                **outcome,
                "status": "INVALID",
                "reason": "INVALID_BYTECODE_SIZE_OBSERVATION",
            }

        normalized = ge.normalize_label(name)
        grouped.setdefault(normalized, []).append(observation)

    root_names = []

    for row in roots:
        normalized = None

        if isinstance(row, dict):
            normalized = (
                row.get("normalized_root")
                or row.get("normalized_label")
            )

            if normalized is None:
                original = row.get("root") or row.get("label")

                if isinstance(original, str):
                    normalized = ge.normalize_label(original)

        root_names.append(
            normalized if isinstance(normalized, str) else None
        )

    entries = []
    used = set()

    for normalized in root_names:
        matching = (
            grouped.get(normalized, [])
            if normalized is not None
            else []
        )

        if normalized is None:
            entries.append({
                "normalized_root": None,
                "status": "UNAVAILABLE",
                "reason": "COMPILED_ROOT_IDENTITY_MISSING",
                "root_instance": None,
                "interpreter_states": {},
            })
            continue

        if root_names.count(normalized) != 1:
            entries.append({
                "normalized_root": normalized,
                "status": "AMBIGUOUS",
                "reason": "COMPILED_ROOT_IDENTITY_COLLISION",
                "root_instance": None,
                "interpreter_states": {},
            })
            continue

        if not matching:
            entries.append({
                "normalized_root": normalized,
                "status": "UNAVAILABLE",
                "reason": "BYTECODE_SIZE_ROOT_NOT_OBSERVED",
                "root_instance": None,
                "interpreter_states": {},
            })
            continue

        instances = {
            item["root_instance"]
            for item in matching
        }

        if len(instances) != 1:
            entries.append({
                "normalized_root": normalized,
                "status": "AMBIGUOUS",
                "reason": "BYTECODE_SIZE_PHYSICAL_ROOT_AMBIGUOUS",
                "root_instance": None,
                "observed_root_instances": sorted(instances),
                "interpreter_states": {},
            })
            continue

        states = {}

        for state in ("UNCACHED", "CACHED"):
            snapshots = [
                item for item in matching
                if item["bytecode_tier"] == state
            ]

            if not snapshots:
                states[state] = {
                    "status": "UNAVAILABLE",
                    "reason": "BYTECODE_STATE_NOT_OBSERVED",
                    "bytecode_bytes": None,
                    "instruction_count": None,
                    "snapshots": [],
                }
                continue

            signatures = {
                (
                    item["instruction_count"],
                    item["bytecode_bytes"],
                    item["first_bci"],
                    item["last_end_bci"],
                )
                for item in snapshots
            }

            if len(signatures) != 1:
                states[state] = {
                    "status": "VARIABLE",
                    "reason": "BYTECODE_SNAPSHOTS_DIFFER",
                    "bytecode_bytes": None,
                    "instruction_count": None,
                    "snapshots": snapshots,
                }
                continue

            states[state] = {
                "status": "AVAILABLE",
                "reason": None,
                "bytecode_bytes": snapshots[0]["bytecode_bytes"],
                "instruction_count": snapshots[0]["instruction_count"],
                "snapshots": snapshots,
            }

        for item in matching:
            used.add(id(item))

        if any(
            value["status"] == "VARIABLE"
            for value in states.values()
        ):
            entry_status = "VARIABLE"
        elif all(
            value["status"] == "AVAILABLE"
            for value in states.values()
        ):
            entry_status = "AVAILABLE"
        else:
            entry_status = "PARTIAL"

        entries.append({
            "normalized_root": normalized,
            "status": entry_status,
            "reason": (
                None
                if entry_status == "AVAILABLE"
                else "INTERPRETER_STATES_NOT_BOTH_STABLE"
            ),
            "root_instance": next(iter(instances)),
            "interpreter_states": states,
        })

    return {
        **outcome,
        "status": (
            "COMPLETE"
            if entries
            and all(
                entry["status"] == "AVAILABLE"
                for entry in entries
            )
            else "PARTIAL"
        ),
        "reason": None,
        "per_compiled_root": entries,
        "unattributed_observations": [
            item for item in observations
            if id(item) not in used
        ],
    }


def structural_report(
    args: argparse.Namespace,
) -> int:
    """Pair retained Tier 1 and Tier 2 evidence by compiled root."""
    tier1 = args.tier1.expanduser().resolve()
    tier2 = args.tier2.expanduser().resolve()
    bytecode = args.bytecode.expanduser().resolve()
    output = args.output.expanduser().resolve()

    if (
        tier1 == tier2
        or bytecode == tier1
        or bytecode == tier2
        or output == bytecode
        or output.is_relative_to(bytecode)
        or bytecode.is_relative_to(output)
        or output == tier1
        or output == tier2
        or output.is_relative_to(tier1)
        or output.is_relative_to(tier2)
        or tier1.is_relative_to(output)
        or tier2.is_relative_to(output)
    ):
        raise mp.UsageError(
            "Structural report inputs and output overlap"
        )

    if args.workload != "all":
        select_workloads(load_policy(), args.workload)

    if args.language not in (*LANGUAGES, "all"):
        raise mp.UsageError(
            f"Unknown language: {args.language}"
        )

    keys = set()

    for source in (tier1, tier2, bytecode):
        if not source.is_dir():
            continue

        for capture_path in source.glob(
            "*/*/capture.json"
        ):
            keys.add((
                capture_path.parent.parent.name,
                capture_path.parent.name,
            ))

    if args.workload != "all":
        keys = {
            key for key in keys
            if key[0] == args.workload
        }

    if args.language != "all":
        keys = {
            key for key in keys
            if key[1] == args.language
        }

    if not keys:
        mp.emit(
            "STRUCTURAL_REPORT",
            "NO_EXISTING_CAPTURE_INPUTS",
        )
        return mp.EXIT_INVALID

    prepare_output(output)

    generated = 0
    reused = 0
    incomplete = 0
    conflicts = 0

    for workload, language in sorted(keys):
        first_dir = tier1 / workload / language
        second_dir = tier2 / workload / language

        first, first_summary, first_info = (
            read_structural_input(
                first_dir, workload, language, 1
            )
        )
        second, second_summary, second_info = (
            read_structural_input(
                second_dir, workload, language, 2
            )
        )

        try:
            pairing = ge.pair_compiled_root_tiers(
                first,
                first_summary,
                second,
                second_summary,
            )
        except ge.EvidenceError as exc:
            pairing = {
                "status": "INVALID",
                "reason": exc.reason,
                "detail": exc.detail,
            }

        bytecode_info = read_structural_bytecode(
            bytecode / workload / language,
            workload,
            language,
            (first, second),
        )

        bytecode_attribution = (
            attribute_bytecode_groups(
                pairing,
                bytecode_info,
            )
        )

        bytecode_size_attribution = (
            attribute_bytecode_sizes(
                pairing,
                bytecode_info,
            )
        )

        status = (
            "COMPLETE"
            if (
                first_info["status"] == "AVAILABLE"
                and second_info["status"] == "AVAILABLE"
                and pairing.get("status") == "COMPLETE"
            )
            else "INCOMPLETE"
        )

        report = {
            "schema": 1,
            "mode": "cold-structural-report",
            "workload": workload,
            "language": language,
            "scope": (
                "observed-compiled-call-targets-only"
            ),
            "interpreted_roots_coverage": (
                "NOT_ESTABLISHED"
            ),
            "status": status,
            "tier_1": first_info,
            "tier_2": second_info,
            "pairing": pairing,
            "bytecode_dsl": {
                "physical_root_attribution": (
                    attribute_physical_bytecode_roots(
                        bytecode_info
                    )
                ),
                "evidence": bytecode_info,
                "attribution": bytecode_attribution,
                "size_attribution": bytecode_size_attribution,
            },
            "timing_evidence": "NONE",
        }

        destination = (
            output / workload / language
            / "structural-report.json"
        )

        if destination.is_file():
            try:
                existing = json.loads(
                    destination.read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, ValueError):
                existing = None

            if existing == report:
                reused += 1
            else:
                conflicts += 1
                mp.emit(
                    "STRUCTURAL_REPORT_CONFLICT",
                    destination,
                )
            continue

        mp.write_json(destination, report)
        generated += 1

        if status != "COMPLETE":
            incomplete += 1

    mp.emit("STRUCTURAL_REPORT_CREATED", generated)
    mp.emit("STRUCTURAL_REPORT_REUSED", reused)
    mp.emit("STRUCTURAL_REPORT_INCOMPLETE", incomplete)
    mp.emit("STRUCTURAL_REPORT_CONFLICTS", conflicts)

    return (
        mp.EXIT_OK
        if incomplete == 0 and conflicts == 0
        else mp.EXIT_INVALID
    )


def cold_jvm_options(
    policy: dict[str, Any],
    tier: int,
    first_threshold: int,
    last_threshold: int,
    dump_path: Path,
    extras: tuple[str, ...] = (),
) -> list[str]:
    """Fixed Graal thresholds; the observed tier is checked separately."""
    if tier not in (1, 2):
        raise mp.UsageError("Tier must be 1 or 2")

    if (
        type(first_threshold) is not int
        or type(last_threshold) is not int
        or first_threshold < 1
        or last_threshold <= first_threshold
    ):
        raise mp.UsageError("Invalid tier thresholds")

    reserved = (
        "-Dpolyglot.engine.MultiTier=",
        "-Dpolyglot.engine.DynamicCompilationThresholds=",
        "-Dpolyglot.engine.FirstTierCompilationThreshold=",
        "-Dpolyglot.engine.LastTierCompilationThreshold=",
        "-Dpolyglot.engine.FirstTierMinInvokeThreshold=",
        "-Dpolyglot.engine.MinInvokeThreshold=",
        "-Dpolyglot.engine.OSR=",
        "-Dpolyglot.engine.TraceCompilation=",
        "-Dpolyglot.engine.BackgroundCompilation=",
        "-Djdk.graal.Dump",
    )

    for option in extras:
        if not option.startswith(("-D", "-XX:")):
            raise mp.UsageError(f"Invalid JVM option: {option}")
        if option.startswith(reserved):
            raise mp.UsageError(f"Reserved JVM option: {option}")

    return [
        *policy["jvm_options"],
        "-Dpolyglot.engine.MultiTier=true",
        "-Dpolyglot.engine.DynamicCompilationThresholds=false",
        "-Dpolyglot.engine.FirstTierMinInvokeThreshold=1",
        "-Dpolyglot.engine.MinInvokeThreshold=1",
        "-Dpolyglot.engine.OSR=false",
        f"-Dpolyglot.engine.FirstTierCompilationThreshold={first_threshold}",
        f"-Dpolyglot.engine.LastTierCompilationThreshold={last_threshold}",
        policy["dump_path_option"] + str(dump_path),
        *extras,
    ]


def cold_invocation_arguments(
    core_arg: str,
    source: Path,
    warmup_calls: int,
    invocations: int,
) -> tuple[list[str], dict[str, int | str]]:
    """Explicit sequence following setup in one newly started JVM."""
    if type(warmup_calls) is not int or warmup_calls < 0:
        raise mp.UsageError("Invalid warmup calls")
    if type(invocations) is not int or invocations < 1:
        raise mp.UsageError("Invalid invocations")

    arguments = [
        "measure", core_arg, str(source),
        str(warmup_calls), str(invocations), "1", "-",
    ]
    sequence = {
        "process": "fresh-jvm",
        "setup": "before-cold-call",
        "cold_calls": 1,
        "warmup_calls": warmup_calls,
        "post_warmup_calls": invocations,
        "total_measured_invocations": 1 + warmup_calls + invocations,
    }
    return arguments, sequence


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="measure_graphs.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="correctness + natural-warmup graph capture")
    cap.add_argument("--dir", type=Path, help="Protos checkout (always recorded)")
    cap.add_argument("--output", type=Path)
    cap.add_argument("--language", default="all")
    cap.add_argument("--workload", default="ladder")
    cap.add_argument("--stage", default="reference", choices=("reference", "smoke"))
    cap.add_argument("--cpu", type=int)
    cap.add_argument("--remeasure", action="store_true")
    cap.add_argument("--allow-dirty-product", action="store_true")

    cold = sub.add_parser(
        "cold",
        help="fresh-JVM compilation capture of one root and tier",
    )
    cold.add_argument("--dir", type=Path, required=True)
    cold.add_argument("--output", type=Path, required=True)
    cold.add_argument("--language", choices=LANGUAGES, required=True)
    cold.add_argument("--workload", required=True)
    cold.add_argument("--tier", type=int, choices=(1, 2), required=True)
    cold.add_argument("--root", default="primary")
    cold.add_argument("--warmup-calls", type=int, default=0)
    cold.add_argument("--invocations", type=int, default=2000)
    cold.add_argument("--first-threshold", type=int, default=100)
    cold.add_argument("--last-threshold", type=int, required=True)
    cold.add_argument("--jvm-option", action="append", default=[])
    cold.add_argument("--cpu", type=int)

    bytecode = sub.add_parser(
        "bytecode",
        help="dedicated-JVM Bytecode DSL histogram",
    )
    bytecode.add_argument("--dir", type=Path)
    bytecode.add_argument("--output", type=Path, required=True)
    bytecode.add_argument("--language", choices=LANGUAGES, required=True)
    bytecode.add_argument("--workload", required=True)
    bytecode.add_argument("--version")
    bytecode.add_argument("--calls", type=int, default=100)
    bytecode.add_argument("--cpu", type=int)

    structural = sub.add_parser(
        "structural-report",
        help="pair existing per-root Tier 1 and Tier 2 evidence",
    )
    structural.add_argument("--tier1", type=Path, required=True)
    structural.add_argument("--tier2", type=Path, required=True)
    structural.add_argument("--bytecode", type=Path, required=True)
    structural.add_argument("--output", type=Path, required=True)
    structural.add_argument("--workload", default="all")
    structural.add_argument("--language", default="all")

    cold_summary = sub.add_parser(
        "cold-summarize",
        help="node counts of one selected compilation per capture",
    )
    cold_summary.add_argument("--output", type=Path, required=True)

    ana = sub.add_parser("analyze", help="IgvUtility filter of retained BGVs (Podman host)")
    ana.add_argument("--output", type=Path, required=True)
    ana.add_argument("--reanalyze", action="store_true")

    summ = sub.add_parser("summarize", help="After-TruffleTier metrics and rung matrix")
    summ.add_argument("--output", type=Path, required=True)

    ver = sub.add_parser("verify", help="producer hashes vs working tree and HEAD")
    ver.add_argument("--output", type=Path, required=True)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if args.command == "bytecode":
            return bytecode_capture(args)
        if args.command == "cold":
            return cold_capture(args)
        if args.command == "cold-summarize":
            return cold_summarize(args)
        if args.command == "structural-report":
            return structural_report(args)
        if args.command == "capture":
            return capture(args)
        if args.command == "analyze":
            return analyze(args)
        if args.command == "verify":
            return verify(args)
        return summarize(args)
    except mp.UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return mp.EXIT_USAGE
    except mp.SurfaceUnsupported as exc:
        mp.emit("SURFACE_SUPPORTED", "NO")
        mp.emit("REASON", exc.reason)
        return mp.EXIT_SURFACE_UNSUPPORTED


if __name__ == "__main__":
    sys.exit(main())
