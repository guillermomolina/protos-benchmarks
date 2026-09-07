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

bash -n scripts/perf002b_validate.sh

python3 - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path('config/perf002.json').read_text(encoding='utf-8'))
assert cfg['schema_version'] == 1
assert cfg['perf_item'] == 'PERF002'
assert cfg['slice'] == 'PERF002-B'
assert cfg['evidence_class'] == 'non_timing_truffle_correctness_and_compilability'
assert cfg['protos_revision'] == '3c93912a5579326374782a43527fbb51046f8f91'
assert cfg['protos_implementation_version'] == '0.2.162-SNAPSHOT'
assert cfg['build_base'] == 'maven:3.9.9-eclipse-temurin-21'
assert cfg['graal_base'] == 'ghcr.io/graalvm/jdk-community:22.0.0'
assert cfg['truffle_runtime_version'] == '24.0.0'
assert cfg['stack'] == '128m'
assert cfg['stability_policy']['workload'] == 'runtime/polymorphic-dispatch'
assert cfg['stability_policy']['mode'] == 'truffle'
assert cfg['stability_policy']['consecutive_runs'] == 10
assert len(cfg['semantic_smoke']) == 2
assert len(cfg['workloads']) == 11
assert set(cfg['modes']) == {'interpreter', 'truffle'}

legacy = json.loads(Path('config/protos.json').read_text(encoding='utf-8'))
suite = json.loads(Path('config/suite.json').read_text(encoding='utf-8'))
assert legacy['pinned_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'
assert suite['protos_corpus_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'

dockerfile = Path('docker/protos-perf002/Dockerfile').read_text(encoding='utf-8')
assert 'ARG BUILD_BASE=maven:3.9.9-eclipse-temurin-21' in dockerfile
assert 'ARG GRAAL_BASE=ghcr.io/graalvm/jdk-community:22.0.0' in dockerfile
assert 'ARG TRUFFLE_RUNTIME_VERSION=24.0.0' in dockerfile
assert 'dependency:copy-dependencies' in dockerfile
assert 'COPY --from=build /out/truffle-runtime /opt/truffle-runtime' in dockerfile
assert 'COPY --from=build /out/protos.jar /opt/protos/protos.jar' in dockerfile
assert 'ENTRYPOINT ["java"]' in dockerfile
print('PERF002_CONFIG_VALIDATION: PASS')
print('PERF002_DOCKERFILE_VALIDATION: PASS')
print('PERF001_HISTORICAL_PIN_GUARD: PASS')
PY

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in \
    scripts/perf002b_validate.sh \
    docker/protos-perf002/Dockerfile \
    docker/protos-perf002/DiagnosticEval.java \
    docker/protos-perf002/RuntimeProbe.java \
    docker/protos-perf002/truffle-runtime-pom.xml
do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done

bash -n scripts/perf001d_measure.sh
python3 -m py_compile scripts/perf001d_finalize.py

python3 - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path('config/perf001d.json').read_text(encoding='utf-8'))
assert cfg['schema_version'] == 1
assert cfg['perf_item'] == 'PERF001'
assert cfg['slice'] == 'PERF001-D'
assert cfg['classification'] == 'protos_measurement_pre_post_perf002'
assert cfg['build_base'] == 'maven:3.9.9-eclipse-temurin-21'
assert cfg['graal_base'] == 'ghcr.io/graalvm/jdk-community:22.0.0'
assert cfg['truffle_runtime_version'] == '24.0.0'
assert cfg['stack'] == '128m'
assert cfg['startup_samples'] == 10
assert cfg['warmup_iterations'] == 20
assert cfg['steady_samples'] == 20
assert cfg['diagnostic_iterations'] == 20
assert len(cfg['workloads']) == 11
assert set(cfg['timing_modes']) == {'interpreter', 'truffle'}
revisions = {x['label']: x['revision'] for x in cfg['revisions']}
assert revisions == {
    'pre-perf002': '8f363d0146164f99e72210eb44667f4efb7b88e7',
    'post-perf002': '3c93912a5579326374782a43527fbb51046f8f91',
}

legacy = json.loads(Path('config/protos.json').read_text(encoding='utf-8'))
suite = json.loads(Path('config/suite.json').read_text(encoding='utf-8'))
perf002 = json.loads(Path('config/perf002.json').read_text(encoding='utf-8'))
assert legacy['pinned_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'
assert suite['protos_corpus_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'
assert perf002['protos_revision'] == '3c93912a5579326374782a43527fbb51046f8f91'
assert perf002['stack'] == '128m'

dockerfile = Path('docker/protos-perf001d/Dockerfile').read_text(encoding='utf-8')
for required in (
    'ARG BUILD_BASE=maven:3.9.9-eclipse-temurin-21',
    'ARG GRAAL_BASE=ghcr.io/graalvm/jdk-community:22.0.0',
    'ARG TRUFFLE_RUNTIME_VERSION=24.0.0',
    'dependency:copy-dependencies',
    'MeasurementDriver.java',
    'StartupDriver.java',
    'COPY --from=build /out/truffle-runtime /opt/truffle-runtime',
    'ENTRYPOINT ["java"]',
):
    assert required in dockerfile

measure = Path('scripts/perf001d_measure.sh').read_text(encoding='utf-8')
assert '--network none' in measure
assert '--cpuset-cpus "$CPUSET"' in measure
assert '-Dpolyglot.engine.Compilation=false' in measure
assert '-Dpolyglot.engine.BackgroundCompilation=false' in measure
assert '-Dpolyglot.engine.TraceCompilation=true' in measure

print('PERF001D_CONFIG_VALIDATION: PASS')
print('PERF001D_DOCKERFILE_VALIDATION: PASS')
print('PERF001D_TIMING_BOUNDARY_STATIC_CHECK: PASS')
print('PERF001_HISTORICAL_PIN_GUARD: PASS')
print('PERF002_EVIDENCE_PIN_GUARD: PASS')
PY

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in \
    scripts/perf001d_measure.sh \
    scripts/perf001d_finalize.py \
    docker/protos-perf001d/Dockerfile \
    docker/protos-perf001d/DiagnosticEval.java \
    docker/protos-perf001d/RuntimeProbe.java \
    docker/protos-perf001d/MeasurementDriver.java \
    docker/protos-perf001d/StartupDriver.java \
    docker/protos-perf001d/truffle-runtime-pom.xml
do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done

printf 'RUNNER_UNIT_TESTS: PASS\n'
printf 'STATIC_VALIDATION: PASS\n'
printf 'LICENSE_CHECK: PASS\n'


# PERF001-E collection equivalence/timing harness
bash -n scripts/perf001e_measure.sh
python3 -m py_compile scripts/perf001e_finalize.py docker/python-perf001e/timing_driver.py

python3 - <<'PY'
import json
from pathlib import Path

cfg=json.loads(Path('config/perf001e.json').read_text(encoding='utf-8'))
assert cfg['schema_version'] == 1
assert cfg['perf_item'] == 'PERF001'
assert cfg['slice'] == 'PERF001-E'
assert cfg['classification'] == 'cross_language_sequential_collections'
assert cfg['protos_revision'] == '86b35d8bb2d7ab2ad54bc2947e1bf7fbff1fca15'
assert cfg['protos_implementation_version'] == '0.2.167-SNAPSHOT'
assert cfg['build_base'] == 'maven:3.9.9-eclipse-temurin-21'
assert cfg['graal_base'] == 'ghcr.io/graalvm/jdk-community:22.0.0'
assert cfg['truffle_runtime_version'] == '24.0.0'
assert cfg['protos_stack'] == '128m'
assert cfg['python_base'] == 'python:3.14.7-slim-bookworm'
assert cfg['python_version'] == '3.14.7'
assert cfg['node_base'] == 'node:24.20.0-bookworm-slim'
assert cfg['node_version'] == '24.20.0'
assert cfg['node_stack_kb'] == 32768
assert cfg['startup_samples'] == 10
assert cfg['warmup_iterations'] == 20
assert cfg['steady_samples'] == 20
assert cfg['diagnostic_iterations'] == 20
assert cfg['languages'] == ['protos','python','javascript']
assert len(cfg['workloads']) == 6
assert [x['expected'] for x in cfg['workloads']] == ['408','136','528','321601','1250','240808']

legacy=json.loads(Path('config/protos.json').read_text(encoding='utf-8'))
suite=json.loads(Path('config/suite.json').read_text(encoding='utf-8'))
perf002=json.loads(Path('config/perf002.json').read_text(encoding='utf-8'))
perf001d=json.loads(Path('config/perf001d.json').read_text(encoding='utf-8'))
assert legacy['pinned_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'
assert suite['protos_corpus_revision'] == '42b8264a36254dafbd97d80f5181790e28b9de12'
assert perf002['protos_revision'] == '3c93912a5579326374782a43527fbb51046f8f91'
assert perf001d['revisions'][1]['revision'] == '3c93912a5579326374782a43527fbb51046f8f91'

protos=Path('docker/protos-perf001e/Dockerfile').read_text(encoding='utf-8')
for required in (
  'ARG BUILD_BASE=maven:3.9.9-eclipse-temurin-21',
  'ARG GRAAL_BASE=ghcr.io/graalvm/jdk-community:22.0.0',
  'ARG TRUFFLE_RUNTIME_VERSION=24.0.0',
  'dependency:copy-dependencies',
  'MeasurementDriver.java',
  'StartupDriver.java',
  'ENTRYPOINT ["java"]',
):
    assert required in protos

python_docker=Path('docker/python-perf001e/Dockerfile').read_text(encoding='utf-8')
node_docker=Path('docker/node-perf001e/Dockerfile').read_text(encoding='utf-8')
assert 'ARG PYTHON_BASE=python:3.14.7-slim-bookworm' in python_docker
assert 'ARG NODE_BASE=node:24.20.0-bookworm-slim' in node_docker
assert 'COPY workloads/python /opt/benchmark/workloads' in python_docker
assert 'COPY workloads/javascript /opt/benchmark/workloads' in node_docker

measure=Path('scripts/perf001e_measure.sh').read_text(encoding='utf-8')
assert '--network none' in measure
assert '--cpuset-cpus "$CPUSET"' in measure
assert '-Dpolyglot.engine.BackgroundCompilation=false' in measure
assert '-Dpolyglot.engine.TraceCompilation=true' in measure
assert 'CROSS_LANGUAGE_CORRECTNESS: PASS 18/18' in measure
assert measure.count('runtime_path="/opt/benchmark/workloads/${source#workloads/python/}"') == 3
assert measure.count('runtime_path="/opt/benchmark/workloads/${source#workloads/javascript/}"') == 3
assert 'runtime_path="/opt/benchmark/${source#workloads/python/}"' not in measure
assert 'runtime_path="/opt/benchmark/${source#workloads/javascript/}"' not in measure

sort_py=Path('workloads/python/collections/array-sort.py').read_text(encoding='utf-8')
sort_js=Path('workloads/javascript/collections/array-sort.mjs').read_text(encoding='utf-8')
assert '.sort(' not in sort_py
assert '.sort(' not in sort_js
assert 'merge_sort' in sort_py and 'mergeSort' in sort_js

set_py=Path('workloads/python/collections/set-algebra.py').read_text(encoding='utf-8')
set_js=Path('workloads/javascript/collections/set-algebra.mjs').read_text(encoding='utf-8')
assert 'union(' in set_py and 'intersection(' in set_py and 'difference(' in set_py
assert 'new Set(' not in set_js
print('PERF001E_CONFIG_VALIDATION: PASS')
print('PERF001E_ALGORITHM_EQUIVALENCE_STATIC_GUARD: PASS')
print('PERF001_HISTORICAL_PIN_GUARD: PASS')
PY

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in \
  scripts/perf001e_measure.sh \
  scripts/perf001e_finalize.py \
  docker/protos-perf001e/Dockerfile \
  docker/protos-perf001e/DiagnosticEval.java \
  docker/protos-perf001e/RuntimeProbe.java \
  docker/protos-perf001e/MeasurementDriver.java \
  docker/protos-perf001e/StartupDriver.java \
  docker/protos-perf001e/truffle-runtime-pom.xml \
  docker/python-perf001e/Dockerfile \
  docker/python-perf001e/timing_driver.py \
  docker/node-perf001e/Dockerfile \
  docker/node-perf001e/timing_driver.mjs
do
  grep -qF "$notice" "$path" || {
    echo "missing APL notice: $path" >&2
    exit 1
  }
done
echo 'PERF001E_STATIC_VALIDATION: PASS'


# Dedicated IGV diagnostic analyzer. This tool must remain isolated from
# benchmark runtime images and pinned to the Graal/Truffle 24.0.0 line.
bash -n scripts/igv_analyzer.sh
python3 - <<'PYIGV'
from pathlib import Path

path = Path('docker/igv-analyzer/Dockerfile')
text = path.read_text(encoding='utf-8')
required = (
    'FROM eclipse-temurin:17-jdk-jammy',
    'ARG GRAAL_REV=78238a5ee6e4ae827059c70549e286ae730b7730',
    'ARG MX_REV=d0d6d6cd2f70bb384dfba9f3f66f3dab21392ae4',
    'javac --release 7 /tmp/Release7Probe.java',
    'build --dependencies=IGV_JSONEXPORTER,IGV_DATA_SETTINGS',
    'help bgv2json >/tmp/bgv2json-command-help.txt 2>&1',
    "grep -q 'Export bgv graphs as json' /tmp/bgv2json-command-help.txt",
    'ENTRYPOINT ["mx", "--primary-suite-path", "/opt/graal/visualizer", "bgv2json"]',
)
for item in required:
    assert item in text, item

wrapper = Path('scripts/igv_analyzer.sh').read_text(encoding='utf-8')
assert '--network none' in wrapper
assert '--entrypoint mx' in wrapper
assert 'help bgv2json' in wrapper
assert 'bgv2json --help' not in wrapper
assert 'docker/igv-analyzer/Dockerfile' in wrapper
assert 'protos-benchmarks/igv-analyzer:graal-24.0.0' in wrapper

for runtime in (
    Path('docker/protos/Dockerfile'),
    Path('docker/protos-perf001d/Dockerfile'),
    Path('docker/protos-perf001e/Dockerfile'),
    Path('docker/protos-perf002/Dockerfile'),
):
    assert 'eclipse-temurin:17-jdk-jammy' not in runtime.read_text(encoding='utf-8')

print('IGV_ANALYZER_STATIC_VALIDATION: PASS')
print('IGV_ANALYZER_RUNTIME_ISOLATION_CHECK: PASS')
PYIGV

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in docker/igv-analyzer/Dockerfile scripts/igv_analyzer.sh; do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done
printf 'IGV_ANALYZER_LICENSE_CHECK: PASS\n'
