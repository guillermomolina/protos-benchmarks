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
IMAGE=${PROTOS_IGV_ANALYZER_IMAGE:-protos-benchmarks/igv-analyzer:graal-24.0.0}
DOCKER=${DOCKER:-docker}

usage() {
    cat <<'EOF'
Usage:
  scripts/igv_analyzer.sh build
  scripts/igv_analyzer.sh smoke [sample.bgv]
  scripts/igv_analyzer.sh analyze <bgv2json-args...>
EOF
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
        output=$(mktemp)
        tmpdir=
        trap 'rm -f "$output"; [ -z "$tmpdir" ] || rm -rf "$tmpdir"' EXIT
        "$DOCKER" run --rm --network none "$IMAGE" --help >"$output" 2>&1
        grep -q 'mx igv-json' "$output"
        echo "IGV_ANALYZER_CLASS_SMOKE: PASS"
        if [ "$#" -eq 1 ]; then
            sample=$1
            [ -f "$sample" ] || { echo "IGV_ANALYZER_REAL_SMOKE: FAIL missing BGV: $sample" >&2; exit 3; }
            tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/protos-igv-smoke.XXXXXX")
            cp -- "$sample" "$tmpdir/sample.bgv"
            set +e
            "$DOCKER" run --rm --network none \
                --user "$(id -u):$(id -g)" \
                --volume "$tmpdir:/work" \
                --workdir /work \
                "$IMAGE" sample.bgv \
                >"$tmpdir/export.stdout" 2>"$tmpdir/export.stderr"
            rc=$?
            set -e
            if [ "$rc" -ne 0 ]; then
                echo "IGV_ANALYZER_REAL_SMOKE: FAIL rc=$rc" >&2
                tail -80 "$tmpdir/export.stderr" >&2 || true
                exit "$rc"
            fi
            mapfile -t jsons < <(find "$tmpdir" -maxdepth 1 -type f -name '*.json' -print | sort)
            [ "${#jsons[@]}" -gt 0 ] || { echo "IGV_ANALYZER_REAL_SMOKE: FAIL no JSON generated" >&2; exit 4; }
            python3 - "${jsons[@]}" <<'PYJSON'
import json, os, sys
for path in sys.argv[1:]:
    name=os.path.basename(path)
    if len(name.encode('utf-8')) > 240:
        raise SystemExit(f'filename too long: {name}')
    with open(path, encoding='utf-8') as fh:
        obj=json.load(fh)
    for key in ('name','graph_type','nodes'):
        if key not in obj:
            raise SystemExit(f'missing {key}: {path}')
PYJSON
            echo "IGV_ANALYZER_REAL_SMOKE: PASS json_count=${#jsons[@]}"
        elif [ "$#" -ne 0 ]; then
            usage >&2; exit 2
        fi
        echo "IGV_ANALYZER_SMOKE: PASS"
        ;;
    analyze)
        shift
        [ "$#" -gt 0 ] || { usage >&2; exit 2; }
        exec "$DOCKER" run --rm --network none \
            --user "$(id -u):$(id -g)" \
            --volume "$PWD:/work" \
            --workdir /work \
            "$IMAGE" "$@"
        ;;
    -h|--help|help|'') usage ;;
    *) echo "Unknown command: $command" >&2; usage >&2; exit 2 ;;
esac
