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
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import shutil
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
WORK = ROOT / ".work"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_PERF001C_IDS = (
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
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def checked_output(command: list[str]) -> str:
    try:
        return run(command, capture=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        rendered = " ".join(command)
        stdout = (exc.stdout or "").strip()
        stderr = (exc.stderr or "").strip()
        details = [f"command failed with exit status {exc.returncode}: {rendered}"]
        if stdout:
            details.append(f"stdout:\n{stdout}")
        if stderr:
            details.append(f"stderr:\n{stderr}")
        raise RuntimeError("\n".join(details)) from exc


def normalize_architecture(value: str) -> str:
    aliases = {"x86_64": "amd64", "aarch64": "arm64"}
    value = value.strip().lower()
    return aliases.get(value, value)


def validate_revision(value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"expected an exact 40-character lowercase Git SHA, got {value!r}")
    return value


def runtime_config() -> dict[str, Any]:
    return load_json(CONFIG / "runtimes.json")


def protos_config() -> dict[str, Any]:
    return load_json(CONFIG / "protos.json")


def suite_config() -> dict[str, Any]:
    return load_json(CONFIG / "suite.json")


def selected_protos_revision(value: str | None) -> str:
    return validate_revision(value or str(protos_config()["pinned_revision"]))


def docker_run_prefix(cpuset: str | None) -> list[str]:
    command = ["docker", "run", "--rm", "--network", "none"]
    if cpuset:
        command += ["--cpuset-cpus", cpuset]
    return command


def last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def validate() -> None:
    runtimes = runtime_config()
    protos = protos_config()
    suite = suite_config()
    result_schema = load_json(ROOT / "schemas" / "result.schema.json")
    correctness_schema = load_json(ROOT / "schemas" / "correctness.schema.json")
    if runtimes.get("schema_version") != 1 or protos.get("schema_version") != 1:
        raise RuntimeError("unsupported harness configuration schema")
    if suite.get("schema_version") != 1:
        raise RuntimeError("unsupported PERF001-C suite schema")
    revision = validate_revision(str(protos["pinned_revision"]))
    if suite.get("protos_corpus_revision") != revision:
        raise RuntimeError("PERF001-C suite and Protos revision pin disagree")
    if protos.get("canonical_corpus") != "protos/benchmarks":
        raise RuntimeError("canonical Protos corpus path drift")
    protos_runtime = runtimes["runtimes"]["protos"]
    if protos_runtime.get("runtime_args") != ["-Xss64m"]:
        raise RuntimeError("PERF001-C Protos recursion stack policy drift")
    graal = protos_runtime["graalvm"]
    if graal.get("graal_truffle_line") != "24.0.0":
        raise RuntimeError("PERF001 Graal/Truffle compatibility line drift")
    if graal.get("base") != "ghcr.io/graalvm/jdk-community:22.0.0":
        raise RuntimeError("PERF001 GraalVM base drift")
    node = runtimes["runtimes"]["javascript"]
    if node.get("base") != "node:24.20.0-bookworm-slim":
        raise RuntimeError("PERF001-C Node base drift")
    if node.get("runtime_args") != ["--stack-size=32768"]:
        raise RuntimeError("PERF001-C Node recursion policy drift")
    if result_schema.get("title") != "Protos benchmark raw result":
        raise RuntimeError("unexpected timing result schema")
    if correctness_schema.get("title") != "Protos cross-language correctness result":
        raise RuntimeError("unexpected correctness result schema")
    if suite.get("classification") != "algorithm-equivalent":
        raise RuntimeError("PERF001-C suite must remain algorithm-equivalent")
    if suite.get("comparison_languages") != ["python", "javascript"]:
        raise RuntimeError("PERF001-C comparison-language set drift")
    entries = suite.get("benchmarks")
    if not isinstance(entries, list):
        raise RuntimeError("PERF001-C benchmark manifest is not a list")
    ids = tuple(str(entry.get("id")) for entry in entries)
    if ids != EXPECTED_PERF001C_IDS:
        raise RuntimeError(f"PERF001-C corpus manifest drift: {ids!r}")
    for entry in entries:
        if not entry.get("expected_stdout"):
            raise RuntimeError(f"missing expected output for {entry.get('id')}")
        if set(entry.get("implementations", {})) != {"python", "javascript"}:
            raise RuntimeError(f"incomplete cross-language mapping for {entry.get('id')}")
        for language, relative in entry["implementations"].items():
            path = ROOT / "workloads" / language / str(relative)
            if not path.is_file():
                raise RuntimeError(f"missing {language} implementation for {entry['id']}: {path}")
    print("HARNESS_CONFIG_VALIDATION: PASS")
    print("PERF001C_MANIFEST_VALIDATION: PASS")


def build(revision: str) -> None:
    cfg = runtime_config()["runtimes"]
    protos = protos_config()
    p = cfg["protos"]
    graal = p["graalvm"]
    print(f"Building Protos benchmark image from {revision}...")
    run([
        "docker", "build", "--pull",
        "--build-arg", f"BUILD_BASE={p['maven_build_image']}",
        "--build-arg", f"GRAAL_BASE={graal['base']}",
        "--build-arg", f"PROTOS_REPOSITORY={protos['repository']}",
        "--build-arg", f"PROTOS_REVISION={revision}",
        "-t", p["image"], "-f", "docker/protos/Dockerfile", ".",
    ])
    py = cfg["python"]
    print("Building Python comparison image...")
    run([
        "docker", "build", "--pull",
        "--build-arg", f"PYTHON_BASE={py['base']}",
        "-t", py["image"], "-f", "docker/python/Dockerfile", ".",
    ])
    js = cfg["javascript"]
    print("Building JavaScript comparison image...")
    run([
        "docker", "build", "--pull",
        "--build-arg", f"NODE_BASE={js['base']}",
        "-t", js["image"], "-f", "docker/node/Dockerfile", ".",
    ])
    print("DOCKER_PROTOS_BUILD: PASS")
    print("DOCKER_PYTHON_BUILD: PASS")
    print("DOCKER_JAVASCRIPT_BUILD: PASS")


def image_identity(image: str) -> dict[str, Any]:
    payload = json.loads(checked_output(["docker", "image", "inspect", image]))[0]
    return {"tag": image, "id": payload.get("Id", ""), "repo_digests": payload.get("RepoDigests") or []}


def host_inventory(cpuset: str | None) -> dict[str, Any]:
    cpu_model = ""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
                break
    memory_bytes = None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                memory_bytes = int(line.split()[1]) * 1024
                break
    return {
        "platform": platform.system().lower(),
        "architecture": normalize_architecture(platform.machine()),
        "kernel": platform.release(),
        "cpu_model": cpu_model,
        "cpu_count": os.cpu_count() or 1,
        "memory_bytes": memory_bytes,
        "cpuset": cpuset or "unrestricted",
        "docker_server_version": checked_output(["docker", "version", "--format", "{{.Server.Version}}"]),
    }


def current_harness_revision() -> str:
    try:
        head = checked_output(["git", "rev-parse", "HEAD"])
        if not SHA_RE.fullmatch(head):
            return "WORKTREE_PRECOMMIT"
        if checked_output(["git", "status", "--porcelain", "--untracked-files=all"]):
            return "WORKTREE_PRECOMMIT"
        return head
    except (RuntimeError, OSError):
        return "WORKTREE_PRECOMMIT"


def smoke(revision: str, cpuset: str | None) -> dict[str, Any]:
    cfg = runtime_config()["runtimes"]
    smoke_cfg = protos_config()["smoke"]
    expected = str(smoke_cfg["expected_stdout"])

    protos_out = checked_output(docker_run_prefix(cpuset) + [
        cfg["protos"]["image"], "-e", str(smoke_cfg["source"])
    ])
    if last_nonempty_line(protos_out) != expected:
        raise RuntimeError(f"Protos smoke mismatch: expected {expected!r}, got {protos_out!r}")

    corpus_path = f"/opt/protos/protos/benchmarks/{smoke_cfg['corpus_probe']}"
    checked_output(docker_run_prefix(cpuset) + [
        "--entrypoint", "/bin/sh", cfg["protos"]["image"], "-c", f"test -f {corpus_path}"
    ])

    python_out = checked_output(docker_run_prefix(cpuset) + [
        cfg["python"]["image"], "-c", "print(1 + 1)"
    ])
    if last_nonempty_line(python_out) != expected:
        raise RuntimeError(f"Python smoke mismatch: expected {expected!r}, got {python_out!r}")

    javascript_out = checked_output(docker_run_prefix(cpuset) + [
        cfg["javascript"]["image"], "-e", "console.log(1 + 1)"
    ])
    if last_nonempty_line(javascript_out) != expected:
        raise RuntimeError(
            f"JavaScript smoke mismatch: expected {expected!r}, got {javascript_out!r}"
        )

    payload = {
        "schema_version": 1,
        "purpose": "Harness correctness smoke; not a timing result",
        "protos_revision": revision,
        "harness_revision": current_harness_revision(),
        "source": str(smoke_cfg["source"]),
        "canonical_corpus_probe": str(smoke_cfg["corpus_probe"]),
        "expected_stdout": expected,
        "environment": host_inventory(cpuset),
        "images": {name: image_identity(runtime["image"]) for name, runtime in cfg.items()},
        "correctness": {
            "protos_cli": "PASS",
            "canonical_corpus_present": "PASS",
            "python_control": "PASS",
            "javascript_control": "PASS",
        },
    }
    WORK.mkdir(exist_ok=True)
    (WORK / "harness-smoke.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("PROTOS_CLI_SMOKE: PASS")
    print("CANONICAL_CORPUS_PROBE: PASS")
    print("PYTHON_CONTROL_SMOKE: PASS")
    print("JAVASCRIPT_CONTROL_SMOKE: PASS")
    print("SMOKE_CORRECTNESS: PASS")
    return payload


def workload_command(language: str, entry: dict[str, Any], cpuset: str | None) -> list[str]:
    cfg = runtime_config()["runtimes"]
    prefix = docker_run_prefix(cpuset)
    if language == "protos":
        return prefix + [
            cfg["protos"]["image"],
            f"/opt/protos/protos/benchmarks/{entry['protos']}",
        ]
    if language in ("python", "javascript"):
        relative = entry["implementations"][language]
        return prefix + [
            cfg[language]["image"],
            f"/opt/benchmark/workloads/{relative}",
        ]
    raise ValueError(f"unsupported benchmark language {language!r}")


def case_log_path(entry_id: str, language: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "__", entry_id)
    safe_language = re.sub(r"[^A-Za-z0-9_.-]+", "_", language)
    return WORK / "perf001c-cases" / safe_id / f"{safe_language}.log"


def write_case_log(
    path: Path,
    command: list[str],
    completed: subprocess.CompletedProcess[str],
    *,
    expected: str,
    observed: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"command={' '.join(command)}",
        f"exit_status={completed.returncode}",
        f"expected_stdout={expected}",
        f"observed_stdout={observed}",
        "",
        "--- stdout ---",
        completed.stdout or "",
        "",
        "--- stderr ---",
        completed.stderr or "",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_correctness_case(language: str, entry: dict[str, Any], cpuset: str | None) -> dict[str, str]:
    command = workload_command(language, entry, cpuset)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = completed.stdout or ""
    observed = last_nonempty_line(output)
    expected = str(entry["expected_stdout"])
    log_path = case_log_path(str(entry["id"]), language)
    write_case_log(
        log_path,
        command,
        completed,
        expected=expected,
        observed=observed,
    )
    relative_log = log_path.relative_to(ROOT)
    if completed.returncode != 0:
        print(
            f"CORRECTNESS FAIL {entry['id']} [{language}] exit={completed.returncode}",
            file=sys.stderr,
        )
        print(f"CASE_LOG={relative_log}", file=sys.stderr)
        raise RuntimeError(
            f"{entry['id']} [{language}] exited with status {completed.returncode}; "
            f"full log retained at {relative_log}"
        )
    if observed != expected:
        print(
            f"CORRECTNESS FAIL {entry['id']} [{language}] expected={expected!r} observed={observed!r}",
            file=sys.stderr,
        )
        print(f"CASE_LOG={relative_log}", file=sys.stderr)
        raise RuntimeError(
            f"{entry['id']} [{language}] correctness mismatch; full log retained at {relative_log}"
        )
    print(f"CORRECTNESS PASS {entry['id']} [{language}] -> {observed}")
    return {
        "status": "PASS",
        "expected_stdout": expected,
        "observed_stdout": observed,
        "log": str(relative_log),
    }


def correctness(revision: str, cpuset: str | None) -> dict[str, Any]:
    cfg = runtime_config()["runtimes"]
    entries = suite_config()["benchmarks"]
    case_root = WORK / "perf001c-cases"
    if case_root.exists():
        shutil.rmtree(case_root)
    results: list[dict[str, Any]] = []
    for entry in entries:
        cases: dict[str, dict[str, str]] = {}
        for language in ("protos", "python", "javascript"):
            cases[language] = run_correctness_case(language, entry, cpuset)
        results.append({
            "id": entry["id"],
            "protos": entry["protos"],
            "equivalence": entry["equivalence"],
            "cases": cases,
        })
    payload = {
        "schema_version": 1,
        "purpose": "PERF001-C cross-language corpus correctness; not a timing result",
        "protos_revision": revision,
        "harness_revision": current_harness_revision(),
        "environment": host_inventory(cpuset),
        "images": {name: image_identity(runtime["image"]) for name, runtime in cfg.items()},
        "benchmarks": results,
    }
    WORK.mkdir(exist_ok=True)
    (WORK / "perf001c-correctness.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(f"CORPUS_WORKLOADS_VALIDATED: {len(results)}")
    print(f"CORRECTNESS_CASES_VALIDATED: {len(results) * 3}")
    print("CROSS_LANGUAGE_CORRECTNESS: PASS")
    return payload


def inventory(revision: str, cpuset: str | None) -> dict[str, Any]:
    cfg = runtime_config()["runtimes"]
    return {
        "schema_version": 1,
        "protos_revision": revision,
        "harness_revision": current_harness_revision(),
        "environment": host_inventory(cpuset),
        "images": {name: image_identity(runtime["image"]) for name, runtime in cfg.items()},
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Protos benchmark harness")
    p.add_argument(
        "command",
        choices=["validate", "build", "smoke", "correctness", "inventory", "all"],
    )
    p.add_argument("--protos-revision")
    p.add_argument("--cpuset")
    p.add_argument("--output")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate":
            validate()
            return 0
        revision = selected_protos_revision(args.protos_revision)
        if args.command == "build":
            validate()
            build(revision)
            return 0
        if args.command == "smoke":
            validate()
            smoke(revision, args.cpuset)
            return 0
        if args.command == "correctness":
            validate()
            correctness(revision, args.cpuset)
            return 0
        if args.command == "inventory":
            validate()
            payload = inventory(revision, args.cpuset)
            encoded = json.dumps(payload, indent=2) + "\n"
            if args.output:
                Path(args.output).write_text(encoded, encoding="utf-8")
            else:
                print(encoded, end="")
            return 0
        if args.command == "all":
            validate()
            build(revision)
            smoke(revision, args.cpuset)
            correctness(revision, args.cpuset)
            return 0
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"benchmark harness error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
