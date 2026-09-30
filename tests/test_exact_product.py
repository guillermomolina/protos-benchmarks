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

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pb_exact_product", ROOT / "runner/exact_product.py")
exact_product = importlib.util.module_from_spec(spec)
sys.modules["pb_exact_product"] = exact_product
spec.loader.exec_module(exact_product)

REVISION = "b72778ca446b602f33af5027a0ed28ab788b39ce"
VERSION = "0.3.119-SNAPSHOT"
POM = b'<project xmlns="http://maven.apache.org/POM/4.0.0"><version>0.3.119-SNAPSHOT</version></project>'
RUNTIME = {"java_runtime_version": "25.0.4.1.1+7-jvmci-25.4-b23", "java_vm_version": "25.0.4.1.1+7-jvmci-25.4-b23"}


def fake_dist006d():
    def require_exact_sha(value, label):
        if value is None or len(value) != 40:
            raise RuntimeError(label)
        return value

    return SimpleNamespace(
        require_exact_sha=require_exact_sha,
        build_and_probe=lambda cfg, revision, cpu: {"tag": "t:1", "runtime": dict(RUNTIME)},
    )


def admit(head=REVISION, pom=POM, version=VERSION, jvmci="25.4-b23", revision=REVISION):
    files = {exact_product.PRODUCT_POM: pom, exact_product.PRODUCT_GIT_HEAD: (head + "\n").encode()}
    with mock.patch.object(exact_product, "image_bytes", side_effect=lambda tag, cpu, path, cwd: files[path]):
        return exact_product.admit_exact_product(
            fake_dist006d(), {"toolchain": {"jvmci": jvmci}}, revision, version, "0", cwd=ROOT
        )


class AdmissionTest(unittest.TestCase):
    def test_exact_product_is_admitted_with_its_own_proof(self):
        build = admit()
        self.assertEqual(VERSION, build["product_version"])
        self.assertEqual(REVISION, build["source_head"])

    def test_wrong_version_fails_closed(self):
        with self.assertRaises(RuntimeError) as caught:
            admit(version="0.3.118-SNAPSHOT")
        self.assertIn("PRODUCT_VERSION_MISMATCH", str(caught.exception))

    def test_unproven_or_wrong_source_head_fails_closed(self):
        for head in ("c" * 40, "ref: refs/heads/main", ""):
            with self.subTest(head=head), self.assertRaises(RuntimeError) as caught:
                admit(head=head)
            self.assertIn("PRODUCT_REVISION_UNPROVEN", str(caught.exception))

    def test_wrong_jvmci_and_malformed_revision_fail_closed(self):
        with self.assertRaises(RuntimeError):
            admit(jvmci="25.3-b1")
        with self.assertRaises(RuntimeError):
            admit(revision="main")


class IsolatedRunTest(unittest.TestCase):
    def test_command_is_isolated_and_raw_logs_are_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "logs"
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                kwargs["stdout"].write(b"raw out\n")
                kwargs["stderr"].write(b"raw err\n")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(exact_product.subprocess, "run", side_effect=fake_run):
                result = exact_product.run_isolated(
                    tag="img", cpu="3", entrypoint="java", args=["-version"],
                    stdout_path=out / "o.log", stderr_path=out / "e.log",
                    volumes=[(Path(tmp), "/diag-out", "rw")], user="1000:1000", cwd=ROOT,
                )
            command = calls[0][0]
            self.assertEqual(["--network", "none"], command[command.index("--network"):command.index("--network") + 2])
            self.assertEqual("3", command[command.index("--cpuset-cpus") + 1])
            self.assertEqual("1000:1000", command[command.index("--user") + 1])
            self.assertIn(f"{Path(tmp).resolve()}:/diag-out:rw", command)
            self.assertNotIn("--privileged", command)
            self.assertEqual(b"raw out\n", (out / "o.log").read_bytes())
            self.assertEqual(0, result["returncode"])
            self.assertEqual(exact_product.sha256_bytes(b"raw err\n"), result["stderr_sha256"])

    def test_timeout_removes_the_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = []

            def fake_run(command, **kwargs):
                seen.append(command)
                if command[:2] == ["docker", "run"]:
                    raise subprocess.TimeoutExpired(command, 1)
                return SimpleNamespace(returncode=0)

            with mock.patch.object(exact_product.subprocess, "run", side_effect=fake_run):
                result = exact_product.run_isolated(
                    tag="img", cpu="0", entrypoint="java", args=[],
                    stdout_path=Path(tmp) / "o", stderr_path=Path(tmp) / "e", cwd=ROOT,
                )
            self.assertTrue(result["timed_out"])
            self.assertEqual(["docker", "rm", "-f"], seen[-1][:3])


class ManifestTest(unittest.TestCase):
    def test_streaming_manifest_and_sums(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "a").mkdir()
            (base / "a/x.bin").write_bytes(b"abc")
            (base / "y.txt").write_bytes(b"")
            rows = exact_product.file_manifest(base)
            self.assertEqual(["a/x.bin", "y.txt"], [r["path"] for r in rows])
            self.assertEqual(exact_product.sha256_bytes(b"abc"), rows[0]["sha256"])
            exact_product.write_sha256sums(base)
            self.assertIn(exact_product.sha256_bytes(b"abc") + "  a/x.bin", (base / "SHA256SUMS").read_text())
            self.assertEqual(2, len(exact_product.file_manifest(base)))


if __name__ == "__main__":
    unittest.main()
