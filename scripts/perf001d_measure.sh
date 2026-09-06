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
[ -n "$OUT" ] || { echo "usage: scripts/perf001d_measure.sh <output-dir>" >&2; exit 2; }

CONFIG="$ROOT/config/perf001d.json"
rm -rf "$OUT"
mkdir -p "$OUT/raw" "$OUT/diagnostics"

command -v docker >/dev/null 2>&1 || {
  echo "ENVIRONMENT_LIMITATION: docker is required for PERF001-D" >&2
  exit 3
}
command -v python3 >/dev/null 2>&1 || {
  echo "ENVIRONMENT_LIMITATION: python3 is required for PERF001-D" >&2
  exit 3
}

eval "$(
python3 - "$CONFIG" <<'PY'
import json, shlex, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
print("PROTOS_REPOSITORY=" + shlex.quote(cfg["protos_repository"]))
print("BUILD_BASE=" + shlex.quote(cfg["build_base"]))
print("GRAAL_BASE=" + shlex.quote(cfg["graal_base"]))
print("TRUFFLE_VERSION=" + shlex.quote(cfg["truffle_runtime_version"]))
print("STACK=" + shlex.quote(cfg["stack"]))
print("STARTUP_SAMPLES=" + str(cfg["startup_samples"]))
print("WARMUP_ITERATIONS=" + str(cfg["warmup_iterations"]))
print("STEADY_SAMPLES=" + str(cfg["steady_samples"]))
print("DIAGNOSTIC_ITERATIONS=" + str(cfg["diagnostic_iterations"]))
PY
)"

allowed_list=$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status 2>/dev/null || true)
[ -n "$allowed_list" ] || allowed_list="0"
first_segment=${allowed_list%%,*}
CPUSET=${first_segment%%-*}
[ -n "$CPUSET" ] || CPUSET=0

echo "PERF001-D measurement run"
echo "STACK=-Xss$STACK"
echo "CPUSET=$CPUSET"
echo "STARTUP_SAMPLES=$STARTUP_SAMPLES"
echo "WARMUP_ITERATIONS=$WARMUP_ITERATIONS"
echo "STEADY_SAMPLES=$STEADY_SAMPLES"
echo "DIAGNOSTIC_ITERATIONS=$DIAGNOSTIC_ITERATIONS"

docker pull "$BUILD_BASE" >/dev/null
docker pull "$GRAAL_BASE" >/dev/null

build_one() {
  local label=$1 revision=$2
  local image="protos-benchmarks-perf001d:${label}-${revision:0:12}"
  echo "BUILD label=$label revision=$revision image=$image"
  docker build \
    --build-arg BUILD_BASE="$BUILD_BASE" \
    --build-arg GRAAL_BASE="$GRAAL_BASE" \
    --build-arg PROTOS_REPOSITORY="$PROTOS_REPOSITORY" \
    --build-arg PROTOS_REVISION="$revision" \
    --build-arg TRUFFLE_RUNTIME_VERSION="$TRUFFLE_VERSION" \
    -t "$image" \
    -f "$ROOT/docker/protos-perf001d/Dockerfile" \
    "$ROOT/docker/protos-perf001d" \
    >"$OUT/raw/build-${label}.stdout" \
    2>"$OUT/raw/build-${label}.stderr"
  echo "$image"
}

PRE_REVISION=$(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
print(next(x["revision"] for x in cfg["revisions"] if x["label"] == "pre-perf002"))
PY
)
POST_REVISION=$(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
print(next(x["revision"] for x in cfg["revisions"] if x["label"] == "post-perf002"))
PY
)

PRE_IMAGE=$(build_one pre-perf002 "$PRE_REVISION")
POST_IMAGE=$(build_one post-perf002 "$POST_REVISION")

# build_one emits a progress line and then image; retain only the last line.
PRE_IMAGE=$(printf '%s\n' "$PRE_IMAGE" | tail -n1)
POST_IMAGE=$(printf '%s\n' "$POST_IMAGE" | tail -n1)

probe_runtime() {
  local label=$1 image=$2
  local klass
  klass=$(
    docker run --rm --network none --cpuset-cpus "$CPUSET" \
      --entrypoint java "$image" \
      --enable-native-access=ALL-UNNAMED \
      -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
      com.guillermomolina.protos.cli.RuntimeProbe
  )
  echo "$klass" >"$OUT/raw/runtime-class-${label}.txt"
  case "$klass" in
    *HotSpotTruffleRuntime*) ;;
    *)
      echo "OPTIMIZING_RUNTIME_CHECK: FAIL label=$label class=$klass" >&2
      exit 10
      ;;
  esac
  echo "OPTIMIZING_RUNTIME_CHECK: PASS label=$label class=$klass"
}

probe_runtime pre-perf002 "$PRE_IMAGE"
probe_runtime post-perf002 "$POST_IMAGE"

docker run --rm --network none --cpuset-cpus "$CPUSET" \
  --entrypoint java "$PRE_IMAGE" -version \
  >"$OUT/raw/java-version-pre.stdout" 2>"$OUT/raw/java-version-pre.stderr"
docker run --rm --network none --cpuset-cpus "$CPUSET" \
  --entrypoint java "$POST_IMAGE" -version \
  >"$OUT/raw/java-version-post.stdout" 2>"$OUT/raw/java-version-post.stderr"
docker --version >"$OUT/raw/docker-version.txt"

mode_args() {
  local mode=$1
  if [ "$mode" = "interpreter" ]; then
    printf '%s\0' \
      '-Dpolyglot.engine.AllowExperimentalOptions=true' \
      '-Dpolyglot.engine.Compilation=false'
  else
    printf '%s\0' \
      '-Dpolyglot.engine.AllowExperimentalOptions=true' \
      '-Dpolyglot.engine.BackgroundCompilation=false'
  fi
}

run_correctness() {
  local label=$1 image=$2 mode=$3 key=$4 source=$5 expected=$6
  local -a props=()
  while IFS= read -r -d '' x; do props+=("$x"); done < <(mode_args "$mode")
  local safe=${key//\//__}
  local stdout="$OUT/raw/correctness-${label}-${mode}-${safe}.stdout"
  local stderr="$OUT/raw/correctness-${label}-${mode}-${safe}.stderr"

  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" \
    "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED \
    "${props[@]}" \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.DiagnosticEval \
    "/opt/protos/$source" >"$stdout" 2>"$stderr"
  rc=$?
  set -e

  actual=$(awk 'NF {x=$0} END {print x}' "$stdout")
  if [ "$rc" -ne 0 ] || [ "$actual" != "$expected" ]; then
    echo "CORRECTNESS_GATE: FAIL label=$label mode=$mode workload=$key rc=$rc expected=$expected actual=${actual:-<empty>}" >&2
    tail -80 "$stderr" >&2 || true
    exit 20
  fi
  echo "CORRECTNESS label=$label mode=$mode workload=$key PASS"
}

run_startup() {
  local label=$1 image=$2 mode=$3 key=$4 source=$5 expected=$6
  local safe=${key//\//__}
  local stdout="$OUT/raw/startup-${label}-${mode}-${safe}.tsv"
  local stderr="$OUT/raw/startup-${label}-${mode}-${safe}.stderr"

  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" \
    "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.StartupDriver \
    "$mode" "/opt/protos/$source" "$expected" "$STARTUP_SAMPLES" "$STACK" \
    >"$stdout" 2>"$stderr"

  count=$(awk -F '\t' '$1=="STARTUP" {c++} END {print c+0}' "$stdout")
  [ "$count" -eq "$STARTUP_SAMPLES" ] || {
    echo "STARTUP_MEASUREMENT: FAIL label=$label mode=$mode workload=$key samples=$count" >&2
    exit 21
  }
}

run_warmup_steady() {
  local label=$1 image=$2 mode=$3 key=$4 source=$5 expected=$6
  local -a props=()
  while IFS= read -r -d '' x; do props+=("$x"); done < <(mode_args "$mode")
  local safe=${key//\//__}
  local stdout="$OUT/raw/execution-${label}-${mode}-${safe}.tsv"
  local stderr="$OUT/raw/execution-${label}-${mode}-${safe}.stderr"

  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" \
    "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED \
    "${props[@]}" \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.MeasurementDriver \
    "/opt/protos/$source" "$expected" "$WARMUP_ITERATIONS" "$STEADY_SAMPLES" \
    >"$stdout" 2>"$stderr"

  warm=$(awk -F '\t' '$1=="WARMUP" {c++} END {print c+0}' "$stdout")
  steady=$(awk -F '\t' '$1=="STEADY" {c++} END {print c+0}' "$stdout")
  [ "$warm" -eq "$WARMUP_ITERATIONS" ] || {
    echo "WARMUP_MEASUREMENT: FAIL label=$label mode=$mode workload=$key samples=$warm" >&2
    exit 22
  }
  [ "$steady" -eq "$STEADY_SAMPLES" ] || {
    echo "STEADY_MEASUREMENT: FAIL label=$label mode=$mode workload=$key samples=$steady" >&2
    exit 23
  }
}

run_diagnostic() {
  local label=$1 image=$2 key=$3 source=$4 expected=$5
  local safe=${key//\//__}
  local stdout="$OUT/diagnostics/${label}-${safe}.stdout"
  local stderr="$OUT/diagnostics/${label}-${safe}.stderr"

  set +e
  docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$image" \
    "-Xss$STACK" \
    --enable-native-access=ALL-UNNAMED \
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

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$label" "$key" "$rc" "$opt_done" "$opt_failed" "$graph" "$frame" "$deep" "$overflow" \
    >>"$OUT/diagnostics/summary.partial.tsv"
  printf '%s\t%s\n' "$label/$key" "$bootstrap" \
    >>"$OUT/diagnostics/bootstrap.partial.tsv"

  echo "DIAGNOSTIC label=$label workload=$key rc=$rc opt_done=$opt_done opt_failed=$opt_failed graph_too_big=$graph frame_escape=$frame deep_inlining=$deep stack_overflow=$overflow bootstrap_error=$bootstrap"

  # Post-PERF002 must retain the compiler-health property established by PERF002.
  if [ "$label" = "post-perf002" ] && {
       [ "$rc" -ne 0 ] ||
       [ "$opt_failed" -ne 0 ] ||
       [ "$graph" -ne 0 ] ||
       [ "$frame" -ne 0 ] ||
       [ "$deep" -ne 0 ] ||
       [ "$overflow" -ne 0 ] ||
       [ "$bootstrap" -ne 0 ];
  }; then
    tail -100 "$stderr" >&2 || true
    echo "POST_PERF002_DIAGNOSTIC_GUARD: FAIL workload=$key" >&2
    exit 24
  fi
}

printf 'revision_label\tworkload\trc\topt_done\topt_failed\tgraph_too_big\tframe_escape\tdeep_inlining\tstack_overflow\tbootstrap_error\n' \
  >"$OUT/diagnostics/summary.tsv"
: >"$OUT/diagnostics/summary.partial.tsv"
: >"$OUT/diagnostics/bootstrap.partial.tsv"

echo "phase=correctness pre-timing gate"
while IFS=$'\t' read -r key source expected; do
  for mode in interpreter truffle; do
    run_correctness pre-perf002 "$PRE_IMAGE" "$mode" "$key" "$source" "$expected"
    run_correctness post-perf002 "$POST_IMAGE" "$mode" "$key" "$source" "$expected"
  done
done < <(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
for x in cfg["workloads"]:
    print(f"{x['id']}\t{x['source']}\t{x['expected_stdout']}")
PY
)
echo "CORRECTNESS_GATE: PASS"

echo "phase=measurement startup/warmup/steady"
while IFS=$'\t' read -r key source expected; do
  echo "WORKLOAD $key"
  for mode in interpreter truffle; do
    for label in pre-perf002 post-perf002; do
      if [ "$label" = "pre-perf002" ]; then image=$PRE_IMAGE; else image=$POST_IMAGE; fi
      echo "MEASURE label=$label mode=$mode workload=$key"
      run_startup "$label" "$image" "$mode" "$key" "$source" "$expected"
      run_warmup_steady "$label" "$image" "$mode" "$key" "$source" "$expected"
    done
  done
done < <(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
for x in cfg["workloads"]:
    print(f"{x['id']}\t{x['source']}\t{x['expected_stdout']}")
PY
)
echo "STARTUP_MEASUREMENTS: PASS"
echo "WARMUP_CURVES: PASS"
echo "STEADY_STATE_MEASUREMENTS: PASS"

echo "phase=non-timing Truffle diagnostics"
while IFS=$'\t' read -r key source expected; do
  run_diagnostic pre-perf002 "$PRE_IMAGE" "$key" "$source" "$expected"
  run_diagnostic post-perf002 "$POST_IMAGE" "$key" "$source" "$expected"
done < <(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
for x in cfg["workloads"]:
    print(f"{x['id']}\t{x['source']}\t{x['expected_stdout']}")
PY
)

python3 - "$OUT/diagnostics/summary.partial.tsv" "$OUT/diagnostics/bootstrap.partial.tsv" "$OUT/diagnostics/summary.tsv" <<'PY'
import sys
partial, bootstrap, out = sys.argv[1:]
boots={}
for line in open(bootstrap, encoding='utf-8'):
    k,v=line.rstrip('\n').split('\t')
    boots[k]=v
with open(out, 'a', encoding='utf-8') as dst:
    for line in open(partial, encoding='utf-8'):
        fields=line.rstrip('\n').split('\t')
        label,key=fields[0],fields[1]
        dst.write(line.rstrip('\n') + '\t' + boots[f"{label}/{key}"] + '\n')
PY
rm -f "$OUT/diagnostics/summary.partial.tsv" "$OUT/diagnostics/bootstrap.partial.tsv"

# Capture exact environment and image identities outside all timing intervals.
PRE_IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$PRE_IMAGE")
POST_IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$POST_IMAGE")
PRE_DIGESTS=$(docker image inspect --format '{{json .RepoDigests}}' "$PRE_IMAGE")
POST_DIGESTS=$(docker image inspect --format '{{json .RepoDigests}}' "$POST_IMAGE")
GRAAL_ID=$(docker image inspect --format '{{.Id}}' "$GRAAL_BASE")
GRAAL_DIGESTS=$(docker image inspect --format '{{json .RepoDigests}}' "$GRAAL_BASE")
BUILD_ID=$(docker image inspect --format '{{.Id}}' "$BUILD_BASE")
BUILD_DIGESTS=$(docker image inspect --format '{{json .RepoDigests}}' "$BUILD_BASE")
DOCKER_SERVER=$(docker version --format '{{.Server.Version}}')
CPU_MODEL=$(awk -F ': ' '/model name/ {print $2; exit}' /proc/cpuinfo 2>/dev/null || true)
CPU_COUNT=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)
MEM_KB=$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
KERNEL=$(uname -srmo)
ARCH=$(uname -m)
GENERATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

GENERATED_AT="$GENERATED_AT" \
PRE_IMAGE="$PRE_IMAGE" PRE_IMAGE_ID="$PRE_IMAGE_ID" PRE_DIGESTS="$PRE_DIGESTS" \
POST_IMAGE="$POST_IMAGE" POST_IMAGE_ID="$POST_IMAGE_ID" POST_DIGESTS="$POST_DIGESTS" \
GRAAL_ID="$GRAAL_ID" GRAAL_DIGESTS="$GRAAL_DIGESTS" \
BUILD_ID="$BUILD_ID" BUILD_DIGESTS="$BUILD_DIGESTS" \
DOCKER_SERVER="$DOCKER_SERVER" CPU_MODEL="$CPU_MODEL" CPU_COUNT="$CPU_COUNT" \
MEM_KB="$MEM_KB" KERNEL="$KERNEL" ARCH="$ARCH" ALLOWED_LIST="$allowed_list" CPUSET="$CPUSET" \
python3 - "$CONFIG" "$OUT/run-metadata.json" <<'PY'
import json, os, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
record={
  "schema_version": 1,
  "perf_item": "PERF001",
  "slice": "PERF001-D",
  "generated_at": os.environ["GENERATED_AT"],
  "harness_revision": None,
  "revisions": cfg["revisions"],
  "measurement_policy": {
    "startup_samples": cfg["startup_samples"],
    "warmup_iterations": cfg["warmup_iterations"],
    "steady_samples": cfg["steady_samples"],
    "diagnostic_iterations": cfg["diagnostic_iterations"],
    "stack": cfg["stack"],
    "cpu_policy": cfg["cpu_policy"],
    "network_policy": cfg["network_policy"],
    "startup_boundary": "fresh child JVM ProcessBuilder.start() through child exit, from a driver already running inside the container; Docker container creation/start is excluded",
    "warmup_boundary": "same compiled Protos CallTarget, fresh module activation per equivalent iteration; bootstrap/source read/parse/lower are outside each timed interval",
    "steady_boundary": "same JVM and CallTarget after the retained warmup curve; fresh module activation is constructed before each timed guest call",
    "diagnostic_boundary": "separate non-timing run with TraceCompilation enabled; diagnostic data is never used as timing samples",
    "aggregation": "median primary; MAD, min, max, p95 secondary; raw samples retained",
  },
  "runtime": {
    "graal_base": cfg["graal_base"],
    "graal_base_id": os.environ["GRAAL_ID"],
    "graal_base_repo_digests": json.loads(os.environ["GRAAL_DIGESTS"]),
    "build_base": cfg["build_base"],
    "build_base_id": os.environ["BUILD_ID"],
    "build_base_repo_digests": json.loads(os.environ["BUILD_DIGESTS"]),
    "truffle_runtime_version": cfg["truffle_runtime_version"],
    "images": {
      "pre-perf002": {
        "tag": os.environ["PRE_IMAGE"],
        "id": os.environ["PRE_IMAGE_ID"],
        "repo_digests": json.loads(os.environ["PRE_DIGESTS"]),
      },
      "post-perf002": {
        "tag": os.environ["POST_IMAGE"],
        "id": os.environ["POST_IMAGE_ID"],
        "repo_digests": json.loads(os.environ["POST_DIGESTS"]),
      },
    },
  },
  "environment": {
    "platform": "linux",
    "architecture": os.environ["ARCH"],
    "kernel": os.environ["KERNEL"],
    "cpu_model": os.environ["CPU_MODEL"],
    "cpu_count": int(os.environ["CPU_COUNT"]),
    "memory_bytes": int(os.environ["MEM_KB"]) * 1024,
    "cpus_allowed_list": os.environ["ALLOWED_LIST"],
    "cpuset": os.environ["CPUSET"],
    "docker_server_version": os.environ["DOCKER_SERVER"],
  },
}
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(record, fh, indent=2)
    fh.write("\n")
PY

echo "PERF001_D_MEASUREMENT: PASS"
echo "OUTPUT_DIR=$OUT"
