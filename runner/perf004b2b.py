# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
# THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
# "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf004b2b.json"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"

spec = importlib.util.spec_from_file_location(
    "perf004b",
    ROOT / "runner/perf004b.py",
)
assert spec is not None and spec.loader is not None
perf004b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf004b)


def load():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def validate():
    cfg = load()

    assert cfg["slice"] == "PERF004-B2-B"
    assert cfg["protos_revision"] == "4a03efc15620b37b2e418b3df30b4a26486446ec"
    assert cfg["baseline_evidence_revision"] == "5e8ff21f966c6c506652eef79c684d8b286bb546"
    assert cfg["b1_evidence_revision"] == "d73a982be26a6661d934727035afad0f459c3c26"
    assert cfg["b2a_evidence_revision"] == "8d8e1c6cce843d0d64c9e0b740ba13df04b3effb"

    assert cfg["workload_operation_count"] == 10000
    assert cfg["warmup_iterations"] == 20
    assert cfg["steady_iterations"] == 100
    assert cfg["execution_sample_period"] == "10 ms"

    expected = {
        "micro/slot-read",
        "micro/closure-call",
        "micro/method-call",
        "runtime/monomorphic-dispatch",
    }

    assert {item[0] for item in cfg["workloads"]} == expected
    assert all(item[2] == "42" for item in cfg["workloads"])

    for evidence in (
        "results/perf004-a/SHA256SUMS",
        "results/perf004-b1/SHA256SUMS",
        "results/perf004-b2a/SHA256SUMS",
    ):
        if not (ROOT / evidence).is_file():
            raise RuntimeError(f"missing evidence: {evidence}")

    perf004b.validate()

    print("PERF004B2B_CONFIG=PASS")
    print("PERF004B2B_BASELINE_EVIDENCE=PASS")
    print("PERF004B2B_B1_EVIDENCE=PASS")
    print("PERF004B2B_B2A_EVIDENCE=PASS")
    print("PERF004B2B_PROTOS_MODIFICATION=NONE")
    print("PERF004B2B_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B2B_WORKLOADS=4")

    return cfg


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(output_dir, harness_revision):
    cfg = validate()

    head = perf004b.output(["git", "rev-parse", "HEAD"])
    if head != harness_revision:
        raise RuntimeError(
            f"exact harness required: HEAD={head} expected={harness_revision}"
        )

    if perf004b.output(
        ["git", "status", "--porcelain", "--untracked-files=all"]
    ):
        raise RuntimeError("B2-B reference requires a clean exact harness")

    if output_dir.exists():
        if not output_dir.is_dir():
            raise RuntimeError("output path exists and is not a directory")
        if any(output_dir.iterdir()):
            raise RuntimeError(
                "output directory already contains evidence: "
                + str(output_dir)
            )
        output_dir.rmdir()

    base_cfg = perf004b.load()
    tag = perf004b.build_image(base_cfg)
    cpu = perf004b.first_cpu()

    runtime = perf004b.runtime_probe(base_cfg, tag, cpu)
    if runtime != EXPECTED_RUNTIME:
        raise RuntimeError(f"runtime mismatch: {runtime}")

    profiles = []

    with tempfile.TemporaryDirectory(prefix="perf004-b2b-") as tmp:
        work = Path(tmp)

        for workload, source, expected in cfg["workloads"]:
            item = {
                "id": workload,
                "source": source,
                "expected": expected,
            }

            print(
                f"PROFILE BEGIN workload={workload} operations=10000",
                flush=True,
            )

            payload = perf004b.profile_one(
                base_cfg,
                tag,
                cpu,
                "protos",
                item,
            )

            # profile_one() already uses the canonical D3 profiler contract.
            payload["workload"] = workload
            payload["expected"] = expected
            payload["operation_count"] = cfg["workload_operation_count"]
            payload["warmup_iterations"] = cfg["warmup_iterations"]
            payload["steady_iterations"] = cfg["steady_iterations"]

            profiles.append(payload)

            print(
                f"PROFILE PASS workload={workload} "
                f"samples={payload['execution_samples']['total']}",
                flush=True,
            )

    output_dir.mkdir(parents=True)

    metadata = {
        "schema_version": 1,
        "perf_item": "PERF004",
        "slice": "PERF004-B2-B",
        "phase": "retained-steady-state-mechanism-profile",
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "baseline_evidence_revision": cfg["baseline_evidence_revision"],
        "b1_evidence_revision": cfg["b1_evidence_revision"],
        "b2a_evidence_revision": cfg["b2a_evidence_revision"],
        "runtime": runtime,
        "host": {
            "platform": platform.system().lower(),
            "architecture": platform.machine(),
            "kernel": platform.release(),
            "cpuset": cpu,
        },
        "workload_operation_count": 10000,
        "warmup_iterations": 20,
        "steady_iterations": 100,
        "execution_sample_period": "10 ms",
        "diagnostic_only": True,
        "timing_claim": False,
    }

    raw = {
        "schema_version": 1,
        "profiles": profiles,
    }

    (output_dir / "run-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# PERF004-B2-B steady-state mechanism profiles",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision: `{cfg['protos_revision']}`",
        f"- PERF004-A evidence: `{cfg['baseline_evidence_revision']}`",
        f"- PERF004-B1 evidence: `{cfg['b1_evidence_revision']}`",
        f"- PERF004-B2-A evidence: `{cfg['b2a_evidence_revision']}`",
        f"- Runtime: `{runtime}`",
        "- Operation count: 10,000.",
        "- Warmup: 20 iterations.",
        "- Steady: 100 iterations.",
        "- JFR execution-sample period: 10 ms.",
        "- Diagnostic-only; no causal or language-wide performance claim.",
        "",
        "| workload | samples | top frame | top-frame share | JDK deopts | Truffle deopts |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]

    for profile in profiles:
        frames = profile["execution_samples"]["top_frames"]
        top = frames[0] if frames else {
            "name": "<none>",
            "percent": 0,
        }

        lines.append(
            f"| {profile['workload']} | "
            f"{profile['execution_samples']['total']} | "
            f"`{top['name']}` | "
            f"{top['percent']:.3f}% | "
            f"{profile['deoptimizations']['jdk_total']} | "
            f"{profile['deoptimizations']['truffle_total']} |"
        )

    lines.extend(
        [
            "",
            "Raw JFR-derived profiles in `raw.json` are authoritative.",
            "Hot-frame concentration is diagnostic evidence, not proof of causality.",
            "Interpretation must be combined with PERF004-B2-A scaling evidence.",
        ]
    )

    (output_dir / "README.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    names = [
        "README.md",
        "raw.json",
        "run-metadata.json",
    ]

    (output_dir / "SHA256SUMS").write_text(
        "\n".join(
            f"{sha256(output_dir / name)}  {name}"
            for name in names
        )
        + "\n",
        encoding="utf-8",
    )

    print("PERF004B2B_REFERENCE=PASS")
    print("PERF004B2B_PROFILES=4")
    print("PERF004B2B_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B2B_PROTOS_REPOSITORY_TOUCHED=NO")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "reference"))
    parser.add_argument("--harness-revision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if args.command == "validate":
        validate()
        return

    if not args.harness_revision or not args.output_dir:
        parser.error(
            "reference requires --harness-revision and --output-dir"
        )

    reference(
        Path(args.output_dir),
        args.harness_revision,
    )


if __name__ == "__main__":
    main()
