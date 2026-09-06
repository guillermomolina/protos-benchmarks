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
[ -n "$OUT" ] || { echo "usage: scripts/perf002b_validate.sh <output-dir>" >&2; exit 2; }

CONFIG="$ROOT/config/perf002.json"
mkdir -p "$OUT/raw"
rm -f "$OUT/summary.tsv" "$OUT/run.json" "$OUT/environment.txt"

command -v docker >/dev/null 2>&1 || {
    echo "ENVIRONMENT_LIMITATION: docker is required for PERF002-B" >&2
    exit 3
}
command -v python3 >/dev/null 2>&1 || {
    echo "ENVIRONMENT_LIMITATION: python3 is required for PERF002-B" >&2
    exit 3
}

eval "$(
python3 - "$CONFIG" <<'PY'
import json, shlex, sys
cfg = json.load(open(sys.argv[1], encoding='utf-8'))
pairs = {
    'PROTOS_REVISION': cfg['protos_revision'],
    'PROTOS_REPOSITORY': cfg['protos_repository'],
    'BUILD_BASE': cfg['build_base'],
    'GRAAL_BASE': cfg['graal_base'],
    'TRUFFLE_VERSION': cfg['truffle_runtime_version'],
    'STACK': cfg['stack'],
}
for key, value in pairs.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
)"

IMAGE="protos-benchmarks-perf002b:${PROTOS_REVISION:0:12}"

allowed_list=$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status 2>/dev/null || true)
if [ -z "$allowed_list" ]; then
    allowed_list="0"
fi
first_cpu=$(
python3 - "$allowed_list" <<'PY'
import sys
first = sys.argv[1].split(',')[0]
print(first.split('-')[0])
PY
)
CPUSET="$first_cpu"

echo "PERF002-B external Truffle validation"
echo "PROTOS_REVISION=$PROTOS_REVISION"
echo "TRUFFLE_RUNTIME=$TRUFFLE_VERSION"
echo "STACK=-Xss$STACK"
echo "CPUSET=$CPUSET"
echo "PUBLICATION: NONE"

docker pull "$BUILD_BASE" >/dev/null
docker pull "$GRAAL_BASE" >/dev/null

docker build \
    --build-arg BUILD_BASE="$BUILD_BASE" \
    --build-arg GRAAL_BASE="$GRAAL_BASE" \
    --build-arg PROTOS_REPOSITORY="$PROTOS_REPOSITORY" \
    --build-arg PROTOS_REVISION="$PROTOS_REVISION" \
    --build-arg TRUFFLE_RUNTIME_VERSION="$TRUFFLE_VERSION" \
    -t "$IMAGE" \
    -f "$ROOT/docker/protos-perf002/Dockerfile" \
    "$ROOT/docker/protos-perf002" \
    >"$OUT/raw/image-build.stdout" 2>"$OUT/raw/image-build.stderr"

image_id=$(docker image inspect --format '{{.Id}}' "$IMAGE")
image_digests=$(docker image inspect --format '{{json .RepoDigests}}' "$IMAGE")
graal_id=$(docker image inspect --format '{{.Id}}' "$GRAAL_BASE")
graal_digests=$(docker image inspect --format '{{json .RepoDigests}}' "$GRAAL_BASE")
build_id=$(docker image inspect --format '{{.Id}}' "$BUILD_BASE")
build_digests=$(docker image inspect --format '{{json .RepoDigests}}' "$BUILD_BASE")

docker --version >"$OUT/raw/docker-version.txt"
docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$IMAGE" -version \
    >"$OUT/raw/java-version.stdout" 2>"$OUT/raw/java-version.stderr"

runtime_class=$(
    docker run --rm --network none --cpuset-cpus "$CPUSET" \
        --entrypoint java "$IMAGE" \
        --enable-native-access=ALL-UNNAMED \
        -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
        com.guillermomolina.protos.cli.RuntimeProbe
)
echo "$runtime_class" >"$OUT/raw/truffle-runtime-class.txt"
case "$runtime_class" in
    *HotSpotTruffleRuntime*) ;;
    *)
        echo "OPTIMIZING_RUNTIME_CHECK: FAIL class=$runtime_class" >&2
        exit 10
        ;;
esac
echo "OPTIMIZING_RUNTIME_CHECK: PASS class=$runtime_class"

printf 'class\tkey\tmode\trepeat\tsource\texpected\tactual\trc\topt_done\topt_failed\tgraph_too_big\tframe_escape\tdeep_inlining\tstack_overflow\tbootstrap_error\n' \
    >"$OUT/summary.tsv"

run_case() {
    local class=$1 key=$2 source=$3 expected=$4 mode=$5 repeat=${6:-1}
    local safe=${key//\//__}
    local stdout="$OUT/raw/${class}-${safe}-${mode}-r${repeat}.stdout"
    local stderr="$OUT/raw/${class}-${safe}-${mode}-r${repeat}.stderr"
    local source_in_container="/opt/protos/$source"
    local -a args=(
        docker run --rm --network none --cpuset-cpus "$CPUSET"
        --entrypoint java "$IMAGE"
        "-Xss$STACK"
        --enable-native-access=ALL-UNNAMED
        -Dpolyglot.engine.AllowExperimentalOptions=true
    )

    if [ "$mode" = "interpreter" ]; then
        args+=(-Dpolyglot.engine.Compilation=false)
    else
        args+=(
            -Dpolyglot.engine.BackgroundCompilation=false
            -Dpolyglot.engine.TraceCompilation=true
        )
    fi

    args+=(
        -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar'
        com.guillermomolina.protos.cli.DiagnosticEval
        "$source_in_container"
    )

    set +e
    "${args[@]}" >"$stdout" 2>"$stderr"
    local rc=$?
    set -e

    local actual opt_done opt_failed graph frame deep stack boot
    actual=$(awk 'NF {x=$0} END {print x}' "$stdout")
    opt_done=$(grep -ci 'opt done' "$stderr" || true)
    opt_failed=$(grep -ci 'opt failed' "$stderr" || true)
    graph=$(grep -ci 'GraphTooBig' "$stderr" || true)
    frame=$(grep -ci 'FrameWithoutBoxing' "$stderr" || true)
    deep=$(grep -ci 'Too deep inlining' "$stderr" || true)
    stack=$(grep -ci 'StackOverflowError' "$stderr" || true)
    boot=$(grep -ci 'BootstrapMethodError' "$stderr" || true)

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$class" "$key" "$mode" "$repeat" "$source" "$expected" "${actual:-<empty>}" \
        "$rc" "$opt_done" "$opt_failed" "$graph" "$frame" "$deep" "$stack" "$boot" \
        >>"$OUT/summary.tsv"

    echo "CASE class=$class key=$key mode=$mode repeat=$repeat rc=$rc actual=${actual:-<empty>} expected=$expected opt_done=$opt_done opt_failed=$opt_failed graph_too_big=$graph frame_escape=$frame deep_inlining=$deep stack_overflow=$stack bootstrap_error=$boot"

    if [ "$rc" -ne 0 ] || [ "$actual" != "$expected" ]; then
        tail -80 "$stderr" >&2 || true
        return 20
    fi

    if [ "$mode" = "truffle" ] && {
        [ "$opt_failed" -ne 0 ] ||
        [ "$graph" -ne 0 ] ||
        [ "$frame" -ne 0 ] ||
        [ "$deep" -ne 0 ] ||
        [ "$stack" -ne 0 ] ||
        [ "$boot" -ne 0 ];
    }; then
        tail -100 "$stderr" >&2 || true
        return 21
    fi
}

while IFS=$'\t' read -r key source expected; do
    for mode in interpreter truffle; do
        run_case semantic "$key" "$source" "$expected" "$mode"
    done
done < <(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
for x in cfg['semantic_smoke']:
    print(f"{x['id']}\t{x['source']}\t{x['expected_stdout']}")
PY
)
echo "SEMANTIC_SMOKE: PASS"

while IFS=$'\t' read -r key source expected; do
    for mode in interpreter truffle; do
        run_case workload "$key" "$source" "$expected" "$mode"
    done
done < <(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
for x in cfg['workloads']:
    print(f"{x['id']}\t{x['source']}\t{x['expected_stdout']}")
PY
)

stability_runs=$(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
print(cfg['stability_policy']['consecutive_runs'])
PY
)
echo "phase=stability polymorphic-dispatch ${stability_runs}x"
stability_source=$(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
target=cfg['stability_policy']['workload']
for x in cfg['workloads']:
    if x['id'] == target:
        print(x['source'])
        break
else:
    raise SystemExit(1)
PY
)
stability_expected=$(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding='utf-8'))
target=cfg['stability_policy']['workload']
for x in cfg['workloads']:
    if x['id'] == target:
        print(x['expected_stdout'])
        break
else:
    raise SystemExit(1)
PY
)

# Canonical r1 already ran above. Require nine additional fresh JVM/container
# executions so the retained evidence contains ten consecutive Truffle passes.
for ((repeat=2; repeat<=stability_runs; repeat++)); do
    run_case stability "runtime/polymorphic-dispatch"         "$stability_source" "$stability_expected" truffle "$repeat"
done

poly_passes=$(
    awk -F '\t' '
      NR > 1 &&
      (($1 == "workload" && $2 == "runtime/polymorphic-dispatch" && $3 == "truffle" && $4 == "1") ||
       ($1 == "stability" && $2 == "runtime/polymorphic-dispatch" && $3 == "truffle")) &&
      $7 == "15000" && $8 == "0" && $10 == "0" && $11 == "0" &&
      $12 == "0" && $13 == "0" && $14 == "0" && $15 == "0" {count++}
      END {print count+0}
    ' "$OUT/summary.tsv"
)
[ "$poly_passes" -eq "$stability_runs" ] || {
    echo "POLYMORPHIC_TRUFFLE_STABILITY: FAIL pass=$poly_passes total=$stability_runs" >&2
    exit 24
}
echo "POLYMORPHIC_TRUFFLE_STABILITY: PASS pass=$poly_passes total=$stability_runs stack=-Xss$STACK"

truffle_opt_done_total=$(
    awk -F '	' 'NR > 1 && $3 == "truffle" {s += $9} END {print s+0}' "$OUT/summary.tsv"
)
truffle_opt_failed_total=$(
    awk -F '	' 'NR > 1 && $3 == "truffle" {s += $10} END {print s+0}' "$OUT/summary.tsv"
)

[ "$truffle_opt_done_total" -gt 0 ] || {
    echo "TRUFFLE_COMPILATION_ACTIVITY: FAIL opt_done_total=0" >&2
    exit 22
}
[ "$truffle_opt_failed_total" -eq 0 ] || {
    echo "TRUFFLE_COMPILATION_ACTIVITY: FAIL opt_failed_total=$truffle_opt_failed_total" >&2
    exit 23
}

cpu_model=$(awk -F ': ' '/model name/ {print $2; exit}' /proc/cpuinfo 2>/dev/null || true)
logical_cpus=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo unknown)
mem_kb=$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo unknown)
kernel=$(uname -srmo)
arch=$(uname -m)
generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat >"$OUT/environment.txt" <<EOF
generated_at=$generated_at
host_kernel=$kernel
host_arch=$arch
host_cpu_model=$cpu_model
host_logical_cpus=$logical_cpus
host_mem_total_kb=$mem_kb
host_cpus_allowed_list=$allowed_list
validation_cpuset=$CPUSET
docker_image=$IMAGE
docker_image_id=$image_id
docker_image_repo_digests=$image_digests
graal_base=$GRAAL_BASE
graal_base_id=$graal_id
graal_base_repo_digests=$graal_digests
build_base=$BUILD_BASE
build_base_id=$build_id
build_base_repo_digests=$build_digests
truffle_runtime_version=$TRUFFLE_VERSION
truffle_runtime_class=$runtime_class
stack=-Xss$STACK
truffle_opt_done_total=$truffle_opt_done_total
truffle_opt_failed_total=$truffle_opt_failed_total
EOF

GENERATED_AT="$generated_at" \
IMAGE="$IMAGE" IMAGE_ID="$image_id" IMAGE_DIGESTS="$image_digests" \
GRAAL_ID="$graal_id" GRAAL_DIGESTS="$graal_digests" \
BUILD_ID="$build_id" BUILD_DIGESTS="$build_digests" \
CPU_MODEL="$cpu_model" LOGICAL_CPUS="$logical_cpus" MEM_KB="$mem_kb" \
ALLOWED_LIST="$allowed_list" CPUSET="$CPUSET" KERNEL="$kernel" ARCH="$arch" \
RUNTIME_CLASS="$runtime_class" OPT_DONE="$truffle_opt_done_total" \
OPT_FAILED="$truffle_opt_failed_total" \
python3 - "$CONFIG" "$OUT/summary.tsv" "$OUT/run.json" <<'PY'
import csv, json, os, sys
cfg = json.load(open(sys.argv[1], encoding='utf-8'))
with open(sys.argv[2], encoding='utf-8', newline='') as fh:
    cases = list(csv.DictReader(fh, delimiter='\t'))
record = {
    "schema_version": 1,
    "perf_item": "PERF002",
    "slice": "PERF002-B",
    "evidence_class": cfg["evidence_class"],
    "timing_results": False,
    "generated_at": os.environ["GENERATED_AT"],
    "protos_revision": cfg["protos_revision"],
    "protos_implementation_version": cfg["protos_implementation_version"],
    "harness_revision": None,
    "runtime": {
        "graal_base": cfg["graal_base"],
        "graal_base_id": os.environ["GRAAL_ID"],
        "graal_base_repo_digests": json.loads(os.environ["GRAAL_DIGESTS"]),
        "truffle_runtime_version": cfg["truffle_runtime_version"],
        "truffle_runtime_class": os.environ["RUNTIME_CLASS"],
        "stack": cfg["stack"],
        "built_image": os.environ["IMAGE"],
        "built_image_id": os.environ["IMAGE_ID"],
        "built_image_repo_digests": json.loads(os.environ["IMAGE_DIGESTS"]),
        "build_base": cfg["build_base"],
        "build_base_id": os.environ["BUILD_ID"],
        "build_base_repo_digests": json.loads(os.environ["BUILD_DIGESTS"]),
    },
    "host": {
        "kernel": os.environ["KERNEL"],
        "architecture": os.environ["ARCH"],
        "cpu_model": os.environ["CPU_MODEL"],
        "logical_cpus": os.environ["LOGICAL_CPUS"],
        "memory_total_kb": os.environ["MEM_KB"],
        "cpus_allowed_list": os.environ["ALLOWED_LIST"],
        "validation_cpuset": os.environ["CPUSET"],
    },
    "validation": {
        "semantic_smoke_pass": True,
        "canonical_11x2_correctness_pass": True,
        "known_truffle_bailout_guard_pass": True,
        "polymorphic_truffle_stability_pass": True,
        "polymorphic_truffle_stability_runs": cfg["stability_policy"]["consecutive_runs"],
        "truffle_opt_done_total": int(os.environ["OPT_DONE"]),
        "truffle_opt_failed_total": int(os.environ["OPT_FAILED"]),
        "cases": cases,
    },
}
json.dump(record, open(sys.argv[3], 'w', encoding='utf-8'), indent=2)
open(sys.argv[3], 'a', encoding='utf-8').write('\n')
PY

echo "CANONICAL_11X2_CORRECTNESS: PASS"
echo "TRUFFLE_KNOWN_BAILOUT_GUARD: PASS"
echo "TRUFFLE_COMPILATION_ACTIVITY: PASS opt_done_total=$truffle_opt_done_total"
echo "POLYMORPHIC_TRUFFLE_STABILITY: PASS pass=$stability_runs total=$stability_runs stack=-Xss$STACK"
echo "PERF002_B_VALIDATION: PASS"
echo "OUTPUT_DIR=$OUT"
