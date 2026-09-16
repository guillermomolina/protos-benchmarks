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

# Current/default BGV tooling aligned with Graal 25.3.4.1.
# Historical Graal 24 tooling is isolated under docker/igv-analyzer24/.

FROM ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825 AS builder

USER root

ARG GRAAL_REV=7b025988a922a73286d1326e1eddc1ca39d3f569
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

FROM eclipse-temurin:21.0.12_8-jre-jammy AS runtime

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

LABEL org.opencontainers.image.title="Protos IGV analyzer" \
      org.opencontainers.image.description="Pinned Graal 25.3.4.1 official igvutil BGV diagnostic tool" \
      org.opencontainers.image.source="https://github.com/guillermomolina/protos-benchmarks"

WORKDIR /work

ENTRYPOINT ["java","-cp","/opt/igvutil/lib/*","org.graalvm.igvutil.IgvUtility"]
