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
.PHONY: perf001g-validate perf001g-run

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
	@if [ -n "$(BGV)" ]; then \
		./scripts/igv_analyzer.sh smoke "$(BGV)"; \
	else \
		./scripts/igv_analyzer.sh smoke; \
	fi

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

perf001g-validate:
	python3 runner/perf001g.py validate

perf001g-run:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf001g-run HARNESS_REVISION=<published-G1-SHA> OUT=<output-dir>" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf001g-run HARNESS_REVISION=<published-G1-SHA> OUT=<output-dir>" >&2; exit 2; }
	python3 runner/perf001g.py run --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf006d-validate perf006d-smoke

perf006d-validate:
	python3 runner/perf006d.py validate

perf006d-smoke:
	python3 runner/perf006d.py smoke

.PHONY: perf006d-timing-smoke perf006d-reference

perf006d-timing-smoke:
	python3 runner/perf006d.py timing-smoke

perf006d-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf006d-reference HARNESS_REVISION=<published-D2A-SHA> OUT=results/perf006-d2" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf006d-reference HARNESS_REVISION=<published-D2A-SHA> OUT=results/perf006-d2" >&2; exit 2; }
	python3 runner/perf006d.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf006d3-validate perf006d3-smoke perf006d3-reference

perf006d3-validate:
	python3 runner/perf006d3.py validate

perf006d3-smoke:
	python3 runner/perf006d3.py smoke

perf006d3-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf006d3-reference HARNESS_REVISION=<published-D3A-SHA> OUT=results/perf006-d3" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf006d3-reference HARNESS_REVISION=<published-D3A-SHA> OUT=results/perf006-d3" >&2; exit 2; }
	python3 runner/perf006d3.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf008-validate perf008-smoke perf008-reference

perf008-validate:
	python3 runner/perf008.py validate

perf008-smoke:
	python3 runner/perf008.py smoke

perf008-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf008-reference HARNESS_REVISION=<published-PERF008-SHA> OUT=results/perf008" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf008-reference HARNESS_REVISION=<published-PERF008-SHA> OUT=results/perf008" >&2; exit 2; }
	python3 runner/perf008.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf010a-validate perf010a-smoke perf010a-reference

# ABLATION selects which PERF010-A causal ablation slice runs: 1 (semantic/helper Bytecode
# dispatch, config/perf010a.json), 2 (ProtosActivation.lookup, config/perf010a-2.json), or 3
# (ProtosObjectValue.readLocalSlot's redundant containsKey+get, config/perf010a-3.json).
# Defaults to 1 so these targets' existing behavior (and PERF010A_ABLATION_1's already-
# retained results/perf010a-1 evidence) is unchanged when ABLATION is not passed explicitly.
ABLATION ?= 1

perf010a-validate:
	python3 runner/perf010a.py validate --ablation $(ABLATION)

perf010a-smoke:
	python3 runner/perf010a.py smoke --ablation $(ABLATION)

perf010a-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf010a-reference HARNESS_REVISION=<published-PERF010A-SHA> OUT=results/perf010a-1 [ABLATION=1|2|3]" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf010a-reference HARNESS_REVISION=<published-PERF010A-SHA> OUT=results/perf010a-1 [ABLATION=1|2|3]" >&2; exit 2; }
	python3 runner/perf010a.py reference --ablation $(ABLATION) --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"
.PHONY: perf004a-validate perf004a-smoke perf004a-reference

perf004a-validate:
	python3 runner/perf004a.py validate

perf004a-smoke:
	python3 runner/perf004a.py smoke

perf004a-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf004a-reference HARNESS_REVISION=<published-A2-SHA>" >&2; exit 2; }
	python3 runner/perf004a.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir results/perf004-a

.PHONY: perf004b1-validate perf004b1-reference

perf004b1-validate:
	python3 runner/perf004b.py validate

perf004b1-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf004b1-reference HARNESS_REVISION=<published-B1-SHA> OUT=results/perf004-b1" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf004b1-reference HARNESS_REVISION=<published-B1-SHA> OUT=results/perf004-b1" >&2; exit 2; }
	python3 runner/perf004b.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf004b2a-validate perf004b2a-reference

perf004b2a-validate:
	python3 runner/perf004b2.py validate

perf004b2a-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf004b2a-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2a" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf004b2a-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2a" >&2; exit 2; }
	python3 runner/perf004b2.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf004b2b-validate perf004b2b-reference

perf004b2b-validate:
	python3 runner/perf004b2b.py validate

perf004b2b-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf004b2b-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2b" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf004b2b-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2b" >&2; exit 2; }
	python3 runner/perf004b2b.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf004b2c-validate perf004b2c-reference

perf004b2c-validate:
	python3 runner/perf004b2c.py validate

perf004b2c-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf004b2c-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2c" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf004b2c-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2c" >&2; exit 2; }
	python3 runner/perf004b2c.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf004b2c-validate perf004b2c-reference

perf004b2c-validate:
	python3 runner/perf004b2c.py validate

perf004b2c-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf004b2c-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2c" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf004b2c-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2c" >&2; exit 2; }
	python3 runner/perf004b2c.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"

.PHONY: perf004b2d-validate perf004b2d-reference

perf004b2d-validate:
	python3 runner/perf004b2d.py validate

perf004b2d-reference:
	@test -n "$(HARNESS_REVISION)" || { echo "usage: make perf004b2d-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2d" >&2; exit 2; }
	@test -n "$(OUT)" || { echo "usage: make perf004b2d-reference HARNESS_REVISION=<published-SHA> OUT=results/perf004-b2d" >&2; exit 2; }
	python3 runner/perf004b2d.py reference --harness-revision "$(HARNESS_REVISION)" --output-dir "$(OUT)"
