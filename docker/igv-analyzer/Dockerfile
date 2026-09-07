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

# IGV is diagnostic tooling, not a benchmark runtime image. Graal vm-24.0.0
# embeds a NetBeans 14 IGV build that still compiles Java 7 release targets;
# JDK 17 is intentionally isolated here because JDK 22 no longer supports
# javac --release 7.
FROM eclipse-temurin:17-jdk-jammy

ARG GRAAL_REV=78238a5ee6e4ae827059c70549e286ae730b7730
ARG MX_REV=d0d6d6cd2f70bb384dfba9f3f66f3dab21392ae4

LABEL org.opencontainers.image.title="Protos IGV analyzer" \
      org.opencontainers.image.description="Pinned Graal 24.0.0 IdealGraphVisualizer bgv2json diagnostic tool" \
      org.opencontainers.image.source="https://github.com/guillermomolina/protos-benchmarks"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ant \
       ca-certificates \
       git \
       python3 \
       unzip \
       zip \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/graalvm/mx.git /opt/mx \
    && git -C /opt/mx checkout --detach "${MX_REV}" \
    && test "$(git -C /opt/mx rev-parse HEAD)" = "${MX_REV}"

ENV PATH="/opt/mx:${PATH}"

RUN git clone https://github.com/oracle/graal.git /opt/graal \
    && git -C /opt/graal checkout --detach "${GRAAL_REV}" \
    && test "$(git -C /opt/graal rev-parse HEAD)" = "${GRAAL_REV}"

# Prove the compatibility assumption before doing the expensive IGV build.
RUN printf 'class Release7Probe {}\n' >/tmp/Release7Probe.java \
    && javac --release 7 /tmp/Release7Probe.java \
    && rm -f /tmp/Release7Probe.java /tmp/Release7Probe.class

RUN mx --version \
    && mx --primary-suite-path /opt/graal/visualizer \
       build --dependencies=IGV_JSONEXPORTER,IGV_DATA_SETTINGS

COPY docker/igv-analyzer/patch_json_exporter.py /tmp/patch_json_exporter.py
RUN python3 /tmp/patch_json_exporter.py \
    && rm -f /tmp/patch_json_exporter.py \
    && set -eux; \
       SRC=/opt/graal/visualizer/IdealGraphVisualizer/JSONExporter/src/org/graalvm/visualizer/JSONExporter.java; \
       DIST=/opt/graal/visualizer/IdealGraphVisualizer/dist/idealgraphvisualizer; \
       test -f "$SRC"; \
       test -d "$DIST"; \
       mkdir -p /opt/igv-jsonexporter/classes; \
       find "$DIST" -type f -name '*.jar' -print | sort > /opt/igv-jsonexporter/jars.txt; \
       test -s /opt/igv-jsonexporter/jars.txt; \
       CP="$(paste -sd: /opt/igv-jsonexporter/jars.txt)"; \
       javac -cp "$CP" -d /opt/igv-jsonexporter/classes "$SRC"; \
       test -f /opt/igv-jsonexporter/classes/org/graalvm/visualizer/JSONExporter.class; \
       printf '%s\n' "$CP" >/opt/igv-jsonexporter/classpath

COPY docker/igv-analyzer/CompactBGVSummary.java /tmp/CompactBGVSummary.java
RUN set -eux; \
    CP="$(cat /opt/igv-jsonexporter/classpath)"; \
    mkdir -p /opt/igv-compact/classes; \
    javac -cp "/opt/igv-jsonexporter/classes:${CP}" \
      -d /opt/igv-compact/classes \
      /tmp/CompactBGVSummary.java; \
    test -f /opt/igv-compact/classes/com/guillermomolina/protos/benchmarks/igv/CompactBGVSummary.class; \
    rm -f /tmp/CompactBGVSummary.java

COPY docker/igv-analyzer/bgv2json /usr/local/bin/bgv2json
COPY docker/igv-analyzer/bgv-summary /usr/local/bin/bgv-summary
RUN chmod 0755 /usr/local/bin/bgv2json /usr/local/bin/bgv-summary \
    && /usr/local/bin/bgv2json --help | grep -q 'mx igv-json'

WORKDIR /work

ENTRYPOINT ["/usr/local/bin/bgv2json"]
