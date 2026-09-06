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
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)

def safe_id(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value)

def parse_samples(path, kind):
    values, observed = [], []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            fields=line.rstrip("\n").split("\t")
            if fields and fields[0] == kind:
                if len(fields) != 4:
                    raise RuntimeError(f"malformed sample in {path}: {line!r}")
                values.append(int(fields[2]))
                observed.append(fields[3])
    return values, observed

def stats(values):
    if not values:
        raise RuntimeError("empty samples")
    ordered=sorted(values)
    med=statistics.median(values)
    return {
        "count":len(values),
        "median_ns":med,
        "mad_ns":statistics.median(abs(x-med) for x in values),
        "min_ns":min(values),
        "max_ns":max(values),
        "p95_ns":ordered[max(0, math.ceil(len(ordered)*0.95)-1)],
    }

if len(sys.argv) != 5:
    raise SystemExit("usage: perf001e_finalize.py <repo-root> <run-dir> <destination> <harness-sha>")

root=Path(sys.argv[1]).resolve()
run=Path(sys.argv[2]).resolve()
dest=Path(sys.argv[3]).resolve()
harness=sys.argv[4]
if not SHA_RE.fullmatch(harness):
    raise SystemExit("harness SHA must be exact lowercase 40-character hex")

cfg=load(root/"config/perf001e.json")
metadata=load(run/"run-metadata.json")
metadata["harness_revision"]=harness

if dest.exists():
    shutil.rmtree(dest)
(dest/"raw").mkdir(parents=True)
(dest/"diagnostics").mkdir(parents=True)
(dest/"results").mkdir(parents=True)

for path in (run/"raw").iterdir():
    if path.is_file():
        shutil.copy2(path, dest/"raw"/path.name)
for path in (run/"diagnostics").iterdir():
    if path.is_file():
        shutil.copy2(path, dest/"diagnostics"/path.name)
with (dest/"run-metadata.json").open("w",encoding="utf-8") as fh:
    json.dump(metadata,fh,indent=2); fh.write("\n")

runtime_meta=metadata["runtime"]
env=metadata["environment"]
rows=[]
all_results=[]

for workload in cfg["workloads"]:
    key=workload["id"]
    safe=safe_id(key)
    expected=str(workload["expected"])
    for language in cfg["languages"]:
        startup, startup_obs=parse_samples(run/"raw"/f"startup-{language}-{safe}.tsv","STARTUP")
        warmup, warmup_obs=parse_samples(run/"raw"/f"execution-{language}-{safe}.tsv","WARMUP")
        steady, steady_obs=parse_samples(run/"raw"/f"execution-{language}-{safe}.tsv","STEADY")
        if len(startup) != cfg["startup_samples"]:
            raise RuntimeError(f"startup count mismatch {language}/{key}")
        if len(warmup) != cfg["warmup_iterations"]:
            raise RuntimeError(f"warmup count mismatch {language}/{key}")
        if len(steady) != cfg["steady_samples"]:
            raise RuntimeError(f"steady count mismatch {language}/{key}")
        if any(x != expected for x in startup_obs+warmup_obs+steady_obs):
            raise RuntimeError(f"retained result mismatch {language}/{key}")

        image_key = {"protos":"protos","python":"python","javascript":"javascript"}[language]
        image = runtime_meta[image_key]["image"]
        image_fields = {
            "image_tag": image["tag"],
            "image_id": image["id"],
            "image_repo_digests": image["repo_digests"],
        }
        if language == "protos":
            runtime={
                "name":"Protos-Truffle",
                "version":cfg["protos_implementation_version"],
                "jdk_version":"GraalVM Community JDK 22.0.0",
                "graal_truffle_line":cfg["truffle_runtime_version"],
                "stack":cfg["protos_stack"],
                **image_fields,
            }
        elif language == "python":
            runtime={"name":"Python","version":cfg["python_version"],**image_fields}
        else:
            runtime={"name":"Node.js","version":cfg["node_version"],
                     "stack_kb":cfg["node_stack_kb"],**image_fields}

        class_values=[
            ("startup", startup, 0),
            ("warmup", warmup, 0),
            ("steady_state", steady, cfg["warmup_iterations"]),
        ]
        class_stats={}
        for cls, values, warm_count in class_values:
            result={
                "schema_version":1,
                "protos_revision":cfg["protos_revision"],
                "harness_revision":harness,
                "workload":key,
                "runtime":runtime,
                "environment":{
                    "platform":env["platform"],"architecture":env["architecture"],
                    "cpu_model":env["cpu_model"],"cpu_count":env["cpu_count"],
                    "memory_bytes":env["memory_bytes"],"kernel":env["kernel"],
                    "cpuset":env["cpuset"],"docker_server_version":env["docker_server_version"],
                },
                "measurement":{
                    "class":cls,
                    "warmup_iterations":warm_count,
                    "samples_ns":values,
                    "aggregation":"median primary; MAD, min, max and nearest-rank p95 secondary; raw samples retained",
                },
                "perf001e":{
                    "language":language,
                    "expected_stdout":expected,
                    "algorithm_equivalent":True,
                    "work_shape":workload["shape"],
                    "network":"disabled",
                    "timing_instrumentation":"Truffle TraceCompilation disabled for all timing samples" if language=="protos" else "none",
                },
            }
            filename=f"{language}__{safe}__{cls}.json"
            with (dest/"results"/filename).open("w",encoding="utf-8") as fh:
                json.dump(result,fh,indent=2); fh.write("\n")
            all_results.append(result)
            class_stats[cls]=stats(values)

        rows.append({
            "language":language,
            "workload":key,
            "startup_median_ns":class_stats["startup"]["median_ns"],
            "startup_mad_ns":class_stats["startup"]["mad_ns"],
            "warmup_first5_median_ns":statistics.median(warmup[:5]),
            "warmup_last5_median_ns":statistics.median(warmup[-5:]),
            "steady_median_ns":class_stats["steady_state"]["median_ns"],
            "steady_mad_ns":class_stats["steady_state"]["mad_ns"],
            "steady_p95_ns":class_stats["steady_state"]["p95_ns"],
        })

diag=[]
with (run/"diagnostics"/"summary.tsv").open("r",encoding="utf-8") as fh:
    header=fh.readline().rstrip("\n").split("\t")
    for line in fh:
        values=line.rstrip("\n").split("\t")
        item=dict(zip(header,values))
        for field in ("rc","opt_done","opt_failed","graph_too_big","frame_escape","deep_inlining","stack_overflow","bootstrap_error"):
            item[field]=int(item[field])
        diag.append(item)
if len(diag) != len(cfg["workloads"]):
    raise RuntimeError("diagnostic row count mismatch")
for item in diag:
    if item["rc"] != 0:
        raise RuntimeError(f"diagnostic execution failed {item['workload']} rc={item['rc']}")

finding_fields=(
    "opt_failed","graph_too_big","frame_escape",
    "deep_inlining","stack_overflow","bootstrap_error",
)
optimization_findings=[
    {
        "workload": item["workload"],
        **{field:item[field] for field in finding_fields if item[field] != 0},
    }
    for item in diag
    if any(item[field] != 0 for field in finding_fields)
]

fields=[
    "language","workload","startup_median_ns","startup_mad_ns",
    "warmup_first5_median_ns","warmup_last5_median_ns",
    "steady_median_ns","steady_mad_ns","steady_p95_ns",
]
with (dest/"summary.tsv").open("w",encoding="utf-8") as fh:
    fh.write("\t".join(fields)+"\n")
    for row in rows:
        fh.write("\t".join(str(row[x]) for x in fields)+"\n")

row_index={(r["language"],r["workload"]):r for r in rows}
comparisons=[]
for workload in cfg["workloads"]:
    key=workload["id"]
    p=row_index[("protos",key)]
    py=row_index[("python",key)]
    js=row_index[("javascript",key)]
    comparisons.append({
        "workload":key,
        "protos_steady_median_ns":p["steady_median_ns"],
        "python_steady_median_ns":py["steady_median_ns"],
        "javascript_steady_median_ns":js["steady_median_ns"],
        "protos_over_python_steady_ratio":p["steady_median_ns"]/py["steady_median_ns"] if py["steady_median_ns"] else None,
        "protos_over_javascript_steady_ratio":p["steady_median_ns"]/js["steady_median_ns"] if js["steady_median_ns"] else None,
    })

evidence={
    "schema_version":1,
    "perf_item":"PERF001",
    "slice":"PERF001-E",
    "status":"PUBLISHED_AWAITING_PROTOS_LEDGER",
    "harness_revision":harness,
    "protos_revision":cfg["protos_revision"],
    "correctness_gate":"PASS",
    "correctness_case_count":len(cfg["workloads"])*len(cfg["languages"]),
    "measurement_classes":["startup","warmup","steady_state"],
    "languages":cfg["languages"],
    "workload_count":len(cfg["workloads"]),
    "raw_result_count":len(all_results),
    "diagnostics":diag,
    "optimization_findings":optimization_findings,
    "optimization_finding_count":len(optimization_findings),
    "diagnostic_policy":"Compiler bailouts with rc=0 are retained PERF001 baseline findings; they do not invalidate correctness-gated timings.",
    "comparisons":comparisons,
    "environment":env,
    "runtime":runtime_meta,
    "interpretation":"Per-workload observations only; no whole-language performance claim.",
}
with (dest/"evidence.json").open("w",encoding="utf-8") as fh:
    json.dump(evidence,fh,indent=2); fh.write("\n")

lines=[
    "# PERF001-E collection benchmark evidence",
    "",
    f"- Protos revision: `{cfg['protos_revision']}`",
    f"- Harness revision: `{harness}`",
    "- Correctness: PASS 18/18 (6 workloads × Protos/Python/JavaScript)",
    f"- Startup: {cfg['startup_samples']} fresh-process samples per language/workload",
    f"- Warmup: {cfg['warmup_iterations']} retained same-process iterations",
    f"- Steady state: {cfg['steady_samples']} retained samples after warmup",
    f"- Protos: GraalVM Community JDK 22 + external Truffle {cfg['truffle_runtime_version']} + `-Xss{cfg['protos_stack']}`",
    f"- Python: {cfg['python_version']}",
    f"- JavaScript: Node.js {cfg['node_version']}",
    f"- CPU set: `{env['cpuset']}`; runtime networking disabled",
    "- Protos compilation diagnostics are separate from timing.",
    f"- Optimization findings: {len(optimization_findings)} workload(s); compiler bailouts with correct execution are retained as baseline evidence rather than hidden or treated as correctness failures.",
    "",
    "## Truffle diagnostic observations",
    "",
    "| Workload | rc | opt done | opt failed | GraphTooBig | FrameWithoutBoxing | Deep inlining | Stack overflow | Bootstrap error |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for item in diag:
    lines.append(
        f"| `{item['workload']}` | {item['rc']} | {item['opt_done']} | {item['opt_failed']} | "
        f"{item['graph_too_big']} | {item['frame_escape']} | {item['deep_inlining']} | "
        f"{item['stack_overflow']} | {item['bootstrap_error']} |"
    )
lines += [
    "",
    "A non-zero compiler-bailout count with `rc=0` is a performance finding, not a failed correctness case.",
    "",
    "## Steady-state medians",
    "",
    "| Workload | Protos ns | Python ns | JavaScript ns |",
    "|---|---:|---:|---:|",
]
for w in cfg["workloads"]:
    key=w["id"]
    lines.append(
        f"| `{key}` | {row_index[('protos',key)]['steady_median_ns']} | "
        f"{row_index[('python',key)]['steady_median_ns']} | "
        f"{row_index[('javascript',key)]['steady_median_ns']} |"
    )
lines += [
    "",
    "These are observations for the exact pinned revisions/runtime identities only.",
    "No row is generalized into a claim that one whole language is faster than another.",
]
(dest/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

print("PERF001E_FINALIZATION: PASS")
print(f"RESULT_JSON_COUNT: {len(all_results)}")
print(f"DIAGNOSTIC_ROW_COUNT: {len(diag)}")
print(f"OPTIMIZATION_FINDING_COUNT: {len(optimization_findings)}")
print(f"CORRECTNESS_CASE_COUNT: {len(cfg['workloads'])*len(cfg['languages'])}")
