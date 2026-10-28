#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.


"""Metadata and timing statistics used by the current harness."""

from __future__ import annotations

import hashlib
import re
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"

STABILITY_WINDOW = 5
STABILITY_MEDIAN_DRIFT_PCT = 15.0
STABILITY_MAD_PCT = 20.0
STABILITY_MAX_INTERNAL_GAP_PCT = 20.0
STABILITY_MIN_GAP_CLUSTER_SIZE = 3


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
    pom = TRUFFLE / "pom.xml"
    root = ET.parse(pom).getroot()
    namespace = ""

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    properties = root.find(f"{namespace}properties")

    if properties is None:
        raise RuntimeError(
            "truffle/pom.xml has no properties"
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


def median_absolute_deviation(
    values: list[int],
) -> float:
    median = float(statistics.median(values))

    return float(
        statistics.median(
            [
                abs(value - median)
                for value in values
            ]
        )
    )


def internal_gap_check(
    samples: list[int],
) -> dict[str, object]:
    ordered = sorted(samples)
    count = len(ordered)

    candidates = []

    for index in range(count - 1):
        left_count = index + 1
        right_count = count - left_count

        if (
            left_count < STABILITY_MIN_GAP_CLUSTER_SIZE
            or right_count < STABILITY_MIN_GAP_CLUSTER_SIZE
        ):
            continue

        low = ordered[index]
        high = ordered[index + 1]
        gap = high - low

        candidates.append(
            (
                gap,
                low,
                high,
                left_count,
                right_count,
            )
        )

    if not candidates:
        return {
            "status": "NOT_STABLE",
            "reason": "insufficient-gap-cluster-samples",
        }

    gap, low, high, left_count, right_count = max(
        candidates
    )

    median = float(statistics.median(ordered))

    gap_pct = (
        float(gap)
        / median
        * 100.0
    )

    stable = (
        gap_pct
        <= STABILITY_MAX_INTERNAL_GAP_PCT
    )

    return {
        "status":
            "PASS" if stable else "NOT_STABLE",
        "largest_internal_gap_ns": gap,
        "largest_internal_gap_pct": gap_pct,
        "gap_low_ns": low,
        "gap_high_ns": high,
        "gap_left_count": left_count,
        "gap_right_count": right_count,
    }


def extreme_sample_check(
    samples: list[int],
) -> dict[str, object]:
    required = STABILITY_WINDOW * 2

    if not samples:
        return {
            "status": "NOT_STABLE",
            "reason": "empty-samples",
            "required_samples": required,
            "actual_samples": 0,
        }

    invalid = [
        {"index": index, "value_ns": value}
        for index, value in enumerate(samples)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not (0 < value < float("inf"))
        )
    ]

    if invalid:
        return {
            "status": "NOT_STABLE",
            "reason": "non-positive-or-invalid-samples",
            "required_samples": required,
            "actual_samples": len(samples),
            "invalid_samples": invalid,
        }

    if len(samples) < required:
        return {
            "status": "NOT_STABLE",
            "reason": "insufficient-samples",
            "required_samples": required,
            "actual_samples": len(samples),
        }

    median = float(statistics.median(samples))
    lower = median / 2.0
    upper = median * 2.0

    extremes = [
        {
            "index": index,
            "value_ns": value,
            "side": (
                "below-half-median"
                if value < lower
                else "above-double-median"
            ),
        }
        for index, value in enumerate(samples)
        if value < lower or value > upper
    ]

    result = {
        "status": "NOT_STABLE" if extremes else "PASS",
        "median_ns": median,
        "lower_bound_ns": lower,
        "upper_bound_ns": upper,
        "extreme_sample_count": len(extremes),
        "extreme_samples": extremes,
    }

    if extremes:
        result["reason"] = "extreme-samples"

    return result


def stability_window(
    samples: list[int],
) -> dict[str, object]:
    required = STABILITY_WINDOW * 2
    extremes = extreme_sample_check(samples[-required:])

    if len(samples) < required:
        return {
            "status": "NOT_STABLE",
            "reason": "insufficient-samples",
            "required_samples": required,
            "actual_samples": len(samples),
            "extreme_sample_check": extremes,
        }

    if "median_ns" not in extremes:
        return {
            "status": "NOT_STABLE",
            "reason": extremes["reason"],
            "extreme_sample_check": extremes,
        }

    previous = samples[
        -required:-STABILITY_WINDOW
    ]
    latest = samples[
        -STABILITY_WINDOW:
    ]

    previous_p50 = float(
        statistics.median(previous)
    )
    latest_p50 = float(
        statistics.median(latest)
    )

    drift_pct = (
        abs(latest_p50 - previous_p50)
        / previous_p50
        * 100.0
    )

    previous_mad_pct = (
        median_absolute_deviation(previous)
        / previous_p50
        * 100.0
    )

    latest_mad_pct = (
        median_absolute_deviation(latest)
        / latest_p50
        * 100.0
    )

    shape = internal_gap_check(
        samples[-required:]
    )

    stable = (
        drift_pct <= STABILITY_MEDIAN_DRIFT_PCT
        and previous_mad_pct <= STABILITY_MAD_PCT
        and latest_mad_pct <= STABILITY_MAD_PCT
        and shape["status"] == "PASS"
        and extremes["status"] == "PASS"
    )

    return {
        "status": "PASS" if stable else "NOT_STABLE",
        "previous_p50_ns": previous_p50,
        "latest_p50_ns": latest_p50,
        "median_drift_pct": drift_pct,
        "previous_mad_pct": previous_mad_pct,
        "latest_mad_pct": latest_mad_pct,
        "shape": shape,
        "extreme_sample_check": extremes,
    }


def reference_admission(
    warmup: list[int],
    steady: list[int],
) -> dict[str, object]:
    warmup_check = stability_window(warmup)
    steady_check = stability_window(steady)

    admitted = (
        warmup_check["status"] == "PASS"
        and steady_check["status"] == "PASS"
    )

    return {
        "status":
            "PASS" if admitted else "NOT_STABLE",
        "warmup": warmup_check,
        "steady": steady_check,
    }
