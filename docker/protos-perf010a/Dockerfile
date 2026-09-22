# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
# THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
# "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE. IF A COPY OF THE
# LICENSE DOES NOT ACCOMPANY THIS FILE, A COPY OF THE LICENSE MAY ALSO BE
# OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# PERF010-A / #691 causal semantic/helper-dispatch ablation image.
#
# Builds either of two images from the exact same pinned Protos revision:
#
#   VARIANT=baseline  - unmodified Protos, no diagnostic patch applied.
#   VARIANT=ablation   - the patch named by ABLATION_PATCH applied before the build. This
#                        harness now backs three distinct causal ablations sharing this same
#                        Dockerfile/image layout, selected only by which patch is supplied:
#                          - ABLATION_PATCH=ablation.patch (default) - PERF010A_ABLATION_1,
#                            bypasses the semantic/helper Bytecode dispatch wrapper (see
#                            docker/protos-perf010a/ablation.patch).
#                          - ABLATION_PATCH=ablation-2.patch - PERF010A_ABLATION_2, bypasses
#                            ProtosActivation.lookup with activation.context().readLocalSlot(name)
#                            (see docker/protos-perf010a/ablation-2.patch).
#                          - ABLATION_PATCH=ablation-3.patch - PERF010A_ABLATION_3, replaces the
#                            redundant containsKey(name)+get(name) probe-then-read inside
#                            ProtosObjectValue.readLocalSlot with a single get(name) (see
#                            docker/protos-perf010a/ablation-3.patch). The full patched (or, for
#                            baseline, unmodified) /src tree is copied to /opt/protos-source in
#                            every image below; this ablation's structural confirmation reads
#                            that source directly instead of JFR call-stack frames, since the
#                            ablated Map operations are simple enough to be JIT-inlined and are
#                            not a reliable sampled-frame signal.
#                        ABLATION_SLICE records which slice produced the image, for the
#                        structural marker written to /opt/perf010a/ablation-slice.txt.
#
# The patch is applied inside this Docker build only; the checked-out `guillermomolina/protos`
# source tree this harness pins is never modified or republished. Both images reuse the
# PERF008/PERF006-D3 diagnostic driver conventions (Perf006dRuntimeProbe, steady-state JFR
# driver + full-stack analyzer) for structural evidence, plus a new JFR-free timing driver
# (Perf010aTimingDriver) so steady-state wall-clock timing is never perturbed by JFR recording
# overhead (see AGENTS.work/REPRODUCIBILITY.md: "Diagnostic instrumentation ... SHOULD be kept
# separate from timing when it materially perturbs execution.").
ARG GRAAL_BASE=ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825
FROM ${GRAAL_BASE} AS build

USER root
ARG PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git
ARG PROTOS_REVISION
ARG VARIANT=baseline
ARG ABLATION_PATCH=ablation.patch
ARG ABLATION_SLICE=PERF010A_ABLATION_1

# Expected toolchain identity declared by protos' own toolchain.json at PROTOS_REVISION.
ARG EXPECTED_GRAALVM_RELEASE=25.3.4.1
ARG EXPECTED_JDK_VERSION=25.0.4.1
ARG EXPECTED_CONTAINER_IMAGE=ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825
ARG EXPECTED_GRAAL_COMPONENTS_VERSION=25.3.4.1
ARG EXPECTED_MAVEN_VERSION=3.9.9
ARG PYTHON_PACKAGE=python3

COPY docker/protos-perf006d/Perf006dRuntimeProbe.java /tmp/Perf006dRuntimeProbe.java
COPY docker/protos-perf006d/Perf006dPersistentDriver.java /tmp/Perf006dPersistentDriver.java
COPY docker/protos-perf006d3/Perf008SteadyStateDriver.java /tmp/Perf008SteadyStateDriver.java
COPY docker/protos-perf006d3/Perf006d3JfrAnalyzer.java /tmp/Perf006d3JfrAnalyzer.java
COPY docker/protos-perf006d3/jfr-java /tmp/perf006d3-jfr-java
COPY docker/protos-perf010a/Perf010aTimingDriver.java /tmp/Perf010aTimingDriver.java
COPY docker/protos-perf010a/${ABLATION_PATCH} /tmp/ablation.patch

# Maven comes from the base image's own OS package repository (ol10 AppStream), not a
# hand-downloaded archive.apache.org tarball: investigation in the `protos` devcontainer
# established that `microdnf install maven` on this exact GraalVM base image resolves to
# `maven-3.9.9-3.el10_1`, matching the `3.9.9` pinned by `toolchain.json`/EXPECTED_MAVEN_VERSION
# exactly, and the resulting `mvn` on PATH already runs under `JAVA_HOME` (GraalVM), not the
# `java-21-openjdk-headless` package it pulls in as a transitive dependency. The RUN below still
# asserts the installed version against EXPECTED_MAVEN_VERSION so an OS-image bump that changes
# the packaged Maven version is caught here instead of silently drifting.
RUN microdnf install -y git gzip tar findutils ca-certificates ${PYTHON_PACKAGE} unzip patch maven \
    && microdnf clean all \
    && mvn -version \
    && mvn -version | grep -q "Apache Maven ${EXPECTED_MAVEN_VERSION} " \
    && mvn -version | grep -q "GraalVM Community"

RUN test -n "$PROTOS_REVISION" \
    && test "$VARIANT" = "baseline" -o "$VARIANT" = "ablation" \
    && git init /src \
    && cd /src \
    && git remote add origin "$PROTOS_REPOSITORY" \
    && git fetch --depth 1 origin "$PROTOS_REVISION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$PROTOS_REVISION" \
    && EXPECTED_GRAALVM_RELEASE="$EXPECTED_GRAALVM_RELEASE" \
       EXPECTED_JDK_VERSION="$EXPECTED_JDK_VERSION" \
       EXPECTED_CONTAINER_IMAGE="$EXPECTED_CONTAINER_IMAGE" \
       EXPECTED_GRAAL_COMPONENTS_VERSION="$EXPECTED_GRAAL_COMPONENTS_VERSION" \
       EXPECTED_MAVEN_VERSION="$EXPECTED_MAVEN_VERSION" \
       python3 - <<'PY'
import json
import os
from pathlib import Path
cfg = json.loads(Path("/src/toolchain.json").read_text(encoding="utf-8"))
assert cfg["graalvm"]["release"] == os.environ["EXPECTED_GRAALVM_RELEASE"]
assert cfg["graalvm"]["jdk_version"] == os.environ["EXPECTED_JDK_VERSION"]
assert cfg["graalvm"]["container_image"] == os.environ["EXPECTED_CONTAINER_IMAGE"]
assert cfg["graal_components"]["version"] == os.environ["EXPECTED_GRAAL_COMPONENTS_VERSION"]
assert cfg["maven"]["version"] == os.environ["EXPECTED_MAVEN_VERSION"]
print("PERF010A_SOURCE_TOOLCHAIN=PASS")
PY

# VARIANT=ablation applies the diagnostic bypass patch to the pinned checkout only; the patch
# never touches guillermomolina/protos itself (git operations here are container-local).
RUN cd /src \
    && if [ "$VARIANT" = "ablation" ]; then \
         git apply --verbose /tmp/ablation.patch \
         && echo "PERF010A_ABLATION_PATCH_APPLIED=YES"; \
       else \
         echo "PERF010A_ABLATION_PATCH_APPLIED=NO"; \
       fi

# `dist/build_portable.py` refuses a dirty worktree by default (its `--allow-dirty` escape
# hatch is documented for "pre-commit validation only"). The ablation variant's `git apply`
# above necessarily leaves `/src` dirty on top of the exact pinned $PROTOS_REVISION commit;
# `git rev-parse HEAD` (recorded as source_revision/SOURCE.txt identity) is unaffected by the
# uncommitted patch, and the resulting SOURCE.txt honestly records `source_dirty=true` for the
# ablation image. The baseline variant never applies the patch, so its build stays on a clean
# tree and needs no flag.
RUN cd /src \
    && if [ "$VARIANT" = "ablation" ]; then \
         python3 dist/build_portable.py --allow-dirty; \
       else \
         python3 dist/build_portable.py; \
       fi \
    && BUNDLE="$(find target/distributions -maxdepth 1 -mindepth 1 -type d -name 'protos-*' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$BUNDLE" \
    && test -f "$BUNDLE/lib/protos.jar" \
    && test -d "$BUNDLE/lib/runtime" \
    && mkdir -p /out/protos /out/source /out/corpus /out/diagnostic /out/analyzer /out/jfr \
    && cp -a "$BUNDLE"/. /out/protos/ \
    && cp -a /src/. /out/source/ \
    && rm -rf /out/source/target \
    && cp -a protos/benchmarks/. /out/corpus/ \
    && javac -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
         -d /out/diagnostic /tmp/Perf006dRuntimeProbe.java /tmp/Perf006dPersistentDriver.java \
         /tmp/Perf010aTimingDriver.java \
    && javac --add-modules jdk.jfr -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
         -d /out/diagnostic /tmp/Perf008SteadyStateDriver.java \
    && javac --add-modules jdk.jfr -d /out/analyzer /tmp/Perf006d3JfrAnalyzer.java \
    && jfr configure \
         --input "$JAVA_HOME/lib/jfr/profile.jfc" \
         --output /out/jfr/perf010a.jfc \
         'jdk.ExecutionSample#enabled=true' \
         'jdk.ExecutionSample#period=10ms' \
         'jdk.Deoptimization#enabled=true' \
         'jdk.Deoptimization#stackTrace=true' \
         '+jdk.graal.compiler.truffle.Deoptimization#enabled=true' \
    && test -s /out/jfr/perf010a.jfc \
    && install -m 0755 /tmp/perf006d3-jfr-java /out/jfr-java \
    && echo "$VARIANT" > /out/variant.txt \
    && if [ "$VARIANT" = "ablation" ]; then \
         echo "$ABLATION_SLICE" > /out/ablation-slice.txt; \
       else \
         echo "none" > /out/ablation-slice.txt; \
       fi

FROM ${GRAAL_BASE}
USER root
ARG VARIANT=baseline
ARG ABLATION_SLICE=PERF010A_ABLATION_1
COPY --from=build /out/protos /opt/protos
COPY --from=build /out/source /opt/protos-source
COPY --from=build /out/corpus /opt/perf010a/corpus
COPY --from=build /out/diagnostic /opt/perf010a/diagnostic
COPY --from=build /out/analyzer /opt/perf010a/analyzer
COPY --from=build /out/jfr/perf010a.jfc /opt/perf010a/perf010a.jfc
COPY --from=build /out/jfr-java /opt/perf010a/jfr-java
COPY --from=build /out/variant.txt /opt/perf010a/variant.txt
COPY --from=build /out/ablation-slice.txt /opt/perf010a/ablation-slice.txt
LABEL org.protos-benchmarks.perf010a.variant="${VARIANT}"
LABEL org.protos-benchmarks.perf010a.ablation-slice="${ABLATION_SLICE}"
ENV PROTOS_HOME=/opt/protos
ENV PERF010A_VARIANT="${VARIANT}"
WORKDIR /opt/protos-source
