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
import collections
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path

RAW_BGV_REHASHED = False
RAW_BGV_COMPRESSED = False
FULL_JSON_MATERIALIZED = False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_marker(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        if "=" not in line:
            raise SystemExit(f"invalid marker line: {path}: {line!r}")
        key, value = line.split("=", 1)
        data[key] = value
    for key in ("version", "source_rel", "source_size", "source_mtime"):
        if key not in data:
            raise SystemExit(f"marker missing {key}: {path}")
    if data["version"] != "1":
        raise SystemExit(f"unsupported marker version: {path}")
    return data


def parse_ndjson(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"invalid NDJSON {path}:{lineno}: {exc}") from exc
    return rows


def stream_term_counts(path: Path, terms: list[str]) -> dict[str, int]:
    counts = {term: 0 for term in terms}
    longest = max((len(term) for term in terms), default=1)
    carry = ""
    with path.open(encoding="utf-8", errors="replace") as fh:
        while True:
            chunk = fh.read(4 * 1024 * 1024)
            if not chunk:
                break
            text = carry + chunk
            split = max(0, len(text) - longest)
            body, carry = text[:split], text[split:]
            for term in terms:
                counts[term] += body.count(term)
    for term in terms:
        counts[term] += carry.count(term)
    return counts


def expansion_counts(path: Path) -> collections.Counter[str]:
    result: collections.Counter[str] = collections.Counter()
    pattern = re.compile(r"^\s*(.*?)\s+[0-9]+(?:\.[0-9]+)?\s+\|\s+[0-9]+\s+[0-9]+\s+([0-9]+)\s+")
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = pattern.match(line.rstrip("\n"))
            if not m:
                continue
            name = m.group(1).strip()
            if name and name != "Name":
                result[name] += int(m.group(2))
    return result


def gzip_file(src: Path, dst: Path) -> None:
    with src.open("rb") as inp, dst.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0) as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)


def gzip_compact(items: list[tuple[str, Path]], dst: Path) -> None:
    with dst.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0) as out:
            for source_rel, path in sorted(items):
                out.write((json.dumps({"kind":"source_boundary","source_rel":source_rel}, separators=(",", ":")) + "\n").encode())
                with path.open("rb") as fh:
                    shutil.copyfileobj(fh, out, 1024 * 1024)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--capture-harness-revision", required=True)
    ap.add_argument("--compact-extractor-revision", required=True)
    ap.add_argument("--finalization-base", required=True)
    args = ap.parse_args()

    for name in ("capture_harness_revision", "compact_extractor_revision", "finalization_base"):
        value = getattr(args, name)
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise SystemExit(f"{name}: expected 40-char lowercase SHA")

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    run = Path(args.run_dir).resolve()
    out = Path(args.output_dir).resolve()
    if out.exists():
        raise SystemExit(f"OUTPUT_PRECONDITION: exists: {out}")
    for required in ("correctness.stdout", "structural.stdout", "structural.stderr", "runtime-class.txt"):
        if not (run / required).is_file():
            raise SystemExit(f"RUN_PRECONDITION: missing {required}")

    actual = ""
    for line in (run / "correctness.stdout").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            actual = line.strip()
    expected = str(cfg["workload"]["expected"])
    if actual != expected:
        raise SystemExit(f"CORRECTNESS_PRECONDITION: expected={expected} actual={actual}")
    if "HotSpotTruffleRuntime" not in (run / "runtime-class.txt").read_text(encoding="utf-8", errors="replace"):
        raise SystemExit("OPTIMIZING_RUNTIME_PRECONDITION: FAIL")

    bgvs = sorted((run / "graal_dumps").glob("**/*.bgv"))
    bgv_rel = {str(p.relative_to(run)) for p in bgvs}
    markers = sorted((run / "igv_compact").glob("*/complete.marker"))
    if not bgvs or len(bgvs) != len(markers):
        raise SystemExit(f"COMPACT_PRECONDITION: bgv={len(bgvs)} markers={len(markers)}")

    terms = list(cfg["suspect_terms"])
    igv_counts = {term: 0 for term in terms}
    seen = set()
    bgv_manifest = []
    compact_manifest = []
    graph_rows = []
    compact_items = []
    total_graphs = total_nodes = total_edges = compact_bytes = 0

    for marker_path in markers:
        marker = parse_marker(marker_path)
        source_rel = marker["source_rel"]
        if source_rel in seen or source_rel not in bgv_rel:
            raise SystemExit(f"COMPACT_PRECONDITION: invalid source {source_rel}")
        seen.add(source_rel)
        bgv = run / source_rel
        stat = bgv.stat()
        if stat.st_size != int(marker["source_size"]) or int(stat.st_mtime) != int(marker["source_mtime"]):
            raise SystemExit(f"COMPACT_PRECONDITION: source changed {source_rel}")

        summary_path = marker_path.parent / "summary.ndjson"
        rows = parse_ndjson(summary_path)
        sources = [r for r in rows if r.get("kind") == "source"]
        graphs = [r for r in rows if r.get("kind") == "graph"]
        term_rows = [r for r in rows if r.get("kind") == "term"]
        totals = [r for r in rows if r.get("kind") == "totals"]
        if len(sources) != 1 or not graphs or len(totals) != 1 or len(term_rows) != len(terms):
            raise SystemExit(f"COMPACT_PRECONDITION: malformed summary {summary_path}")
        source = sources[0]
        digest = str(source.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SystemExit(f"COMPACT_PRECONDITION: bad source sha {source_rel}")
        if source.get("source") != source_rel or int(source.get("size_bytes", -1)) != stat.st_size:
            raise SystemExit(f"COMPACT_PRECONDITION: source identity mismatch {source_rel}")

        tmap = {r["term"]: int(r["occurrences"]) for r in term_rows}
        if set(tmap) != set(terms):
            raise SystemExit(f"COMPACT_PRECONDITION: suspect term mismatch {source_rel}")
        for term in terms:
            igv_counts[term] += tmap[term]

        local_nodes = sum(int(r["nodes"]) for r in graphs)
        local_edges = sum(int(r["edges"]) for r in graphs)
        tot = totals[0]
        if int(tot["graphs"]) != len(graphs) or int(tot["nodes"]) != local_nodes or int(tot["edges"]) != local_edges:
            raise SystemExit(f"COMPACT_PRECONDITION: totals mismatch {source_rel}")

        for r in graphs:
            graph_rows.append((source_rel, int(r["dump_id"]), str(r.get("graph_type", "")), str(r.get("graph_name", "")), int(r["nodes"]), int(r["edges"])))
        total_graphs += len(graphs)
        total_nodes += local_nodes
        total_edges += local_edges
        size = summary_path.stat().st_size
        compact_bytes += size
        bgv_manifest.append((source_rel, stat.st_size, int(marker["source_mtime"]), digest))
        compact_manifest.append((source_rel, str(summary_path.relative_to(run)), size, sha256_file(summary_path)))
        compact_items.append((source_rel, summary_path))

    if seen != bgv_rel:
        raise SystemExit("COMPACT_PRECONDITION: incomplete source coverage")

    trace = run / "structural.stderr"
    trace_counts = stream_term_counts(trace, terms)
    expansions = expansion_counts(trace)
    graph_too_big = 0
    opt_done = 0
    opt_failed = 0
    graph_lines = []
    with trace.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lower = line.lower()
            if "graphtoobig" in lower:
                graph_too_big += 1
                graph_lines.append(line.rstrip())
            opt_done += int("opt done" in lower)
            opt_failed += int("opt failed" in lower)

    out.mkdir(parents=True)
    raw = out / "raw"
    raw.mkdir()

    with (out / "bgv-manifest.tsv").open("w", encoding="utf-8") as fh:
        fh.write("path\tsize_bytes\tmtime_epoch\tsha256\n")
        for row in sorted(bgv_manifest):
            fh.write("\t".join(map(str, row)) + "\n")
    with (out / "compact-manifest.tsv").open("w", encoding="utf-8") as fh:
        fh.write("source_bgv\tcompact_path\tsize_bytes\tsha256\n")
        for row in sorted(compact_manifest):
            fh.write("\t".join(map(str, row)) + "\n")
    with (out / "igv-graphs.tsv").open("w", encoding="utf-8") as fh:
        fh.write("source_bgv\tdump_id\tgraph_type\tgraph_name\tnodes\tedges\n")
        for row in sorted(graph_rows):
            fh.write("\t".join(str(v).replace("\t", "\\t").replace("\n", "\\n") for v in row) + "\n")
    with (out / "suspect-occurrences.tsv").open("w", encoding="utf-8") as fh:
        fh.write("term\tstructural_trace\tigv_object\ttotal_attribution\n")
        for term in terms:
            fh.write(f"{term}\t{trace_counts[term]}\t{igv_counts[term]}\t{trace_counts[term] + igv_counts[term]}\n")
    with (out / "expansion-top.tsv").open("w", encoding="utf-8") as fh:
        fh.write("name\taggregated_reported_size\n")
        for name, size in expansions.most_common(100):
            fh.write(f"{name.replace(chr(9), ' ')}\t{size}\n")
    (out / "graph-too-big.txt").write_text("\n".join(graph_lines) + ("\n" if graph_lines else ""), encoding="utf-8")

    gzip_file(trace, raw / "structural-trace.stderr.gz")
    gzip_compact(compact_items, raw / "igv-compact.ndjson.gz")
    shutil.copy2(run / "correctness.stdout", raw / "correctness.stdout")
    shutil.copy2(run / "structural.stdout", raw / "structural.stdout")
    shutil.copy2(run / "runtime-class.txt", raw / "runtime-class.txt")

    summary = {
        "schema_version": 1,
        "perf_item": "PERF003",
        "slice": "PERF003-A",
        "evidence_class": "structural_truffle_graal_compact_attribution",
        "timing_evidence": False,
        "capture_harness_revision": args.capture_harness_revision,
        "compact_extractor_revision": args.compact_extractor_revision,
        "finalization_base": args.finalization_base,
        "protos_revision": cfg["protos_revision"],
        "protos_implementation_version": cfg["protos_implementation_version"],
        "workload": cfg["workload"]["id"],
        "expected_result": expected,
        "bgv_files": len(bgvs),
        "bgv_bytes": sum(r[1] for r in bgv_manifest),
        "compact_summaries": len(compact_manifest),
        "compact_bytes": compact_bytes,
        "igv_graphs": total_graphs,
        "igv_nodes": total_nodes,
        "igv_edges": total_edges,
        "graph_too_big_text_occurrences": graph_too_big,
        "opt_done_text_occurrences": opt_done,
        "opt_failed_text_occurrences": opt_failed,
        "raw_bgv_rehashed_during_finalization": RAW_BGV_REHASHED,
        "raw_bgv_compressed_during_finalization": RAW_BGV_COMPRESSED,
        "raw_bgv_retained_in_git": False,
        "full_igv_json_materialized": FULL_JSON_MATERIALIZED,
        "suspect_occurrences": {
            term: {"structural_trace": trace_counts[term], "igv_object": igv_counts[term], "total_attribution": trace_counts[term] + igv_counts[term]}
            for term in terms
        },
        "interpretation": "Attribution evidence only; occurrence and expansion rankings do not establish causality.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("PERF003A_COMPACT_FINALIZE: PASS")
    print(f"BGV_FILES={summary['bgv_files']}")
    print(f"COMPACT_SUMMARIES={summary['compact_summaries']}")
    print(f"COMPACT_BYTES={summary['compact_bytes']}")
    print(f"IGV_GRAPHS={summary['igv_graphs']}")
    print(f"IGV_NODES={summary['igv_nodes']}")
    print(f"IGV_EDGES={summary['igv_edges']}")
    print(f"GRAPH_TOO_BIG_OCCURRENCES={summary['graph_too_big_text_occurrences']}")
    print("RAW_BGV_REHASHED=NO")
    print("RAW_BGV_COMPRESSED=NO")
    print("FULL_JSON_MATERIALIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
