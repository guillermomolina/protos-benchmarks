#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.


"""Metadata and timing statistics used by the current harness."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS_DIR = ROOT / "harness"

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()

    for item in sorted(
        item for item in path.rglob("*") if item.is_file()
    ):
        digest.update(str(item.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")

    return digest.hexdigest()


def project_properties(repo: Path) -> tuple[str, str]:
    pom = repo / "pom.xml"

    if not pom.is_file():
        raise RuntimeError(f"Protos pom.xml missing: {pom}")

    root = ET.parse(pom).getroot()
    namespace = ""

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    version = root.findtext(
        f"{namespace}version",
        "",
    ).strip()

    properties = root.find(f"{namespace}properties")
    graalvm_version = ""

    if properties is not None:
        graalvm_version = properties.findtext(
            f"{namespace}graalvm.version",
            "",
        ).strip()

    if not version:
        raise RuntimeError(
            f"cannot resolve Protos project version from {pom}"
        )

    return version, graalvm_version


def harness_graalvm_version() -> str:
    pom = HARNESS_DIR / "pom.xml"
    root = ET.parse(pom).getroot()
    namespace = ""

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    properties = root.find(f"{namespace}properties")

    if properties is None:
        raise RuntimeError(
            "harness/pom.xml has no properties"
        )

    version = properties.findtext(
        f"{namespace}graal.languages.version",
        "",
    ).strip()

    if not version:
        raise RuntimeError(
            "cannot resolve graal.languages.version"
        )

    return version


def peer_pom(version: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.guillermomolina</groupId>
  <artifactId>protos-benchmarks-peer-runtime</artifactId>
  <version>1.0-SNAPSHOT</version>
  <dependencies>
    <dependency>
      <groupId>org.graalvm.polyglot</groupId>
      <artifactId>polyglot</artifactId>
      <version>{version}</version>
    </dependency>
    <dependency>
      <groupId>org.graalvm.polyglot</groupId>
      <artifactId>js</artifactId>
      <version>{version}</version>
      <type>pom</type>
    </dependency>
    <dependency>
      <groupId>org.graalvm.polyglot</groupId>
      <artifactId>python</artifactId>
      <version>{version}</version>
      <type>pom</type>
    </dependency>
  </dependencies>
</project>
"""


def parse_cpu_list(value: str) -> set[int]:
    cpus: set[int] = set()

    for part in value.strip().split(","):
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            cpus.update(range(start, end + 1))
        elif part:
            cpus.add(int(part))

    return cpus


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass

    return "unknown"


def parse_output(
    output: str,
) -> dict[str, object] | None:
    setup_ns: int | None = None
    sample_calls = 1
    cold: list[int] = []
    warmup: list[int] = []
    steady: list[int] = []
    result_value: str | None = None

    sample_pattern = re.compile(
        r"^sample phase=(cold|warmup|steady) "
        r"iteration=\d+ elapsed_ns=(\d+)$"
    )

    for line in output.splitlines():
        if line.startswith("setup_ns="):
            setup_ns = int(
                line.split("=", 1)[1]
            )
            continue

        if line.startswith("sample_calls="):
            sample_calls = int(
                line.split("=", 1)[1]
            )
            continue

        match = sample_pattern.match(line)

        if match:
            phase = match.group(1)
            elapsed = int(match.group(2))

            if phase == "cold":
                cold.append(elapsed)
            elif phase == "warmup":
                warmup.append(elapsed)
            else:
                steady.append(elapsed)

            continue

        if line.startswith("result="):
            result_value = line.split("=", 1)[1]

    if (
        setup_ns is None
        or not cold
        or not steady
        or result_value is None
    ):
        print(output, end="")
        return None

    return {
        "setup_ns": setup_ns,
        "sample_calls": sample_calls,
        "cold_ns": cold[0],
        "warmup_ns": warmup,
        "steady_ns": steady,
        "result": result_value,
    }
