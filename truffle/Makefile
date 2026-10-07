# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

.PHONY: measure compile correctness jvm-smoke jvm-benchmark jvm-ab native-setup native-smoke native-benchmark clean prepare retain-results verify-retained-results perf025-d2-validate perf025-d2-prepare perf025-d2-smoke perf025-reference perf024-rebaseline-validate perf024-rebaseline-prepare perf024-rebaseline-smoke perf024-rebaseline-reference perf025-e3-validate perf025-e3-prepare perf025-e3-smoke perf025-e3-reference

MAIN_CLASS := com.guillermomolina.protos.benchmarks.truffle.TruffleJvmRunner

WORKLOAD ?= all
LANGUAGE ?= protos
PROTOS_CHECKOUT ?= /workspaces/protos
PROTOS_RUN_MODE ?= auto
DIAGNOSTIC_WARMUP ?= 5
DIAGNOSTIC_STEADY ?= 10
DIAGNOSTIC_SAMPLE_CALLS ?=
RETENTION_PROFILE ?= perf023

# Revision-independent driver: measures exactly PROTOS_CHECKOUT. A new Protos
# revision never requires editing harness source; see BENCHMARKING.md.
SURFACE ?= canonical
STAGE ?= reference
PROFILE ?= none
OUTPUT ?=

measure:
	python3 measure_protos.py --dir "$(PROTOS_CHECKOUT)" --language "$(LANGUAGE)" \
		$(if $(filter protos,$(LANGUAGE)),--surface "$(SURFACE)",) \
		--workload "$(WORKLOAD)" --stage "$(STAGE)" --profile "$(PROFILE)" \
		--output "$(OUTPUT)"

prepare:
	python3 prepare.py

compile:
	mvn -q compile

correctness:
	PROTOS_CHECKOUT="$(PROTOS_CHECKOUT)" PROTOS_RUN_MODE="$(PROTOS_RUN_MODE)" python3 jvm_correctness.py $(WORKLOAD)

jvm-smoke:
	PROTOS_CHECKOUT="$(PROTOS_CHECKOUT)" PROTOS_RUN_MODE="$(PROTOS_RUN_MODE)" python3 jvm_matrix.py smoke $(WORKLOAD)

jvm-benchmark:
	PROTOS_CHECKOUT="$(PROTOS_CHECKOUT)" PROTOS_RUN_MODE="$(PROTOS_RUN_MODE)" python3 jvm_matrix.py benchmark $(WORKLOAD)


jvm-ab:
	WORKLOAD=$(WORKLOAD) python3 jvm_protos_ab.py benchmark \
		.work/protos-ab/0.3.128 \
		.work/protos-ab/0.3.129

# PERF025: PRE_A/dynamic, A/dynamic, B/prepared, FINAL/prepared on the three
# primitive embedding workloads. perf025-reference requires a clean harness.
perf025-d2-validate:
	python3 jvm_protos_ab.py perf025 validate

perf025-d2-prepare:
	python3 jvm_protos_ab.py perf025 prepare

perf025-d2-smoke:
	python3 jvm_protos_ab.py perf025 smoke

perf025-reference:
	python3 jvm_protos_ab.py perf025 benchmark

# PERF024 post-PERF025/PERF026 cross-Truffle re-baseline: CURRENT Protos
# (prepared) vs GraalJS/GraalPy (prepared executable Value) on four existing
# workloads. perf024-rebaseline-reference requires a clean harness.
perf024-rebaseline-validate:
	python3 perf024_rebaseline.py validate

perf024-rebaseline-prepare:
	python3 perf024_rebaseline.py prepare

perf024-rebaseline-smoke:
	python3 perf024_rebaseline.py smoke

perf024-rebaseline-reference:
	python3 perf024_rebaseline.py benchmark

# PERF025-E3: PRE_E2/prepared vs E2/prepared (exact parent) on the three
# primitive embedding workloads, isolating the E2 carrier transport delta.
# perf025-e3-reference requires a clean published harness.
perf025-e3-validate:
	python3 perf025_e3.py validate

perf025-e3-prepare:
	python3 perf025_e3.py prepare

perf025-e3-smoke:
	python3 perf025_e3.py smoke

perf025-e3-reference:
	python3 perf025_e3.py benchmark


jvm-jfr:
	PROTOS_CHECKOUT="$(PROTOS_CHECKOUT)" PROTOS_RUN_MODE="$(PROTOS_RUN_MODE)" DIAGNOSTIC_WARMUP="$(DIAGNOSTIC_WARMUP)" DIAGNOSTIC_STEADY="$(DIAGNOSTIC_STEADY)" $(if $(DIAGNOSTIC_SAMPLE_CALLS),DIAGNOSTIC_SAMPLE_CALLS="$(DIAGNOSTIC_SAMPLE_CALLS)",) python3 jvm_diagnostic.py jfr $(LANGUAGE) $(WORKLOAD)

jvm-igv:
	PROTOS_CHECKOUT="$(PROTOS_CHECKOUT)" PROTOS_RUN_MODE="$(PROTOS_RUN_MODE)" DIAGNOSTIC_WARMUP="$(DIAGNOSTIC_WARMUP)" DIAGNOSTIC_STEADY="$(DIAGNOSTIC_STEADY)" $(if $(DIAGNOSTIC_SAMPLE_CALLS),DIAGNOSTIC_SAMPLE_CALLS="$(DIAGNOSTIC_SAMPLE_CALLS)",) python3 jvm_diagnostic.py igv $(LANGUAGE) $(WORKLOAD)

native-jfr:
	@printf '%s\n' 'mode=native diagnostic=jfr status=N/A reason=pinned-native-runtime-not-built-and-validated-with-jfr-support'

native-igv:
	@printf '%s\n' 'mode=native diagnostic=igv status=N/A reason=pinned-native-runtime-graph-dump-support-not-validated'

native-setup:
	python3 native_setup.py

native-smoke:
	python3 native_matrix.py smoke $(WORKLOAD)

native-benchmark:
	python3 native_matrix.py benchmark $(WORKLOAD)


retain-results:
	python3 retain_results.py retain \
		--work-item "$(WORK_ITEM)" \
		--producer-revision "$(PRODUCER_REVISION)" \
		--workloads "$(RETAIN_WORKLOADS)" \
		--expect "$(EXPECTED_RETAINED)" \
		--profile "$(RETENTION_PROFILE)"

verify-retained-results:
	python3 retain_results.py verify \
		--work-item "$(WORK_ITEM)"

clean:
	mvn -q clean
