#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Generic Truffle compiled-graph structural evidence (pure, no I/O).

Everything here maps retained raw evidence to derived structure, so every
derived number is reproducible from the retained raw trace log and BGV-derived
JSON alone:

    TraceCompilation + TraceInlining + TraceNodeExpansion text
      -> per-CallTarget compilation lifecycle (superseded / final / invalidated)
      -> relevant language-owned compilation units of one steady
         ``Value.execute()`` operation (framework entry -> primary guest unit
         -> separately compiled callees that remain calls)
      -> trace-side stabilization signature per natural-warmup budget
    IgvUtility ``filter`` JSON of each selected unit's BGV
      -> exactly one selected-phase graph (``After TruffleTier``)
      -> exact node count, node-class histogram and structural families
    per-language unit summaries
      -> cross-language rung comparison (peer reference, Protos status)

Nothing is language specific except data supplied by the caller (framework
label patterns, primary-label pattern). A new Truffle language needs a policy
entry, not new parsing code. Missing, ambiguous or unexpected evidence raises
``EvidenceError``; nothing is guessed.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

import compiler_trace as trace

COMPILATION_TIME_RE = re.compile(
    r"\|Time\s+(?P<total>\d+)\(\s*(?P<truffle>\d+)\s*\+\s*(?P<graal>\d+)\s*\)ms"
)
CODE_SIZE_RE = re.compile(r"\|CodeSize\s+(?P<bytes>\d+)")
AST_NODES_RE = re.compile(r"\|AST\s+(?P<count>\d+)")
INLINE_COUNTS_RE = re.compile(
    r"\|Inlined\s+(?P<yes>\d+)Y\s+(?P<no>\d+)N"
)

EXPANSION_COLUMNS = ("count", "size", "cycles", "ifs", "loops", "invokes", "allocs")
EXPANSION_RE = re.compile(
    r"^\[engine\] Expansion tree for (?P<label>.+?) after (?P<tier>\w+):\s*$"
)
IR_RE = re.compile(r"\|IR\s+(?P<after>\d+)/\s*(?P<final>\d+)")
DUMP_NAME_RE = re.compile(r"^TruffleHotSpotCompilation-(?P<comp_id>\d+)\[.*\]\.bgv$")
PHASE_PREFIX_RE = re.compile(r"^\s*\d+\s*:\s*")
LABEL_IDENTITY_RE = re.compile(r"(?<=@)[0-9a-f]+\b|(?<= at )[0-9a-f]+(?=>)")

STABLE_CANDIDATE = "STABLE_CANDIDATE"
NOT_STABLE = "NOT_STABLE"
STABLE = "STABLE"
GRAPH_NOT_STABLE = "GRAPH_NOT_STABLE"

PEER_CONVERGED = "CONVERGED"
PEER_UNRESOLVED = "UNRESOLVED"
STRUCTURALLY_CONVERGED = "STRUCTURALLY_CONVERGED"
STRUCTURAL_EXCESS = "STRUCTURAL_EXCESS"
NOT_EVALUATED = "NOT_EVALUATED"
DIVERGED_BEFORE_GRAPH_PARITY = "DIVERGED_BEFORE_GRAPH_PARITY"
COMPARISON_PERFORMED = "PERFORMED"
COMPARISON_SKIPPED = "SKIPPED"
MAX_COMPILATIONS_RE = re.compile(r"Maximum compilation count \d+ reached")

# Structural families derived from the node-class histogram. Qualitative peer
# agreement is judged on graph topology plus the presence of these families.
FAMILIES = (
    "invokes",
    "control_flow_splits",
    "allocations",
    "guards_deopts",
    "loads",
    "loops",
)
QUALITATIVE_FAMILIES = ("invokes", "allocations", "loops")


class EvidenceError(Exception):
    def __init__(self, reason: str, detail: object = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail != "" else reason)
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------------------
# Trace parsing


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def parse_expansion(record: Any) -> dict[str, Any] | None:
    """One ``Expansion tree for <label> after <tier>:`` table.

    Each row is ``<indent><name> <frequency> | <7 totals> | <7 self> | <ids>
    <Lang:File:Line:Chars>``; the ``<call-root>`` row holds graph totals.
    """
    match = EXPANSION_RE.match(record.header)

    if match is None:
        return None

    rows = []

    for line in record.lines[1:]:
        parts = line.split("|")

        if len(parts) < 3:
            continue

        head = parts[0].rstrip()
        stripped = head.lstrip()

        if not stripped or stripped.startswith("Name"):
            continue

        total = [_int(x) for x in parts[1].split()]
        own = [_int(x) for x in parts[2].split()]

        if len(total) != 7 or len(own) != 7 or None in total or None in own:
            continue

        name_frequency = stripped.rsplit(None, 1)
        tail = parts[3].split() if len(parts) > 3 else []
        rows.append(
            {
                "depth": len(head) - len(stripped),
                "name": name_frequency[0] if len(name_frequency) == 2 else stripped,
                "total": dict(zip(EXPANSION_COLUMNS, total)),
                "self": dict(zip(EXPANSION_COLUMNS, own)),
                "location": tail[-1] if tail and ":" in tail[-1] else None,
            }
        )

    root = next((row for row in rows if row["name"] == "<call-root>"), None)

    return {
        "label": match.group("label").strip(),
        "tier_name": match.group("tier"),
        "root": root["total"] if root else None,
        "rows": rows,
    }


def _target_key(fields: dict[str, Any]) -> str:
    if fields.get("id") is not None:
        return f"{fields.get('engine')}:{fields['id']}"
    return "label:" + str(fields.get("label", "")).strip()


def _inline_tree(entries: list[dict[str, Any]], label: str) -> list[dict[str, Any]] | None:
    """Decisions between the last ``Inline start <label>`` and its
    ``Inline done``; None when inlining was not traced for this compilation."""
    start = None

    for index, entry in enumerate(entries):
        if entry["verb"] == "Inline start" and entry["label"] == label:
            start = index

    if start is None:
        return None

    tree = []

    for entry in entries[start + 1 :]:
        if entry["verb"] == "Inline done" and entry["label"] == label:
            return tree
        if entry["verb"] not in ("Inline start", "Inline done"):
            tree.append(
                {"verb": entry["verb"], "label": entry["label"], "depth": entry["depth"]}
            )

    raise EvidenceError("INLINING_TRACE_UNTERMINATED", label)


def compilation_metrics(header: str) -> dict[str, int | None]:
    """Keep AST, Graal IR, compilation time and machine code distinct."""
    timing = COMPILATION_TIME_RE.search(header)
    code = CODE_SIZE_RE.search(header)
    ast = AST_NODES_RE.search(header)
    inline = INLINE_COUNTS_RE.search(header)

    return {
        "compilation_time_ms": (
            int(timing.group("total")) if timing else None
        ),
        "truffle_compilation_ms": (
            int(timing.group("truffle")) if timing else None
        ),
        "graal_compilation_ms": (
            int(timing.group("graal")) if timing else None
        ),
        "machine_code_bytes": (
            int(code.group("bytes")) if code else None
        ),
        "ast_nodes": (
            int(ast.group("count")) if ast else None
        ),
        "inlined_yes": (
            int(inline.group("yes")) if inline else None
        ),
        "inlined_no": (
            int(inline.group("no")) if inline else None
        ),
    }


def parse_trace(text: str) -> dict[str, Any]:
    """Ordered compilation lifecycle of one single-threaded
    (``BackgroundCompilation=false``) traced run.

    Inlining decisions and the expansion table printed before an ``opt done``
    belong to that compilation.
    """
    records = trace.split_records(text)
    compilations: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    invalidations: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    pending_inline: list[dict[str, Any]] = []
    pending_expansion: list[dict[str, Any]] = []

    for record in records:
        kind = record.kind
        fields = record.fields

        if kind in (trace.INLINE_START, trace.INLINE_DONE, trace.INLINE_DECISION):
            pending_inline.append(
                {
                    "verb": fields["verb"],
                    "label": fields["label"].strip(),
                    "depth": _int(fields["values"].get("Depth")),
                }
            )
        elif kind == trace.ENGINE_OTHER and EXPANSION_RE.match(record.header):
            pending_expansion.append(parse_expansion(record))
        elif kind == trace.OPT_DONE:
            label = fields["label"].strip()
            ir = IR_RE.search(record.header)
            compilations.append(
                {
                    "seq": record.seq,
                    "line": record.line,
                    "target": _target_key(fields),
                    "label": label,
                    "tier": fields["tier"],
                    "comp_id": fields["comp_id"],
                    "src": fields.get("src"),
                    "ir_after_truffle_tier": int(ir.group("after")) if ir else None,
                    "ir_final": int(ir.group("final")) if ir else None,
                    **compilation_metrics(record.header),
                    "inline_tree": _inline_tree(pending_inline, label),
                    "expansion": next(
                        (e for e in reversed(pending_expansion) if e["label"] == label),
                        None,
                    ),
                }
            )
            pending_inline = []
            pending_expansion = []
        elif kind == trace.OPT_FAILED:
            failures.append(
                {
                    "seq": record.seq,
                    "line": record.line,
                    "target": _target_key(fields),
                    "label": fields["label"].strip(),
                    "tier": fields["tier"],
                    "reason": fields.get("reason"),
                    "classification": trace.classify_failure(record.raw),
                }
            )
            pending_inline = []
            pending_expansion = []
        elif kind == trace.OPT_INVALIDATED or (
            kind == trace.OPT_DEOPT and fields.get("invalidated") is True
        ):
            invalidations.append(
                {
                    "seq": record.seq,
                    "line": record.line,
                    "target": _target_key(fields),
                    "label": fields["label"].strip(),
                    "reason": fields.get("reason"),
                }
            )
        elif kind in (trace.OPT_UNKNOWN, trace.OPT_UNPARSED):
            unknown.append({"line": record.line, "header": record.header})

    return {
        "compilations": compilations,
        "failures": failures,
        "invalidations": invalidations,
        "unknown_lifecycle_events": unknown,
        "option_rejections": trace.find_option_rejections(text),
    }


def target_lifecycles(parsed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per CallTarget: every successful compilation in order, the final one,
    the superseded ones and whether the final one was later invalidated or
    followed by a failed recompilation."""
    targets: dict[str, dict[str, Any]] = {}

    for compilation in parsed["compilations"]:
        entry = targets.setdefault(
            compilation["target"],
            {"target": compilation["target"], "label": compilation["label"], "compilations": []},
        )
        entry["compilations"].append(compilation)

    for key, entry in targets.items():
        final = entry["compilations"][-1]
        entry["final"] = final
        entry["superseded_comp_ids"] = [c["comp_id"] for c in entry["compilations"][:-1]]
        entry["invalidated_after_final"] = any(
            item["target"] == key and item["seq"] > final["seq"]
            for item in parsed["invalidations"]
        )
        entry["failed_after_final"] = any(
            item["target"] == key and item["seq"] > final["seq"]
            for item in parsed["failures"]
        )

    return targets


def select_tier_compilation(
    parsed: dict[str, Any],
    requested_tier: int,
    root: str,
    resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Require exactly one observed compilation of the requested root/tier."""
    if requested_tier not in (1, 2):
        raise EvidenceError("INVALID_REQUESTED_TIER")

    if parsed.get("option_rejections"):
        raise EvidenceError("OPTION_REJECTED")

    if parsed.get("unknown_lifecycle_events"):
        raise EvidenceError("UNKNOWN_LIFECYCLE_EVENT")

    targets = target_lifecycles(parsed)

    if root == "primary":
        if resolution is None:
            raise EvidenceError("PRIMARY_RESOLUTION_REQUIRED")
        candidates = [
            unit["target"]
            for unit in resolution["units"]
            if unit["role"] == "primary"
        ]
    else:
        candidates = [
            key for key, item in targets.items()
            if item["label"] == root
            or normalize_label(item["label"]) == root
        ]

    if not candidates:
        raise EvidenceError("ROOT_NOT_COMPILED", root)
    if len(candidates) != 1:
        raise EvidenceError("ROOT_AMBIGUOUS", root)

    target = targets[candidates[0]]
    observed = [
        item for item in target["compilations"]
        if item["tier"] == requested_tier
    ]

    if not observed:
        raise EvidenceError(
            "REQUESTED_TIER_NOT_OBSERVED",
            f"{root}: Tier {requested_tier}",
        )

    if len(observed) != 1:
        raise EvidenceError(
            "TIER_COMPILATION_AMBIGUOUS",
            [item["comp_id"] for item in observed],
        )

    item = observed[0]
    required = (
        "comp_id",
        "compilation_time_ms",
        "ir_after_truffle_tier",
        "ir_final",
        "machine_code_bytes",
    )

    missing = [
        key for key in required
        if item.get(key) is None
    ]

    if missing:
        raise EvidenceError("COMPILATION_METRICS_MISSING", missing)

    if target["invalidated_after_final"]:
        raise EvidenceError(
            "ROOT_INVALIDATED_AFTER_COMPILATION",
            target["label"],
        )

    return {
        **item,
        "root": target["label"],
        "target": target["target"],
        "requested_tier": requested_tier,
        "observed_tier": item["tier"],
        "other_compilation_ids": [
            entry["comp_id"]
            for entry in target["compilations"]
            if entry["comp_id"] != item["comp_id"]
        ],
        "evidence_kind": "single-compilation",
    }



def observed_compilation_roots(
    parsed: dict[str, Any],
    requested_tier: int,
) -> dict[str, Any]:
    """Inventory every observed compiled CallTarget independently.

    Coverage is limited to compilation-trace targets. An interpreted root
    that never compiles cannot be discovered from this trace alone.
    """
    if requested_tier not in (1, 2):
        raise EvidenceError("INVALID_REQUESTED_TIER")

    if parsed.get("option_rejections"):
        raise EvidenceError("OPTION_REJECTED")

    if parsed.get("unknown_lifecycle_events"):
        raise EvidenceError("UNKNOWN_LIFECYCLE_EVENT")

    targets = target_lifecycles(parsed)

    normalized_counts: dict[str, int] = {}

    for target in targets.values():
        label = normalize_label(target["label"])
        normalized_counts[label] = normalized_counts.get(label, 0) + 1

    roots = []

    for target_key, lifecycle in sorted(
        targets.items(),
        key=lambda item: (
            normalize_label(item[1]["label"]),
            item[0],
        ),
    ):
        label = lifecycle["label"]
        normalized = normalize_label(label)

        candidates = [
            compilation
            for compilation in lifecycle["compilations"]
            if compilation["tier"] == requested_tier
        ]

        entry: dict[str, Any] = {
            "target": target_key,
            "label": label,
            "normalized_label": normalized,
            "requested_tier": requested_tier,
            "observed_tiers": sorted({
                compilation["tier"]
                for compilation in lifecycle["compilations"]
            }),
            "compilation_ids": [
                compilation["comp_id"]
                for compilation in lifecycle["compilations"]
            ],
            "cross_run_identity": (
                "AMBIGUOUS"
                if normalized_counts[normalized] > 1
                else "UNIQUE"
            ),
            "status": "UNAVAILABLE",
            "reason": None,
            "selected": None,
        }

        if not candidates:
            entry["reason"] = "REQUESTED_TIER_NOT_OBSERVED"

        elif len(candidates) != 1:
            entry["reason"] = "TIER_COMPILATION_AMBIGUOUS"

        elif lifecycle["invalidated_after_final"]:
            entry["reason"] = "ROOT_INVALIDATED_AFTER_COMPILATION"

        elif lifecycle["failed_after_final"]:
            entry["reason"] = "ROOT_FAILED_AFTER_COMPILATION"

        else:
            compilation = candidates[0]

            required = (
                "comp_id",
                "compilation_time_ms",
                "ir_after_truffle_tier",
                "ir_final",
                "machine_code_bytes",
            )

            missing = [
                name
                for name in required
                if compilation.get(name) is None
            ]

            if missing:
                entry["reason"] = "COMPILATION_METRICS_MISSING"
                entry["missing_metrics"] = missing

            else:
                entry["status"] = "AVAILABLE"
                entry["selected"] = {
                    **compilation,
                    "root": label,
                    "target": target_key,
                    "requested_tier": requested_tier,
                    "observed_tier": compilation["tier"],
                    "other_compilation_ids": [
                        item["comp_id"]
                        for item in lifecycle["compilations"]
                        if item["comp_id"] != compilation["comp_id"]
                    ],
                    "evidence_kind": "single-compilation",
                }

        roots.append(entry)

    return {
        "schema": 1,
        "scope": "observed-compiled-call-targets-only",
        "requested_tier": requested_tier,
        "status": (
            "AVAILABLE" if roots else "UNAVAILABLE"
        ),
        "reason": (
            None if roots else "NO_COMPILED_ROOTS_REPORTED"
        ),
        "roots": roots,
        "available": sum(
            item["status"] == "AVAILABLE"
            for item in roots
        ),
        "unavailable": sum(
            item["status"] == "UNAVAILABLE"
            for item in roots
        ),
        "interpreted_roots_coverage": "NOT_ESTABLISHED",
    }



def cold_producer_identity(metadata: dict[str, Any]) -> dict[str, Any]:
    """Identity relevant to cross-tier structural comparability."""
    product = metadata.get("product_before") or {}
    harness = metadata.get("harness") or {}
    java = metadata.get("java") or {}

    return {
        "language": metadata.get("language"),
        "workload": metadata.get("workload"),
        "surface": metadata.get("surface"),
        "expected_result": metadata.get("expected_result"),
        "phase": metadata.get("selected_phase"),
        "product_revision": product.get("revision"),
        "product_source_state_sha256": product.get(
            "source_state_sha256"
        ),
        "product_version": product.get("version"),
        "peer_runtime": metadata.get("peer_runtime"),
        "harness_git_head": harness.get("git_head"),
        "harness_source_sha256": harness.get("source_sha256"),
        "java_runtime_version": java.get("java.runtime.version"),
        "java_vm_version": java.get("java.vm.version"),
    }


def pair_compiled_root_tiers(
    tier1_capture: dict[str, Any] | None,
    tier1_summary: dict[str, Any] | None,
    tier2_capture: dict[str, Any] | None,
    tier2_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Pair only uniquely identified, producer-compatible compiled roots.

    Never interpret a missing tier, BGV or graph analysis as a zero count.
    """
    captures = {
        1: tier1_capture,
        2: tier2_capture,
    }
    summaries = {
        1: tier1_summary,
        2: tier2_summary,
    }

    identities = {
        tier: (
            cold_producer_identity(capture)
            if capture is not None
            else None
        )
        for tier, capture in captures.items()
    }

    compatible = (
        identities[1] is not None
        and identities[2] is not None
        and identities[1] == identities[2]
    )

    indexed: dict[int, dict[str, dict[str, Any]]] = {
        1: {},
        2: {},
    }

    for tier in (1, 2):
        capture = captures[tier] or {}
        summary = summaries[tier] or {}

        def slot(label: str) -> dict[str, Any]:
            normalized = normalize_label(label)
            return indexed[tier].setdefault(
                normalized,
                {
                    "inventory": [],
                    "unavailable": [],
                    "units": [],
                },
            )

        for entry in (
            capture.get("root_inventory") or {}
        ).get("roots", []):
            slot(entry["label"])["inventory"].append(entry)

        for entry in capture.get("unavailable_roots", []):
            slot(entry["label"])["unavailable"].append(entry)

        for unit in summary.get("units", []):
            slot(unit["label"])["units"].append(unit)

    normalized_roots = sorted(
        set(indexed[1]) | set(indexed[2])
    )

    def tier_observation(
        tier: int,
        normalized: str,
    ) -> dict[str, Any]:
        capture = captures[tier]
        summary = summaries[tier]

        if capture is None:
            return {
                "status": "UNAVAILABLE",
                "reason": "CAPTURE_NOT_AVAILABLE",
            }

        if not capture.get("capture_valid"):
            return {
                "status": "UNAVAILABLE",
                "reason": "CAPTURE_INVALID",
                "detail": capture.get("invalid_reason"),
            }

        if capture.get("requested_root") != "all":
            return {
                "status": "UNAVAILABLE",
                "reason": "CAPTURE_NOT_ALL_ROOTS",
            }

        if capture.get("requested_tier") != tier:
            return {
                "status": "UNAVAILABLE",
                "reason": "CAPTURE_TIER_MISMATCH",
            }

        if (
            (capture.get("correctness") or {}).get("result")
            != "PASS"
        ):
            return {
                "status": "UNAVAILABLE",
                "reason": "CORRECTNESS_NOT_VERIFIED",
            }

        items = indexed[tier].get(normalized)

        if items is None:
            return {
                "status": "UNAVAILABLE",
                "reason": "ROOT_NOT_OBSERVED",
            }

        inventory = items["inventory"]
        units = items["units"]
        unavailable = items["unavailable"]

        if (
            len(inventory) > 1
            or len(units) > 1
            or any(
                entry.get("cross_run_identity") == "AMBIGUOUS"
                for entry in inventory
            )
        ):
            return {
                "status": "AMBIGUOUS",
                "reason": "ROOT_IDENTITY_AMBIGUOUS",
                "observed_targets": [
                    entry.get("target")
                    for entry in inventory
                ],
            }

        if unavailable:
            return {
                "status": "UNAVAILABLE",
                "reason": unavailable[0].get(
                    "reason", "ROOT_EVIDENCE_UNAVAILABLE"
                ),
            }

        if inventory and inventory[0]["status"] != "AVAILABLE":
            return {
                "status": "UNAVAILABLE",
                "reason": inventory[0].get(
                    "reason", "ROOT_NOT_COMPILED"
                ),
            }

        if summary is None:
            return {
                "status": "UNAVAILABLE",
                "reason": "GRAPH_SUMMARY_NOT_AVAILABLE",
            }

        if summary.get("mode") != "cold-all-compiled-roots":
            return {
                "status": "UNAVAILABLE",
                "reason": "GRAPH_SUMMARY_MODE_MISMATCH",
            }

        if (
            summary.get("requested_tier") != tier
            or summary.get("language") != capture.get("language")
            or summary.get("workload") != capture.get("workload")
            or summary.get("phase") != capture.get("selected_phase")
        ):
            return {
                "status": "UNAVAILABLE",
                "reason": "GRAPH_SUMMARY_IDENTITY_MISMATCH",
            }

        if len(units) != 1:
            return {
                "status": "UNAVAILABLE",
                "reason": "ROOT_GRAPH_NOT_AVAILABLE",
            }

        unit = units[0]

        if unit.get("tier") != tier:
            return {
                "status": "UNAVAILABLE",
                "reason": "ROOT_GRAPH_TIER_MISMATCH",
            }

        graph = unit.get("graph") or {}
        count = graph.get("node_count")
        histogram = graph.get("node_class_histogram")

        if (
            type(count) is not int
            or count < 0
            or not isinstance(histogram, dict)
        ):
            return {
                "status": "UNAVAILABLE",
                "reason": "GRAPH_METRICS_MISSING",
            }

        if (
            any(
                type(value) is not int or value < 0
                for value in histogram.values()
            )
            or sum(histogram.values()) != count
        ):
            raise EvidenceError(
                "GRAPH_HISTOGRAM_INCONSISTENT",
                normalized,
            )

        if inventory:
            recorded_target = inventory[0].get("target")
            if (
                recorded_target is not None
                and unit.get("target") != recorded_target
            ):
                return {
                    "status": "UNAVAILABLE",
                    "reason": "ROOT_TARGET_MISMATCH",
                }

        matching_compilations = [
            item
            for item in capture.get(
                "selected_compilations", []
            )
            if (
                item.get("comp_id") == unit.get("comp_id")
                and normalize_label(
                    item.get("root", "")
                ) == normalized
            )
        ]

        if len(matching_compilations) != 1:
            return {
                "status": "UNAVAILABLE",
                "reason": "ROOT_COMPILATION_METADATA_NOT_UNIQUE",
            }

        machine_bytes = matching_compilations[0].get(
            "machine_code_bytes"
        )

        if type(machine_bytes) is not int or machine_bytes < 0:
            return {
                "status": "UNAVAILABLE",
                "reason": "MACHINE_CODE_SIZE_NOT_AVAILABLE",
            }

        return {
            "status": "AVAILABLE",
            "root": unit["label"],
            "normalized_root": normalized,
            "target": unit.get("target"),
            "tier": tier,
            "comp_id": unit.get("comp_id"),
            "node_count": count,
            "node_class_histogram": histogram,
            "machine_code_bytes": machine_bytes,
            "bgv": unit.get("bgv"),
            "bgv_sha256": unit.get("bgv_sha256"),
            "analysis": unit.get("analysis"),
            "analysis_sha256": unit.get("analysis_sha256"),
        }

    rows = []

    for normalized in normalized_roots:
        first = tier_observation(1, normalized)
        second = tier_observation(2, normalized)

        if not compatible:
            pair_status = "PRODUCER_IDENTITY_MISMATCH"
        elif (
            first["status"] == "AMBIGUOUS"
            or second["status"] == "AMBIGUOUS"
        ):
            pair_status = "ROOT_IDENTITY_AMBIGUOUS"
        elif (
            first["status"] != "AVAILABLE"
            or second["status"] != "AVAILABLE"
        ):
            pair_status = "INCOMPLETE"
        else:
            pair_status = "PAIRED"

        rows.append({
            "normalized_root": normalized,
            "pair_status": pair_status,
            "tier_1": first,
            "tier_2": second,
            "node_count_delta_t2_minus_t1": (
                second["node_count"] - first["node_count"]
                if pair_status == "PAIRED"
                else None
            ),
        })

    if not compatible:
        status = "INCOMPATIBLE"
    elif rows and all(
        row["pair_status"] == "PAIRED"
        for row in rows
    ):
        status = "COMPLETE"
    else:
        status = "PARTIAL"

    return {
        "schema": 1,
        "mode": "cold-compiled-root-tier-pair",
        "scope": "observed-compiled-call-targets-only",
        "status": status,
        "producer_identity_compatible": compatible,
        "producer_identities": identities,
        "pairing_basis": (
            "normalized-label-unique-within-each-capture"
        ),
        "roots": rows,
        "interpreted_roots_coverage": "NOT_ESTABLISHED",
        "timing_evidence": "NONE",
    }


def normalize_label(label: str) -> str:
    """Removes per-process object identity (``@4ae9cfc1``, `` at 2cbc655a>``)
    so that the same root can be compared across processes."""
    return LABEL_IDENTITY_RE.sub("*", label)


# ---------------------------------------------------------------------------
# Relevant compilation units


def resolve_units(
    parsed: dict[str, Any],
    policy: dict[str, Any],
    language_policy: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    """Relevant language-owned compilation units of one steady
    ``Value.execute()``.

    The primary unit is the single guest root the framework entry root calls
    (depth-1 callee in every framework compilation's inlining tree), checked
    against the language's primary-label pattern. Additional units are the
    separately compiled language-owned callees that remain calls
    (``call_edge_verbs``) in the final compilation of a unit already counted,
    transitively. Inlined callees are already inside their caller's graph and
    are never added. Framework roots, superseded compilations and roots not
    reachable from the primary unit (setup, module evaluation, unrelated
    builtins) are never counted; the latter are listed as unattributed.
    """
    framework = [re.compile(p) for p in policy["framework_label_patterns"]]
    call_verbs = set(policy["call_edge_verbs"])

    def is_framework(label: str) -> bool:
        return any(pattern.search(label) for pattern in framework)

    targets = target_lifecycles(parsed)
    by_label: dict[str, list[str]] = {}

    for key, entry in targets.items():
        if not is_framework(entry["label"]):
            by_label.setdefault(entry["label"], []).append(key)

    framework_targets = [t for t in targets.values() if is_framework(t["label"])]

    if not framework_targets:
        raise EvidenceError("FRAMEWORK_ENTRY_NOT_COMPILED")

    entry_labels: set[str] = set()

    for target in framework_targets:
        for compilation in target["compilations"]:
            if compilation["inline_tree"] is None:
                raise EvidenceError("INLINING_TRACE_MISSING", compilation["label"])
            entry_labels.update(
                e["label"] for e in compilation["inline_tree"] if e["depth"] == 1
            )

    if not entry_labels:
        raise EvidenceError("PRIMARY_ENTRY_MISSING")

    if len(entry_labels) > 1:
        raise EvidenceError("PRIMARY_ENTRY_AMBIGUOUS", sorted(entry_labels))

    primary_label = next(iter(entry_labels))
    keys = by_label.get(primary_label, [])

    if not keys:
        raise EvidenceError("PRIMARY_NOT_COMPILED", primary_label)

    if len(keys) > 1:
        raise EvidenceError("PRIMARY_AMBIGUOUS", primary_label)

    primary = targets[keys[0]]

    if not re.search(language_policy["primary_label_pattern"], primary_label):
        raise EvidenceError("PRIMARY_IDENTITY_MISMATCH", primary_label)

    if language_policy.get("primary_src_contains_source") and source not in str(
        primary["final"].get("src") or ""
    ):
        raise EvidenceError(
            "PRIMARY_SOURCE_MISMATCH", f"{primary_label}: {primary['final'].get('src')}"
        )

    units = [{"role": "primary", "target": primary["target"], "via": None, "edge": None}]
    seen = {primary["target"]}
    queue = [primary["target"]]
    uncompiled: list[str] = []

    while queue:
        key = queue.pop(0)
        tree = targets[key]["final"]["inline_tree"]

        if tree is None:
            raise EvidenceError("INLINING_TRACE_MISSING", targets[key]["label"])

        for edge in tree:
            if edge["verb"] not in call_verbs or is_framework(edge["label"]):
                continue

            callee = by_label.get(edge["label"], [])

            if not callee:
                uncompiled.append(edge["label"])
                continue

            if len(callee) > 1:
                raise EvidenceError("CALLEE_AMBIGUOUS", edge["label"])

            if callee[0] not in seen:
                seen.add(callee[0])
                queue.append(callee[0])
                units.append(
                    {
                        "role": "additional",
                        "target": callee[0],
                        "via": targets[key]["label"],
                        "edge": edge["verb"],
                    }
                )

    for unit in units:
        entry = targets[unit["target"]]
        final = entry["final"]
        unit.update(
            {
                "label": entry["label"],
                "normalized_label": normalize_label(entry["label"]),
                "tier": final["tier"],
                "comp_id": final["comp_id"],
                "src": final.get("src"),
                "superseded_comp_ids": entry["superseded_comp_ids"],
                "invalidated_after_final": entry["invalidated_after_final"],
                "failed_after_final": entry["failed_after_final"],
                "ir_after_truffle_tier": final["ir_after_truffle_tier"],
                "inlined": [e["label"] for e in final["inline_tree"] or [] if e["verb"] == "Inlined"],
                "expansion_truffle_tier": (final["expansion"] or {}).get("root"),
            }
        )

    return {
        "primary_label": primary_label,
        "units": units,
        "uncompiled_callees": sorted(set(uncompiled)),
        "framework_targets": sorted(t["label"] for t in framework_targets),
        "unattributed_language_targets": sorted(
            targets[k]["label"]
            for keys_ in by_label.values()
            for k in keys_
            if k not in seen
        ),
    }


def expansion_attribution(parsed: dict[str, Any], comp_id: int, limit: int = 12) -> list[dict[str, Any]]:
    """Expansion-tree rows of one compilation with the largest own node count:
    compact language/runtime attribution of the selected graph."""
    for compilation in parsed["compilations"]:
        if compilation["comp_id"] == comp_id and compilation["expansion"]:
            rows = [r for r in compilation["expansion"]["rows"] if r["name"] != "<call-root>"]
            rows.sort(key=lambda r: (-r["self"]["count"], r["name"]))
            return [
                {"name": r["name"], "self": r["self"], "location": r["location"]}
                for r in rows[:limit]
                if r["self"]["count"] > 0
            ]
    return []


def assess_run(
    parsed: dict[str, Any],
    resolution: dict[str, Any] | None,
    final_tier: int,
    error: EvidenceError | None = None,
) -> dict[str, Any]:
    """Trace-side status and stabilization signature of one budget run."""
    problems: list[str] = []

    if error is not None:
        problems.append(error.reason)
    if parsed["option_rejections"]:
        problems.append("OPTION_REJECTED")
    if parsed["unknown_lifecycle_events"]:
        problems.append("UNKNOWN_LIFECYCLE_EVENT")

    signature = None

    if resolution is not None:
        for unit in resolution["units"]:
            if unit["tier"] != final_tier:
                problems.append("UNIT_NOT_AT_FINAL_TIER")
            if unit["invalidated_after_final"]:
                problems.append("UNIT_INVALIDATED_AFTER_FINAL")
            if unit["failed_after_final"]:
                problems.append("UNIT_RECOMPILATION_FAILED")
        if resolution["uncompiled_callees"]:
            problems.append("UNCOMPILED_CALLEE")
        signature = [
            {
                "role": unit["role"],
                "label": unit["normalized_label"],
                "tier": unit["tier"],
                "ir_after_truffle_tier": unit["ir_after_truffle_tier"],
                "expansion_truffle_tier": unit["expansion_truffle_tier"],
            }
            for unit in resolution["units"]
        ]

    return {
        "status": NOT_STABLE if problems else STABLE_CANDIDATE,
        "problems": sorted(set(problems)),
        "signature": signature,
    }


def stabilize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """First two consecutive budgets that are both stable candidates with an
    identical signature (tier, graph count, per-unit structure)."""
    for previous, current in zip(runs, runs[1:]):
        a, b = previous["assessment"], current["assessment"]
        if (
            a["status"] == STABLE_CANDIDATE
            and b["status"] == STABLE_CANDIDATE
            and a["signature"] == b["signature"]
        ):
            return {"status": STABLE, "pair": [previous["budget"], current["budget"]]}

    return {"status": GRAPH_NOT_STABLE, "pair": None}


# ---------------------------------------------------------------------------
# BGV-derived graphs (IgvUtility filter JSON)



def parse_bytecode_histogram(output: str) -> dict[str, Any]:
    """Parse GraalVM's diagnostic Bytecode DSL instruction histogram.

    Grouping is expected to be language,root. Counts describe executed
    interpreter instructions, never static bytecode size or JIT Tier 1/2
    graph nodes. Missing instrumentation is explicit, not a zero count.
    """
    header = re.compile(
        r"^(?:\[engine\]\s+)?\[bc\] Instruction histogram for:\s*(.+?)\s*$"
    )
    row_pattern = re.compile(
        r"^\s*(\d+)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*(.*?)\s*$"
    )
    instruction_pattern = re.compile(
        r"^[0-9a-fA-F]+\s+(.+?)\s*$"
    )
    total_pattern = re.compile(
        r"^Total executed instructions:\s*(\d+)\s*$"
    )

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    interpreter = None
    language = None
    root = None
    block_sum = 0
    block_total_seen = False
    declared_total = 0
    saw_header = False

    def finish_block() -> None:
        if interpreter is not None and not block_total_seen:
            raise EvidenceError(
                "BYTECODE_HISTOGRAM_TOTAL_MISSING",
                interpreter,
            )

    for original_line in output.splitlines():
        line = original_line.strip()

        match = header.match(line)
        if match:
            finish_block()
            interpreter = match.group(1)
            language = None
            root = None
            block_sum = 0
            block_total_seen = False
            saw_header = True
            continue

        if interpreter is None:
            continue

        if line.startswith("[bc]"):
            line = line[4:].strip()

        total = total_pattern.match(line)
        if total:
            count = int(total.group(1))
            if block_total_seen or count != block_sum:
                raise EvidenceError(
                    "BYTECODE_HISTOGRAM_TOTAL_MISMATCH",
                    {
                        "interpreter": interpreter,
                        "reported": count,
                        "operations": block_sum,
                    },
                )
            declared_total += count
            block_total_seen = True
            continue

        match = row_pattern.match(line)
        if not match:
            continue

        count = int(match.group(1))
        label = match.group(3).strip()

        if label.startswith("▶"):
            group_name = label[1:].strip()
            if group_name.startswith("Language:"):
                language = group_name.partition(":")[2].strip()
                root = None
            elif group_name.startswith("Root:"):
                root = group_name.partition(":")[2].strip()
            elif re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", group_name):
                language = group_name
                root = None
            else:
                raise EvidenceError(
                    "BYTECODE_HISTOGRAM_UNKNOWN_GROUP",
                    group_name,
                )
            continue

        instruction = instruction_pattern.match(label)
        if instruction is None:
            continue

        if not language or not root or block_total_seen:
            raise EvidenceError(
                "BYTECODE_HISTOGRAM_ROOT_MISSING",
                label,
            )

        operation = instruction.group(1).strip()
        if not operation:
            raise EvidenceError(
                "BYTECODE_HISTOGRAM_OPERATION_MISSING",
                label,
            )

        key = (interpreter, language, root)
        group = groups.setdefault(
            key,
            {
                "interpreter": interpreter,
                "language": language,
                "root": root,
                "normalized_root": normalize_label(root),
                "operation_counts": {},
                "executed_instructions": 0,
            },
        )
        counts = group["operation_counts"]
        counts[operation] = counts.get(operation, 0) + count
        group["executed_instructions"] += count
        block_sum += count

    finish_block()

    if not saw_header:
        return {
            "schema": 1,
            "status": "UNAVAILABLE",
            "reason": "BYTECODE_DSL_HISTOGRAM_NOT_REPORTED",
            "groups": [],
            "total_executed_instructions": None,
        }

    if not groups:
        raise EvidenceError(
            "BYTECODE_HISTOGRAM_NO_ROOT_OPERATIONS"
        )

    ordered = sorted(
        groups.values(),
        key=lambda item: (
            item["language"],
            item["normalized_root"],
            item["root"],
            item["interpreter"],
        ),
    )

    for group in ordered:
        group["operation_counts"] = dict(
            sorted(group["operation_counts"].items())
        )

    return {
        "schema": 1,
        "status": "AVAILABLE",
        "kind": "executed-bytecode-dsl-operations",
        "groups": ordered,
        "total_executed_instructions": declared_total,
    }


def dump_comp_id(name: str) -> int | None:
    match = DUMP_NAME_RE.match(name)
    return int(match.group("comp_id")) if match else None


def dumps_for(comp_id: int, names: Iterable[str]) -> list[str]:
    return sorted(name for name in names if dump_comp_id(name) == comp_id)


GRAPH_NAME_KEYS = ("name", "title", "graph_name", "graphName")
NODE_PROPERTY_KEYS = ("properties", "props", "node_properties")
NODE_CLASS_KEYS = ("class", "nodeClass", "node_class", "className", "class_name", "type")


def _name_of(value: dict[str, Any]) -> str | None:
    for key in GRAPH_NAME_KEYS:
        if isinstance(value.get(key), str):
            return value[key]
    return None


def iter_graphs(value: Any, path: tuple[str, ...] = ()) -> Iterable[dict[str, Any]]:
    """Every graph (an object with a ``nodes`` collection) with its group
    path, at any nesting depth of the exported document."""
    if isinstance(value, dict):
        name = _name_of(value)
        if isinstance(value.get("nodes"), (list, dict)):
            yield {
                "path": list(path),
                "name": name or "",
                "graph_type": value.get("graph_type"),
                "graph": value,
            }
            return
        child_path = path + ((name,) if name else ())
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from iter_graphs(item, child_path)
    elif isinstance(value, list):
        for item in value:
            yield from iter_graphs(item, path)


def phase_name(name: str) -> str:
    return PHASE_PREFIX_RE.sub("", name or "").strip()


IR_GRAPH_TYPE = "StructuredGraph"


def select_phase(graphs: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    """The single compiler-IR graph of ``phase``. Dumps also carry same-named
    non-IR views (for example the ``AST`` group's ``After TruffleTier`` tree,
    ``graph_type=defaultType``); when graph types are exported, only
    ``StructuredGraph`` graphs are candidates."""
    if any(g.get("graph_type") is not None for g in graphs):
        graphs = [g for g in graphs if g.get("graph_type") == IR_GRAPH_TYPE]
    matches = [g for g in graphs if phase_name(g["name"]) == phase]

    if not matches:
        raise EvidenceError("PHASE_MISSING", phase)

    if len(matches) > 1:
        raise EvidenceError("PHASE_AMBIGUOUS", f"{phase} x{len(matches)}")

    return matches[0]


def iter_nodes(nodes: Any) -> Iterable[dict[str, Any]]:
    if isinstance(nodes, dict):
        for key, node in nodes.items():
            yield node if isinstance(node, dict) else {"id": key, "value": node}
    else:
        for node in nodes:
            yield node if isinstance(node, dict) else {"value": node}


def _properties(node: dict[str, Any]) -> dict[str, Any]:
    for key in NODE_PROPERTY_KEYS:
        if isinstance(node.get(key), dict):
            return node[key]
    return {}


def node_class(node: dict[str, Any]) -> str | None:
    for source in (node, _properties(node)):
        for key in NODE_CLASS_KEYS:
            value = source.get(key)
            if isinstance(value, dict):
                value = value.get("name") or value.get("className")
            if isinstance(value, str) and value:
                return value.rsplit(".", 1)[-1]
    return None


def family_of(cls: str) -> str | None:
    if cls.startswith("Invoke"):
        return "invokes"
    if cls == "IfNode" or cls.endswith("SwitchNode"):
        return "control_flow_splits"
    if (
        cls.startswith(("New", "Allocate", "BoxNode"))
        or cls == "CommitAllocationNode"
        or "Allocating" in cls
    ):
        return "allocations"
    if "Guard" in cls or "Deoptimize" in cls:
        return "guards_deopts"
    if "Load" in cls or cls in ("ReadNode", "FloatingReadNode"):
        return "loads"
    if cls == "LoopBeginNode":
        return "loops"
    return None


def graph_metrics(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = list(iter_nodes(graph["nodes"]))
    classes = [node_class(node) for node in nodes]
    histogram = Counter(cls or "?" for cls in classes)
    families = {family: 0 for family in FAMILIES}
    invoke_targets: Counter[str] = Counter()

    for node, cls in zip(nodes, classes):
        family = family_of(cls or "")
        if family:
            families[family] += 1
        if family == "invokes":
            props = _properties(node)
            target = props.get("targetMethod") or node.get("targetMethod")
            if isinstance(target, str):
                invoke_targets[target] += 1

    return {
        "node_count": len(nodes),
        "histogram_available": None not in classes,
        "node_class_histogram": dict(sorted(histogram.items())),
        **families,
        "invoke_targets": dict(sorted(invoke_targets.items())),
    }


def select_unit_graph(document: Any, phase: str) -> dict[str, Any]:
    graphs = list(iter_graphs(document))

    if not graphs:
        raise EvidenceError("BGV_NO_GRAPHS")

    selected = select_phase(graphs, phase)
    return {
        "phase": phase_name(selected["name"]),
        "graph_name": selected["name"],
        "graph_type": selected.get("graph_type"),
        "group_path": selected["path"],
        "graphs_in_dump": len(graphs),
        **graph_metrics(selected["graph"]),
    }


def instability_evidence(parsed: dict[str, Any], policy: dict[str, Any], primary_label: str) -> dict[str, Any]:
    """Lifecycle facts of an unstable primary unit, derived from the raw
    trace: compilations per tier, invalidations, failures and the final edge
    the framework entry compilation recorded for it (e.g. ``BailedOut``)."""
    framework = [re.compile(p) for p in policy["framework_label_patterns"]]
    compilations = [c for c in parsed["compilations"] if c["label"] == primary_label]
    failures = [f for f in parsed["failures"] if f["label"] == primary_label]
    edge = None

    for compilation in parsed["compilations"]:
        if any(p.search(compilation["label"]) for p in framework):
            for entry in compilation["inline_tree"] or []:
                if entry["depth"] == 1 and entry["label"] == primary_label:
                    edge = entry["verb"]

    last_done = compilations[-1]["seq"] if compilations else -1

    if edge == "BailedOut":
        state = "BailedOut"
    elif failures and failures[-1]["seq"] > last_done:
        state = "FAILED"
    elif compilations:
        state = f"COMPILED_TIER_{compilations[-1]['tier']}"
    else:
        state = "NOT_COMPILED"

    tiers = Counter(c["tier"] for c in compilations)
    return {
        "primary_label": primary_label,
        "primary_compilations": len(compilations),
        "primary_compilations_by_tier": {str(k): v for k, v in sorted(tiers.items())},
        "primary_invalidation_events": sum(1 for i in parsed["invalidations"] if i["label"] == primary_label),
        "primary_failures": [
            {"tier": f["tier"], "reason": str(f["reason"] or "").split("|", 1)[0].strip()}
            for f in failures
        ],
        "maximum_compilation_count_reached": any(
            MAX_COMPILATIONS_RE.search(str(f["reason"] or "")) for f in failures
        ),
        "framework_edge_to_primary": edge,
        "final_compilation_state": state,
    }


# ---------------------------------------------------------------------------
# Per-case and cross-language summaries


def case_summary(units: list[dict[str, Any]]) -> dict[str, Any]:
    """Relevant total over the selected units. Each unit carries its
    ``graph`` (``select_unit_graph`` result)."""
    if not units or units[0]["role"] != "primary":
        raise EvidenceError("PRIMARY_UNIT_MISSING")

    total = sum(unit["graph"]["node_count"] for unit in units)
    histogram: Counter[str] = Counter()

    for unit in units:
        histogram.update(unit["graph"]["node_class_histogram"])

    return {
        "relevant_graph_nodes_total_after_truffle_tier": total,
        "primary_guest_graph_nodes": units[0]["graph"]["node_count"],
        "graph_count": len(units),
        "additional_language_owned_compiled_units": [
            {"label": u["label"], "via": u["via"], "edge": u["edge"], "nodes": u["graph"]["node_count"]}
            for u in units[1:]
        ],
        "families": {f: sum(u["graph"][f] for u in units) for f in FAMILIES},
        "node_class_histogram": dict(sorted(histogram.items())),
        "trace_node_expansion_truffle_tier": [u.get("expansion_truffle_tier") for u in units],
    }


def compare_rung(
    workload: str,
    mechanism: str,
    cases: dict[str, dict[str, Any] | None],
    protos_instability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Peer reference (GraalJS/GraalPy) and Protos structural status of one rung.

    ``cases[language]`` is a ``case_summary`` or None when that language has
    no valid stable evidence; ``protos_instability`` (``{"problems": [...],
    "evidence": instability_evidence(...)}``) is given when Protos evidence is
    missing because its graph never stabilized: with converged peers that is
    ``DIVERGED_BEFORE_GRAPH_PARITY`` and no node comparison is made. No
    fixed tolerance: the peer band is the
    observed JS/Python range and the excess threshold is their spread.
    """
    js, python, protos = cases.get("js"), cases.get("python"), cases.get("protos")
    total = "relevant_graph_nodes_total_after_truffle_tier"
    result: dict[str, Any] = {
        "workload": workload,
        "mechanism": mechanism,
        "protos_total": protos[total] if protos else None,
        "protos_node_total": protos[total] if protos else "N/A",
        "protos_stabilization": (
            STABLE if protos else (GRAPH_NOT_STABLE if protos_instability is not None else None)
        ),
        "peer_node_comparison": COMPARISON_SKIPPED,
        "final_compilation_state": None,
        "js_total": js[total] if js else None,
        "python_total": python[total] if python else None,
        "graph_counts": {
            lang: (case["graph_count"] if case else None)
            for lang, case in (("protos", protos), ("js", js), ("python", python))
        },
        "additional_units": {
            lang: ([u["label"] for u in case["additional_language_owned_compiled_units"]] if case else None)
            for lang, case in (("protos", protos), ("js", js), ("python", python))
        },
        "peer_spread": None,
        "peer_band": None,
        "peer_reference": PEER_UNRESOLVED,
        "peer_reasons": [],
        "protos_status": NOT_EVALUATED,
        "protos_signals": [],
        "secondary_deltas_vs_peer_max": None,
    }

    if js is None or python is None:
        result["peer_reasons"].append("PEER_EVIDENCE_MISSING")
        return result

    if js["graph_count"] != python["graph_count"]:
        result["peer_reasons"].append("PEER_TOPOLOGY_DISAGREES")

    for family in QUALITATIVE_FAMILIES:
        if (js["families"][family] > 0) != (python["families"][family] > 0):
            result["peer_reasons"].append(f"PEER_{family.upper()}_PRESENCE_DISAGREES")

    low, high = sorted((js[total], python[total]))
    result["peer_band"] = [low, high]
    result["peer_spread"] = high - low

    if result["peer_reasons"]:
        return result

    result["peer_reference"] = PEER_CONVERGED

    if protos is None:
        if protos_instability is not None:
            evidence = protos_instability.get("evidence") or {}
            signals = sorted(protos_instability.get("problems") or [GRAPH_NOT_STABLE])
            if evidence.get("final_compilation_state") == "BailedOut":
                signals.append("FINAL_COMPILATION_STATE_BAILED_OUT")
            if evidence.get("maximum_compilation_count_reached"):
                signals.append("MAXIMUM_COMPILATION_COUNT_REACHED")
            result["protos_status"] = DIVERGED_BEFORE_GRAPH_PARITY
            result["protos_signals"] = signals
            result["protos_instability"] = evidence
            result["final_compilation_state"] = evidence.get("final_compilation_state")
        else:
            result["protos_signals"].append("PROTOS_EVIDENCE_MISSING")
        return result

    signals = []

    if protos["graph_count"] > js["graph_count"]:
        signals.append("ADDITIONAL_PROTOS_COMPILED_UNIT")

    if protos[total] - high > result["peer_spread"]:
        signals.append("NODE_EXCESS_BEYOND_PEER_SPREAD")

    for family in FAMILIES:
        if protos["families"][family] > 0 and js["families"][family] == 0 and python["families"][family] == 0:
            signals.append(f"PROTOS_ONLY_{family.upper()}")

    result["protos_signals"] = signals
    result["peer_node_comparison"] = COMPARISON_PERFORMED
    result["protos_status"] = STRUCTURAL_EXCESS if signals else STRUCTURALLY_CONVERGED
    result["secondary_deltas_vs_peer_max"] = {
        family: protos["families"][family] - max(js["families"][family], python["families"][family])
        for family in FAMILIES
    }
    result["excess_over_peer_max"] = protos[total] - high
    return result


def first_divergent(rungs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for rung in rungs:
        if rung["protos_status"] in (STRUCTURAL_EXCESS, DIVERGED_BEFORE_GRAPH_PARITY):
            return {
                "workload": rung["workload"],
                "mechanism": rung["mechanism"],
                "protos_status": rung["protos_status"],
                "signals": rung["protos_signals"],
            }
    return None



def parse_bytecode_size_trace(output: str) -> dict[str, Any]:
    """Parse exact per-root Bytecode DSL sizes from diagnostic JVM output.

    Each record is tied to an observed physical root instance, bytecode
    interpreter tier, and instruction snapshot. Separate snapshots are not
    collapsed when quickening changes the bytecode representation.

    No observed records means unavailable evidence, never zero bytecode.
    """
    import base64
    import binascii

    marker = "BENCH_BYTECODE_SIZE_V2"
    observations = []
    seen = set()
    instance_identities = {}
    physical_handles = {}

    for line in output.splitlines():
        if not line.startswith(marker + "\t"):
            continue

        fields = line.split("\t")

        if len(fields) != 9:
            raise EvidenceError(
                "INVALID_BYTECODE_SIZE_RECORD", line
            )

        (
            _,
            encoded_name,
            instance_text,
            tier,
            count_text,
            bytes_text,
            first_text,
            last_text,
            encoded_physical,
        ) = fields

        try:
            root_name = base64.b64decode(
                encoded_name, validate=True
            ).decode("utf-8")

            physical_root_label = base64.b64decode(
                encoded_physical, validate=True
            ).decode("utf-8")

            root_instance = int(instance_text)
            instruction_count = int(count_text)
            bytecode_bytes = int(bytes_text)
            first_bci = int(first_text)
            last_end_bci = int(last_text)

        except (
            UnicodeDecodeError,
            binascii.Error,
            ValueError,
        ) as error:
            raise EvidenceError(
                "INVALID_BYTECODE_SIZE_RECORD", line
            ) from error

        if (
            not root_name
            or not re.fullmatch(
                r"[^@\s]+@[0-9a-fA-F]+",
                physical_root_label,
            )
            or root_instance < 1
            or tier not in {"UNCACHED", "CACHED"}
            or instruction_count < 1
            or bytecode_bytes < 1
            or first_bci < 0
            or last_end_bci <= first_bci
            or last_end_bci - first_bci != bytecode_bytes
        ):
            raise EvidenceError(
                "INCONSISTENT_BYTECODE_SIZE", line
            )

        identity_signature = (
            root_name,
            physical_root_label,
        )

        previous = instance_identities.get(root_instance)

        if previous is not None and previous != identity_signature:
            raise EvidenceError(
                "INCONSISTENT_BYTECODE_ROOT_IDENTITY",
                line,
            )

        previous_instance = physical_handles.get(
            physical_root_label
        )

        if (
            previous_instance is not None
            and previous_instance != root_instance
        ):
            raise EvidenceError(
                "BYTECODE_PHYSICAL_ROOT_COLLISION",
                line,
            )

        instance_identities[root_instance] = identity_signature
        physical_handles[physical_root_label] = root_instance

        observation = {
            "root_name": root_name,
            "root_instance": root_instance,
            "physical_root_label": physical_root_label,
            "bytecode_tier": tier,
            "instruction_count": instruction_count,
            "bytecode_bytes": bytecode_bytes,
            "first_bci": first_bci,
            "last_end_bci": last_end_bci,
        }

        identity = (
            physical_root_label,
            root_instance,
            tier,
            instruction_count,
            bytecode_bytes,
            first_bci,
            last_end_bci,
        )

        if identity not in seen:
            observations.append(observation)
            seen.add(identity)

    if not observations:
        return {
            "status": "UNAVAILABLE",
            "reason": "NO_BYTECODE_SIZE_RECORDS",
            "observations": [],
        }

    return {
        "status": "AVAILABLE",
        "source": "TRUFFLE_INSTRUCTION_LENGTH",
        "unit": "bytes",
        "scope": "OBSERVED_INSTRUMENTED_ROOTS",
        "observations": observations,
    }
