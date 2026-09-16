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

"""PERF009-A repository baseline and critical-path attribution harness."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from runner.toolchain import read_toolchain


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "perf009a.json"
WORK = ROOT / ".work" / "perf009a"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def materialize_source(
    repository: str,
    revision: str,
    destination: Path,
) -> Path:
    if not SHA_RE.fullmatch(revision):
        raise RuntimeError(f"invalid Protos revision: {revision!r}")

    if destination.exists():
        shutil.rmtree(destination)

    destination.mkdir(parents=True)

    run(["git", "init", "."], cwd=destination)
    run(["git", "remote", "add", "origin", repository], cwd=destination)
    run(
        ["git", "fetch", "--depth", "1", "origin", revision],
        cwd=destination,
    )
    run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=destination)

    observed = run(
        ["git", "rev-parse", "HEAD"],
        cwd=destination,
    ).stdout.strip()

    if observed != revision:
        raise RuntimeError(
            f"materialized revision mismatch: expected {revision}, got {observed}"
        )

    return destination


def materialized_source_identity(
    repository: str,
    revision: str,
    destination: Path,
) -> dict[str, Any]:
    source = materialize_source(repository, revision, destination)

    return {
        "protos_repository": repository,
        "protos_revision": revision,
        "toolchain": read_toolchain(source),
    }
