#!/usr/bin/env python3
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

import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
WORK = ROOT / ".work"
AB_ROOT = WORK / "protos-ab"
STATE = WORK / "truffle-prepare"

PROTOS_WORKSPACE = Path("/workspaces/protos")
PROTOS_REMOTE = "https://github.com/guillermomolina/protos.git"

VARIANTS = (
    (
        "0.3.128",
        "f0791896c3c022a747b4d47af629227da58acfab",
        "0.3.128-SNAPSHOT",
    ),
    (
        "0.3.129",
        "6e9dfd5aa2132adedeea43f75263f4cd264a6e8a",
        "0.3.129-SNAPSHOT",
    ),
)

NATIVE_BINARY_SHA256 = {
    "protos": "8b3b451e3bf90c7af8a87c210d210e8136166ca2cfc36df7bfba6a3ca1d30e99",
    "js": "5d3ec6dfdbee0da72d31b9358916194894c58ad73b2543d5e0e44e01ec62d75d",
    "python": "0149d9d967e6bef020a33dea6b73d5f3764eb3b5f085f31e5a3b1811e78c354f",
}


def run(
    *command: str,
    cwd: Path | None = None,
    capture: bool = False,
) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )

    return result.stdout.strip() if capture else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()

    for item in sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file()
    ):
        digest.update(
            str(item.relative_to(path)).encode()
        )
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")

    return digest.hexdigest()


def require_tools() -> None:
    tools = (
        "git",
        "java",
        "mvn",
        "curl",
        "unzip",
        "tar",
        "taskset",
    )

    missing = [
        tool
        for tool in tools
        if shutil.which(tool) is None
    ]

    if missing:
        raise RuntimeError(
            "missing required tools: "
            + ", ".join(missing)
        )


def project_version(repo: Path) -> str:
    root = ET.parse(repo / "pom.xml").getroot()
    namespace = ""

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    version = root.findtext(
        f"{namespace}version",
        "",
    ).strip()

    if not version:
        raise RuntimeError(
            f"cannot resolve project version in {repo}"
        )

    return version


def git_capture(
    repo: Path,
    *arguments: str,
) -> str:
    return run(
        "git",
        "-C",
        str(repo),
        *arguments,
        capture=True,
    )


def ensure_checkout(
    name: str,
    revision: str,
    expected_version: str,
) -> Path:
    repo = AB_ROOT / name

    if not (repo / ".git").exists():
        if repo.exists():
            shutil.rmtree(repo)

        repo.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        print(
            f"checkout={name} action=clone",
            flush=True,
        )

        run(
            "git",
            "clone",
            "-q",
            PROTOS_REMOTE,
            str(repo),
        )

    dirty = git_capture(
        repo,
        "status",
        "--porcelain",
        "--untracked-files=no",
    )

    if dirty:
        raise RuntimeError(
            f"managed checkout has tracked changes: "
            f"{repo}\n{dirty}"
        )

    present = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "cat-file",
            "-e",
            f"{revision}^{{commit}}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if present.returncode != 0:
        print(
            f"checkout={name} action=fetch",
            flush=True,
        )

        run(
            "git",
            "-C",
            str(repo),
            "fetch",
            "-q",
            "origin",
            revision,
        )

    current = git_capture(
        repo,
        "rev-parse",
        "HEAD",
    )

    if current != revision:
        print(
            f"checkout={name} action=checkout",
            flush=True,
        )

        run(
            "git",
            "-C",
            str(repo),
            "checkout",
            "-q",
            "--detach",
            revision,
        )
    else:
        print(
            f"checkout={name} action=reuse",
            flush=True,
        )

    actual_revision = git_capture(
        repo,
        "rev-parse",
        "HEAD",
    )

    if actual_revision != revision:
        raise RuntimeError(
            f"{name} revision mismatch: "
            f"expected {revision}, got {actual_revision}"
        )

    actual_version = project_version(repo)

    if actual_version != expected_version:
        raise RuntimeError(
            f"{name} version mismatch: "
            f"expected {expected_version}, "
            f"got {actual_version}"
        )

    return repo


def ensure_jvm_artifact(
    repo: Path,
    revision: str,
    version: str,
) -> Path:
    jar = (
        Path.home()
        / ".m2"
        / "repository"
        / "com"
        / "guillermomolina"
        / "protos"
        / version
        / f"protos-{version}.jar"
    )

    stamp = STATE / f"jvm-{version}.json"

    if jar.is_file() and stamp.is_file():
        state = json.loads(
            stamp.read_text(encoding="utf-8")
        )

        if (
            state.get("revision") == revision
            and state.get("version") == version
            and state.get("jar_sha256")
            == sha256_file(jar)
        ):
            print(
                f"jvm_artifact={version} action=reuse",
                flush=True,
            )
            return jar

    print(
        f"jvm_artifact={version} action=install",
        flush=True,
    )

    run(
        "mvn",
        "-q",
        "-f",
        str(repo / "pom.xml"),
        "-DskipTests",
        "install",
        cwd=ROOT,
    )

    if not jar.is_file():
        raise RuntimeError(
            f"Maven install did not produce {jar}"
        )

    STATE.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp.write_text(
        json.dumps(
            {
                "revision": revision,
                "version": version,
                "jar_sha256": sha256_file(jar),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return jar


def ensure_ab_variant(
    repo: Path,
    revision: str,
) -> None:
    stamp = STATE / f"ab-{revision}.json"
    classes = repo / "target" / "classes"
    classpath = (
        AB_ROOT
        / "classpath"
        / f"{revision}.txt"
    )

    if (
        classes.is_dir()
        and classpath.is_file()
        and stamp.is_file()
    ):
        state = json.loads(
            stamp.read_text(encoding="utf-8")
        )

        if state.get("revision") == revision:
            print(
                f"jvm_ab_variant={revision[:12]} "
                "action=reuse",
                flush=True,
            )
            return

    print(
        f"jvm_ab_variant={revision[:12]} "
        "action=prepare",
        flush=True,
    )

    run(
        "mvn",
        "-q",
        "-f",
        str(repo / "pom.xml"),
        "-DskipTests",
        "compile",
        cwd=ROOT,
    )

    classpath.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    run(
        "mvn",
        "-q",
        "-f",
        str(repo / "pom.xml"),
        "dependency:build-classpath",
        f"-Dmdep.outputFile={classpath}",
        cwd=ROOT,
    )

    if not classes.is_dir():
        raise RuntimeError(
            f"A/B classes missing after compile: {classes}"
        )

    if (
        not classpath.is_file()
        or not classpath.read_text(
            encoding="utf-8"
        ).strip()
    ):
        raise RuntimeError(
            f"A/B classpath missing: {classpath}"
        )

    STATE.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp.write_text(
        json.dumps(
            {"revision": revision},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def verify_core(
    baseline_repo: Path,
) -> str:
    baseline = sha256_tree(
        baseline_repo
        / "protos"
        / "lib"
        / "core"
    )

    current_core = (
        PROTOS_WORKSPACE
        / "protos"
        / "lib"
        / "core"
    )

    if not current_core.is_dir():
        raise RuntimeError(
            f"current Protos Core missing: {current_core}"
        )

    current = sha256_tree(current_core)

    print(
        f"core_baseline_sha256={baseline}"
    )
    print(
        f"core_current_sha256={current}"
    )

    if baseline != current:
        raise RuntimeError(
            "current /workspaces/protos Core differs "
            "from pinned 0.3.128 Core"
        )

    print("core_compatibility=PASS")
    return baseline


def compile_harness() -> None:
    runner = (
        TRUFFLE
        / "target"
        / "classes"
        / "com"
        / "guillermomolina"
        / "protos"
        / "benchmarks"
        / "truffle"
        / "TruffleJvmRunner.class"
    )

    if runner.is_file():
        print(
            "truffle_harness=READY action=reuse",
            flush=True,
        )
        return

    print(
        "truffle_harness=READY action=compile",
        flush=True,
    )

    run(
        "mvn",
        "-q",
        "-f",
        str(TRUFFLE / "pom.xml"),
        "compile",
        cwd=ROOT,
    )

    if not runner.is_file():
        raise RuntimeError(
            "Truffle JVM runner class not produced"
        )


def ensure_native() -> dict[str, object]:
    run(
        sys.executable,
        str(TRUFFLE / "native_setup.py"),
        cwd=ROOT,
    )

    manifest_path = (
        WORK
        / "truffle-native"
        / "runtime-manifest.json"
    )

    if not manifest_path.is_file():
        raise RuntimeError(
            "native setup did not produce runtime manifest"
        )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    for language, expected_sha in (
        NATIVE_BINARY_SHA256.items()
    ):
        item = manifest.get(language)

        if not isinstance(item, dict):
            raise RuntimeError(
                f"native manifest missing {language}"
            )

        actual_sha = item.get(
            "binary_sha256"
        )

        if actual_sha != expected_sha:
            raise RuntimeError(
                f"{language} native binary mismatch: "
                f"expected {expected_sha}, "
                f"got {actual_sha}"
            )

    print("native_runtime_identity=PASS")
    return manifest


def main() -> None:
    require_tools()

    STATE.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "java="
        + run(
            "java",
            "-version",
            capture=True,
        ).splitlines()[0]
    )

    print(
        "maven="
        + run(
            "mvn",
            "-version",
            capture=True,
        ).splitlines()[0]
    )

    repos: dict[str, Path] = {}

    for name, revision, version in VARIANTS:
        repos[name] = ensure_checkout(
            name,
            revision,
            version,
        )

    baseline_name = VARIANTS[0][0]
    baseline_revision = VARIANTS[0][1]
    baseline_version = VARIANTS[0][2]

    jar = ensure_jvm_artifact(
        repos[baseline_name],
        baseline_revision,
        baseline_version,
    )

    core_sha = verify_core(
        repos[baseline_name]
    )

    compile_harness()

    for name, revision, _ in VARIANTS:
        ensure_ab_variant(
            repos[name],
            revision,
        )

    manifest = ensure_native()

    print(
        "jvm_protos=READY "
        f"version={baseline_version} "
        f"revision={baseline_revision} "
        f"jar_sha256={sha256_file(jar)} "
        f"core_sha256={core_sha}"
    )

    print(
        "jvm_ab=READY "
        f"baseline={VARIANTS[0][1]} "
        f"candidate={VARIANTS[1][1]}"
    )

    for language in (
        "protos",
        "js",
        "python",
    ):
        print(
            f"native_{language}=READY "
            f"binary_sha256="
            f"{manifest[language]['binary_sha256']}"
        )

    print("prepare=PASS")


if __name__ == "__main__":
    main()
