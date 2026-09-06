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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
WORK = ROOT / ".work"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


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
    schema = load_json(ROOT / "schemas" / "result.schema.json")
    if runtimes.get("schema_version") != 1 or protos.get("schema_version") != 1:
        raise RuntimeError("unsupported harness configuration schema")
    validate_revision(str(protos["pinned_revision"]))
    if protos.get("canonical_corpus") != "protos/benchmarks":
        raise RuntimeError("canonical Protos corpus path drift")
    graal = runtimes["runtimes"]["protos"]["graalvm"]
    if graal.get("graal_truffle_line") != "24.0.0":
        raise RuntimeError("PERF001-B Graal/Truffle compatibility line drift")
    if graal.get("base") != "ghcr.io/graalvm/jdk-community:22.0.0":
        raise RuntimeError("PERF001-B GraalVM base drift")
    if schema.get("title") != "Protos benchmark raw result":
        raise RuntimeError("unexpected result schema")
    print("HARNESS_CONFIG_VALIDATION: PASS")


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
    print("Building Python control image...")
    run([
        "docker", "build", "--pull",
        "--build-arg", f"PYTHON_BASE={py['base']}",
        "-t", py["image"], "-f", "docker/python/Dockerfile", ".",
    ])
    print("DOCKER_PROTOS_BUILD: PASS")
    print("DOCKER_PYTHON_BUILD: PASS")


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
        value = checked_output(["git", "rev-parse", "HEAD"])
        return value if SHA_RE.fullmatch(value) else "WORKTREE_PRECOMMIT"
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
        cfg["python"]["image"], "/opt/benchmark/smoke.py"
    ])
    if last_nonempty_line(python_out) != expected:
        raise RuntimeError(f"Python smoke mismatch: expected {expected!r}, got {python_out!r}")

    payload = {
        "schema_version": 1,
        "purpose": "PERF001-B harness correctness smoke; not a timing result",
        "protos_revision": revision,
        "harness_revision": current_harness_revision(),
        "source": str(smoke_cfg["source"]),
        "canonical_corpus_probe": str(smoke_cfg["corpus_probe"]),
        "expected_stdout": expected,
        "environment": host_inventory(cpuset),
        "images": {
            "protos": image_identity(cfg["protos"]["image"]),
            "python": image_identity(cfg["python"]["image"]),
        },
        "correctness": {
            "protos_cli": "PASS",
            "canonical_corpus_present": "PASS",
            "python_control": "PASS",
        },
    }
    WORK.mkdir(exist_ok=True)
    (WORK / "perf001b-smoke.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("PROTOS_CLI_SMOKE: PASS")
    print("CANONICAL_CORPUS_PROBE: PASS")
    print("PYTHON_CONTROL_SMOKE: PASS")
    print("SMOKE_CORRECTNESS: PASS")
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
    p.add_argument("command", choices=["validate", "build", "smoke", "inventory", "all"])
    p.add_argument("--protos-revision")
    p.add_argument("--cpuset")
    p.add_argument("--output")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate":
            validate(); return 0
        revision = selected_protos_revision(args.protos_revision)
        if args.command == "build":
            validate(); build(revision); return 0
        if args.command == "smoke":
            validate(); smoke(revision, args.cpuset); return 0
        if args.command == "inventory":
            validate(); payload = inventory(revision, args.cpuset)
            encoded = json.dumps(payload, indent=2) + "\n"
            if args.output:
                Path(args.output).write_text(encoded, encoding="utf-8")
            else:
                print(encoded, end="")
            return 0
        if args.command == "all":
            validate(); build(revision); smoke(revision, args.cpuset); return 0
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"benchmark harness error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
