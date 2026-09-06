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

mapfile -d '' -t python_sources < <(find workloads/python -type f -name '*.py' -print0 | sort -z)
python3 -m py_compile runner/__init__.py runner/bench.py tests/test_runner.py docker/python/smoke.py "${python_sources[@]}"
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

entry = 'ENTRYPOINT ["java", "-Xss64m", "--enable-native-access=ALL-UNNAMED", "-jar", "/opt/protos/protos.jar"]'
text = path.read_text(encoding='utf-8')
assert 'COPY --from=build /out/protos.jar /opt/protos/protos.jar' in text
assert entry in text
assert 'ENTRYPOINT ["/opt/protos/bin/protos"]' not in text
assert "! -name 'original-*'" in text
print('DOCKERFILE_RUNTIME_LAUNCHER_CHECK: PASS')

node = Path('docker/node/Dockerfile').read_text(encoding='utf-8')
node_lines = [line.strip() for line in node.splitlines()]
node_first_from = next(i for i, line in enumerate(node_lines) if line.startswith('FROM '))
assert 'ARG NODE_BASE=node:24.20.0-bookworm-slim' in node_lines[:node_first_from]
assert 'ENTRYPOINT ["node", "--stack-size=32768"]' in node
print('NODE_RUNTIME_CONFIG_CHECK: PASS')
PY

python3 runner/bench.py validate
python3 - <<'PY'
import json
from pathlib import Path

paths = (
    Path('config/protos.json'),
    Path('config/runtimes.json'),
    Path('config/suite.json'),
    Path('schemas/result.schema.json'),
    Path('schemas/correctness.schema.json'),
)
for path in paths:
    json.loads(path.read_text(encoding='utf-8'))

suite = json.loads(Path('config/suite.json').read_text(encoding='utf-8'))
runtimes = json.loads(Path('config/runtimes.json').read_text(encoding='utf-8'))
protos = json.loads(Path('config/protos.json').read_text(encoding='utf-8'))
assert protos['pinned_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'
assert suite['protos_corpus_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'
assert runtimes['runtimes']['protos']['runtime_args'] == ['-Xss64m']
assert len(suite['benchmarks']) == 11
assert suite['comparison_languages'] == ['python', 'javascript']
assert sum(len(entry['implementations']) + 1 for entry in suite['benchmarks']) == 33
print('JSON_VALIDATION: PASS')
print('CORPUS_MANIFEST_COUNT_CHECK: PASS')
PY

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in Makefile runner/__init__.py runner/bench.py tests/test_runner.py scripts/validate.sh docker/protos/Dockerfile docker/python/Dockerfile docker/python/smoke.py docker/node/Dockerfile; do
    grep -qF "$notice" "$path" || { echo "missing APL notice: $path" >&2; exit 1; }
done

while IFS= read -r -d '' path; do
    grep -qF "$notice" "$path" || { echo "missing APL notice: $path" >&2; exit 1; }
done < <(find workloads/python workloads/javascript -type f \( -name '*.py' -o -name '*.mjs' \) -print0)

test -f config/LICENSE_NOTICE.txt
test -f schemas/LICENSE_NOTICE.txt
grep -q 'Protos Benchmarks' LICENSE.TXT
grep -q 'guillermomolina/protos-benchmarks' LICENSE.TXT

printf 'RUNNER_UNIT_TESTS: PASS\n'
printf 'STATIC_VALIDATION: PASS\n'
printf 'LICENSE_CHECK: PASS\n'
