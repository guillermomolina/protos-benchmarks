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
RUN test -n "$PROTOS_REVISION"
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git init /src \
    && cd /src \
    && git remote add origin "$PROTOS_REPOSITORY" \
    && git fetch --depth 1 origin "$PROTOS_REVISION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$PROTOS_REVISION" \
    && mvn -q -DskipTests package \
    && mkdir -p /out \
    && JAR="$(find /src/target -maxdepth 1 -type f -name 'protos-*.jar' ! -name 'original-*' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$JAR" \
    && cp "$JAR" /out/protos.jar

FROM ${GRAAL_BASE}
USER root
COPY --from=build /src /opt/protos
COPY --from=build /out/protos.jar /opt/protos/protos.jar
ENV PROTOS_HOME=/opt/protos
WORKDIR /opt/protos
ENTRYPOINT ["java", "-Xss64m", "--enable-native-access=ALL-UNNAMED", "-jar", "/opt/protos/protos.jar"]
