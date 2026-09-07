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
  scripts/igv_analyzer.sh smoke
  scripts/igv_analyzer.sh analyze <bgv2json-args...>

Examples:
  scripts/igv_analyzer.sh build
  scripts/igv_analyzer.sh analyze results/example.bgv > results/example.json

The analyzer runs in a dedicated JDK 17 container. Runtime analysis is executed
with networking disabled and the current working directory mounted at /work.
Override the image with PROTOS_IGV_ANALYZER_IMAGE and the container CLI with
DOCKER (for example DOCKER=podman).
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
        tmp=$(mktemp)
        trap 'rm -f "$tmp"' EXIT
        "$DOCKER" run --rm --network none \
            --entrypoint mx \
            "$IMAGE" \
            --primary-suite-path /opt/graal/visualizer \
            help bgv2json >"$tmp" 2>&1
        grep -q 'Export bgv graphs as json' "$tmp"
        printf 'IGV_ANALYZER_SMOKE: PASS\n'
        ;;
    analyze)
        shift
        if [ "$#" -eq 0 ]; then
            usage >&2
            exit 2
        fi
        exec "$DOCKER" run --rm --network none \
            --user "$(id -u):$(id -g)" \
            --volume "$PWD:/work" \
            --workdir /work \
            "$IMAGE" "$@"
        ;;
    -h|--help|help|'')
        usage
        ;;
    *)
        printf 'Unknown command: %s\n' "$command" >&2
        usage >&2
        exit 2
        ;;
esac
