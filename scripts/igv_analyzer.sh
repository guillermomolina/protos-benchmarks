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
IMAGE=${PROTOS_IGV_ANALYZER_IMAGE:-protos-benchmarks/igv-analyzer:graal-25.3.4.1}
DOCKER=${DOCKER:-docker}

usage() {
    cat <<'USAGE'
Usage:
  scripts/igv_analyzer.sh build
  scripts/igv_analyzer.sh smoke [sample.bgv]
  scripts/igv_analyzer.sh list <igvutil-list-args...>
  scripts/igv_analyzer.sh filter <igvutil-filter-args...>
  scripts/igv_analyzer.sh flatten <igvutil-flatten-args...>

Direct list/filter/flatten arguments are evaluated inside the current working
directory, which is mounted read/write as /work in the analyzer container.
USAGE
}

command=${1:-}

case "$command" in
    build)
        exec "$DOCKER" build \
            --file "$ROOT/docker/igv-analyzer/Dockerfile" \
            --tag "$IMAGE" \
            "$ROOT"
        ;;
    smoke)
        shift
        [ "$#" -le 1 ] || { usage >&2; exit 2; }

        output=$(mktemp)
        tmpdir=
        trap 'rm -f "$output"; [ -z "$tmpdir" ] || rm -rf "$tmpdir"' EXIT

        "$DOCKER" run --rm --network none "$IMAGE" --help >"$output"
        grep -q 'list' "$output"
        grep -q 'filter' "$output"
        grep -q 'flatten' "$output"

        echo "IGV_ANALYZER_CLASS_SMOKE: PASS"

        if [ "$#" -eq 1 ]; then
            sample=$1
            [ -f "$sample" ] || {
                echo "IGV_ANALYZER_REAL_SMOKE: FAIL missing BGV: $sample" >&2
                exit 3
            }

            tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/protos-igv-smoke.XXXXXX")
            cp -- "$sample" "$tmpdir/sample.bgv"

            "$DOCKER" run \
                --rm \
                --network none \
                --user "$(id -u):$(id -g)" \
                --volume "$tmpdir:/work" \
                --workdir /work \
                "$IMAGE" \
                list sample.bgv \
                >/dev/null

            "$DOCKER" run \
                --rm \
                --network none \
                --user "$(id -u):$(id -g)" \
                --volume "$tmpdir:/work" \
                --workdir /work \
                "$IMAGE" \
                filter sample.bgv \
                >"$tmpdir/sample.json"

            python3 - "$tmpdir/sample.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
if path.stat().st_size == 0:
    raise SystemExit("IGV analyzer produced empty JSON")
with path.open(encoding="utf-8") as fh:
    json.load(fh)
PY
            echo "IGV_ANALYZER_REAL_SMOKE: PASS"
        fi

        echo "IGV_ANALYZER_SMOKE: PASS"
        ;;
    list|filter|flatten)
        shift
        [ "$#" -gt 0 ] || { usage >&2; exit 2; }

        exec "$DOCKER" run \
            --rm \
            --network none \
            --user "$(id -u):$(id -g)" \
            --volume "$PWD:/work" \
            --workdir /work \
            "$IMAGE" \
            "$command" "$@"
        ;;
    -h|--help|help|'')
        usage
        ;;
    *)
        echo "Unknown command: $command" >&2
        usage >&2
        exit 2
        ;;
esac
