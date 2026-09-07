#!/usr/bin/env bash
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. See LICENSE.TXT.
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT=${1:-}
[ -n "$OUT" ] || {
  echo "usage: scripts/perf003a_a4h_experiment.sh <output-dir>" >&2
  exit 2
}
[ ! -e "$OUT" ] || {
  echo "OUTPUT_PRECONDITION: output path exists: $OUT" >&2
  exit 3
}
command -v docker >/dev/null 2>&1 || {
  echo "ENVIRONMENT_LIMITATION: docker is required" >&2
  exit 4
}
command -v python3 >/dev/null 2>&1 || {
  echo "ENVIRONMENT_LIMITATION: python3 is required" >&2
  exit 4
}
mkdir -p "$OUT"

CONFIG="$ROOT/config/perf003a-a4h.json"
eval "$(python3 - "$CONFIG" <<'PYCFG'
import json, shlex, sys
cfg=json.load(open(sys.argv[1],encoding="utf-8"))
vals={
  "PROTOS_REVISION":cfg["protos_revision"],
  "PROTOS_VERSION":cfg["protos_implementation_version"],
  "BUILD_BASE":cfg["build_base"],
  "GRAAL_BASE":cfg["graal_base"],
  "TRUFFLE_VERSION":cfg["truffle_runtime_version"],
  "STACK":cfg["protos_stack"],
  "ITERATIONS":str(cfg["diagnostic_iterations"]),
  "SOURCE":cfg["workload"]["protos"],
  "EXPECTED":str(cfg["workload"]["expected"]),
  "CONTROL_VARIANT":cfg["control_variant"],
  "EXPERIMENTAL_VARIANT":cfg["experimental_variant"],
  "REFERENCE_GRAPH_TOO_BIG":str(cfg["reference_variant"]["graph_too_big"]),
  "REFERENCE_NODE_COUNT":str(cfg["reference_variant"]["graph_shapes"][0]["node_count"]),
  "REFERENCE_GRAPH_SIZE":str(cfg["reference_variant"]["graph_shapes"][0]["graph_size"]),
  "REFERENCE_LIMIT":str(cfg["reference_variant"]["graph_shapes"][0]["limit"]),
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
    raise SystemExit("cannot determine allowed CPU set")
print(cpus[0])
PYCPU
)

CONTROL_IMAGE="protos-benchmarks-perf003a-a4h-control:${PROTOS_REVISION:0:12}"
SPLIT_IMAGE="protos-benchmarks-perf003a-a4h-split:${PROTOS_REVISION:0:12}"
CTX="$ROOT/docker/protos-perf003a-a4h"

echo "HARNESS_REVISION=$HARNESS_REVISION"
echo "PROTOS_REVISION=$PROTOS_REVISION"
echo "PROTOS_VERSION=$PROTOS_VERSION"
echo "CPUSET=$CPUSET"
echo "ITERATIONS=$ITERATIONS"

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
    exit "$rc"
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
    *)
      echo "OPTIMIZING_RUNTIME_CHECK: FAIL variant=$prefix class=$runtime" >&2
      exit 10
      ;;
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

check_split_source() {
  local image=$1
  local source=/opt/protos/src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java
  docker run --rm --network none --entrypoint sh "$image" -c \
    "grep -B1 -F 'private static Object invokePrepared(' '$source' | grep -q -F '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' &&
     grep -q -F 'private static ProtosActivation prepareImmediateMethodDirectActivation(' '$source' &&
     grep -q -F 'private static ProtosActivation prepareImmediateMethodTaskActivation(' '$source' &&
     test \"\$(grep -c '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' '$source')\" -eq 1"
  docker run --rm --network none --entrypoint sh "$image" -c '
    source=/opt/protos/src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java
    direct="$(
      sed -n \
        "/private static ProtosActivation prepareImmediateMethodDirectActivation(/,/private static ProtosActivation prepareImmediateMethodTaskActivation(/p" \
        "$source"
    )"
    for forbidden in "Supplier" "evaluatorContinuation" "attachTask" "caller.task"; do
      if printf "%s\n" "$direct" | grep -q -F "$forbidden"; then
        echo "DIRECT_PATH_TASK_MACHINERY: FAIL token=$forbidden" >&2
        exit 1
      fi
    done
    echo "DIRECT_PATH_TASK_MACHINERY: NONE"
  '
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
    com.guillermomolina.protos.cli.MeasurementDriver \
    "/opt/protos/$SOURCE" "$EXPECTED" "$ITERATIONS" 0 \
    >"$OUT/${prefix}-trace.stdout" 2>"$OUT/${prefix}-trace.stderr"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "TRACE_EXECUTION: FAIL variant=$prefix rc=$rc" >&2
    tail -100 "$OUT/${prefix}-trace.stderr" >&2 || true
    exit 30
  fi
}

echo "phase=01 build exact control image"
build_variant "$CONTROL_VARIANT" "$CONTROL_IMAGE" control
check_runtime "$CONTROL_IMAGE" control
run_correctness "$CONTROL_IMAGE" control
echo "CONTROL_IMAGE_BUILD: PASS"

echo "phase=02 build production-shaped split image"
build_variant "$EXPERIMENTAL_VARIANT" "$SPLIT_IMAGE" split
check_split_source "$SPLIT_IMAGE"
echo "SPLIT_SOURCE_CHECK: PASS count=1"
check_runtime "$SPLIT_IMAGE" split
run_correctness "$SPLIT_IMAGE" split
echo "SPLIT_IMAGE_BUILD: PASS"

echo "phase=03 control TraceCompilation"
run_trace "$CONTROL_IMAGE" control

echo "phase=04 split TraceCompilation"
run_trace "$SPLIT_IMAGE" split

docker image inspect "$CONTROL_IMAGE" >"$OUT/control-image.json"
docker image inspect "$SPLIT_IMAGE" >"$OUT/split-image.json"

python3 - "$OUT" \
  "$HARNESS_REVISION" "$PROTOS_REVISION" "$PROTOS_VERSION" "$EXPECTED" "$ITERATIONS" \
  "$REFERENCE_GRAPH_TOO_BIG" "$REFERENCE_NODE_COUNT" "$REFERENCE_GRAPH_SIZE" "$REFERENCE_LIMIT" <<'PYSUM'
import json,re,sys
from pathlib import Path

out=Path(sys.argv[1])
harness,protos,version,expected=sys.argv[2:6]
iterations=int(sys.argv[6])
ref_graph=int(sys.argv[7])
ref_shape=(int(sys.argv[8]),int(sys.argv[9]),int(sys.argv[10]))

def stats(path):
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    done=len(re.findall(r"opt done",text,re.I))
    failed=len(re.findall(r"opt failed",text,re.I))
    graph=len(re.findall(r"GraphTooBig",text,re.I))
    shapes=sorted({tuple(map(int,p)) for p in re.findall(
        r"Node count:\s*(\d+)\.\s*Graph Size:\s*(\d+)\.\s*Limit:\s*(\d+)",text)})
    return {"opt_done":done,"opt_failed":failed,"graph_too_big":graph,
            "graph_shapes":[{"node_count":n,"graph_size":g,"limit":l} for n,g,l in shapes]}

control=stats(out/"control-trace.stderr")
split=stats(out/"split-trace.stderr")

control_shape=[(x["node_count"],x["graph_size"],x["limit"]) for x in control["graph_shapes"]]
split_shape=[(x["node_count"],x["graph_size"],x["limit"]) for x in split["graph_shapes"]]

# Exact original-control reproduction is a hard experiment validity gate.
expected_control=[(50681,150026,150000)]
if control["graph_too_big"] != 40 or control_shape != expected_control:
    conclusion="INCONCLUSIVE"
    reason="control did not reproduce the exact PERF003-A4 control baseline"
    control_reproduction=False
else:
    control_reproduction=True
    if split["graph_too_big"] == 0:
        conclusion="SUPPORTED"
        reason="sync/task split eliminated the A4a residual GraphTooBig"
    elif split["graph_too_big"] < ref_graph:
        conclusion="SUPPORTED"
        reason="sync/task split reduced GraphTooBig occurrences relative to A4a"
    elif split_shape and max(x[1] for x in split_shape) < ref_shape[1]:
        conclusion="SUPPORTED"
        reason="sync/task split reduced failing graph size relative to A4a"
    elif split["graph_too_big"] == ref_graph and split_shape == [ref_shape]:
        conclusion="NOT_SUPPORTED"
        reason="sync/task split left the A4a residual graph unchanged"
    else:
        conclusion="INCONCLUSIVE"
        reason="sync/task split changed the A4a residual diagnostics without a directional result"

summary={
    "schema_version":1,
    "perf_item":"PERF003",
    "slice":"PERF003-A4h",
    "evidence_class":"production_shaped_immediate_method_sync_task_split_falsification",
    "harness_revision":harness,
    "protos_revision":protos,
    "protos_implementation_version":version,
    "workload":"collections/array-reduce",
    "expected_result":expected,
    "diagnostic_iterations":iterations,
    "timing_evidence":False,
    "protos_repository_changed":False,
    "reference":{
        "source":"PERF003-A4a",
        "graph_too_big":ref_graph,
        "graph_shapes":[{"node_count":ref_shape[0],"graph_size":ref_shape[1],"limit":ref_shape[2]}],
    },
    "control":control,
    "split":split,
    "control_reproduction":control_reproduction,
    "hypothesis":conclusion,
    "reason":reason,
}
(out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
(out/"conclusion.txt").write_text(
    f"conclusion={conclusion}\nreason={reason}\n",encoding="utf-8")
def shapes(v):
    if not v["graph_shapes"]:
        return "NONE"
    return ",".join(
        f'{x["node_count"]}:{x["graph_size"]}:{x["limit"]}'
        for x in v["graph_shapes"])
(out/"summary.md").write_text(
    "# PERF003-A4h result\n\n"
    f"- Harness: `{harness}`\n"
    f"- Protos: `{protos}` (`{version}`)\n"
    f"- Workload/result: `collections/array-reduce => {expected}`\n"
    f"- Iterations: {iterations}\n"
    f"- Control: GraphTooBig={control['graph_too_big']}, shapes={shapes(control)}\n"
    f"- Split: GraphTooBig={split['graph_too_big']}, shapes={shapes(split)}\n"
    f"- Control reproduction: {'PASS' if control_reproduction else 'FAIL'}\n"
    f"- Hypothesis: **{conclusion}**\n"
    f"- Reason: {reason}\n"
    "- Timing evidence: NO\n",
    encoding="utf-8")

print(f"CONTROL_OPT_DONE={control['opt_done']}")
print(f"CONTROL_OPT_FAILED={control['opt_failed']}")
print(f"CONTROL_GRAPH_TOO_BIG={control['graph_too_big']}")
print(f"CONTROL_GRAPH_SHAPES={shapes(control)}")
print(f"SPLIT_OPT_DONE={split['opt_done']}")
print(f"SPLIT_OPT_FAILED={split['opt_failed']}")
print(f"SPLIT_GRAPH_TOO_BIG={split['graph_too_big']}")
print(f"SPLIT_GRAPH_SHAPES={shapes(split)}")
print(f"CONTROL_REPRODUCTION={'PASS' if control_reproduction else 'FAIL'}")
print(f"A4H_HYPOTHESIS={conclusion}")
print(f"A4H_REASON={reason}")
PYSUM

echo "PERF003A_A4H_EXPERIMENT: PASS"
echo "TIMING_EVIDENCE: NO"
echo "PROTOS_REPOSITORY_CHANGED: NO"
