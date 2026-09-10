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

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import perf001f

STARTUP_CHILD_TIMEOUT_SECONDS = 120
CASE_TIMEOUT_SECONDS = 600
SMOKE_STARTUP_SAMPLES = 2
SMOKE_WARMUP_ITERATIONS = 2
SMOKE_STEADY_SAMPLES = 2
RETAINED_OUTPUT = ROOT / "results" / "perf001-f"
SMOKE_OUTPUT = ROOT / ".work" / "perf001f" / "reference-smoke"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTOR_FANOUT_ID = "concurrency/actor-fanout-requests"
STRONG_SCALING_IDS = {
    "concurrency/parallel-array-map",
    "concurrency/actor-fanout-requests",
}


def last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def percentile_nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        raise ValueError("cannot summarize an empty sample set")
    if percentile <= 0.0 or percentile > 1.0:
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def summarize_ns(values: list[int]) -> dict[str, float | int]:
    if not values or any(not isinstance(value, int) or value <= 0 for value in values):
        raise ValueError("timing samples must be positive integers")
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    return {
        "samples": len(values),
        "median_ns": median,
        "mad_ns": statistics.median(deviations),
        "p95_ns": percentile_nearest_rank(values, 0.95),
        "min_ns": min(values),
        "max_ns": max(values),
    }


def reference_cases(
    cfg: dict[str, Any], topology: dict[str, Any], *, smoke: bool
) -> list[dict[str, Any]]:
    series = {int(entry["width"]): entry for entry in topology["reference_series"]}
    cases: list[dict[str, Any]] = []
    for workload in cfg["workloads"]:
        for raw_width in workload["cpu_widths"]:
            width = int(raw_width)
            if width not in series:
                continue
            cases.append(
                {
                    "id": str(workload["id"]),
                    "source": str(workload["source"]),
                    "expected": str(workload["expected"]),
                    "kind": str(workload["kind"]),
                    "width": width,
                    "cpuset": str(series[width]["cpuset"]),
                }
            )
    if not cases:
        raise RuntimeError("PERF001-F has no eligible reference cases on this host")
    if smoke:
        order = {name: index for index, name in enumerate(perf001f.EXPECTED_IDS)}
        cases.sort(
            key=lambda case: (
                0 if case["id"] == ACTOR_FANOUT_ID and case["width"] == 8 else 1,
                order[case["id"]],
                case["width"],
            )
        )
    return cases


def docker_cleanup(name: str) -> None:
    subprocess.run(
        ["docker", "rm", "-f", name],
        cwd=ROOT,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def bounded_docker(
    command: list[str], *, container_name: str, timeout_seconds: int
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=None,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        docker_cleanup(container_name)
        raise RuntimeError(
            f"Docker case timed out after {timeout_seconds}s: {container_name}"
        ) from exc
    except KeyboardInterrupt:
        docker_cleanup(container_name)
        raise


def container_name(prefix: str, case: dict[str, Any]) -> str:
    leaf = re.sub(r"[^a-z0-9]+", "-", case["id"].lower()).strip("-")
    return f"perf001f-{prefix}-{os.getpid()}-{leaf}-w{case['width']}"[:120]


def startup_command(
    image: str, case: dict[str, Any], samples: int, name: str
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--cpuset-cpus",
        case["cpuset"],
        "--entrypoint",
        "java",
        image,
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/perf001f/startup:/opt/perf001f/driver:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf001fStartupDriver",
        f"/opt/perf001f/corpus/{case['source']}",
        case["expected"],
        str(samples),
        str(STARTUP_CHILD_TIMEOUT_SECONDS),
    ]


def run_startup_case(image: str, case: dict[str, Any], samples: int) -> list[int]:
    name = container_name("startup", case)
    print(
        f"STARTUP_CASE_BEGIN id={case['id']} width={case['width']} "
        f"cpuset={case['cpuset']} samples={samples}",
        flush=True,
    )
    completed = bounded_docker(
        startup_command(image, case, samples, name),
        container_name=name,
        timeout_seconds=CASE_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"startup controller failed for {case['id']} width={case['width']}: "
            f"exit={completed.returncode} stdout={completed.stdout!r}"
        )
    line = last_nonempty_line(completed.stdout or "")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"startup controller emitted invalid JSON for {case['id']}: {line!r}"
        ) from exc
    if payload.get("schema_version") != 1:
        raise RuntimeError("unsupported startup-controller payload schema")
    if payload.get("expected") != case["expected"]:
        raise RuntimeError(f"startup expected-result drift for {case['id']}")
    if payload.get("child_timeout_seconds") != STARTUP_CHILD_TIMEOUT_SECONDS:
        raise RuntimeError(f"startup child-timeout drift for {case['id']}")
    if payload.get("fresh_jvm_per_sample") is not True:
        raise RuntimeError(f"startup fresh-JVM contract failed for {case['id']}")
    if payload.get("docker_start_outside_timing") is not True:
        raise RuntimeError(f"startup Docker timing boundary drift for {case['id']}")
    values = payload.get("startup_ns")
    if not isinstance(values, list) or len(values) != samples:
        raise RuntimeError(f"startup sample-count mismatch for {case['id']}")
    if any(not isinstance(value, int) or value <= 0 for value in values):
        raise RuntimeError(f"startup non-positive sample for {case['id']}")
    print(
        f"STARTUP_CASE_PASS id={case['id']} width={case['width']} samples={samples}",
        flush=True,
    )
    return values


def named_persistent_command(
    image: str,
    case: dict[str, Any],
    warmup: int,
    steady: int,
    name: str,
) -> list[str]:
    command = perf001f.persistent_driver_command(
        image,
        case["cpuset"],
        case["source"],
        case["expected"],
        warmup,
        steady,
    )
    if command[:3] != ["docker", "run", "--rm"]:
        raise RuntimeError("persistent-driver Docker command shape drift")
    return command[:3] + ["--name", name] + command[3:]


def run_persistent_case(
    image: str, case: dict[str, Any], *, warmup: int, steady: int
) -> dict[str, Any]:
    name = container_name("persistent", case)
    print(
        f"PERSISTENT_CASE_BEGIN id={case['id']} width={case['width']} "
        f"cpuset={case['cpuset']} warmup={warmup} steady={steady}",
        flush=True,
    )
    completed = bounded_docker(
        named_persistent_command(image, case, warmup, steady, name),
        container_name=name,
        timeout_seconds=CASE_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"persistent driver failed for {case['id']} width={case['width']}: "
            f"exit={completed.returncode} stdout={completed.stdout!r}"
        )
    line = last_nonempty_line(completed.stdout or "")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"persistent driver emitted invalid JSON for {case['id']}: {line!r}"
        ) from exc
    if payload.get("schema_version") != 1 or payload.get("expected") != case["expected"]:
        raise RuntimeError(f"persistent payload identity mismatch for {case['id']}")
    for flag in ("setup_run_binding_ready", "process_reused", "context_reused", "run_binding_reused"):
        if payload.get(flag) is not True:
            raise RuntimeError(f"persistent production-hosting contract failed: {flag}")
    if payload.get("setup_projection") != "terminal run() -> run":
        raise RuntimeError(f"persistent setup-projection drift for {case['id']}")
    warmup_ns = payload.get("warmup_ns")
    steady_ns = payload.get("steady_ns")
    if not isinstance(warmup_ns, list) or len(warmup_ns) != warmup:
        raise RuntimeError(f"persistent warmup count mismatch for {case['id']}")
    if not isinstance(steady_ns, list) or len(steady_ns) != steady:
        raise RuntimeError(f"persistent steady count mismatch for {case['id']}")
    if any(
        not isinstance(value, int) or value <= 0
        for value in list(warmup_ns) + list(steady_ns)
    ):
        raise RuntimeError(f"persistent non-positive sample for {case['id']}")
    print(
        f"PERSISTENT_CASE_PASS id={case['id']} width={case['width']} "
        f"warmup={warmup} steady={steady}",
        flush=True,
    )
    return payload


def command_output(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return f"<unavailable exit={completed.returncode}>"
    return (completed.stdout or "").strip()


def host_identity() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "kernel": command_output(["uname", "-srvm"]),
        "docker_server_version": command_output(
            ["docker", "version", "--format", "{{.Server.Version}}"]
        ),
    }


def exact_harness_revision(required: str | None, *, retained: bool) -> str:
    observed = perf001f.harness_revision()
    if not retained:
        return observed
    if required is None or not SHA_RE.fullmatch(required):
        raise RuntimeError("--harness-revision=<exact 40-char SHA> is required for retained H4")
    if observed != required:
        raise RuntimeError(
            f"retained evidence requires exact clean harness revision {required}; observed {observed}"
        )
    return observed


def apply_scaling(cases: list[dict[str, Any]]) -> None:
    baselines: dict[str, float] = {}
    for case in cases:
        if case["id"] in STRONG_SCALING_IDS and case["width"] == 1:
            baselines[case["id"]] = float(case["summary"]["steady"]["median_ns"])
    for case in cases:
        if case["id"] not in STRONG_SCALING_IDS:
            case["scaling"] = None
            continue
        baseline = baselines.get(case["id"])
        if baseline is None:
            raise RuntimeError(f"missing width=1 scaling baseline for {case['id']}")
        current = float(case["summary"]["steady"]["median_ns"])
        speedup = baseline / current
        case["scaling"] = {
            "steady_median_speedup_vs_width1": speedup,
            "steady_median_efficiency": speedup / int(case["width"]),
        }


def write_summary_tsv(path: Path, cases: list[dict[str, Any]]) -> None:
    columns = [
        "workload", "kind", "width", "cpuset", "phase", "samples",
        "median_ns", "mad_ns", "p95_ns", "min_ns", "max_ns",
        "speedup_vs_width1", "efficiency",
    ]
    lines = ["\t".join(columns)]
    for case in cases:
        scaling = case.get("scaling")
        for phase in ("startup", "warmup", "steady"):
            summary = case["summary"][phase]
            speedup = ""
            efficiency = ""
            if phase == "steady" and scaling is not None:
                speedup = f"{scaling['steady_median_speedup_vs_width1']:.6f}"
                efficiency = f"{scaling['steady_median_efficiency']:.6f}"
            row = [
                case["id"], case["kind"], str(case["width"]), case["cpuset"],
                phase, str(summary["samples"]), str(summary["median_ns"]),
                str(summary["mad_ns"]), str(summary["p95_ns"]),
                str(summary["min_ns"]), str(summary["max_ns"]),
                speedup, efficiency,
            ]
            lines.append("\t".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_md(
    path: Path,
    cases: list[dict[str, Any]],
    *,
    retained: bool,
    protos_revision: str,
    harness_revision: str,
) -> None:
    lines = [
        "# PERF001-F reference evidence summary",
        "",
        f"- Evidence class: {'retained H4 reference evidence' if retained else 'non-retained H3 smoke'}",
        f"- Protos revision: `{protos_revision}`",
        f"- Harness revision: `{harness_revision}`",
        "- Statistics: median, MAD, nearest-rank p95, min, max.",
        "- Scaling speedup/efficiency: steady median only, strong-scaling workloads only.",
        "",
        "| workload | width | startup median ns | steady median ns | speedup | efficiency |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in cases:
        scaling = case.get("scaling")
        speedup = "" if scaling is None else f"{scaling['steady_median_speedup_vs_width1']:.3f}"
        efficiency = "" if scaling is None else f"{scaling['steady_median_efficiency']:.3f}"
        lines.append(
            f"| `{case['id']}` | {case['width']} | "
            f"{case['summary']['startup']['median_ns']} | "
            f"{case['summary']['steady']['median_ns']} | {speedup} | {efficiency} |"
        )
    lines += [
        "",
        "Raw ordered startup, warmup and steady samples remain authoritative in `evidence.json`.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(output: Path, names: list[str]) -> None:
    lines = [f"{sha256_file(output / name)}  {name}" for name in sorted(names)]
    (output / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_output(output: Path, *, retained: bool) -> None:
    if retained:
        if output.exists() and any(output.iterdir()):
            raise RuntimeError(f"retained output directory must be absent or empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
    else:
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True, exist_ok=True)


def execute(*, smoke: bool, harness_revision_arg: str | None, output_arg: str | None) -> None:
    cfg = perf001f.validate_config(announce=False)
    retained = not smoke
    revision = perf001f.selected_revision(None)
    harness_revision = exact_harness_revision(harness_revision_arg, retained=retained)

    if cfg.get("phase") != "reference-evidence-runner-ready":
        raise RuntimeError("PERF001-F H3 phase is not reference-evidence-runner-ready")
    if cfg.get("runtime_blocker_239_fixed_by") != revision:
        raise RuntimeError("PERF001-F runtime blocker fix identity drift")

    source = perf001f.source_checkout(revision)
    toolchain = perf001f.read_toolchain(source)
    image = perf001f.build_image(revision, source, toolchain)

    correctness = perf001f.correctness(revision, source, image, toolchain)
    topology = perf001f.host_topology()
    cases = reference_cases(cfg, topology, smoke=smoke)

    policy = cfg["measurement_policy"]
    startup_samples = SMOKE_STARTUP_SAMPLES if smoke else int(policy["startup_samples"])
    warmup_iterations = SMOKE_WARMUP_ITERATIONS if smoke else int(policy["warmup_iterations"])
    steady_samples = SMOKE_STEADY_SAMPLES if smoke else int(policy["steady_samples"])

    output = Path(output_arg).resolve() if output_arg else (SMOKE_OUTPUT if smoke else RETAINED_OUTPUT)
    prepare_output(output, retained=retained)

    measured: list[dict[str, Any]] = []
    for index, case in enumerate(cases, 1):
        print(
            f"REFERENCE_CASE_BEGIN index={index}/{len(cases)} id={case['id']} "
            f"width={case['width']} cpuset={case['cpuset']}",
            flush=True,
        )
        startup_ns = run_startup_case(image, case, startup_samples)
        persistent = run_persistent_case(
            image, case, warmup=warmup_iterations, steady=steady_samples
        )
        record = dict(case)
        record["raw"] = {
            "startup_ns": startup_ns,
            "warmup_ns": list(persistent["warmup_ns"]),
            "steady_ns": list(persistent["steady_ns"]),
        }
        record["summary"] = {
            "startup": summarize_ns(record["raw"]["startup_ns"]),
            "warmup": summarize_ns(record["raw"]["warmup_ns"]),
            "steady": summarize_ns(record["raw"]["steady_ns"]),
        }
        measured.append(record)
        print(
            f"REFERENCE_CASE_PASS index={index}/{len(cases)} id={case['id']} width={case['width']}",
            flush=True,
        )

    apply_scaling(measured)

    metadata = {
        "schema_version": 1,
        "perf_item": "PERF001",
        "slice": "PERF001-F",
        "phase": "H4_RETAINED_REFERENCE" if retained else "H3_NON_RETAINED_SMOKE",
        "retained": retained,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protos_revision": revision,
        "corpus_publication_revision": cfg["corpus_publication_revision"],
        "reference_gate": cfg["reference_gate"],
        "reference_gate_satisfied_by": cfg["reference_gate_satisfied_by"],
        "runtime_blocker_239_fixed_by": cfg["runtime_blocker_239_fixed_by"],
        "harness_revision": harness_revision,
        "toolchain": toolchain,
        "optimizing_runtime": correctness["optimizing_runtime"],
        "image": perf001f.image_identity(image),
        "host": host_identity(),
        "topology": topology,
        "measurement_policy": {
            "startup_samples": startup_samples,
            "warmup_iterations": warmup_iterations,
            "steady_samples": steady_samples,
            "startup_child_timeout_seconds": STARTUP_CHILD_TIMEOUT_SECONDS,
            "case_timeout_seconds": CASE_TIMEOUT_SECONDS,
        },
        "startup_boundary": {
            "docker_container_creation_start_included": False,
            "fresh_jvm_per_sample": True,
            "child_driver": "Perf001fPersistentDriver with warmup=0 steady=1",
        },
    }
    evidence = {
        "schema_version": 1,
        "retained": retained,
        "protos_revision": revision,
        "harness_revision": harness_revision,
        "cases": measured,
    }

    (output / "run-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    (output / "evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    write_summary_tsv(output / "summary.tsv", measured)
    write_summary_md(
        output / "summary.md",
        measured,
        retained=retained,
        protos_revision=revision,
        harness_revision=harness_revision,
    )
    write_manifest(output, ["evidence.json", "run-metadata.json", "summary.md", "summary.tsv"])

    print(f"PERF001F_REFERENCE_CASES: PASS {len(measured)}/{len(measured)}")
    print(f"PERF001F_REFERENCE_OUTPUT={output}")
    if smoke:
        print("PERF001F_H3_REFERENCE_RUNNER_SMOKE: PASS")
        print("PERF001F_REFERENCE_TIMING: NOT_RUN")
    else:
        print("PERF001F_H4_RETAINED_REFERENCE: PASS")
        print("PERF001F_REFERENCE_TIMING: RETAINED")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="PERF001-F H3/H4 reference evidence runner")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="run H3 2/2/2 non-retained smoke")
    mode.add_argument("--run", action="store_true", help="run H4 retained 10/20/20 reference evidence")
    result.add_argument("--harness-revision", help="exact published H3 harness SHA; required with --run")
    result.add_argument("--output-dir")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        execute(
            smoke=bool(args.smoke),
            harness_revision_arg=args.harness_revision,
            output_arg=args.output_dir,
        )
        return 0
    except KeyboardInterrupt:
        print("PERF001-F reference runner interrupted; active Docker case cleaned", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"PERF001-F reference runner error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
