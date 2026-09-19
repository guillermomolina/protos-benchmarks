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
import json
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf004b2c.json"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"


def load() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def run(command: list[str], *, capture=False, check=True):
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )


def output(command: list[str]) -> str:
    p = run(command, capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed: " + " ".join(command)
            + "\nstdout:\n" + (p.stdout or "")[-5000:]
            + "\nstderr:\n" + (p.stderr or "")[-5000:]
        )
    return (p.stdout or "").rstrip("\n")


def validate() -> dict[str, Any]:
    cfg = load()

    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF004"
    assert cfg["slice"] == "PERF004-B2-C"
    assert cfg["diagnostic_claim"] is False
    assert cfg["protos_revision"] == (
        "4a03efc15620b37b2e418b3df30b4a26486446ec"
    )
    assert cfg["baseline_evidence_revision"] == (
        "5e8ff21f966c6c506652eef79c684d8b286bb546"
    )
    assert cfg["b2a_evidence_revision"] == (
        "8d8e1c6cce843d0d64c9e0b740ba13df04b3effb"
    )
    assert cfg["b2b_evidence_revision"] == (
        "cf9974970b4102d3e58191667b64d2981132c4bf"
    )

    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 20
    assert cfg["steady_iterations"] == 50
    assert cfg["network"] == "none"

    expected = {
        "micro/slot-read",
        "micro/closure-call",
        "micro/method-call",
        "runtime/monomorphic-dispatch",
    }
    assert {item["id"] for item in cfg["controls"]} == expected

    for evidence in (
        "results/perf004-a/SHA256SUMS",
        "results/perf004-b2a/SHA256SUMS",
        "results/perf004-b2b/SHA256SUMS",
    ):
        if not (ROOT / evidence).is_file():
            raise RuntimeError("missing evidence: " + evidence)

    print("PERF004B2C_CONFIG=PASS")
    print("PERF004B2C_BASELINE_EVIDENCE=PASS")
    print("PERF004B2C_B2A_EVIDENCE=PASS")
    print("PERF004B2C_B2B_EVIDENCE=PASS")
    print("PERF004B2C_PROTOS_MODIFICATION=NONE")
    print("PERF004B2C_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B2C_WORKLOADS=4")
    return cfg


def first_cpu() -> str:
    status = Path("/proc/self/status").read_text(
        encoding="utf-8",
        errors="replace",
    )
    marker = "Cpus_allowed_list:"
    line = next(
        line for line in status.splitlines()
        if line.startswith(marker)
    )
    return line.split(":", 1)[1].strip().split(",")[0].split("-")[0]


def image_tag() -> str:
    return "protos-benchmarks-perf004b2c:4a03efc15620"


def build_image(cfg: dict[str, Any]) -> str:
    tag = image_tag()
    run(
        [
            "docker",
            "build",
            "--build-arg",
            "GRAAL_BASE=" + cfg["toolchain"]["container_image"],
            "--build-arg",
            "MAVEN_VERSION=" + cfg["toolchain"]["maven_version"],
            "--build-arg",
            "PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git",
            "--build-arg",
            "PROTOS_REVISION=" + cfg["protos_revision"],
            "-t",
            tag,
            "-f",
            "docker/protos-perf006d/Dockerfile",
            ".",
        ]
    )
    return tag


def runtime_probe(tag: str, cpu: str) -> str:
    completed = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpuset-cpus",
            cpu,
            "--entrypoint",
            "java",
            tag,
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            "/opt/perf006d/probe:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
            "Perf006dRuntimeProbe",
        ],
        capture=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "runtime probe failed\n"
            + (completed.stderr or "")[-4000:]
        )

    observed = next(
        (
            line.split("=", 1)[1].strip()
            for line in (completed.stdout or "").splitlines()
            if line.startswith("PERF006D_RUNTIME=")
        ),
        "",
    )

    if observed != EXPECTED_RUNTIME:
        raise RuntimeError(f"runtime mismatch: {observed!r}")

    return observed


def parse_driver_output(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("driver emitted no output")
    return json.loads(lines[-1])


def summarize(values: list[int]) -> dict[str, float | int]:
    ordered = sorted(values)
    median = float(statistics.median(ordered))
    mad = float(statistics.median(
        abs(value - median) for value in ordered
    ))

    return {
        "count": len(ordered),
        "median_ns": median,
        "mad_ns": mad,
        "min_ns": ordered[0],
        "max_ns": ordered[-1],
    }


def run_case(
    tag: str,
    cpu: str,
    work: Path,
    item: dict[str, Any],
    mode: str,
    warmup: int,
    steady: int,
) -> dict[str, Any]:
    slug = item["id"].replace("/", "__")
    source = "/opt/perf006d/corpus/" + item["source"]

    if mode == "canonical":
        driver_source = source
    elif mode == "control":
        host_source = ROOT / "results/.perf004-b2c-work" / (
            slug + "-control.protos"
        )
        host_source.parent.mkdir(parents=True, exist_ok=True)

        canonical = output(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/bin/cat",
                tag,
                source,
            ]
        )

        before = item["replace"]
        after = item["with"]

        occurrences = canonical.count(before)
        if occurrences != 1:
            raise RuntimeError(
                f"control transform expected exactly one occurrence: "
                f"{item['id']} found={occurrences}"
            )

        control = canonical.replace(before, after, 1)
        host_source.write_text(control, encoding="utf-8")

        driver_source = "/work/" + host_source.name
    else:
        raise ValueError(mode)

    docker_command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpuset-cpus",
        cpu,
    ]

    if mode == "control":
        host_source = (
            ROOT / "results/.perf004-b2c-work" /
            (slug + "-control.protos")
        )
        docker_command.extend([
            "--volume",
            f"{host_source.resolve()}:/work/{host_source.name}",
        ])

    docker_command.extend([
        "--entrypoint",
        "java",
        tag,
        "-Xss128m",
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/perf006d/timing:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf006dPersistentDriver",
        driver_source,
        item["expected"],
        str(warmup),
        str(steady),
    ])

    completed = run(
        docker_command,
        capture=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"{mode} failed {item['id']} "
            f"returncode={completed.returncode}\n"
            f"stdout:\n{(completed.stdout or '')[-6000:]}\n"
            f"stderr:\n{(completed.stderr or '')[-6000:]}"
        )

    payload = parse_driver_output(completed.stdout or "")

    if payload.get("expected") != item["expected"]:
        raise RuntimeError(
            f"{mode} correctness failed: {item['id']}"
        )

    if payload.get("runtime") != EXPECTED_RUNTIME:
        raise RuntimeError(
            f"{mode} runtime identity failed: {item['id']}"
        )

    if payload.get("source_reused") is not True:
        raise RuntimeError("source reuse contract failed")

    if payload.get("process_reused") is not True:
        raise RuntimeError("process reuse contract failed")

    if payload.get("context_reused") is not True:
        raise RuntimeError("context reuse contract failed")

    if payload.get("fresh_activation_per_iteration") is not True:
        raise RuntimeError("fresh activation contract failed")

    payload["steady_summary"] = summarize(
        [int(x) for x in payload["steady_ns"]]
    )
    payload["warmup_summary"] = summarize(
        [int(x) for x in payload["warmup_ns"]]
    )

    return payload


def reference(output_dir: Path, harness_revision: str):
    cfg = validate()

    head = output(["git", "rev-parse", "HEAD"])
    if head != harness_revision:
        raise RuntimeError(
            f"exact harness required: HEAD={head} expected={harness_revision}"
        )

    if output(
        ["git", "status", "--porcelain", "--untracked-files=all"]
    ):
        raise RuntimeError("reference requires clean exact harness")

    if output_dir.exists():
        if not output_dir.is_dir():
            raise RuntimeError("output path is not a directory")
        if any(output_dir.iterdir()):
            raise RuntimeError(
                "output directory already contains evidence"
            )
        output_dir.rmdir()

    cpu = first_cpu()
    tag = build_image(cfg)
    runtime = runtime_probe(tag, cpu)

    cases = []

    for item in cfg["controls"]:
        for mode in ("canonical", "control"):
            print(
                f"CONTRAST BEGIN workload={item['id']} mode={mode} "
                f"operations={cfg['operation_count']}",
                flush=True,
            )

            work = (
                ROOT / "results/.perf004-b2c-work"
            )
            work.mkdir(
                parents=True,
                exist_ok=True,
            )

            payload = run_case(
                tag,
                cpu,
                work,
                item,
                mode,
                cfg["warmup_iterations"],
                cfg["steady_iterations"],
            )

            cases.append(
                {
                    "workload": item["id"],
                    "mode": mode,
                    "expected": item["expected"],
                    "warmup_ns": payload["warmup_ns"],
                    "steady_ns": payload["steady_ns"],
                    "warmup_summary": payload["warmup_summary"],
                    "steady_summary": payload["steady_summary"],
                }
            )

            print(
                f"CONTRAST PASS workload={item['id']} mode={mode} "
                f"median_ns={payload['steady_summary']['median_ns']}",
                flush=True,
            )

    canonical_by_workload = {
        item["workload"]: item
        for item in cases
        if item["mode"] == "canonical"
    }

    control_by_workload = {
        item["workload"]: item
        for item in cases
        if item["mode"] == "control"
    }

    comparisons = []

    for workload in canonical_by_workload:
        canonical = canonical_by_workload[workload]
        control = control_by_workload[workload]

        canonical_ns = canonical["steady_summary"]["median_ns"]
        control_ns = control["steady_summary"]["median_ns"]

        comparisons.append(
            {
                "workload": workload,
                "canonical_median_ns": canonical_ns,
                "control_median_ns": control_ns,
                "delta_ns": canonical_ns - control_ns,
                "control_over_canonical": (
                    control_ns / canonical_ns
                    if canonical_ns
                    else 0.0
                ),
            }
        )

    output_dir.mkdir(parents=True)

    report = {
        "schema_version": 1,
        "perf_item": "PERF004",
        "slice": "PERF004-B2-C",
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "baseline_evidence_revision": cfg["baseline_evidence_revision"],
        "b2a_evidence_revision": cfg["b2a_evidence_revision"],
        "b2b_evidence_revision": cfg["b2b_evidence_revision"],
        "runtime": runtime,
        "host": {
            "platform": platform.system().lower(),
            "architecture": platform.machine(),
            "kernel": platform.release(),
            "cpuset": cpu,
        },
        "measurement_contract": {
            "operation_count": cfg["operation_count"],
            "warmup_iterations": cfg["warmup_iterations"],
            "steady_iterations": cfg["steady_iterations"],
            "network": cfg["network"],
        },
        "cases": cases,
        "comparisons": comparisons,
        "interpretation_policy": {
            "causal_claim": False,
            "control_transform": (
                "only one guest operation expression is replaced by sink = 42"
            ),
            "correctness_required_before_timing": True,
        },
    }

    (output_dir / "raw.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = [
        "workload\tcanonical_median_ns\tcontrol_median_ns"
        "\tdelta_ns\tcontrol_over_canonical"
    ]

    for comparison in comparisons:
        rows.append(
            "\t".join(
                [
                    comparison["workload"],
                    str(comparison["canonical_median_ns"]),
                    str(comparison["control_median_ns"]),
                    str(comparison["delta_ns"]),
                    str(comparison["control_over_canonical"]),
                ]
            )
        )

    (output_dir / "summary.tsv").write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    readme = [
        "# PERF004-B2-C causal control contrast",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision: `{cfg['protos_revision']}`",
        f"- PERF004-A evidence: `{cfg['baseline_evidence_revision']}`",
        f"- PERF004-B2-A evidence: `{cfg['b2a_evidence_revision']}`",
        f"- PERF004-B2-B evidence: `{cfg['b2b_evidence_revision']}`",
        f"- Runtime: `{runtime}`",
        "- Operation count: 10,000.",
        "- Warmup: 20 iterations.",
        "- Steady: 50 iterations.",
        "",
        "Canonical and control variants retain the same outer repeat and",
        "activation structure. Only the selected guest operation is replaced",
        "with `sink = 42`.",
        "",
        "This is a causal-control experiment, not a claim that the measured",
        "difference is the whole cross-language performance gap.",
    ]

    (output_dir / "README.md").write_text(
        "\n".join(readme) + "\n",
        encoding="utf-8",
    )

    names = ["README.md", "raw.json", "summary.tsv"]

    (output_dir / "SHA256SUMS").write_text(
        "\n".join(
            f"{hashlib.sha256((output_dir / name).read_bytes()).hexdigest()}  {name}"
            for name in names
        )
        + "\n",
        encoding="utf-8",
    )

    print("PERF004B2C_REFERENCE=PASS")
    print("PERF004B2C_CASES=8")
    print("PERF004B2C_CORRECTNESS=PASS")
    print("PERF004B2C_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B2C_PROTOS_REPOSITORY_TOUCHED=NO")


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
