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
[ -n "$OUT" ] || { echo "usage: scripts/perf003a_a4g_experiment.sh <output-dir>" >&2; exit 2; }
[ ! -e "$OUT" ] || { echo "OUTPUT_PRECONDITION: output path exists: $OUT" >&2; exit 3; }
command -v docker >/dev/null 2>&1 || { echo "ENVIRONMENT_LIMITATION: docker is required" >&2; exit 4; }
command -v python3 >/dev/null 2>&1 || { echo "ENVIRONMENT_LIMITATION: python3 is required" >&2; exit 4; }
mkdir -p "$OUT"

CONFIG="$ROOT/config/perf003a-a4g.json"
eval "$(python3 - "$CONFIG" <<'PYCFG'
import json, shlex, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
vals={
    'PROTOS_REVISION':cfg['protos_revision'],
    'PROTOS_VERSION':cfg['protos_implementation_version'],
    'BUILD_BASE':cfg['build_base'],
    'GRAAL_BASE':cfg['graal_base'],
    'TRUFFLE_VERSION':cfg['truffle_runtime_version'],
    'STACK':cfg['protos_stack'],
    'ITERATIONS':str(cfg['diagnostic_iterations']),
    'SOURCE':cfg['workload']['protos'],
    'EXPECTED':str(cfg['workload']['expected']),
    'CONTROL_VARIANT':cfg['control_variant'],
    'EXPERIMENTAL_VARIANT':cfg['experimental_variant'],
    'REFERENCE_GRAPH_TOO_BIG':str(cfg['reference_variant']['graph_too_big']),
    'REFERENCE_NODE_COUNT':str(cfg['reference_variant']['graph_shapes'][0]['node_count']),
    'REFERENCE_GRAPH_SIZE':str(cfg['reference_variant']['graph_shapes'][0]['graph_size']),
    'REFERENCE_LIMIT':str(cfg['reference_variant']['graph_shapes'][0]['limit']),
}
for k,v in vals.items():
    print(f"{k}={shlex.quote(v)}")
PYCFG
)"

HARNESS_REVISION=$(git -C "$ROOT" rev-parse HEAD)
CPUSET=$(python3 - <<'PYCPU'
import os
cpus=sorted(os.sched_getaffinity(0))
if not cpus:
    raise SystemExit('cannot determine allowed CPU set')
print(cpus[0])
PYCPU
)

CONTROL_IMAGE="protos-benchmarks-perf003a-a4g-control:${PROTOS_REVISION:0:12}"
BOUNDARY_IMAGE="protos-benchmarks-perf003a-a4g-boundary:${PROTOS_REVISION:0:12}"
CTX="$ROOT/docker/protos-perf003a-a4g"

printf 'HARNESS_REVISION=%s\n' "$HARNESS_REVISION"
printf 'PROTOS_REVISION=%s\n' "$PROTOS_REVISION"
printf 'PROTOS_VERSION=%s\n' "$PROTOS_VERSION"
printf 'CPUSET=%s\n' "$CPUSET"
printf 'ITERATIONS=%s\n' "$ITERATIONS"

uname -a >"$OUT/host-uname.txt"
uname -m >"$OUT/host-arch.txt"
if command -v lscpu >/dev/null 2>&1; then
  lscpu >"$OUT/host-cpu.txt"
else
  grep -m1 -E 'model name|Hardware|Processor' /proc/cpuinfo >"$OUT/host-cpu.txt" || true
fi
docker --version >"$OUT/docker-version.txt"
printf 'HARNESS_REVISION=%s\nPROTOS_REVISION=%s\nPROTOS_VERSION=%s\nCPUSET=%s\nITERATIONS=%s\nSTACK=%s\n' \
  "$HARNESS_REVISION" "$PROTOS_REVISION" "$PROTOS_VERSION" "$CPUSET" "$ITERATIONS" "$STACK" \
  >"$OUT/environment.txt"

build_variant() {
  local variant=$1 image=$2 prefix=$3 rc
  set +e
  docker build \
    --build-arg BUILD_BASE="$BUILD_BASE" \
    --build-arg GRAAL_BASE="$GRAAL_BASE" \
    --build-arg PROTOS_REVISION="$PROTOS_REVISION" \
    --build-arg TRUFFLE_RUNTIME_VERSION="$TRUFFLE_VERSION" \
    --build-arg DIAGNOSTIC_VARIANT="$variant" \
    -t "$image" -f "$CTX/Dockerfile" "$CTX" \
    >"$OUT/${prefix}-build.stdout" 2>"$OUT/${prefix}-build.stderr"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "IMAGE_BUILD: FAIL variant=$prefix rc=$rc" >&2
    tail -100 "$OUT/${prefix}-build.stderr" >&2 || true
    return "$rc"
  fi
}

check_runtime() {
  local image=$1 prefix=$2 runtime
  runtime=$(docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" \
    --enable-native-access=ALL-UNNAMED \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.RuntimeProbe)
  printf '%s\n' "$runtime" >"$OUT/${prefix}-runtime-class.txt"
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" -version \
    >"$OUT/${prefix}-java-version.txt" 2>&1
  case "$runtime" in
    *HotSpotTruffleRuntime*) ;;
    *) echo "OPTIMIZING_RUNTIME_CHECK: FAIL variant=$prefix class=$runtime" >&2; exit 10;;
  esac
}

run_correctness() {
  local image=$1 prefix=$2 rc actual
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED \
    -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.DiagnosticEval "/opt/protos/$SOURCE" \
    >"$OUT/${prefix}-correctness.stdout" 2>"$OUT/${prefix}-correctness.stderr"
  rc=$?
  set -e
  actual=$(awk 'NF {x=$0} END {print x}' "$OUT/${prefix}-correctness.stdout")
  if [ "$rc" -ne 0 ] || [ "$actual" != "$EXPECTED" ]; then
    echo "CORRECTNESS: FAIL variant=$prefix rc=$rc expected=$EXPECTED actual=${actual:-<empty>}" >&2
    tail -80 "$OUT/${prefix}-correctness.stderr" >&2 || true
    exit 20
  fi
  echo "CORRECTNESS: PASS variant=$prefix result=$actual"
}

run_trace() {
  local image=$1 prefix=$2 rc
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED \
    -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false \
    -Dpolyglot.engine.TraceCompilation=true \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.MeasurementDriver "/opt/protos/$SOURCE" "$EXPECTED" "$ITERATIONS" 0 \
    >"$OUT/${prefix}-trace.stdout" 2>"$OUT/${prefix}-trace.stderr"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "TRACE_EXECUTION: FAIL variant=$prefix rc=$rc" >&2
    tail -100 "$OUT/${prefix}-trace.stderr" >&2 || true
    exit 30
  fi
}

summarize_trace() {
  local prefix=$1
  python3 - "$OUT/${prefix}-trace.stderr" "$prefix" <<'PYSUM'
import re,sys
path,prefix=sys.argv[1:]
text=open(path,encoding='utf-8',errors='replace').read()
done=len(re.findall(r'opt done',text,re.I))
failed=len(re.findall(r'opt failed',text,re.I))
graph=len(re.findall(r'GraphTooBig',text,re.I))
pairs=re.findall(r'Node count:\s*(\d+)\.\s*Graph Size:\s*(\d+)\.\s*Limit:\s*(\d+)',text)
unique=sorted({tuple(map(int,p)) for p in pairs})
print(f'{prefix}_opt_done={done}')
print(f'{prefix}_opt_failed={failed}')
print(f'{prefix}_graph_too_big={graph}')
print(f'{prefix}_graph_shapes=' + (','.join(f'{n}:{g}:{limit}' for n,g,limit in unique) if unique else 'NONE'))
PYSUM
}

echo "phase=01 build exact control image"
build_variant "$CONTROL_VARIANT" "$CONTROL_IMAGE" control
echo "CONTROL_IMAGE_BUILD: PASS"
check_runtime "$CONTROL_IMAGE" control
run_correctness "$CONTROL_IMAGE" control

echo "phase=02 build A4g preparation-unit image"
build_variant "$EXPERIMENTAL_VARIANT" "$BOUNDARY_IMAGE" boundary
echo "BOUNDARY_IMAGE_BUILD: PASS"
docker run --rm --network none --entrypoint sh "$BOUNDARY_IMAGE" -c \
  "grep -B1 -F 'private static ProtosActivation prepareImmediateMethodActivation(' /opt/protos/src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java | grep -q -F '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' && \
   grep -B1 -F 'private static Object invokePrepared(' /opt/protos/src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java | grep -q -F '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary'"
echo "BOUNDARY_SOURCE_CHECK: PASS"
check_runtime "$BOUNDARY_IMAGE" boundary
run_correctness "$BOUNDARY_IMAGE" boundary

echo "phase=03 control TraceCompilation"
run_trace "$CONTROL_IMAGE" control
control_summary=$(summarize_trace control)
printf '%s\n' "$control_summary"

echo "phase=04 A4g boundary TraceCompilation"
run_trace "$BOUNDARY_IMAGE" boundary
boundary_summary=$(summarize_trace boundary)
printf '%s\n' "$boundary_summary"

python3 - "$OUT/control-trace.stderr" "$OUT/boundary-trace.stderr" "$OUT/conclusion.txt" \
  "$REFERENCE_GRAPH_TOO_BIG" "$REFERENCE_NODE_COUNT" "$REFERENCE_GRAPH_SIZE" "$REFERENCE_LIMIT" <<'PYCON'
import re,sys
cp,bp,out,ref_graph,ref_nodes,ref_size,ref_limit=sys.argv[1:]
ref_graph=int(ref_graph)
ref_shape=(int(ref_nodes),int(ref_size),int(ref_limit))

def stats(path):
    text=open(path,encoding='utf-8',errors='replace').read()
    graph=len(re.findall(r'GraphTooBig',text,re.I))
    shapes=sorted({tuple(map(int,p)) for p in re.findall(
        r'Node count:\s*(\d+)\.\s*Graph Size:\s*(\d+)\.\s*Limit:\s*(\d+)',text)})
    return graph,shapes

cg,cs=stats(cp)
bg,bs=stats(bp)
if cg==0:
    c,r='INCONCLUSIVE','control did not reproduce GraphTooBig'
elif bg==0:
    c,r='SUPPORTED','immediate-preparation boundary eliminated the A4a residual GraphTooBig'
elif bg<ref_graph:
    c,r='SUPPORTED','immediate-preparation boundary reduced GraphTooBig occurrences relative to A4a'
elif bs and max(x[1] for x in bs)<ref_shape[1]:
    c,r='SUPPORTED','immediate-preparation boundary reduced failing graph size relative to A4a'
elif bg==ref_graph and bs==[ref_shape]:
    c,r='NOT_SUPPORTED','immediate-preparation boundary left the A4a residual graph unchanged'
else:
    c,r='INCONCLUSIVE','immediate-preparation boundary changed the A4a residual diagnostics without a directional result'
open(out,'w',encoding='utf-8').write(f'conclusion={c}\nreason={r}\n')
print(f'A4G_HYPOTHESIS={c}')
print(f'A4G_REASON={r}')
PYCON

docker image inspect "$CONTROL_IMAGE" >"$OUT/control-image.json"
docker image inspect "$BOUNDARY_IMAGE" >"$OUT/boundary-image.json"

echo "PERF003A_A4G_EXPERIMENT: PASS"
echo "TIMING_EVIDENCE: NO"
echo "PROTOS_REPOSITORY_CHANGED: NO"
