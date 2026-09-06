#!/usr/bin/env bash
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


set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT=${1:-}
[ -n "$OUT" ] || { echo "usage: scripts/perf001e_measure.sh <output-dir>" >&2; exit 2; }

CONFIG="$ROOT/config/perf001e.json"
rm -rf "$OUT"
mkdir -p "$OUT/raw" "$OUT/diagnostics"

command -v docker >/dev/null 2>&1 || {
  echo "ENVIRONMENT_LIMITATION: docker is required for PERF001-E" >&2
  exit 3
}
command -v python3 >/dev/null 2>&1 || {
  echo "ENVIRONMENT_LIMITATION: python3 is required for PERF001-E" >&2
  exit 3
}

eval "$(
python3 - "$CONFIG" <<'PY'
import json, shlex, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
pairs={
  "PROTOS_REVISION":cfg["protos_revision"],
  "BUILD_BASE":cfg["build_base"],
  "GRAAL_BASE":cfg["graal_base"],
  "TRUFFLE_VERSION":cfg["truffle_runtime_version"],
  "STACK":cfg["protos_stack"],
  "PYTHON_BASE":cfg["python_base"],
  "NODE_BASE":cfg["node_base"],
  "NODE_STACK_KB":str(cfg["node_stack_kb"]),
  "STARTUP_SAMPLES":str(cfg["startup_samples"]),
  "WARMUP_ITERATIONS":str(cfg["warmup_iterations"]),
  "STEADY_SAMPLES":str(cfg["steady_samples"]),
  "DIAGNOSTIC_ITERATIONS":str(cfg["diagnostic_iterations"]),
}
for k,v in pairs.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"

CPUSET=$(
python3 - <<'PY'
import re
text=open('/proc/self/status', encoding='utf-8').read()
m=re.search(r'^Cpus_allowed_list:\s*(.+)$', text, re.M)
if not m:
    raise SystemExit("cannot determine allowed CPU list")
first=m.group(1).strip().split(',')[0].split('-')[0]
print(first)
PY
)

echo "PERF001-E cross-language measurement"
echo "PROTOS_REVISION=$PROTOS_REVISION"
echo "CPUSET=$CPUSET"
echo "STARTUP_SAMPLES=$STARTUP_SAMPLES"
echo "WARMUP_ITERATIONS=$WARMUP_ITERATIONS"
echo "STEADY_SAMPLES=$STEADY_SAMPLES"
echo "DIAGNOSTIC_ITERATIONS=$DIAGNOSTIC_ITERATIONS"

docker pull "$BUILD_BASE" >/dev/null
docker pull "$GRAAL_BASE" >/dev/null
docker pull "$PYTHON_BASE" >/dev/null
docker pull "$NODE_BASE" >/dev/null

PROTOS_IMAGE="protos-benchmarks-perf001e-protos:${PROTOS_REVISION:0:12}"
PYTHON_IMAGE="protos-benchmarks-perf001e-python:${PROTOS_REVISION:0:12}"
NODE_IMAGE="protos-benchmarks-perf001e-node:${PROTOS_REVISION:0:12}"

echo "phase=build exact runtime images"
docker build \
  --build-arg BUILD_BASE="$BUILD_BASE" \
  --build-arg GRAAL_BASE="$GRAAL_BASE" \
  --build-arg PROTOS_REVISION="$PROTOS_REVISION" \
  --build-arg TRUFFLE_RUNTIME_VERSION="$TRUFFLE_VERSION" \
  -t "$PROTOS_IMAGE" \
  -f "$ROOT/docker/protos-perf001e/Dockerfile" \
  "$ROOT/docker/protos-perf001e" \
  >"$OUT/raw/build-protos.stdout" 2>"$OUT/raw/build-protos.stderr"

docker build \
  --build-arg PYTHON_BASE="$PYTHON_BASE" \
  -t "$PYTHON_IMAGE" \
  -f "$ROOT/docker/python-perf001e/Dockerfile" \
  "$ROOT" \
  >"$OUT/raw/build-python.stdout" 2>"$OUT/raw/build-python.stderr"

docker build \
  --build-arg NODE_BASE="$NODE_BASE" \
  -t "$NODE_IMAGE" \
  -f "$ROOT/docker/node-perf001e/Dockerfile" \
  "$ROOT" \
  >"$OUT/raw/build-javascript.stdout" 2>"$OUT/raw/build-javascript.stderr"

runtime_class=$(
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" \
    --enable-native-access=ALL-UNNAMED \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.RuntimeProbe
)
printf '%s\n' "$runtime_class" >"$OUT/raw/protos-runtime-class.txt"
case "$runtime_class" in
  *HotSpotTruffleRuntime*) ;;
  *) echo "OPTIMIZING_RUNTIME_CHECK: FAIL class=$runtime_class" >&2; exit 10 ;;
esac
echo "OPTIMIZING_RUNTIME_CHECK: PASS class=$runtime_class"

docker run --rm --network none --cpuset-cpus "$CPUSET" --entrypoint java "$PROTOS_IMAGE" -version \
  >"$OUT/raw/java-version.stdout" 2>"$OUT/raw/java-version.stderr"
docker run --rm --network none --cpuset-cpus "$CPUSET" "$PYTHON_IMAGE" --version \
  >"$OUT/raw/python-version.stdout" 2>"$OUT/raw/python-version.stderr"
docker run --rm --network none --cpuset-cpus "$CPUSET" "$NODE_IMAGE" --version \
  >"$OUT/raw/node-version.stdout" 2>"$OUT/raw/node-version.stderr"
docker --version >"$OUT/raw/docker-version.txt"

protos_props=(
  '-Dpolyglot.engine.AllowExperimentalOptions=true'
  '-Dpolyglot.engine.BackgroundCompilation=false'
)

run_protos_correctness() {
  local key=$1 source=$2 expected=$3 safe=${key//\//__}
  local stdout="$OUT/raw/correctness-protos-${safe}.stdout"
  local stderr="$OUT/raw/correctness-protos-${safe}.stderr"
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" \
    "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
    "${protos_props[@]}" \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.DiagnosticEval \
    "/opt/protos/$source" >"$stdout" 2>"$stderr"
  rc=$?
  set -e
  actual=$(awk 'NF {x=$0} END {print x}' "$stdout")
  [ "$rc" -eq 0 ] && [ "$actual" = "$expected" ] || {
    echo "CORRECTNESS: FAIL language=protos workload=$key rc=$rc expected=$expected actual=${actual:-<empty>}" >&2
    tail -100 "$stderr" >&2 || true
    exit 20
  }
  echo "CORRECTNESS language=protos workload=$key PASS"
}

run_host_correctness() {
  local language=$1 image=$2 source=$3 expected=$4 key=$5 safe=${key//\//__}
  local stdout="$OUT/raw/correctness-${language}-${safe}.stdout"
  local stderr="$OUT/raw/correctness-${language}-${safe}.stderr"
  local runtime_path
  if [ "$language" = "python" ]; then
    runtime_path="/opt/benchmark/workloads/${source#workloads/python/}"
  else
    runtime_path="/opt/benchmark/workloads/${source#workloads/javascript/}"
  fi
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" "$image" \
    "$runtime_path" >"$stdout" 2>"$stderr"
  rc=$?
  set -e
  actual=$(awk 'NF {x=$0} END {print x}' "$stdout")
  [ "$rc" -eq 0 ] && [ "$actual" = "$expected" ] || {
    echo "CORRECTNESS: FAIL language=$language workload=$key rc=$rc expected=$expected actual=${actual:-<empty>}" >&2
    tail -100 "$stderr" >&2 || true
    exit 20
  }
  echo "CORRECTNESS language=$language workload=$key PASS"
}

workload_rows() {
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
for w in cfg["workloads"]:
    print("\t".join([w["id"], w["protos"], w["py"], w["js"], str(w["expected"])]))
PY
}

echo "phase=correctness 18/18"
while IFS=$'\t' read -r key protos_source py_source js_source expected; do
  run_protos_correctness "$key" "$protos_source" "$expected"
  run_host_correctness python "$PYTHON_IMAGE" "$py_source" "$expected" "$key"
  run_host_correctness javascript "$NODE_IMAGE" "$js_source" "$expected" "$key"
done < <(workload_rows)
echo "CROSS_LANGUAGE_CORRECTNESS: PASS 18/18"

run_protos_startup() {
  local key=$1 source=$2 expected=$3 safe=${key//\//__}
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" \
    "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.StartupDriver \
    "/opt/protos/$source" "$expected" "$STARTUP_SAMPLES" "$STACK" \
    >"$OUT/raw/startup-protos-${safe}.tsv" \
    2>"$OUT/raw/startup-protos-${safe}.stderr"
}

run_protos_execution() {
  local key=$1 source=$2 expected=$3 safe=${key//\//__}
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" \
    "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
    "${protos_props[@]}" \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.MeasurementDriver \
    "/opt/protos/$source" "$expected" "$WARMUP_ITERATIONS" "$STEADY_SAMPLES" \
    >"$OUT/raw/execution-protos-${safe}.tsv" \
    2>"$OUT/raw/execution-protos-${safe}.stderr"
}

run_host_startup() {
  local language=$1 image=$2 source=$3 expected=$4 key=$5 safe=${key//\//__}
  local runtime_path driver
  if [ "$language" = "python" ]; then
    runtime_path="/opt/benchmark/workloads/${source#workloads/python/}"
    driver="/opt/benchmark/timing_driver.py"
  else
    runtime_path="/opt/benchmark/workloads/${source#workloads/javascript/}"
    driver="/opt/benchmark/timing_driver.mjs"
  fi
  docker run --rm --network none --cpuset-cpus "$CPUSET" "$image" \
    "$driver" startup "$runtime_path" "$expected" "$STARTUP_SAMPLES" \
    >"$OUT/raw/startup-${language}-${safe}.tsv" \
    2>"$OUT/raw/startup-${language}-${safe}.stderr"
}

run_host_execution() {
  local language=$1 image=$2 source=$3 expected=$4 key=$5 safe=${key//\//__}
  local runtime_path driver
  if [ "$language" = "python" ]; then
    runtime_path="/opt/benchmark/workloads/${source#workloads/python/}"
    driver="/opt/benchmark/timing_driver.py"
  else
    runtime_path="/opt/benchmark/workloads/${source#workloads/javascript/}"
    driver="/opt/benchmark/timing_driver.mjs"
  fi
  docker run --rm --network none --cpuset-cpus "$CPUSET" "$image" \
    "$driver" execution "$runtime_path" "$expected" "$WARMUP_ITERATIONS" "$STEADY_SAMPLES" \
    >"$OUT/raw/execution-${language}-${safe}.tsv" \
    2>"$OUT/raw/execution-${language}-${safe}.stderr"
}

echo "phase=measurement startup/warmup/steady"
while IFS=$'\t' read -r key protos_source py_source js_source expected; do
  echo "WORKLOAD $key"
  run_protos_startup "$key" "$protos_source" "$expected"
  run_protos_execution "$key" "$protos_source" "$expected"
  run_host_startup python "$PYTHON_IMAGE" "$py_source" "$expected" "$key"
  run_host_execution python "$PYTHON_IMAGE" "$py_source" "$expected" "$key"
  run_host_startup javascript "$NODE_IMAGE" "$js_source" "$expected" "$key"
  run_host_execution javascript "$NODE_IMAGE" "$js_source" "$expected" "$key"

  for language in protos python javascript; do
    safe=${key//\//__}
    startup_count=$(awk -F '\t' '$1=="STARTUP"{c++} END{print c+0}' "$OUT/raw/startup-${language}-${safe}.tsv")
    warm_count=$(awk -F '\t' '$1=="WARMUP"{c++} END{print c+0}' "$OUT/raw/execution-${language}-${safe}.tsv")
    steady_count=$(awk -F '\t' '$1=="STEADY"{c++} END{print c+0}' "$OUT/raw/execution-${language}-${safe}.tsv")
    [ "$startup_count" -eq "$STARTUP_SAMPLES" ] || exit 30
    [ "$warm_count" -eq "$WARMUP_ITERATIONS" ] || exit 31
    [ "$steady_count" -eq "$STEADY_SAMPLES" ] || exit 32
  done
done < <(workload_rows)
echo "STARTUP_MEASUREMENTS: PASS"
echo "WARMUP_CURVES: PASS"
echo "STEADY_STATE_MEASUREMENTS: PASS"

echo "phase=separate non-timing Protos Truffle diagnostics"
printf 'workload\trc\topt_done\topt_failed\tgraph_too_big\tframe_escape\tdeep_inlining\tstack_overflow\tbootstrap_error\n' \
  >"$OUT/diagnostics/summary.tsv"

while IFS=$'\t' read -r key protos_source py_source js_source expected; do
  safe=${key//\//__}
  stdout="$OUT/diagnostics/${safe}.stdout"
  stderr="$OUT/diagnostics/${safe}.stderr"
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" \
    "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
    -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false \
    -Dpolyglot.engine.TraceCompilation=true \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.MeasurementDriver \
    "/opt/protos/$protos_source" "$expected" "$DIAGNOSTIC_ITERATIONS" 0 \
    >"$stdout" 2>"$stderr"
  rc=$?
  set -e
  opt_done=$(grep -ci 'opt done' "$stderr" || true)
  opt_failed=$(grep -ci 'opt failed' "$stderr" || true)
  graph=$(grep -ci 'GraphTooBig' "$stderr" || true)
  frame=$(grep -ci 'FrameWithoutBoxing' "$stderr" || true)
  deep=$(grep -ci 'Too deep inlining' "$stderr" || true)
  overflow=$(grep -ci 'StackOverflowError' "$stderr" || true)
  bootstrap=$(grep -ci 'BootstrapMethodError' "$stderr" || true)
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$key" "$rc" "$opt_done" "$opt_failed" "$graph" "$frame" "$deep" "$overflow" "$bootstrap" \
    >>"$OUT/diagnostics/summary.tsv"
  echo "DIAGNOSTIC workload=$key rc=$rc opt_done=$opt_done opt_failed=$opt_failed graph_too_big=$graph frame_escape=$frame deep_inlining=$deep stack_overflow=$overflow bootstrap_error=$bootstrap"
  if [ "$rc" -ne 0 ]; then
    tail -100 "$stderr" >&2 || true
    echo "TRUFFLE_DIAGNOSTIC_EXECUTION: FAIL workload=$key rc=$rc" >&2
    exit 40
  fi
done < <(workload_rows)
echo "TRUFFLE_DIAGNOSTICS: RETAINED 6/6"
echo "TRUFFLE_DIAGNOSTIC_POLICY: compiler bailouts are PERF baseline findings, not correctness failures"

docker image inspect "$PROTOS_IMAGE" >"$OUT/raw/image-protos.json"
docker image inspect "$PYTHON_IMAGE" >"$OUT/raw/image-python.json"
docker image inspect "$NODE_IMAGE" >"$OUT/raw/image-javascript.json"

python3 - "$CONFIG" "$OUT" "$CPUSET" "$PROTOS_IMAGE" "$PYTHON_IMAGE" "$NODE_IMAGE" <<'PY'
import json, os, platform, re, subprocess, sys
from pathlib import Path
cfg_path,out_path,cpuset,*tags=sys.argv[1:]
cfg=json.load(open(cfg_path, encoding='utf-8'))
out=Path(out_path)

def inspect(name):
    data=json.load(open(out/"raw"/f"image-{name}.json", encoding='utf-8'))[0]
    return {"tag": tags[{"protos":0,"python":1,"javascript":2}[name]],
            "id":data.get("Id"), "repo_digests":data.get("RepoDigests") or []}

cpu_model=""
try:
    for line in open("/proc/cpuinfo", encoding="utf-8", errors="replace"):
        if line.lower().startswith("model name"):
            cpu_model=line.split(":",1)[1].strip(); break
except OSError:
    pass
mem=0
try:
    for line in open("/proc/meminfo", encoding="utf-8"):
        if line.startswith("MemTotal:"):
            mem=int(line.split()[1])*1024; break
except OSError:
    pass
allowed=""
try:
    text=open("/proc/self/status", encoding="utf-8").read()
    m=re.search(r'^Cpus_allowed_list:\s*(.+)$', text, re.M)
    allowed=m.group(1).strip() if m else ""
except OSError:
    pass
docker_version=subprocess.check_output(["docker","version","--format","{{.Server.Version}}"], text=True).strip()

metadata={
 "schema_version":1,
 "perf_item":"PERF001",
 "slice":"PERF001-E",
 "generated_at":subprocess.check_output(["date","-u","+%Y-%m-%dT%H:%M:%SZ"], text=True).strip(),
 "harness_revision":None,
 "protos_revision":cfg["protos_revision"],
 "measurement_policy":{
   "startup_samples":cfg["startup_samples"],
   "warmup_iterations":cfg["warmup_iterations"],
   "steady_samples":cfg["steady_samples"],
   "diagnostic_iterations":cfg["diagnostic_iterations"],
   "protos_stack":cfg["protos_stack"],
   "node_stack_kb":cfg["node_stack_kb"],
   "cpuset":cpuset,
   "network":"disabled",
 },
 "runtime":{
   "protos":{"version":cfg["protos_implementation_version"],"graal_base":cfg["graal_base"],
             "truffle_runtime_version":cfg["truffle_runtime_version"],"image":inspect("protos")},
   "python":{"version":cfg["python_version"],"base":cfg["python_base"],"image":inspect("python")},
   "javascript":{"runtime":"Node.js","version":cfg["node_version"],"base":cfg["node_base"],"image":inspect("javascript")},
 },
 "environment":{
   "platform":platform.system().lower(),
   "architecture":platform.machine(),
   "kernel":platform.release(),
   "cpu_model":cpu_model,
   "cpu_count":os.cpu_count(),
   "memory_bytes":mem,
   "cpus_allowed_list":allowed,
   "cpuset":cpuset,
   "docker_server_version":docker_version,
 }
}
with open(out/"run-metadata.json","w",encoding="utf-8") as fh:
    json.dump(metadata,fh,indent=2); fh.write("\n")
PY

echo "PERF001E_MEASUREMENT: PASS"
