#!/usr/bin/env sh
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

set -eu

usage() {
    echo "usage: run <probe|correctness> <optimizer|fallback> [source expected]" >&2
    exit 2
}

[ "$#" -ge 2 ] || usage
ACTION=$1
VARIANT=$2
shift 2

case "$VARIANT" in
    optimizer)
        RUNTIME_DIR=/opt/protos/lib/runtime
        ;;
    fallback)
        RUNTIME_DIR=/opt/perf006d/runtime-fallback
        ;;
    *)
        usage
        ;;
esac

CP="/opt/perf006d/probe:/opt/perf006d/driver:/opt/protos/lib/protos.jar:$RUNTIME_DIR/*"
JAVA_ARGS="-Xss128m"

case "$ACTION" in
    probe)
        [ "$#" -eq 0 ] || usage
        exec java $JAVA_ARGS --enable-native-access=ALL-UNNAMED \
            -cp "$CP" Perf006dRuntimeProbe
        ;;
    correctness)
        [ "$#" -eq 2 ] || usage
        SOURCE="/opt/perf006d/corpus/$1"
        EXPECTED=$2
        [ -f "$SOURCE" ] || {
            echo "missing benchmark source: $SOURCE" >&2
            exit 2
        }
        exec java $JAVA_ARGS --enable-native-access=ALL-UNNAMED \
            -cp "$CP" Perf006dCorrectnessDriver "$SOURCE" "$EXPECTED"
        ;;
    *)
        usage
        ;;
esac
