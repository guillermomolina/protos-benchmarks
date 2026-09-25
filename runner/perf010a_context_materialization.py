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

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PRODUCT_REVISION = "f1cee2d85858804ad3775adf43a9fab97664da2a"
IMAGE = "protos-benchmarks-perf010a-post-i068-protos:f1cee2d85858"

JAVA_SOURCE = (
    ROOT
    / "docker"
    / "protos-perf010a"
    / "Perf010aContextMaterializationProbe.java"
)

PROBE_CLASS = (
    "com.guillermomolina.protos.benchmarks.perf010a."
    "Perf010aContextMaterializationProbe"
)

NO_BINDING_SOURCE = """\
repeat: (count, operation) => {
    (count > 0).ifTrue() {
        operation()
        repeat(count - 1, operation)
    }
}

repeat(10000, () => { 42 })
42
"""

UNUSED_LOCAL_SOURCE = """\
repeat: (count, operation) => {
    (count > 0).ifTrue() {
        operation()
        repeat(count - 1, operation)
    }
}

repeat(10000, () => {
    local: 42
    42
})
42
"""


def run(
    command: list[str],
    *,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "command failed: "
            + " ".join(command)
            + "\nstdout:\n"
            + (completed.stdout or "")[-8000:]
            + "\nstderr:\n"
            + (completed.stderr or "")[-8000:]
        )

    return completed


def output(command: list[str]) -> str:
    return run(command).stdout.strip()


def first_allowed_cpu() -> str:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("Cpus_allowed_list:"):
            spec = line.split(":", 1)[1].strip()
            first_group = spec.split(",", 1)[0]
            return first_group.split("-", 1)[0]

    raise RuntimeError("cannot determine Cpus_allowed_list")


def validate_image_identity() -> None:
    run(["docker", "image", "inspect", IMAGE])

    head = output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/bin/cat",
            IMAGE,
            "/opt/protos-source/.git/HEAD",
        ]
    )

    if head != EXPECTED_PRODUCT_REVISION:
        raise RuntimeError(
            "product revision mismatch: "
            f"expected {EXPECTED_PRODUCT_REVISION}, got {head!r}"
        )


def compile_probe(work: Path) -> Path:
    classes = work / "classes"
    classes.mkdir()

    run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{ROOT}:/repo:ro",
            "-v",
            f"{work}:/work",
            "--entrypoint",
            "/bin/bash",
            IMAGE,
            "-lc",
            "javac "
            "--add-modules jdk.management "
            "-cp '/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*' "
            "-d /work/classes "
            "/repo/docker/protos-perf010a/"
            "Perf010aContextMaterializationProbe.java "
            "&& chmod -R a+rwX /work",
        ]
    )

    return classes


def parse_probe(text: str) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}

    for line in text.splitlines():
        if not line.startswith("CASE="):
            continue

        fields = dict(item.split("=", 1) for item in line.split())
        result[fields["CASE"]] = {
            "iterations": float(fields["ITERATIONS"]),
            "bytes_per_op": float(fields["BYTES_PER_OP"]),
            "ns_per_op": float(fields["NS_PER_OP"]),
        }

    expected = {"execution-context", "ordinary-object", "return-home"}
    if set(result) != expected:
        raise RuntimeError(
            "allocation probe did not report the expected cases: "
            + repr(result)
        )

    return result


def run_allocation_probe(
    work: Path,
    *,
    warmup: int,
    steady: int,
) -> dict[str, dict[str, float]]:
    cpu = first_allowed_cpu()

    text = output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpuset-cpus",
            cpu,
            "-v",
            f"{work}:/work:ro",
            "--entrypoint",
            "java",
            IMAGE,
            "--add-modules",
            "jdk.management",
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            "/work/classes:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
            PROBE_CLASS,
            str(warmup),
            str(steady),
        ]
    )

    return parse_probe(text)


def write_guest_sources(work: Path) -> None:
    (work / "no-binding.protos").write_text(
        NO_BINDING_SOURCE,
        encoding="utf-8",
    )
    (work / "unused-local.protos").write_text(
        UNUSED_LOCAL_SOURCE,
        encoding="utf-8",
    )


def run_guest_timing(
    work: Path,
    case: str,
    *,
    warmup: int,
    steady: int,
) -> list[int]:
    cpu = first_allowed_cpu()

    text = output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpuset-cpus",
            cpu,
            "-v",
            f"{work}:/work:ro",
            "--entrypoint",
            "java",
            IMAGE,
            "-Xss128m",
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            (
                "/opt/perf010a/diagnostic:"
                "/opt/protos/lib/protos.jar:"
                "/opt/protos/lib/runtime/*"
            ),
            "Perf010aTimingDriver",
            f"/work/{case}.protos",
            "42",
            str(warmup),
            str(steady),
        ]
    )

    data = json.loads(text)

    values = [int(value) for value in data["steady_ns"]]
    if len(values) != steady:
        raise RuntimeError(
            f"{case}: expected {steady} steady samples, got {len(values)}"
        )

    return values


def guest_summary(
    work: Path,
    *,
    forks: int,
    warmup: int,
    steady: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for case in ("no-binding", "unused-local"):
        fork_medians: list[float] = []
        all_values: list[int] = []

        for _ in range(forks):
            values = run_guest_timing(
                work,
                case,
                warmup=warmup,
                steady=steady,
            )
            fork_medians.append(statistics.median(values))
            all_values.extend(values)

        median = statistics.median(all_values)
        mad = statistics.median(abs(value - median) for value in all_values)

        result[case] = {
            "fork_medians_ns": fork_medians,
            "steady_median_ns": median,
            "mad_ns": mad,
            "min_ns": min(all_values),
            "max_ns": max(all_values),
        }

    control = float(result["no-binding"]["steady_median_ns"])
    treatment = float(result["unused-local"]["steady_median_ns"])
    delta = treatment - control

    result["delta"] = {
        "ns_per_10000_callbacks": delta,
        "ns_per_callback": delta / 10000.0,
        "ratio": treatment / control,
        "percent": (treatment / control - 1.0) * 100.0,
    }

    return result


def validate() -> None:
    if not JAVA_SOURCE.is_file():
        raise RuntimeError(f"missing probe source: {JAVA_SOURCE}")

    validate_image_identity()

    with tempfile.TemporaryDirectory(
        prefix="perf010a-context-materialization-"
    ) as tmp:
        work = Path(tmp)
        compile_probe(work)
        write_guest_sources(work)

        allocation = run_allocation_probe(
            work,
            warmup=1000,
            steady=1000,
        )

        run_guest_timing(
            work,
            "no-binding",
            warmup=1,
            steady=1,
        )

        run_guest_timing(
            work,
            "unused-local",
            warmup=1,
            steady=1,
        )

    context_bytes = allocation["execution-context"]["bytes_per_op"]
    ordinary_bytes = allocation["ordinary-object"]["bytes_per_op"]

    if abs(context_bytes - ordinary_bytes) > 1.0:
        raise RuntimeError(
            "execution-context and ordinary-object allocation footprints "
            "unexpectedly diverged during validation"
        )

    print("PERF010A_CONTEXT_MATERIALIZATION_VALIDATE=PASS")


def smoke() -> None:
    validate_image_identity()

    with tempfile.TemporaryDirectory(
        prefix="perf010a-context-materialization-"
    ) as tmp:
        work = Path(tmp)
        compile_probe(work)
        write_guest_sources(work)

        allocation = run_allocation_probe(
            work,
            warmup=10000,
            steady=10000,
        )

        guest = guest_summary(
            work,
            forks=1,
            warmup=5,
            steady=5,
        )

    print(
        json.dumps(
            {
                "kind": "PERF010A_CONTEXT_MATERIALIZATION_SMOKE",
                "product_revision": EXPECTED_PRODUCT_REVISION,
                "allocation": allocation,
                "guest": guest,
            },
            indent=2,
            sort_keys=True,
        )
    )


def measure(args: argparse.Namespace) -> None:
    validate_image_identity()

    with tempfile.TemporaryDirectory(
        prefix="perf010a-context-materialization-"
    ) as tmp:
        work = Path(tmp)
        compile_probe(work)
        write_guest_sources(work)

        allocation = run_allocation_probe(
            work,
            warmup=args.allocation_warmup,
            steady=args.allocation_steady,
        )

        guest = guest_summary(
            work,
            forks=args.forks,
            warmup=args.warmup,
            steady=args.steady,
        )

    result = {
        "kind": "PERF010A_CONTEXT_MATERIALIZATION_MEASUREMENT",
        "product_revision": EXPECTED_PRODUCT_REVISION,
        "image": IMAGE,
        "cpu": first_allowed_cpu(),
        "allocation_contract": {
            "warmup": args.allocation_warmup,
            "steady": args.allocation_steady,
            "thread_allocated_bytes": True,
            "normal_tlab": True,
        },
        "guest_timing_contract": {
            "forks": args.forks,
            "warmup_per_fork": args.warmup,
            "steady_per_fork": args.steady,
            "network": "none",
            "stack": "-Xss128m",
            "jfr": False,
            "compiler_tracing": False,
        },
        "allocation": allocation,
        "guest": guest,
    }

    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate")
    subparsers.add_parser("smoke")

    measure_parser = subparsers.add_parser("measure")
    measure_parser.add_argument("--forks", type=int, default=5)
    measure_parser.add_argument("--warmup", type=int, default=120)
    measure_parser.add_argument("--steady", type=int, default=100)
    measure_parser.add_argument(
        "--allocation-warmup",
        type=int,
        default=100000,
    )
    measure_parser.add_argument(
        "--allocation-steady",
        type=int,
        default=500000,
    )
    measure_parser.add_argument(
        "--output",
        type=Path,
    )

    args = parser.parse_args()

    if args.command == "validate":
        validate()
    elif args.command == "smoke":
        smoke()
    elif args.command == "measure":
        measure(args)
    else:
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
