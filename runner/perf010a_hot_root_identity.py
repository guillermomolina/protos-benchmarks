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

"""Durable root identity, logical-role resolution and lifecycle correlation (pure).

A root's durable identity is derived from things that survive a rebuild or another process:

    SHA256(source bytes) + sourceName + [startOffset, endOffset) + startLine
      + exact SourceSection text + rootNodeClassName + logical root role

The run-local `Name@hash` label and the numeric compiler id are used only as same-run correlation
keys between the root-identity inventory written by the diagnostic driver and the compiler-trace
lifecycle of that very run; they never enter the durable identity and are never assumed stable.

Logical roles are resolved from the source itself, not from numbers: a role's anchor text (for
example the workload target statement `sink = identity(42)`, whose visibility was proven by the
historical PERF010-A source-identity smoke) selects the root that contains a node with that exact
source text, and the semantic-wrapper / helper companions of that root are the roots that share its
own source section. A role that finds no root, more than one root group, a root group claimed by
another role, or lacks its semantic or helper member is an error, never a guess.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

IDENTITY_SCHEMA = "perf010a-hot-root-identity-v1"
ROOT_KEYS = ("rootNodeClassName", "simpleName", "identityHash", "label", "toString", "rootSection", "nodes")
SECTION_KEYS = ("startOffset", "endOffset", "length", "line", "column", "text")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_identity_document(
    document: Any, *, expected_source_name: str, expected_source_sha256: str
) -> dict[str, Any]:
    """Fail closed on a malformed inventory or on one that describes another source."""
    if not isinstance(document, dict) or document.get("schema") != IDENTITY_SCHEMA:
        raise RuntimeError("ROOT_IDENTITY_SCHEMA_MISMATCH")
    if document.get("source_name") != expected_source_name:
        raise RuntimeError(
            f"ROOT_IDENTITY_SOURCE_NAME_MISMATCH: {document.get('source_name')!r} != {expected_source_name!r}"
        )
    if document.get("source_sha256") != expected_source_sha256:
        raise RuntimeError("ROOT_IDENTITY_SOURCE_SHA256_MISMATCH")
    roots = document.get("roots")
    if not isinstance(roots, list) or not roots:
        raise RuntimeError("ROOT_IDENTITY_INVENTORY_EMPTY: the instrument observed no root for the target Source")
    for index, root in enumerate(roots):
        missing = [key for key in ROOT_KEYS if key not in root]
        if missing:
            raise RuntimeError(f"ROOT_IDENTITY_ROOT_INCOMPLETE: root {index} lacks {missing}")
        sections = [root["rootSection"]] if root["rootSection"] is not None else []
        sections += [node["section"] for node in root["nodes"]]
        for section in sections:
            absent = [key for key in SECTION_KEYS if key not in section]
            if absent:
                raise RuntimeError(f"ROOT_IDENTITY_SECTION_INCOMPLETE: root {index} lacks {absent}")
    return document


def root_kind(root_class_name: str, markers: dict[str, str]) -> str:
    """semantic, helper or other. The semantic marker is tested first: the helper marker is not a
    substring of the semantic class name, but the order keeps the rule independent of that."""
    if markers["semantic"] in root_class_name:
        return "semantic"
    if markers["helper"] in root_class_name:
        return "helper"
    return "other"


def role_anchor(role: dict[str, Any], variant: str) -> str | None:
    by_variant = role.get("anchor_text_by_variant")
    if by_variant is not None:
        return by_variant.get(variant)
    return role.get("anchor_text")


def node_text_matches(text: str, anchor: str, mode: str) -> bool:
    if mode == "equals":
        return text == anchor
    if mode == "contains":
        return anchor in text
    raise RuntimeError("unknown role match mode: " + repr(mode))


def durable_identity(
    *,
    source_sha256: str,
    source_name: str,
    section: dict[str, Any],
    section_origin: str,
    root_class: str,
    kind: str,
    logical_role: str | None,
    role_id: str | None,
) -> dict[str, Any]:
    payload = {
        "sourceSha256": source_sha256,
        "sourceName": source_name,
        "startOffset": section["startOffset"],
        "endOffset": section["endOffset"],
        "startLine": section["line"],
        "text": section["text"],
        "rootNodeClassName": root_class,
        "logicalRole": logical_role,
        "roleId": role_id,
    }
    return {**payload, "rootKind": kind, "sectionOrigin": section_origin, "durableId": sha256_text(canonical_json(payload))}


def identity_string(identity: dict[str, Any]) -> str:
    """The exact stable identity as one line (ROOT_SOURCE_IDENTITY)."""
    return (
        f"sha256:{identity['sourceSha256']}|{identity['sourceName']}"
        f"|[{identity['startOffset']},{identity['endOffset']})|L{identity['startLine']}"
        f"|{identity['rootNodeClassName']}|{identity['logicalRole']}|{identity['text']!r}"
    )


def _group_key(root: dict[str, Any], index: int) -> tuple[Any, ...]:
    section = root["rootSection"]
    if section is not None:
        return ("section", section["startOffset"], section["endOffset"])
    return ("root", index)


def resolve_roles(
    document: dict[str, Any], roles: list[dict[str, Any]], variant: str, markers: dict[str, str]
) -> dict[str, Any]:
    """Resolve every role that applies to `variant`. Never raises: each role carries a status of
    RESOLVED, MISSING, AMBIGUOUS or OVERLAP, and `require_roles_resolved` decides."""
    roots = document["roots"]
    kinds = [root_kind(root["rootNodeClassName"], markers) for root in roots]
    groups = [_group_key(root, index) for index, root in enumerate(roots)]
    resolutions: dict[str, Any] = {}
    claimed: dict[tuple[Any, ...], list[str]] = {}

    for role in roles:
        if variant not in role["variants"]:
            continue
        anchor = role_anchor(role, variant)
        direct: dict[int, dict[str, Any]] = {}
        if anchor:
            for index, root in enumerate(roots):
                for node in root["nodes"]:
                    if node_text_matches(node["section"]["text"], anchor, role["match"]):
                        direct[index] = node["section"]
                        break
        direct_groups = sorted({groups[index] for index in direct})
        entry: dict[str, Any] = {
            "role_id": role["id"],
            "logical_role": role["logical_role"],
            "anchor_text": anchor,
            "match": role["match"],
            "direct_root_indices": sorted(direct),
            "members": [],
            "missing_kinds": [],
        }
        if not direct_groups:
            entry["status"] = "MISSING"
        elif len(direct_groups) > 1:
            entry["status"] = "AMBIGUOUS"
        else:
            group = direct_groups[0]
            entry["status"] = "RESOLVED"
            claimed.setdefault(group, []).append(role["id"])
            anchor_section = direct[sorted(direct)[0]]
            for index, root in enumerate(roots):
                if groups[index] != group:
                    continue
                own = root["rootSection"]
                section = own if own is not None else direct.get(index, anchor_section)
                entry["members"].append(
                    {
                        "root_index": index,
                        "label": root["label"],
                        "toString": root["toString"],
                        "rootNodeClassName": root["rootNodeClassName"],
                        "kind": kinds[index],
                        "identity": durable_identity(
                            source_sha256=document["source_sha256"],
                            source_name=document["source_name"],
                            section=section,
                            section_origin="root" if own is not None else "anchor",
                            root_class=root["rootNodeClassName"],
                            kind=kinds[index],
                            logical_role=role["logical_role"],
                            role_id=role["id"],
                        ),
                    }
                )
            present = {member["kind"] for member in entry["members"]}
            entry["missing_kinds"] = [kind for kind in ("semantic", "helper") if kind not in present]
        entry["group"] = list(direct_groups[0]) if len(direct_groups) == 1 else None
        resolutions[role["id"]] = entry

    for group, role_ids in claimed.items():
        if len(role_ids) > 1:
            for role_id in role_ids:
                resolutions[role_id]["status"] = "OVERLAP"
                resolutions[role_id]["overlaps_with"] = sorted(set(role_ids) - {role_id})

    labels: dict[str, list[int]] = {}
    for index, root in enumerate(roots):
        labels.setdefault(root["label"], []).append(index)
    return {
        "variant": variant,
        "roles": resolutions,
        "ambiguous_labels": {label: idx for label, idx in labels.items() if len(idx) > 1},
    }


def require_roles_resolved(resolution: dict[str, Any], *, require_pair: bool = True) -> None:
    """Fail closed unless every applicable role resolved to one root group with both its semantic
    and its helper member, and no run-local label is shared by two inventory roots."""
    problems: list[str] = []
    for role_id, entry in resolution["roles"].items():
        if entry["status"] != "RESOLVED":
            problems.append(f"{role_id}: {entry['status']} (anchor {entry['anchor_text']!r}, {entry['match']})")
        elif require_pair and entry["missing_kinds"]:
            problems.append(f"{role_id}: missing {entry['missing_kinds']} member")
    for label, indices in resolution["ambiguous_labels"].items():
        problems.append(f"label {label} shared by inventory roots {indices}")
    if problems:
        raise RuntimeError(
            "REQUIRED_ROOT_IDENTITY_UNRESOLVED: required SourceSection identity is missing or ambiguous: "
            + "; ".join(problems)
        )


def inventory_summary(document: dict[str, Any], *, max_nodes: int = 12, width: int = 72) -> list[str]:
    """Compact human-readable inventory, for console output when identity cannot be resolved."""

    def short(text: str) -> str:
        flat = " ".join(text.split())
        return flat if len(flat) <= width else flat[: width - 3] + "..."

    lines = []
    for index, root in enumerate(document["roots"]):
        own = root["rootSection"]
        lines.append(
            f"root[{index}] {root['label']} {root['rootNodeClassName']} "
            + (f"section=[{own['startOffset']},{own['endOffset']}) {short(own['text'])!r}" if own else "section=None")
        )
        for node in root["nodes"][:max_nodes]:
            lines.append(f"    node {short(node['section']['text'])!r} ({node['nodeClassName'].rsplit('.', 1)[-1]})")
        if len(root["nodes"]) > max_nodes:
            lines.append(f"    ... {len(root['nodes']) - max_nodes} more nodes")
    return lines


def _not_in_trace(lifecycle: dict[str, Any]) -> dict[str, Any]:
    complete = lifecycle["run"]["complete"] and not [a for a in lifecycle["anomalies"] if a["key"] is None]
    return {
        "correlation": "NOT_IN_TRACE",
        "run_local_key": None,
        "OPTIMIZATION_STATE": "NOT_TRIGGERED" if complete else "INCONCLUSIVE",
        "TIER_REACHED": "NONE",
        "FAILURE_OR_BAILOUT": "NONE",
        "INVALIDATION_OR_RECOMPILATION": "ABSENT" if complete else "INCONCLUSIVE",
        "STABLE_FINAL_OPTIMIZED_STATE": "NO" if complete else "INCONCLUSIVE",
        "classes": None,
        "events": [],
    }


def lifecycle_for_member(member: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    """The required lifecycle result for one identified root, correlated to the compiler trace of
    the same run through its run-local label. Ambiguity is INCONCLUSIVE, never a pick."""
    labels = {label for label in (member["label"], member["toString"]) if label}
    keys = sorted({key for label in labels for key in lifecycle["label_index"].get(label, [])})
    if not keys:
        return _not_in_trace(lifecycle)
    if len(keys) > 1:
        return {
            "correlation": "AMBIGUOUS_LABEL",
            "run_local_key": keys,
            "OPTIMIZATION_STATE": "INCONCLUSIVE",
            "TIER_REACHED": "INCONCLUSIVE",
            "FAILURE_OR_BAILOUT": "INCONCLUSIVE",
            "INVALIDATION_OR_RECOMPILATION": "INCONCLUSIVE",
            "STABLE_FINAL_OPTIMIZED_STATE": "INCONCLUSIVE",
            "classes": None,
            "events": [],
        }
    root = lifecycle["roots"][keys[0]]
    return {
        "correlation": "LABEL",
        "run_local_key": {"key": keys[0], "label": root["label"]},
        "OPTIMIZATION_STATE": root["OPTIMIZATION_STATE"],
        "TIER_REACHED": root["TIER_REACHED"],
        "FAILURE_OR_BAILOUT": root["FAILURE_OR_BAILOUT"],
        "INVALIDATION_OR_RECOMPILATION": root["INVALIDATION_OR_RECOMPILATION"],
        "STABLE_FINAL_OPTIMIZED_STATE": root["STABLE_FINAL_OPTIMIZED_STATE"],
        "classes": root["classes"],
        "events": root["events"],
    }


def correlate_roles(resolution: dict[str, Any], lifecycle: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per required root (role member), in role then root order."""
    rows: list[dict[str, Any]] = []
    for role_id, entry in resolution["roles"].items():
        for member in entry["members"]:
            result = lifecycle_for_member(member, lifecycle)
            rows.append(
                {
                    "role_id": role_id,
                    "logical_role": entry["logical_role"],
                    "kind": member["kind"],
                    "ROOT_SOURCE_IDENTITY": identity_string(member["identity"]),
                    "durable_id": member["identity"]["durableId"],
                    "identity": member["identity"],
                    "run_local_label": member["label"],
                    **result,
                }
            )
    return rows
