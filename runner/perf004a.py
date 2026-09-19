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

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf004a.json"

EXPECTED_PROTOS_REVISION = "4a03efc15620b37b2e418b3df30b4a26486446ec"
EXPECTED_EQUIVALENCE_REVISION = "42b8264a36254dafbd97d80f5181790e28b9de12"
EXPECTED_IDS = (
    "micro/slot-read",
    "micro/slot-write",
    "micro/closure-call",
    "micro/method-call",
    "micro/object-creation",
    "micro/delegation-shallow",
    "micro/delegation-deep",
    "runtime/monomorphic-dispatch",
    "runtime/polymorphic-dispatch",
    "algorithms/factorial/recursive",
    "algorithms/fibonacci/recursive",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_python_run(path: Path):
    spec = importlib.util.spec_from_file_location(
        "perf004a_" + path.as_posix().replace("/", "_").replace("-", "_"),
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        spec.loader.exec_module(module)
    if captured.getvalue():
        raise RuntimeError(f"import printed output: {path}")
    run = getattr(module, "run", None)
    if not callable(run):
        raise RuntimeError(f"workload has no callable run(): {path}")
    return run


def validate() -> dict[str, Any]:
    cfg = load_json(CONFIG)
    if cfg.get("schema_version") != 1:
        raise RuntimeError("unsupported PERF004-A config schema")
    if cfg.get("perf_item") != "PERF004" or cfg.get("slice") != "PERF004-A1":
        raise RuntimeError("PERF004-A identity drift")
    if cfg.get("phase") != "callable-cross-language-corpus-preparation":
        raise RuntimeError("PERF004-A1 phase drift")
    if cfg.get("timing_claim") is not False:
        raise RuntimeError("PERF004-A1 must not publish a timing claim")
    if cfg.get("protos_revision") != EXPECTED_PROTOS_REVISION:
        raise RuntimeError("PERF004-A1 Protos revision drift")
    if cfg.get("equivalence_source_revision") != EXPECTED_EQUIVALENCE_REVISION:
        raise RuntimeError("PERF004-A1 equivalence-source revision drift")
    if cfg.get("comparison_languages") != ["protos", "python", "javascript"]:
        raise RuntimeError("PERF004-A1 language set drift")

    contract = cfg.get("measurement_contract", {})
    expected_contract = {
        "startup_process_samples_per_language_workload": 10,
        "persistent_forks_per_language_workload": 5,
        "warmup_iterations_per_fork": 20,
        "steady_samples_per_fork": 20,
        "primary_statistic": "median",
        "dispersion": ["mad", "min", "max", "p95"],
        "correctness_before_timing": True,
        "heavy_diagnostics_separate": True,
    }
    if contract != expected_contract:
        raise RuntimeError("PERF004-A1 measurement contract drift")

    suite = load_json(ROOT / "config" / "suite.json")
    entries = suite.get("benchmarks")
    if not isinstance(entries, list):
        raise RuntimeError("suite benchmark manifest is not a list")
    observed_ids = tuple(str(entry.get("id")) for entry in entries)
    if observed_ids != EXPECTED_IDS:
        raise RuntimeError(f"cross-language corpus identity drift: {observed_ids!r}")
    if suite.get("classification") != "algorithm-equivalent":
        raise RuntimeError("cross-language suite must remain algorithm-equivalent")
    if suite.get("protos_corpus_revision") != EXPECTED_EQUIVALENCE_REVISION:
        raise RuntimeError("suite equivalence revision drift")

    configured_ids = tuple(str(entry.get("id")) for entry in cfg.get("workloads", []))
    if configured_ids != EXPECTED_IDS:
        raise RuntimeError("PERF004-A1 workload list drift")

    validated = 0
    for entry in entries:
        benchmark_id = str(entry["id"])
        expected = str(entry["expected_stdout"])
        implementations = entry.get("implementations", {})

        python_path = ROOT / "workloads" / "python" / str(implementations["python"])
        run = load_python_run(python_path)
        observed = str(run())
        if observed != expected:
            raise RuntimeError(
                f"Python callable mismatch {benchmark_id}: expected={expected} observed={observed}"
            )

        javascript_path = (
            ROOT / "workloads" / "javascript" / str(implementations["javascript"])
        )
        javascript = javascript_path.read_text(encoding="utf-8")
        if "export function run()" not in javascript:
            raise RuntimeError(f"JavaScript workload has no exported run(): {javascript_path}")
        if "console.log(run())" not in javascript:
            raise RuntimeError(f"JavaScript workload lacks direct-execution result: {javascript_path}")
        if javascript.count("console.log(") != 1:
            raise RuntimeError(f"JavaScript workload has unexpected console output: {javascript_path}")

        validated += 1

    print("PERF004A1_CONFIG=PASS")
    print("PERF004A1_ALGORITHM_EQUIVALENT_CORPUS=PASS")
    print(f"PERF004A1_CALLABLE_WORKLOADS=PASS {validated}/{validated}")
    print("PERF004A1_PROTOS_MODIFICATION=NONE")
    print("PERF004A1_TIMING_CLAIM=NO")
    return cfg


def main() -> int:
    validate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
