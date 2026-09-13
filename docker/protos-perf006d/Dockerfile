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

ARG GRAAL_BASE=ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825
FROM ${GRAAL_BASE} AS build

USER root
ARG MAVEN_VERSION=3.9.9
ARG PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git
ARG PROTOS_REVISION=4a03efc15620b37b2e418b3df30b4a26486446ec

COPY docker/protos-perf006d/Perf006dRuntimeProbe.java /tmp/Perf006dRuntimeProbe.java
COPY docker/protos-perf006d/Perf006dCorrectnessDriver.java /tmp/Perf006dCorrectnessDriver.java
COPY docker/protos-perf006d/run.sh /tmp/perf006d-run.sh

RUN microdnf install -y git gzip tar findutils ca-certificates python39 unzip \
    && microdnf clean all
RUN curl --fail --location --silent --show-error \
        "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
        --output /tmp/apache-maven.tar.gz \
    && tar --extract --gzip --file /tmp/apache-maven.tar.gz --directory /opt \
    && ln --symbolic "/opt/apache-maven-${MAVEN_VERSION}" /opt/maven \
    && rm /tmp/apache-maven.tar.gz
ENV MAVEN_HOME=/opt/maven
ENV PATH="/opt/maven/bin:${PATH}"

RUN git init /src \
    && cd /src \
    && git remote add origin "$PROTOS_REPOSITORY" \
    && git fetch --depth 1 origin "$PROTOS_REVISION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$PROTOS_REVISION" \
    && python3 - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path("/src/toolchain.json").read_text(encoding="utf-8"))
assert cfg["graalvm"]["release"] == "25.3.4.1"
assert cfg["graalvm"]["jdk_version"] == "25.0.4.1"
assert cfg["graalvm"]["container_image"] == "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825"
assert cfg["graal_components"]["version"] == "25.3.4.1"
assert cfg["maven"]["version"] == "3.9.9"
print("PERF006D1_SOURCE_TOOLCHAIN=PASS")
PY

RUN cd /src \
    && python3 dist/build_portable.py \
    && BUNDLE="$(find target/distributions -maxdepth 1 -mindepth 1 -type d -name 'protos-*' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$BUNDLE" \
    && test -f "$BUNDLE/lib/protos.jar" \
    && test -d "$BUNDLE/lib/runtime" \
    && mkdir -p /out/protos /out/corpus /out/probe /out/driver /out/runtime-fallback \
    && cp -a "$BUNDLE"/. /out/protos/ \
    && cp -a protos/benchmarks/. /out/corpus/ \
    && for jar in "$BUNDLE"/lib/runtime/*.jar; do \
         base="$(basename "$jar")"; \
         case "$base" in \
           *truffle-runtime-*|*truffle-compiler-*) ;; \
           *) cp "$jar" /out/runtime-fallback/ ;; \
         esac; \
       done \
    && test "$(find /out/runtime-fallback -maxdepth 1 -type f -name '*truffle-runtime-*' | wc -l)" -eq 0 \
    && test "$(find /out/runtime-fallback -maxdepth 1 -type f -name '*truffle-compiler-*' | wc -l)" -eq 0 \
    && test "$(find "$BUNDLE/lib/runtime" -maxdepth 1 -type f -name '*truffle-runtime-*' | wc -l)" -eq 1 \
    && javac -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
         -d /out/probe /tmp/Perf006dRuntimeProbe.java \
    && javac -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
         -d /out/driver /tmp/Perf006dCorrectnessDriver.java \
    && install -m 0755 /tmp/perf006d-run.sh /out/run

FROM ${GRAAL_BASE}
USER root
COPY --from=build /out/protos /opt/protos
COPY --from=build /out/corpus /opt/perf006d/corpus
COPY --from=build /out/probe /opt/perf006d/probe
COPY --from=build /out/driver /opt/perf006d/driver
COPY --from=build /out/runtime-fallback /opt/perf006d/runtime-fallback
COPY --from=build /out/run /opt/perf006d/run
ENV PROTOS_HOME=/opt/protos
WORKDIR /opt/protos
ENTRYPOINT ["/opt/perf006d/run"]
