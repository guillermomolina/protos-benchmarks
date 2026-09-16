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

"""Canonical Protos toolchain resolution for benchmark harnesses."""

import json
from pathlib import Path
import re
from typing import Any


def validate_toolchain_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "protos-toolchain-v1":
        raise RuntimeError("unsupported Protos toolchain schema")

    java = payload.get("java", {})
    graal = payload.get("graalvm", {})
    components = payload.get("graal_components", {})
    maven = payload.get("maven", {})
    policy = payload.get("policy", {})

    bytecode_release = java.get("bytecode_release")
    maven_version = str(maven.get("version", ""))
    graal_release = str(graal.get("release", ""))
    jdk_version = str(graal.get("jdk_version", ""))
    image = str(graal.get("container_image", ""))

    if not isinstance(bytecode_release, int) or bytecode_release < 21:
        raise RuntimeError("invalid Protos bytecode release")

    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", maven_version):
        raise RuntimeError("invalid pinned Maven version")

    if not graal_release or not jdk_version or not image:
        raise RuntimeError("incomplete GraalVM runtime identity")

    if str(components.get("version", "")) != graal_release:
        raise RuntimeError("Graal component/runtime version mismatch")

    if policy.get("floating_primary_runtime") is not False:
        raise RuntimeError("floating primary Protos runtime is not allowed")

    if image.endswith(":latest") or ":latest-" in image:
        raise RuntimeError("floating GraalVM image is not allowed")

    return {
        "schema": payload["schema"],
        "bytecode_release": bytecode_release,
        "maven_version": maven_version,
        "graalvm_release": graal_release,
        "jdk_feature": graal.get("jdk_feature"),
        "jdk_version": jdk_version,
        "graal_components_version": str(components["version"]),
        "container_channel": str(graal.get("container_channel", "")),
        "container_image": image,
    }


def read_toolchain(source: Path) -> dict[str, Any]:
    path = source / "toolchain.json"
    if not path.is_file():
        raise RuntimeError(
            f"measured Protos revision has no toolchain.json: {path}"
        )

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return validate_toolchain_payload(payload)
