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

# Expected toolchain identity declared by protos' own toolchain.json at PROTOS_REVISION. Defaults
# match the PERF004-B2-D/PERF006-D3 historical revision; PERF008-style builds pinning a newer
# revision override these explicitly so drift (e.g. a container OS-image bump) is caught here
# instead of silently producing evidence with an unverified toolchain identity.
ARG EXPECTED_GRAALVM_RELEASE=25.3.4.1
ARG EXPECTED_JDK_VERSION=25.0.4.1
ARG EXPECTED_CONTAINER_IMAGE=ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825
ARG EXPECTED_GRAAL_COMPONENTS_VERSION=25.3.4.1
ARG EXPECTED_MAVEN_VERSION=3.9.9

# The build environment's Python 3 package name is base-OS-dependent, not part of the
# protos/GraalVM toolchain identity: Oracle Linux 8's unversioned `python3` is a restricted
# platform-python, so it needs the versioned `python39` module package, while Oracle Linux 10
# removed versioned Python module packages and ships a sufficient `python3` (3.12) directly.
ARG PYTHON_PACKAGE=python39

COPY docker/protos-perf006d/Perf006dRuntimeProbe.java /tmp/Perf006dRuntimeProbe.java
COPY docker/protos-perf006d/Perf006dPersistentDriver.java /tmp/Perf006dPersistentDriver.java
COPY docker/protos-perf006d3/Perf008SteadyStateDriver.java /tmp/Perf008SteadyStateDriver.java
COPY docker/protos-perf006d3/Perf006d3JfrAnalyzer.java /tmp/Perf006d3JfrAnalyzer.java
COPY docker/protos-perf006d3/jfr-java /tmp/perf006d3-jfr-java

RUN microdnf install -y git gzip tar findutils ca-certificates ${PYTHON_PACKAGE} unzip \
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
    && javac --add-modules jdk.jfr -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
         -d /out/diagnostic /tmp/Perf008SteadyStateDriver.java \
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
