#!/usr/bin/env bash
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. See LICENSE.TXT.
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT=${1:-}
[ -n "$OUT" ] || { echo "usage: scripts/perf003a_a4i_experiment.sh <output-dir>" >&2; exit 2; }
[ ! -e "$OUT" ] || { echo "OUTPUT_PRECONDITION: output path exists: $OUT" >&2; exit 3; }
command -v docker >/dev/null 2>&1 || { echo "ENVIRONMENT_LIMITATION: docker is required" >&2; exit 4; }
command -v python3 >/dev/null 2>&1 || { echo "ENVIRONMENT_LIMITATION: python3 is required" >&2; exit 4; }
mkdir -p "$OUT"
CONFIG="$ROOT/config/perf003a-a4i.json"
eval "$(python3 - "$CONFIG" <<'PYCFG'
import json,shlex,sys
cfg=json.load(open(sys.argv[1],encoding='utf-8'))
vals={
 'PROTOS_REVISION':cfg['protos_revision'],
 'PROTOS_VERSION':cfg['protos_implementation_version'],
 'BUILD_BASE':cfg['build_base'],
 'GRAAL_BASE':cfg['graal_base'],
 'TRUFFLE_VERSION':cfg['truffle_runtime_version'],
 'STACK':cfg['protos_stack'],
 'TRACE_ITERATIONS':str(cfg['diagnostic_iterations']),
 'TIMING_WARMUP':str(cfg['timing_warmup']),
 'TIMING_ITERATIONS':str(cfg['timing_iterations']),
 'SOURCE':cfg['workload']['protos'],
 'EXPECTED':str(cfg['workload']['expected']),
 'CONTROL_VARIANT':cfg['control_variant'],
 'EXPERIMENTAL_VARIANT':cfg['experimental_variant'],
}
for k,v in vals.items(): print(f"{k}={shlex.quote(v)}")
PYCFG
)"
HARNESS_REVISION=$(git -C "$ROOT" rev-parse HEAD)
CPUSET=$(python3 - <<'PYCPU'
import os
cpus=sorted(os.sched_getaffinity(0))
if not cpus: raise SystemExit('cannot determine allowed CPU set')
print(cpus[0])
PYCPU
)
CONTROL_IMAGE="protos-benchmarks-perf003a-a4i-control:${PROTOS_REVISION:0:12}"
BOUNDARY_IMAGE="protos-benchmarks-perf003a-a4i-boundary:${PROTOS_REVISION:0:12}"
CTX="$ROOT/docker/protos-perf003a-a4i"
printf 'HARNESS_REVISION=%s\nPROTOS_REVISION=%s\nPROTOS_VERSION=%s\nCPUSET=%s\nTRACE_ITERATIONS=%s\nTIMING_WARMUP=%s\nTIMING_ITERATIONS=%s\nSTACK=%s\n' \
  "$HARNESS_REVISION" "$PROTOS_REVISION" "$PROTOS_VERSION" "$CPUSET" "$TRACE_ITERATIONS" "$TIMING_WARMUP" "$TIMING_ITERATIONS" "$STACK" >"$OUT/environment.txt"
uname -a >"$OUT/host-uname.txt"
uname -m >"$OUT/host-arch.txt"
if command -v lscpu >/dev/null 2>&1; then lscpu >"$OUT/host-cpu.txt"; else grep -m1 -E 'model name|Hardware|Processor' /proc/cpuinfo >"$OUT/host-cpu.txt" || true; fi
docker --version >"$OUT/docker-version.txt"

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
  rc=$?; set -e
  if [ "$rc" -ne 0 ]; then tail -100 "$OUT/${prefix}-build.stderr" >&2 || true; exit "$rc"; fi
}
check_runtime() {
  local image=$1 prefix=$2 runtime
  runtime=$(docker run --rm --network none --cpuset-cpus "$CPUSET" --entrypoint java "$image" \
    --enable-native-access=ALL-UNNAMED -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.RuntimeProbe)
  printf '%s\n' "$runtime" >"$OUT/${prefix}-runtime-class.txt"
  docker run --rm --network none --cpuset-cpus "$CPUSET" --entrypoint java "$image" -version >"$OUT/${prefix}-java-version.txt" 2>&1
  case "$runtime" in *HotSpotTruffleRuntime*) ;; *) echo "OPTIMIZING_RUNTIME_CHECK: FAIL variant=$prefix class=$runtime" >&2; exit 10;; esac
}
run_correctness() {
  local image=$1 prefix=$2 rc actual
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" --entrypoint java "$image" "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.DiagnosticEval "/opt/protos/$SOURCE" \
    >"$OUT/${prefix}-correctness.stdout" 2>"$OUT/${prefix}-correctness.stderr"
  rc=$?; set -e
  actual=$(awk 'NF {x=$0} END {print x}' "$OUT/${prefix}-correctness.stdout")
  [ "$rc" -eq 0 ] && [ "$actual" = "$EXPECTED" ] || { echo "CORRECTNESS: FAIL variant=$prefix rc=$rc expected=$EXPECTED actual=${actual:-<empty>}" >&2; exit 20; }
  echo "CORRECTNESS: PASS variant=$prefix result=$actual"
}
check_boundary_source() {
  local image=$1 source=/opt/protos/src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java
  docker run --rm --network none --entrypoint sh "$image" -c \
    "grep -B1 -F 'private static ProtosActivation prepareImmediateMethodActivation(' '$source' | grep -q -F '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' && \
     test \"\$(grep -c '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' '$source')\" -eq 1 && \
     ! grep -B1 -F 'private static Object invokePrepared(' '$source' | grep -q -F '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary'"
}
run_trace() {
  local image=$1 prefix=$2 rc
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" --entrypoint java "$image" "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false -Dpolyglot.engine.TraceCompilation=true \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.MeasurementDriver "/opt/protos/$SOURCE" "$EXPECTED" "$TRACE_ITERATIONS" 0 \
    >"$OUT/${prefix}-trace.stdout" 2>"$OUT/${prefix}-trace.stderr"
  rc=$?; set -e
  [ "$rc" -eq 0 ] || { tail -100 "$OUT/${prefix}-trace.stderr" >&2 || true; exit 30; }
}
run_timing() {
  local image=$1 prefix=$2 rc
  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" --entrypoint java "$image" "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.MeasurementDriver "/opt/protos/$SOURCE" "$EXPECTED" "$TIMING_WARMUP" "$TIMING_ITERATIONS" \
    >"$OUT/${prefix}-timing.stdout" 2>"$OUT/${prefix}-timing.stderr"
  rc=$?; set -e
  [ "$rc" -eq 0 ] || { tail -100 "$OUT/${prefix}-timing.stderr" >&2 || true; exit 31; }
  [ "$(grep -c '^STEADY' "$OUT/${prefix}-timing.stdout")" -eq "$TIMING_ITERATIONS" ] || { echo "TIMING_COUNT: FAIL variant=$prefix" >&2; exit 32; }
}

echo "phase=01 control image"
build_variant "$CONTROL_VARIANT" "$CONTROL_IMAGE" control
check_runtime "$CONTROL_IMAGE" control
run_correctness "$CONTROL_IMAGE" control

echo "phase=02 preparation-boundary-only image"
build_variant "$EXPERIMENTAL_VARIANT" "$BOUNDARY_IMAGE" boundary
check_boundary_source "$BOUNDARY_IMAGE"
echo "BOUNDARY_SOURCE_CHECK: PASS preparation=1 invokePrepared=0"
check_runtime "$BOUNDARY_IMAGE" boundary
run_correctness "$BOUNDARY_IMAGE" boundary

echo "phase=03 TraceCompilation"
run_trace "$CONTROL_IMAGE" control
run_trace "$BOUNDARY_IMAGE" boundary

echo "phase=04 separate no-trace timing"
run_timing "$CONTROL_IMAGE" control
run_timing "$BOUNDARY_IMAGE" boundary

docker image inspect "$CONTROL_IMAGE" >"$OUT/control-image.json"
docker image inspect "$BOUNDARY_IMAGE" >"$OUT/boundary-image.json"

python3 - "$OUT" "$HARNESS_REVISION" "$PROTOS_REVISION" "$PROTOS_VERSION" "$EXPECTED" "$TRACE_ITERATIONS" "$TIMING_WARMUP" "$TIMING_ITERATIONS" <<'PYSUM'
import json,re,statistics,sys
from pathlib import Path
out=Path(sys.argv[1]); harness,protos,version,expected=sys.argv[2:6]
trace_iterations=int(sys.argv[6]); timing_warmup=int(sys.argv[7]); timing_iterations=int(sys.argv[8])
def trace_stats(path):
    text=Path(path).read_text(encoding='utf-8',errors='replace')
    shapes=sorted({tuple(map(int,p)) for p in re.findall(r'Node count:\s*(\d+)\.\s*Graph Size:\s*(\d+)\.\s*Limit:\s*(\d+)',text)})
    return {'opt_done':len(re.findall(r'opt done',text,re.I)), 'opt_failed':len(re.findall(r'opt failed',text,re.I)), 'graph_too_big':len(re.findall(r'GraphTooBig',text,re.I)), 'graph_shapes':[{'node_count':n,'graph_size':g,'limit':l} for n,g,l in shapes]}
def timing(path):
    vals=[]
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        parts=line.split('\t')
        if len(parts)>=4 and parts[0]=='STEADY': vals.append(int(parts[2]))
    if len(vals)!=timing_iterations: raise SystemExit(f'timing sample count mismatch {path}: {len(vals)}')
    return {'samples':len(vals),'median_ns':int(statistics.median(vals)),'min_ns':min(vals),'max_ns':max(vals)}
control=trace_stats(out/'control-trace.stderr'); boundary=trace_stats(out/'boundary-trace.stderr')
control_shapes=[(x['node_count'],x['graph_size'],x['limit']) for x in control['graph_shapes']]
if control['graph_too_big']!=40 or control_shapes!=[(50681,150026,150000)]:
    raise SystemExit('CONTROL_REPRODUCTION: FAIL')
ct=timing(out/'control-timing.stdout'); bt=timing(out/'boundary-timing.stdout')
ratio=(bt['median_ns']/ct['median_ns']) if ct['median_ns'] else None
if boundary['graph_too_big']==0:
    decision='SUPPORTED'
    reason='preparation boundary alone eliminated all deterministic GraphTooBig bailouts'
    next_step='canonical architecture candidate; no further PE microexperiments'
else:
    decision='NOT_SUFFICIENT'
    reason='preparation boundary alone did not eliminate all deterministic GraphTooBig bailouts'
    next_step='close this boundary-localization line; no further PE microexperiments'
summary={
 'schema_version':1,'perf_item':'PERF003','slice':'PERF003-A4i','harness_revision':harness,
 'protos_revision':protos,'protos_implementation_version':version,'workload':'collections/array-reduce','expected_result':expected,
 'trace_iterations':trace_iterations,'timing_warmup':timing_warmup,'timing_iterations':timing_iterations,
 'control':control,'boundary':boundary,'control_timing':ct,'boundary_timing':bt,'median_ratio_boundary_over_control':ratio,
 'compilability_decision':decision,'reason':reason,'next_step':next_step,'protos_repository_changed':False
}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
def shapes(v):
    return 'NONE' if not v['graph_shapes'] else ','.join(f"{x['node_count']}:{x['graph_size']}:{x['limit']}" for x in v['graph_shapes'])
(out/'summary.md').write_text(
 f"# PERF003-A4i decision\n\n- Control: GraphTooBig={control['graph_too_big']}, {shapes(control)}\n- Preparation boundary only: GraphTooBig={boundary['graph_too_big']}, {shapes(boundary)}\n- Control median: {ct['median_ns']} ns\n- Boundary median: {bt['median_ns']} ns\n- Boundary/control median ratio: {ratio:.4f}\n- Compilability decision: **{decision}**\n- Reason: {reason}\n- Next: {next_step}\n",encoding='utf-8')
(out/'conclusion.txt').write_text(f'decision={decision}\nreason={reason}\nnext={next_step}\n',encoding='utf-8')
print('CONTROL_REPRODUCTION: PASS')
print(f"CONTROL_OPT_DONE={control['opt_done']}")
print(f"CONTROL_OPT_FAILED={control['opt_failed']}")
print(f"CONTROL_GRAPH_TOO_BIG={control['graph_too_big']}")
print(f"CONTROL_GRAPH_SHAPES={shapes(control)}")
print(f"BOUNDARY_OPT_DONE={boundary['opt_done']}")
print(f"BOUNDARY_OPT_FAILED={boundary['opt_failed']}")
print(f"BOUNDARY_GRAPH_TOO_BIG={boundary['graph_too_big']}")
print(f"BOUNDARY_GRAPH_SHAPES={shapes(boundary)}")
print(f"CONTROL_TIMING_MEDIAN_NS={ct['median_ns']}")
print(f"BOUNDARY_TIMING_MEDIAN_NS={bt['median_ns']}")
print(f"BOUNDARY_CONTROL_MEDIAN_RATIO={ratio:.6f}")
print(f"A4I_DECISION={decision}")
print(f"A4I_REASON={reason}")
print(f"A4I_NEXT={next_step}")
PYSUM

echo "PERF003A_A4I_EXPERIMENT: PASS"
echo "PROTOS_REPOSITORY_CHANGED: NO"
