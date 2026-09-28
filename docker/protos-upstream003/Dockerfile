# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
# THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
# "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE. IF A COPY OF THE
# LICENSE DOES NOT ACCOMPANY THIS FILE, A COPY OF THE LICENSE MAY ALSO BE
# OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

ARG GRAAL_BASE
FROM ${GRAAL_BASE} AS build

USER root

ARG PLATFORM_ROLE
ARG PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git
ARG PROTOS_REVISION
ARG EXPECTED_PLATFORM_VERSION
ARG EXPECTED_JDK_VERSION=25.0.4.1
ARG EXPECTED_MAVEN_VERSION=3.9.9
ARG PYTHON_PACKAGE=python3

COPY docker/protos-upstream003/apply_toolchain_overlay.py /tmp/apply_toolchain_overlay.py
COPY docker/protos-upstream003/Upstream003RuntimeProbe.java /tmp/Upstream003RuntimeProbe.java
COPY docker/protos-perf006d/Perf006dPersistentDriver.java /tmp/Perf006dPersistentDriver.java
COPY docker/protos-perf010a/Perf010aTimingDriver.java /tmp/Perf010aTimingDriver.java

RUN microdnf install -y git gzip tar findutils ca-certificates ${PYTHON_PACKAGE} unzip patch maven \
    && microdnf clean all \
    && mvn -version \
    && mvn -version | grep -q "Apache Maven ${EXPECTED_MAVEN_VERSION} " \
    && mvn -version | grep -q "GraalVM Community"

RUN test "$PLATFORM_ROLE" = "platform_a" -o "$PLATFORM_ROLE" = "platform_b" \
    && test -n "$PROTOS_REVISION" \
    && git init /src \
    && cd /src \
    && git remote add origin "$PROTOS_REPOSITORY" \
    && git fetch --depth 1 origin "$PROTOS_REVISION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$PROTOS_REVISION" \
    && test -z "$(git status --porcelain --untracked-files=all)" \
    && python3 - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path("/src/toolchain.json").read_text(encoding="utf-8"))
assert cfg["graalvm"]["distribution"] == "graalvm-community"
assert cfg["graalvm"]["release"] == "25.3.4.1"
assert cfg["graalvm"]["jdk_feature"] == 25
assert cfg["graalvm"]["jdk_version"] == "25.0.4.1"
assert cfg["graalvm"]["container_channel"] == "25i3"
assert cfg["graalvm"]["container_image"] == (
    "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825"
)
assert cfg["graal_components"]["version"] == "25.3.4.1"
assert cfg["maven"]["version"] == "3.9.9"

pom = Path("/src/pom.xml").read_text(encoding="utf-8")
assert pom.count("<version>0.3.106-SNAPSHOT</version>") >= 1
assert pom.count("<graalvm.version>25.3.4.1</graalvm.version>") == 1

portable = Path("/src/dist/build_portable.py").read_text(encoding="utf-8")
for marker in (
    'SUPPORTED_JAVA_VERSION = "25.0.4.1"',
    'SUPPORTED_GRAALVM_RELEASE = "25.3.4.1"',
    'EXPECTED_TRUFFLE_VERSION = "25.3.4.1"',
    'EXPECTED_OPTIMIZING_RUNTIME = "HotSpotTruffleRuntime"',
):
    assert marker in portable, marker

print("UPSTREAM003_PINNED_SOURCE_TOOLCHAIN_BASELINE=PASS")
PY

RUN cd /src \
    && if [ "$PLATFORM_ROLE" = "platform_b" ]; then \
         python3 /tmp/apply_toolchain_overlay.py; \
       else \
         echo "UPSTREAM003_B_TOOLCHAIN_OVERLAY=NOT_APPLIED_PLATFORM_A"; \
       fi \
    && PLATFORM_ROLE="$PLATFORM_ROLE" \
       PROTOS_REVISION="$PROTOS_REVISION" \
       EXPECTED_PLATFORM_VERSION="$EXPECTED_PLATFORM_VERSION" \
       EXPECTED_JDK_VERSION="$EXPECTED_JDK_VERSION" \
       EXPECTED_MAVEN_VERSION="$EXPECTED_MAVEN_VERSION" \
       python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

role = os.environ["PLATFORM_ROLE"]
revision = os.environ["PROTOS_REVISION"]
expected_platform = os.environ["EXPECTED_PLATFORM_VERSION"]
expected_jdk = os.environ["EXPECTED_JDK_VERSION"]
expected_maven = os.environ["EXPECTED_MAVEN_VERSION"]
authorized = ("dist/build_portable.py", "pom.xml", "toolchain.json")

head = subprocess.run(
    ["git", "rev-parse", "HEAD"], check=True, text=True, stdout=subprocess.PIPE
).stdout.strip()
assert head == revision

dirty = tuple(sorted(
    line for line in subprocess.run(
        ["git", "diff", "--name-only"], check=True, text=True, stdout=subprocess.PIPE
    ).stdout.splitlines() if line
))
status = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all"],
    check=True, text=True, stdout=subprocess.PIPE,
).stdout.splitlines()
tracked_dirty = tuple(sorted(line[3:] for line in status if len(line) >= 4))

if role == "platform_a":
    assert dirty == ()
    assert tracked_dirty == ()
else:
    assert dirty == authorized
    assert tracked_dirty == authorized

cfg = json.loads(Path("toolchain.json").read_text(encoding="utf-8"))
assert cfg["graalvm"]["release"] == expected_platform
assert cfg["graalvm"]["jdk_version"] == expected_jdk
assert cfg["graal_components"]["version"] == expected_platform
assert cfg["maven"]["version"] == expected_maven
if role == "platform_a":
    assert cfg["graalvm"]["container_channel"] == "25i3"
    assert cfg["graalvm"]["container_image"] == (
        "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825"
    )
else:
    assert cfg["graalvm"]["container_channel"] == "25i4"
    assert cfg["graalvm"]["container_image"] == "ghcr.io/graalvm/graalvm-community:25i4-ol10"

pom = Path("pom.xml").read_text(encoding="utf-8")
assert pom.count("<version>0.3.106-SNAPSHOT</version>") >= 1
assert pom.count(f"<graalvm.version>{expected_platform}</graalvm.version>") == 1

portable = Path("dist/build_portable.py").read_text(encoding="utf-8")
assert f'SUPPORTED_GRAALVM_RELEASE = "{expected_platform}"' in portable
assert f'EXPECTED_TRUFFLE_VERSION = "{expected_platform}"' in portable
assert 'SUPPORTED_JAVA_VERSION = "25.0.4.1"' in portable

def tree_digest(directory: str) -> tuple[str, int]:
    root = Path(directory)
    assert root.is_dir(), directory
    digest = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if path.is_symlink():
            payload = ("L\0" + os.readlink(path)).encode("utf-8")
        elif path.is_file():
            payload = b"F\0" + hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii")
        else:
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + payload + b"\n")
        count += 1
    return digest.hexdigest(), count

src_digest, src_files = tree_digest("src")
protos_digest, protos_files = tree_digest("protos")

overlay_text = subprocess.run(
    ["git", "diff", "--no-ext-diff", "--binary", "--", *authorized],
    check=True, text=True, stdout=subprocess.PIPE,
).stdout

out = Path("/tmp/upstream003-identity")
out.mkdir(parents=True, exist_ok=True)
(out / "dirty-paths.txt").write_text(
    "".join(path + "\n" for path in dirty), encoding="utf-8"
)
(out / "overlay.diff").write_text(overlay_text, encoding="utf-8")
(out / "source-identity.json").write_text(
    json.dumps(
        {
            "protos_revision": head,
            "platform_role": role,
            "dirty_paths": list(dirty),
            "authorized_overlay_paths": list(authorized),
            "src_content_sha256": src_digest,
            "src_file_count": src_files,
            "protos_content_sha256": protos_digest,
            "protos_file_count": protos_files,
            "overlay_diff_sha256": hashlib.sha256(overlay_text.encode("utf-8")).hexdigest(),
            "overlay_script_sha256": hashlib.sha256(
                Path("/tmp/apply_toolchain_overlay.py").read_bytes()
            ).hexdigest(),
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
print("UPSTREAM003_SOURCE_SCOPE_GATE=PASS")
PY

RUN cd /src \
    && if [ "$PLATFORM_ROLE" = "platform_b" ]; then \
         python3 dist/build_portable.py --allow-dirty; \
       else \
         python3 dist/build_portable.py; \
       fi \
    && BUNDLE="$(find target/distributions -maxdepth 1 -mindepth 1 -type d -name 'protos-*' | LC_ALL=C sort | tail -n 1)" \
    && test -n "$BUNDLE" \
    && test -f "$BUNDLE/lib/protos.jar" \
    && test -d "$BUNDLE/lib/runtime" \
    && mkdir -p /out/protos /out/source /out/corpus /out/diagnostic /out/upstream003 \
    && cp -a "$BUNDLE"/. /out/protos/ \
    && cp -a /src/. /out/source/ \
    && rm -rf /out/source/target \
    && cp -a /src/protos/benchmarks/. /out/corpus/ \
    && cp -a /tmp/upstream003-identity/. /out/upstream003/ \
    && javac -cp "$BUNDLE/lib/protos.jar:$BUNDLE/lib/runtime/*" \
         -d /out/diagnostic \
         /tmp/Perf006dPersistentDriver.java \
         /tmp/Perf010aTimingDriver.java \
         /tmp/Upstream003RuntimeProbe.java \
    && (java -version; mvn -version; uname -m) > /out/upstream003/build-identity.txt 2>&1 \
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
Path("/out/upstream003/runtime-components.json").write_text(
    json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

FROM ${GRAAL_BASE}
USER root

ARG PLATFORM_ROLE
ARG PROTOS_REVISION
ARG EXPECTED_PLATFORM_VERSION

COPY --from=build /out/protos /opt/protos
COPY --from=build /out/source /opt/protos-source
COPY --from=build /out/corpus /opt/upstream003/corpus
COPY --from=build /out/diagnostic /opt/upstream003/diagnostic
COPY --from=build /out/upstream003 /opt/upstream003/identity

LABEL org.opencontainers.image.revision="${PROTOS_REVISION}"
LABEL org.protos-benchmarks.upstream003.platform-role="${PLATFORM_ROLE}"
LABEL org.protos-benchmarks.upstream003.platform-version="${EXPECTED_PLATFORM_VERSION}"

ENV PROTOS_HOME=/opt/protos
WORKDIR /opt/protos-source
