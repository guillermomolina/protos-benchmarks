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
cd "$ROOT"

python3 -m py_compile runner/__init__.py runner/bench.py tests/test_runner.py docker/python/smoke.py
python3 -m unittest discover -s tests -v
python3 - <<'PY'
from pathlib import Path
path = Path('docker/protos/Dockerfile')
lines = [line.strip() for line in path.read_text(encoding='utf-8').splitlines()]
first_from = next(i for i, line in enumerate(lines) if line.startswith('FROM '))
prefix = lines[:first_from]
assert 'ARG BUILD_BASE=maven:3.9.9-eclipse-temurin-21' in prefix
assert 'ARG GRAAL_BASE=ghcr.io/graalvm/jdk-community:22.0.0' in prefix
assert 'FROM ${GRAAL_BASE}' in lines[first_from + 1:]
print('DOCKERFILE_ARG_SCOPE_CHECK: PASS')
entry = 'ENTRYPOINT [\"java\", \"--enable-native-access=ALL-UNNAMED\", \"-jar\", \"/opt/protos/protos.jar\"]'
text = path.read_text(encoding='utf-8')
assert 'COPY --from=build /out/protos.jar /opt/protos/protos.jar' in text
assert entry in text
assert 'ENTRYPOINT [\"/opt/protos/bin/protos\"]' not in text
assert "! -name 'original-*'" in text
print('DOCKERFILE_RUNTIME_LAUNCHER_CHECK: PASS')
PY

python3 runner/bench.py validate
python3 - <<'PY'
import json
from pathlib import Path
for path in (Path('config/protos.json'), Path('config/runtimes.json'), Path('schemas/result.schema.json')):
    json.loads(path.read_text(encoding='utf-8'))
print('JSON_VALIDATION: PASS')
PY

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in Makefile runner/__init__.py runner/bench.py tests/test_runner.py scripts/validate.sh docker/protos/Dockerfile docker/python/Dockerfile docker/python/smoke.py; do
    grep -qF "$notice" "$path" || { echo "missing APL notice: $path" >&2; exit 1; }
done
test -f config/LICENSE_NOTICE.txt
test -f schemas/LICENSE_NOTICE.txt
grep -q 'Protos Benchmarks' LICENSE.TXT
grep -q 'guillermomolina/protos-benchmarks' LICENSE.TXT

printf 'RUNNER_UNIT_TESTS: PASS\n'
printf 'STATIC_VALIDATION: PASS\n'
printf 'LICENSE_CHECK: PASS\n'
