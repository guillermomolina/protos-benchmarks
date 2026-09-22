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

"""PERF008 steady-state full-stack JFR evidence harness.

Reuses the exact PERF004-B2-D canonical/control matrix (slot-read, closure-call,
method-call, monomorphic-dispatch; N=10,000; warmup=20; steady=100) against the
current pinned `protos` revision, fixing two instrumental gaps in the historical
PERF004-B2-D / PERF006-D3 evidence:

  1. Full bounded call stacks (leaf-first, depth <= 32) are retained per
     `jdk.ExecutionSample` by `Perf006d3JfrAnalyzer`, instead of only the leaf frame.
  2. The JFR recording covers steady-state execution only: `Perf008SteadyStateDriver`
     starts a `jdk.jfr.Recording` immediately before the steady loop and stops it
     immediately after, excluding JVM startup, Core/Process bootstrap, and warmup.

This module implements measurement infrastructure only. It does not optimize
Protos and does not change the experiment (workloads, N, warmup/steady counts,
CPU policy, or correctness contract) relative to `runner/perf004b2d.py`.
"""

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
CONFIG = ROOT / "config/perf008.json"
B2D_CONFIG = ROOT / "config/perf004b2d.json"
EXPECTED_PROTOS_REVISION = "529ab58c2cf57a2e4170dd5ffa972651e89ac92e"
EXPECTED_HISTORICAL_PROTOS_REVISION = "4a03efc15620b37b2e418b3df30b4a26486446ec"
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def worktree_harness_revision() -> str:
    """Declared harness source identity for the non-retained `smoke` command only.

    Mirrors `runner/perf001f.harness_revision()`: returns the exact HEAD SHA when the
    working tree is clean, otherwise the explicit `WORKTREE_PRECOMMIT` sentinel. Retained
    reference evidence never uses this helper - `reference()` still requires an exact clean
    SHA matching `--harness-revision`, per `AGENTS.work/REPRODUCIBILITY.md` ("Floating
    branch names ... are not sufficient identities for retained reference results"; an
    uncommitted tree is weaker still). `smoke` exists so an uncommitted harness fix can be
    exercised end-to-end before publication, without producing evidence that claims a
    pinned identity it does not have.
    """
    head = output(["git", "rev-parse", "HEAD"])
    dirty = output(["git", "status", "--porcelain", "--untracked-files=all"])
    return head if not dirty else "WORKTREE_PRECOMMIT"


def validate() -> dict[str, Any]:
    cfg = load()
    b2d_cfg = json.loads(B2D_CONFIG.read_text(encoding="utf-8"))

    assert cfg["perf_item"] == "PERF008"
    assert cfg["slice"] == "PERF008"
    assert cfg["diagnostic_claim"] is False
    assert cfg["protos_revision"] == EXPECTED_PROTOS_REVISION
    assert cfg["historical_protos_revision"] == EXPECTED_HISTORICAL_PROTOS_REVISION
    assert cfg["historical_protos_revision"] == b2d_cfg["protos_revision"]

    # PERF008 is an instrumental slice: it must not redefine the PERF004-B2-D
    # experiment (workloads, replacements, N, warmup/steady counts).
    assert cfg["operation_count"] == 10000 == b2d_cfg["operation_count"]
    assert cfg["warmup_iterations"] == 20 == b2d_cfg["warmup_iterations"]
    assert cfg["steady_iterations"] == 100 == b2d_cfg["steady_iterations"]
    assert cfg["execution_sample_period"] == "10 ms" == b2d_cfg["execution_sample_period"]
    assert cfg["controls"] == b2d_cfg["controls"]
    assert len(cfg["controls"]) == 4
    assert cfg["stack_depth_limit"] == 32
    assert cfg["jfr_recording_phase"] == "steady_only"

    for p in ("results/perf004-b2d/SHA256SUMS", "results/perf006-d3/SHA256SUMS"):
        assert (ROOT / p).is_file(), p

    driver_src = (
        ROOT / "docker/protos-perf006d3/Perf008SteadyStateDriver.java"
    ).read_text(encoding="utf-8")
    for required in (
        "import jdk.jfr.Configuration;",
        "import jdk.jfr.Recording;",
        "recording.start();",
        "recording.stop();",
    ):
        assert required in driver_src

    analyzer_src = (
        ROOT / "docker/protos-perf006d3/Perf006d3JfrAnalyzer.java"
    ).read_text(encoding="utf-8")
    for required in (
        "MAX_STACK_DEPTH = 32",
        "callPaths",
        "continueAtAnyDepth",
        "builderAnyDepth",
        "CONTINUE_AT_MARKERS",
    ):
        assert required in analyzer_src

    assert cfg["toolchain"]["python_package"]

    dockerfile = (ROOT / "docker/protos-perf006d3/Dockerfile").read_text(encoding="utf-8")
    for required in ("Perf008SteadyStateDriver.java", "EXPECTED_CONTAINER_IMAGE", "${PYTHON_PACKAGE}"):
        assert required in dockerfile

    print("PERF008_CONFIG=PASS")
    print("PERF008_EXPERIMENT_MATRIX_UNCHANGED=PASS")
    print("PERF008_HISTORICAL_EVIDENCE_PRESENT=PASS")
    print("PERF008_HARNESS_SOURCE=PASS")
    print("PERF008_PROTOS_MODIFICATION=NONE")
    print("PERF008_DIAGNOSTIC_CLAIM=NO")
    print("PERF008_WORKLOADS=4")
    return cfg


def first_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return line.split(":", 1)[1].strip().split(",")[0].split("-")[0]
    raise RuntimeError("cannot determine allowed CPU")


def host_identity() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def build_image(cfg: dict[str, Any]) -> str:
    tag = "protos-benchmarks-perf008:" + cfg["protos_revision"][:12]
    toolchain = cfg["toolchain"]
    run([
        "docker", "build",
        "--build-arg", "GRAAL_BASE=" + toolchain["container_image"],
        "--build-arg", "MAVEN_VERSION=" + toolchain["maven_version"],
        "--build-arg", "PROTOS_REPOSITORY=" + cfg["protos_repository"],
        "--build-arg", "PROTOS_REVISION=" + cfg["protos_revision"],
        "--build-arg", "EXPECTED_GRAALVM_RELEASE=" + toolchain["graalvm_release"],
        "--build-arg", "EXPECTED_JDK_VERSION=" + toolchain["jdk_version"],
        "--build-arg", "EXPECTED_CONTAINER_IMAGE=" + toolchain["container_image"],
        "--build-arg", "EXPECTED_GRAAL_COMPONENTS_VERSION=" + toolchain["graal_truffle_version"],
        "--build-arg", "EXPECTED_MAVEN_VERSION=" + toolchain["maven_version"],
        "--build-arg", "PYTHON_PACKAGE=" + toolchain["python_package"],
        "--label", "org.opencontainers.image.revision=" + cfg["protos_revision"],
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


def java_version_probe(tag: str, cpu: str) -> str:
    p = run([
        "docker", "run", "--rm", "--network", "none",
        "--cpuset-cpus", cpu,
        "--entrypoint", "java", tag,
        "-version",
    ], capture=True, check=False)
    if p.returncode != 0:
        raise RuntimeError("java -version probe failed: " + (p.stderr or "")[-2000:])
    # `java -version` writes to stderr by convention.
    return (p.stderr or p.stdout or "").strip()


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
    """Runs Perf008SteadyStateDriver (steady-state-only JFR) and analyzes the recording.

    Unlike PERF004-B2-D's `profile()`, no `-XX:StartFlightRecording=...` JVM flag is
    passed: the recording is started/stopped programmatically by the driver itself,
    strictly bracketing the steady loop, so bootstrap and warmup are excluded.
    """
    jfr = work / f"{label}.jfr"
    analysis = work / f"{label}.json"

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
        "--add-modules", "jdk.jfr",
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/perf006d3/diagnostic:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf008SteadyStateDriver",
        source_container,
        expected,
        str(warmup),
        str(steady),
        "/opt/perf006d3/perf006d3.jfc",
        "/work/" + jfr.name,
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
    if payload.get("stack_depth_limit") != 32:
        raise RuntimeError("unexpected stack_depth_limit in analyzer output: " + label)

    call_paths = payload["execution_samples"]["call_paths"]
    if not call_paths or " -> " not in call_paths[0]["name"]:
        raise RuntimeError(
            "full-stack capture did not observe a multi-frame call path: " + label
        )

    continue_at = payload["continue_at"]
    if continue_at["any_depth_count"] < continue_at["leaf_count"]:
        raise RuntimeError("continueAt any-depth count below leaf count: " + label)

    return {
        "profile": payload,
        "jfr_identity": {
            "sha256": sha256(jfr),
            "size_bytes": jfr.stat().st_size,
            "retained_in_git": False,
            "retention_reason": (
                "binary JFR omitted from git; derived structural JSON (this profile), "
                "its SHA256, and its size are retained instead, matching the "
                "results/perf006-d3 evidence-retention pattern"
            ),
        },
    }


def run_matrix(cfg: dict[str, Any], tag: str, cpu: str, work: Path) -> list[dict[str, Any]]:
    """Runs the full canonical/control profile matrix (4 workloads) and returns paired results.

    Shared by `smoke()` (ephemeral, non-retained) and `reference()` (persisted, retained
    evidence); the matrix itself - workloads, N, warmup/steady counts - is identical either
    way, matching the PERF004-B2-D experiment exactly (see `validate()`).
    """
    paired = []

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
            f"samples={canonical['profile']['execution_samples']['total']}",
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
            f"samples={control['profile']['execution_samples']['total']}",
            flush=True,
        )

        paired.append({
            "workload": workload,
            "canonical": canonical,
            "control": control,
        })

    return paired


def smoke() -> None:
    """Non-retained, dirty-working-tree-tolerant run of the exact PERF008 matrix.

    Exists so an uncommitted harness fix (for example, a driver compile error) can be
    exercised end-to-end - full image build, all 4 canonical/control profile pairs,
    full-stack and steady-state-only JFR capture, correctness checks - before the harness
    is committed. Mirrors the `smoke` command already used by the sibling PERF006-D3/PERF004-A
    harnesses (see `runner/perf006d3.py:smoke()`): nothing is written under `results/` or any
    other persisted location, and the declared harness identity is HEAD when the tree is
    clean, or the `WORKTREE_PRECOMMIT` sentinel when dirty (matching
    `runner/perf001f.harness_revision()`). Retained reference evidence is produced only by
    `reference()`, which still requires an exact clean `--harness-revision` per
    `AGENTS.work/REPRODUCIBILITY.md`.
    """
    cfg = validate()
    harness_revision = worktree_harness_revision()
    cpu = first_cpu()
    tag = build_image(cfg)
    runtime = runtime_probe(tag, cpu)
    java_version_probe(tag, cpu)

    with tempfile.TemporaryDirectory(prefix="perf008-smoke-") as tmp:
        work = Path(tmp)
        paired = run_matrix(cfg, tag, cpu, work)

    print("PERF008_SMOKE_HARNESS_REVISION=" + harness_revision)
    print("PERF008_SMOKE_RUNTIME=" + runtime)
    print("PERF008_SMOKE_PAIRS=" + str(len(paired)))
    print("PERF008_SMOKE_EVIDENCE_UNITS=" + str(len(paired) * 2))
    print("PERF008_FULL_STACK_SUPPORT=PASS")
    print("PERF008_STEADY_STATE_CAPTURE=PASS")
    print("PERF008_CURRENT_MAIN_MATRIX=PASS")
    print("PERF008_CORRECTNESS=PASS")
    print("PERF008_SMOKE=PASS")
    print("PERF008_SMOKE_RETAINED=NO")
    print("PERF008_DIAGNOSTIC_CLAIM=NO")


def reference(harness_revision: str, output_dir: Path) -> None:
    cfg = validate()

    if output(["git", "rev-parse", "HEAD"]) != harness_revision:
        raise RuntimeError("exact harness revision mismatch")

    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires clean exact harness")

    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise RuntimeError("output directory already contains evidence")
        output_dir.rmdir()

    cpu = first_cpu()
    tag = build_image(cfg)
    runtime = runtime_probe(tag, cpu)
    java_version = java_version_probe(tag, cpu)

    with tempfile.TemporaryDirectory(prefix="perf008-") as tmp:
        work = Path(tmp)
        paired = run_matrix(cfg, tag, cpu, work)

    output_dir.mkdir(parents=True)

    raw = {
        "schema_version": 1,
        "perf_item": "PERF008",
        "slice": "PERF008",
        "harness_revision": harness_revision,
        "protos_revision": cfg["protos_revision"],
        "historical_protos_revision": cfg["historical_protos_revision"],
        "historical_evidence_references": cfg["historical_evidence"],
        "runtime": runtime,
        "java_version_probe": java_version,
        "toolchain": cfg["toolchain"],
        "host_identity": host_identity(),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "resource_limits": {
            "memory": "no explicit --memory limit set; host default applies",
            "cpu": "no CPU quota/period limit; pinned to one CPU via --cpuset-cpus",
            "network": "none (--network none)",
        },
        "operation_count": cfg["operation_count"],
        "warmup_iterations": cfg["warmup_iterations"],
        "steady_iterations": cfg["steady_iterations"],
        "execution_sample_period": cfg["execution_sample_period"],
        "stack_depth_limit": cfg["stack_depth_limit"],
        "jfr_recording_phase": cfg["jfr_recording_phase"],
        "diagnostic_only": True,
        "pairs": paired,
    }

    (output_dir / "raw.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = [
        "workload\tmode\texecution_samples\t"
        "continueAt_leaf_percent\tcontinueAt_leaf_count\tcontinueAt_any_depth_percent\t"
        "builder_any_depth_percent\tbuilder_co_occurs_with_continueAt_percent_of_builder\t"
        "jdk_deopts\ttruffle_deopts"
    ]

    for pair in paired:
        for mode in ("canonical", "control"):
            profile_payload = pair[mode]["profile"]
            samples = profile_payload["execution_samples"]
            continue_at = profile_payload["continue_at"]
            builder = profile_payload["builder"]
            rows.append(
                "\t".join([
                    pair["workload"],
                    mode,
                    str(samples["total"]),
                    str(continue_at["leaf_percent"]),
                    str(continue_at["leaf_count"]),
                    str(continue_at["any_depth_percent"]),
                    str(builder["any_depth_percent"]),
                    str(builder["co_occurs_with_continue_at_percent_of_builder"]),
                    str(profile_payload["deoptimizations"]["jdk_total"]),
                    str(profile_payload["deoptimizations"]["truffle_total"]),
                ])
            )

    (output_dir / "summary.tsv").write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    readme = [
        "# PERF008 steady-state full-stack JFR evidence",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Protos revision (current): `{cfg['protos_revision']}`",
        "- Historical Protos revision (PERF004-B2-D / PERF006-D3; not mixed with "
        f"current-revision measurements): `{cfg['historical_protos_revision']}`",
        f"- Runtime: `{runtime}`",
        f"- Java: `{java_version.splitlines()[0] if java_version else '<unknown>'}`",
        f"- GraalVM release: `{cfg['toolchain']['graalvm_release']}`",
        f"- Graal/Truffle components version: `{cfg['toolchain']['graal_truffle_version']}`",
        f"- Container image: `{cfg['toolchain']['container_image']}`",
        f"- CPU policy: cpuset-cpus=`{cpu}`; network disabled; no explicit memory limit.",
        "- N=10,000.",
        "- Warmup=20, steady=100.",
        "- JFR ExecutionSample period=10 ms.",
        "- JFR recording phase: **steady-state only** — `Recording.start()` immediately "
        "before the steady loop, `Recording.stop()` immediately after; bootstrap and "
        "warmup are excluded from the captured recording.",
        "- Stack depth limit: 32 bounded, leaf-first frames retained per "
        "`jdk.ExecutionSample`.",
        "- Diagnostic-only; no sole-cause claim; no Protos optimization applied.",
        "",
        "Canonical/control pairs use the identical PERF004-B2-C-approved operation "
        "replacement as `results/perf004-b2d`. This evidence does not supersede "
        "`results/perf004-b2d` or `results/perf006-d3`; it is a same-matrix, "
        "current-revision, steady-state-only, full-bounded-stack capture meant to be "
        "read alongside them without merging revisions into one comparison.",
        "",
        "See `raw.json` for the per-profile `continue_at` (leaf/any-depth share, "
        "callers, callees, ranked full paths, and marker co-occurrence with "
        "`Unsafe.putObject`, `FrameExtensionsUnsafe`, `ProtosObjectValue.readLocalSlot`, "
        "`ProtosActivation.lookup`, and `CallTarget`) and `builder` relationship "
        "sections, and `summary.tsv` for a flat per-workload overview.",
    ]

    (output_dir / "README.md").write_text(
        "\n".join(readme) + "\n",
        encoding="utf-8",
    )

    names = ["README.md", "raw.json", "summary.tsv"]
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(
            f"{sha256(output_dir / n)}  {n}"
            for n in names
        ) + "\n",
        encoding="utf-8",
    )

    print("PERF008_REFERENCE=PASS")
    print("PERF008_PAIRS=4")
    print("PERF008_EVIDENCE_UNITS=8")
    print("PERF008_FULL_STACK_SUPPORT=PASS")
    print("PERF008_STEADY_STATE_CAPTURE=PASS")
    print("PERF008_CURRENT_MAIN_MATRIX=PASS")
    print("PERF008_CORRECTNESS=PASS")
    print("PERF008_EVIDENCE_RETENTION=PASS")
    print("PERF008_DIAGNOSTIC_CLAIM=NO")
    print("PERF008_PROTOS_REPOSITORY_TOUCHED=NO")
    print("PERF008_NEXT_EVIDENCE_READY=YES")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("validate", "smoke", "reference"))
    ap.add_argument("--harness-revision")
    ap.add_argument("--output-dir")
    args = ap.parse_args()

    if args.command == "validate":
        validate()
        return

    if args.command == "smoke":
        smoke()
        return

    if not args.harness_revision or not args.output_dir:
        ap.error("reference requires --harness-revision and --output-dir")

    reference(args.harness_revision, Path(args.output_dir))


if __name__ == "__main__":
    main()
