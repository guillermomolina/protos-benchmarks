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

"""Compiled-shape evidence: dump manifest correlation and candidate-family classification (pure).

Two things live here, both independent of Docker:

1. The graph-dump manifest. Every dump file of one unit's isolated dump directory is listed with its
   size and SHA-256 and correlated to the compilation that produced it. Graal names a dump
   `TruffleHotSpotCompilation-<CompId>[<label>].bgv` and `opt done` carries the same `CompId`, so the
   correlation key is objective; the label is only a cross-check. Compilations without a dump and
   dumps without a compilation are reported, never dropped.

2. Candidate-family classification from shape facts (schema `perf010a-shape-facts-v1`): per view
   (`pe` after partial evaluation, `late` late enough to show what escape analysis removed) a list of
   graph nodes of kind allocation / invoke / field access with the Java frames they are attributed to.
   `SURVIVES_OPTIMIZED_GRAPH` is decided from the late view only and `SURVIVES_AFTER_PARTIAL_EVALUATION`
   from the pe view only; a candidate that is present after partial evaluation and absent late is
   reported as removed, never as surviving. YES needs a matching node. NO needs a view that is complete
   and carries source positions and has no matching node. Everything else is INCONCLUSIVE, so a missing
   or partial view can never turn into a NO.

`perf_warn_view` turns the retained `perf warn` compiler records (calls that survived partial
evaluation, with their attributed stack) into a partial pe view: it can prove presence (YES) but,
because only problem calls are printed, never absence.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Callable


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


trace = _sibling("compiler_trace")
exact_product = _sibling("exact_product")

FACTS_SCHEMA = "perf010a-shape-facts-v1"
MANIFEST_SCHEMA = "perf010a-dump-manifest-v1"
VIEWS = ("pe", "late")
NODE_KINDS = ("allocation", "invoke", "field_load", "field_store", "branch", "call_edge", "other")
SURVIVAL = ("YES", "NO", "INCONCLUSIVE")


# --- dump manifest -----------------------------------------------------------------------------


def dump_manifest(
    dump_dir: Path,
    lifecycle: dict[str, Any],
    records: list[Any],
    *,
    hasher: Callable[[Path], str] = exact_product.sha256_file,
) -> dict[str, Any]:
    """List and correlate every dump below `dump_dir` (one unit's isolated directory)."""
    done_by_comp_id: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for key, root in lifecycle["roots"].items():
        for event in root["events"]:
            if event["kind"] == trace.OPT_DONE and event["comp_id"] is not None:
                done_by_comp_id.setdefault(event["comp_id"], []).append((key, event))

    files: list[dict[str, Any]] = []
    seen_comp_ids: set[int] = set()
    for path in sorted(p for p in dump_dir.rglob("*") if p.is_file()) if dump_dir.is_dir() else []:
        name = trace.DUMP_NAME_RE.search(path.name)
        row: dict[str, Any] = {
            "path": path.relative_to(dump_dir).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": hasher(path),
            "comp_id": int(name.group("comp_id")) if name else None,
            "label": name.group("label") if name else None,
            "correlation": "UNCORRELATED",
            "run_local_key": None,
            "tier": None,
        }
        if row["comp_id"] is not None:
            seen_comp_ids.add(row["comp_id"])
            matches = done_by_comp_id.get(row["comp_id"], [])
            if len(matches) == 1:
                key, event = matches[0]
                row["run_local_key"] = key
                row["tier"] = event["tier"]
                row["correlation"] = (
                    "COMP_ID" if lifecycle["roots"][key]["label"] == row["label"] else "COMP_ID_LABEL_MISMATCH"
                )
            elif len(matches) > 1:
                row["correlation"] = "COMP_ID_AMBIGUOUS"
            else:
                keys = lifecycle["label_index"].get(row["label"], [])
                if len(keys) == 1:
                    row["run_local_key"] = keys[0]
                    row["correlation"] = "LABEL_ONLY"
        files.append(row)

    without_dump = [
        {"run_local_key": key, "comp_id": comp_id, "tier": event["tier"]}
        for comp_id, matches in sorted(done_by_comp_id.items())
        for key, event in matches
        if comp_id not in seen_comp_ids
    ]
    log_paths = {
        record.fields["path"].rsplit("/", 1)[-1] for record in records if record.kind == trace.DUMP_FILE
    }
    disk_names = {Path(row["path"]).name for row in files}
    return {
        "schema": MANIFEST_SCHEMA,
        "directory": dump_dir.name,
        "files": files,
        "total_bytes": sum(row["size_bytes"] for row in files),
        "compilations_without_dump": without_dump,
        "log_dump_files_missing_on_disk": sorted(log_paths - disk_names),
        "disk_dump_files_missing_from_log": sorted(disk_names - log_paths),
        "uncorrelated_files": [row["path"] for row in files if row["correlation"] == "UNCORRELATED"],
    }


def member_dumps(row: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """The dump files whose compilation belongs to one required root (by run-local key)."""
    key = (row.get("run_local_key") or {}).get("key") if isinstance(row.get("run_local_key"), dict) else None
    if key is None:
        return []
    return [
        {"path": f["path"], "comp_id": f["comp_id"], "tier": f["tier"], "sha256": f["sha256"], "correlation": f["correlation"]}
        for f in manifest["files"]
        if f["run_local_key"] == key
    ]


# --- partial pe view from perf warn records -----------------------------------------------------


def attribute_perf_warnings(records: list[Any], lifecycle: dict[str, Any]) -> dict[str, dict[int, list[Any]]]:
    """key -> completion-event seq -> the `perf warn` records printed for that compilation.

    A warning is printed at the end of partial evaluation, before the compilation completes, so it
    belongs to the first `opt done` / `opt failed` of its compilable that follows it in the log."""
    out: dict[str, dict[int, list[Any]]] = {}
    for record in records:
        if record.kind != trace.PERF_WARN:
            continue
        keys = lifecycle["label_index"].get(record.fields["label"], [])
        if len(keys) != 1:
            continue
        outcome = next(
            (
                e
                for e in lifecycle["roots"][keys[0]]["events"]
                if e["kind"] in (trace.OPT_DONE, trace.OPT_FAILED) and e["seq"] > record.seq
            ),
            None,
        )
        if outcome is not None:
            out.setdefault(keys[0], {}).setdefault(outcome["seq"], []).append(record)
    return out


def perf_warn_view(warnings: list[Any]) -> dict[str, Any]:
    nodes = [
        {"kind": "invoke", "target": w.fields.get("target") or w.fields["message"], "frames": w.fields.get("frames", []), "count": 1}
        for w in warnings
    ]
    return {
        "graph_name": "perf warn (post partial evaluation)",
        "complete": False,
        "node_source_positions": all(node["frames"] for node in nodes) if nodes else False,
        "nodes": nodes,
    }


def partial_pe_views(
    rows: list[dict[str, Any]], records: list[Any], lifecycle: dict[str, Any], final_tier: int
) -> dict[str, dict[str, Any]]:
    """run-local key -> partial pe view, from the `perf warn` records printed for the compilation
    that produced each required root's last final-tier code. Roots without such warnings get no
    entry, which the classifier reads as 'no pe view', never as 'no survivors'."""
    attributed = attribute_perf_warnings(records, lifecycle)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        run_local = row.get("run_local_key")
        key = run_local.get("key") if isinstance(run_local, dict) else None
        if key is None:
            continue
        done = [e for e in row["events"] if e["kind"] == trace.OPT_DONE and e["tier"] == final_tier]
        if not done:
            continue
        warnings = attributed.get(key, {}).get(done[-1]["seq"], [])
        if warnings:
            out[key] = perf_warn_view(warnings)
    return out


# --- shape facts ---------------------------------------------------------------------------------


def validate_shape_facts(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or doc.get("schema") != FACTS_SCHEMA:
        raise RuntimeError("SHAPE_FACTS_SCHEMA_MISMATCH")
    if not isinstance(doc.get("durable_id"), str) or not isinstance(doc.get("comp_id"), int):
        raise RuntimeError("SHAPE_FACTS_IDENTITY_MISSING: durable_id and comp_id are required")
    views = doc.get("views")
    if not isinstance(views, dict) or not set(views) <= set(VIEWS):
        raise RuntimeError("SHAPE_FACTS_VIEWS_INVALID")
    for name, view in views.items():
        for key in ("graph_name", "complete", "node_source_positions", "nodes"):
            if key not in view:
                raise RuntimeError(f"SHAPE_FACTS_VIEW_INCOMPLETE: {name} lacks {key}")
        for node in view["nodes"]:
            if node.get("kind") not in NODE_KINDS or not isinstance(node.get("count"), int) or node["count"] < 1:
                raise RuntimeError(f"SHAPE_FACTS_NODE_INVALID: {node!r}")
            if not isinstance(node.get("frames", []), list):
                raise RuntimeError(f"SHAPE_FACTS_NODE_INVALID: frames {node!r}")
    return doc


def _texts(node: dict[str, Any]) -> list[str]:
    return [str(node.get(key, "")) for key in ("class", "target", "field")] + [str(f) for f in node.get("frames", [])]


def view_matches(view: dict[str, Any] | None, markers: list[str]) -> dict[str, Any]:
    nodes = [] if view is None else view["nodes"]
    hits = [n for n in nodes if any(marker in text for text in _texts(n) for marker in markers)]
    return {
        "count": sum(n["count"] for n in hits),
        "sites": [{"kind": n["kind"], "class": n.get("class"), "target": n.get("target"), "frames": n.get("frames", [])[:8], "count": n["count"]} for n in hits[:20]],
    }


def survival(view: dict[str, Any] | None, markers: list[str], *, min_count: int) -> tuple[str, dict[str, Any], str | None]:
    """(YES|NO|INCONCLUSIVE, matches, limit). NO only from a complete view with source positions."""
    if view is None:
        return "INCONCLUSIVE", view_matches(None, markers), "VIEW_UNAVAILABLE"
    matches = view_matches(view, markers)
    if matches["count"] >= min_count:
        return "YES", matches, None
    if not view["complete"]:
        return "INCONCLUSIVE", matches, "VIEW_INCOMPLETE"
    if not view["node_source_positions"]:
        return "INCONCLUSIVE", matches, "NO_NODE_SOURCE_POSITIONS"
    return "NO", matches, None


def classify_member_families(
    views: dict[str, dict[str, Any] | None], families: list[dict[str, Any]], other_family: dict[str, Any], *, min_count: int
) -> dict[str, Any]:
    """Per-family result for one stably compiled root from its pe/late views."""
    results: dict[str, Any] = {}
    claimed: list[str] = []
    for family in families:
        pe, pe_matches, pe_limit = survival(views.get("pe"), family["markers"], min_count=min_count)
        late, late_matches, late_limit = survival(views.get("late"), family["markers"], min_count=min_count)
        claimed += family["markers"]
        results[family["id"]] = {
            "SURVIVES_AFTER_PARTIAL_EVALUATION": pe,
            "SURVIVES_OPTIMIZED_GRAPH": late,
            "removed_after_partial_evaluation": True if (pe == "YES" and late == "NO") else None,
            "pe": pe_matches,
            "late": late_matches,
            "evidence_limits": sorted({limit for limit in (pe_limit, late_limit) if limit}),
        }
    other_results: dict[str, Any] = {}
    for name in VIEWS:
        view = views.get(name)
        if view is None:
            other_results[name] = ("INCONCLUSIVE", {"count": 0, "sites": []}, "VIEW_UNAVAILABLE")
            continue
        leftovers = [
            n
            for n in view["nodes"]
            if n["kind"] in ("allocation", "invoke")
            and any("com.guillermomolina.protos" in text for text in _texts(n))
            and not any(marker in text for text in _texts(n) for marker in claimed)
        ]
        matches = {"count": sum(n["count"] for n in leftovers), "sites": view_matches({"nodes": leftovers}, [""])["sites"]}
        if matches["count"] >= min_count:
            other_results[name] = ("YES", matches, None)
        elif not view["complete"]:
            other_results[name] = ("INCONCLUSIVE", matches, "VIEW_INCOMPLETE")
        elif not view["node_source_positions"]:
            other_results[name] = ("INCONCLUSIVE", matches, "NO_NODE_SOURCE_POSITIONS")
        else:
            other_results[name] = ("NO", matches, None)
    results[other_family["id"]] = {
        "SURVIVES_AFTER_PARTIAL_EVALUATION": other_results["pe"][0],
        "SURVIVES_OPTIMIZED_GRAPH": other_results["late"][0],
        "removed_after_partial_evaluation": True if (other_results["pe"][0] == "YES" and other_results["late"][0] == "NO") else None,
        "pe": other_results["pe"][1],
        "late": other_results["late"][1],
        "evidence_limits": sorted({r[2] for r in other_results.values() if r[2]}),
    }
    return results


def roll_up_family(results: list[dict[str, Any]], field: str) -> str:
    """Unit-level value over the stably compiled members: YES if any, NO if all and at least one,
    otherwise INCONCLUSIVE."""
    values = [r[field] for r in results]
    if any(v == "YES" for v in values):
        return "YES"
    if values and all(v == "NO" for v in values):
        return "NO"
    return "INCONCLUSIVE"


def final_tier_comp_id(events: list[dict[str, Any]], final_tier: int) -> int | None:
    done = [e for e in events if e["kind"] == trace.OPT_DONE and e["tier"] == final_tier and e["comp_id"] is not None]
    return done[-1]["comp_id"] if done else None


def classify_shape(
    rows: list[dict[str, Any]],
    facts_by_durable_id: dict[str, dict[str, Any]],
    partial_pe_by_key: dict[str, dict[str, Any]],
    *,
    families: list[dict[str, Any]],
    other_family: dict[str, Any],
    final_tier: int,
    min_count: int,
) -> dict[str, Any]:
    """Compiled-shape result for one unit. Members that did not stably compile are not classified
    (all families INCONCLUSIVE, limit ROOT_NOT_STABLY_COMPILED); facts recorded for another
    compilation than the member's last final-tier one are refused."""
    per_member: list[dict[str, Any]] = []
    applicable: list[dict[str, Any]] = []
    for row in rows:
        entry: dict[str, Any] = {"durable_id": row["durable_id"], "role_id": row["role_id"], "kind": row["kind"], "families": None, "limits": []}
        comp_id = final_tier_comp_id(row["events"], final_tier)
        if row["STABLE_FINAL_OPTIMIZED_STATE"] != "YES" or comp_id is None:
            entry["limits"].append("ROOT_NOT_STABLY_COMPILED")
            per_member.append(entry)
            continue
        views: dict[str, dict[str, Any] | None] = {"pe": None, "late": None}
        facts = facts_by_durable_id.get(row["durable_id"])
        if facts is not None:
            if facts["comp_id"] != comp_id:
                entry["limits"].append(f"FACTS_FOR_DIFFERENT_COMPILATION facts={facts['comp_id']} final_tier={comp_id}")
            else:
                for name in VIEWS:
                    views[name] = facts["views"].get(name)
        key = (row.get("run_local_key") or {}).get("key") if isinstance(row.get("run_local_key"), dict) else None
        if views["pe"] is None and key in partial_pe_by_key:
            views["pe"] = partial_pe_by_key[key]
        entry["families"] = classify_member_families(views, families, other_family, min_count=min_count)
        entry["comp_id"] = comp_id
        applicable.append(entry)
        per_member.append(entry)

    rollup: dict[str, Any] = {}
    for family in [*families, other_family]:
        fam_results = [m["families"][family["id"]] for m in applicable]
        rollup[family["id"]] = {
            "description": family["description"],
            "SURVIVES_AFTER_PARTIAL_EVALUATION": roll_up_family(fam_results, "SURVIVES_AFTER_PARTIAL_EVALUATION"),
            "SURVIVES_OPTIMIZED_GRAPH": roll_up_family(fam_results, "SURVIVES_OPTIMIZED_GRAPH"),
        }
    return {"schema": "perf010a-compiled-shape-v1", "members": per_member, "families": rollup, "applicable_members": len(applicable)}
