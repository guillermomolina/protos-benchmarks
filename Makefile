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

PYTHON ?= python3
HARNESS := benchmark.py

CASE ?= primitive-return-literal
LANGUAGE ?= all
PROTOS_VERSION ?=
GRAALJS_VERSION ?=
GRAALPY_VERSION ?=
STAGE ?= reference
PROFILE ?= none
TEMPERATURE ?= hot
TIER ?= 2
COMPILATION_ROOT ?= primary
WARMUP_CALLS ?= 0
INVOCATIONS ?= 2000
FIRST_THRESHOLD ?= 100
LAST_THRESHOLD ?=
JVM_OPTION ?=
SURFACE ?= canonical
CPU ?=
OUTPUT ?=
PROTOS_REPO ?= $(abspath ../protos)
PODMAN_IMAGE ?= localhost/protos-bench-runner:graal25.4.4.1.1-standalone

ARGS = --case "$(CASE)" --language "$(LANGUAGE)" --stage "$(STAGE)" \
       --profile "$(PROFILE)" --surface "$(SURFACE)" \
       --temperature "$(TEMPERATURE)" \
       --product "$(PROTOS_REPO)" --image "$(PODMAN_IMAGE)" \
       $(if $(strip $(PROTOS_VERSION)),--protos-version "$(PROTOS_VERSION)",) \
       $(if $(strip $(GRAALJS_VERSION)),--js-version "$(GRAALJS_VERSION)",) \
       $(if $(strip $(GRAALPY_VERSION)),--python-version "$(GRAALPY_VERSION)",) \
       $(if $(strip $(CPU)),--cpu "$(CPU)",) \
       $(if $(strip $(OUTPUT)),--output "$(OUTPUT)",)

.PHONY: help validate correctness measure smoke graphs-capture graphs-analyze graphs-summarize graphs-verify image-status image-build peer-prepare cold-capture cold-analyze cold-summarize

help:
	@$(PYTHON) $(HARNESS) --help

validate:
	@$(PYTHON) $(HARNESS) validate

correctness:
	@$(PYTHON) $(HARNESS) correctness $(ARGS)

measure:
	@$(PYTHON) $(HARNESS) measure $(ARGS)

smoke:
	@$(PYTHON) $(HARNESS) smoke $(ARGS)

graphs-capture:
	@$(PYTHON) $(HARNESS) graphs-capture $(ARGS)

graphs-analyze:
	@$(PYTHON) $(HARNESS) graphs-analyze $(ARGS)

graphs-summarize:
	@$(PYTHON) $(HARNESS) graphs-summarize $(ARGS)

graphs-verify:
	@$(PYTHON) $(HARNESS) graphs-verify $(ARGS)

peer-prepare:
	@$(PYTHON) $(HARNESS) peer-prepare $(ARGS)

image-status:
	@$(PYTHON) $(HARNESS) image-status --image "$(PODMAN_IMAGE)"

image-build:
	@$(PYTHON) $(HARNESS) image-build --image "$(PODMAN_IMAGE)"

COLD_ARGS = --tier "$(TIER)" --root "$(COMPILATION_ROOT)" \
            --warmup-calls "$(WARMUP_CALLS)" \
            --invocations "$(INVOCATIONS)" \
            --first-threshold "$(FIRST_THRESHOLD)" \
            $(if $(strip $(LAST_THRESHOLD)),--last-threshold "$(LAST_THRESHOLD)",) \
            $(if $(strip $(JVM_OPTION)),--jvm-option "$(JVM_OPTION)",)

cold-capture:
	@$(PYTHON) $(HARNESS) cold-capture $(ARGS) $(COLD_ARGS)

cold-analyze:
	@$(PYTHON) $(HARNESS) cold-analyze $(ARGS) $(COLD_ARGS)

cold-summarize:
	@$(PYTHON) $(HARNESS) cold-summarize $(ARGS) $(COLD_ARGS)
