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
ANALYZER_GRAAL_VERSION=25.4.4.1.1
DEFAULT_IMAGE=ghcr.io/guillermomolina/protos-benchmarks/igv-analyzer:graal-$ANALYZER_GRAAL_VERSION
IMAGE=${PROTOS_IGV_ANALYZER_IMAGE:-$DEFAULT_IMAGE}
DOCKER=${DOCKER:-docker}

usage() {
    cat <<'USAGE'
Usage:
  scripts/igv_analyzer.sh pull
  scripts/igv_analyzer.sh inspect <file.bgv> [protos-root:<16 lowercase hex>]
  scripts/igv_analyzer.sh list <igvutil-list-args...>
  scripts/igv_analyzer.sh filter <igvutil-filter-args...>
  scripts/igv_analyzer.sh flatten <igvutil-flatten-args...>
  scripts/igv_analyzer.sh smoke [sample.bgv]
  scripts/igv_analyzer.sh build          (maintainer only)

Normal use runs the prebuilt, versioned analyzer image. `pull` is the one-time
setup step and the only command that contacts a registry. inspect, list,
filter, flatten and smoke never build, clone or pull; they fail if the image
is absent locally. PROTOS_IGV_ANALYZER_IMAGE overrides the image reference.

Direct list/filter/flatten arguments are evaluated inside the current working
directory, which is mounted read/write as /work in the analyzer container.
USAGE
}

require_image() {
    "$DOCKER" image inspect "$IMAGE" >/dev/null 2>&1 || {
        echo "IGV analyzer image not present locally: $IMAGE" >&2
        echo "Run once: scripts/igv_analyzer.sh pull" >&2
        exit 4
    }
}

command=${1:-}

case "$command" in
    build)
        exec "$DOCKER" build \
            --file "$ROOT/docker/igv-analyzer/Dockerfile" \
            --tag "$IMAGE" \
            "$ROOT"
        ;;
    pull)
        shift
        [ "$#" -eq 0 ] || { usage >&2; exit 2; }
        exec "$DOCKER" pull "$IMAGE"
        ;;
    inspect)
        shift
        [ "$#" -ge 1 ] && [ "$#" -le 2 ] || { usage >&2; exit 2; }
        bgv=$1
        selector=${2:-}

        if [ -n "$selector" ] \
            && ! printf '%s' "$selector" | grep -Eqx 'protos-root:[0-9a-f]{16}'; then
            echo "Invalid selector (expected protos-root:<16 lowercase hex>): $selector" >&2
            exit 2
        fi

        echo "BGV_FILE=$bgv"
        echo "SELECTOR=${selector:-NONE}"
        echo "ANALYZER_GRAAL_VERSION=$ANALYZER_GRAAL_VERSION"
        echo "ANALYZER_IMAGE=$IMAGE"

        root_fail=NOT_REQUESTED
        [ -z "$selector" ] || root_fail=FAIL

        if [ ! -f "$bgv" ] || [ ! -s "$bgv" ]; then
            if [ ! -f "$bgv" ]; then
                echo "BGV file missing: $bgv" >&2
            else
                echo "BGV file empty: $bgv" >&2
            fi
            echo "BGV_READABLE=FAIL"
            echo "SELECTED_ROOT_PRESENT=$root_fail"
            echo "AFTER_TRUFFLE_TIER_PRESENT=FAIL"
            echo "IGV_INSPECT=FAIL"
            exit 3
        fi

        require_image

        bgv_dir=$(CDPATH= cd -- "$(dirname -- "$bgv")" && pwd)
        bgv_name=$(basename -- "$bgv")
        listing=$(mktemp)
        trap 'rm -f "$listing"' EXIT

        # Cheap structural acceptance: hierarchy listing only, no JSON export.
        readable=PASS
        "$DOCKER" run \
            --rm \
            --network none \
            --user "$(id -u):$(id -g)" \
            --volume "$bgv_dir:/input:ro" \
            --workdir /input \
            "$IMAGE" \
            list "$bgv_name" \
            >"$listing" || readable=FAIL
        [ -s "$listing" ] || readable=FAIL

        root=$root_fail
        tier=FAIL
        if [ "$readable" = PASS ]; then
            if [ -n "$selector" ] && grep -qF -- "$selector" "$listing"; then
                root=PASS
            fi
            if grep -qF 'After TruffleTier' "$listing"; then
                tier=PASS
            fi
        fi

        echo "BGV_READABLE=$readable"
        echo "SELECTED_ROOT_PRESENT=$root"
        echo "AFTER_TRUFFLE_TIER_PRESENT=$tier"
        if [ "$readable" = PASS ] && [ "$tier" = PASS ] && [ "$root" != FAIL ]; then
            echo "IGV_INSPECT=PASS"
        else
            echo "IGV_INSPECT=FAIL"
            exit 1
        fi
        ;;
    smoke)
        shift
        [ "$#" -le 1 ] || { usage >&2; exit 2; }
        require_image

        output=$(mktemp)
        tmpdir=
        trap 'rm -f "$output"; [ -z "$tmpdir" ] || rm -rf "$tmpdir"' EXIT

        "$DOCKER" run --rm --network none "$IMAGE" --help >"$output"
        grep -q 'list' "$output"
        grep -q 'filter' "$output"
        grep -q 'flatten' "$output"

        echo "IGV_ANALYZER_CLASS_SMOKE: PASS"

        "$DOCKER" run --rm --network none --entrypoint cat "$IMAGE" \
            /opt/igvutil/SELFTEST >"$output"
        grep -qx 'IGV_ANALYZER_BUILD_SELFTEST=PASS' "$output"
        cat "$output"

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
        require_image

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
