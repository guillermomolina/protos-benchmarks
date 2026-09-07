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
[ -n "$OUT" ] || { echo "usage: scripts/perf003a_diagnostic.sh <output-dir>" >&2; exit 2; }
CONFIG="$ROOT/config/perf003a.json"

command -v docker >/dev/null 2>&1 || { echo "ENVIRONMENT_LIMITATION: docker is required for PERF003-A external diagnostics" >&2; exit 3; }
command -v python3 >/dev/null 2>&1 || { echo "ENVIRONMENT_LIMITATION: python3 is required for PERF003-A external diagnostics" >&2; exit 3; }

[ ! -e "$OUT" ] || { echo "OUTPUT_PRECONDITION: output path already exists: $OUT" >&2; exit 4; }
mkdir -p "$OUT/raw" "$OUT/diagnostics"

eval "$(
python3 - "$CONFIG" <<'PY'
import json, shlex, sys
cfg=json.load(open(sys.argv[1], encoding="utf-8"))
for key, value in {
    "PROTOS_REVISION": cfg["protos_revision"],
    "PROTOS_VERSION": cfg["protos_implementation_version"],
    "BUILD_BASE": cfg["build_base"],
    "GRAAL_BASE": cfg["graal_base"],
    "TRUFFLE_VERSION": cfg["truffle_runtime_version"],
    "STACK": cfg["protos_stack"],
    "DIAGNOSTIC_ITERATIONS": str(cfg["diagnostic_iterations"]),
}.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

HARNESS_REVISION=$(git -C "$ROOT" rev-parse HEAD)
[ "${#HARNESS_REVISION}" -eq 40 ] || { echo "HARNESS_IDENTITY_CHECK: FAIL revision=$HARNESS_REVISION" >&2; exit 5; }

CPUSET=$(
python3 - <<'PY'
import re
text=open("/proc/self/status", encoding="utf-8").read()
m=re.search(r"^Cpus_allowed_list:\s*(.+)$", text, re.M)
if not m:
    raise SystemExit("cannot determine allowed CPU list")
print(m.group(1).strip().split(",")[0].split("-")[0])
PY
)

echo "PERF003-A external compilability diagnostic"
echo "HARNESS_REVISION=$HARNESS_REVISION"
echo "PROTOS_REVISION=$PROTOS_REVISION"
echo "PROTOS_VERSION=$PROTOS_VERSION"
echo "CPUSET=$CPUSET"
echo "DIAGNOSTIC_ITERATIONS=$DIAGNOSTIC_ITERATIONS"

docker pull "$BUILD_BASE" >/dev/null
docker pull "$GRAAL_BASE" >/dev/null

PROTOS_IMAGE="protos-benchmarks-perf003a-protos:${PROTOS_REVISION:0:12}"

echo "phase=build exact Protos diagnostic image"
docker build \
  --build-arg BUILD_BASE="$BUILD_BASE" \
  --build-arg GRAAL_BASE="$GRAAL_BASE" \
  --build-arg PROTOS_REVISION="$PROTOS_REVISION" \
  --build-arg TRUFFLE_RUNTIME_VERSION="$TRUFFLE_VERSION" \
  -t "$PROTOS_IMAGE" \
  -f "$ROOT/docker/protos-perf001e/Dockerfile" \
  "$ROOT/docker/protos-perf001e" \
  >"$OUT/raw/build-protos.stdout" 2>"$OUT/raw/build-protos.stderr"

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

docker run --rm --network none --cpuset-cpus "$CPUSET" \
  --entrypoint java "$PROTOS_IMAGE" -version \
  >"$OUT/raw/java-version.stdout" 2>"$OUT/raw/java-version.stderr"
docker --version >"$OUT/raw/docker-version.txt"
docker image inspect "$PROTOS_IMAGE" >"$OUT/raw/image-protos.json"

workload_rows() {
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding="utf-8"))
for w in cfg["workloads"]:
    print("\t".join((w["id"], w["protos"], str(w["expected"]))))
PY
}

run_correctness() {
  local mode=$1 key=$2 source=$3 expected=$4 safe=${key//\//__}
  local stdout="$OUT/raw/correctness-${mode}-${safe}.stdout"
  local stderr="$OUT/raw/correctness-${mode}-${safe}.stderr"
  local props=(
    '-Dpolyglot.engine.AllowExperimentalOptions=true'
    '-Dpolyglot.engine.BackgroundCompilation=false'
  )
  if [ "$mode" = "interpreter" ]; then
    props+=('-Dpolyglot.engine.Compilation=false')
  fi

  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" \
    "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
    "${props[@]}" \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.DiagnosticEval \
    "/opt/protos/$source" >"$stdout" 2>"$stderr"
  local rc=$?
  set -e

  local actual
  actual=$(awk 'NF {x=$0} END {print x}' "$stdout")
  if [ "$rc" -ne 0 ] || [ "$actual" != "$expected" ]; then
    echo "CORRECTNESS: FAIL mode=$mode workload=$key rc=$rc expected=$expected actual=${actual:-<empty>}" >&2
    tail -100 "$stderr" >&2 || true
    exit 20
  fi
  echo "CORRECTNESS mode=$mode workload=$key PASS result=$actual"
}

echo "phase=correctness interpreter + optimizing runtime"
while IFS=$'\t' read -r key source expected; do
  run_correctness interpreter "$key" "$source" "$expected"
  run_correctness truffle "$key" "$source" "$expected"
done < <(workload_rows)
echo "PERF003A_CORRECTNESS: PASS"

echo "phase=separate non-timing TraceCompilation diagnostics"
printf 'workload\trc\topt_done\topt_failed\tgraph_too_big\tframe_escape\tdeep_inlining\tstack_overflow\tbootstrap_error\tgate\n' \
  >"$OUT/diagnostics/summary.tsv"

overall=PASS
while IFS=$'\t' read -r key source expected; do
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
    "/opt/protos/$source" "$expected" "$DIAGNOSTIC_ITERATIONS" 0 \
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

  gate=PASS
  if [ "$rc" -ne 0 ] || [ "$opt_failed" -ne 0 ] || [ "$graph" -ne 0 ] || \
     [ "$frame" -ne 0 ] || [ "$deep" -ne 0 ] || [ "$overflow" -ne 0 ] || \
     [ "$bootstrap" -ne 0 ]; then
    gate=BLOCKED
    overall=BLOCKED
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$key" "$rc" "$opt_done" "$opt_failed" "$graph" "$frame" "$deep" "$overflow" "$bootstrap" "$gate" \
    >>"$OUT/diagnostics/summary.tsv"

  echo "DIAGNOSTIC workload=$key rc=$rc opt_done=$opt_done opt_failed=$opt_failed graph_too_big=$graph frame_escape=$frame deep_inlining=$deep stack_overflow=$overflow bootstrap_error=$bootstrap gate=$gate"

  if [ "$rc" -ne 0 ]; then
    tail -100 "$stderr" >&2 || true
    echo "TRUFFLE_DIAGNOSTIC_EXECUTION: FAIL workload=$key rc=$rc" >&2
    exit 30
  fi
done < <(workload_rows)

python3 - "$CONFIG" "$OUT" "$CPUSET" "$PROTOS_IMAGE" "$HARNESS_REVISION" "$overall" <<'PY'
import json, os, platform, re, subprocess, sys
from pathlib import Path
cfg_path, out_path, cpuset, image_tag, harness_revision, gate = sys.argv[1:]
cfg=json.load(open(cfg_path, encoding="utf-8"))
out=Path(out_path)
image=json.load(open(out/"raw"/"image-protos.json", encoding="utf-8"))[0]

cpu_model=""
try:
    for line in open("/proc/cpuinfo", encoding="utf-8", errors="replace"):
        if line.lower().startswith("model name"):
            cpu_model=line.split(":",1)[1].strip()
            break
except OSError:
    pass

memory_bytes=0
try:
    for line in open("/proc/meminfo", encoding="utf-8"):
        if line.startswith("MemTotal:"):
            memory_bytes=int(line.split()[1])*1024
            break
except OSError:
    pass

allowed=""
try:
    text=open("/proc/self/status", encoding="utf-8").read()
    m=re.search(r"^Cpus_allowed_list:\s*(.+)$", text, re.M)
    allowed=m.group(1).strip() if m else ""
except OSError:
    pass

metadata={
  "schema_version":1,
  "perf_item":"PERF003",
  "slice":"PERF003-A",
  "evidence_class":"external_non_timing_compilability_gate",
  "generated_at":subprocess.check_output(["date","-u","+%Y-%m-%dT%H:%M:%SZ"], text=True).strip(),
  "harness_revision":harness_revision,
  "protos_revision":cfg["protos_revision"],
  "protos_implementation_version":cfg["protos_implementation_version"],
  "gate":gate,
  "runtime":{
    "graal_base":cfg["graal_base"],
    "truffle_runtime_version":cfg["truffle_runtime_version"],
    "stack":cfg["protos_stack"],
    "image":{"tag":image_tag,"id":image.get("Id"),"repo_digests":image.get("RepoDigests") or []},
  },
  "diagnostic_policy":{
    "iterations":cfg["diagnostic_iterations"],
    "trace_compilation":True,
    "timing_evidence":False,
    "network":"disabled",
    "cpuset":cpuset,
    "closure_gate":"zero optimizing failures and zero known bailout/runtime failure classes",
  },
  "environment":{
    "platform":platform.system().lower(),
    "architecture":platform.machine(),
    "kernel":platform.release(),
    "cpu_model":cpu_model,
    "cpu_count":os.cpu_count(),
    "memory_bytes":memory_bytes,
    "cpus_allowed_list":allowed,
    "cpuset":cpuset,
    "docker_server_version":subprocess.check_output(["docker","version","--format","{{.Server.Version}}"], text=True).strip(),
  },
}
with open(out/"run-metadata.json","w",encoding="utf-8") as fh:
    json.dump(metadata,fh,indent=2)
    fh.write("\n")
PY

printf '%s\n' "$overall" >"$OUT/gate.txt"
echo "PERF003A_EXTERNAL_GATE: $overall"
if [ "$overall" = "BLOCKED" ]; then
  echo "PERF003A_NEXT_DIAGNOSTIC: retain this evidence; use the isolated IGV analyzer for structural attribution rather than another blind source micro-edit"
else
  echo "PERF003A_NEXT_DIAGNOSTIC: zero-bailout gate satisfied for reduce and sort; canonical Protos ledger reconciliation can close PERF003-A and unblock PERF003-B"
fi
echo "PERF003A_DIAGNOSTIC: PASS"
