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

ARG BUILD_BASE=maven:3.9.9-eclipse-temurin-21
ARG GRAAL_BASE=ghcr.io/graalvm/jdk-community:22.0.0

FROM ${BUILD_BASE} AS build
ARG PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git
ARG PROTOS_REVISION
ARG TRUFFLE_RUNTIME_VERSION=24.0.0
ARG DIAGNOSTIC_VARIANT=control

RUN test -n "$PROTOS_REVISION"
RUN case "$DIAGNOSTIC_VARIANT" in control|immediate-preparation-unit-boundary) ;; *) exit 2 ;; esac
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

COPY truffle-runtime-pom.xml /tmp/truffle-runtime-pom.xml
COPY DiagnosticEval.java /tmp/DiagnosticEval.java
COPY RuntimeProbe.java /tmp/RuntimeProbe.java
COPY MeasurementDriver.java /tmp/MeasurementDriver.java
COPY apply_boundary.py /tmp/apply_boundary.py

RUN git init /src \
    && cd /src \
    && git remote add origin "$PROTOS_REPOSITORY" \
    && git fetch --depth 1 origin "$PROTOS_REVISION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$PROTOS_REVISION" \
    && if [ "$DIAGNOSTIC_VARIANT" = immediate-preparation-unit-boundary ]; then \
         python3 /tmp/apply_boundary.py /src; \
       fi \
    && mvn -q -DskipTests package \
    && mkdir -p /out \
    && JAR="$(find /src/target -maxdepth 1 -type f -name 'protos-*.jar' ! -name 'original-*' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$JAR" \
    && cp "$JAR" /out/protos.jar

RUN mkdir -p /out/truffle-runtime \
    && mvn -q -f /tmp/truffle-runtime-pom.xml \
       -Dtruffle.version="$TRUFFLE_RUNTIME_VERSION" \
       dependency:copy-dependencies -DincludeScope=runtime \
       -DoutputDirectory=/out/truffle-runtime

RUN mkdir -p /out/diag \
    && javac -cp '/out/protos.jar:/out/truffle-runtime/*' -d /out/diag \
       /tmp/DiagnosticEval.java /tmp/RuntimeProbe.java /tmp/MeasurementDriver.java

FROM ${GRAAL_BASE}
ARG DIAGNOSTIC_VARIANT=control
USER root
COPY --from=build /src /opt/protos
COPY --from=build /out/protos.jar /opt/protos/protos.jar
COPY --from=build /out/truffle-runtime /opt/truffle-runtime
COPY --from=build /out/diag /opt/diag
ENV PROTOS_HOME=/opt/protos
ENV PERF003A_DIAGNOSTIC_VARIANT=${DIAGNOSTIC_VARIANT}
WORKDIR /opt/protos
ENTRYPOINT ["java"]
