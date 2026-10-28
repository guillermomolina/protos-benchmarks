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

# Current/default BGV tooling aligned with GraalVM 25.4.4.1.1
# (oracle/graal tag vm-25.4.4.1.1). Historical Graal 24 tooling is isolated
# under docker/igv-analyzer24/.
#
# Building this image is a rare maintainer/publication operation. Normal BGV
# analysis pulls the published image and never clones, runs mx or compiles.

FROM ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10-20260922@sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5 AS builder

USER root

ARG GRAALVM_VERSION=25.4.4.1.1
ARG GRAAL_REV=95ce1499c8c96ab7d5a6697c5b4bf42160f3b68b
ARG MX_REV=22381992c7322f661498cd6101144f0f49c72ae1

RUN microdnf install -y \
        findutils \
        git \
        python3 \
        unzip \
        zip \
    && microdnf clean all

RUN git clone --filter=blob:none https://github.com/graalvm/mx.git /opt/mx \
    && git -C /opt/mx checkout --detach "${MX_REV}" \
    && test "$(git -C /opt/mx rev-parse HEAD)" = "${MX_REV}"

ENV PATH="/opt/mx:${PATH}"

RUN git clone --filter=blob:none https://github.com/oracle/graal.git /opt/graal \
    && git -C /opt/graal checkout --detach "${GRAAL_REV}" \
    && test "$(git -C /opt/graal rev-parse HEAD)" = "${GRAAL_REV}"

RUN java -version && mx --version

RUN mx \
    --primary-suite-path /opt/graal/compiler \
    build \
    --dependencies=GRAAL_IGVUTIL

RUN set -eux; \
    CP="$(mx --primary-suite-path /opt/graal/compiler classpath GRAAL_IGVUTIL)"; \
    mkdir -p /opt/igvutil/lib; \
    printf '%s\n' "$CP" >/opt/igvutil/classpath.source; \
    printf 'GRAALVM_VERSION=%s\nGRAAL_REV=%s\nMX_REV=%s\n' \
        "${GRAALVM_VERSION}" "${GRAAL_REV}" "${MX_REV}" >/opt/igvutil/IDENTITY; \
    OLDIFS="$IFS"; \
    IFS=':'; \
    for jar in $CP; do \
        test -f "$jar"; \
        cp "$jar" /opt/igvutil/lib/; \
    done; \
    IFS="$OLDIFS"; \
    test -f /opt/igvutil/lib/graal-igvutil.jar; \
    test -f /opt/igvutil/lib/graal.jar; \
    find /opt/igvutil/lib -maxdepth 1 -type f -name '*.jar' -printf '%f\n' | sort

# Real-parser self-test input: a repository-owned BGV fixture from the exact
# pinned Graal checkout. Fail closed if it is absent. It is not shipped.
RUN set -eux; \
    fixture="$(find /opt/graal -type f -name 'bigv-3.0.bgv' | sort | head -n 1)"; \
    test -n "$fixture"; \
    test -s "$fixture"; \
    mkdir -p /opt/igvutil-selftest; \
    cp "$fixture" /opt/igvutil-selftest/fixture.bgv; \
    printf '%s\n' "${fixture#/opt/graal/}" >/opt/igvutil-selftest/fixture.source

FROM eclipse-temurin:21.0.12_8-jre-jammy AS runtime-base

COPY --from=builder /opt/igvutil /opt/igvutil

RUN java -version \
    && if java --list-modules | grep -q '^jdk\.graal\.compiler@'; then \
         echo 'ERROR: neutral runtime unexpectedly contains jdk.graal.compiler'; \
         exit 1; \
       fi \
    && java -cp '/opt/igvutil/lib/*' org.graalvm.igvutil.IgvUtility --help >/tmp/igvutil-help.txt \
    && grep -q 'list' /tmp/igvutil-help.txt \
    && grep -q 'filter' /tmp/igvutil-help.txt \
    && grep -q 'flatten' /tmp/igvutil-help.txt \
    && rm -f /tmp/igvutil-help.txt

# Parse the upstream fixture with the shipped jars on the shipped runtime.
FROM runtime-base AS selftest

COPY --from=builder /opt/igvutil-selftest /selftest

RUN set -eux; \
    mkdir -p /selftest/out; \
    cd /selftest; \
    java -cp '/opt/igvutil/lib/*' org.graalvm.igvutil.IgvUtility list fixture.bgv >/selftest/out/list.txt; \
    test -s /selftest/out/list.txt; \
    java -cp '/opt/igvutil/lib/*' org.graalvm.igvutil.IgvUtility filter fixture.bgv >/selftest/out/filter.json; \
    test -s /selftest/out/filter.json; \
    cp /selftest/fixture.source /selftest/out/fixture.source

# Validate the self-test JSON where python3 is available.
FROM builder AS selftest-verify

COPY --from=selftest /selftest/out /selftest-out

RUN set -eux; \
    python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' /selftest-out/filter.json; \
    printf 'IGV_ANALYZER_BUILD_SELFTEST=PASS\nFIXTURE=%s\nFIXTURE_SHA256=%s\n' \
        "$(cat /selftest-out/fixture.source)" \
        "$(sha256sum /opt/igvutil-selftest/fixture.bgv | cut -d' ' -f1)" \
        >/selftest-out/SELFTEST

FROM runtime-base AS runtime

# Copying the marker makes the final image depend on a passing self-test.
COPY --from=selftest-verify /selftest-out/SELFTEST /opt/igvutil/SELFTEST

LABEL org.opencontainers.image.title="Protos IGV analyzer" \
      org.opencontainers.image.description="Pinned GraalVM 25.4.4.1.1 official igvutil headless BGV analyzer" \
      org.opencontainers.image.version="graal-25.4.4.1.1" \
      org.opencontainers.image.source="https://github.com/guillermomolina/protos-benchmarks"

WORKDIR /work

ENTRYPOINT ["java","-cp","/opt/igvutil/lib/*","org.graalvm.igvutil.IgvUtility"]
