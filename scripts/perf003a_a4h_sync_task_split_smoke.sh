#!/usr/bin/env bash
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. See LICENSE.TXT.
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT=${1:-}
[ -n "$OUT" ] || { echo "usage: scripts/perf003a_a4h_sync_task_split_smoke.sh <output-dir>" >&2; exit 2; }
[ ! -e "$OUT" ] || { echo "OUTPUT_PRECONDITION: output path exists: $OUT" >&2; exit 3; }
command -v docker >/dev/null 2>&1 || { echo "ENVIRONMENT_LIMITATION: docker is required" >&2; exit 4; }
mkdir -p "$OUT"
CONFIG="$ROOT/config/perf003a-a4h.json"
eval "$(python3 - "$CONFIG" <<'PYCFG'
import json,shlex,sys
cfg=json.load(open(sys.argv[1],encoding='utf-8'))
for k,v in {
 'PROTOS_REVISION':cfg['protos_revision'],'BUILD_BASE':cfg['build_base'],
 'GRAAL_BASE':cfg['graal_base'],'TRUFFLE_VERSION':cfg['truffle_runtime_version'],
 'STACK':cfg['protos_stack'],'SOURCE':cfg['workload']['protos'],
 'EXPECTED':str(cfg['workload']['expected']),'VARIANT':cfg['experimental_variant']}.items():
 print(f"{k}={shlex.quote(v)}")
PYCFG
)"
CPUSET=$(python3 - <<'PYCPU'
import os
cpus=sorted(os.sched_getaffinity(0))
if not cpus: raise SystemExit('cannot determine allowed CPU set')
print(cpus[0])
PYCPU
)
IMAGE="protos-benchmarks-perf003a-a4h-smoke:${PROTOS_REVISION:0:12}"
CTX="$ROOT/docker/protos-perf003a-a4h"
echo "PERF003-A4h2 sync/task split smoke"
echo "PROTOS_REVISION=$PROTOS_REVISION"
echo "CPUSET=$CPUSET"
docker build \
 --build-arg BUILD_BASE="$BUILD_BASE" \
 --build-arg GRAAL_BASE="$GRAAL_BASE" \
 --build-arg PROTOS_REVISION="$PROTOS_REVISION" \
 --build-arg TRUFFLE_RUNTIME_VERSION="$TRUFFLE_VERSION" \
 --build-arg DIAGNOSTIC_VARIANT="$VARIANT" \
 -t "$IMAGE" -f "$CTX/Dockerfile" "$CTX" \
 >"$OUT/build.stdout" 2>"$OUT/build.stderr"
echo "BOUNDARY_IMAGE_BUILD: PASS"
source=/opt/protos/src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java
docker run --rm --network none --entrypoint sh "$IMAGE" -c \
 "grep -B1 -F 'private static Object invokePrepared(' '$source' | grep -q -F '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' && \
  grep -q -F 'private static ProtosActivation prepareImmediateMethodDirectActivation(' '$source' && \
  grep -q -F 'private static ProtosActivation prepareImmediateMethodTaskActivation(' '$source' && \
  test \"\$(grep -c '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' '$source')\" -eq 1"
echo "BOUNDARY_SOURCE_CHECK: PASS count=1"
docker run --rm --network none --entrypoint sh "$IMAGE" -c '
  source=/opt/protos/src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java
  direct="$(
    sed -n \
      "/private static ProtosActivation prepareImmediateMethodDirectActivation(/,/private static ProtosActivation prepareImmediateMethodTaskActivation(/p" \
      "$source"
  )"
  for forbidden in \
    "Supplier" \
    "evaluatorContinuation" \
    "attachTask" \
    "caller.task"
  do
    if printf "%s
" "$direct" | grep -q -F "$forbidden"; then
      echo "DIRECT_PATH_TASK_MACHINERY: FAIL token=$forbidden" >&2
      exit 1
    fi
  done
  echo "DIRECT_PATH_TASK_MACHINERY: NONE"
'
runtime=$(docker run --rm --network none --cpuset-cpus "$CPUSET" \
 --entrypoint java "$IMAGE" --enable-native-access=ALL-UNNAMED \
 -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
 com.guillermomolina.protos.cli.RuntimeProbe)
printf '%s\n' "$runtime" >"$OUT/runtime-class.txt"
case "$runtime" in *HotSpotTruffleRuntime*) ;; *) echo "OPTIMIZING_RUNTIME_CHECK: FAIL class=$runtime" >&2; exit 10;; esac
echo "OPTIMIZING_RUNTIME_CHECK: PASS class=$runtime"
set +e
docker run --rm --network none --cpuset-cpus "$CPUSET" \
 --entrypoint java "$IMAGE" "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
 -Dpolyglot.engine.AllowExperimentalOptions=true \
 -Dpolyglot.engine.BackgroundCompilation=false \
 -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
 com.guillermomolina.protos.cli.DiagnosticEval "/opt/protos/$SOURCE" \
 >"$OUT/correctness.stdout" 2>"$OUT/correctness.stderr"
rc=$?
set -e
actual=$(awk 'NF {x=$0} END {print x}' "$OUT/correctness.stdout")
if [ "$rc" -ne 0 ] || [ "$actual" != "$EXPECTED" ]; then
 echo "CORRECTNESS: FAIL rc=$rc expected=$EXPECTED actual=${actual:-<empty>}" >&2
 tail -80 "$OUT/correctness.stderr" >&2 || true
 exit 20
fi
docker image inspect "$IMAGE" >"$OUT/image.json"
echo "BOUNDARY_CORRECTNESS_SMOKE: PASS result=$actual"
echo "REAL_20_ITERATION_EXPERIMENT_EXECUTED: NO"
echo "CONTROL_TRACE_EXECUTED: NO"
echo "BOUNDARY_TRACE_EXECUTED: NO"
echo "TIMING_EVIDENCE: NO"
echo "PROTOS_REPOSITORY_CHANGED: NO"
echo "PERF003A_A4H2_SMOKE: PASS"
