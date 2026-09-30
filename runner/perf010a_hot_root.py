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

"""PERF010-A current-25.4 hot-root lifecycle and compiled-shape discriminator (harness).

One exact Protos revision (b72778ca..., 0.3.119-SNAPSHOT), one canonical GraalVM 25.4.4.1.1 toolchain,
compiler lifecycle plus compiled-shape diagnostic evidence, no timing. It is not PERF020 (there is no
control/intervention pair and no timing comparator) and it never selects an A/B/C/D causal class: the
harness collects objective evidence and a later interpretation of a real measurement classifies it.

Commands (validate << smoke << diagnostic):

  validate    static and synthetic only: no Docker, no compiler run, no timing.
  smoke       admission on the real toolchain: builds and admits the exact product, builds the overlay
              image, proves correctness and root identity, and runs ONE bounded unit (lifecycle and
              graph run kinds) to prove that 25.4 accepts every diagnostic option and produces the
              expected artifacts. Retains nothing under results/. Its output is admission evidence,
              not the authoritative measurement.
  diagnostic  the authoritative measurement: every required unit, both run kinds, retained evidence.
              Requires the exact clean published harness revision. NOT executed by this slice.

Evidence unit: exact product revision and version, exact harness revision, canonical toolchain and
runtime identity, overlay image identity and the SHA-256 of the harness Java compiled into it, host and
CPU policy, per workload and variant the source SHA-256 and correctness result, the diagnostic option
set, the raw logs (byte for byte), the root identity inventory, the normalized lifecycle, the dump
manifest with its root correlation, and the compiled-shape result. Derived views are reproducible from
the raw files.

Measurement phases: the driver prints objective startup/warmup/steady/closing/end markers on stderr, the
stream of the compiler trace, so every record is assigned to a phase by its position alone. Lifecycle is
classified from the lifecycle run kind, which has no graph dumping and so cannot be perturbed by
dump-induced compilation slowdown; the graph run kind exists for the dumps and keeps the same options so
every dump correlates to its compilation by CompId.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from typing import Any
import importlib.util


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
contract = _sibling("perf010a_hot_root_contract")

ROOT = contract.ROOT
require = contract.require
dist006d = contract.load_dist006d()
EVIDENCE_SCHEMA = "perf010a-hot-root-evidence-v1"
CONTAINER_WORK = "/work"
DIAG_OUT = "/diag-out"


# --- diagnostic command lines ------------------------------------------------------------------------


def kind_options(cfg: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """The ordered option list of a run kind, resolving `extends` (lifecycle first)."""
    spec = cfg["diagnostic"]["run_kinds"][kind]
    inherited = kind_options(cfg, spec["extends"]) if "extends" in spec else []
    return [*inherited, *spec["options"]]


def java_args(
    cfg: dict[str, Any],
    kind: str,
    unit: dict[str, Any],
    iterations: tuple[int, int],
    source_container: str,
) -> list[str]:
    diagnostic = cfg["diagnostic"]
    options: list[str] = []

    for option in kind_options(cfg, kind):
        name = option["name"]
        value = option["value"]

        if name.startswith("polyglot."):
            engine_option = name.removeprefix("polyglot.")
            options.append(
                "-Dperf010a.hotRoot.engineOption."
                + engine_option
                + "="
                + str(value)
            )
        else:
            options.append(
                "-D" + name + "=" + str(value)
            )

    options.append(
        "-Dperf010a.hotRoot.targetSource="
        + unit["source_name"]
    )

    return [
        *diagnostic["jvm_args"],
        *options,
        "-cp",
        cfg["image"]["diagnostic_classpath"],
        "Perf010aHotRootDriver",
        source_container,
        unit["expected"],
        str(iterations[0]),
        str(iterations[1]),
        diagnostic["identity_output_container_path"],
    ]


def scan_option_problems(stderr_text: str) -> list[str]:
    return trace.find_option_rejections(stderr_text)


# --- sources -------------------------------------------------------------------------------------------


def workload_by_id(cfg: dict[str, Any], workload_id: str) -> dict[str, Any]:
    return next(w for w in cfg["workloads"] if w["id"] == workload_id)


def control_bytes(canonical: bytes, workload: dict[str, Any]) -> bytes:
    """The workload-control source: the workload target statement replaced by `sink = 42`."""
    try:
        text = canonical.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError(f"workload source {workload['id']} is not valid UTF-8") from error
    count = text.count(workload["target_text"])
    require(count == 1, f"expected exactly one target statement in {workload['id']}, found {count}")
    return text.replace(workload["target_text"], workload["control_text"], 1).encode("utf-8")


def require_shared_driver(cfg: dict[str, Any], canonical: bytes, workload: dict[str, Any]) -> None:
    text = canonical.decode("utf-8")
    require(cfg["shared_driver"]["text"] in text, f"{workload['id']}: the shared repeat driver is not in the built source")
    require(text.count(workload["target_text"]) == 1, f"{workload['id']}: the workload target statement is not unique")


# --- build and admission -------------------------------------------------------------------------------


def admit(cfg: dict[str, Any], cpu: str) -> dict[str, Any]:
    """Build and admit the exact product, then build the diagnostic overlay FROM it."""
    protos = cfg["protos"]
    build = exact_product.admit_exact_product(dist006d, cfg, protos["revision"], protos["version"], cpu, cwd=ROOT)
    build["revision_label"] = dist006d.image_revision_label(build["tag"])
    contract.verify_admitted_build(cfg, build)

    overlay_tag = f"{cfg['image']['overlay_tag_prefix']}:{protos['revision'][:12]}"
    overlay_identity = exact_product.build_overlay(
        dist006d,
        build["tag"],
        overlay_tag,
        contract.OVERLAY_DOCKERFILE,
        {"PROTOS_REVISION": protos["revision"], "EXPECTED_JDK_VERSION": contract.EXPECTED_JDK_VERSION},
        cwd=ROOT,
    )
    hashes = exact_product.image_bytes(overlay_tag, cpu, cfg["image"]["harness_sources_hash_file"], cwd=ROOT).decode("utf-8")
    compiled = {}
    for line in hashes.splitlines():
        digest, _, name = line.partition("  ")
        compiled[name.strip()] = digest
    expected = {
        Path(rel).name: digest
        for rel, digest in cfg["reused_infrastructure"]["source_identity_mechanism"]["files"].items()
    }
    for path in (contract.INSTRUMENT_JAVA, contract.PROVIDER_JAVA, contract.DRIVER_JAVA):
        expected[path.name] = exact_product.sha256_file(path)
    for name, digest in expected.items():
        require(compiled.get(name) == digest, f"HARNESS_SOURCE_MISMATCH: {name} compiled into the image differs from the repository file")
    build["overlay_tag"] = overlay_tag
    build["overlay_image_identity"] = overlay_identity
    build["harness_sources_sha256"] = compiled
    return build


def read_sources(cfg: dict[str, Any], build: dict[str, Any], cpu: str) -> dict[str, dict[str, Any]]:
    """Canonical and workload-control source bytes of every workload, from the built image."""
    out: dict[str, dict[str, Any]] = {}
    for workload in cfg["workloads"]:
        canonical = exact_product.image_bytes(build["tag"], cpu, f"{cfg['image']['corpus_dir']}/{workload['source']}", cwd=ROOT)
        require_shared_driver(cfg, canonical, workload)
        control = control_bytes(canonical, workload)
        out[workload["id"]] = {
            "canonical": canonical,
            "workload_control": control,
            "sha256": {"canonical": exact_product.sha256_bytes(canonical), "workload_control": exact_product.sha256_bytes(control)},
        }
    return out


def correctness_gate(cfg: dict[str, Any], build: dict[str, Any], cpu: str, unit: dict[str, Any], source_path: Path) -> dict[str, Any]:
    """Correctness PASS for the very workload and variant about to be diagnosed, through the reused
    DIST006-D driver, before any diagnostic run is accepted."""
    result = dist006d.driver_correctness(build["tag"], cpu, "", unit["expected"], source_host=source_path)
    require(result["observed"] == unit["expected"], f"CORRECTNESS_FAILED: {unit['id']}")
    return {"unit": unit["id"], "expected": unit["expected"], "observed": result["observed"], "runtime": result["runtime"], "result": "PASS"}


def write_unit_source(work: Path, unit: dict[str, Any], data: bytes) -> Path:
    """The source is written under its canonical file name: the instrument selects it by Source name."""
    directory = work / unit["slug"]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / unit["source_name"]
    path.write_bytes(data)
    return path


# --- one diagnostic run ------------------------------------------------------------------------------------


def run_kind(
    cfg: dict[str, Any],
    build: dict[str, Any],
    cpu: str,
    unit: dict[str, Any],
    kind: str,
    source_path: Path,
    source_sha256: str,
    iterations: tuple[int, int],
    logs_dir: Path,
    dump_dir: Path,
) -> dict[str, Any]:
    """Run one unit once: raw logs byte for byte, an isolated `/diag-out` volume, identity inventory."""
    diagnostic = cfg["diagnostic"]
    volume_host = dump_dir
    volume_host.mkdir(parents=True, exist_ok=True)
    (volume_host / "graal_dumps").mkdir(exist_ok=True)
    stdout_path = logs_dir / f"{kind}.stdout.log"
    stderr_path = logs_dir / f"{kind}.stderr.log"
    run = exact_product.run_isolated(
        tag=build["overlay_tag"],
        cpu=cpu,
        entrypoint="java",
        args=java_args(cfg, kind, unit, iterations, f"{CONTAINER_WORK}/{unit['source_name']}"),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        volumes=[(source_path.parent, CONTAINER_WORK, "ro"), (volume_host, DIAG_OUT, "rw")],
        user=f"{os.getuid()}:{os.getgid()}",
        timeout_seconds=diagnostic["unit_timeout_seconds"][kind],
        cwd=ROOT,
    )
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    problems = scan_option_problems(stderr_text)
    require(not problems, f"DIAGNOSTIC_OPTION_REJECTED: unit={unit['id']} kind={kind}: {problems[:3]}")
    require(not run["timed_out"], f"DIAGNOSTIC_RUN_TIMED_OUT: unit={unit['id']} kind={kind}")

    completed = run["returncode"] == 0
    summary: dict[str, Any] = {}
    stdout_lines = [ln for ln in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if completed and stdout_lines:
        summary = json.loads(stdout_lines[-1])
    if completed:
        require(summary.get("mode") == "hot-root-diagnostic" and summary.get("observed") == unit["expected"], f"DIAGNOSTIC_RESULT_MISMATCH: unit={unit['id']} kind={kind}")
        require(summary.get("runtime") == contract.EXPECTED_RUNTIME, f"DIAGNOSTIC_RUNTIME_MISMATCH: unit={unit['id']} kind={kind}")
        require(summary.get("source_sha256") == source_sha256, f"DIAGNOSTIC_SOURCE_MISMATCH: unit={unit['id']} kind={kind}")
    else:
        raise RuntimeError(f"DIAGNOSTIC_RUN_FAILED: unit={unit['id']} kind={kind} returncode={run['returncode']}\n" + stderr_text[-4000:])

    records = trace.split_records(stderr_text)
    diagnostic_lifecycle = lifecycle_mod.normalize_lifecycle(
        records,
        first_tier=diagnostic["tier_model"]["first_tier"],
        final_tier=diagnostic["tier_model"]["final_tier"],
        replacement_patterns=cfg["lifecycle"]["replacement_reason_patterns"],
        required_phases=tuple(diagnostic["required_phase_sequence"]),
        process_completed=completed,
    )
    identity_document = identity.validate_identity_document(
        json.loads((volume_host / "root-identity.json").read_text(encoding="utf-8")),
        expected_source_name=unit["source_name"],
        expected_source_sha256=source_sha256,
    )
    return {
        "run": run,
        "summary": summary,
        "records": records,
        "lifecycle": diagnostic_lifecycle,
        "identity_document": identity_document,
        "deprecated_options": trace.deprecated_options(records),
        "dump_dir": volume_host / "graal_dumps",
    }


# --- one unit ------------------------------------------------------------------------------------------------


def diagnose_unit(
    cfg: dict[str, Any],
    build: dict[str, Any],
    cpu: str,
    unit: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    work: Path,
    dump_root: Path,
    run_id: str,
    iterations: tuple[int, int],
    evidence_dir: Path,
    kinds: tuple[str, ...],
) -> dict[str, Any]:
    workload = workload_by_id(cfg, unit["workload"])
    data = sources[unit["workload"]][unit["variant"]]
    source_sha256 = sources[unit["workload"]]["sha256"][unit["variant"]]
    source_path = write_unit_source(work, unit, data)
    correctness = correctness_gate(cfg, build, cpu, unit, source_path)
    print(f"PERF010A_HOT_ROOT CORRECTNESS PASS unit={unit['id']}", flush=True)

    evidence_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = evidence_dir / "logs"
    runs: dict[str, Any] = {}
    for kind in kinds:
        result = run_kind(cfg, build, cpu, unit, kind, source_path, source_sha256, iterations, logs_dir, contract.unit_dump_dir(dump_root, run_id, unit, kind))
        resolution = identity.resolve_roles(result["identity_document"], workload["roles"], unit["variant"], cfg["root_kind_markers"])
        try:
            identity.require_roles_resolved(resolution)
        except RuntimeError:
            print("\n".join(identity.inventory_summary(result["identity_document"])), flush=True)
            raise
        rows = identity.correlate_roles(resolution, result["lifecycle"])
        result["resolution"] = resolution
        result["rows"] = rows
        runs[kind] = result
        states = lifecycle_mod.summarize_states(result["lifecycle"])
        print(f"PERF010A_HOT_ROOT RUN unit={unit['id']} kind={kind} roots={len(rows)} {json.dumps(states, sort_keys=True)}", flush=True)

    manifest = None
    facts: dict[str, Any] = {}
    if "graph" in runs:
        graph = runs["graph"]
        manifest = shape.dump_manifest(graph["dump_dir"], graph["lifecycle"], graph["records"])
        facts_dir = graph["dump_dir"].parent / "shape-facts"
        if facts_dir.is_dir():
            for path in sorted(facts_dir.glob("*.json")):
                document = shape.validate_shape_facts(json.loads(path.read_text(encoding="utf-8")))
                facts[document["durable_id"]] = document
    return {"unit": unit, "correctness": correctness, "source_sha256": source_sha256, "runs": runs, "dump_manifest": manifest, "facts": facts}


def unit_record(cfg: dict[str, Any], diagnosed: dict[str, Any]) -> dict[str, Any]:
    """The retained per-unit record. The lifecycle classification comes from the lifecycle run; the
    graph run supplies dumps and shape."""
    runs = diagnosed["runs"]
    primary = runs.get("lifecycle") or runs["graph"]
    tier = cfg["diagnostic"]["tier_model"]
    record: dict[str, Any] = {
        "unit": diagnosed["unit"]["id"],
        "workload": diagnosed["unit"]["workload"],
        "variant": diagnosed["unit"]["variant"],
        "source_sha256": diagnosed["source_sha256"],
        "correctness": diagnosed["correctness"],
        "lifecycle_source": "lifecycle" if "lifecycle" in runs else "graph",
        "required_roots": [{k: v for k, v in row.items() if k != "events"} | {"event_count": len(row["events"])} for row in primary["rows"]],
        "run_kinds": {},
    }
    for kind, result in runs.items():
        record["run_kinds"][kind] = {
            "returncode": result["run"]["returncode"],
            "stdout_sha256": result["run"]["stdout_sha256"],
            "stderr_sha256": result["run"]["stderr_sha256"],
            "deprecated_options": result["deprecated_options"],
            "run_complete": result["lifecycle"]["run"]["complete"],
            "phase_sequence": result["lifecycle"]["run"]["phase_sequence"],
            "anomalies": result["lifecycle"]["anomalies"],
            "root_count_in_trace": len(result["lifecycle"]["roots"]),
        }
    if diagnosed["dump_manifest"] is not None:
        graph = runs["graph"]
        partial = shape.partial_pe_views(graph["rows"], graph["records"], graph["lifecycle"], tier["final_tier"])
        by_durable = {row["durable_id"]: row for row in graph["rows"]}
        stable_rows = []
        for row in primary["rows"]:
            # Facts and dumps belong to the graph run's own compilations; whether the root stably
            # compiled is decided by the lifecycle run, which graph dumping cannot perturb.
            counterpart = by_durable.get(row["durable_id"])
            stable_rows.append(row if counterpart is None else {**counterpart, "STABLE_FINAL_OPTIMIZED_STATE": row["STABLE_FINAL_OPTIMIZED_STATE"]})
        record["compiled_shape"] = shape.classify_shape(
            stable_rows,
            diagnosed["facts"],
            partial,
            families=cfg["shape"]["families"],
            other_family=cfg["shape"]["other_family"],
            final_tier=tier["final_tier"],
            min_count=cfg["shape"]["min_count_for_yes"],
        )
        record["dump_manifest_summary"] = {k: diagnosed["dump_manifest"][k] for k in ("total_bytes", "compilations_without_dump", "uncorrelated_files", "log_dump_files_missing_on_disk", "disk_dump_files_missing_from_log")} | {"files": len(diagnosed["dump_manifest"]["files"])}
        record["shape_facts_supplied"] = sorted(diagnosed["facts"])
    return record


def classification_inputs(unit_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Objective predicates a later executor applies to the causal decision table. No class is chosen."""
    rows = [(u["unit"], r) for u in unit_records for r in u["required_roots"]]

    def units_where(pred: Any) -> list[str]:
        return sorted({f"{unit}::{r['role_id']}::{r['kind']}" for unit, r in rows if pred(r)})

    families: dict[str, dict[str, list[str]]] = {}
    for u in unit_records:
        for family, values in (u.get("compiled_shape") or {"families": {}})["families"].items():
            bucket = families.setdefault(family, {"YES": [], "NO": [], "INCONCLUSIVE": []})
            bucket[values["SURVIVES_OPTIMIZED_GRAPH"]].append(u["unit"])
    return {
        "A_required_roots_permanently_failed_without_later_success": units_where(lambda r: r["classes"] is not None and r["classes"]["permanent_bailout"]),
        "B_required_roots_compiled_but_not_stable": units_where(lambda r: r["STABLE_FINAL_OPTIMIZED_STATE"] == "NO" and r["classes"] is not None and r["classes"]["final_tier_done"]),
        "required_roots_stable": units_where(lambda r: r["STABLE_FINAL_OPTIMIZED_STATE"] == "YES"),
        "required_roots_inconclusive": units_where(lambda r: r["STABLE_FINAL_OPTIMIZED_STATE"] == "INCONCLUSIVE"),
        "C_D_family_survival_by_unit": families,
        "note": "predicates only; the causal class A/B/C/D is decided later from these and the raw evidence",
    }


# --- evidence ------------------------------------------------------------------------------------------------


def host_record(cpu: str) -> dict[str, Any]:
    return {**dist006d.host_identity(), "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu}, "python": platform.python_version()}


def write_unit_files(evidence_dir: Path, diagnosed: dict[str, Any]) -> None:
    for kind, result in diagnosed["runs"].items():
        base = evidence_dir / kind
        base.mkdir(parents=True, exist_ok=True)
        (base / "root-identity.json").write_text(json.dumps(result["identity_document"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (base / "lifecycle.json").write_text(json.dumps(result["lifecycle"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (base / "role-resolution.json").write_text(json.dumps(result["resolution"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if diagnosed["dump_manifest"] is not None:
        (evidence_dir / "dump-manifest.json").write_text(json.dumps(diagnosed["dump_manifest"], indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_readme(cfg: dict[str, Any], raw: dict[str, Any]) -> str:
    lines = [
        "# PERF010-A current-25.4 hot-root lifecycle and compiled-shape diagnostic",
        "",
        "Diagnostic evidence, not timing. `raw.json` and the per-unit raw logs are authoritative; every other file is a derived view.",
        "",
        f"- Protos revision: `{raw['protos']['revision']}` (`{raw['protos']['version']}`)",
        f"- Harness revision: `{raw['harness_revision']}`",
        f"- Toolchain: GraalVM `{cfg['toolchain']['graalvm']['release']}`, JDK `{cfg['toolchain']['graalvm']['jdk_version']}`, JVMCI `{cfg['toolchain']['jvmci']}`",
        f"- Runtime: `{contract.EXPECTED_RUNTIME}`",
        f"- CPU: `--cpuset-cpus {raw['host']['cpu_policy']['cpuset']}`, network `none`",
        f"- Iterations: warmup {raw['iterations']['warmup']}, steady {raw['iterations']['steady']} (correctness enforced on every iteration)",
        "- `CAUSAL_CLASS=NOT_CLASSIFIED`: the A/B/C/D classification is a later interpretation of these predicates and the raw evidence.",
        "- Raw graph dumps are a bulky local artifact; their size and SHA-256 are in each unit's `dump-manifest.json`.",
        "",
        "## Decision table for the later executor",
        "",
        "```text",
        "A COMPILATION_FAILURE                required roots permanently fail without a later successful final optimized state",
        "B COMPILATION_LIFECYCLE_INSTABILITY  roots compile but invalidate/recompile, are replaced, or do not keep a stable optimized state",
        "C COMPILED_BUT_EXPENSIVE_SURVIVING_MACHINERY   required roots stably compile and the late graph retains implementation-only machinery",
        "D MATURE_COMPILED_FORM_WITH_RESIDUAL_SEMANTIC_COST   required roots stably compile and the investigated machinery is removed",
        "```",
        "",
        "Each unit's required roots carry `OPTIMIZATION_STATE`, `TIER_REACHED`, `FAILURE_OR_BAILOUT`, `INVALIDATION_OR_RECOMPILATION` and `STABLE_FINAL_OPTIMIZED_STATE`; every candidate family carries `SURVIVES_AFTER_PARTIAL_EVALUATION` and `SURVIVES_OPTIMIZED_GRAPH` (`YES`/`NO`/`INCONCLUSIVE`). A `NO` needs a complete late view with source positions; a missing or partial view is `INCONCLUSIVE`.",
        "",
    ]
    return "\n".join(lines)


def diagnostic_command(harness_revision: str | None) -> None:
    cfg = contract.validate()
    harness = dist006d.exact_published_harness_revision(harness_revision)
    out = ROOT / cfg["retention"]["output"]
    dist006d.prepare_output(out)
    dump_root = ROOT / cfg["retention"]["dump_root_default"]
    run_id = "diagnostic-" + harness[:12]
    cpu = dist006d.first_cpu()
    build = admit(cfg, cpu)
    sources = read_sources(cfg, build, cpu)
    iterations = (cfg["diagnostic"]["warmup_iterations"], cfg["diagnostic"]["steady_iterations"])
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="perf010a-hot-root-") as tmp:
        for unit in contract.units(cfg):
            evidence_dir = contract.unit_evidence_dir(out, unit)
            diagnosed = diagnose_unit(cfg, build, cpu, unit, sources, Path(tmp), dump_root, run_id, iterations, evidence_dir, contract.RUN_KINDS)
            write_unit_files(evidence_dir, diagnosed)
            records.append(unit_record(cfg, diagnosed))
    raw = {
        "schema": EVIDENCE_SCHEMA,
        "evidence_status": "RETAINED_DIAGNOSTIC_NOT_TIMING",
        "protos": {**cfg["protos"], "source_head": build["source_head"], "revision_label": build["revision_label"], "product_version": build["product_version"]},
        "harness_revision": harness,
        "toolchain": build["toolchain"],
        "runtime_identity": build["runtime"],
        "base_image_identity": build["base_image_identity"],
        "built_image_identity": build["built_image_identity"],
        "overlay_image_identity": build["overlay_image_identity"],
        "harness_sources_sha256": build["harness_sources_sha256"],
        "host": host_record(cpu),
        "iterations": {"warmup": iterations[0], "steady": iterations[1]},
        "diagnostic_options": {kind: kind_options(cfg, kind) for kind in contract.RUN_KINDS},
        "units": records,
        "classification_inputs": classification_inputs(records),
        "causal_class": cfg["boundaries"]["causal_class_in_harness"],
        "timing_evidence": False,
    }
    (out / "raw.json").write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "README.md").write_text(render_readme(cfg, raw), encoding="utf-8")
    exact_product.write_sha256sums(out)
    print("PERF010A_HOT_ROOT_DIAGNOSTIC=PASS")
    print("PERF010A_HOT_ROOT_EVIDENCE_STATUS=RETAINED_DIAGNOSTIC_NOT_TIMING")
    print("CAUSAL_CLASS=NOT_CLASSIFIED")


def smoke_command() -> None:
    cfg = contract.validate()
    smoke = cfg["diagnostic"]["smoke"]
    cpu = dist006d.first_cpu()
    build = admit(cfg, cpu)
    sources = read_sources(cfg, build, cpu)
    iterations = (smoke["warmup_iterations"], smoke["steady_iterations"])
    wanted = [u for u in contract.units(cfg) if u["id"] in smoke["units"]]
    work_root = ROOT / cfg["retention"]["dump_root_default"]
    work_root.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="smoke-", dir=work_root))
    with tempfile.TemporaryDirectory(prefix="perf010a-hot-root-") as tmp:
        for unit in wanted:
            diagnosed = diagnose_unit(cfg, build, cpu, unit, sources, Path(tmp), run_root, "smoke", iterations, run_root / "evidence" / unit["slug"], contract.RUN_KINDS)
            write_unit_files(run_root / "evidence" / unit["slug"], diagnosed)
            manifest = diagnosed["dump_manifest"]
            require(manifest["files"], "SMOKE_NO_GRAPH_DUMP: the graph run produced no dump file; the dump options were not honoured")
            print(f"PERF010A_HOT_ROOT_SMOKE_DUMPS files={len(manifest['files'])} bytes={manifest['total_bytes']} uncorrelated={len(manifest['uncorrelated_files'])}")
            for kind, result in diagnosed["runs"].items():
                print(f"PERF010A_HOT_ROOT_SMOKE_DEPRECATED_OPTIONS kind={kind} {result['deprecated_options']}")
    print("PERF010A_HOT_ROOT_SMOKE_ARTIFACTS=" + str(run_root))
    print("RETAINED_EVIDENCE=NO")
    print("TIMING_EVIDENCE=NO")
    print("AUTHORITATIVE_DISCRIMINATOR_EXECUTED=NO")
    print("PERF010A_HOT_ROOT_SMOKE=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "smoke", "diagnostic"))
    parser.add_argument("--harness-revision")
    args = parser.parse_args()
    if args.command == "validate":
        contract.validate()
    elif args.command == "smoke":
        smoke_command()
    else:
        diagnostic_command(args.harness_revision)


if __name__ == "__main__":
    main()
