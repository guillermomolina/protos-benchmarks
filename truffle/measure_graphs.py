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

    capture    (needs the product/peer JVM; no Docker)
        correctness PASS on the measured surface
          -> natural-warmup budgets from truffle/measure/graphs.json, one fresh
             JVM per budget with TraceCompilation + TraceInlining +
             TraceNodeExpansion + Dump=Truffle:1
          -> stop at the first two consecutive budgets with an identical
             trace-side signature (tier, graph count, per-unit structure)
          -> retain gzipped trace logs and the selected units' BGVs (gzipped);
             every other BGV is recorded by name/size/sha256 and discarded
    analyze    (needs Docker: scripts/igv_analyzer.sh, the published
                Graal 25.4.4.1.1 IgvUtility image; no second analyzer)
        IgvUtility filter of each retained BGV -> gzipped JSON next to it
    verify     producer hashes of every case vs working tree / HEAD
    summarize  (pure Python)
        After-TruffleTier selection, exact node counts, BGV-side stabilization
        confirmation, per-case evidence units and the rung matrix

Policy (phase, options, budgets, root identity, ladder) is data in
``truffle/measure/graphs.json``; graph logic is ``graph_evidence.py``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import graph_cache
import graph_evidence as ge
import measure_protos as mp
import workload_catalog

ROOT = mp.ROOT
TRUFFLE = mp.TRUFFLE
POLICY = TRUFFLE / "measure" / "graphs.json"
ANALYZER = ROOT / "scripts" / "igv_analyzer.sh"
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
    TRUFFLE / "measure_graphs.py",
    TRUFFLE / "graph_evidence.py",
    TRUFFLE / "graph_cache.py",
    POLICY,
    ROOT / "runner" / "compiler_trace.py",
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
        "Created by truffle/measure_graphs.py. "
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
    existing_ref = destination / graph_cache.REFERENCE_NAME

    if existing_ref.is_file() and not args.remeasure:
        referenced_dir, referenced, _ = graph_cache.resolve_reference(
            ROOT, existing_ref
        )
        reference = json.loads(existing_ref.read_text(encoding="utf-8"))
        if reference["cache_key"] == key:
            mp.emit("CASE", f"{workload}/{language} EXISTS HISTORICAL")
            return referenced

    if existing.is_file() and not args.remeasure:
        previous = json.loads(existing.read_text(encoding="utf-8"))
        if previous.get("capture_key") == key and previous.get("capture_valid"):
            mp.emit("CASE", f"{workload}/{language} EXISTS")
            return previous

    if destination.exists() and any(destination.iterdir()) and not args.remeasure:
        raise mp.UsageError(
            f"case destination already contains different evidence: {destination}"
        )

    if args.stage == "reference" and not args.remeasure:
        candidates = [
            path for path in args.historical_captures
            if path.parent.name == language
            and path.parent.parent.name == workload
        ]
        if candidates:
            adapter_hash = mp.adapter_source_sha256(
                mp.adapter_sources(cases, surface_def)
            )
            cpu, siblings, allowed = mp.choose_cpu(args.cpu)
            current_host = mp.host_identity(cpu, siblings, allowed)
            peer_hash = None
            if language != "protos":
                if not hasattr(args, "peer_classpath_hash"):
                    _, peer_cp = mp.peer_classpath()
                    args.peer_classpath_hash = mp.sha256_bytes(
                        peer_cp.encode("utf-8")
                    )
                peer_hash = args.peer_classpath_hash

            found = graph_cache.find(
                ROOT, output, candidates, key, adapter_hash,
                current_host, peer_hash,
            )
            if found is not None:
                historical_dir, historical, historical_unit = found
                historical_dir = graph_cache.publishable_source(
                    ROOT, historical_dir, historical, historical_unit
                )
                destination.mkdir(parents=True, exist_ok=True)
                reference = graph_cache.make_reference(
                    ROOT, historical_dir, historical, key
                )
                mp.write_json(existing_ref, reference)
                mp.emit(
                    "CASE",
                    f"{workload}/{language} REUSED {reference['source']}",
                )
                return historical

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
    args.historical_captures = (
        graph_cache.historical_candidates(ROOT)
        if args.stage == "reference" and not args.remeasure else []
    )
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
# analyze (Docker host)


def iter_cases(output: Path):
    for directory in sorted(output.glob("*/*")):
        if not directory.is_dir():
            continue
        capture_file = directory / "capture.json"
        reference_file = directory / graph_cache.REFERENCE_NAME
        if capture_file.is_file() and reference_file.is_file():
            raise mp.UsageError(f"ambiguous case evidence: {directory}")
        if capture_file.is_file():
            yield directory, json.loads(capture_file.read_text(encoding="utf-8"))
        elif reference_file.is_file():
            source, metadata, _ = graph_cache.resolve_reference(
                ROOT, reference_file
            )
            yield source, metadata



def require_analysis_container_runtime() -> None:
    """Fail with actionable guidance before invoking the IGV analyzer."""
    configured = os.environ.get("DOCKER", "").strip()

    if configured:
        available = shutil.which(configured)
        requested = f"DOCKER={configured}"
    else:
        available = shutil.which("podman") or shutil.which("docker")
        requested = "podman or docker"

    if available is None:
        raise mp.UsageError(
            f"CONTAINER_RUNTIME_NOT_FOUND: {requested} is unavailable. "
            "Run graph analysis outside the devcontainer, on the host "
            "with Docker or Podman installed and access to the results "
            "directory. Capture, summarize and verify do not require "
            "a container runtime."
        )


def analyze(args: argparse.Namespace) -> int:
    """IgvUtility ``filter`` (through scripts/igv_analyzer.sh only) of every
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
        "script": "scripts/igv_analyzer.sh",
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

    ana = sub.add_parser("analyze", help="IgvUtility filter of retained BGVs (Docker host)")
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
