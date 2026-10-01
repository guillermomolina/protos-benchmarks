#!/usr/bin/env python3
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

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from workload_catalog import cases_for_selection, expected_result

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
MAIN_CLASS = (
    "com.guillermomolina.protos.benchmarks.truffle."
    "TruffleJvmRunner"
)


def run_case(
    language: str,
    workload: str,
    source: Path,
) -> None:
    result = subprocess.run(
        [
            "mvn",
            "-q",
            "-f",
            str(TRUFFLE / "pom.xml"),
            "exec:java",
            f"-Dexec.mainClass={MAIN_CLASS}",
            (
                "-Dexec.args="
                f"correctness {language} {source}"
            ),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.returncode != 0:
        print(result.stdout, end="")
        raise RuntimeError(
            f"correctness failed for {language}/{workload}"
        )

    values = [
        line.strip()
        for line in result.stdout.splitlines()
        if re.fullmatch(r"-?\d+", line.strip())
    ]

    expected = expected_result(workload)
    actual = values[-1] if values else None

    if actual != expected:
        print(result.stdout, end="")
        raise RuntimeError(
            f"{language}/{workload}: expected "
            f"{expected}, got {actual!r}"
        )

    print(
        f"{language}/{workload}=PASS "
        f"result={actual}"
    )


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit(
            "usage: jvm_correctness.py [all|<workload>]"
        )

    selected = sys.argv[1] if len(sys.argv) == 2 else "all"

    try:
        cases = cases_for_selection(selected)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    for case in cases:
        run_case(*case)


if __name__ == "__main__":
    main()
