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

.PHONY: validate test build smoke correctness all inventory igv-analyzer-build igv-analyzer-smoke perf003a-diagnostic perf003a-structural perf003a-structural-resume perf003a-structural-compact perf003a-structural-finalize perf003a-a4a-smoke perf003a-a4a perf003a-a4b-smoke perf003a-a4b perf003a-a4c-smoke perf003a-a4c perf003a-a4d-smoke perf003a-a4d perf003a-a4e-smoke perf003a-a4e perf003a-a4f-smoke perf003a-a4f perf003a-a4g-smoke perf003a-a4g perf003a-a4h-smoke perf003a-a4h perf003a-a4i perf001f-validate perf001f-topology perf001f-build perf001f-correctness perf001f-prepare perf001f-persistent-smoke perf001f-h2-prepare
.PHONY: perf001f-reference-smoke perf001f-reference

validate:
	./scripts/validate.sh

test:
	python3 -m unittest discover -s tests -v

build:
	python3 runner/bench.py build

smoke:
	python3 runner/bench.py smoke

correctness:
	python3 runner/bench.py correctness

all:
	python3 runner/bench.py all

inventory:
	python3 runner/bench.py inventory

igv-analyzer-build:
	./scripts/igv_analyzer.sh build

igv-analyzer-smoke:
	./scripts/igv_analyzer.sh smoke

perf003a-diagnostic:
	./scripts/perf003a_diagnostic.sh .work/perf003-a

perf003a-structural:
	./scripts/perf003a_structural.sh .work/perf003-a-structural

perf003a-structural-resume:
	@test -n "$(WORK)" || { echo "usage: make perf003a-structural-resume WORK=<existing-run-dir>" >&2; exit 2; }
	./scripts/perf003a_structural_resume.sh "$(WORK)"

perf003a-structural-compact:
	@test -n "$(WORK)" || { echo "usage: make perf003a-structural-compact WORK=<existing-run-dir>" >&2; exit 2; }
	./scripts/perf003a_structural_compact.sh "$(WORK)"

perf003a-structural-finalize:
	@test -n "$(WORK)" || { echo "WORK is required" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "OUT is required" >&2; exit 2; }
	@test -n "$(CAPTURE_HARNESS_REVISION)" || { echo "CAPTURE_HARNESS_REVISION is required" >&2; exit 2; }
	@test -n "$(COMPACT_EXTRACTOR_REVISION)" || { echo "COMPACT_EXTRACTOR_REVISION is required" >&2; exit 2; }
	@test -n "$(FINALIZATION_BASE)" || { echo "FINALIZATION_BASE is required" >&2; exit 2; }
	python3 scripts/perf003a_structural_finalize_compact.py --config config/perf003a-structural.json --run-dir "$(WORK)" --output-dir "$(OUT)" --capture-harness-revision "$(CAPTURE_HARNESS_REVISION)" --compact-extractor-revision "$(COMPACT_EXTRACTOR_REVISION)" --finalization-base "$(FINALIZATION_BASE)"

perf003a-a4a-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4a-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4a_boundary_experiment.sh --smoke "$(OUT)"

perf003a-a4a:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4a OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4a_boundary_experiment.sh --run "$(OUT)"

perf003a-a4b-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4b-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4b_invoke_entry_experiment.sh --smoke "$(OUT)"

perf003a-a4b:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4b OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4b_invoke_entry_experiment.sh --run "$(OUT)"

perf003a-a4c-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4c-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4c_immediate_method_experiment.sh --smoke "$(OUT)"

perf003a-a4c:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4c OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4c_immediate_method_experiment.sh --run "$(OUT)"

perf003a-a4d-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4d-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4d_immediate_activation_experiment.sh --smoke "$(OUT)"

perf003a-a4d:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4d OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4d_immediate_activation_experiment.sh --run "$(OUT)"

perf003a-a4e-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4e-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4e_prepared_dynamic_control_experiment.sh --smoke "$(OUT)"

perf003a-a4e:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4e OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4e_prepared_dynamic_control_experiment.sh --run "$(OUT)"

perf003a-a4f-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4f-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4f_prepared_replay_activation_experiment.sh --smoke "$(OUT)"

perf003a-a4f:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4f OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4f_prepared_replay_activation_experiment.sh --run "$(OUT)"

perf003a-a4g-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4g-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4g_preparation_smoke.sh "$(OUT)"

perf003a-a4g:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4g OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4g_experiment.sh "$(OUT)"

perf003a-a4h-smoke:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4h-smoke OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4h_sync_task_split_smoke.sh "$(OUT)"

perf003a-a4h:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4h OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4h_experiment.sh "$(OUT)"

perf003a-a4i:
	@test -n "$(OUT)" || { echo "usage: make perf003a-a4i OUT=<output-dir>" >&2; exit 2; }
	./scripts/perf003a_a4i_experiment.sh "$(OUT)"

perf001f-validate:
	python3 runner/perf001f.py validate

perf001f-topology:
	python3 runner/perf001f.py topology

perf001f-build:
	python3 runner/perf001f.py build

perf001f-correctness:
	python3 runner/perf001f.py correctness

perf001f-prepare:
	python3 runner/perf001f.py prepare

perf001f-persistent-smoke:
	python3 runner/perf001f.py persistent-smoke

perf001f-h2-prepare:
	python3 runner/perf001f.py h2-prepare

perf001f-reference-smoke:
	python3 runner/perf001f_reference.py --smoke

perf001f-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf001f-reference HARNESS_REVISION=<published-H3-SHA>" >&2; exit 2; }
	python3 runner/perf001f_reference.py --run --harness-revision "$(HARNESS_REVISION)" --output-dir results/perf001-f
