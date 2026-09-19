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

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time


def last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def load_run(path: str):
    source = Path(path)
    spec = importlib.util.spec_from_file_location(
        "perf004a_workload_" + source.as_posix().replace("/", "_").replace("-", "_"),
        source,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import workload: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise RuntimeError(f"workload has no callable run(): {source}")
    return run


def startup(path: str, expected: str, samples: int) -> None:
    if samples <= 0:
        raise ValueError("samples must be positive")
    values: list[int] = []
    for index in range(samples):
        print(
            f"STARTUP_SAMPLE_BEGIN index={index + 1}/{samples}",
            file=sys.stderr,
            flush=True,
        )
        started = time.perf_counter_ns()
        completed = subprocess.run(
            [sys.executable, path],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
        elapsed = time.perf_counter_ns() - started
        actual = last_nonempty_line(completed.stdout or "")
        if completed.returncode != 0 or actual != expected:
            raise RuntimeError(
                f"startup failed rc={completed.returncode} "
                f"expected={expected!r} actual={actual!r} "
                f"stderr={(completed.stderr or '')[-4000:]!r}"
            )
        if elapsed <= 0:
            raise RuntimeError("non-positive startup sample")
        values.append(elapsed)
        print(
            f"STARTUP_SAMPLE_PASS index={index + 1}/{samples} elapsed_ns={elapsed}",
            file=sys.stderr,
            flush=True,
        )
    print(
        json.dumps(
            {
                "schema_version": 1,
                "runtime": "python",
                "expected": expected,
                "fresh_process_per_sample": True,
                "docker_start_outside_timing": True,
                "startup_ns": values,
            },
            separators=(",", ":"),
        )
    )


def execution(path: str, expected: str, warmup: int, steady: int) -> None:
    if warmup < 0 or steady < 0:
        raise ValueError("iteration counts must be non-negative")
    run = load_run(path)
    warmup_ns: list[int] = []
    steady_ns: list[int] = []
    for phase, count, target in (
        ("warmup", warmup, warmup_ns),
        ("steady", steady, steady_ns),
    ):
        for index in range(count):
            started = time.perf_counter_ns()
            result = run()
            elapsed = time.perf_counter_ns() - started
            actual = str(result)
            if actual != expected:
                raise RuntimeError(
                    f"{phase}[{index}] result mismatch "
                    f"expected={expected!r} actual={actual!r}"
                )
            if elapsed <= 0:
                raise RuntimeError(f"non-positive {phase} sample")
            target.append(elapsed)
    print(
        json.dumps(
            {
                "schema_version": 1,
                "runtime": "python",
                "expected": expected,
                "module_reused": True,
                "run_binding_reused": True,
                "warmup_ns": warmup_ns,
                "steady_ns": steady_ns,
            },
            separators=(",", ":"),
        )
    )


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: timing_driver.py startup|execution ...")
    mode = sys.argv[1]
    if mode == "startup" and len(sys.argv) == 5:
        startup(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return 0
    if mode == "execution" and len(sys.argv) == 6:
        execution(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
        return 0
    raise SystemExit("invalid arguments")


if __name__ == "__main__":
    raise SystemExit(main())
