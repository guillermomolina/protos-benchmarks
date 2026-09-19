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
import json
from pathlib import Path
import platform
import re
import statistics
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf004b2.json"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"


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


def load() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def validate() -> dict[str, Any]:
    cfg = load()
    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF004"
    assert cfg["slice"] == "PERF004-B2-A"
    assert cfg["phase"] == "work-scaling-contrast-harness-ready"
    assert cfg["diagnostic_claim"] is False
    assert cfg["protos_revision"] == "4a03efc15620b37b2e418b3df30b4a26486446ec"
    assert cfg["baseline_evidence_revision"] == "5e8ff21f966c6c506652eef79c684d8b286bb546"
    assert cfg["b1_evidence_revision"] == "d73a982be26a6661d934727035afad0f459c3c26"
    assert cfg["comparison"]["operation_counts"] == [100, 1000, 10000]
    assert cfg["comparison"]["warmup_iterations"] == 20
    assert cfg["comparison"]["steady_iterations"] == 50
    assert cfg["comparison"]["network"] == "none"
    assert cfg["comparison"]["variant_transform"] == (
        "replace exactly one repeat(10000, occurrence with repeat(N,)"
    )
    assert len(cfg["workloads"]) == 4
    for item in cfg["workloads"]:
        assert item["expected"] == "42"
        assert item["source"].endswith(".protos")
    if not (ROOT / "results/perf004-a/SHA256SUMS").is_file():
        raise RuntimeError("PERF004-A evidence missing")
    if not (ROOT / "results/perf004-b1/SHA256SUMS").is_file():
        raise RuntimeError("PERF004-B1 evidence missing")
    print("PERF004B2A_CONFIG=PASS")
    print("PERF004B2A_BASELINE_EVIDENCE=PASS")
    print("PERF004B2A_B1_EVIDENCE=PASS")
    print("PERF004B2A_PROTOS_MODIFICATION=NONE")
    print("PERF004B2A_DIAGNOSTIC_CLAIM=NO")
    print(f"PERF004B2A_WORKLOADS={len(cfg['workloads'])}")
    return cfg


def first_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Cpus_allowed_list:\s*(.+)$", text, re.M)
    if not match:
        raise RuntimeError("cannot determine allowed CPU list")
    return match.group(1).split(",")[0].split("-")[0]


def image_tag(cfg: dict[str, Any]) -> str:
    return "protos-benchmarks-perf004b2a:" + cfg["protos_revision"][:12]


def build_image(cfg: dict[str, Any]) -> str:
    tag = image_tag(cfg)
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
    p = run(
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
            "/opt/perf006d/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
            "Perf006dRuntimeProbe",
        ],
        capture=True,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "")[-4000:])
    observed = next(
        (
            line.split("=", 1)[1].strip()
            for line in (p.stdout or "").splitlines()
            if line.startswith("PERF006D_RUNTIME=")
        ),
        "",
    )
    if observed != EXPECTED_RUNTIME:
        raise RuntimeError(f"runtime mismatch: {observed!r}")
    return observed


def parse_payload(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("driver emitted no stdout")
    return json.loads(lines[-1])


def run_variant(
    tag: str,
    cpu: str,
    item: dict[str, Any],
    count: int,
    work: Path,
    warmup: int,
    steady: int,
) -> dict[str, Any]:
    slug = item["id"].replace("/", "__")
    variant = f"/work/{slug}-{count}.protos"
    source = "/opt/perf006d/corpus/" + item["source"]

    shell = f"""
set -eu
src='{source}'
dst='{variant}'
count=$(grep -o 'repeat(10000,' "$src" | wc -l)
test "$count" -eq 1
sed 's/repeat(10000,/repeat({count_value},/' "$src" > "$dst"
test "$(grep -o 'repeat({count_value},' "$dst" | wc -l)" -eq 1
test "$(grep -o 'repeat(10000,' "$dst" | wc -l)" -eq 0
exec java -Xss128m \\
  --enable-native-access=ALL-UNNAMED \\
  -cp /opt/perf006d/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/* \\
  Perf006dPersistentDriver "$dst" '{expected}' '{warmup}' '{steady}'
""".format(
        count_value=count,
        expected=item["expected"],
        warmup=warmup,
        steady=steady,
    )

    p = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpuset-cpus",
            cpu,
            "--volume",
            f"{work.resolve()}:/work",
            "--entrypoint",
            "/bin/sh",
            tag,
            "-c",
            shell,
        ],
        capture=True,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"variant failed {item['id']} N={count}\n"
            f"stdout:\n{(p.stdout or '')[-6000:]}\n"
            f"stderr:\n{(p.stderr or '')[-6000:]}"
        )

    payload = parse_payload(p.stdout or "")
    if payload.get("expected") != item["expected"]:
        raise RuntimeError("correctness result mismatch")
    if payload.get("runtime") != EXPECTED_RUNTIME:
        raise RuntimeError("runtime identity mismatch")
    if payload.get("source_reused") is not True:
        raise RuntimeError("source reuse contract failed")
    if payload.get("process_reused") is not True:
        raise RuntimeError("process reuse contract failed")
    if payload.get("context_reused") is not True:
        raise RuntimeError("context reuse contract failed")
    if payload.get("fresh_activation_per_iteration") is not True:
        raise RuntimeError("fresh activation contract failed")

    return payload


def summarize(values: list[int]) -> dict[str, float | int]:
    ordered = sorted(values)
    median = float(statistics.median(ordered))
    mad = float(statistics.median(abs(x - median) for x in ordered))
    return {
        "count": len(ordered),
        "median_ns": median,
        "mad_ns": mad,
        "min_ns": ordered[0],
        "max_ns": ordered[-1],
        "ns_per_operation_median": median,
    }


def reference(output_dir: Path, harness_revision: str):
    cfg = validate()
    if output_dir.exists():
        if not output_dir.is_dir():
            raise RuntimeError("output path is not a directory")
        if any(output_dir.iterdir()):
            raise RuntimeError("output already contains evidence")
        output_dir.rmdir()

    head = output(["git", "rev-parse", "HEAD"])
    if head != harness_revision:
        raise RuntimeError(f"exact harness required: HEAD={head} expected={harness_revision}")
    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires clean exact harness")

    cpu = first_cpu()
    tag = build_image(cfg)
    runtime = runtime_probe(tag, cpu)

    with tempfile.TemporaryDirectory(prefix="perf004-b2a-") as tmp:
        work = Path(tmp)
        cases: list[dict[str, Any]] = []
        for item in cfg["workloads"]:
            for count in cfg["comparison"]["operation_counts"]:
                print(
                    f"CONTRAST BEGIN workload={item['id']} operations={count}",
                    flush=True,
                )
                payload = run_variant(
                    tag,
                    cpu,
                    item,
                    count,
                    work,
                    cfg["comparison"]["warmup_iterations"],
                    cfg["comparison"]["steady_iterations"],
                )
                steady = [int(x) for x in payload["steady_ns"]]
                warmup = [int(x) for x in payload["warmup_ns"]]
                case = {
                    "workload": item["id"],
                    "operations": count,
                    "expected": item["expected"],
                    "warmup_ns": warmup,
                    "steady_ns": steady,
                    "steady_summary": summarize(steady),
                    "warmup_summary": summarize(warmup),
                }
                cases.append(case)
                print(
                    f"CONTRAST PASS workload={item['id']} operations={count} "
                    f"median_ns={case['steady_summary']['median_ns']}",
                    flush=True,
                )

    output_dir.mkdir(parents=True)

    payload = {
        "schema_version": 1,
        "perf_item": "PERF004",
        "slice": "PERF004-B2-A",
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "baseline_evidence_revision": cfg["baseline_evidence_revision"],
        "b1_evidence_revision": cfg["b1_evidence_revision"],
        "protos_runtime": runtime,
        "host": {
            "platform": platform.system().lower(),
            "architecture": platform.machine(),
            "kernel": platform.release(),
            "cpu_model": next(
                (
                    line.split(":", 1)[1].strip()
                    for line in Path("/proc/cpuinfo")
                    .read_text(encoding="utf-8", errors="replace")
                    .splitlines()
                    if line.lower().startswith("model name") and ":" in line
                ),
                "",
            ),
            "cpuset": cpu,
        },
        "measurement_contract": cfg["comparison"],
        "cases": cases,
        "interpretation_policy": {
            "purpose": "distinguish fixed execution cost from cost scaling with repeated guest work",
            "causal_claim": False,
            "operation_normalization": "steady median divided by repeat count",
            "variant_semantics": "only the single repeat(10000, occurrence is changed",
        },
    }

    (output_dir / "raw.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = [
        "workload\toperations\tmedian_ns\tmad_ns\tmin_ns\tmax_ns\tns_per_operation"
    ]
    for case in cases:
        s = case["steady_summary"]
        rows.append(
            "\t".join(
                [
                    case["workload"],
                    str(case["operations"]),
                    str(s["median_ns"]),
                    str(s["mad_ns"]),
                    str(s["min_ns"]),
                    str(s["max_ns"]),
                    str(s["ns_per_operation_median"]),
                ]
            )
        )
    (output_dir / "summary.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    readme = [
        "# PERF004-B2-A work-scaling contrast",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision: `{cfg['protos_revision']}`",
        f"- PERF004-A evidence: `{cfg['baseline_evidence_revision']}`",
        f"- PERF004-B1 evidence: `{cfg['b1_evidence_revision']}`",
        f"- Runtime: `{runtime}`",
        "",
        "This is a diagnostic contrast, not a performance claim.",
        "Each variant changes exactly one canonical `repeat(10000,` literal to",
        "`repeat(N,` inside the benchmark container. Observable results remain 42.",
        "",
        "A roughly stable time-per-operation across N supports a per-operation",
        "cost interpretation; a large fixed intercept suggests execution/setup",
        "cost that is not proportional to guest work. Neither result alone proves",
        "a specific hotspot is causal.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")

    import hashlib

    names = ["README.md", "raw.json", "summary.tsv"]
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(
            f"{hashlib.sha256((output_dir / n).read_bytes()).hexdigest()}  {n}"
            for n in names
        )
        + "\n",
        encoding="utf-8",
    )

    print("PERF004B2A_REFERENCE=PASS")
    print(f"PERF004B2A_CASES={len(cases)}")
    print("PERF004B2A_CORRECTNESS=PASS")
    print("PERF004B2A_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B2A_PROTOS_REPOSITORY_TOUCHED=NO")


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
        parser.error("reference requires --harness-revision and --output-dir")

    reference(Path(args.output_dir), args.harness_revision)


if __name__ == "__main__":
    main()
