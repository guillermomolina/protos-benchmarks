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
RESERVE_BYTES=${PERF003A_COMPACT_RESERVE_BYTES:-67108864}

[ -n "$RUN" ] || {
    echo "usage: scripts/perf003a_structural_compact.sh <existing-run-dir> [--status]" >&2
    exit 2
}
case "$MODE" in
    run|'') ;;
    --status) ;;
    *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac

case "$RESERVE_BYTES" in
    ''|*[!0-9]*)
        echo "CONFIG_PRECONDITION: PERF003A_COMPACT_RESERVE_BYTES must be an integer" >&2
        exit 3
        ;;
esac

[ -d "$RUN" ] || {
    echo "RUN_PRECONDITION: missing run directory: $RUN" >&2
    exit 4
}
RUN=$(CDPATH= cd -- "$RUN" && pwd)

CONFIG="$ROOT/config/perf003a-structural.json"
DUMPS="$RUN/graal_dumps"
OUT="$RUN/igv_compact"
MARKER_VERSION=1

eval "$(
python3 - "$CONFIG" <<'PY'
import json, shlex, sys
cfg=json.load(open(sys.argv[1], encoding="utf-8"))
print("EXPECTED=" + shlex.quote(str(cfg["workload"]["expected"])))
print("WORKLOAD=" + shlex.quote(cfg["workload"]["id"]))
PY
)"

mapfile -d '' -t TERMS < <(
python3 - "$CONFIG" <<'PY'
import json, sys
cfg=json.load(open(sys.argv[1], encoding="utf-8"))
for term in cfg["suspect_terms"]:
    sys.stdout.buffer.write(term.encode("utf-8") + b"\0")
PY
)

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
    echo "BGV_PRECONDITION: missing graal_dumps" >&2
    exit 8
}

mapfile -d '' -t BGV_FILES < <(
    find "$DUMPS" -type f -name '*.bgv' -print0 | sort -z
)
[ "${#BGV_FILES[@]}" -gt 0 ] || {
    echo "BGV_PRECONDITION: no BGV files found" >&2
    exit 8
}

mkdir -p "$OUT"

job_key() {
    local rel=$1
    local digest
    digest=$(printf '%s' "$rel" | sha256sum)
    printf '%s\n' "${digest%% *}"
}

summary_valid() {
    local summary=$1
    local terms=${#TERMS[@]}
    [ -s "$summary" ] || return 1
    python3 - "$summary" "$terms" <<'PY'
import json, re, sys
path=sys.argv[1]
expected_terms=int(sys.argv[2])
records=[]
with open(path, encoding="utf-8") as fh:
    for line in fh:
        line=line.strip()
        if line:
            records.append(json.loads(line))
if len(records) < 2:
    raise SystemExit(1)
if records[0].get("kind") != "source":
    raise SystemExit(1)
if not re.fullmatch(r"[0-9a-f]{64}", records[0].get("sha256","")):
    raise SystemExit(1)
totals=[r for r in records if r.get("kind")=="totals"]
terms=[r for r in records if r.get("kind")=="term"]
graphs=[r for r in records if r.get("kind")=="graph"]
if len(totals) != 1 or len(terms) != expected_terms or not graphs:
    raise SystemExit(1)
if totals[0].get("graphs") != len(graphs):
    raise SystemExit(1)
for r in terms:
    if not isinstance(r.get("occurrences"), int) or r["occurrences"] < 0:
        raise SystemExit(1)
PY
}

marker_valid() {
    local marker=$1 rel=$2 size=$3 mtime=$4 summary=$5
    [ -f "$marker" ] || return 1
    grep -qxF "version=$MARKER_VERSION" "$marker" || return 1
    grep -qxF "source_rel=$rel" "$marker" || return 1
    grep -qxF "source_size=$size" "$marker" || return 1
    grep -qxF "source_mtime=$mtime" "$marker" || return 1
    summary_valid "$summary"
}

total=${#BGV_FILES[@]}
completed=0
pending=0
compact_bytes=0

for bgv in "${BGV_FILES[@]}"; do
    rel=${bgv#"$RUN/"}
    size=$(stat -c '%s' "$bgv")
    mtime=$(stat -c '%Y' "$bgv")
    key=$(job_key "$rel")
    job="$OUT/$key"
    marker="$job/complete.marker"
    summary="$job/summary.ndjson"
    mkdir -p "$job"
    if marker_valid "$marker" "$rel" "$size" "$mtime" "$summary"; then
        completed=$((completed + 1))
        compact_bytes=$((compact_bytes + $(stat -c '%s' "$summary")))
    else
        pending=$((pending + 1))
    fi
done

available=$(LC_ALL=C df -PB1 "$RUN" | awk 'NR==2 {print $4}')
echo "PERF003-A3a compact IGV extraction"
echo "run_dir=$RUN"
echo "workload=$WORKLOAD"
echo "bgv_total=$total"
echo "completed=$completed"
echo "pending=$pending"
echo "compact_bytes=$compact_bytes"
echo "available_bytes=$available"
echo "disk_reserve_bytes=$RESERVE_BYTES"

if [ "$MODE" = "--status" ]; then
    echo "PERF003A_COMPACT_STATUS: PASS"
    exit 0
fi

command -v docker >/dev/null 2>&1 || {
    echo "ENVIRONMENT_LIMITATION: docker is required" >&2
    exit 9
}
"$ROOT/scripts/igv_analyzer.sh" smoke
echo "IGV_ANALYZER_READY: PASS"

converted=0
skipped=0
index=0

for bgv in "${BGV_FILES[@]}"; do
    index=$((index + 1))
    rel=${bgv#"$RUN/"}
    size=$(stat -c '%s' "$bgv")
    mtime=$(stat -c '%Y' "$bgv")
    key=$(job_key "$rel")
    job="$OUT/$key"
    marker="$job/complete.marker"
    summary="$job/summary.ndjson"
    tmp="$job/summary.ndjson.tmp"
    log="$job/compact.log"
    mkdir -p "$job"

    if marker_valid "$marker" "$rel" "$size" "$mtime" "$summary"; then
        skipped=$((skipped + 1))
        echo "IGV_COMPACT_ITEM: SKIP index=$index/$total bgv=$rel"
        continue
    fi

    free_bytes=$(LC_ALL=C df -PB1 "$RUN" | awk 'NR==2 {print $4}')
    if [ "$free_bytes" -lt "$RESERVE_BYTES" ]; then
        echo "IGV_COMPACT_DISK_GUARD: BLOCKED free_bytes=$free_bytes reserve_bytes=$RESERVE_BYTES bgv=$rel" >&2
        echo "COMPACT_RESUME_PRESERVED: YES completed=$((converted + skipped))/$total" >&2
        exit 50
    fi

    rm -f "$marker" "$tmp"
    : >"$log"
    set +e
    (
        cd "$RUN"
        "$ROOT/scripts/igv_analyzer.sh" summarize \
            "$rel" \
            "igv_compact/$key/summary.ndjson.tmp" \
            "${TERMS[@]}"
    ) >"$log" 2>&1
    rc=$?
    set -e
    if [ "$rc" -ne 0 ]; then
        rm -f "$tmp"
        echo "IGV_COMPACT_ITEM: FAIL index=$index/$total rc=$rc bgv=$rel" >&2
        tail -60 "$log" >&2 || true
        echo "COMPACT_RESUME_PRESERVED: YES completed=$((converted + skipped))/$total" >&2
        exit 40
    fi

    summary_valid "$tmp" || {
        rm -f "$tmp"
        echo "IGV_COMPACT_ITEM: FAIL index=$index/$total invalid_summary bgv=$rel" >&2
        tail -60 "$log" >&2 || true
        exit 41
    }

    mv "$tmp" "$summary"
    tmp_marker="$marker.tmp.$$"
    cat >"$tmp_marker" <<EOF
version=$MARKER_VERSION
source_rel=$rel
source_size=$size
source_mtime=$mtime
EOF
    mv "$tmp_marker" "$marker"

    totals=$(python3 - "$summary" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    for line in fh:
        r=json.loads(line)
        if r.get("kind")=="totals":
            print(f"graphs={r['graphs']} nodes={r['nodes']} edges={r['edges']}")
            break
PY
)
    converted=$((converted + 1))
    echo "IGV_COMPACT_ITEM: PASS index=$index/$total $totals bgv=$rel"
done

final=0
final_bytes=0
for bgv in "${BGV_FILES[@]}"; do
    rel=${bgv#"$RUN/"}
    size=$(stat -c '%s' "$bgv")
    mtime=$(stat -c '%Y' "$bgv")
    key=$(job_key "$rel")
    job="$OUT/$key"
    marker="$job/complete.marker"
    summary="$job/summary.ndjson"
    marker_valid "$marker" "$rel" "$size" "$mtime" "$summary" || {
        echo "FINAL_COMPACT_CHECK: FAIL bgv=$rel" >&2
        exit 42
    }
    final=$((final + 1))
    final_bytes=$((final_bytes + $(stat -c '%s' "$summary")))
done

echo "PERF003A_COMPACT_EXTRACTION: PASS"
echo "bgv_completed=$final"
echo "bgv_compacted_this_run=$converted"
echo "bgv_skipped_this_run=$skipped"
echo "compact_bytes=$final_bytes"
echo "FULL_JSON_MATERIALIZED: NO"
echo "BGV_RECAPTURED: NO"
echo "STRUCTURAL_EXECUTION_REPEATED: NO"
echo "NEXT=PERF003-A3b aggregate compact structural evidence"
