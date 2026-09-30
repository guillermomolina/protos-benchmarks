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

"""Objective per-compilable lifecycle normalization from ordered compiler-trace records.

Input is the ordered record list of runner/compiler_trace.py; output is a JSON-serializable dict
that keeps every lifecycle event in raw order and derives, per compilable, the result schema

    OPTIMIZATION_STATE                 OPT_DONE | OPT_FAILED | NOT_TRIGGERED | INCONCLUSIVE
    TIER_REACHED                       observed tiers with a successful compilation
    FAILURE_OR_BAILOUT                 exact failure text | NONE
    INVALIDATION_OR_RECOMPILATION      PRESENT | ABSENT | INCONCLUSIVE
    STABLE_FINAL_OPTIMIZED_STATE       YES | NO | INCONCLUSIVE

plus the nine lifecycle classes that must be told apart objectively: never compiled, compiled only
first tier, compiled final tier, permanent bailout, temporary failure/retry, compiled then
invalidated, compiled then recompiled successfully, compiled then replaced by a generic
specialization, and stable optimized state.

Design rules:

* Numeric compiler ids and `Name@hash` labels are run-local correlation keys only; nothing here
  treats them as durable identity.
* Silence is never a pass: STABLE=YES needs a final-tier success, no later failure, invalidation or
  recompilation attempt, no unresolved queued/started task, no parse anomaly for the compilable and a
  run whose completion is proven (process completed and the driver's phase markers all seen in
  order). Missing proof gives INCONCLUSIVE, and unknown or unparseable `opt` records are anomalies
  that poison the affected claims instead of being ignored.
* A 10,000-deep recursion deoptimizes every stacked compiled frame one by one, so thousands of
  `opt deopt ... Invalidated true` records belong to one invalidation. Invalidations are therefore
  modelled as episodes (first invalidating record after a compilation until the next successful
  compilation); the individual frame deoptimizations are counted inside the episode, not dropped.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
from typing import Any


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

SCHEMA = "perf010a-lifecycle-v1"
OPTIMIZATION_STATES = ("OPT_DONE", "OPT_FAILED", "NOT_TRIGGERED", "INCONCLUSIVE")
LIFECYCLE_CLASS_KEYS = (
    "never_compiled",
    "first_tier_only",
    "final_tier_done",
    "permanent_bailout",
    "temporary_failure_retry",
    "compiled_then_invalidated",
    "compiled_then_recompiled",
    "compiled_then_replaced_by_generic_specialization",
    "stable_final_state",
)
DEFAULT_REPLACEMENT_PATTERNS = (
    r"(?i)node\s+replac",
    r"(?i)replaced\b.*\bgeneric",
    r"(?i)specializ",
    r"(?i)rewrit",
)
# Records that are not positive evidence of instability after the last final-tier compilation: a
# stale-task dequeue only removes work, and an unknown/unparseable record is an anomaly that poisons
# the affected claims (INCONCLUSIVE) instead of counting as evidence either way.
SILENT_ACTIVITY_KINDS = frozenset({trace.OPT_DEQUEUED, trace.OPT_UNKNOWN, trace.OPT_UNPARSED})
LATER_ACTIVITY_SAMPLE = 20


def classify_invalidation_reason(reason: str | None, patterns: tuple[str, ...] | list[str]) -> str:
    """GENERIC_REPLACEMENT, UNCOMMON_TRAP or OTHER. Unrecognised reasons stay OTHER with their raw
    text retained; they are never silently mapped to a benign category."""
    text = reason or ""
    for pattern in patterns:
        if re.search(pattern, text):
            return "GENERIC_REPLACEMENT"
    if re.search(r"(?i)uncommon trap", text):
        return "UNCOMMON_TRAP"
    return "OTHER"


def _event(record: Any, phase: str) -> dict[str, Any]:
    f = record.fields
    return {
        "seq": record.seq,
        "line": record.line,
        "kind": record.kind,
        "phase": phase,
        "tier": f.get("tier"),
        "comp_id": f.get("comp_id"),
        "invalidated": f.get("invalidated"),
        "reason": f.get("reason"),
    }


def _new_work() -> dict[str, Any]:
    return {
        "queued": 0,
        "started": 0,
        "done": [],
        "failed": [],
        "episodes": [],
        "open_episode": None,
        "frame_deopts_without_invalidation": 0,
        "anomaly_kinds": [],
    }


def normalize_lifecycle(
    records: list[Any],
    *,
    first_tier: int,
    final_tier: int,
    replacement_patterns: tuple[str, ...] | list[str] = DEFAULT_REPLACEMENT_PATTERNS,
    required_phases: tuple[str, ...] | list[str] = (),
    process_completed: bool = False,
) -> dict[str, Any]:
    roots: dict[str, dict[str, Any]] = {}
    work: dict[str, dict[str, Any]] = {}
    label_index: dict[str, list[str]] = {}
    anomalies: list[dict[str, Any]] = []
    assumption_records: list[dict[str, Any]] = []
    phase = "unmarked"
    phase_sequence: list[str] = []

    def anomaly(kind: str, record: Any, detail: str, key: str | None = None) -> None:
        anomalies.append(
            {"kind": kind, "seq": record.seq, "line": record.line, "detail": detail, "key": key}
        )
        if key is not None and key in work:
            work[key]["anomaly_kinds"].append(kind)

    def root_key(record: Any) -> str | None:
        f = record.fields
        if f.get("id") is None:
            return None
        key = f"{f['engine']}:{f['id']}"
        if key not in roots:
            roots[key] = {"key": key, "engine": f["engine"], "id": f["id"], "label": f["label"], "events": []}
            work[key] = _new_work()
            label_index.setdefault(f["label"], []).append(key)
        elif roots[key]["label"] != f["label"]:
            anomaly("ID_LABEL_CONFLICT", record, f"{roots[key]['label']} vs {f['label']}", key)
        return key

    for record in records:
        kind = record.kind
        if kind == trace.MARK:
            phase = record.fields["phase"]
            phase_sequence.append(phase)
            continue
        if kind == trace.ENGINE_OTHER and re.search(r"(?i)assumption", record.header):
            assumption_records.append(
                {"seq": record.seq, "line": record.line, "phase": phase, "text": record.raw[:600]}
            )
            continue
        if kind not in trace.LIFECYCLE_KINDS:
            continue

        key = root_key(record)
        if kind == trace.OPT_FAIL_DETAIL and key is None:
            label = record.fields.get("label")
            candidates = [
                k
                for k in label_index.get(label, [])
                if any(item["detail_seq"] is None for item in work[k]["failed"])
            ]
            if len(candidates) != 1:
                anomaly("UNMATCHED_FAIL_DETAIL", record, f"label={label} candidates={candidates}")
                continue
            key = candidates[0]
        if key is None:
            unknown = kind in (trace.OPT_UNKNOWN, trace.OPT_UNPARSED)
            anomaly(
                "UNKNOWN_LIFECYCLE_RECORD" if unknown else "UNATTRIBUTED_LIFECYCLE_RECORD",
                record,
                record.header[:200],
            )
            continue

        state = work[key]
        event = _event(record, phase)
        roots[key]["events"].append(event)
        index = len(roots[key]["events"]) - 1

        if kind == trace.OPT_QUEUED:
            state["queued"] += 1
        elif kind == trace.OPT_START:
            if state["queued"] > 0:
                state["queued"] -= 1
            state["started"] += 1
        elif kind == trace.OPT_DEQUEUED:
            if state["queued"] > 0:
                state["queued"] -= 1
            else:
                anomaly("DEQUEUE_WITHOUT_QUEUE", record, "opt unque. without a pending queued task", key)
        elif kind in (trace.OPT_DONE, trace.OPT_FAILED):
            if state["started"] > 0:
                state["started"] -= 1
            else:
                anomaly("COMPLETION_WITHOUT_START", record, record.header[:200], key)
            if kind == trace.OPT_DONE:
                state["done"].append({"index": index, "tier": event["tier"], "comp_id": event["comp_id"]})
                episode = state["open_episode"]
                if episode is not None:
                    episode["recovered_by_seq"] = record.seq
                    state["open_episode"] = None
            else:
                state["failed"].append(
                    {
                        "index": index,
                        "tier": event["tier"],
                        "raw": record.raw,
                        "detail_seq": None,
                        "detail_raw": "",
                        "kind": trace.classify_failure(record.raw),
                    }
                )
        elif kind == trace.OPT_FAIL_DETAIL:
            pending = [item for item in state["failed"] if item["detail_seq"] is None]
            if not pending:
                anomaly("UNMATCHED_FAIL_DETAIL", record, "opt fail detail without a failed record", key)
            else:
                item = pending[-1]
                item["detail_seq"] = record.seq
                item["detail_raw"] = record.raw
                item["kind"] = trace.classify_failure(item["raw"] + "\n" + record.raw)
        elif kind in (trace.OPT_DEOPT, trace.OPT_INVALIDATED):
            invalidating = event["invalidated"] if kind == trace.OPT_DEOPT else True
            if invalidating is None:
                anomaly("DEOPT_WITHOUT_INVALIDATED_FLAG", record, record.header[:200], key)
            elif invalidating:
                episode = state["open_episode"]
                if episode is None:
                    episode = {
                        "start_seq": record.seq,
                        "start_line": record.line,
                        "after_done": bool(state["done"]),
                        "reason": event["reason"],
                        "category": classify_invalidation_reason(event["reason"], replacement_patterns),
                        "frame_deopts": 0,
                        "recovered_by_seq": None,
                    }
                    state["episodes"].append(episode)
                    state["open_episode"] = episode
                episode["frame_deopts"] += 1
            else:
                state["frame_deopts_without_invalidation"] += 1
        else:  # OPT_UNKNOWN / OPT_UNPARSED with an id
            anomaly("UNKNOWN_LIFECYCLE_RECORD", record, record.header[:200], key)

    reasons: list[str] = []
    if not process_completed:
        reasons.append("process_not_completed")
    if list(phase_sequence) != list(required_phases):
        reasons.append(
            f"phase_markers_missing_or_out_of_order observed={phase_sequence} required={list(required_phases)}"
        )
    run_complete = not reasons
    global_anomalies = [a for a in anomalies if a["key"] is None]

    for key, root in roots.items():
        _finish_root(
            root,
            work[key],
            first_tier=first_tier,
            final_tier=final_tier,
            run_complete=run_complete,
            has_global_anomaly=bool(global_anomalies),
        )
        label = root["label"]
        root["assumption_record_seqs"] = [
            item["seq"] for item in assumption_records if label in item["text"]
        ]

    return {
        "schema": SCHEMA,
        "tier_model": {"first_tier": first_tier, "final_tier": final_tier},
        "run": {
            "process_completed": bool(process_completed),
            "phase_sequence": phase_sequence,
            "phase_boundaries_objective": list(phase_sequence) == list(required_phases),
            "complete": run_complete,
            "incomplete_reasons": reasons,
        },
        "anomalies": anomalies,
        "roots": roots,
        "label_index": label_index,
        "assumption_records": assumption_records,
        "events_total": sum(len(root["events"]) for root in roots.values()),
    }


def _finish_root(
    root: dict[str, Any],
    state: dict[str, Any],
    *,
    first_tier: int,
    final_tier: int,
    run_complete: bool,
    has_global_anomaly: bool,
) -> None:
    events = root["events"]
    done = state["done"]
    failed = state["failed"]
    episodes = state["episodes"]
    tiers = sorted({item["tier"] for item in done if item["tier"] is not None})
    final_done = [item for item in done if item["tier"] == final_tier]
    unresolved = state["queued"] > 0 or state["started"] > 0
    poisoned = bool(state["anomaly_kinds"]) or has_global_anomaly

    outcomes = [e for e in events if e["kind"] in (trace.OPT_DONE, trace.OPT_FAILED)]
    last_outcome = outcomes[-1] if outcomes else None
    last_failed = failed[-1] if failed else None
    unrecovered_failure = last_outcome is not None and last_outcome["kind"] == trace.OPT_FAILED

    if poisoned:
        optimization_state = "INCONCLUSIVE"
    elif last_outcome is None:
        optimization_state = "NOT_TRIGGERED" if (run_complete and not unresolved) else "INCONCLUSIVE"
    elif unrecovered_failure:
        optimization_state = "OPT_FAILED"
    else:
        optimization_state = "OPT_DONE"

    repeated_same_tier = len(done) != len({item["tier"] for item in done})
    post_done_episodes = [ep for ep in episodes if ep["after_done"]]
    recovered_episodes = [ep for ep in post_done_episodes if ep["recovered_by_seq"] is not None]
    if post_done_episodes or repeated_same_tier:
        invalidation = "PRESENT"
    elif poisoned or not run_complete or unresolved:
        invalidation = "INCONCLUSIVE"
    else:
        invalidation = "ABSENT"

    later_activity: list[dict[str, Any]] = []
    if final_done:
        for event in events[final_done[-1]["index"] + 1 :]:
            if event["kind"] in SILENT_ACTIVITY_KINDS or event["kind"] == trace.OPT_FAIL_DETAIL:
                continue
            if event["kind"] == trace.OPT_DEOPT and event["invalidated"] is not True:
                continue
            later_activity.append(event)
    if not final_done:
        stable = "INCONCLUSIVE" if (poisoned or not run_complete or unresolved) else "NO"
    elif later_activity:
        stable = "NO"
    elif poisoned or not run_complete or unresolved:
        stable = "INCONCLUSIVE"
    else:
        stable = "YES"

    recovered_failure = any(
        item["kind"] != "PERMANENT" and any(d["index"] > item["index"] for d in done) for item in failed
    )
    classes = {
        "never_compiled": not done,
        "first_tier_only": bool(done) and set(tiers) == {first_tier},
        "final_tier_done": bool(final_done),
        "permanent_bailout": unrecovered_failure and last_failed is not None and last_failed["kind"] == "PERMANENT",
        "temporary_failure_retry": recovered_failure,
        "compiled_then_invalidated": bool(post_done_episodes),
        "compiled_then_recompiled": bool(recovered_episodes) or repeated_same_tier,
        "compiled_then_replaced_by_generic_specialization": any(
            ep["category"] == "GENERIC_REPLACEMENT" for ep in post_done_episodes
        ),
        "stable_final_state": stable == "YES",
    }

    by_phase: dict[str, dict[str, int]] = {}
    for event in events:
        bucket = by_phase.setdefault(event["phase"], {})
        bucket[event["kind"]] = bucket.get(event["kind"], 0) + 1

    root.update(
        {
            "OPTIMIZATION_STATE": optimization_state,
            "TIER_REACHED": ",".join(str(t) for t in tiers) if tiers else "NONE",
            "FAILURE_OR_BAILOUT": (last_failed["raw"] + ("\n" + last_failed["detail_raw"] if last_failed["detail_raw"] else "")) if last_failed else "NONE",
            "failure_kind": last_failed["kind"] if last_failed else None,
            "failure_recovered": bool(last_failed) and not unrecovered_failure,
            "INVALIDATION_OR_RECOMPILATION": invalidation,
            "STABLE_FINAL_OPTIMIZED_STATE": stable,
            "classes": classes,
            "invalidation_episodes": episodes,
            "frame_deopts_without_invalidation": state["frame_deopts_without_invalidation"],
            "later_activity_after_final_done": later_activity[:LATER_ACTIVITY_SAMPLE],
            "later_activity_count": len(later_activity),
            "pending": {"queued": state["queued"], "started": state["started"]},
            "unresolved": unresolved,
            "anomaly_kinds": sorted(set(state["anomaly_kinds"])),
            "events_by_phase": by_phase,
        }
    )


def summarize_states(lifecycle: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Counts by OPTIMIZATION_STATE and STABLE_FINAL_OPTIMIZED_STATE, for console output only."""
    states: dict[str, int] = {}
    stable: dict[str, int] = {}
    for root in lifecycle["roots"].values():
        states[root["OPTIMIZATION_STATE"]] = states.get(root["OPTIMIZATION_STATE"], 0) + 1
        stable[root["STABLE_FINAL_OPTIMIZED_STATE"]] = stable.get(root["STABLE_FINAL_OPTIMIZED_STATE"], 0) + 1
    return {"optimization_state": states, "stable_final_optimized_state": stable}
