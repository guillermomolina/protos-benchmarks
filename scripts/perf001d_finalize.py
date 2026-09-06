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

import json
import math
from pathlib import Path
import re
import shutil
import statistics
import sys

SHA_RE = re.compile(r"^[0-9a-f]{40}$")

def load(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)

def safe_id(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value)

def parse_samples(path, kind):
    values = []
    observed = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if not fields or fields[0] != kind:
                continue
            if len(fields) != 4:
                raise RuntimeError(f"malformed measurement line in {path}: {line!r}")
            values.append(int(fields[2]))
            observed.append(fields[3])
    return values, observed

def p95(values):
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]

def stats(values):
    if not values:
        raise RuntimeError("cannot summarize an empty sample set")
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    return {
        "count": len(values),
        "median_ns": med,
        "mad_ns": statistics.median(deviations),
        "min_ns": min(values),
        "max_ns": max(values),
        "p95_ns": p95(values),
    }

def ratio(a, b):
    if b == 0:
        return None
    return a / b

if len(sys.argv) != 5:
    raise SystemExit(
        "usage: perf001d_finalize.py <repo-root> <run-dir> <destination> <harness-sha>"
    )

root = Path(sys.argv[1]).resolve()
run_dir = Path(sys.argv[2]).resolve()
destination = Path(sys.argv[3]).resolve()
harness_sha = sys.argv[4]

if not SHA_RE.fullmatch(harness_sha):
    raise SystemExit("harness SHA must be exact 40-character lowercase hex")

cfg = load(root / "config/perf001d.json")
metadata = load(run_dir / "run-metadata.json")
metadata["harness_revision"] = harness_sha

if destination.exists():
    shutil.rmtree(destination)
(destination / "raw").mkdir(parents=True)
(destination / "diagnostics").mkdir(parents=True)
(destination / "results").mkdir(parents=True)

# Preserve exact raw timing/correctness/build logs and diagnostics.
for path in (run_dir / "raw").iterdir():
    if path.is_file():
        shutil.copy2(path, destination / "raw" / path.name)
for path in (run_dir / "diagnostics").iterdir():
    if path.is_file():
        shutil.copy2(path, destination / "diagnostics" / path.name)

revision_by_label = {x["label"]: x for x in cfg["revisions"]}
image_by_label = metadata["runtime"]["images"]
environment = metadata["environment"]

rows = []
all_results = []

for workload in cfg["workloads"]:
    key = workload["id"]
    expected = str(workload["expected_stdout"])
    safe = safe_id(key)

    for label in ("pre-perf002", "post-perf002"):
        rev = revision_by_label[label]
        for mode in ("interpreter", "truffle"):
            startup_path = run_dir / "raw" / f"startup-{label}-{mode}-{safe}.tsv"
            execution_path = run_dir / "raw" / f"execution-{label}-{mode}-{safe}.tsv"

            startup, startup_observed = parse_samples(startup_path, "STARTUP")
            warmup, warmup_observed = parse_samples(execution_path, "WARMUP")
            steady, steady_observed = parse_samples(execution_path, "STEADY")

            if len(startup) != cfg["startup_samples"]:
                raise RuntimeError(f"startup sample count mismatch: {label}/{mode}/{key}")
            if len(warmup) != cfg["warmup_iterations"]:
                raise RuntimeError(f"warmup sample count mismatch: {label}/{mode}/{key}")
            if len(steady) != cfg["steady_samples"]:
                raise RuntimeError(f"steady sample count mismatch: {label}/{mode}/{key}")
            if any(x != expected for x in startup_observed + warmup_observed + steady_observed):
                raise RuntimeError(f"result mismatch in retained samples: {label}/{mode}/{key}")

            runtime = {
                "name": f"Protos-{mode}",
                "version": rev["implementation_version"],
                "jdk_version": "GraalVM Community JDK 22.0.0",
                "graal_truffle_line": cfg["truffle_runtime_version"],
                "image_tag": image_by_label[label]["tag"],
                "image_id": image_by_label[label]["id"],
                "image_repo_digests": image_by_label[label]["repo_digests"],
                "stack": cfg["stack"],
            }

            classes = [
                ("startup", startup, 0),
                ("warmup", warmup, 0),
                ("steady_state", steady, cfg["warmup_iterations"]),
            ]
            class_stats = {}
            for cls, values, warm_count in classes:
                result = {
                    "schema_version": 1,
                    "protos_revision": rev["revision"],
                    "harness_revision": harness_sha,
                    "workload": key,
                    "runtime": runtime,
                    "environment": {
                        "platform": environment["platform"],
                        "architecture": environment["architecture"],
                        "cpu_model": environment["cpu_model"],
                        "cpu_count": environment["cpu_count"],
                        "memory_bytes": environment["memory_bytes"],
                        "kernel": environment["kernel"],
                        "cpuset": environment["cpuset"],
                        "docker_server_version": environment["docker_server_version"],
                    },
                    "measurement": {
                        "class": cls,
                        "warmup_iterations": warm_count,
                        "samples_ns": values,
                        "aggregation": "median primary; MAD, min, max and nearest-rank p95 secondary; raw samples retained",
                    },
                    "perf001d": {
                        "revision_label": label,
                        "mode": mode,
                        "expected_stdout": expected,
                        "timing_instrumentation": "TraceCompilation disabled",
                    },
                }
                filename = f"{label}__{mode}__{safe}__{cls}.json"
                with (destination / "results" / filename).open("w", encoding="utf-8") as fh:
                    json.dump(result, fh, indent=2)
                    fh.write("\n")
                all_results.append(result)
                class_stats[cls] = stats(values)

            warm_first = stats(warmup[: min(5, len(warmup))])["median_ns"]
            warm_last = stats(warmup[-min(5, len(warmup)):])["median_ns"]

            rows.append({
                "revision_label": label,
                "protos_revision": rev["revision"],
                "implementation_version": rev["implementation_version"],
                "mode": mode,
                "workload": key,
                "startup_median_ns": class_stats["startup"]["median_ns"],
                "startup_mad_ns": class_stats["startup"]["mad_ns"],
                "warmup_first5_median_ns": warm_first,
                "warmup_last5_median_ns": warm_last,
                "steady_median_ns": class_stats["steady_state"]["median_ns"],
                "steady_mad_ns": class_stats["steady_state"]["mad_ns"],
                "steady_p95_ns": class_stats["steady_state"]["p95_ns"],
            })

# Parse non-timing diagnostic summary.
diagnostics = []
with (run_dir / "diagnostics" / "summary.tsv").open("r", encoding="utf-8") as handle:
    header = handle.readline().rstrip("\n").split("\t")
    for line in handle:
        values = line.rstrip("\n").split("\t")
        item = dict(zip(header, values))
        for key in (
            "rc", "opt_done", "opt_failed", "graph_too_big", "frame_escape",
            "deep_inlining", "stack_overflow", "bootstrap_error"
        ):
            item[key] = int(item[key])
        diagnostics.append(item)

# Diagnostics are intentionally separate from timing samples.
diag_index = {(x["revision_label"], x["workload"]): x for x in diagnostics}

# Human/TSV summary.
summary_fields = [
    "revision_label", "protos_revision", "implementation_version", "mode", "workload",
    "startup_median_ns", "startup_mad_ns",
    "warmup_first5_median_ns", "warmup_last5_median_ns",
    "steady_median_ns", "steady_mad_ns", "steady_p95_ns",
]
with (destination / "summary.tsv").open("w", encoding="utf-8") as fh:
    fh.write("\t".join(summary_fields) + "\n")
    for row in rows:
        fh.write("\t".join(str(row[field]) for field in summary_fields) + "\n")

# Per-workload pre/post ratios, explicitly scoped rather than generalized.
comparisons = []
row_index = {(r["revision_label"], r["mode"], r["workload"]): r for r in rows}
for workload in cfg["workloads"]:
    key = workload["id"]
    for mode in ("interpreter", "truffle"):
        pre = row_index[("pre-perf002", mode, key)]
        post = row_index[("post-perf002", mode, key)]
        comparisons.append({
            "workload": key,
            "mode": mode,
            "pre_steady_median_ns": pre["steady_median_ns"],
            "post_steady_median_ns": post["steady_median_ns"],
            "pre_over_post_steady_ratio": ratio(
                pre["steady_median_ns"], post["steady_median_ns"]
            ),
            "pre_startup_median_ns": pre["startup_median_ns"],
            "post_startup_median_ns": post["startup_median_ns"],
            "pre_over_post_startup_ratio": ratio(
                pre["startup_median_ns"], post["startup_median_ns"]
            ),
        })

evidence = {
    "schema_version": 1,
    "perf_item": "PERF001",
    "slice": "PERF001-D",
    "status": "PUBLISHED_AWAITING_PROTOS_LEDGER",
    "harness_revision": harness_sha,
    "measurement_identity": metadata,
    "correctness_gate": "PASS",
    "measurement_classes": ["startup", "warmup", "steady_state"],
    "raw_result_count": len(all_results),
    "diagnostics": diagnostics,
    "comparisons": comparisons,
    "interpretation_guard": (
        "Ratios are per-workload, per-mode observations for the two pinned revisions. "
        "They are not a claim about whole-language performance."
    ),
}
with (destination / "evidence.json").open("w", encoding="utf-8") as fh:
    json.dump(evidence, fh, indent=2)
    fh.write("\n")

# Markdown report.
pre_sha = revision_by_label["pre-perf002"]["revision"]
post_sha = revision_by_label["post-perf002"]["revision"]
lines = [
    "# PERF001-D Protos startup, warmup and steady-state measurements",
    "",
    "Status: PUBLISHED_AWAITING_PROTOS_LEDGER",
    "",
    f"- Harness revision: `{harness_sha}`",
    f"- Pre-PERF002 Protos revision: `{pre_sha}`",
    f"- Post-PERF002 Protos revision: `{post_sha}`",
    f"- Stack: `-Xss{cfg['stack']}`",
    f"- CPU set: `{environment['cpuset']}`",
    f"- Startup samples: `{cfg['startup_samples']}` per workload/mode/revision",
    f"- Warmup curve: `{cfg['warmup_iterations']}` retained iterations",
    f"- Steady samples: `{cfg['steady_samples']}` after warmup",
    "- Truffle compilation tracing: separate non-timing diagnostic runs only",
    "",
    "## Steady-state medians and pre/post ratios",
    "",
    "| Workload | Mode | Pre median ns | Post median ns | Pre/Post |",
    "|---|---|---:|---:|---:|",
]
for c in comparisons:
    ratio_value = c["pre_over_post_steady_ratio"]
    rendered_ratio = "n/a" if ratio_value is None else f"{ratio_value:.3f}"
    lines.append(
        f"| `{c['workload']}` | {c['mode']} | "
        f"{c['pre_steady_median_ns']} | {c['post_steady_median_ns']} | {rendered_ratio} |"
    )

lines += [
    "",
    "## Truffle diagnostics",
    "",
    "| Revision | Workload | rc | opt done | opt failed | GraphTooBig | Frame escape | Deep inlining | Stack overflow | Bootstrap error |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for d in diagnostics:
    lines.append(
        f"| {d['revision_label']} | `{d['workload']}` | {d['rc']} | "
        f"{d['opt_done']} | {d['opt_failed']} | {d['graph_too_big']} | "
        f"{d['frame_escape']} | {d['deep_inlining']} | {d['stack_overflow']} | "
        f"{d['bootstrap_error']} |"
    )

lines += [
    "",
    "Raw samples, per-class schema-compatible result JSON, environment/image identity,",
    "and diagnostic stdout/stderr are retained alongside this report.",
    "",
    "The pre/post ratios are intentionally scoped to each exact workload and runtime",
    "mode. They must not be generalized into a whole-language speed claim.",
]
(destination / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# Final exact metadata copy with harness SHA.
with (destination / "run-metadata.json").open("w", encoding="utf-8") as fh:
    json.dump(metadata, fh, indent=2)
    fh.write("\n")

print(f"FINALIZED_RESULTS={len(all_results)}")
print(f"HARNESS_REVISION={harness_sha}")
print("PERF001_D_FINALIZATION: PASS")
