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

"""Small reusable boundary: exact-revision product admission and isolated diagnostic execution.

Extracted for the PERF010-A hot-root lifecycle discriminator and deliberately usable by a future
exact-revision comparator (PERF020) without importing any timing logic. It owns only mechanics that
are not specific to one experiment:

* exact-revision product build and identity admission on top of the DIST006-D infrastructure
  (`admit_exact_product`): revision label, the source tree's own detached `.git/HEAD`, the product
  `pom.xml` version, the canonical toolchain contract, the runtime probe and JVMCI identity;
* an overlay image build FROM the admitted image (`build_overlay`);
* one isolated `docker run` whose raw stdout/stderr go byte-for-byte to files (`run_isolated`),
  with a fixed CPU set, networking disabled, an optional per-run writable volume and container
  cleanup on timeout;
* streaming SHA-256 file manifests (`file_manifest`, `write_sha256sums`) that stay usable for
  multi-hundred-megabyte compiler dumps.

DIST006-D, PERF014 and PERF016 are not modified and keep their own copies of the few helpers
(`image_bytes`, `image_product_version`, `require_jvmci`) that are repeated here.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import uuid
from typing import Any
import xml.etree.ElementTree as ET

POM_NAMESPACE = "{http://maven.apache.org/POM/4.0.0}"
PRODUCT_POM = "/opt/protos-source/pom.xml"
PRODUCT_GIT_HEAD = "/opt/protos-source/.git/HEAD"
SHA1_HEX_RE = re.compile(r"[0-9a-f]{40}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_module(name: str, path: Path) -> Any:
    """Load a runner module by file path (works for `python3 runner/x.py` and for tests)."""
    key = "pb_" + name
    module = sys.modules.get(key)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(key, path)
    require(spec is not None and spec.loader is not None, "cannot load module: " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_manifest(base: Path, *, exclude: tuple[str, ...] = ("SHA256SUMS",)) -> list[dict[str, Any]]:
    """Sorted `{path,size_bytes,sha256}` rows for every regular file below `base`."""
    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in base.rglob("*") if p.is_file() and p.name not in exclude):
        rows.append(
            {
                "path": path.relative_to(base).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def write_sha256sums(out_dir: Path) -> None:
    rows = [f"{row['sha256']}  {row['path']}" for row in file_manifest(out_dir)]
    (out_dir / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def image_bytes(tag: str, cpu: str, path: str, *, cwd: Path) -> bytes:
    """Exact bytes of a file inside an image, so identity is a true SHA-256 of the file."""
    completed = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--cpuset-cpus", cpu, "--entrypoint", "cat", tag, path],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(
        completed.returncode == 0,
        f"cannot read {path} from image {tag}: " + completed.stderr.decode("utf-8", errors="replace")[-2000:],
    )
    return completed.stdout


def image_product_version(tag: str, cpu: str, *, cwd: Path) -> str:
    """The built image's own pom.xml version, read back from the artifact."""
    root = ET.fromstring(image_bytes(tag, cpu, PRODUCT_POM, cwd=cwd))
    element = root.find(POM_NAMESPACE + "version")
    return element.text.strip() if element is not None and element.text else ""


def image_source_head(tag: str, cpu: str, *, cwd: Path) -> str:
    """The source tree's own detached HEAD as built into the image (`git checkout --detach`)."""
    return image_bytes(tag, cpu, PRODUCT_GIT_HEAD, cwd=cwd).decode("utf-8", errors="replace").strip()


def require_jvmci(runtime: dict[str, str], jvmci: str, label: str) -> None:
    needle = "jvmci-" + jvmci
    for field in ("java_runtime_version", "java_vm_version"):
        observed = runtime.get(field, "")
        require(
            needle in observed,
            f"JVMCI_IDENTITY_MISMATCH: {label} {field}={observed!r} does not contain {needle!r}",
        )


def admit_exact_product(
    dist006d: Any, cfg: dict[str, Any], revision: str, expected_version: str, cpu: str, *, cwd: Path
) -> dict[str, Any]:
    """Build the exact product through DIST006-D and fail closed unless the built artifact proves
    the pinned revision (label and the source tree's own HEAD), the pinned product version, the
    canonical toolchain contract, the runtime identity and JVMCI. Returns the DIST006-D build record
    extended with `product_version` and `source_head`."""
    dist006d.require_exact_sha(revision, "Protos revision")
    build = dist006d.build_and_probe(cfg, revision, cpu)
    require_jvmci(build["runtime"], cfg["toolchain"]["jvmci"], "product image")
    version = image_product_version(build["tag"], cpu, cwd=cwd)
    require(
        version == expected_version,
        f"PRODUCT_VERSION_MISMATCH: image pom version {version!r}, expected {expected_version!r}",
    )
    head = image_source_head(build["tag"], cpu, cwd=cwd)
    require(
        SHA1_HEX_RE.fullmatch(head) is not None and head == revision,
        f"PRODUCT_REVISION_UNPROVEN: image source HEAD {head!r}, expected {revision!r}",
    )
    build["product_version"] = version
    build["source_head"] = head
    return build


def build_overlay(
    dist006d: Any,
    base_tag: str,
    overlay_tag: str,
    dockerfile: Path,
    build_args: dict[str, str],
    *,
    cwd: Path,
) -> dict[str, Any]:
    """Build an overlay image FROM an admitted base image; returns the overlay image identity."""
    command = ["docker", "build", "--build-arg", "BASE_IMAGE=" + base_tag]
    for key, value in build_args.items():
        command += ["--build-arg", f"{key}={value}"]
    command += ["-t", overlay_tag, "-f", str(dockerfile.relative_to(cwd)), "."]
    completed = subprocess.run(command, cwd=cwd, check=False)
    require(completed.returncode == 0, "overlay image build failed: " + overlay_tag)
    return dist006d.image_identity(overlay_tag)


def run_isolated(
    *,
    tag: str,
    cpu: str,
    entrypoint: str,
    args: list[str],
    stdout_path: Path,
    stderr_path: Path,
    volumes: list[tuple[Path, str, str]] | None = None,
    user: str | None = None,
    timeout_seconds: int = 3600,
    cwd: Path,
) -> dict[str, Any]:
    """One isolated container run: `--network none`, a fixed CPU set, an optional per-run writable
    volume list of `(host_dir, container_dir, "ro"|"rw")` and raw stdout/stderr streamed to files.
    Never raises on a non-zero exit (the caller decides); a timeout removes the container and is
    reported as `timed_out`."""
    name = "pb-diag-" + uuid.uuid4().hex[:12]
    command = ["docker", "run", "--rm", "--name", name, "--network", "none", "--cpuset-cpus", cpu]
    if user:
        command += ["--user", user]
    for host, guest, mode in volumes or []:
        command += ["--volume", f"{host.resolve()}:{guest}:{mode}"]
    command += ["--entrypoint", entrypoint, tag, *args]
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    timed_out = False
    returncode: int | None = None
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        try:
            returncode = subprocess.run(
                command, cwd=cwd, stdout=out, stderr=err, timeout=timeout_seconds, check=False
            ).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(["docker", "rm", "-f", name], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return {
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout": stdout_path.name,
        "stderr": stderr_path.name,
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
    }
