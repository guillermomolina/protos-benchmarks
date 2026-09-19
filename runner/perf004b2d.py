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
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf004b2d.json"
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

    assert cfg["slice"] == "PERF004-B2-D"
    assert cfg["diagnostic_claim"] is False
    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 20
    assert cfg["steady_iterations"] == 100
    assert cfg["execution_sample_period"] == "10 ms"
    assert cfg["protos_revision"] == "4a03efc15620b37b2e418b3df30b4a26486446ec"
    assert cfg["baseline_evidence_revision"] == "5e8ff21f966c6c506652eef79c684d8b286bb546"
    assert cfg["b2a_evidence_revision"] == "8d8e1c6cce843d0d64c9e0b740ba13df04b3effb"
    assert cfg["b2b_evidence_revision"] == "cf9974970b4102d3e58191667b64d2981132c4bf"
    assert cfg["b2c_evidence_revision"] == "8899ec163d6c0c7133b15ffa9c323447b683dbf2"
    assert len(cfg["controls"]) == 4

    for p in (
        "results/perf004-a/SHA256SUMS",
        "results/perf004-b2a/SHA256SUMS",
        "results/perf004-b2b/SHA256SUMS",
        "results/perf004-b2c/SHA256SUMS",
    ):
        assert (ROOT / p).is_file(), p

    print("PERF004B2D_CONFIG=PASS")
    print("PERF004B2D_BASELINE_EVIDENCE=PASS")
    print("PERF004B2D_B2A_EVIDENCE=PASS")
    print("PERF004B2D_B2B_EVIDENCE=PASS")
    print("PERF004B2D_B2C_EVIDENCE=PASS")
    print("PERF004B2D_PROTOS_MODIFICATION=NONE")
    print("PERF004B2D_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B2D_WORKLOADS=4")
    return cfg


def first_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return line.split(":", 1)[1].strip().split(",")[0].split("-")[0]
    raise RuntimeError("cannot determine allowed CPU")


def build_image(cfg: dict[str, Any]) -> str:
    tag = "protos-benchmarks-perf004b2d:" + cfg["protos_revision"][:12]
    run([
        "docker", "build",
        "--build-arg", "GRAAL_BASE=" + cfg["toolchain"]["container_image"],
        "--build-arg", "MAVEN_VERSION=" + cfg["toolchain"]["maven_version"],
        "--build-arg", "PROTOS_REPOSITORY=https://github.com/guillermomolina/protos.git",
        "--build-arg", "PROTOS_REVISION=" + cfg["protos_revision"],
        "-t", tag,
        "-f", "docker/protos-perf006d3/Dockerfile", ".",
    ])
    return tag


def runtime_probe(tag: str, cpu: str) -> str:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "java", tag,
        "--enable-native-access=ALL-UNNAMED",
        "-cp", "/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf006dRuntimeProbe",
    ], capture=True, check=False)
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


def analyze(tag: str, work: Path, jfr: Path, analysis: Path) -> dict[str, Any]:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--volume", f"{work.resolve()}:/work",
        "--entrypoint", "java", tag,
        "--add-modules", "jdk.jfr",
        "-cp", "/opt/perf006d3/analyzer",
        "Perf006d3JfrAnalyzer",
        "/work/" + jfr.name,
        "/work/" + analysis.name,
    ], capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            f"JFR analysis failed\nstdout:\n{(p.stdout or '')[-4000:]}\n"
            f"stderr:\n{(p.stderr or '')[-4000:]}"
        )
    return json.loads(analysis.read_text(encoding="utf-8"))


def profile(
    tag: str,
    cpu: str,
    work: Path,
    source_host: Path | None,
    source_container: str,
    expected: str,
    label: str,
    warmup: int,
    steady: int,
) -> dict[str, Any]:
    jfr = work / f"{label}.jfr"
    analysis = work / f"{label}.json"

    recording = (
        "-XX:StartFlightRecording="
        f"filename=/work/{jfr.name},"
        "settings=/opt/perf006d3/perf006d3.jfc,"
        "dumponexit=true"
    )

    command = [
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
    ]

    if source_host is not None:
        command += [
            "--volume",
            f"{source_host.resolve()}:/work/source.protos:ro",
        ]
        source_container = "/work/source.protos"

    command += [
        "--volume",
        f"{work.resolve()}:/work",
        "--entrypoint", "java", tag,
        "-Xss128m",
        recording,
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf006dPersistentDriver",
        source_container,
        expected,
        str(warmup),
        str(steady),
    ]

    p = run(command, capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            f"profile failed {label} returncode={p.returncode}\n"
            f"stdout:\n{(p.stdout or '')[-6000:]}\n"
            f"stderr:\n{(p.stderr or '')[-6000:]}"
        )

    if not jfr.is_file() or jfr.stat().st_size == 0:
        raise RuntimeError("missing JFR: " + label)

    payload = analyze(tag, work, jfr, analysis)
    if payload["execution_samples"]["total"] <= 0:
        raise RuntimeError("no execution samples: " + label)
    return payload


def top_frame(profile_payload: dict[str, Any]) -> dict[str, Any]:
    frames = profile_payload["execution_samples"]["top_frames"]
    return frames[0] if frames else {"name": "<none>", "percent": 0, "count": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("validate", "reference"))
    ap.add_argument("--harness-revision")
    ap.add_argument("--output-dir")
    args = ap.parse_args()

    cfg = validate()

    if args.command == "validate":
        return

    if not args.harness_revision or not args.output_dir:
        ap.error("reference requires --harness-revision and --output-dir")

    if output(["git", "rev-parse", "HEAD"]) != args.harness_revision:
        raise RuntimeError("exact harness revision mismatch")

    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires clean exact harness")

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise RuntimeError("output directory already contains evidence")
        output_dir.rmdir()

    cpu = first_cpu()
    tag = build_image(cfg)
    runtime = runtime_probe(tag, cpu)

    paired = []

    with tempfile.TemporaryDirectory(prefix="perf004-b2d-") as tmp:
        work = Path(tmp)

        for item in cfg["controls"]:
            workload = item["id"]
            slug = workload.replace("/", "__")
            canonical_source = "/opt/perf006d3/corpus/" + item["source"]

            source_text = output([
                "docker", "run", "--rm",
                "--entrypoint", "/bin/cat", tag,
                canonical_source,
            ])

            if source_text.count(item["replace"]) != 1:
                raise RuntimeError(
                    f"expected exactly one control target in {workload}"
                )

            control_text = source_text.replace(
                item["replace"], item["with"], 1
            )

            control_host = work / f"{slug}-control.protos"
            control_host.write_text(control_text, encoding="utf-8")

            print(
                f"PROFILE BEGIN workload={workload} mode=canonical operations=10000",
                flush=True,
            )
            canonical = profile(
                tag, cpu, work, None, canonical_source,
                item["expected"], slug + "-canonical",
                cfg["warmup_iterations"], cfg["steady_iterations"],
            )
            print(
                f"PROFILE PASS workload={workload} mode=canonical "
                f"samples={canonical['execution_samples']['total']}",
                flush=True,
            )

            print(
                f"PROFILE BEGIN workload={workload} mode=control operations=10000",
                flush=True,
            )
            control = profile(
                tag, cpu, work, control_host, "/work/source.protos",
                item["expected"], slug + "-control",
                cfg["warmup_iterations"], cfg["steady_iterations"],
            )
            print(
                f"PROFILE PASS workload={workload} mode=control "
                f"samples={control['execution_samples']['total']}",
                flush=True,
            )

            paired.append({
                "workload": workload,
                "canonical": canonical,
                "control": control,
            })

    output_dir.mkdir(parents=True)

    raw = {
        "schema_version": 1,
        "perf_item": "PERF004",
        "slice": "PERF004-B2-D",
        "harness_revision": args.harness_revision,
        "protos_revision": cfg["protos_revision"],
        "baseline_evidence_revision": cfg["baseline_evidence_revision"],
        "b2a_evidence_revision": cfg["b2a_evidence_revision"],
        "b2b_evidence_revision": cfg["b2b_evidence_revision"],
        "b2c_evidence_revision": cfg["b2c_evidence_revision"],
        "runtime": runtime,
        "operation_count": 10000,
        "warmup_iterations": 20,
        "steady_iterations": 100,
        "execution_sample_period": "10 ms",
        "diagnostic_only": True,
        "pairs": paired,
    }

    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = [
        "workload\tmode\texecution_samples\t"
        "continueAt_percent\tcontinueAt_count\t"
        "jdk_deopts\ttruffle_deopts"
    ]

    for pair in paired:
        for mode in ("canonical", "control"):
            payload = pair[mode]
            top = next(
                (
                    frame for frame in payload["execution_samples"]["top_frames"]
                    if "CachedBytecodeRootNodeGen$CachedBytecodeNode.continueAt" in frame["name"]
                    or "ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt" in frame["name"]
                ),
                {"percent": 0, "count": 0},
            )
            rows.append(
                "\t".join([
                    pair["workload"],
                    mode,
                    str(payload["execution_samples"]["total"]),
                    str(top["percent"]),
                    str(top["count"]),
                    str(payload["deoptimizations"]["jdk_total"]),
                    str(payload["deoptimizations"]["truffle_total"]),
                ])
            )

    (output_dir / "summary.tsv").write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    readme = [
        "# PERF004-B2-D paired JFR canonical/control",
        "",
        f"- Harness revision: `{args.harness_revision}`",
        f"- Protos revision: `{cfg['protos_revision']}`",
        f"- PERF004-A evidence: `{cfg['baseline_evidence_revision']}`",
        f"- PERF004-B2-A evidence: `{cfg['b2a_evidence_revision']}`",
        f"- PERF004-B2-B evidence: `{cfg['b2b_evidence_revision']}`",
        f"- PERF004-B2-C evidence: `{cfg['b2c_evidence_revision']}`",
        f"- Runtime: `{runtime}`",
        "- N=10,000.",
        "- Warmup=20, steady=100.",
        "- JFR ExecutionSample period=10 ms.",
        "- Diagnostic-only; no sole-cause claim.",
        "",
        "Canonical/control pairs differ only by the approved B2-C operation replacement.",
    ]

    (output_dir / "README.md").write_text(
        "\n".join(readme) + "\n",
        encoding="utf-8",
    )

    names = ["README.md", "raw.json", "summary.tsv"]
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(
            f"{hashlib.sha256((output_dir / n).read_bytes()).hexdigest()}  {n}"
            for n in names
        ) + "\n",
        encoding="utf-8",
    )

    print("PERF004B2D_REFERENCE=PASS")
    print("PERF004B2D_PAIRS=4")
    print("PERF004B2D_PROFILES=8")
    print("PERF004B2D_DIAGNOSTIC_CLAIM=NO")
    print("PERF004B2D_PROTOS_REPOSITORY_TOUCHED=NO")


if __name__ == "__main__":
    main()
