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

# The default is the exact runtime of the pinned PERF001-F corpus revision. The
# runner always overrides this ARG from that revision's toolchain.json.
ARG GRAAL_BASE=ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825
FROM ${GRAAL_BASE} AS build

USER root
ARG MAVEN_VERSION=3.9.9
ARG PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git
ARG PROTOS_REVISION
COPY docker/protos-perf001f/Perf001fPersistentDriver.java /tmp/Perf001fPersistentDriver.java
RUN test -n "$MAVEN_VERSION" && test -n "$PROTOS_REVISION"
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
    && python3 dist/build_portable.py \
    && ARCHIVE="$(find target/distributions -maxdepth 1 -type f -name 'protos-*-posix-jvm.zip' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$ARCHIVE" \
    && sh dist/smoke_optimizing_runtime.sh "$ARCHIVE" \
    && BUNDLE="$(find target/distributions -maxdepth 1 -mindepth 1 -type d -name 'protos-*' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$BUNDLE" \
    && mkdir -p /out/protos /out/corpus /out/probe \
    && cp -a "$BUNDLE"/. /out/protos/ \
    && cp -a protos/benchmarks/concurrency/. /out/corpus/ \
    && javac \
        -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
        -d /out/probe \
        dist/Dist001RuntimeProbe.java \
    && mkdir -p /out/driver \
    && javac \
        -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
        -d /out/driver \
        /tmp/Perf001fPersistentDriver.java

FROM ${GRAAL_BASE}
USER root
COPY --from=build /out/protos /opt/protos
COPY --from=build /out/corpus /opt/perf001f/corpus
COPY --from=build /out/probe /opt/perf001f/probe
COPY --from=build /out/driver /opt/perf001f/driver
ENV PROTOS_HOME=/opt/protos
WORKDIR /opt/protos
ENTRYPOINT ["/opt/protos/bin/protos"]
