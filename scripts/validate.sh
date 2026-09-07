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
    'COPY docker/igv-analyzer/patch_json_exporter.py /tmp/patch_json_exporter.py',
    'COPY docker/igv-analyzer/bgv2json /usr/local/bin/bgv2json',
    'javac -cp "$CP" -d /opt/igv-jsonexporter/classes "$SRC"',
    'ENTRYPOINT ["/usr/local/bin/bgv2json"]',
)
for item in required:
    assert item in text, item

wrapper = Path('scripts/igv_analyzer.sh').read_text(encoding='utf-8')
assert '--network none' in wrapper
assert '--entrypoint mx' not in wrapper
assert 'help bgv2json' not in wrapper
assert 'IGV_ANALYZER_REAL_SMOKE' in wrapper
assert 'docker/igv-analyzer/Dockerfile' in wrapper
assert 'protos-benchmarks/igv-analyzer:graal-24.0.0' in wrapper

exporter_wrapper = Path('docker/igv-analyzer/bgv2json').read_text(encoding='utf-8')
assert 'org.graalvm.visualizer.JSONExporter' in exporter_wrapper
assert '/opt/igv-jsonexporter/classpath' in exporter_wrapper
exporter_patch = Path('docker/igv-analyzer/patch_json_exporter.py').read_text(encoding='utf-8')
assert 'UUID.nameUUIDFromBytes' in exporter_patch
assert 'gn.length() > 96' in exporter_patch
assert 'gt.length() > 48' in exporter_patch
print('IGV_ANALYZER_STATIC_VALIDATION: PASS')

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

bash -n docker/igv-analyzer/bgv-summary
bash -n scripts/perf003a_structural_compact.sh
python3 - <<'PYIGVCOMPACT'
from pathlib import Path

dockerfile=Path("docker/igv-analyzer/Dockerfile").read_text(encoding="utf-8")
for required in (
    "CompactBGVSummary.java",
    "/opt/igv-compact/classes",
    "/usr/local/bin/bgv-summary",
):
    assert required in dockerfile, required

wrapper=Path("scripts/igv_analyzer.sh").read_text(encoding="utf-8")
assert "summarize <input.bgv> <output.ndjson> [term...]" in wrapper
assert "--entrypoint /usr/local/bin/bgv-summary" in wrapper

compact=Path("scripts/perf003a_structural_compact.sh").read_text(encoding="utf-8")
for required in (
    "igv_compact",
    "summary.ndjson",
    "complete.marker",
    "PERF003A_COMPACT_RESERVE_BYTES",
    "FULL_JSON_MATERIALIZED: NO",
    "BGV_RECAPTURED: NO",
    "STRUCTURAL_EXECUTION_REPEATED: NO",
    "--status",
):
    assert required in compact, required
for forbidden in (
    "MeasurementDriver",
    "DiagnosticEval",
    "-Djdk.graal.Dump=",
    "perf003a_structural_summary.py",
):
    assert forbidden not in compact, forbidden

java=Path("docker/igv-analyzer/CompactBGVSummary.java").read_text(encoding="utf-8")
for required in (
    "DigestInputStream",
    "BinaryReader",
    "LocationStackFrame",
    "kind\\\":\\\"graph",
    "kind\\\":\\\"term",
):
    assert required in java, required

makefile=Path("Makefile").read_text(encoding="utf-8")
assert "perf003a-structural-compact:" in makefile
print("PERF003A_COMPACT_STATIC_VALIDATION: PASS")
PYIGVCOMPACT

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in \
    docker/igv-analyzer/CompactBGVSummary.java \
    docker/igv-analyzer/bgv-summary \
    scripts/perf003a_structural_compact.sh
do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done
printf 'PERF003A_COMPACT_LICENSE_CHECK: PASS\n'

# PERF003-A external compilability diagnostic
bash -n scripts/perf003a_diagnostic.sh
python3 - <<'PY'
import json
from pathlib import Path
cfg=json.loads(Path("config/perf003a.json").read_text(encoding="utf-8"))
assert cfg["schema_version"] == 1
assert cfg["perf_item"] == "PERF003"
assert cfg["slice"] == "PERF003-A"
assert cfg["classification"] == "collection_algorithm_truffle_compilability"
assert cfg["protos_revision"] == "d66841adb0b820047ed079f0bc7d643873f23194"
assert cfg["protos_implementation_version"] == "0.2.180-SNAPSHOT"
assert cfg["build_base"] == "maven:3.9.9-eclipse-temurin-21"
assert cfg["graal_base"] == "ghcr.io/graalvm/jdk-community:22.0.0"
assert cfg["truffle_runtime_version"] == "24.0.0"
assert cfg["protos_stack"] == "128m"
assert cfg["diagnostic_iterations"] == 20
assert [(w["id"], w["expected"]) for w in cfg["workloads"]] == [
    ("collections/array-reduce", "528"),
    ("collections/array-sort", "321601"),
]
script=Path("scripts/perf003a_diagnostic.sh").read_text(encoding="utf-8")
for required in (
    "--network none",
    '--cpuset-cpus "$CPUSET"',
    "-Dpolyglot.engine.Compilation=false",
    "-Dpolyglot.engine.TraceCompilation=true",
    "PERF003A_EXTERNAL_GATE:",
    "docker/protos-perf001e/Dockerfile",
):
    assert required in script
print("PERF003A_STATIC_VALIDATION: PASS")
PY
notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
grep -qF "$notice" scripts/perf003a_diagnostic.sh || {
  echo "missing APL notice: scripts/perf003a_diagnostic.sh" >&2
  exit 1
}

# PERF003-A structural Graal/IGV diagnostic
bash -n scripts/perf003a_structural.sh
bash -n scripts/perf003a_structural_resume.sh
python3 -m py_compile scripts/perf003a_structural_summary.py
python3 - <<'PY'
import json
from pathlib import Path

cfg=json.loads(Path("config/perf003a-structural.json").read_text(encoding="utf-8"))
assert cfg["schema_version"] == 1
assert cfg["perf_item"] == "PERF003"
assert cfg["slice"] == "PERF003-A"
assert cfg["evidence_class"] == "structural_truffle_graal_diagnostic"
assert cfg["protos_revision"] == "d66841adb0b820047ed079f0bc7d643873f23194"
assert cfg["protos_implementation_version"] == "0.2.180-SNAPSHOT"
assert cfg["graal_base"] == "ghcr.io/graalvm/jdk-community:22.0.0"
assert cfg["truffle_runtime_version"] == "24.0.0"
assert cfg["protos_stack"] == "128m"
assert cfg["diagnostic_iterations"] == 20
assert cfg["workload"]["id"] == "collections/array-reduce"
assert cfg["workload"]["expected"] == "528"
assert cfg["graal_dump"] == "Truffle:2"
assert cfg["expansion_tier"] == "peTier"
assert cfg["retained_bgv_compressed_limit_bytes"] == 80 * 1024 * 1024

script=Path("scripts/perf003a_structural.sh").read_text(encoding="utf-8")
for required in (
    "-Dpolyglot.engine.MethodExpansionStatistics=$EXPANSION_TIER",
    "-Dpolyglot.engine.NodeExpansionStatistics=$EXPANSION_TIER",
    "-Dpolyglot.engine.TraceMethodExpansion=$EXPANSION_TIER",
    "-Dpolyglot.engine.TraceNodeExpansion=$EXPANSION_TIER",
    "-Dpolyglot.engine.NodeSourcePositions=true",
    "-Djdk.graal.Dump=$DUMP",
    "-Djdk.graal.DumpPath=/diag-out/graal_dumps",
    'scripts/igv_analyzer.sh" analyze',
    "--network none",
):
    assert required in script, required
resume=Path("scripts/perf003a_structural_resume.sh").read_text(encoding="utf-8")
for required in (
    "igv_json",
    "complete.marker",
    "PERF003A_RESUME_RESERVE_BYTES",
    "PERF003A_RESUME_ESTIMATE_MULTIPLIER",
    "IGV_RESUME_DISK_GUARD: BLOCKED",
    'scripts/igv_analyzer.sh" analyze',
    "STRUCTURAL_EXECUTION_REPEATED: NO",
    "BGV_RECAPTURED: NO",
    "--status",
):
    assert required in resume, required
for forbidden in (
    "MeasurementDriver",
    "DiagnosticEval",
    "docker/protos-perf001e/Dockerfile",
    "perf003a_structural_summary.py",
    "-Djdk.graal.Dump=",
):
    assert forbidden not in resume, forbidden

makefile=Path("Makefile").read_text(encoding="utf-8")
assert "perf003a-structural-resume:" in makefile
assert 'WORK=<existing-run-dir>' in makefile
assert 'perf003a_structural_resume.sh "$(WORK)"' in makefile

print("PERF003A_STRUCTURAL_STATIC_VALIDATION: PASS")
print("PERF003A_RESUME_STATIC_VALIDATION: PASS")
PY

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in scripts/perf003a_structural.sh scripts/perf003a_structural_resume.sh scripts/perf003a_structural_summary.py; do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done

# PERF003-A compact evidence finalizer
python3 -m py_compile scripts/perf003a_structural_finalize_compact.py scripts/perf003a_verify_compact_evidence.py
python3 - <<'PYFINAL'
from pathlib import Path
f=Path('scripts/perf003a_structural_finalize_compact.py').read_text(encoding='utf-8')
for x in ('RAW_BGV_REHASHED = False','RAW_BGV_COMPRESSED = False','FULL_JSON_MATERIALIZED = False','structural_truffle_graal_compact_attribution'):
    assert x in f, x
v=Path('scripts/perf003a_verify_compact_evidence.py').read_text(encoding='utf-8')
assert 'raw_bgv_rehashed_during_finalization' in v
assert 'full_igv_json_materialized' in v
assert 'perf003a-structural-finalize:' in Path('Makefile').read_text(encoding='utf-8')
print('PERF003A_COMPACT_FINALIZER_STATIC_VALIDATION: PASS')
PYFINAL
notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in scripts/perf003a_structural_finalize_compact.py scripts/perf003a_verify_compact_evidence.py; do
  grep -qF "$notice" "$path" || exit 1
done
printf 'PERF003A_COMPACT_FINALIZER_LICENSE_CHECK: PASS\n'


# PERF003-A4a controlled closure-invocation boundary falsification harness
bash -n scripts/perf003a_a4a_boundary_experiment.sh
python3 -m py_compile docker/protos-perf003a-a4a/apply_boundary.py
python3 - <<'PYA4A'
import json
from pathlib import Path
cfg=json.loads(Path("config/perf003a-a4a.json").read_text(encoding="utf-8"))
assert cfg["schema_version"] == 1
assert cfg["perf_item"] == "PERF003"
assert cfg["slice"] == "PERF003-A4a"
assert cfg["protos_revision"] == "d66841adb0b820047ed079f0bc7d643873f23194"
assert cfg["protos_implementation_version"] == "0.2.180-SNAPSHOT"
assert cfg["workload"]["id"] == "collections/array-reduce"
assert str(cfg["workload"]["expected"]) == "528"
assert cfg["diagnostic_iterations"] == 20
assert cfg["experimental_variant"] == "closure-invoke-boundary"
assert cfg["experimental_boundary"] == "ProtosClosureInvoker.invokePrepared"

dockerfile=Path("docker/protos-perf003a-a4a/Dockerfile").read_text(encoding="utf-8")
for required in (
    "ARG DIAGNOSTIC_VARIANT=control",
    "closure-invoke-boundary",
    "python3 /tmp/apply_boundary.py /src",
    "apt-get install -y --no-install-recommends git ca-certificates python3",
    "git fetch --depth 1 origin",
):
    assert required in dockerfile, required

patch=Path("docker/protos-perf003a-a4a/apply_boundary.py").read_text(encoding="utf-8")
assert "@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary" in patch
assert "ProtosClosureInvoker.java" in patch
assert "invokePrepared" in patch

runner=Path("scripts/perf003a_a4a_boundary_experiment.sh").read_text(encoding="utf-8")
import re
assert not re.search(r'local\\s+[^\\n]*prefix=\\$[0-9][^\\n]*\\$\\{prefix\\}', runner)
assert not re.search(r'local\\s+[^\\n]*image=\\$[0-9][^\\n]*\\$\\{image\\}', runner)
for required in (
    "--smoke|--run",
    "TraceCompilation=true",
    "EXPERIMENT_PRECONDITION",
    "IMAGE_BUILD: FAIL",
    "build stderr tail",
    "A4A_HYPOTHESIS",
    "PROTOS_REPOSITORY_CHANGED: NO",
):
    assert required in runner, required
makefile=Path("Makefile").read_text(encoding="utf-8")
assert "perf003a-a4a-smoke:" in makefile
assert "perf003a-a4a:" in makefile
print("PERF003A_A4A_STATIC_VALIDATION: PASS")
PYA4A

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in \
    docker/protos-perf003a-a4a/Dockerfile \
    docker/protos-perf003a-a4a/apply_boundary.py \
    scripts/perf003a_a4a_boundary_experiment.sh
do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done
printf 'PERF003A_A4A_LICENSE_CHECK: PASS\n'


# PERF003-A4b closure invoke-entry boundary falsification harness
bash -n scripts/perf003a_a4b_invoke_entry_experiment.sh
python3 -m py_compile docker/protos-perf003a-a4b/apply_boundary.py
python3 - <<'PYA4B'
import json, re
from pathlib import Path
cfg=json.loads(Path('config/perf003a-a4b.json').read_text(encoding='utf-8'))
assert cfg['schema_version'] == 1
assert cfg['perf_item'] == 'PERF003'
assert cfg['slice'] == 'PERF003-A4b'
assert cfg['protos_revision'] == 'd66841adb0b820047ed079f0bc7d643873f23194'
assert cfg['protos_implementation_version'] == '0.2.180-SNAPSHOT'
assert cfg['workload']['id'] == 'collections/array-reduce'
assert str(cfg['workload']['expected']) == '528'
assert cfg['diagnostic_iterations'] == 20
assert cfg['experimental_variant'] == 'closure-invoke-entry-boundary'
assert cfg['experimental_boundary'] == 'ProtosClosureInvoker.invoke(ProtosClosureValue,List,ProtosActivation)'

dockerfile=Path('docker/protos-perf003a-a4b/Dockerfile').read_text(encoding='utf-8')
for required in (
    'closure-invoke-entry-boundary',
    'python3 /tmp/apply_boundary.py /src',
    'apt-get install -y --no-install-recommends git ca-certificates python3',
    'git fetch --depth 1 origin',
):
    assert required in dockerfile, required
patch=Path('docker/protos-perf003a-a4b/apply_boundary.py').read_text(encoding='utf-8')
assert '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' in patch
assert 'ProtosActivation caller' in patch
runner=Path('scripts/perf003a_a4b_invoke_entry_experiment.sh').read_text(encoding='utf-8')
assert not re.search(r'local\s+[^\n]*prefix=\$[0-9][^\n]*\$\{prefix\}', runner)
for required in ('--smoke|--run','TraceCompilation=true','EXPERIMENT_PRECONDITION','A4B_HYPOTHESIS','PROTOS_REPOSITORY_CHANGED: NO'):
    assert required in runner, required
makefile=Path('Makefile').read_text(encoding='utf-8')
assert 'perf003a-a4b-smoke:' in makefile
assert 'perf003a-a4b:' in makefile
print('PERF003A_A4B_STATIC_VALIDATION: PASS')
PYA4B

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in \
    docker/protos-perf003a-a4b/Dockerfile \
    docker/protos-perf003a-a4b/apply_boundary.py \
    scripts/perf003a_a4b_invoke_entry_experiment.sh
do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done
printf 'PERF003A_A4B_LICENSE_CHECK: PASS\n'


# PERF003-A4c closure immediate-method boundary falsification harness
bash -n scripts/perf003a_a4c_immediate_method_experiment.sh
python3 -m py_compile docker/protos-perf003a-a4c/apply_boundary.py
python3 - <<'PYA4C'
import json, re
from pathlib import Path
cfg=json.loads(Path('config/perf003a-a4c.json').read_text(encoding='utf-8'))
assert cfg['schema_version']==1
assert cfg['perf_item']=='PERF003'
assert cfg['slice']=='PERF003-A4c'
assert cfg['protos_revision']=='d66841adb0b820047ed079f0bc7d643873f23194'
assert cfg['protos_implementation_version']=='0.2.180-SNAPSHOT'
assert cfg['diagnostic_iterations']==20
assert cfg['workload']['id']=='collections/array-reduce'
assert str(cfg['workload']['expected'])=='528'
assert cfg['experimental_variant']=='closure-immediate-method-boundary'
assert cfg['experimental_boundary']=='ProtosClosureInvoker.invokeImmediateMethod'
d=Path('docker/protos-perf003a-a4c/Dockerfile').read_text(encoding='utf-8')
for x in ('closure-immediate-method-boundary','python3 /tmp/apply_boundary.py /src','git ca-certificates python3'): assert x in d,x
b=Path('docker/protos-perf003a-a4c/apply_boundary.py').read_text(encoding='utf-8')
assert '@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary' in b
assert 'invokeImmediateMethod' in b and 'ProtosObjectValue methodHome' in b
r=Path('scripts/perf003a_a4c_immediate_method_experiment.sh').read_text(encoding='utf-8')
assert not re.search(r'local\s+[^\n]*prefix=\$[0-9][^\n]*\$\{prefix\}',r)
assert 'os.sched_getaffinity(0)' in r
assert 'Cpus_allowed_list' not in r
for x in ('--smoke|--run','TraceCompilation=true','A4C_HYPOTHESIS','PROTOS_REPOSITORY_CHANGED: NO'): assert x in r,x
m=Path('Makefile').read_text(encoding='utf-8')
assert 'perf003a-a4c-smoke:' in m and 'perf003a-a4c:' in m
print('PERF003A_A4C_STATIC_VALIDATION: PASS')
PYA4C
notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in docker/protos-perf003a-a4c/Dockerfile docker/protos-perf003a-a4c/apply_boundary.py scripts/perf003a_a4c_immediate_method_experiment.sh; do
  grep -qF "$notice" "$path" || { echo "missing APL notice: $path" >&2; exit 1; }
done
printf 'PERF003A_A4C_LICENSE_CHECK: PASS
'


# PERF003-A4c TraceCompilation graph-shape parser regression fixture.
python3 - <<'PYA4CPARSER'
import re
from pathlib import Path

runner = Path("scripts/perf003a_a4c_immediate_method_experiment.sh").read_text(
    encoding="utf-8"
)
bad = r"r'Node count:\\s*(\\d+)\\.\\s*Graph Size:\\s*(\\d+)\\.\\s*Limit:\\s*(\\d+)'"
good = r"r'Node count:\s*(\d+)\.\s*Graph Size:\s*(\d+)\.\s*Limit:\s*(\d+)'"
assert bad not in runner
assert runner.count(good) == 2

sample = (
    "GraphTooBigBailoutException: Graph too big to safely compile.\n"
    "Node count: 50681. Graph Size: 150026. Limit: 150000.\n"
)
pattern = re.compile(
    r"Node count:\s*(\d+)\.\s*Graph Size:\s*(\d+)\.\s*Limit:\s*(\d+)"
)
matches = pattern.findall(sample)
assert matches == [("50681", "150026", "150000")], matches
print("PERF003A_A4C_TRACE_PARSER_FIXTURE: PASS")
PYA4CPARSER


# PERF003-A4c conclusion serialization regression fixture.
python3 - <<'PYA4CCONCLUSION'
from pathlib import Path
runner=Path('scripts/perf003a_a4c_immediate_method_experiment.sh').read_text(encoding='utf-8')
bad="open(out,'w',encoding='utf-8').write(f'conclusion={c}\\\\nreason={r}\\\\n')"
good="open(out,'w',encoding='utf-8').write(f'conclusion={c}\\nreason={r}\\n')"
assert bad not in runner
assert runner.count(good) == 1
s='conclusion=SUPPORTED\nreason=immediate-method boundary eliminated GraphTooBig\n'
assert s.splitlines() == ['conclusion=SUPPORTED','reason=immediate-method boundary eliminated GraphTooBig']
print('PERF003A_A4C_CONCLUSION_SERIALIZER_FIXTURE: PASS')
PYA4CCONCLUSION


# PERF003-A4d immediate-activation boundary falsification harness
bash -n scripts/perf003a_a4d_immediate_activation_experiment.sh
python3 -m py_compile docker/protos-perf003a-a4d/apply_boundary.py
python3 - <<'PYA4D'
import json
from pathlib import Path

cfg=json.loads(Path("config/perf003a-a4d.json").read_text(encoding="utf-8"))
assert cfg["slice"]=="PERF003-A4d"
assert cfg["protos_revision"]=="d66841adb0b820047ed079f0bc7d643873f23194"
assert cfg["diagnostic_iterations"]==20
assert cfg["workload"]["id"]=="collections/array-reduce"
assert str(cfg["workload"]["expected"])=="528"
assert cfg["experimental_variant"]=="immediate-activation-boundary"
assert cfg["experimental_boundary"]=="ProtosActivation.forImmediateMethodInvocation"

dockerfile=Path("docker/protos-perf003a-a4d/Dockerfile").read_text(encoding="utf-8")
assert "control|immediate-activation-boundary" in dockerfile
assert 'if [ "$DIAGNOSTIC_VARIANT" = immediate-activation-boundary ]; then' in dockerfile

patch=Path("docker/protos-perf003a-a4d/apply_boundary.py").read_text(encoding="utf-8")
assert "ProtosActivation.java" in patch
assert "forImmediateMethodInvocation" in patch
assert "@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary" in patch

runner=Path("scripts/perf003a_a4d_immediate_activation_experiment.sh").read_text(encoding="utf-8")
for required in (
    "os.sched_getaffinity(0)",
    "TraceCompilation=true",
    "ProtosActivation.java",
    "forImmediateMethodInvocation",
    "A4D_HYPOTHESIS",
    "PROTOS_REPOSITORY_CHANGED: NO",
):
    assert required in runner, required
assert "Cpus_allowed_list" not in runner
print("PERF003A_A4D_STATIC_VALIDATION: PASS")
PYA4D

notice='THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE'
for path in \
    docker/protos-perf003a-a4d/Dockerfile \
    docker/protos-perf003a-a4d/apply_boundary.py \
    scripts/perf003a_a4d_immediate_activation_experiment.sh
do
    grep -qF "$notice" "$path" || {
        echo "missing APL notice: $path" >&2
        exit 1
    }
done
printf 'PERF003A_A4D_LICENSE_CHECK: PASS\n'
