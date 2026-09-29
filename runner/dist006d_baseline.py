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

"""DIST006-D post-adoption GraalVM 25.4 single-platform baseline harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import statistics
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/dist006d-baseline.json"
DOCKERFILE = ROOT / "docker/protos-dist006d/Dockerfile"
DRIVER_JAVA = ROOT / "docker/protos-dist006d/Dist006dDriver.java"
RUNTIME_PROBE_JAVA = ROOT / "docker/protos-dist006d/Dist006dRuntimeProbe.java"
MAKEFILE = ROOT / "Makefile"

EXPECTED_SLICE = "DIST006-D1"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_ENGINE_VERSION = "25.4.4.1.1"
EXPECTED_JDK_VERSION = "25.0.4.1.1"
EXPECTED_JVMCI = "25.4-b23"
MAVEN_MINIMUM_VERSION = "3.9.9"
MAVEN_SUPPORTED_MAJOR = 3
EXPECTED_CONTAINER_IMAGE = (
    "ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@"
    "sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5"
)
EXPECTED_WORKLOAD_IDS = (
    "micro/slot-read",
    "micro/closure-call",
    "micro/method-call",
    "runtime/monomorphic-dispatch",
)
EXPECTED_WORKLOAD_ROLES = {
    "micro/slot-read": "broad/control compiler movement",
    "micro/closure-call": "closure-call baseline",
    "micro/method-call": "guest method-call baseline",
    "runtime/monomorphic-dispatch": "selected-send/direct-call baseline",
}
CANONICAL_TOOLCHAIN_JSON: dict[str, Any] = {
    "schema": "protos-toolchain-v2",
    "java": {"bytecode_release": 21},
    "graalvm": {
        "distribution": "graalvm-community",
        "release": EXPECTED_ENGINE_VERSION,
        "jdk_feature": 25,
        "jdk_version": EXPECTED_JDK_VERSION,
        "container_channel": "25i4",
        "container_image": EXPECTED_CONTAINER_IMAGE,
    },
    "graal_components": {"version": EXPECTED_ENGINE_VERSION},
    "maven": {
        "minimum_version": MAVEN_MINIMUM_VERSION,
        "supported_major": MAVEN_SUPPORTED_MAJOR,
    },
    "policy": {
        "primary_runtime_alignment": "development-ci-distribution",
        "upgrade_mode": "explicit-validated-change",
        "floating_primary_runtime": False,
    },
}


def run(
    command: list[str], *, capture: bool = False, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )


def output(command: list[str]) -> str:
    completed = run(command, capture=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "command failed: "
            + " ".join(command)
            + "\nstdout:\n"
            + (completed.stdout or "")[-8000:]
            + "\nstderr:\n"
            + (completed.stderr or "")[-8000:]
        )
    return (completed.stdout or "").rstrip("\n")


def load(path: Path = CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_exact_sha(value: str | None, label: str) -> str:
    if value is None or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise RuntimeError(f"{label} must be exactly 40 lowercase hexadecimal characters")
    return value


STABLE_MAVEN_VERSION_RE = re.compile(
    r"(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)"
)


def parse_stable_maven_version(
    value: str,
) -> tuple[int, int, int]:
    match = STABLE_MAVEN_VERSION_RE.fullmatch(value)

    if match is None:
        raise RuntimeError(
            f"Maven version is not a stable x.y.z coordinate: {value!r}"
        )

    return tuple(int(part) for part in match.groups())


ANSI_ESCAPE_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
)


def extract_maven_runtime_version(identity: str) -> str:
    clean_identity = ANSI_ESCAPE_RE.sub("", identity)

    match = re.search(
        r"Apache Maven ([^\s]+)",
        clean_identity,
    )

    if match is None:
        raise RuntimeError("Maven identity missing")

    return validate_maven_runtime_version(
        match.group(1)
    )


def validate_maven_runtime_version(value: str) -> str:
    actual = parse_stable_maven_version(value)
    minimum = parse_stable_maven_version(
        MAVEN_MINIMUM_VERSION
    )

    if actual[0] != MAVEN_SUPPORTED_MAJOR:
        raise RuntimeError(
            "unsupported Maven major: "
            f"expected {MAVEN_SUPPORTED_MAJOR}, "
            f"observed {actual[0]}"
        )

    if minimum[0] != MAVEN_SUPPORTED_MAJOR:
        raise RuntimeError(
            "invalid internal Maven minimum/supported-major contract"
        )

    if actual < minimum:
        raise RuntimeError(
            "Maven version below minimum: "
            f"expected >= {MAVEN_MINIMUM_VERSION}, "
            f"observed {value}"
        )

    return value


def validate_toolchain_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if payload != CANONICAL_TOOLCHAIN_JSON:
        raise RuntimeError(
            "canonical DIST006-D toolchain mismatch: expected="
            + json.dumps(CANONICAL_TOOLCHAIN_JSON, sort_keys=True)
            + " observed="
            + json.dumps(payload, sort_keys=True)
        )
    return payload


def validate_config_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    if cfg.get("schema_version") != 1:
        raise RuntimeError("unsupported DIST006-D config schema")
    if cfg.get("dist_item") != "DIST006" or cfg.get("issue") != "guillermomolina/protos#733":
        raise RuntimeError("DIST006-D authority mismatch")
    if cfg.get("slice") != EXPECTED_SLICE:
        raise RuntimeError("DIST006-D slice mismatch")
    if cfg.get("single_platform_baseline") is not True:
        raise RuntimeError("DIST006-D must remain a single-platform baseline")
    if cfg.get("retained_performance_evidence_produced_by_smoke") is not False:
        raise RuntimeError("smoke must not produce retained evidence")

    protos = cfg.get("protos", {})
    if protos.get("repository") != "https://github.com/guillermomolina/protos.git":
        raise RuntimeError("unexpected Protos repository")
    if protos.get("revision") is not None:
        raise RuntimeError("DIST006-D must not hard-code a Protos revision")
    contract = protos.get("revision_input_contract", {})
    if contract.get("revision_format") != "exactly 40 lowercase hexadecimal characters":
        raise RuntimeError("exact Protos SHA input contract missing")
    if contract.get("floating_branch_forbidden") is not True:
        raise RuntimeError("floating Protos revision must be forbidden")

    toolchain_cfg = cfg.get("toolchain", {})
    toolchain_json = {
        "schema": toolchain_cfg.get("schema"),
        "java": toolchain_cfg.get("java"),
        "graalvm": toolchain_cfg.get("graalvm"),
        "graal_components": toolchain_cfg.get("graal_components"),
        "maven": toolchain_cfg.get("maven"),
        "policy": toolchain_cfg.get("policy"),
    }
    validate_toolchain_contract(toolchain_json)
    if toolchain_cfg.get("jvmci") != EXPECTED_JVMCI:
        raise RuntimeError("JVMCI identity mismatch")
    if toolchain_cfg.get("expected_runtime") != EXPECTED_RUNTIME:
        raise RuntimeError("optimizing runtime identity mismatch")

    if cfg.get("operation_count") != 10000:
        raise RuntimeError("DIST006-D operation_count drift")
    if cfg.get("warmup_iterations") != 120 or cfg.get("steady_iterations") != 100:
        raise RuntimeError("DIST006-D reference scale drift")
    if cfg.get("network") != "none":
        raise RuntimeError("DIST006-D must disable networking")
    if cfg.get("timing_recording_phase") != "steady_only_no_diagnostic_instrumentation":
        raise RuntimeError("DIST006-D timing phase drift")
    exclusions = set(cfg.get("clean_timing_exclusions", []))
    required_exclusions = {
        "JFR",
        "TraceCompilation",
        "TraceCompilationDetails",
        "TraceInlining",
        "IGV",
        "allocation profiling",
        "source instrumentation",
        "Test Tool diagnostics",
    }
    if exclusions != required_exclusions:
        raise RuntimeError("DIST006-D timing exclusions drift")

    workloads = cfg.get("workloads", [])
    if tuple(item.get("id") for item in workloads) != EXPECTED_WORKLOAD_IDS:
        raise RuntimeError("DIST006-D requires the exact four-workload set")
    if any(item.get("expected") != "42" for item in workloads):
        raise RuntimeError("all DIST006-D workload/control results must be 42")
    if {item["id"]: item.get("role") for item in workloads} != EXPECTED_WORKLOAD_ROLES:
        raise RuntimeError("DIST006-D workload roles drift")
    for item in workloads:
        if not item.get("source") or not item.get("replace") or item.get("with") != "sink = 42":
            raise RuntimeError("incomplete DIST006-D workload/control definition")

    smoke = cfg.get("smoke", {})
    if smoke.get("retained_performance_evidence") is not False:
        raise RuntimeError("smoke retained-evidence marker must be false")
    if smoke.get("timing_evidence") is not False or smoke.get("reference_evidence") is not False:
        raise RuntimeError("smoke must explicitly reject timing/reference evidence")

    reference = cfg.get("reference", {})
    if reference.get("requires_exact_protos_revision") is not True:
        raise RuntimeError("reference must require exact Protos revision")
    if reference.get("requires_exact_clean_published_harness_revision") is not True:
        raise RuntimeError("reference must require clean published harness identity")
    if reference.get("comparison_kind") != "single-platform-post-adoption-baseline":
        raise RuntimeError("reference comparison kind drift")
    if reference.get("paired_platform_formula") is not False:
        raise RuntimeError("UPSTREAM003 paired-platform formula must not be imported")

    return cfg


def validate_dockerfile_contract(docker_text: str) -> None:
    required_markers = {
        "canonical GraalVM base": (
            "ARG GRAAL_BASE=" + EXPECTED_CONTAINER_IMAGE
        ),
        "ordinary OL10 packages": (
            "microdnf install -y git gzip tar findutils "
            "ca-certificates python3 unzip"
        ),
        "Maven minimum build arg": (
            "ARG MAVEN_MINIMUM_VERSION="
            + MAVEN_MINIMUM_VERSION
        ),
        "Maven supported-major build arg": (
            "ARG MAVEN_SUPPORTED_MAJOR="
            + str(MAVEN_SUPPORTED_MAJOR)
        ),
        "CodeReady Builder Maven repository": (
            "--enablerepo=ol10_codeready_builder"
        ),
        "maven-unbound package": "maven-unbound",
        "JAVA_HOME-first PATH": (
            'ENV PATH="${JAVA_HOME}/bin:${PATH}"'
        ),
        "JAVA_HOME Java executable": (
            'test -x "$JAVA_HOME/bin/java"'
        ),
        "JAVA_HOME Javac executable": (
            'test -x "$JAVA_HOME/bin/javac"'
        ),
        "bare Java selection": (
            'test "$(command -v java)" = "$JAVA_HOME/bin/java"'
        ),
        "bare Javac selection": (
            'test "$(command -v javac)" = "$JAVA_HOME/bin/javac"'
        ),
        "Java version assertion": (
            'grep -Fq "java.version = ${EXPECTED_JDK_VERSION}"'
        ),
        "Java vendor assertion": (
            'grep -Fq "java.vm.vendor = GraalVM Community"'
        ),
        "Javac feature derivation": (
            'JAVAC_FEATURE="${EXPECTED_JDK_VERSION%%.*}"'
        ),
        "Javac version assertion": (
            'grep -Eq "^javac ${JAVAC_FEATURE}([.]|$)"'
        ),
        "range minimum assertion": (
            "if actual < minimum:"
        ),
        "range major assertion": (
            "if actual[0] != supported_major:"
        ),
        "Maven Java version assertion": (
            'grep -Fq "Java version: ${EXPECTED_JDK_VERSION}"'
        ),
        "Maven vendor assertion": (
            'grep -Fq "vendor: GraalVM Community"'
        ),
        "Maven JAVA_HOME runtime assertion": (
            'grep -Fq "runtime: ${JAVA_HOME}"'
        ),
        "redundant OpenJDK rejection": (
            '&& test -z "$(rpm -qa \'java-*-openjdk*\')"'
        ),
        "maven-unbound identity evidence": (
            "MAVEN_UNBOUND_RPM=%s"
        ),
        "redundant OpenJDK identity evidence": (
            "REDUNDANT_OPENJDK_RPM=NO"
        ),
        "explicit GraalVM Javac compilation": (
            '"$JAVA_HOME/bin/javac" -cp'
        ),
        "build Java command identity": (
            "printf 'JAVA_COMMAND=%s\\n' "
            '"$(command -v java)"'
        ),
        "build Javac command identity": (
            "printf 'JAVAC_COMMAND=%s\\n' "
            '"$(command -v javac)"'
        ),
        "portable distribution build": (
            "python3 dist/build_portable.py"
        ),
        "source toolchain gate": (
            "DIST006D_SOURCE_TOOLCHAIN_CONTRACT=PASS"
        ),
        "source current schema": (
            '"schema": "protos-toolchain-v2"'
        ),
        "source Maven minimum": (
            '"minimum_version": "3.9.9"'
        ),
        "source Maven supported major": (
            '"supported_major": 3'
        ),
        "benchmark corpus": "/opt/dist006d/corpus",
        "runtime classpath": "$BUNDLE/lib/runtime/*",
        "reference-only evidence label": (
            'LABEL org.protos-benchmarks.dist006d.'
            'retained-evidence="reference-only"'
        ),
    }

    for label, marker in required_markers.items():
        if marker not in docker_text:
            raise RuntimeError(
                "Dockerfile structural contract missing "
                f"{label}: {marker}"
            )

    if (
        docker_text.count(
            "--enablerepo=ol10_codeready_builder"
        )
        != 1
    ):
        raise RuntimeError(
            "CodeReady Builder must be scoped to exactly "
            "one Maven transaction"
        )

    repo_position = docker_text.index(
        "--enablerepo=ol10_codeready_builder"
    )

    transaction_start = docker_text.rfind(
        "RUN microdnf install -y",
        0,
        repo_position,
    )

    transaction_end = docker_text.find(
        "microdnf clean all",
        repo_position,
    )

    if transaction_start < 0 or transaction_end < 0:
        raise RuntimeError(
            "cannot identify scoped Maven provisioning transaction"
        )

    maven_transaction = docker_text[
        transaction_start:transaction_end
    ]

    for marker in (
        "--enablerepo=ol10_codeready_builder",
        "\n    maven \\",
        "\n    maven-unbound \\",
    ):
        if marker not in maven_transaction:
            raise RuntimeError(
                "incomplete scoped Maven provisioning "
                "transaction: "
                + marker
            )

    ordinary_position = docker_text.index(
        "microdnf install -y git gzip tar findutils "
        "ca-certificates python3 unzip"
    )

    if ordinary_position >= transaction_start:
        raise RuntimeError(
            "ordinary OS packages must be provisioned "
            "separately from Maven"
        )

    if "EXPECTED_MAVEN_VERSION" in docker_text:
        raise RuntimeError(
            "exact Maven patch assertion is forbidden "
            "by DIST008-B2"
        )

    for forbidden in (
        "ubuntu",
        "eclipse-temurin",
        "archive.apache.org",
        "apply_toolchain_overlay",
    ):
        if forbidden.lower() in docker_text.lower():
            raise RuntimeError(
                "forbidden DIST006-D Docker authority: "
                + forbidden
            )


def validate() -> dict[str, Any]:
    cfg = validate_config_payload(load())
    for path in (CONFIG, DOCKERFILE, DRIVER_JAVA, RUNTIME_PROBE_JAVA, MAKEFILE):
        if not path.is_file():
            raise RuntimeError(f"missing DIST006-D harness file: {path}")

    docker_text = DOCKERFILE.read_text(encoding="utf-8")
    validate_dockerfile_contract(docker_text)

    driver_text = DRIVER_JAVA.read_text(encoding="utf-8")
    if "import jdk.jfr" in driver_text:
        raise RuntimeError("DIST006-D timing driver must not import JFR")
    if 'mode.equals("correctness")' not in driver_text or 'mode.equals("timing")' not in driver_text:
        raise RuntimeError("DIST006-D driver must separate correctness from timing")

    makefile = MAKEFILE.read_text(encoding="utf-8")
    for target in ("dist006d-validate:", "dist006d-smoke:", "dist006d-reference:"):
        if target not in makefile:
            raise RuntimeError("missing Makefile target: " + target[:-1])

    print("DIST006D_D1_CONFIG=PASS")
    print("DIST006D_D1_TOOLCHAIN_CONTRACT=PASS")
    print("DIST006D_D1_WORKLOAD_SET=PASS")
    print("DIST006D_D1_DOCKER_STRUCTURE=PASS")
    print("DIST006D_D2_BUILD_TOOLCHAIN_SELECTION=PASS")
    print("DIST006D_D1_EXACT_SHA_POLICY=PASS")
    print("DIST006D_D1_HISTORICAL_UPSTREAM003_MUTATION=NO")
    print("DIST006D_D1_SMOKE_RETAINED_PERFORMANCE_EVIDENCE=NO")
    return cfg


def worktree_harness_state() -> dict[str, Any]:
    head = output(["git", "rev-parse", "HEAD"])
    dirty = output(["git", "status", "--porcelain", "--untracked-files=all"])
    return {
        "head": head,
        "clean": not bool(dirty),
        "identity": head if not dirty else "WORKTREE_PRECOMMIT",
    }


def exact_published_harness_revision(explicit: str | None) -> str:
    expected = require_exact_sha(explicit, "harness revision")
    head = output(["git", "rev-parse", "HEAD"])
    if head != expected:
        raise RuntimeError(f"exact harness revision mismatch: expected={expected} observed={head}")
    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("retained reference evidence requires a clean harness worktree")
    published = run(
        ["git", "merge-base", "--is-ancestor", head, "origin/main"],
        capture=True,
        check=False,
    )
    if published.returncode != 0:
        raise RuntimeError("retained reference evidence requires a harness revision published on origin/main")
    return head


def first_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return line.split(":", 1)[1].strip().split(",")[0].split("-")[0]
    raise RuntimeError("cannot determine current allowed CPU set")


def host_identity() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "kernel": platform.release(),
    }


def image_identity(ref: str) -> dict[str, Any]:
    payload = json.loads(output(["docker", "image", "inspect", ref]))[0]
    return {
        "selector": ref,
        "id": payload.get("Id", ""),
        "repo_digests": payload.get("RepoDigests") or [],
        "architecture": payload.get("Architecture", ""),
        "os": payload.get("Os", ""),
    }


def image_revision_label(tag: str) -> str:
    payload = json.loads(output(["docker", "image", "inspect", tag]))[0]
    labels = ((payload.get("Config") or {}).get("Labels")) or {}
    return labels.get("org.opencontainers.image.revision", "")


def docker_entrypoint(
    cpu: str, tag: str, entrypoint: str, *args: str, volume: tuple[Path, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpuset-cpus",
        cpu,
    ]
    if volume is not None:
        host, guest = volume
        command += ["--volume", f"{host.resolve()}:{guest}:ro"]
    command += ["--entrypoint", entrypoint, tag, *args]
    completed = run(command, capture=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"docker entrypoint failed: {entrypoint}\n"
            + (completed.stdout or "")[-4000:]
            + "\n"
            + (completed.stderr or "")[-4000:]
        )
    return completed


def image_text(tag: str, cpu: str, path: str) -> str:
    return docker_entrypoint(cpu, tag, "cat", path).stdout or ""


def image_json(tag: str, cpu: str, path: str) -> Any:
    return json.loads(image_text(tag, cpu, path))


def build_image(cfg: dict[str, Any], protos_revision: str) -> tuple[str, dict[str, Any]]:
    revision = require_exact_sha(protos_revision, "Protos revision")
    selector = cfg["toolchain"]["graalvm"]["container_image"]
    run(["docker", "pull", selector])
    base_identity = image_identity(selector)
    if not base_identity["id"] or not base_identity["repo_digests"]:
        raise RuntimeError("resolved canonical base image identity is incomplete")

    tag = f"protos-benchmarks-dist006d:{revision[:12]}"
    run(
        [
            "docker",
            "build",
            "--build-arg",
            "GRAAL_BASE=" + selector,
            "--build-arg",
            "PROTOS_REPOSITORY=" + cfg["protos"]["repository"],
            "--build-arg",
            "PROTOS_REVISION=" + revision,
            "--build-arg",
            "EXPECTED_GRAALVM_RELEASE=" + EXPECTED_ENGINE_VERSION,
            "--build-arg",
            "EXPECTED_JDK_VERSION=" + EXPECTED_JDK_VERSION,
            "--build-arg",
            "MAVEN_MINIMUM_VERSION=" + MAVEN_MINIMUM_VERSION,
            "--build-arg",
            "MAVEN_SUPPORTED_MAJOR=" + str(MAVEN_SUPPORTED_MAJOR),
            "--label",
            "org.opencontainers.image.revision=" + revision,
            "-t",
            tag,
            "-f",
            str(DOCKERFILE.relative_to(ROOT)),
            ".",
        ]
    )
    return tag, base_identity


def runtime_probe(tag: str, cpu: str) -> dict[str, str]:
    completed = docker_entrypoint(
        cpu,
        tag,
        "java",
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/dist006d/driver:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Dist006dRuntimeProbe",
    )
    result: dict[str, str] = {}
    for line in (completed.stdout or "").splitlines():
        if line.startswith("DIST006D_PROBE_") and "=" in line:
            key, value = line.split("=", 1)
            result[key.removeprefix("DIST006D_PROBE_").lower()] = value.strip()
    return result


def build_and_probe(cfg: dict[str, Any], protos_revision: str, cpu: str) -> dict[str, Any]:
    tag, base_identity = build_image(cfg, protos_revision)
    built_identity = image_identity(tag)
    if image_revision_label(tag) != protos_revision:
        raise RuntimeError("built image Protos revision label mismatch")

    observed_toolchain = image_json(tag, cpu, "/opt/dist006d/identity/toolchain.json")
    validate_toolchain_contract(observed_toolchain)

    runtime = runtime_probe(tag, cpu)
    if runtime.get("runtime_class") != EXPECTED_RUNTIME:
        raise RuntimeError(
            f"optimizing runtime mismatch: expected={EXPECTED_RUNTIME!r} "
            f"observed={runtime.get('runtime_class')!r}"
        )
    if runtime.get("engine_version") != EXPECTED_ENGINE_VERSION:
        raise RuntimeError(
            f"engine version mismatch: expected={EXPECTED_ENGINE_VERSION!r} "
            f"observed={runtime.get('engine_version')!r}"
        )
    if runtime.get("java_version") != EXPECTED_JDK_VERSION:
        raise RuntimeError(
            f"JDK version mismatch: expected={EXPECTED_JDK_VERSION!r} "
            f"observed={runtime.get('java_version')!r}"
        )

    build_identity = image_text(tag, cpu, "/opt/dist006d/identity/build-identity.txt")

    identity_fields: dict[str, str] = {}
    for line in build_identity.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"JAVA_HOME", "JAVA_COMMAND", "JAVAC_COMMAND"}:
            identity_fields[key] = value

    java_home = identity_fields.get("JAVA_HOME", "")
    if not java_home:
        raise RuntimeError("build-stage JAVA_HOME identity missing")
    if identity_fields.get("JAVA_COMMAND") != java_home + "/bin/java":
        raise RuntimeError("build-stage java does not resolve through JAVA_HOME")
    if identity_fields.get("JAVAC_COMMAND") != java_home + "/bin/javac":
        raise RuntimeError("build-stage javac does not resolve through JAVA_HOME")

    if f"java.version = {EXPECTED_JDK_VERSION}" not in build_identity:
        raise RuntimeError("build-stage Java version mismatch")
    if "java.vm.vendor = GraalVM Community" not in build_identity:
        raise RuntimeError("build-stage Java vendor mismatch")

    expected_javac_feature = EXPECTED_JDK_VERSION.split(".", 1)[0]
    if re.search(
        rf"(?m)^javac {re.escape(expected_javac_feature)}(?:[.]|$)",
        build_identity,
    ) is None:
        raise RuntimeError("build-stage Javac version mismatch")

    extract_maven_runtime_version(
        build_identity
    )

    if "MAVEN_UNBOUND_RPM=maven-unbound-" not in build_identity:
        raise RuntimeError(
            "maven-unbound provisioning identity missing"
        )

    if "REDUNDANT_OPENJDK_RPM=NO" not in build_identity:
        raise RuntimeError(
            "redundant OpenJDK RPM rejection evidence missing"
        )

    if f"Java version: {EXPECTED_JDK_VERSION}" not in build_identity:
        raise RuntimeError("Maven Java version mismatch")

    if "vendor: GraalVM Community" not in build_identity:
        raise RuntimeError("Maven Java vendor mismatch")

    if f"runtime: {java_home}" not in build_identity:
        raise RuntimeError(
            "Maven runtime does not match build-stage JAVA_HOME"
        )

    runtime_components = image_json(tag, cpu, "/opt/dist006d/identity/runtime-components.json")
    if EXPECTED_ENGINE_VERSION not in json.dumps(runtime_components, sort_keys=True):
        raise RuntimeError("bundled Graal/Truffle component identity mismatch")

    return {
        "tag": tag,
        "base_image_identity": base_identity,
        "built_image_identity": built_identity,
        "toolchain": observed_toolchain,
        "runtime": runtime,
        "build_identity": build_identity,
        "runtime_components": runtime_components,
    }


def control_source(tag: str, cpu: str, work: Path, item: dict[str, Any]) -> tuple[str, Path, str]:
    canonical = "/opt/dist006d/corpus/" + item["source"]
    source_text = image_text(tag, cpu, canonical)
    if source_text.count(item["replace"]) != 1:
        raise RuntimeError(
            f"expected exactly one control target in {item['id']}, found "
            f"{source_text.count(item['replace'])}"
        )
    control_text = source_text.replace(item["replace"], item["with"], 1)
    path = work / (item["id"].replace("/", "__") + "-control.protos")
    path.write_text(control_text, encoding="utf-8")
    return canonical, path, hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def driver_correctness(
    tag: str,
    cpu: str,
    source_container: str,
    expected: str,
    *,
    source_host: Path | None = None,
) -> dict[str, Any]:
    volume = (source_host, "/work/source.protos") if source_host is not None else None
    if source_host is not None:
        source_container = "/work/source.protos"
    completed = docker_entrypoint(
        cpu,
        tag,
        "java",
        "-Xss128m",
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/dist006d/driver:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Dist006dDriver",
        "correctness",
        source_container,
        expected,
        volume=volume,
    )
    payload = json.loads((completed.stdout or "").strip().splitlines()[-1])
    if payload.get("mode") != "correctness" or payload.get("observed") != expected:
        raise RuntimeError("DIST006-D correctness driver result mismatch")
    if payload.get("runtime") != EXPECTED_RUNTIME:
        raise RuntimeError("DIST006-D correctness driver runtime mismatch")
    if payload.get("timing_evidence") is not False:
        raise RuntimeError("DIST006-D correctness path must not emit timing evidence")
    return payload


def driver_timing(
    tag: str,
    cpu: str,
    source_container: str,
    expected: str,
    warmup: int,
    steady: int,
    *,
    source_host: Path | None = None,
) -> dict[str, Any]:
    volume = (source_host, "/work/source.protos") if source_host is not None else None
    if source_host is not None:
        source_container = "/work/source.protos"
    completed = docker_entrypoint(
        cpu,
        tag,
        "java",
        "-Xss128m",
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/dist006d/driver:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Dist006dDriver",
        "timing",
        source_container,
        expected,
        str(warmup),
        str(steady),
        volume=volume,
    )
    payload = json.loads((completed.stdout or "").strip().splitlines()[-1])
    if payload.get("mode") != "timing" or payload.get("runtime") != EXPECTED_RUNTIME:
        raise RuntimeError("DIST006-D timing driver identity mismatch")
    if len(payload.get("warmup_ns", [])) != warmup or len(payload.get("steady_ns", [])) != steady:
        raise RuntimeError("DIST006-D timing sample count mismatch")
    if payload.get("diagnostic_instrumentation_present") is not False:
        raise RuntimeError("DIST006-D timing must exclude diagnostic instrumentation")
    return payload


def summarize_ns(values: list[int]) -> dict[str, float | int]:
    if not values or any(not isinstance(value, int) or value <= 0 for value in values):
        raise ValueError("timing samples must be positive integers")
    ordered = sorted(values)
    median = statistics.median(ordered)
    deviations = [abs(value - median) for value in ordered]
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "samples": len(ordered),
        "median_ns": median,
        "mad_ns": statistics.median(deviations),
        "p95_ns": ordered[p95_index],
        "min_ns": ordered[0],
        "max_ns": ordered[-1],
    }


def smoke(protos_revision: str | None) -> None:
    cfg = validate()
    revision = require_exact_sha(protos_revision, "Protos revision")
    cpu = first_cpu()
    build = build_and_probe(cfg, revision, cpu)
    workload_identity: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="dist006d-smoke-") as tmp:
        work = Path(tmp)
        for item in cfg["workloads"]:
            canonical, control, source_sha = control_source(build["tag"], cpu, work, item)
            canonical_result = driver_correctness(
                build["tag"], cpu, canonical, item["expected"]
            )
            control_result = driver_correctness(
                build["tag"], cpu, "", item["expected"], source_host=control
            )
            workload_identity[item["id"]] = {
                "source_sha256": source_sha,
                "canonical_observed": canonical_result["observed"],
                "control_observed": control_result["observed"],
            }

    identity = {
        "protos_revision": revision,
        "harness": worktree_harness_state(),
        "container": build["built_image_identity"],
        "base_container": build["base_image_identity"],
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "network": "none",
        "toolchain": build["toolchain"],
        "runtime": build["runtime"],
        "workloads": workload_identity,
        "retained_performance_evidence": False,
        "timing_evidence": False,
        "reference_evidence": False,
    }
    print("DIST006D_SMOKE_IDENTITY=" + json.dumps(identity, sort_keys=True))
    print("DIST006D_SMOKE_CORRECTNESS=PASS")
    print("RETAINED_PERFORMANCE_EVIDENCE=NO")
    print("TIMING_EVIDENCE=NO")
    print("REFERENCE_EVIDENCE=NO")
    print("DIST006D_SMOKE=PASS")


def prepare_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise RuntimeError("output directory already contains evidence: " + str(path))
        path.rmdir()
    path.mkdir(parents=True)


def write_manifest(output_dir: Path) -> None:
    paths = [
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    rows = [
        f"{sha256(path)}  {path.relative_to(output_dir).as_posix()}" for path in sorted(paths)
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def reference(
    protos_revision: str | None,
    harness_revision: str | None,
    output_dir: Path | None,
) -> None:
    cfg = validate()
    revision = require_exact_sha(protos_revision, "Protos revision")
    harness = exact_published_harness_revision(harness_revision)
    out = output_dir or ROOT / cfg["reference"]["output"]
    if not out.is_absolute():
        out = ROOT / out
    prepare_output(out)

    cpu = first_cpu()
    build = build_and_probe(cfg, revision, cpu)
    raw_workloads: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="dist006d-reference-") as tmp:
        work = Path(tmp)
        for item in cfg["workloads"]:
            canonical, control, source_sha = control_source(build["tag"], cpu, work, item)
            canonical_result = driver_timing(
                build["tag"],
                cpu,
                canonical,
                item["expected"],
                cfg["warmup_iterations"],
                cfg["steady_iterations"],
            )
            control_result = driver_timing(
                build["tag"],
                cpu,
                "",
                item["expected"],
                cfg["warmup_iterations"],
                cfg["steady_iterations"],
                source_host=control,
            )
            raw_workloads.append(
                {
                    "id": item["id"],
                    "role": item["role"],
                    "source": item["source"],
                    "source_sha256": source_sha,
                    "expected": item["expected"],
                    "canonical": canonical_result,
                    "control": control_result,
                    "canonical_summary": summarize_ns(canonical_result["steady_ns"]),
                    "control_summary": summarize_ns(control_result["steady_ns"]),
                }
            )

    raw = {
        "schema_version": 1,
        "dist_item": "DIST006",
        "slice": EXPECTED_SLICE,
        "evidence_kind": "single-platform-post-adoption-baseline",
        "evidence_status": "RETAINED",
        "protos_revision": revision,
        "harness_revision": harness,
        "base_image_identity": build["base_image_identity"],
        "built_image_identity": build["built_image_identity"],
        "host_identity": host_identity(),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "network": "none",
        "toolchain": build["toolchain"],
        "jvmci_contract": EXPECTED_JVMCI,
        "runtime_identity": build["runtime"],
        "build_identity": build["build_identity"],
        "runtime_components": build["runtime_components"],
        "operation_count": cfg["operation_count"],
        "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"],
        "timing_recording_phase": cfg["timing_recording_phase"],
        "clean_timing_exclusions": cfg["clean_timing_exclusions"],
        "workloads": raw_workloads,
        "paired_platform_formula": False,
        "diagnostic_instrumentation_present": False,
    }
    (out / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    rows = ["workload\tmode\tsamples\tmedian_ns\tmad_ns\tp95_ns\tmin_ns\tmax_ns"]
    for item in raw_workloads:
        for mode in ("canonical", "control"):
            summary = item[mode + "_summary"]
            rows.append(
                "\t".join(
                    [
                        item["id"],
                        mode,
                        str(summary["samples"]),
                        str(summary["median_ns"]),
                        str(summary["mad_ns"]),
                        str(summary["p95_ns"]),
                        str(summary["min_ns"]),
                        str(summary["max_ns"]),
                    ]
                )
            )
    (out / "summary.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    readme = [
        "# DIST006-D canonical post-adoption 25.4 baseline",
        "",
        "Single-platform retained baseline for the canonical DIST006 GraalVM/Graal/Truffle 25.4.4.1.1 toolchain.",
        "",
        f"- Protos revision: `{revision}`",
        f"- Harness revision: `{harness}`",
        f"- Runtime: `{EXPECTED_RUNTIME}`",
        f"- Container selector: `{EXPECTED_CONTAINER_IMAGE}`",
        f"- CPU affinity: `--cpuset-cpus {cpu}`",
        "- Network: `none`",
        f"- Warmup iterations: `{cfg['warmup_iterations']}`",
        f"- Steady iterations: `{cfg['steady_iterations']}`",
        "- Timing contains no JFR, compiler tracing, IGV, allocation profiling, source instrumentation, or Test Tool diagnostics.",
        "- This is not a recreated 25.3-vs-25.4 comparison and contains no paired-platform formula.",
        "",
        "`raw.json` is authoritative; `summary.tsv` is a derived view.",
        "",
    ]
    (out / "README.md").write_text("\n".join(readme), encoding="utf-8")
    write_manifest(out)

    print("DIST006D_REFERENCE=PASS")
    print("DIST006D_REFERENCE_EVIDENCE_STATUS=RETAINED")
    print("DIST006D_REFERENCE_PROTOS_REVISION=" + revision)
    print("DIST006D_REFERENCE_HARNESS_REVISION=" + harness)
    print("DIST006D_REFERENCE_PLATFORM=25.4.4.1.1")
    print("DIST006D_REFERENCE_PAIRED_PLATFORM_FORMULA=NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "smoke", "reference"))
    parser.add_argument("--protos-revision")
    parser.add_argument("--harness-revision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if args.command == "validate":
        validate()
    elif args.command == "smoke":
        smoke(args.protos_revision)
    else:
        reference(
            args.protos_revision,
            args.harness_revision,
            Path(args.output_dir) if args.output_dir else None,
        )


if __name__ == "__main__":
    main()
