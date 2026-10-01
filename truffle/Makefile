# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

.PHONY: compile correctness jvm-smoke jvm-benchmark jvm-ab native-setup native-smoke native-benchmark clean prepare retain-results verify-retained-results

MAIN_CLASS := com.guillermomolina.protos.benchmarks.truffle.TruffleJvmRunner

WORKLOAD ?= all
LANGUAGE ?= protos

prepare:
	python3 prepare.py

compile:
	mvn -q compile

correctness: compile
	python3 jvm_correctness.py $(WORKLOAD)

jvm-smoke:
	python3 jvm_matrix.py smoke $(WORKLOAD)

jvm-benchmark:
	python3 jvm_matrix.py benchmark $(WORKLOAD)


jvm-ab:
	WORKLOAD=$(WORKLOAD) python3 jvm_protos_ab.py benchmark \
		.work/protos-ab/0.3.128 \
		.work/protos-ab/0.3.129


jvm-jfr:
	python3 jvm_diagnostic.py jfr $(LANGUAGE) $(WORKLOAD)

jvm-igv:
	python3 jvm_diagnostic.py igv $(LANGUAGE) $(WORKLOAD)

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
		--expect "$(EXPECTED_RETAINED)"

verify-retained-results:
	python3 retain_results.py verify \
		--work-item "$(WORK_ITEM)"

clean:
	mvn -q clean
