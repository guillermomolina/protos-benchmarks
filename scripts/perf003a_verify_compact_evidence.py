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

import argparse
import gzip
import json
import re
from pathlib import Path


def lines(path: Path):
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result-dir", required=True)
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    out = Path(args.result_dir)
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))

    assert summary["schema_version"] == 1
    assert summary["perf_item"] == "PERF003"
    assert summary["slice"] == "PERF003-A"
    assert summary["evidence_class"] == "structural_truffle_graal_compact_attribution"
    assert summary["timing_evidence"] is False
    assert summary["protos_revision"] == cfg["protos_revision"]
    assert summary["workload"] == cfg["workload"]["id"]
    assert summary["expected_result"] == str(cfg["workload"]["expected"])
    assert summary["bgv_files"] > 0
    assert summary["compact_summaries"] == summary["bgv_files"]
    assert summary["compact_bytes"] > 0
    assert summary["igv_graphs"] > 0
    assert summary["igv_nodes"] > 0
    assert summary["igv_edges"] > 0
    assert summary["raw_bgv_rehashed_during_finalization"] is False
    assert summary["raw_bgv_compressed_during_finalization"] is False
    assert summary["raw_bgv_retained_in_git"] is False
    assert summary["full_igv_json_materialized"] is False
    for key in ("capture_harness_revision", "compact_extractor_revision", "finalization_base"):
        assert re.fullmatch(r"[0-9a-f]{40}", summary[key])

    assert len(lines(out / "bgv-manifest.tsv")) - 1 == summary["bgv_files"]
    assert len(lines(out / "compact-manifest.tsv")) - 1 == summary["compact_summaries"]
    assert len(lines(out / "igv-graphs.tsv")) - 1 == summary["igv_graphs"]
    assert len(lines(out / "suspect-occurrences.tsv")) - 1 == len(cfg["suspect_terms"])

    for name in (
        "summary.json", "bgv-manifest.tsv", "compact-manifest.tsv", "igv-graphs.tsv",
        "suspect-occurrences.tsv", "expansion-top.tsv", "graph-too-big.txt",
        "raw/igv-compact.ndjson.gz", "raw/structural-trace.stderr.gz",
        "raw/correctness.stdout", "raw/structural.stdout", "raw/runtime-class.txt",
    ):
        path = out / name
        assert path.is_file(), path
        if name != "graph-too-big.txt":
            assert path.stat().st_size > 0, path

    for name in ("raw/igv-compact.ndjson.gz", "raw/structural-trace.stderr.gz"):
        with gzip.open(out / name, "rb") as fh:
            fh.read(1)

    for path in out.rglob("*"):
        if path.is_file():
            assert not path.name.endswith(".bgv"), path
            if path.name != "summary.json":
                assert not path.name.endswith(".json"), path

    print("PERF003A_COMPACT_EVIDENCE_VERIFY: PASS")
    print(f"BGV_FILES={summary['bgv_files']}")
    print(f"COMPACT_SUMMARIES={summary['compact_summaries']}")
    print(f"IGV_GRAPHS={summary['igv_graphs']}")
    print("RAW_BGV_REHASHED=NO")
    print("RAW_BGV_COMPRESSED=NO")
    print("FULL_JSON_MATERIALIZED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
