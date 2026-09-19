# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
# THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
# "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf004b.json"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

def run(command: list[str], *, capture=False, check=True):
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )

def output(command: list[str]) -> str:
    p = run(command, capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed: " + " ".join(command)
            + "\nstdout:\n" + (p.stdout or "")[-5000:]
            + "\nstderr:\n" + (p.stderr or "")[-5000:]
        )
    return (p.stdout or "").strip()

def load() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))

def validate() -> dict[str, Any]:
    cfg = load()
    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF004"
    assert cfg["slice"] == "PERF004-B1"
    assert cfg["phase"] == "mechanism-profile-diagnostic-harness-ready"
    assert cfg["diagnostic_claim"] is False
    assert cfg["protos_revision"] == "4a03efc15620b37b2e418b3df30b4a26486446ec"
    assert cfg["baseline_evidence_revision"] == "5e8ff21f966c6c506652eef79c684d8b286bb546"
    assert cfg["baseline_harness_revision"] == "60dbce7faf5510bd1bd6867a866aa7ca69c48637"
    contract = cfg["measurement_contract"]
    assert contract == {
        "warmup_iterations": 20,
        "steady_iterations": 100,
        "execution_sample_period": "10 ms",
        "cpu_affinity": "one physical-core representative from current allowed cpuset",
        "network": "none",
        "jfr_diagnostics_outside_reference_timing": True,
        "startup_timing_not_measured": True,
    }
    assert len(cfg["workloads"]) == 9
    for item in cfg["workloads"]:
        assert item["source"].endswith(".protos")
    baseline = ROOT / "results/perf004-a/SHA256SUMS"
    if not baseline.is_file():
        raise RuntimeError("published PERF004-A evidence is missing")
    print("PERF004B1_CONFIG=PASS")
    print("PERF004B1_BASELINE_EVIDENCE=PASS")
    print("PERF004B1_PROTOS_MODIFICATION=NONE")
    print("PERF004B1_DIAGNOSTIC_CLAIM=NO")
    print(f"PERF004B1_WORKLOADS={len(cfg['workloads'])}")
    return cfg

def first_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^Cpus_allowed_list:\s*(.+)$", text, re.M)
    if not m:
        raise RuntimeError("cannot determine allowed CPU list")
    return m.group(1).split(",")[0].split("-")[0]

def image_tag(cfg):
    return "protos-benchmarks-perf004b1:" + cfg["protos_revision"][:12]

def build_image(cfg):
    tag = image_tag(cfg)
    run([
        "docker","build",
        "--build-arg","GRAAL_BASE="+cfg["toolchain"]["container_image"],
        "--build-arg","MAVEN_VERSION="+cfg["toolchain"]["maven_version"],
        "--build-arg","PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git",
        "--build-arg","PROTOS_REVISION="+cfg["protos_revision"],
        "-t",tag,"-f","docker/protos-perf006d3/Dockerfile","."
    ])
    return tag

def runtime_probe(tag, cpu):
    p=run([
        "docker","run","--rm","--network","none","--cpuset-cpus",cpu,
        "--entrypoint","java",tag,
        "--enable-native-access=ALL-UNNAMED",
        "-cp","/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf006dRuntimeProbe"
    ],capture=True,check=False)
    if p.returncode!=0:
        raise RuntimeError("runtime probe failed\n"+(p.stderr or "")[-4000:])
    observed=""
    for line in (p.stdout or "").splitlines():
        if line.startswith("PERF006D_RUNTIME="):
            observed=line.split("=",1)[1].strip()
    if observed!=EXPECTED_RUNTIME:
        raise RuntimeError(f"runtime mismatch: {observed!r}")
    return observed

def profile_one(tag, cpu, item, work):
    jfr_path = work / (item["id"].replace("/","__") + ".jfr")
    json_path = work / (item["id"].replace("/","__") + ".json")
    source = "/opt/perf006d3/corpus/" + item["source"]
    jfr_arg = (
        "-XX:StartFlightRecording="
        f"filename=/work/{jfr_path.name},"
        "settings=/opt/perf006d3/perf006d3.jfc,"
        "dumponexit=true"
    )
    p = run([
        "docker","run","--rm","--network","none","--cpuset-cpus",cpu,
        "--volume",f"{work.resolve()}:/work",
        "--entrypoint","java",tag,
        "-Xss128m",jfr_arg,
        "--enable-native-access=ALL-UNNAMED",
        "-cp","/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf006dPersistentDriver",
        source,item["expected"],"20","100"
    ],capture=True,check=False)
    if p.returncode!=0:
        raise RuntimeError(
            f"profile failed {item['id']}\nstdout:\n{(p.stdout or '')[-6000:]}\nstderr:\n{(p.stderr or '')[-6000:]}"
        )
    if not jfr_path.is_file() or jfr_path.stat().st_size<=0:
        raise RuntimeError("profile produced no JFR: "+item["id"])
    a = run([
        "docker","run","--rm","--network","none",
        "--volume",f"{work.resolve()}:/work",
        "--entrypoint","java",tag,
        "--add-modules","jdk.jfr",
        "-cp","/opt/perf006d3/analyzer",
        "Perf006d3JfrAnalyzer",
        "/work/"+jfr_path.name,
        "/work/"+json_path.name
    ],capture=True,check=False)
    if a.returncode!=0:
        raise RuntimeError(
            f"JFR analysis failed {item['id']}\nstdout:\n{(a.stdout or '')[-4000:]}\nstderr:\n{(a.stderr or '')[-4000:]}"
        )
    return json.loads(json_path.read_text(encoding="utf-8"))

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def host_inventory(cpu):
    return {
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "cpu_model": next(
            (
                line.split(":",1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text(encoding="utf-8",errors="replace").splitlines()
                if line.lower().startswith("model name") and ":" in line
            ),
            ""
        ),
        "cpu_count": os.cpu_count() or 1,
        "cpuset": cpu,
        "docker_server_version": output(["docker","version","--format","{{.Server.Version}}"]),
    }

def reference(output_dir: Path, harness_revision: str):
    cfg = validate()
    head = output(["git","rev-parse","HEAD"])
    if head != harness_revision:
        raise RuntimeError(f"exact harness required: HEAD={head} expected={harness_revision}")
    if output(["git","status","--porcelain","--untracked-files=all"]):
        raise RuntimeError("B1 reference requires a clean exact harness worktree")
    if output_dir.exists():
        raise RuntimeError("output already exists: "+str(output_dir))
    cpu=first_cpu()
    tag=build_image(cfg)
    runtime=runtime_probe(tag,cpu)
    with tempfile.TemporaryDirectory(prefix="perf004-b1-") as tmp:
        work=Path(tmp)
        profiles=[]
        for item in cfg["workloads"]:
            print(f"PROFILE BEGIN workload={item['id']}",flush=True)
            payload=profile_one(tag,cpu,item,work)
            payload["workload"]=item["id"]
            payload["expected"]=item["expected"]
            profiles.append(payload)
            print(
                f"PROFILE PASS workload={item['id']} "
                f"samples={payload['execution_samples']['total']}",
                flush=True,
            )
    output_dir.mkdir(parents=True)
    metadata={
        "schema_version":1,
        "perf_item":"PERF004",
        "slice":"PERF004-B1",
        "phase":"retained-mechanism-profile",
        "harness_revision":harness_revision,
        "protos_revision":cfg["protos_revision"],
        "baseline_evidence_revision":cfg["baseline_evidence_revision"],
        "protos_runtime":runtime,
        "host":host_inventory(cpu),
        "measurement_contract":cfg["measurement_contract"],
        "diagnostic_only":True,
        "timing_claim":False,
    }
    raw={"schema_version":1,"profiles":profiles}
    rows=[]
    for p in profiles:
        frames=p["execution_samples"]["top_frames"]
        top=frames[0] if frames else {"value":"<none>","count":0,"percent":0}
        rows.append((p["workload"],p["execution_samples"]["total"],top["value"],top["percent"],p["deoptimizations"]["jdk_total"],p["deoptimizations"]["truffle_total"]))
    (output_dir/"run-metadata.json").write_text(json.dumps(metadata,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (output_dir/"raw.json").write_text(json.dumps(raw,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    lines=[
        "# PERF004-B1 Protos mechanism profiles",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision: `{cfg['protos_revision']}`",
        f"- Baseline evidence revision: `{cfg['baseline_evidence_revision']}`",
        f"- Runtime: `{runtime}`",
        "- Diagnostic-only: yes",
        "- This report does not select an optimization and does not claim whole-language performance.",
        "",
        "| workload | execution samples | top frame | top-frame share | JDK deopts | Truffle deopts |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for workload,total,frame,pct,jd,td in rows:
        lines.append(f"| {workload} | {total} | `{frame}` | {pct:.3f}% | {jd} | {td} |")
    lines += [
        "",
        "The raw JFR-derived profiles in `raw.json` are authoritative for this diagnostic slice.",
        "Top-frame concentration is evidence of where sampled execution time was observed; it is not by itself proof of causality.",
        "PERF004-B must combine these profiles with the exact PERF004-A steady-state ratios and targeted counterfactual/contrast experiments before assigning a mechanism as causal.",
    ]
    (output_dir/"README.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    checks=["README.md","raw.json","run-metadata.json"]
    (output_dir/"SHA256SUMS").write_text(
        "\n".join(f"{sha256(output_dir/n)}  {n}" for n in checks)+"\n",
        encoding="utf-8",
    )
    print("PERF004B1_REFERENCE=PASS")
    print(f"PERF004B1_PROFILES={len(profiles)}")
    print("PERF004B1_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B1_PROTOS_REPOSITORY_TOUCHED=NO")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",choices=["validate","reference"])
    ap.add_argument("--harness-revision")
    ap.add_argument("--output-dir")
    args=ap.parse_args()
    if args.command=="validate":
        validate()
        return 0
    if not args.harness_revision or not args.output_dir:
        ap.error("reference requires --harness-revision and --output-dir")
    reference(Path(args.output_dir),args.harness_revision)

if __name__=="__main__":
    main()
