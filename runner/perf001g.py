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
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf001g.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
D_HARNESS = "0a406373c497df1173ff26a3ed4fcada015e0879"
E_HARNESS = "280173d743b2ed838a89be0ad930b20828d89558"
F_H3_HARNESS = "b8a9eeca85c241f544512a02a6fa29d935f240ef"
F_H4_EVIDENCE = "f34e37da11f209aa9f9ea84465822c3362fc4da0"
RETAINED_PATHS = ("results/perf001-d", "results/perf001-e", "results/perf001-f")
EXPECTED_D_CASES = 44
EXPECTED_E_CASES = 18
EXPECTED_F_CONFIGS = 12


def run(command: list[str], *, cwd: Path = ROOT, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def output(command: list[str], *, cwd: Path = ROOT) -> str:
    try:
        return run(command, cwd=cwd, capture=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        rendered = " ".join(command)
        details = [f"command failed rc={exc.returncode}: {rendered}"]
        if exc.stdout:
            details.append("stdout:\n" + exc.stdout[-4000:])
        if exc.stderr:
            details.append("stderr:\n" + exc.stderr[-4000:])
        raise RuntimeError("\n".join(details)) from exc


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def last_nonempty(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def require_sha(value: str, label: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise RuntimeError(f"{label} is not an exact lowercase 40-character Git SHA: {value!r}")
    return value


def git(*args: str, cwd: Path = ROOT, capture: bool = True) -> str:
    command = ["git", *args]
    if capture:
        return output(command, cwd=cwd)
    run(command, cwd=cwd)
    return ""


def validate_config() -> dict[str, Any]:
    cfg = load(CONFIG)
    assert cfg["schema_version"] == 1
    assert cfg["perf_item"] == "PERF001"
    assert cfg["slice"] == "PERF001-G"
    assert cfg["phase"] == "reproducibility-harness-ready"
    assert cfg["methodology"] == "bounded_exact_pin_reproducibility_replay"
    assert cfg["methodology_approval"] == "project-owner-approved-2026-09-10"
    assert cfg["timing_values_are_pass_fail_threshold"] is False
    pins = cfg["historical_harnesses"]
    assert pins == {
        "perf001d": D_HARNESS,
        "perf001e": E_HARNESS,
        "perf001f_h3": F_H3_HARNESS,
        "perf001f_h4_evidence": F_H4_EVIDENCE,
    }
    expected = cfg["expected_replay"]
    assert expected["perf001d_correctness_cases"] == EXPECTED_D_CASES
    assert expected["perf001e_correctness_cases"] == EXPECTED_E_CASES
    assert expected["perf001f_reference_smoke_configurations"] == EXPECTED_F_CONFIGS
    assert expected["perf001f_startup_samples_per_configuration"] == 2
    assert expected["perf001f_warmup_iterations_per_configuration"] == 2
    assert expected["perf001f_steady_samples_per_configuration"] == 2
    assert tuple(cfg["retained_evidence_paths"]) == RETAINED_PATHS
    report = cfg["report_policy"]
    assert report["aggregate_existing_summaries_as_separate_sections"] is True
    assert report["cross_generation_normalization"] is False
    assert report["cross_generation_performance_ranking"] is False
    assert report["replay_timings_retained"] is False
    return cfg


def ensure_commit(sha: str) -> None:
    require_sha(sha, "commit")
    try:
        run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture=True)
    except subprocess.CalledProcessError:
        run(["git", "fetch", "origin", sha])
        run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture=True)


def verify_retained_evidence_identity() -> dict[str, str]:
    ensure_commit(F_H4_EVIDENCE)
    identities: dict[str, str] = {}
    for path in RETAINED_PATHS:
        retained = git("rev-parse", f"{F_H4_EVIDENCE}:{path}")
        current = git("rev-parse", f"HEAD:{path}")
        if retained != current:
            raise RuntimeError(
                f"retained evidence drift for {path}: {current} != F H4 authority {retained}"
            )
        identities[path] = retained
    return identities


def validate_historical_pins() -> None:
    d = load(ROOT / "config" / "perf001d.json")
    e = load(ROOT / "config" / "perf001e.json")
    f = load(ROOT / "config" / "perf001f.json")
    d_revisions = {entry["label"]: entry["revision"] for entry in d["revisions"]}
    assert d_revisions == {
        "pre-perf002": "8f363d0146164f99e72210eb44667f4efb7b88e7",
        "post-perf002": "3c93912a5579326374782a43527fbb51046f8f91",
    }
    assert e["protos_revision"] == "86b35d8bb2d7ab2ad54bc2947e1bf7fbff1fca15"
    assert f["protos_revision"] == "0372a58addc63f305c911811659edd9b2b508420"
    assert f["corpus_publication_revision"] == "faa1714523d68650447047a05d184ab17a747c06"
    assert f["reference_gate_satisfied_by"] == "a08844c7ba59f4a213e4d318bcf3bee32393c2a9"
    assert f["runtime_blocker_239_fixed_by"] == "0372a58addc63f305c911811659edd9b2b508420"


def validate_repository() -> dict[str, str]:
    validate_config()
    validate_historical_pins()
    for sha in (D_HARNESS, E_HARNESS, F_H3_HARNESS, F_H4_EVIDENCE):
        ensure_commit(sha)
        run(["git", "merge-base", "--is-ancestor", sha, "HEAD"], capture=True)
    identities = verify_retained_evidence_identity()
    print("PERF001G_CONFIG_VALIDATION: PASS")
    print("PERF001G_HISTORICAL_PIN_VALIDATION: PASS")
    print("PERF001G_RETAINED_EVIDENCE_IDENTITY: PASS")
    print("PERF001G_REFERENCE_TIMING_REPLACEMENT: NO")
    return identities


def first_allowed_cpu() -> str:
    status = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Cpus_allowed_list:\s*(.+)$", status, re.M)
    if not match:
        raise RuntimeError("cannot determine Cpus_allowed_list")
    return match.group(1).strip().split(",")[0].split("-")[0]


def image_identity(tag: str) -> dict[str, Any]:
    payload = json.loads(output(["docker", "image", "inspect", tag]))[0]
    return {"tag": tag, "id": payload.get("Id", ""), "repo_digests": payload.get("RepoDigests") or []}


def host_inventory(cpu: str) -> dict[str, Any]:
    cpu_model = ""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
                break
    return {
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "cpu_model": cpu_model,
        "cpu_count": os.cpu_count() or 1,
        "cpuset": cpu,
        "docker_server_version": output(["docker", "version", "--format", "{{.Server.Version}}"]),
    }


@contextlib.contextmanager
def detached_worktree(sha: str, parent: Path, name: str) -> Iterator[Path]:
    ensure_commit(sha)
    target = parent / name
    run(["git", "worktree", "add", "--detach", str(target), sha])
    try:
        yield target
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(target)], cwd=ROOT, check=False)


def docker_checked(command: list[str]) -> str:
    return output(command)


def replay_d(worktree: Path, cpu: str) -> tuple[int, list[dict[str, Any]]]:
    cfg = load(worktree / "config" / "perf001d.json")
    images: list[dict[str, Any]] = []
    built: dict[str, str] = {}
    for entry in cfg["revisions"]:
        label = entry["label"]
        revision = entry["revision"]
        tag = f"protos-benchmarks-perf001g-d-{label}:{revision[:12]}"
        print(f"PERF001G_D_BUILD_BEGIN label={label} revision={revision}")
        run([
            "docker", "build",
            "--build-arg", f"BUILD_BASE={cfg['build_base']}",
            "--build-arg", f"GRAAL_BASE={cfg['graal_base']}",
            "--build-arg", f"PROTOS_REPOSITORY={cfg['protos_repository']}",
            "--build-arg", f"PROTOS_REVISION={revision}",
            "--build-arg", f"TRUFFLE_RUNTIME_VERSION={cfg['truffle_runtime_version']}",
            "-t", tag,
            "-f", str(worktree / "docker/protos-perf001d/Dockerfile"),
            str(worktree / "docker/protos-perf001d"),
        ])
        klass = docker_checked([
            "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
            "--entrypoint", "java", tag,
            "--enable-native-access=ALL-UNNAMED",
            "-cp", "/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar",
            "com.guillermomolina.protos.cli.RuntimeProbe",
        ])
        if "HotSpotTruffleRuntime" not in klass:
            raise RuntimeError(f"PERF001-D optimizing runtime check failed for {label}: {klass}")
        built[label] = tag
        images.append(image_identity(tag))
        print(f"PERF001G_D_BUILD_PASS label={label}")

    count = 0
    for workload in cfg["workloads"]:
        for mode in ("interpreter", "truffle"):
            props = list(cfg["timing_modes"][mode])
            for entry in cfg["revisions"]:
                label = entry["label"]
                tag = built[label]
                actual = docker_checked([
                    "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
                    "--entrypoint", "java", tag,
                    f"-Xss{cfg['stack']}", "--enable-native-access=ALL-UNNAMED",
                    *props,
                    "-cp", "/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar",
                    "com.guillermomolina.protos.cli.DiagnosticEval",
                    f"/opt/protos/{workload['source']}",
                ])
                observed = last_nonempty(actual)
                expected = str(workload["expected_stdout"])
                if observed != expected:
                    raise RuntimeError(
                        f"PERF001-D correctness mismatch label={label} mode={mode} "
                        f"workload={workload['id']} expected={expected} observed={observed}"
                    )
                count += 1
                print(f"PERF001G_D_CASE_PASS {count}/{EXPECTED_D_CASES} label={label} mode={mode} workload={workload['id']}")
    if count != EXPECTED_D_CASES:
        raise RuntimeError(f"PERF001-D replay count mismatch: {count} != {EXPECTED_D_CASES}")
    return count, images


def replay_e(worktree: Path, cpu: str) -> tuple[int, list[dict[str, Any]]]:
    cfg = load(worktree / "config" / "perf001e.json")
    protos_tag = f"protos-benchmarks-perf001g-e-protos:{cfg['protos_revision'][:12]}"
    python_tag = f"protos-benchmarks-perf001g-e-python:{cfg['protos_revision'][:12]}"
    node_tag = f"protos-benchmarks-perf001g-e-node:{cfg['protos_revision'][:12]}"
    print("PERF001G_E_BUILD_BEGIN")
    run([
        "docker", "build",
        "--build-arg", f"BUILD_BASE={cfg['build_base']}",
        "--build-arg", f"GRAAL_BASE={cfg['graal_base']}",
        "--build-arg", f"PROTOS_REVISION={cfg['protos_revision']}",
        "--build-arg", f"TRUFFLE_RUNTIME_VERSION={cfg['truffle_runtime_version']}",
        "-t", protos_tag,
        "-f", str(worktree / "docker/protos-perf001e/Dockerfile"),
        str(worktree / "docker/protos-perf001e"),
    ])
    run([
        "docker", "build", "--build-arg", f"PYTHON_BASE={cfg['python_base']}",
        "-t", python_tag, "-f", str(worktree / "docker/python-perf001e/Dockerfile"), str(worktree),
    ])
    run([
        "docker", "build", "--build-arg", f"NODE_BASE={cfg['node_base']}",
        "-t", node_tag, "-f", str(worktree / "docker/node-perf001e/Dockerfile"), str(worktree),
    ])
    klass = docker_checked([
        "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
        "--entrypoint", "java", protos_tag,
        "--enable-native-access=ALL-UNNAMED",
        "-cp", "/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar",
        "com.guillermomolina.protos.cli.RuntimeProbe",
    ])
    if "HotSpotTruffleRuntime" not in klass:
        raise RuntimeError(f"PERF001-E optimizing runtime check failed: {klass}")
    print("PERF001G_E_BUILD_PASS")

    count = 0
    props = [
        "-Dpolyglot.engine.AllowExperimentalOptions=true",
        "-Dpolyglot.engine.BackgroundCompilation=false",
    ]
    for workload in cfg["workloads"]:
        expected = str(workload["expected"])
        protos_out = docker_checked([
            "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
            "--entrypoint", "java", protos_tag,
            f"-Xss{cfg['protos_stack']}", "--enable-native-access=ALL-UNNAMED",
            *props,
            "-cp", "/opt/diag:/opt/truffle-runtime/*:/opt/protos/protos.jar",
            "com.guillermomolina.protos.cli.DiagnosticEval",
            f"/opt/protos/{workload['protos']}",
        ])
        if last_nonempty(protos_out) != expected:
            raise RuntimeError(f"PERF001-E Protos mismatch workload={workload['id']}")
        count += 1
        py_path = "/opt/benchmark/workloads/" + str(workload["py"]).removeprefix("workloads/python/")
        py_out = docker_checked([
            "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
            python_tag, py_path,
        ])
        if last_nonempty(py_out) != expected:
            raise RuntimeError(f"PERF001-E Python mismatch workload={workload['id']}")
        count += 1
        js_path = "/opt/benchmark/workloads/" + str(workload["js"]).removeprefix("workloads/javascript/")
        js_out = docker_checked([
            "docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu,
            node_tag, js_path,
        ])
        if last_nonempty(js_out) != expected:
            raise RuntimeError(f"PERF001-E JavaScript mismatch workload={workload['id']}")
        count += 1
        print(f"PERF001G_E_WORKLOAD_PASS workload={workload['id']} cumulative={count}/{EXPECTED_E_CASES}")
    if count != EXPECTED_E_CASES:
        raise RuntimeError(f"PERF001-E replay count mismatch: {count} != {EXPECTED_E_CASES}")
    return count, [image_identity(protos_tag), image_identity(python_tag), image_identity(node_tag)]


def replay_f(worktree: Path) -> tuple[int, dict[str, Any] | None]:
    print("PERF001G_F_H3_SMOKE_BEGIN")
    completed = subprocess.run(
        ["python3", "runner/perf001f_reference.py", "--smoke"],
        cwd=worktree,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"PERF001-F exact H3 smoke failed rc={completed.returncode}")
    metadata_path = worktree / ".work/perf001f/reference-smoke/run-metadata.json"
    metadata: dict[str, Any] | None = None
    if metadata_path.is_file():
        raw = load(metadata_path)
        metadata = {
            "harness_revision": raw.get("harness_revision"),
            "protos_revision": raw.get("protos_revision"),
            "runtime": raw.get("runtime"),
            "environment": raw.get("environment"),
            "topology": raw.get("topology"),
        }
    print(f"PERF001G_F_H3_SMOKE_PASS configurations={EXPECTED_F_CONFIGS} policy=2/2/2 retained=NO")
    return EXPECTED_F_CONFIGS, metadata


def strip_title(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).rstrip() + "\n"


def write_manifest(directory: Path, names: list[str]) -> None:
    rows = []
    for name in names:
        digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        rows.append(f"{digest}  {name}")
    (directory / "MANIFEST.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def generate_baseline_report(out: Path, payload: dict[str, Any]) -> None:
    sections = []
    for label, path in (
        ("PERF001-D — Protos pre/post PERF002", ROOT / "results/perf001-d/summary.md"),
        ("PERF001-E — Sequential collections cross-language", ROOT / "results/perf001-e/summary.md"),
        ("PERF001-F — Future/P/Actor focused concurrency", ROOT / "results/perf001-f/summary.md"),
    ):
        sections.append(f"## {label}\n\nSource authority: `{path.relative_to(ROOT)}`.\n\n" + strip_title(path.read_text(encoding="utf-8")))
    report = f"""# PERF001 baseline report\n\nStatus: REPRODUCIBILITY PASS\n\nThis report closes the PERF001-G reporting question using the owner-approved bounded exact-pin replay. It does **not** create replacement timing samples or compare incompatible benchmark generations. Timing values below are derived views of the already-retained PERF001-D/E/F evidence and remain scoped to their exact historical revisions and environments.\n\n## Reproducibility gate\n\n- PERF001-D exact historical correctness replay: `{payload['replay']['perf001d']['cases']}/{EXPECTED_D_CASES}` PASS.\n- PERF001-E exact historical correctness replay: `{payload['replay']['perf001e']['cases']}/{EXPECTED_E_CASES}` PASS.\n- PERF001-F exact H3 non-retained smoke: `{payload['replay']['perf001f']['configurations']}/{EXPECTED_F_CONFIGS}` PASS with `2 startup / 2 warmup / 2 steady`; replay timings retained: **NO**.\n- Retained D/E/F result subtree identity against companion evidence commit `{F_H4_EVIDENCE}`: PASS.\n- Timing drift threshold: **NONE**; timing values are observations, not reproducibility pass/fail criteria.\n\n## Provenance\n\n- PERF001-D harness: `{D_HARNESS}`.\n- PERF001-E harness: `{E_HARNESS}`.\n- PERF001-F H3 harness: `{F_H3_HARNESS}`.\n- PERF001-F H4 / D+E+F retained evidence authority: `{F_H4_EVIDENCE}`.\n- PERF001-G harness: `{payload['harness_revision']}`.\n\n""" + "\n".join(sections)
    (out / "baseline.md").write_text(report, encoding="utf-8")


def execute(harness_revision: str, output_dir: Path) -> None:
    require_sha(harness_revision, "PERF001-G harness revision")
    head = git("rev-parse", "HEAD")
    if head != harness_revision:
        raise RuntimeError(f"exact harness gate failed: HEAD={head} requested={harness_revision}")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("PERF001-G retained replay requires a clean exact harness worktree")
    identities = validate_repository()
    for executable in ("git", "docker", "python3"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"required executable not found: {executable}")
    cpu = first_allowed_cpu()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="protos-perf001g-") as raw_tmp:
        temp = Path(raw_tmp)
        with detached_worktree(D_HARNESS, temp, "d") as d_wt:
            d_cases, d_images = replay_d(d_wt, cpu)
        with detached_worktree(E_HARNESS, temp, "e") as e_wt:
            e_cases, e_images = replay_e(e_wt, cpu)
        with detached_worktree(F_H3_HARNESS, temp, "f") as f_wt:
            f_configs, f_metadata = replay_f(f_wt)

    payload = {
        "schema_version": 1,
        "perf_item": "PERF001",
        "slice": "PERF001-G",
        "methodology": "bounded_exact_pin_reproducibility_replay",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "harness_revision": harness_revision,
        "retained_evidence_authority": F_H4_EVIDENCE,
        "timing_values_are_pass_fail_threshold": False,
        "replacement_timing_samples_retained": False,
        "retained_subtree_identity": identities,
        "host": host_inventory(cpu),
        "replay": {
            "perf001d": {"harness_revision": D_HARNESS, "cases": d_cases, "expected_cases": EXPECTED_D_CASES, "status": "PASS", "images": d_images},
            "perf001e": {"harness_revision": E_HARNESS, "cases": e_cases, "expected_cases": EXPECTED_E_CASES, "status": "PASS", "images": e_images},
            "perf001f": {"harness_revision": F_H3_HARNESS, "configurations": f_configs, "expected_configurations": EXPECTED_F_CONFIGS, "policy": "2/2/2 non-retained smoke", "status": "PASS", "metadata": f_metadata},
        },
    }
    (output_dir / "reproduction.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    generate_baseline_report(output_dir, payload)
    write_manifest(output_dir, ["reproduction.json", "baseline.md"])
    print("PERF001G_REPRODUCIBILITY: PASS")
    print(f"PERF001G_D_CORRECTNESS: PASS {d_cases}/{EXPECTED_D_CASES}")
    print(f"PERF001G_E_CORRECTNESS: PASS {e_cases}/{EXPECTED_E_CASES}")
    print(f"PERF001G_F_H3_SMOKE: PASS {f_configs}/{EXPECTED_F_CONFIGS} policy=2/2/2 retained=NO")
    print("PERF001G_REPLACEMENT_TIMING_EVIDENCE: NO")
    print(f"OUTPUT_DIR={output_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PERF001-G bounded exact-pin reproducibility controller")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate G methodology pins and retained evidence identity without Docker replay")
    run_parser = sub.add_parser("run", help="execute the approved exact-pin reproducibility replay")
    run_parser.add_argument("--harness-revision", required=True)
    run_parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        validate_repository()
    else:
        execute(args.harness_revision, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
