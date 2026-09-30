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
#
# PERF010-A / #691 current-25.4 hot-root lifecycle and compiled-shape discriminator image.
#
# This is an overlay, not a second product build: it is built FROM the exact DIST006-D image
# (docker/protos-dist006d/Dockerfile) that runner/dist006d_baseline.py builds for the pinned Protos
# revision, so the exact-revision checkout, the canonical GraalVM 25.4.4.1.1 toolchain, the Maven
# compatibility contract, the portable distribution build and the benchmark corpus are inherited
# unchanged and are never copied here. The historical PERF010-A image
# (docker/protos-perf010a/Dockerfile) uses an older toolchain contract and is deliberately not
# reused; only its source-identity instrument mechanism is.
#
# The Protos source tree is not modified. The overlay adds harness-local
# diagnostic classes only, compiled by the pinned GraalVM JDK of the base image against the built
# product's own jars, so compatibility is proven against the exact pinned JDK and not against any
# locally installed one:
#   - the historical Perf010aSourceIdentityInstrument, Provider and SmokeDriver, unchanged;
#   - the root-aware Perf010aHotRootIdentityInstrument and Provider;
#   - Perf010aHotRootDriver (diagnostic driver with objective phase markers).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
ARG PROTOS_REVISION
ARG EXPECTED_JDK_VERSION=25.0.4.1.1

COPY docker/protos-perf010a/Perf010aSourceIdentityInstrument.java /tmp/hot-root/Perf010aSourceIdentityInstrument.java
COPY docker/protos-perf010a/Perf010aSourceIdentityInstrumentProvider.java /tmp/hot-root/Perf010aSourceIdentityInstrumentProvider.java
COPY docker/protos-perf010a/Perf010aSourceIdentitySmokeDriver.java /tmp/hot-root/Perf010aSourceIdentitySmokeDriver.java
COPY docker/protos-perf010a-hot-root/Perf010aHotRootIdentityInstrument.java /tmp/hot-root/Perf010aHotRootIdentityInstrument.java
COPY docker/protos-perf010a-hot-root/Perf010aHotRootIdentityInstrumentProvider.java /tmp/hot-root/Perf010aHotRootIdentityInstrumentProvider.java
COPY docker/protos-perf010a-hot-root/Perf010aHotRootDriver.java /tmp/hot-root/Perf010aHotRootDriver.java
COPY docker/protos-perf010a-hot-root/META-INF /tmp/hot-root/META-INF

RUN test -x "$JAVA_HOME/bin/java" \
    && test -x "$JAVA_HOME/bin/javac" \
    && JAVA_PROPERTIES="$("$JAVA_HOME/bin/java" -XshowSettings:properties -version 2>&1)" \
    && printf '%s\n' "$JAVA_PROPERTIES" | grep -Fq "java.version = ${EXPECTED_JDK_VERSION}" \
    && printf '%s\n' "$JAVA_PROPERTIES" | grep -Fq "java.vm.vendor = GraalVM Community" \
    && JAVAC_FEATURE="${EXPECTED_JDK_VERSION%%.*}" \
    && "$JAVA_HOME/bin/javac" -version 2>&1 | grep -Eq "^javac ${JAVAC_FEATURE}([.]|$)" \
    && mkdir -p /opt/perf010a-hot-root/diagnostic/META-INF/services /opt/perf010a-hot-root/identity \
    && "$JAVA_HOME/bin/javac" -cp "/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*" \
         -d /opt/perf010a-hot-root/diagnostic \
         /tmp/hot-root/*.java \
    && cp /tmp/hot-root/META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider \
         /opt/perf010a-hot-root/diagnostic/META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider \
    && (cd /tmp/hot-root \
        && sha256sum *.java META-INF/services/com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider) \
         > /opt/perf010a-hot-root/identity/harness-sources.sha256 \
    && { \
         printf 'JAVA_HOME=%s\n' "$JAVA_HOME"; \
         "$JAVA_HOME/bin/java" -version 2>&1; \
         "$JAVA_HOME/bin/javac" -version 2>&1; \
       } > /opt/perf010a-hot-root/identity/overlay-build-identity.txt \
    && rm -rf /tmp/hot-root

LABEL org.protos-benchmarks.perf010a-hot-root.overlay="diagnostic-only"
LABEL org.protos-benchmarks.perf010a-hot-root.retained-evidence="diagnostic-not-timing"
LABEL org.opencontainers.image.revision="${PROTOS_REVISION}"
