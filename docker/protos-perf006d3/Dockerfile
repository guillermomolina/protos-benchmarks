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
COPY docker/protos-perf006d/Perf006dPersistentDriver.java /tmp/Perf006dPersistentDriver.java
COPY docker/protos-perf006d3/Perf006d3JfrAnalyzer.java /tmp/Perf006d3JfrAnalyzer.java
COPY docker/protos-perf006d3/jfr-java /tmp/perf006d3-jfr-java

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
print("PERF006D3_SOURCE_TOOLCHAIN=PASS")
PY

RUN cd /src \
    && python3 dist/build_portable.py \
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
    && javac --add-modules jdk.jfr -d /out/analyzer /tmp/Perf006d3JfrAnalyzer.java \
    && jfr configure \
         --input "$JAVA_HOME/lib/jfr/profile.jfc" \
         --output /out/jfr/perf006d3.jfc \
         'jdk.ExecutionSample#enabled=true' \
         'jdk.ExecutionSample#period=10ms' \
         'jdk.Deoptimization#enabled=true' \
         'jdk.Deoptimization#stackTrace=true' \
         '+jdk.graal.compiler.truffle.Deoptimization#enabled=true' \
    && test -s /out/jfr/perf006d3.jfc \
    && install -m 0755 /tmp/perf006d3-jfr-java /out/jfr-java

FROM ${GRAAL_BASE}
USER root
COPY --from=build /out/protos /opt/protos
COPY --from=build /out/source /opt/protos-source
COPY --from=build /out/corpus /opt/perf006d3/corpus
COPY --from=build /out/diagnostic /opt/perf006d3/diagnostic
COPY --from=build /out/analyzer /opt/perf006d3/analyzer
COPY --from=build /out/jfr/perf006d3.jfc /opt/perf006d3/perf006d3.jfc
COPY --from=build /out/jfr-java /opt/perf006d3/jfr-java
ENV PROTOS_HOME=/opt/protos
WORKDIR /opt/protos-source
