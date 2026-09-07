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
[ -n "$OUT" ] || {
    echo "usage: scripts/perf003a_structural.sh <output-dir>" >&2
    exit 2
}
OUT=$(mkdir -p "$(dirname -- "$OUT")" && CDPATH= cd -- "$(dirname -- "$OUT")" && pwd)/$(basename -- "$OUT")
[ ! -e "$OUT" ] || {
    echo "OUTPUT_PRECONDITION: output path already exists: $OUT" >&2
    exit 3
}
mkdir -p "$OUT/graal_dumps"

CONFIG="$ROOT/config/perf003a-structural.json"
command -v docker >/dev/null 2>&1 || {
    echo "ENVIRONMENT_LIMITATION: docker is required" >&2
    exit 4
}
command -v python3 >/dev/null 2>&1 || {
    echo "ENVIRONMENT_LIMITATION: python3 is required" >&2
    exit 4
}

eval "$(
python3 - "$CONFIG" <<'PY'
import json, shlex, sys
cfg=json.load(open(sys.argv[1], encoding="utf-8"))
w=cfg["workload"]
pairs={
    "PROTOS_REVISION":cfg["protos_revision"],
    "PROTOS_VERSION":cfg["protos_implementation_version"],
    "BUILD_BASE":cfg["build_base"],
    "GRAAL_BASE":cfg["graal_base"],
    "TRUFFLE_VERSION":cfg["truffle_runtime_version"],
    "STACK":cfg["protos_stack"],
    "ITERATIONS":str(cfg["diagnostic_iterations"]),
    "SOURCE":w["protos"],
    "EXPECTED":str(w["expected"]),
    "WORKLOAD":w["id"],
    "DUMP":cfg["graal_dump"],
    "EXPANSION_TIER":cfg["expansion_tier"],
}
for k,v in pairs.items():
    print(f"{k}={shlex.quote(v)}")
PY
)"

HARNESS_REVISION=$(git -C "$ROOT" rev-parse HEAD)
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

echo "PERF003-A structural Truffle/Graal diagnostic"
echo "HARNESS_REVISION=$HARNESS_REVISION"
echo "PROTOS_REVISION=$PROTOS_REVISION"
echo "PROTOS_VERSION=$PROTOS_VERSION"
echo "WORKLOAD=$WORKLOAD"
echo "CPUSET=$CPUSET"

PROTOS_IMAGE="protos-benchmarks-perf003a-structural:${PROTOS_REVISION:0:12}"
ANALYZER_IMAGE=${PROTOS_IGV_ANALYZER_IMAGE:-protos-benchmarks/igv-analyzer:graal-24.0.0}

echo "phase=01 ensure exact runtime + analyzer"
docker pull "$BUILD_BASE" >/dev/null
docker pull "$GRAAL_BASE" >/dev/null
docker build \
    --build-arg BUILD_BASE="$BUILD_BASE" \
    --build-arg GRAAL_BASE="$GRAAL_BASE" \
    --build-arg PROTOS_REVISION="$PROTOS_REVISION" \
    --build-arg TRUFFLE_RUNTIME_VERSION="$TRUFFLE_VERSION" \
    -t "$PROTOS_IMAGE" \
    -f "$ROOT/docker/protos-perf001e/Dockerfile" \
    "$ROOT/docker/protos-perf001e" \
    >"$OUT/build-protos.stdout" 2>"$OUT/build-protos.stderr"

if ! docker image inspect "$ANALYZER_IMAGE" >/dev/null 2>&1; then
    echo "IGV analyzer image missing; building isolated analyzer"
    "$ROOT/scripts/igv_analyzer.sh" build
fi
"$ROOT/scripts/igv_analyzer.sh" smoke
echo "IGV_ANALYZER_READY: PASS"

runtime_class=$(
    docker run --rm --network none --cpuset-cpus "$CPUSET" \
        --entrypoint java "$PROTOS_IMAGE" \
        --enable-native-access=ALL-UNNAMED \
        -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
        com.guillermomolina.protos.cli.RuntimeProbe
)
case "$runtime_class" in
    *HotSpotTruffleRuntime*) ;;
    *)
        echo "OPTIMIZING_RUNTIME_CHECK: FAIL class=$runtime_class" >&2
        exit 10
        ;;
esac
printf '%s\n' "$runtime_class" >"$OUT/runtime-class.txt"
echo "OPTIMIZING_RUNTIME_CHECK: PASS class=$runtime_class"

echo "phase=02 correctness gate"
set +e
docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" \
    "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
    -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.DiagnosticEval \
    "/opt/protos/$SOURCE" >"$OUT/correctness.stdout" 2>"$OUT/correctness.stderr"
rc=$?
set -e
actual=$(awk 'NF {x=$0} END {print x}' "$OUT/correctness.stdout")
if [ "$rc" -ne 0 ] || [ "$actual" != "$EXPECTED" ]; then
    echo "CORRECTNESS: FAIL rc=$rc expected=$EXPECTED actual=${actual:-<empty>}" >&2
    tail -100 "$OUT/correctness.stderr" >&2 || true
    exit 20
fi
echo "CORRECTNESS: PASS result=$actual"

echo "phase=03 structural diagnostic with BGV + expansion statistics"
set +e
docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --user "$(id -u):$(id -g)" \
    --volume "$OUT:/diag-out" \
    --entrypoint java "$PROTOS_IMAGE" \
    "-Xss$STACK" --enable-native-access=ALL-UNNAMED \
    -Dpolyglot.engine.AllowExperimentalOptions=true \
    -Dpolyglot.engine.BackgroundCompilation=false \
    -Dpolyglot.engine.TraceCompilation=true \
    "-Dpolyglot.engine.MethodExpansionStatistics=$EXPANSION_TIER" \
    "-Dpolyglot.engine.NodeExpansionStatistics=$EXPANSION_TIER" \
    "-Dpolyglot.engine.TraceMethodExpansion=$EXPANSION_TIER" \
    "-Dpolyglot.engine.TraceNodeExpansion=$EXPANSION_TIER" \
    -Dpolyglot.engine.NodeSourcePositions=true \
    -Dpolyglot.engine.TracePerformanceWarnings=all \
    "-Djdk.graal.Dump=$DUMP" \
    -Djdk.graal.DumpPath=/diag-out/graal_dumps \
    -Djdk.graal.PrintGraph=File \
    -Djdk.graal.ShowDumpFiles=true \
    -cp '/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar' \
    com.guillermomolina.protos.cli.MeasurementDriver \
    "/opt/protos/$SOURCE" "$EXPECTED" "$ITERATIONS" 0 \
    >"$OUT/structural.stdout" 2>"$OUT/structural.stderr"
rc=$?
set -e

if [ "$rc" -ne 0 ]; then
    echo "STRUCTURAL_EXECUTION: FAIL rc=$rc" >&2
    tail -200 "$OUT/structural.stderr" >&2 || true
    exit 30
fi
echo "STRUCTURAL_EXECUTION: PASS"

mapfile -d '' -t bgv_files < <(find "$OUT/graal_dumps" -type f -name '*.bgv' -print0 | sort -z)
[ "${#bgv_files[@]}" -gt 0 ] || {
    echo "BGV_CAPTURE: FAIL no .bgv files generated" >&2
    tail -200 "$OUT/structural.stderr" >&2 || true
    exit 31
}
echo "BGV_CAPTURE: PASS count=${#bgv_files[@]}"

echo "phase=04 isolated IGV JSON export"
export_log="$OUT/igv-export.log"
: >"$export_log"
for bgv in "${bgv_files[@]}"; do
    rel=${bgv#"$OUT/"}
    (
        cd "$OUT"
        "$ROOT/scripts/igv_analyzer.sh" analyze "$rel"
    ) >>"$export_log" 2>&1
done

json_count=$(find "$OUT/graal_dumps" -type f -name '*.json' | wc -l)
[ "$json_count" -gt 0 ] || {
    echo "IGV_JSON_EXPORT: FAIL exporter produced no JSON" >&2
    cat "$export_log" >&2
    exit 32
}
echo "IGV_JSON_EXPORT: PASS count=$json_count"

echo "phase=05 compact structural attribution"
python3 "$ROOT/scripts/perf003a_structural_summary.py" \
    --config "$CONFIG" \
    --run-dir "$OUT" \
    --harness-revision "$HARNESS_REVISION"

docker image inspect "$PROTOS_IMAGE" >"$OUT/evidence/runtime-image.json"
docker image inspect "$ANALYZER_IMAGE" >"$OUT/evidence/igv-analyzer-image.json"
docker --version >"$OUT/evidence/docker-version.txt"
java_version_tmp="$OUT/java-version"
docker run --rm --network none --cpuset-cpus "$CPUSET" \
    --entrypoint java "$PROTOS_IMAGE" -version \
    >"${java_version_tmp}.stdout" 2>"${java_version_tmp}.stderr"
mv "${java_version_tmp}.stdout" "$OUT/evidence/java-version.stdout"
mv "${java_version_tmp}.stderr" "$OUT/evidence/java-version.stderr"

cat >"$OUT/evidence/run-identity.txt" <<EOF
harness_revision=$HARNESS_REVISION
protos_revision=$PROTOS_REVISION
protos_version=$PROTOS_VERSION
workload=$WORKLOAD
expected=$EXPECTED
runtime_image=$PROTOS_IMAGE
analyzer_image=$ANALYZER_IMAGE
cpuset=$CPUSET
stack=$STACK
diagnostic_iterations=$ITERATIONS
graal_dump=$DUMP
expansion_tier=$EXPANSION_TIER
network=disabled
timing_evidence=NO
EOF

echo "PERF003A_STRUCTURAL_DIAGNOSTIC: PASS"
echo "RAW_ARTIFACTS=$OUT"
echo "COMPACT_EVIDENCE=$OUT/evidence"
cat "$OUT/evidence/summary.txt"
