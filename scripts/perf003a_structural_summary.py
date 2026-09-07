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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stream_term_counts(path: Path, terms: list[str]) -> dict[str, int]:
    counts = {term: 0 for term in terms}
    longest = max((len(term) for term in terms), default=1)
    carry = ""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        while True:
            chunk = fh.read(4 * 1024 * 1024)
            if not chunk:
                break
            text = carry + chunk
            usable = text if len(text) <= longest else text[:-longest]
            for term in terms:
                counts[term] += usable.count(term)
            carry = text[-longest:]
    for term in terms:
        counts[term] += carry.count(term)
    return counts


def parse_expansion_rows(path: Path) -> collections.Counter[str]:
    # TraceMethodExpansion / TraceNodeExpansion rows share this useful prefix:
    # Name ... Frequency | Count Size Cycles ...
    counter: collections.Counter[str] = collections.Counter()
    row = re.compile(r"^\s*(.*?)\s+([0-9]+(?:\.[0-9]+)?)\s+\|\s+([0-9]+)\s+([0-9]+)\s+")
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = row.match(line.rstrip("\n"))
            if not m:
                continue
            name = m.group(1).strip()
            if not name or name.startswith("<") or name == "Name":
                continue
            size = int(m.group(4))
            counter[name] += size
    return counter


def extract_graph_metadata(path: Path) -> tuple[str, str]:
    # JSONExporter writes id/name/graph_type before the node object, so a bounded
    # prefix is sufficient even when a graph JSON is hundreds of MB.
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        prefix = fh.read(256 * 1024)
    name_m = re.search(r'"name"\s*:\s*"([^"]*)"', prefix)
    type_m = re.search(r'"graph_type"\s*:\s*"([^"]*)"', prefix)
    return (name_m.group(1) if name_m else "", type_m.group(1) if type_m else "")


def write_manifest(paths: list[Path], base: Path, dest: Path) -> None:
    with dest.open("w", encoding="utf-8") as fh:
        fh.write("path\tsize_bytes\tsha256\n")
        for path in paths:
            fh.write(f"{path.relative_to(base)}\t{path.stat().st_size}\t{sha256(path)}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--harness-revision", required=True)
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir).resolve()
    evidence = run_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)

    trace = run_dir / "structural.stderr"
    stdout = run_dir / "structural.stdout"
    if not trace.is_file() or not stdout.is_file():
        raise SystemExit("STRUCTURAL_SUMMARY: missing structural stdout/stderr")

    bgv_files = sorted(run_dir.glob("graal_dumps/**/*.bgv"))
    if not bgv_files:
        raise SystemExit("STRUCTURAL_SUMMARY: no BGV files were generated")
    json_files = sorted(run_dir.glob("graal_dumps/**/*.json"))
    if not json_files:
        raise SystemExit("STRUCTURAL_SUMMARY: IGV exporter produced no JSON files")

    terms = list(cfg["suspect_terms"])
    trace_counts = stream_term_counts(trace, terms)
    json_counts = {term: 0 for term in terms}
    for path in json_files:
        counts = stream_term_counts(path, terms)
        for term, count in counts.items():
            json_counts[term] += count

    expansion = parse_expansion_rows(trace)

    opt_done = opt_failed = graph_too_big = 0
    graph_lines: list[str] = []
    with trace.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lower = line.lower()
            opt_done += "opt done" in lower
            opt_failed += "opt failed" in lower
            if "graphtoobig" in lower:
                graph_too_big += 1
                graph_lines.append(line.rstrip())

    write_manifest(bgv_files, run_dir, evidence / "bgv-manifest.tsv")
    write_manifest(json_files, run_dir, evidence / "igv-json-manifest.tsv")

    with (evidence / "igv-graphs.tsv").open("w", encoding="utf-8") as fh:
        fh.write("path\tgraph_type\tgraph_name\tsize_bytes\n")
        for path in json_files:
            name, graph_type = extract_graph_metadata(path)
            fh.write(f"{path.relative_to(run_dir)}\t{graph_type}\t{name}\t{path.stat().st_size}\n")

    with (evidence / "suspect-occurrences.tsv").open("w", encoding="utf-8") as fh:
        fh.write("term\ttrace_occurrences\tigv_json_occurrences\ttotal\n")
        for term in terms:
            a, b = trace_counts[term], json_counts[term]
            fh.write(f"{term}\t{a}\t{b}\t{a+b}\n")

    with (evidence / "expansion-top.tsv").open("w", encoding="utf-8") as fh:
        fh.write("name\taggregated_reported_size\n")
        for name, size in expansion.most_common(80):
            fh.write(f"{name}\t{size}\n")

    (evidence / "graph-too-big.txt").write_text(
        "\n".join(graph_lines) + ("\n" if graph_lines else ""),
        encoding="utf-8",
    )

    # Retain compressed raw BGV remotely only when bounded. The full raw run,
    # including all JSON, remains in the ignored .work path for local reanalysis.
    compressed_dir = run_dir / "_compressed_bgv"
    compressed_dir.mkdir(exist_ok=True)
    compressed: list[Path] = []
    total_compressed = 0
    for src in bgv_files:
        target = compressed_dir / (src.name + ".gz")
        with src.open("rb") as inp, gzip.open(target, "wb", compresslevel=9) as out:
            shutil.copyfileobj(inp, out, length=1024 * 1024)
        compressed.append(target)
        total_compressed += target.stat().st_size

    retention_limit = int(cfg["retained_bgv_compressed_limit_bytes"])
    retained = total_compressed <= retention_limit
    if retained:
        remote_bgv = evidence / "bgv"
        remote_bgv.mkdir()
        for src in compressed:
            shutil.copy2(src, remote_bgv / src.name)

    raw_trace_gz = evidence / "structural-trace.stderr.gz"
    with trace.open("rb") as inp, gzip.open(raw_trace_gz, "wb", compresslevel=9) as out:
        shutil.copyfileobj(inp, out, length=1024 * 1024)

    summary = {
        "schema_version": 1,
        "perf_item": "PERF003",
        "slice": "PERF003-A",
        "evidence_class": "structural_truffle_graal_diagnostic",
        "harness_revision": args.harness_revision,
        "protos_revision": cfg["protos_revision"],
        "protos_implementation_version": cfg["protos_implementation_version"],
        "workload": cfg["workload"]["id"],
        "expected_result": cfg["workload"]["expected"],
        "diagnostic_iterations": cfg["diagnostic_iterations"],
        "graal_dump": cfg["graal_dump"],
        "expansion_tier": cfg["expansion_tier"],
        "opt_done_text_occurrences": opt_done,
        "opt_failed_text_occurrences": opt_failed,
        "graph_too_big_text_occurrences": graph_too_big,
        "bgv_files": len(bgv_files),
        "bgv_bytes": sum(p.stat().st_size for p in bgv_files),
        "igv_json_files": len(json_files),
        "igv_json_bytes": sum(p.stat().st_size for p in json_files),
        "compressed_bgv_bytes": total_compressed,
        "raw_bgv_retained_in_git": retained,
        "raw_bgv_retention_limit_bytes": retention_limit,
        "suspect_occurrences": {
            term: {
                "trace": trace_counts[term],
                "igv_json": json_counts[term],
                "total": trace_counts[term] + json_counts[term],
            }
            for term in terms
        },
        "interpretation": (
            "Structural evidence only. Term occurrence and aggregated expansion "
            "size identify candidates for controlled experiments; they do not "
            "establish causality."
        ),
    }
    (evidence / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    top_suspects = sorted(
        ((term, trace_counts[term] + json_counts[term]) for term in terms),
        key=lambda x: (-x[1], x[0]),
    )
    with (evidence / "summary.txt").open("w", encoding="utf-8") as fh:
        fh.write("PERF003-A structural diagnostic\n")
        fh.write(f"harness_revision={args.harness_revision}\n")
        fh.write(f"protos_revision={cfg['protos_revision']}\n")
        fh.write(f"workload={cfg['workload']['id']}\n")
        fh.write(f"expected={cfg['workload']['expected']}\n")
        fh.write(f"opt_done_text_occurrences={opt_done}\n")
        fh.write(f"opt_failed_text_occurrences={opt_failed}\n")
        fh.write(f"graph_too_big_text_occurrences={graph_too_big}\n")
        fh.write(f"bgv_files={len(bgv_files)}\n")
        fh.write(f"igv_json_files={len(json_files)}\n")
        fh.write(f"raw_bgv_retained_in_git={'YES' if retained else 'NO_OVERSIZE'}\n")
        fh.write("top_suspect_terms:\n")
        for term, count in top_suspects:
            fh.write(f"  {term}\t{count}\n")
        fh.write("top_expansion_names_by_aggregated_reported_size:\n")
        for name, size in expansion.most_common(20):
            fh.write(f"  {name}\t{size}\n")
        fh.write(
            "NOTE: occurrence/size rankings are attribution evidence, not causal proof.\n"
        )

    print("STRUCTURAL_SUMMARY: PASS")
    print(f"BGV_FILES={len(bgv_files)}")
    print(f"IGV_JSON_FILES={len(json_files)}")
    print(f"RAW_BGV_RETAINED_IN_GIT={'YES' if retained else 'NO_OVERSIZE'}")
    for term, count in top_suspects:
        print(f"SUSPECT term={term} occurrences={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
