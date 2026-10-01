# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

.PHONY: compile correctness jvm-smoke jvm-benchmark jvm-ab native-setup native-smoke native-benchmark clean

MAIN_CLASS := com.guillermomolina.protos.benchmarks.truffle.TruffleJvmRunner

WORKLOAD ?= all
LANGUAGE ?= protos
PROTOS_REPO ?= .work/protos-ab/0.3.128

compile:
	mvn -q compile

correctness: compile
	mvn -q exec:java -Dexec.mainClass=$(MAIN_CLASS) -Dexec.args="correctness protos workloads/fibonacci/fibonacci.protos"
	mvn -q exec:java -Dexec.mainClass=$(MAIN_CLASS) -Dexec.args="correctness js workloads/fibonacci/fibonacci.mjs"
	mvn -q exec:java -Dexec.mainClass=$(MAIN_CLASS) -Dexec.args="correctness python workloads/fibonacci/fibonacci.py"
	mvn -q exec:java -Dexec.mainClass=$(MAIN_CLASS) -Dexec.args="correctness protos workloads/factorial/factorial.protos"
	mvn -q exec:java -Dexec.mainClass=$(MAIN_CLASS) -Dexec.args="correctness js workloads/factorial/factorial.mjs"
	mvn -q exec:java -Dexec.mainClass=$(MAIN_CLASS) -Dexec.args="correctness python workloads/factorial/factorial.py"

jvm-smoke:
	python3 jvm_matrix.py smoke $(WORKLOAD)

jvm-benchmark:
	python3 jvm_matrix.py benchmark $(WORKLOAD)


jvm-ab:
	WORKLOAD=$(WORKLOAD) python3 jvm_protos_ab.py benchmark \
		.work/protos-ab/0.3.128 \
		.work/protos-ab/0.3.129


jvm-jfr:
	PROTOS_REPO=$(PROTOS_REPO) python3 jvm_diagnostic.py jfr $(LANGUAGE) $(WORKLOAD)

jvm-igv:
	PROTOS_REPO=$(PROTOS_REPO) python3 jvm_diagnostic.py igv $(LANGUAGE) $(WORKLOAD)

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

clean:
	mvn -q clean
