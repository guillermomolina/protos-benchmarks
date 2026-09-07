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
RUN=${1:-}
MODE=${2:-run}

[ -n "$RUN" ] || {
    echo "usage: scripts/perf003a_structural_resume.sh <existing-run-dir> [--status]" >&2
    exit 2
}
case "$MODE" in
    run|'') ;;
    --status) ;;
    *)
        echo "unknown mode: $MODE" >&2
        exit 2
        ;;
esac

[ -d "$RUN" ] || {
    echo "RUN_PRECONDITION: missing run directory: $RUN" >&2
    exit 3
}
RUN=$(CDPATH= cd -- "$RUN" && pwd)

CONFIG="$ROOT/config/perf003a-structural.json"
DUMPS="$RUN/graal_dumps"
EXPORT_ROOT="$RUN/igv_json"
ANALYZER_IMAGE=${PROTOS_IGV_ANALYZER_IMAGE:-protos-benchmarks/igv-analyzer:graal-24.0.0}
RESERVE_BYTES=${PERF003A_RESUME_RESERVE_BYTES:-5368709120}
ESTIMATE_MULTIPLIER=${PERF003A_RESUME_ESTIMATE_MULTIPLIER:-16}
MARKER_VERSION=1

for value_name in RESERVE_BYTES ESTIMATE_MULTIPLIER; do
    value=${!value_name}
    case "$value" in
        ''|*[!0-9]*)
            echo "CONFIG_PRECONDITION: $value_name must be a non-negative integer" >&2
            exit 4
            ;;
    esac
done
[ "$ESTIMATE_MULTIPLIER" -gt 0 ] || {
    echo "CONFIG_PRECONDITION: ESTIMATE_MULTIPLIER must be greater than zero" >&2
    exit 4
}

command -v python3 >/dev/null 2>&1 || {
    echo "ENVIRONMENT_LIMITATION: python3 is required" >&2
    exit 4
}

eval "$(
python3 - "$CONFIG" <<'PY'
import json
import shlex
import sys

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
print("EXPECTED=" + shlex.quote(str(cfg["workload"]["expected"])))
print("WORKLOAD=" + shlex.quote(cfg["workload"]["id"]))
PY
)"

for required in \
    "$RUN/correctness.stdout" \
    "$RUN/structural.stdout" \
    "$RUN/structural.stderr" \
    "$RUN/runtime-class.txt"
do
    [ -f "$required" ] || {
        echo "RUN_PRECONDITION: missing $(basename "$required")" >&2
        exit 5
    }
done

actual=$(awk 'NF {x=$0} END {print x}' "$RUN/correctness.stdout")
[ "$actual" = "$EXPECTED" ] || {
    echo "CORRECTNESS_PRECONDITION: FAIL expected=$EXPECTED actual=${actual:-<empty>}" >&2
    exit 6
}
grep -q 'HotSpotTruffleRuntime' "$RUN/runtime-class.txt" || {
    echo "OPTIMIZING_RUNTIME_PRECONDITION: FAIL" >&2
    exit 7
}
[ -d "$DUMPS" ] || {
    echo "BGV_PRECONDITION: missing graal_dumps directory" >&2
    exit 8
}

mapfile -d '' -t bgv_files < <(
    find "$DUMPS" -type f -name '*.bgv' -print0 | sort -z
)
[ "${#bgv_files[@]}" -gt 0 ] || {
    echo "BGV_PRECONDITION: no BGV files found" >&2
    exit 8
}

mkdir -p "$EXPORT_ROOT"

job_key() {
    local rel=$1
    local digest
    digest=$(printf '%s' "$rel" | sha256sum)
    printf '%s\n' "${digest%% *}"
}

json_counts() {
    local job=$1
    python3 - "$job" <<'PY'
from pathlib import Path
import sys

job = Path(sys.argv[1])
files = [
    p for p in job.iterdir()
    if p.is_file() and p.name.startswith("input_") and p.name.endswith(".json")
]
nonempty = sum(1 for p in files if p.stat().st_size > 0)
total_bytes = sum(p.stat().st_size for p in files)
print(len(files), nonempty, total_bytes)
PY
}

marker_valid() {
    local marker=$1
    local rel=$2
    local size=$3
    local mtime=$4
    local job=$5

    [ -f "$marker" ] || return 1
    grep -qxF "version=$MARKER_VERSION" "$marker" || return 1
    grep -qxF "source_rel=$rel" "$marker" || return 1
    grep -qxF "source_size=$size" "$marker" || return 1
    grep -qxF "source_mtime=$mtime" "$marker" || return 1

    local expected_count
    expected_count=$(awk -F= '$1=="json_count" {print $2}' "$marker")
    case "$expected_count" in
        ''|*[!0-9]*) return 1 ;;
    esac

    local total nonempty bytes
    read -r total nonempty bytes < <(json_counts "$job")
    [ "$total" -gt 0 ] &&
    [ "$total" -eq "$nonempty" ] &&
    [ "$total" -eq "$expected_count" ]
}

remove_partial_json() {
    local job=$1
    find "$job" -maxdepth 1 -type f -name 'input_*.json' -delete
}

total=${#bgv_files[@]}
completed=0
pending=0
json_files=0
json_bytes=0
bgv_bytes=0

for bgv in "${bgv_files[@]}"; do
    rel=${bgv#"$RUN/"}
    size=$(stat -c '%s' "$bgv")
    mtime=$(stat -c '%Y' "$bgv")
    bgv_bytes=$((bgv_bytes + size))
    key=$(job_key "$rel")
    job="$EXPORT_ROOT/$key"
    marker="$job/complete.marker"
    mkdir -p "$job"

    if marker_valid "$marker" "$rel" "$size" "$mtime" "$job"; then
        completed=$((completed + 1))
        read -r count nonempty bytes < <(json_counts "$job")
        json_files=$((json_files + count))
        json_bytes=$((json_bytes + bytes))
    else
        pending=$((pending + 1))
    fi
done

available_bytes=$(LC_ALL=C df -PB1 "$RUN" | awk 'NR==2 {print $4}')

echo "PERF003-A2 resumable IGV export"
echo "run_dir=$RUN"
echo "workload=$WORKLOAD"
echo "bgv_total=$total"
echo "bgv_bytes=$bgv_bytes"
echo "completed=$completed"
echo "pending=$pending"
echo "json_files=$json_files"
echo "json_bytes=$json_bytes"
echo "available_bytes=$available_bytes"
echo "disk_reserve_bytes=$RESERVE_BYTES"
echo "per_bgv_estimate_multiplier=$ESTIMATE_MULTIPLIER"

if [ "$MODE" = "--status" ]; then
    echo "PERF003A_STRUCTURAL_RESUME_STATUS: PASS"
    exit 0
fi

command -v docker >/dev/null 2>&1 || {
    echo "ENVIRONMENT_LIMITATION: docker is required" >&2
    exit 9
}

if ! docker image inspect "$ANALYZER_IMAGE" >/dev/null 2>&1; then
    echo "IGV_ANALYZER_IMAGE: MISSING; building isolated analyzer"
    "$ROOT/scripts/igv_analyzer.sh" build
fi
"$ROOT/scripts/igv_analyzer.sh" smoke
echo "IGV_ANALYZER_READY: PASS"

converted=0
skipped=0
index=0

for bgv in "${bgv_files[@]}"; do
    index=$((index + 1))
    rel=${bgv#"$RUN/"}
    size=$(stat -c '%s' "$bgv")
    mtime=$(stat -c '%Y' "$bgv")
    key=$(job_key "$rel")
    job="$EXPORT_ROOT/$key"
    marker="$job/complete.marker"
    input="$job/input.bgv"
    log="$job/export.log"

    mkdir -p "$job"

    if marker_valid "$marker" "$rel" "$size" "$mtime" "$job"; then
        read -r count nonempty bytes < <(json_counts "$job")
        skipped=$((skipped + 1))
        echo "IGV_RESUME_ITEM: SKIP index=$index/$total json_count=$count bgv=$rel"
        continue
    fi

    rm -f "$marker"
    remove_partial_json "$job"

    target=$(realpath --relative-to="$job" "$bgv")
    if [ -L "$input" ]; then
        [ "$(readlink "$input")" = "$target" ] || {
            rm -f "$input"
            ln -s "$target" "$input"
        }
    elif [ -e "$input" ]; then
        echo "JOB_PRECONDITION: unexpected non-symlink input: $input" >&2
        exit 10
    else
        ln -s "$target" "$input"
    fi

    free_bytes=$(LC_ALL=C df -PB1 "$RUN" | awk 'NR==2 {print $4}')
    estimated_json=$((size * ESTIMATE_MULTIPLIER))
    required_free=$((estimated_json + RESERVE_BYTES))
    if [ "$free_bytes" -lt "$required_free" ]; then
        echo "IGV_RESUME_DISK_GUARD: BLOCKED index=$index/$total free_bytes=$free_bytes estimated_json_bytes=$estimated_json reserve_bytes=$RESERVE_BYTES bgv=$rel" >&2
        echo "RESUME_PRESERVED: YES completed=$((converted + skipped))/$total" >&2
        exit 50
    fi

    : >"$log"
    set +e
    (
        cd "$RUN"
        "$ROOT/scripts/igv_analyzer.sh" analyze "igv_json/$key/input.bgv"
    ) >"$log" 2>&1
    rc=$?
    set -e

    if [ "$rc" -ne 0 ]; then
        remove_partial_json "$job"
        echo "IGV_RESUME_ITEM: FAIL index=$index/$total rc=$rc bgv=$rel" >&2
        tail -60 "$log" >&2 || true
        echo "RESUME_PRESERVED: YES completed=$((converted + skipped))/$total" >&2
        exit 40
    fi

    read -r count nonempty bytes < <(json_counts "$job")
    if [ "$count" -eq 0 ] || [ "$count" -ne "$nonempty" ]; then
        remove_partial_json "$job"
        echo "IGV_RESUME_ITEM: FAIL index=$index/$total invalid_json_outputs count=$count nonempty=$nonempty bgv=$rel" >&2
        tail -60 "$log" >&2 || true
        echo "RESUME_PRESERVED: YES completed=$((converted + skipped))/$total" >&2
        exit 41
    fi

    tmp_marker="$marker.tmp.$$"
    cat >"$tmp_marker" <<EOF
version=$MARKER_VERSION
source_rel=$rel
source_size=$size
source_mtime=$mtime
json_count=$count
json_bytes=$bytes
EOF
    mv "$tmp_marker" "$marker"

    converted=$((converted + 1))
    echo "IGV_RESUME_ITEM: PASS index=$index/$total json_count=$count json_bytes=$bytes bgv=$rel"
done

final_completed=0
final_json_files=0
final_json_bytes=0
for bgv in "${bgv_files[@]}"; do
    rel=${bgv#"$RUN/"}
    size=$(stat -c '%s' "$bgv")
    mtime=$(stat -c '%Y' "$bgv")
    key=$(job_key "$rel")
    job="$EXPORT_ROOT/$key"
    marker="$job/complete.marker"
    marker_valid "$marker" "$rel" "$size" "$mtime" "$job" || {
        echo "FINAL_COMPLETION_CHECK: FAIL bgv=$rel" >&2
        exit 42
    }
    read -r count nonempty bytes < <(json_counts "$job")
    final_completed=$((final_completed + 1))
    final_json_files=$((final_json_files + count))
    final_json_bytes=$((final_json_bytes + bytes))
done

echo "IGV_JSON_EXPORT_RESUME: PASS"
echo "bgv_completed=$final_completed"
echo "bgv_converted_this_run=$converted"
echo "bgv_skipped_this_run=$skipped"
echo "json_files=$final_json_files"
echo "json_bytes=$final_json_bytes"
echo "BGV_RECAPTURED: NO"
echo "STRUCTURAL_EXECUTION_REPEATED: NO"
echo "PERF003A_STRUCTURAL_RESUME: PASS"
echo "NEXT=PERF003-A3 structural summary/publication"
