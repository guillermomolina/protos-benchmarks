# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. A COPY OF THE LICENSE IS LOCATED IN LICENSE.TXT.

"""PERF010-A Tier-B execution-context local-storage causal Evidence Unit.

CONTROL is the clean pinned Protos revision. INTERVENTION is the same revision with only
`docker/protos-perf010a/context-storage.patch` applied inside the diagnostic image. The patch
keeps one fresh ordinary `ProtosObjectValue` per execution context while replacing only those
contexts' hot local-slot backing store with an array-backed private representation. Ordinary
objects remain LinkedHashMap-backed. No JFR/compiler tracing/profiling is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import tempfile
from typing import Any

import perf010a as common

ROOT = common.ROOT
CONFIG = ROOT / "config/perf010a-context-storage.json"
PHASE2_CONFIG = ROOT / "config/perf010a-phase2.json"
PATCH = ROOT / "docker/protos-perf010a/context-storage.patch"
CORRECTNESS_PROBE = ROOT / "docker/protos-perf010a/Perf010aContextStorageCorrectnessProbe.java"
OUTPUT_DIR = ROOT / "results/perf010a-context-storage"
EXPECTED_PROTOS_REVISION = "3e8e6b565c95eb5098c2168d241536ba13ad19e9"
EXPECTED_BENCHMARK_BASE = "fb938c1f3c4d299b125b9aa08c854ef494f2e920"
SLICE = "PERF010A_TIER_B_CONTEXT_STORAGE_CAUSAL"
ROLES = ("control", "intervention")
OBJECT_VALUE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosObjectValue.java"
PRELUDE_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosPrelude.java"
ACTIVATION_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosActivation.java"
VALUE_LOOKUP_PATH = "src/main/java/com/guillermomolina/protos/runtime/ProtosValueLookup.java"
SOURCE_ROOT = "/opt/protos-source"


def _parse_diff_paths(patch_text: str) -> set[str]:
    result: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("--- a/"):
            result.add(line[6:])
    return result


def validate() -> dict[str, Any]:
    cfg = common.load(CONFIG)
    phase2 = common.load(PHASE2_CONFIG)
    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF010-A"
    assert cfg["slice"] == SLICE
    assert cfg["protos_revision"] == EXPECTED_PROTOS_REVISION
    assert cfg["operation_count"] == phase2["operation_count"] == 10000
    assert cfg["warmup_iterations"] == phase2["warmup_iterations"] == 120
    assert cfg["steady_iterations"] == phase2["steady_iterations"] == 100
    assert cfg["block_order"] == phase2["block_order"] == ["A", "B", "A", "B"]
    assert cfg["controls"] == phase2["controls"]
    assert cfg["toolchain"] == phase2["toolchain"]
    assert cfg["ablation_patch"] == "docker/protos-perf010a/context-storage.patch"
    assert PATCH.is_file() and CORRECTNESS_PROBE.is_file()

    patch_text = PATCH.read_text(encoding="utf-8")
    assert _parse_diff_paths(patch_text) == {OBJECT_VALUE_PATH, PRELUDE_PATH}
    assert "PERF010A_CONTEXT_STORAGE_DIAGNOSTIC" in patch_text
    assert "private String[] names = new String[4];" in patch_text
    assert "private Object[] values = new Object[4];" in patch_text
    assert "perf010aDiagnosticExecutionContext" in patch_text
    assert "return ProtosObjectValue.perf010aDiagnosticExecutionContext(contextPrototype);" in patch_text
    assert "ProtosActivation.java" not in patch_text
    assert "ProtosValueLookup.java" not in patch_text
    assert "extends ProtosObjectValue" not in patch_text
    for forbidden in (
        "continueAt", "RootTag", "PrepareSendArguments", "nativeBodyProjection",
        "readLocalSlotSingleProbe", "CanonicalToBytecodeLowerer", "JFR", "jdk.jfr",
    ):
        assert forbidden not in patch_text, forbidden

    probe = CORRECTNESS_PROBE.read_text(encoding="utf-8")
    for marker in (
        "fresh context identity across calls", "parameter bind/read", "local create/read",
        "local assign", "local remove", "local shadowing", "captured lexical lookup",
        "captured lexical mutation visibility", "receiver fallback after lexical miss",
        "Context prototype/delegation behavior", "context intrinsic identity",
        "method receiver behavior", "methodHome behavior",
        "closure capture by reference mutation visibility", "interop/tooling-visible local slots",
    ):
        assert marker in probe, marker

    print("PERF010A_CONTEXT_STORAGE_VALIDATE=PASS")
    print("BENCHMARK_BASE_REVISION=" + EXPECTED_BENCHMARK_BASE)
    print("BASE_PROTOS_REVISION=" + EXPECTED_PROTOS_REVISION)
    print("CONTROL_PATCH=NONE")
    print("INTERVENTION_PATCH=docker/protos-perf010a/context-storage.patch")
    print("WORKLOAD_MATRIX_MATCHES_PHASE2=YES")
    print("TIMING_POLICY_MATCHES_PHASE2=YES")
    print("PROTOS_REPOSITORY_MODIFICATION=NONE")
    return cfg


def build_image(cfg: dict[str, Any], role: str) -> str:
    assert role in ROLES
    variant = "baseline" if role == "control" else "ablation"
    toolchain = cfg["toolchain"]
    tag = f"protos-benchmarks-perf010a-context-storage-{role}:{cfg['protos_revision'][:12]}"
    common.run([
        "docker", "build",
        "--build-arg", "GRAAL_BASE=" + toolchain["container_image"],
        "--build-arg", "PROTOS_REPOSITORY=" + cfg["protos_repository"],
        "--build-arg", "PROTOS_REVISION=" + cfg["protos_revision"],
        "--build-arg", "VARIANT=" + variant,
        "--build-arg", "ABLATION_PATCH=" + Path(cfg["ablation_patch"]).name,
        "--build-arg", "ABLATION_SLICE=" + cfg["slice"],
        "--build-arg", "EXPECTED_GRAALVM_RELEASE=" + toolchain["graalvm_release"],
        "--build-arg", "EXPECTED_JDK_VERSION=" + toolchain["jdk_version"],
        "--build-arg", "EXPECTED_CONTAINER_IMAGE=" + toolchain["container_image"],
        "--build-arg", "EXPECTED_GRAAL_COMPONENTS_VERSION=" + toolchain["graal_truffle_version"],
        "--build-arg", "EXPECTED_MAVEN_VERSION=" + toolchain["maven_version"],
        "--build-arg", "PYTHON_PACKAGE=" + toolchain["python_package"],
        "--label", "org.opencontainers.image.revision=" + cfg["protos_revision"],
        "--label", "org.protos-benchmarks.perf010a.variant=" + variant,
        "--label", "org.protos-benchmarks.perf010a.ablation-slice=" + cfg["slice"],
        "-t", tag,
        "-f", "docker/protos-perf010a/Dockerfile", ".",
    ])
    return tag


def _cat(tag: str, path: str) -> str:
    return common.output([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "cat", tag,
        f"{SOURCE_ROOT}/{path}",
    ])


def _method_region(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start + len(signature))
    return source[start:end]


def structural_gate(tags: dict[str, str]) -> dict[str, bool]:
    baseline_obj = _cat(tags["control"], OBJECT_VALUE_PATH)
    intervention_obj = _cat(tags["intervention"], OBJECT_VALUE_PATH)
    baseline_prelude = _cat(tags["control"], PRELUDE_PATH)
    intervention_prelude = _cat(tags["intervention"], PRELUDE_PATH)
    baseline_activation = _cat(tags["control"], ACTIVATION_PATH)
    intervention_activation = _cat(tags["intervention"], ACTIVATION_PATH)
    baseline_lookup = _cat(tags["control"], VALUE_LOOKUP_PATH)
    intervention_lookup = _cat(tags["intervention"], VALUE_LOOKUP_PATH)

    public_ctor = _method_region(
        intervention_obj,
        "public ProtosObjectValue(Object parent)",
        "private ProtosObjectValue(Object parent, Perf010aContextLocalSlots contextLocalSlots)",
    )
    diagnostic_storage_start = intervention_obj.index("private static final class Perf010aContextLocalSlots")
    diagnostic_storage = intervention_obj[diagnostic_storage_start:]

    checks = {
        "CONTROL_EXECUTION_CONTEXT_STORAGE_LINKED_HASH_MAP": (
            "private final Map<String, Object> localSlots = new LinkedHashMap<>();" in baseline_obj
            and "return new ProtosObjectValue(contextPrototype);" in baseline_prelude
        ),
        "INTERVENTION_EXECUTION_CONTEXT_STORAGE_NON_MAP": (
            "PERF010A_CONTEXT_STORAGE_DIAGNOSTIC" in intervention_obj
            and "private String[] names = new String[4];" in diagnostic_storage
            and "private Object[] values = new Object[4];" in diagnostic_storage
            and "perf010aContextLocalSlots.read(name)" in intervention_obj
            and "perf010aContextLocalSlots.create(name, value)" in intervention_obj
            and "perf010aContextLocalSlots.assign(name, value)" in intervention_obj
            and "perf010aContextLocalSlots.remove(name)" in intervention_obj
            and "return ProtosObjectValue.perf010aDiagnosticExecutionContext(contextPrototype);"
                in intervention_prelude
        ),
        "EXECUTION_CONTEXT_ONLY": (
            intervention_obj.count("perf010aDiagnosticExecutionContext(") == 1
            and intervention_prelude.count("perf010aDiagnosticExecutionContext(") == 1
        ),
        "ORDINARY_OBJECT_STORAGE_UNCHANGED": (
            "this.localSlots = new LinkedHashMap<>();" in public_ctor
            and "this.perf010aContextLocalSlots = null;" in public_ctor
        ),
        "RUNTIME_CLASS_UNCHANGED": (
            "public class ProtosObjectValue implements TruffleObject" in intervention_obj
            and "class ProtosObjectValue extends" not in intervention_obj
        ),
        "LEXICAL_LOOKUP_ORDER_SOURCE_UNCHANGED": baseline_activation == intervention_activation,
        "RECEIVER_FALLBACK_SOURCE_UNCHANGED": baseline_lookup == intervention_lookup,
    }
    checks["STRUCTURAL_SCOPE_VALID"] = all(checks.values())
    for key, value in checks.items():
        print(f"{key}={'YES' if value else 'NO'}")
    if not checks["STRUCTURAL_SCOPE_VALID"]:
        raise RuntimeError("context-storage structural gate failed closed")
    return checks


def correctness_probe(tag: str, cpu: str, role: str) -> str:
    source = CORRECTNESS_PROBE.resolve()
    shell = (
        "set -eu; rm -rf /tmp/perf010a-context-probe; mkdir -p /tmp/perf010a-context-probe; "
        "javac -cp '/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*' "
        "-d /tmp/perf010a-context-probe /work/Perf010aContextStorageCorrectnessProbe.java; "
        "java --enable-native-access=ALL-UNNAMED "
        "-cp '/tmp/perf010a-context-probe:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*' "
        "Perf010aContextStorageCorrectnessProbe"
    )
    p = common.run([
        "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
        "--volume", f"{source}:/work/Perf010aContextStorageCorrectnessProbe.java:ro",
        "--entrypoint", "/bin/sh", tag, "-c", shell,
    ], capture=True, check=False)
    stdout, stderr = p.stdout or "", p.stderr or ""
    if p.returncode != 0 or "PERF010A_CONTEXT_STORAGE_CORRECTNESS=PASS" not in stdout:
        raise RuntimeError(
            f"correctness probe failed role={role} returncode={p.returncode}\n"
            f"stdout:\n{stdout[-6000:]}\nstderr:\n{stderr[-6000:]}"
        )
    print(f"CORRECTNESS role={role}=PASS")
    return stdout


def build_and_gate(cfg: dict[str, Any], cpu: str) -> dict[str, Any]:
    tags = {role: build_image(cfg, role) for role in ROLES}
    identities: dict[str, Any] = {}
    for role, tag in tags.items():
        common.runtime_probe(tag, cpu)
        observed = common.variant_label_probe(tag, cpu)
        expected = "baseline" if role == "control" else "ablation"
        if observed != expected:
            raise RuntimeError(f"variant mismatch role={role}: {observed}")
        slice_label = common.ablation_slice_label_probe(tag, cpu)
        expected_slice = "none" if role == "control" else SLICE
        if slice_label != expected_slice:
            raise RuntimeError(f"ablation slice mismatch role={role}: {slice_label}")
        identities[role] = common.image_identity(tag)
    structural = structural_gate(tags)
    correctness = {role: correctness_probe(tags[role], cpu, role) for role in ROLES}
    print("CORRECTNESS_GATE=PASS")
    return {"tags": tags, "image_identity": identities, "structural": structural,
            "correctness_stdout": correctness}


def _role_order(label: str) -> tuple[str, str]:
    if label == "A": return ("control", "intervention")
    if label == "B": return ("intervention", "control")
    raise ValueError(label)


def run_blocks(cfg: dict[str, Any], tags: dict[str, str], cpu: str, work: Path, logs: Path,
               block_order: tuple[str, ...], warmup: int, steady: int,
               *, stationarity: bool) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block_index, label in enumerate(block_order):
        order = _role_order(label)
        for item in cfg["controls"]:
            workload = item["id"]
            by_role: dict[str, Any] = {}
            for role in order:
                canonical_source, control_host = common.control_source(tags[role], work, item)
                by_mode: dict[str, Any] = {}
                for mode, source_host, source_container in (
                    ("canonical", None, canonical_source),
                    ("control", control_host, "/work/source.protos"),
                ):
                    run_label = f"block{block_index}-{label}-{workload.replace('/', '__')}-{role}-{mode}"
                    result = common.timing_visible(
                        tags[role], cpu, work, logs, source_host, source_container,
                        item["expected"], run_label, warmup, steady,
                        collect_stationarity=stationarity,
                    )
                    suffix = ""
                    if result["stationarity"] is not None:
                        suffix = (
                            " last_vs_first_pct="
                            f"{result['stationarity']['last_quarter_vs_first_quarter_percent']:.4f}"
                        )
                    print(
                        f"CONTEXT_STORAGE TIMING PASS block={block_index} order={label} "
                        f"workload={workload} role={role} mode={mode} "
                        f"median_ns={result['steady_summary']['median_ns']}{suffix}", flush=True,
                    )
                    by_mode[mode] = result
                by_role[role] = by_mode
            blocks.append({
                "block_index": block_index, "block_order": label,
                "role_sequence": list(order), "workload": workload, "roles": by_role,
            })
    return blocks


def classify_block(entry: dict[str, Any]) -> dict[str, Any]:
    c = entry["roles"]["control"]
    i = entry["roles"]["intervention"]
    cc = c["canonical"]["steady_summary"]["median_ns"]
    cw = c["control"]["steady_summary"]["median_ns"]
    ic = i["canonical"]["steady_summary"]["median_ns"]
    iw = i["control"]["steady_summary"]["median_ns"]
    canonical_improvement = cc - ic
    control_movement = cw - iw
    paired = canonical_improvement - control_movement
    return {
        "block_index": entry["block_index"], "block_order": entry["block_order"],
        "workload": entry["workload"],
        "control_canonical_median_ns": cc,
        "control_workload_control_median_ns": cw,
        "intervention_canonical_median_ns": ic,
        "intervention_workload_control_median_ns": iw,
        "canonical_improvement_ns": canonical_improvement,
        "control_movement_ns": control_movement,
        "paired_control_effect_ns": paired,
        "paired_control_effect_percent": 100.0 * paired / cc,
    }


def summarize(classified: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for row in classified: by.setdefault(row["workload"], []).append(row)
    result: dict[str, dict[str, Any]] = {}
    for workload, rows in by.items():
        values = [r["paired_control_effect_percent"] for r in rows]
        med = statistics.median(values)
        result[workload] = {
            "blocks_percent": values,
            "median_percent": med,
            "mad_percent": statistics.median([abs(v - med) for v in values]),
            "min_percent": min(values), "max_percent": max(values),
        }
    return result


def interpret(summary: dict[str, dict[str, Any]]) -> dict[str, str]:
    medians = [summary[w]["median_percent"] for w in (
        "micro/slot-read", "micro/closure-call", "micro/method-call",
        "runtime/monomorphic-dispatch",
    )]
    all_blocks_positive = all(
        all(v > 0 for v in summary[w]["blocks_percent"]) for w in summary
    )
    if all(m >= 90.0 for m in medians) and all_blocks_positive:
        return {
            "scale": "ORDER_OF_MAGNITUDE",
            "runtime": "ESTABLISHED_ORDER_OF_MAGNITUDE",
            "big": "POSSIBLE", "disposition": "LARGE_EFFECT_REQUIRES_EXTERNAL_BASELINE",
            "oom": "YES", "dominant": "POSSIBLE_CONTEXT_STORAGE",
            "next": "OBTAIN_CURRENT_EXTERNAL_BASELINE",
        }
    if all(m >= 50.0 for m in medians) and all_blocks_positive:
        return {
            "scale": "MULTIPLICATIVE", "runtime": "ESTABLISHED_LARGE",
            "big": "POSSIBLE", "disposition": "LARGE_EFFECT_REQUIRES_EXTERNAL_BASELINE",
            "oom": "NO", "dominant": "POSSIBLE_CONTEXT_STORAGE",
            "next": "OBTAIN_CURRENT_EXTERNAL_BASELINE",
        }
    if all(m > 0 for m in medians):
        scale = "PERCENT_SCALE" if max(medians) < 10.0 else "TENS_OF_PERCENT"
        return {
            "scale": scale, "runtime": "ESTABLISHED_SMALL_OR_MODERATE", "big": "NO",
            "disposition": "REAL_COST_BUT_NOT_THE_BIG_COST", "oom": "NO",
            "dominant": "NOT_ESTABLISHED",
            "next": "STOP_CONTEXT_STORAGE_CANDIDATE_AND_CONTINUE_TIER_B_SEARCH",
        }
    return {
        "scale": "NO_CLEAR_EFFECT", "runtime": "NOT_ESTABLISHED", "big": "NO",
        "disposition": "NO_MATERIAL_CAUSAL_EFFECT", "oom": "NO",
        "dominant": "NOT_ESTABLISHED",
        "next": "STOP_CONTEXT_STORAGE_CANDIDATE_AND_CONTINUE_TIER_B_SEARCH",
    }


def smoke() -> None:
    cfg = validate()
    cpu = common.first_cpu()
    gated = build_and_gate(cfg, cpu)
    with tempfile.TemporaryDirectory(prefix="perf010a-context-storage-smoke-") as tmp:
        work = Path(tmp)
        blocks = run_blocks(
            cfg, gated["tags"], cpu, work, work / "logs", ("A", "B"),
            common.SMOKE_WARMUP_ITERATIONS, common.SMOKE_STEADY_ITERATIONS,
            stationarity=False,
        )
    print("PERF010A_CONTEXT_STORAGE_SMOKE_BLOCKS=" + str(len({b['block_index'] for b in blocks})))
    print("PERF010A_CONTEXT_STORAGE_SMOKE_WORKLOADS=" + str(len(cfg["controls"])))
    print("PERF010A_CONTEXT_STORAGE_SMOKE=PASS")
    print("PERF010A_CONTEXT_STORAGE_SMOKE_RETAINED=NO")
    print("PROTOS_REPOSITORY_MODIFICATION=NONE")


def reference(harness_revision: str | None, output_dir: Path | None) -> None:
    cfg = validate()
    harness_revision = common.resolved_harness_revision(harness_revision)
    if common.output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires clean exact harness")
    output_dir = output_dir or OUTPUT_DIR
    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise RuntimeError("output directory already contains evidence")
        output_dir.rmdir()
    cpu = common.first_cpu()
    gated = build_and_gate(cfg, cpu)
    output_dir.mkdir(parents=True)
    logs = output_dir / "logs"
    with tempfile.TemporaryDirectory(prefix="perf010a-context-storage-") as tmp:
        blocks = run_blocks(
            cfg, gated["tags"], cpu, Path(tmp), logs, tuple(cfg["block_order"]),
            cfg["warmup_iterations"], cfg["steady_iterations"], stationarity=True,
        )
    classified = [classify_block(b) for b in blocks]
    summary = summarize(classified)
    interpretation = interpret(summary)

    stationarity = [
        {"block_index": b["block_index"], "block_order": b["block_order"],
         "workload": b["workload"], "role": role, "mode": mode,
         **b["roles"][role][mode]["stationarity"]}
        for b in blocks for role in b["roles"] for mode in b["roles"][role]
    ]
    raw = {
        "schema_version": 1, "perf_item": "PERF010-A", "slice": SLICE,
        "harness_revision": harness_revision, "base_protos_revision": EXPECTED_PROTOS_REVISION,
        "control_patch": "none", "intervention_patch": cfg["ablation_patch"],
        "structural_scope_valid": True, "correctness_gate": "PASS",
        "evidence_status": "RETAINED", "toolchain": cfg["toolchain"],
        "host_identity": common.host_identity(), "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "operation_count": cfg["operation_count"], "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"], "block_order": cfg["block_order"],
        "built_image_identity": gated["image_identity"], "blocks": blocks,
        "classified_blocks": classified, "per_workload_summary": summary,
        "per_timed_unit_stationarity": stationarity, "interpretation": interpretation,
    }
    (output_dir / "raw.json").write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = ["workload\tpaired_effect_blocks_percent\tmedian_percent\tmad_percent\tmin_percent\tmax_percent"]
    for workload, s in summary.items():
        rows.append("\t".join([
            workload, ",".join(f"{v:.4f}" for v in s["blocks_percent"]),
            f"{s['median_percent']:.4f}", f"{s['mad_percent']:.4f}",
            f"{s['min_percent']:.4f}", f"{s['max_percent']:.4f}",
        ]))
    (output_dir / "context-storage-summary.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    stat_rows = ["block_index\tblock_order\tworkload\trole\tmode\tsteady_median_ns\tfirst_quarter_median_ns\tlast_quarter_median_ns\tlast_quarter_vs_first_quarter_percent"]
    for s in stationarity:
        stat_rows.append("\t".join([
            str(s["block_index"]), s["block_order"], s["workload"], s["role"], s["mode"],
            str(s["steady_median_ns"]), str(s["first_quarter_median_ns"]),
            str(s["last_quarter_median_ns"]), f"{s['last_quarter_vs_first_quarter_percent']:.4f}",
        ]))
    (output_dir / "stationarity.tsv").write_text("\n".join(stat_rows) + "\n", encoding="utf-8")

    readme = [
        "# PERF010-A Tier-B execution-context storage causal Evidence Unit", "",
        f"Harness revision: `{harness_revision}`", f"Protos revision: `{EXPECTED_PROTOS_REVISION}`",
        "CONTROL is clean; INTERVENTION is the same Protos revision plus the diagnostic context-storage patch.",
        "Structural and correctness gates passed before timing. No JFR/compiler tracing/IGV was used.", "",
        "| workload | blocks % | median % | MAD % |", "|---|---|---:|---:|",
    ]
    for workload, s in summary.items():
        readme.append(
            f"| {workload} | {', '.join(f'{v:.4f}' for v in s['blocks_percent'])} "
            f"| {s['median_percent']:.4f} | {s['mad_percent']:.4f} |"
        )
    readme += ["", f"PRIMARY_EFFECT_SCALE={interpretation['scale']}",
               f"TIER_B_CONTEXT_STORAGE_BIG_COST={interpretation['big']}",
               f"CANDIDATE_DISPOSITION={interpretation['disposition']}", ""]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    names = ["README.md", "raw.json", "context-storage-summary.tsv", "stationarity.tsv"]
    manifest = [f"{common.sha256(output_dir / n)}  {n}" for n in names]
    if logs.is_dir():
        for path in sorted(logs.iterdir()):
            manifest.append(f"{common.sha256(path)}  logs/{path.name}")
    (output_dir / "SHA256SUMS").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    labels = {
        "micro/slot-read": "SLOT_READ", "micro/closure-call": "CLOSURE_CALL",
        "micro/method-call": "METHOD_CALL", "runtime/monomorphic-dispatch": "MONOMORPHIC_DISPATCH",
    }
    print("SLICE_TYPE=IMPLEMENTATION_CAUSAL_EVIDENCE")
    print("IMPLEMENTATION_REPOSITORY=guillermomolina/protos-benchmarks")
    print("PROTOS_REPOSITORY_MODIFICATION=NONE")
    print("BASE_PROTOS_REVISION=" + EXPECTED_PROTOS_REVISION)
    print("CONTROL_PATCH=NONE")
    print("INTERVENTION_PATCH=" + cfg["ablation_patch"])
    print("STRUCTURAL_SCOPE_VALID=YES")
    print("CORRECTNESS_GATE=PASS")
    print("EVIDENCE_VALID=YES")
    print("EVIDENCE_STATUS=RETAINED")
    for workload, label in labels.items():
        s = summary[workload]
        print(f"{label}_PAIRED_EFFECT_BLOCKS=" + ",".join(f"{v:.4f}" for v in s["blocks_percent"]))
        print(f"{label}_PAIRED_EFFECT_MEDIAN={s['median_percent']:.4f}")
        print(f"{label}_PAIRED_EFFECT_MAD={s['mad_percent']:.4f}")
    print("PRIMARY_EFFECT_SCALE=" + interpretation["scale"])
    print("CAUSAL_RUNTIME_EFFECT=" + interpretation["runtime"])
    print("TIER_B_CONTEXT_STORAGE_BIG_COST=" + interpretation["big"])
    print("CANDIDATE_DISPOSITION=" + interpretation["disposition"])
    print("ORDER_OF_MAGNITUDE_RELEVANT=" + interpretation["oom"])
    print("PERF010A_DOMINANT_CAUSE=" + interpretation["dominant"])
    print("ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED")
    print("MORE_INVESTIGATION_OF_THIS_CANDIDATE_BEFORE_DECISION=NO")
    print("NEXT_ACTION=" + interpretation["next"])
    print("PRODUCT_COMMIT=NONE")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("validate", "smoke", "reference"))
    ap.add_argument("--harness-revision")
    ap.add_argument("--output-dir")
    args = ap.parse_args()
    if args.command == "validate": validate(); return
    if args.command == "smoke": smoke(); return
    reference(args.harness_revision, Path(args.output_dir) if args.output_dir else None)


if __name__ == "__main__":
    main()
