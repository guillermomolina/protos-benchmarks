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

"""PERF009-A repository baseline and critical-path attribution harness."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from runner.toolchain import read_toolchain


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf009a.json"
WORK = ROOT / ".work" / "perf009a"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def materialize_source(
    repository: str,
    revision: str,
    destination: Path,
) -> Path:
    if not SHA_RE.fullmatch(revision):
        raise RuntimeError(f"invalid Protos revision: {revision!r}")

    if destination.exists():
        shutil.rmtree(destination)

    destination.mkdir(parents=True)

    run(["git", "init", "."], cwd=destination)
    run(["git", "remote", "add", "origin", repository], cwd=destination)
    run(
        ["git", "fetch", "--depth", "1", "origin", revision],
        cwd=destination,
    )
    run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=destination)

    observed = run(
        ["git", "rev-parse", "HEAD"],
        cwd=destination,
    ).stdout.strip()

    if observed != revision:
        raise RuntimeError(
            f"materialized revision mismatch: expected {revision}, got {observed}"
        )

    return destination


def materialized_source_identity(
    repository: str,
    revision: str,
    destination: Path,
) -> dict[str, Any]:
    source = materialize_source(repository, revision, destination)

    return {
        "protos_repository": repository,
        "protos_revision": revision,
        "toolchain": read_toolchain(source),
    }


def parse_makefile_contract_text(text: str) -> dict[str, Any]:
    def scalar(name: str) -> str:
        match = re.search(rf"(?m)^{re.escape(name)}\s*\?=\s*(\S+)\s*$", text)
        if match is None:
            raise RuntimeError(f"missing Makefile default: {name}")
        return match.group(1)

    slow_match = re.search(r"(?m)^JAVA_SLOW_TEST_EXCLUDES\s*:=\s*(.+)$", text)
    if slow_match is None:
        raise RuntimeError("missing JAVA_SLOW_TEST_EXCLUDES")

    slow_classes: list[str] = []
    for item in slow_match.group(1).split(","):
        item = item.strip()
        match = re.fullmatch(r"\*\*/([^/,]+)\.java", item)
        if match is None:
            raise RuntimeError(f"unexpected slow-test exclude entry: {item!r}")
        slow_classes.append(match.group(1))

    serial_match = re.search(r"(?m)^JAVA_SERIAL_TEST\s*:=\s*(\S+)\s*$", text)
    if serial_match is None:
        raise RuntimeError("missing JAVA_SERIAL_TEST")

    if "test: test-java test-protos" not in text:
        raise RuntimeError("Makefile test target no longer composes Java + Protos")
    if 'bin/protos test --jobs $(PROTOS_TEST_JOBS)' not in text:
        raise RuntimeError("Makefile no longer invokes public Test Tool as expected")

    return {
        "java_test_jobs_default": int(scalar("JAVA_TEST_JOBS")),
        "protos_test_jobs_default": int(scalar("PROTOS_TEST_JOBS")),
        "slow_test_classes": slow_classes,
        "serial_test_class": serial_match.group(1),
        "test_target_order": ["test-java", "test-protos"],
        "protos_test_public_command": True,
    }


def parse_test_tool_phase_names_text(text: str) -> list[str]:
    start_marker = "phaseNames: Array("
    end_marker = "phaseNames.freeze()"

    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError("Test Tool phaseNames array start not found")

    start += len(start_marker)
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError("Test Tool phaseNames array end not found")

    body = text[start:end]
    names = re.findall(r'"([^"]+)"', body)

    if not names:
        raise RuntimeError("Test Tool phaseNames array is empty")

    return names

def measurement_plan(config: dict[str, Any]) -> dict[str, Any]:
    contract = config["a1_inventory_contract"]
    java_jobs = int(contract["ci_java_jobs"])
    protos_jobs = int(contract["ci_protos_jobs"])
    lanes = [
        {
            "id": "current-ci",
            "role": "CURRENT_OPERATIONAL_PATH_WITH_QUARANTINE",
            "command": ["make", "test", f"JAVA_TEST_JOBS={java_jobs}", f"PROTOS_TEST_JOBS={protos_jobs}"],
        },
        {
            "id": "java-current",
            "role": "CURRENT_JAVA_PATH_WITH_QUARANTINE",
            "command": ["make", "test-java", f"JAVA_TEST_JOBS={java_jobs}"],
        },
        {
            "id": "protos-current",
            "role": "CURRENT_PUBLIC_TEST_TOOL_PATH",
            "command": ["make", "test-protos", f"PROTOS_TEST_JOBS={protos_jobs}"],
        },
        {
            "id": "java-complete-reference",
            "role": "COMPLETE_JAVA_COVERAGE_REFERENCE_NOT_CURRENT_CI_TOPOLOGY",
            "command": ["mvn", "test"],
        },
    ]
    return {
        "minimum_repetitions": int(contract["minimum_repetitions"]),
        "lanes": lanes,
        "diagnostic_protos_jobs": [int(value) for value in contract["diagnostic_protos_jobs"]],
        "direct_protos_prepare_command": ["mvn", "package", "-DskipTests"],
        "direct_protos_command_template": ["bin/protos", "test", "--jobs", "<N>"],
    }


def build_inventory(source: Path, config: dict[str, Any]) -> dict[str, Any]:
    makefile = parse_makefile_contract_text((source / "Makefile").read_text(encoding="utf-8"))
    phase_names = parse_test_tool_phase_names_text(
        (source / "protos/tools/test/Main.protos").read_text(encoding="utf-8")
    )
    inventory = {
        "protos_repository": config["protos_repository"],
        "protos_revision": config["protos_revision"],
        "toolchain": read_toolchain(source),
        "makefile": makefile,
        "test_tool": {
            "phase_names": phase_names,
            "phase_count": len(phase_names),
            "outer_suite_order_is_sequential": True,
            "jobs_scope": "bounded case admission within each suite",
        },
        "measurement_plan": measurement_plan(config),
        "timing_claim": False,
    }
    validate_inventory(inventory, config)
    return inventory


def validate_inventory(inventory: dict[str, Any], config: dict[str, Any]) -> None:
    contract = config["a1_inventory_contract"]
    observed_slow = inventory["makefile"]["slow_test_classes"]
    expected_slow = contract["expected_java_slow_test_classes"]
    if observed_slow != expected_slow:
        raise RuntimeError(f"Java slow-test quarantine mismatch: expected {expected_slow!r}, got {observed_slow!r}")

    observed_serial = inventory["makefile"]["serial_test_class"]
    expected_serial = contract["expected_java_serial_test"]
    if observed_serial != expected_serial:
        raise RuntimeError(f"Java serial-test mismatch: expected {expected_serial!r}, got {observed_serial!r}")

    observed_phases = inventory["test_tool"]["phase_names"]
    expected_phases = contract["expected_test_tool_phases"]
    if observed_phases != expected_phases:
        raise RuntimeError(f"Test Tool phase order mismatch: expected {expected_phases!r}, got {observed_phases!r}")


def materialize_inventory(destination: Path) -> dict[str, Any]:
    config = load_config()
    source = materialize_source(config["protos_repository"], config["protos_revision"], destination)
    return build_inventory(source, config)
