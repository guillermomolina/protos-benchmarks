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

TRUFFLE_DIR := truffle

WORKLOAD ?= all
LANGUAGE ?= protos
PROTOS_REPO ?= .work/protos-ab/0.3.128

.PHONY: truffle-compile truffle-correctness truffle-jvm-smoke truffle-jvm-benchmark truffle-jvm-ab truffle-native-setup truffle-native-smoke truffle-native-benchmark truffle-clean truffle-prepare truffle-retain-results truffle-verify-retained-results

include docker/Makefile

truffle-prepare:
	$(MAKE) -C $(TRUFFLE_DIR) prepare

truffle-compile:
	$(MAKE) -C $(TRUFFLE_DIR) compile

truffle-correctness:
	$(MAKE) -C $(TRUFFLE_DIR) correctness

truffle-jvm-smoke:
	$(MAKE) -C $(TRUFFLE_DIR) jvm-smoke

truffle-jvm-benchmark:
	$(MAKE) -C $(TRUFFLE_DIR) jvm-benchmark


truffle-jvm-ab:
	$(MAKE) -C $(TRUFFLE_DIR) jvm-ab


truffle-jvm-jfr:
	$(MAKE) -C $(TRUFFLE_DIR) jvm-jfr LANGUAGE=$(LANGUAGE) WORKLOAD=$(WORKLOAD) PROTOS_REPO=$(PROTOS_REPO)

truffle-jvm-igv:
	$(MAKE) -C $(TRUFFLE_DIR) jvm-igv LANGUAGE=$(LANGUAGE) WORKLOAD=$(WORKLOAD) PROTOS_REPO=$(PROTOS_REPO)

truffle-native-jfr:
	$(MAKE) -C $(TRUFFLE_DIR) native-jfr

truffle-native-igv:
	$(MAKE) -C $(TRUFFLE_DIR) native-igv

truffle-native-setup:
	$(MAKE) -C $(TRUFFLE_DIR) native-setup

truffle-native-smoke:
	$(MAKE) -C $(TRUFFLE_DIR) native-smoke

truffle-native-benchmark:
	$(MAKE) -C $(TRUFFLE_DIR) native-benchmark


truffle-retain-results:
	$(MAKE) -C $(TRUFFLE_DIR) retain-results \
		WORK_ITEM="$(WORK_ITEM)" \
		PRODUCER_REVISION="$(PRODUCER_REVISION)" \
		RETAIN_WORKLOADS="$(RETAIN_WORKLOADS)" \
		EXPECTED_RETAINED="$(EXPECTED_RETAINED)"

truffle-verify-retained-results:
	$(MAKE) -C $(TRUFFLE_DIR) verify-retained-results \
		WORK_ITEM="$(WORK_ITEM)"

truffle-clean:
	$(MAKE) -C $(TRUFFLE_DIR) clean
