#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work" / "truffle-native"
DOWNLOADS = WORK / "downloads"
RUNTIMES = WORK / "runtimes"
MANIFEST = WORK / "runtime-manifest.json"

ASSETS = {
    "protos": {
        "version": "0.3.116",
        "candidate_revision": "0336ae20216bf2eec17854bea0f6435e4e1e9b19",
        "filename": "protos-0.3.116-native-linux-x86_64.zip",
        "url": (
            "https://github.com/guillermomolina/protos/releases/download/"
            "v0.3.116/protos-0.3.116-native-linux-x86_64.zip"
        ),
        "sha256": "61fd90b39a43c574900b3c61d4fe2e65e100166ced66e495281b336f934883e8",
        "kind": "zip",
        "directory": "protos-0.3.116-native-linux-x86_64",
    },
    "js": {
        "version": "25.4.4.1.1",
        "filename": "graaljs-25.4.4.1.1-linux-amd64.tar.gz",
        "url": (
            "https://github.com/oracle/graaljs/releases/download/"
            "graal-25.4.4.1.1/graaljs-25.4.4.1.1-linux-amd64.tar.gz"
        ),
        "sha256": "9df063a913fa0075a16673b8eb97ef0a4bc547779c3db3e0d4079b8534666e92",
        "kind": "tar",
        "directory": "graaljs-25.4.4.1.1",
    },
    "python": {
        "version": "25.4.4",
        "filename": "graalpy3.13-25.4.4-linux-amd64.tar.gz",
        "url": (
            "https://github.com/oracle/graalpython/releases/download/"
            "graal-25.4.4/graalpy3.13-25.4.4-linux-amd64.tar.gz"
        ),
        "sha256": "8b72e6e513d06976e5c8e051228d69d541fde76d05d5f907eaef4bb31db83af4",
        "kind": "tar",
        "directory": "graalpy-25.4.4",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture(*command: str) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def ensure_archive(name: str) -> Path:
    asset = ASSETS[name]
    DOWNLOADS.mkdir(parents=True, exist_ok=True)

    archive = DOWNLOADS / asset["filename"]

    if archive.is_file():
        actual = sha256_file(archive)
        if actual == asset["sha256"]:
            return archive

        archive.unlink()

    print(f"download={name}", flush=True)
    subprocess.run(
        [
            "curl",
            "-L",
            "--fail",
            "--progress-bar",
            "-o",
            str(archive),
            asset["url"],
        ],
        check=True,
    )

    actual = sha256_file(archive)
    if actual != asset["sha256"]:
        raise RuntimeError(
            f"{name}: expected sha256 {asset['sha256']}, got {actual}"
        )

    return archive


def ensure_runtime(name: str) -> Path:
    asset = ASSETS[name]
    archive = ensure_archive(name)

    target = RUNTIMES / asset["directory"]
    if target.is_dir():
        return target

    temporary = RUNTIMES / f"{asset['directory']}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True, exist_ok=True)

    if asset["kind"] == "zip":
        subprocess.run(
            ["unzip", "-q", str(archive), "-d", str(temporary)],
            check=True,
        )

        extracted = temporary / asset["directory"]
        if not extracted.is_dir():
            raise RuntimeError(
                f"{name}: expected extracted directory {extracted}"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        extracted.replace(target)
        temporary.rmdir()
    else:
        subprocess.run(
            [
                "tar",
                "-xzf",
                str(archive),
                "-C",
                str(temporary),
                "--strip-components=1",
            ],
            check=True,
        )

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)

    return target


def find_python(home: Path) -> Path:
    preferred = [
        home / "bin" / "graalpy",
        home / "bin" / "graalpy3",
        home / "bin" / "python",
    ]

    for candidate in preferred:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    candidates = sorted(
        candidate
        for candidate in (home / "bin").glob("graalpy*")
        if candidate.is_file() and os.access(candidate, os.X_OK)
    )

    if not candidates:
        raise RuntimeError(
            f"cannot locate GraalPy launcher under {home / 'bin'}"
        )

    return candidates[0]


def main() -> None:
    protos_home = ensure_runtime("protos")
    js_home = ensure_runtime("js")
    python_home = ensure_runtime("python")

    protos_bin = protos_home / "bin" / "protos"
    js_bin = js_home / "bin" / "js"
    python_bin = find_python(python_home)

    for binary in (protos_bin, js_bin, python_bin):
        if not binary.is_file():
            raise RuntimeError(f"runtime launcher missing: {binary}")

    manifest = {
        "schema": 1,
        "protos": {
            "version": ASSETS["protos"]["version"],
            "candidate_revision": ASSETS["protos"]["candidate_revision"],
            "archive_sha256": ASSETS["protos"]["sha256"],
            "binary_sha256": sha256_file(protos_bin),
            "path": str(protos_bin),
            "home": str(protos_home),
            "reported_version": capture(str(protos_bin), "--version"),
        },
        "js": {
            "version": ASSETS["js"]["version"],
            "archive_sha256": ASSETS["js"]["sha256"],
            "binary_sha256": sha256_file(js_bin),
            "path": str(js_bin),
            "home": str(js_home),
            "reported_version": capture(str(js_bin), "--version"),
        },
        "python": {
            "version": ASSETS["python"]["version"],
            "archive_sha256": ASSETS["python"]["sha256"],
            "binary_sha256": sha256_file(python_bin),
            "path": str(python_bin),
            "home": str(python_home),
            "reported_version": capture(str(python_bin), "--version"),
        },
    }

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("native_setup=PASS")
    for language in ("protos", "js", "python"):
        item = manifest[language]
        print(f"{language}_version={item['reported_version']}")
        print(f"{language}_binary_sha256={item['binary_sha256']}")


if __name__ == "__main__":
    main()
