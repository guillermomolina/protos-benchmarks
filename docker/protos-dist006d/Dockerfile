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

ARG GRAAL_BASE=ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5
FROM ${GRAAL_BASE} AS build

USER root
ARG PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git
ARG PROTOS_REVISION
ARG EXPECTED_GRAALVM_RELEASE=25.4.4.1.1
ARG EXPECTED_JDK_VERSION=25.0.4.1.1
ARG EXPECTED_MAVEN_VERSION=3.9.9

COPY docker/protos-dist006d/Dist006dRuntimeProbe.java /tmp/Dist006dRuntimeProbe.java
COPY docker/protos-dist006d/Dist006dDriver.java /tmp/Dist006dDriver.java

RUN microdnf install -y git gzip tar findutils ca-certificates python3 unzip maven \
    && microdnf clean all \
    && mvn -version \
    && mvn -version | grep -q "Apache Maven ${EXPECTED_MAVEN_VERSION} " \
    && mvn -version | grep -q "GraalVM Community"

RUN PROTOS_REVISION="$PROTOS_REVISION" python3 - <<'PY'
import os
import re

revision = os.environ["PROTOS_REVISION"]
if not re.fullmatch(r"[0-9a-f]{40}", revision):
    raise SystemExit("PROTOS_REVISION must be exactly 40 lowercase hexadecimal characters")
PY

RUN git init /src \
    && cd /src \
    && git remote add origin "$PROTOS_REPOSITORY" \
    && git fetch --depth 1 origin "$PROTOS_REVISION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$PROTOS_REVISION" \
    && test -z "$(git status --porcelain --untracked-files=all)"

RUN cd /src \
    && python3 - <<'PY'
import json
from pathlib import Path

expected = {
    "schema": "protos-toolchain-v1",
    "java": {"bytecode_release": 21},
    "graalvm": {
        "distribution": "graalvm-community",
        "release": "25.4.4.1.1",
        "jdk_feature": 25,
        "jdk_version": "25.0.4.1.1",
        "container_channel": "25i4",
        "container_image": (
            "ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@"
            "sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5"
        ),
    },
    "graal_components": {"version": "25.4.4.1.1"},
    "maven": {"version": "3.9.9"},
    "policy": {
        "primary_runtime_alignment": "development-ci-distribution",
        "upgrade_mode": "explicit-validated-change",
        "floating_primary_runtime": False,
    },
}
actual = json.loads(Path("toolchain.json").read_text(encoding="utf-8"))
if actual != expected:
    raise SystemExit(
        "DIST006-D toolchain mismatch\nexpected="
        + json.dumps(expected, sort_keys=True)
        + "\nactual="
        + json.dumps(actual, sort_keys=True)
    )
print("DIST006D_SOURCE_TOOLCHAIN_CONTRACT=PASS")
PY

RUN cd /src \
    && python3 dist/build_portable.py \
    && BUNDLE="$(find target/distributions -maxdepth 1 -mindepth 1 -type d -name 'protos-*' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$BUNDLE" \
    && test -f "$BUNDLE/lib/protos.jar" \
    && test -d "$BUNDLE/lib/runtime" \
    && test -d /src/protos/benchmarks \
    && mkdir -p /out/protos /out/source /out/corpus /out/dist006d/driver /out/dist006d/identity \
    && cp -a "$BUNDLE"/. /out/protos/ \
    && cp -a /src/. /out/source/ \
    && rm -rf /out/source/target \
    && cp -a /src/protos/benchmarks/. /out/corpus/ \
    && cp /src/toolchain.json /out/dist006d/identity/toolchain.json \
    && javac -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
         -d /out/dist006d/driver \
         /tmp/Dist006dRuntimeProbe.java \
         /tmp/Dist006dDriver.java \
    && (java -version; mvn -version; uname -m) > /out/dist006d/identity/build-identity.txt 2>&1 \
    && python3 - "$BUNDLE" <<'PY'
import json
import sys
import zipfile
from pathlib import Path

bundle = Path(sys.argv[1])
rows = []
for jar in sorted((bundle / "lib/runtime").glob("*.jar")):
    lower = jar.name.lower()
    if not any(token in lower for token in ("truffle", "polyglot", "graal")):
        continue
    manifest = ""
    try:
        with zipfile.ZipFile(jar) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile):
        pass
    rows.append({"jar": jar.name, "manifest": manifest})
Path("/out/dist006d/identity/runtime-components.json").write_text(
    json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

FROM ${GRAAL_BASE}
USER root
ARG PROTOS_REVISION

COPY --from=build /out/protos /opt/protos
COPY --from=build /out/source /opt/protos-source
COPY --from=build /out/corpus /opt/dist006d/corpus
COPY --from=build /out/dist006d /opt/dist006d

LABEL org.opencontainers.image.revision="${PROTOS_REVISION}"
LABEL org.protos-benchmarks.dist006d.toolchain="25.4.4.1.1"
LABEL org.protos-benchmarks.dist006d.retained-evidence="reference-only"

ENV PROTOS_HOME=/opt/protos
WORKDIR /opt/protos-source
