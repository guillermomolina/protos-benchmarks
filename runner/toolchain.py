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


STABLE_MAVEN_VERSION_RE = re.compile(
    r"(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)"
)


def _stable_maven_version(
    value: Any,
    label: str,
) -> tuple[str, tuple[int, int, int]]:
    text = str(value)
    match = STABLE_MAVEN_VERSION_RE.fullmatch(text)
    if match is None:
        raise RuntimeError(f"invalid stable {label}: {text!r}")
    return text, tuple(int(part) for part in match.groups())


def _runtime_identity(
    payload: dict[str, Any],
) -> tuple[int, str, str, str, dict[str, Any]]:
    java = payload.get("java", {})
    graal = payload.get("graalvm", {})
    components = payload.get("graal_components", {})
    policy = payload.get("policy", {})

    bytecode_release = java.get("bytecode_release")
    graal_release = str(graal.get("release", ""))
    jdk_version = str(graal.get("jdk_version", ""))
    image = str(graal.get("container_image", ""))

    if not isinstance(bytecode_release, int) or bytecode_release < 21:
        raise RuntimeError("invalid Protos bytecode release")

    if not graal_release or not jdk_version or not image:
        raise RuntimeError("incomplete GraalVM runtime identity")

    if str(components.get("version", "")) != graal_release:
        raise RuntimeError("Graal component/runtime version mismatch")

    if policy.get("floating_primary_runtime") is not False:
        raise RuntimeError(
            "floating primary Protos runtime is not allowed"
        )

    if image.endswith(":latest") or ":latest-" in image:
        raise RuntimeError("floating GraalVM image is not allowed")

    return bytecode_release, graal_release, jdk_version, image, graal


def validate_toolchain_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate the current canonical Protos toolchain contract."""

    if payload.get("schema") != "protos-toolchain-v2":
        raise RuntimeError("unsupported Protos toolchain schema")

    maven = payload.get("maven", {})
    if not isinstance(maven, dict):
        raise RuntimeError("invalid Maven compatibility contract")

    if "version" in maven:
        raise RuntimeError(
            "legacy exact Maven version is not current Protos identity"
        )

    minimum_text, minimum = _stable_maven_version(
        maven.get("minimum_version", ""),
        "Maven minimum_version",
    )

    supported_major = maven.get("supported_major")

    if type(supported_major) is not int:
        raise RuntimeError(
            "Maven supported_major must be an integer"
        )

    if supported_major != 3:
        raise RuntimeError(
            "unsupported Maven major in current Protos contract"
        )

    if minimum[0] != supported_major:
        raise RuntimeError(
            "Maven minimum_version major does not match supported_major"
        )

    (
        bytecode_release,
        graal_release,
        jdk_version,
        image,
        graal,
    ) = _runtime_identity(payload)

    components = payload["graal_components"]

    return {
        "schema": payload["schema"],
        "bytecode_release": bytecode_release,
        "maven_minimum_version": minimum_text,
        "maven_supported_major": supported_major,
        "graalvm_release": graal_release,
        "jdk_feature": graal.get("jdk_feature"),
        "jdk_version": jdk_version,
        "graal_components_version": str(components["version"]),
        "container_channel": str(
            graal.get("container_channel", "")
        ),
        "container_image": image,
    }


def validate_historical_toolchain_v1_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate a pinned historical Protos v1 toolchain."""

    if payload.get("schema") != "protos-toolchain-v1":
        raise RuntimeError(
            "unsupported historical Protos toolchain schema"
        )

    maven = payload.get("maven", {})

    if not isinstance(maven, dict):
        raise RuntimeError("invalid historical Maven identity")

    maven_version = str(maven.get("version", ""))

    if not re.fullmatch(
        r"[0-9]+(?:[.][0-9]+)+",
        maven_version,
    ):
        raise RuntimeError(
            "invalid pinned historical Maven version"
        )

    (
        bytecode_release,
        graal_release,
        jdk_version,
        image,
        graal,
    ) = _runtime_identity(payload)

    components = payload["graal_components"]

    return {
        "schema": payload["schema"],
        "bytecode_release": bytecode_release,
        "maven_version": maven_version,
        "graalvm_release": graal_release,
        "jdk_feature": graal.get("jdk_feature"),
        "jdk_version": jdk_version,
        "graal_components_version": str(components["version"]),
        "container_channel": str(
            graal.get("container_channel", "")
        ),
        "container_image": image,
    }


def _read_payload(source: Path) -> dict[str, Any]:
    path = source / "toolchain.json"

    if not path.is_file():
        raise RuntimeError(
            f"measured Protos revision has no toolchain.json: {path}"
        )

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_toolchain(source: Path) -> dict[str, Any]:
    return validate_toolchain_payload(_read_payload(source))


def read_historical_toolchain_v1(
    source: Path,
) -> dict[str, Any]:
    return validate_historical_toolchain_v1_payload(
        _read_payload(source)
    )
