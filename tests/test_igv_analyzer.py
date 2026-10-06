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

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "igv_analyzer.sh"
GRAAL_VERSION = "25.4.4.1.1"
DEFAULT_IMAGE = (
    "ghcr.io/guillermomolina/protos-benchmarks/igv-analyzer:graal-"
    + GRAAL_VERSION
)
SELECTOR = "protos-root:0123456789abcdef"

# Records every invocation; `image inspect` succeeds when FAKE_IMAGE_PRESENT=1;
# `run` prints FAKE_LIST_OUTPUT and exits with FAKE_RUN_STATUS.
FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >>"$FAKE_DOCKER_LOG"
case "$1" in
    image)
        [ "${FAKE_IMAGE_PRESENT:-1}" = 1 ]
        ;;
    run)
        [ -z "${FAKE_LIST_OUTPUT:-}" ] || cat "$FAKE_LIST_OUTPUT"
        exit "${FAKE_RUN_STATUS:-0}"
        ;;
    *)
        exit 0
        ;;
esac
"""

LISTING_WITH_ROOT = f"""fixture.bgv
├─ {SELECTOR} Truffle::example
│  ├─ Before TruffleTier
│  ├─ After TruffleTier
│  └─ After PartialEscape
"""


class IgvAnalyzerWrapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.docker = self.dir / "docker"
        self.docker.write_text(FAKE_DOCKER, encoding="utf-8")
        self.docker.chmod(0o755)
        self.log = self.dir / "docker.log"
        self.log.write_text("", encoding="utf-8")
        self.bgv = self.dir / "input.bgv"
        self.bgv.write_bytes(b"BIGV-not-parsed-by-fake")

    def tearDown(self):
        self.tmp.cleanup()

    def run_wrapper(self, *args, listing=None, image_present=True,
                    run_status=0):
        env = dict(os.environ)
        env.pop("PROTOS_IGV_ANALYZER_IMAGE", None)
        env["DOCKER"] = str(self.docker)
        env["FAKE_DOCKER_LOG"] = str(self.log)
        env["FAKE_IMAGE_PRESENT"] = "1" if image_present else "0"
        env["FAKE_RUN_STATUS"] = str(run_status)
        if listing is not None:
            listing_path = self.dir / "listing.txt"
            listing_path.write_text(listing, encoding="utf-8")
            env["FAKE_LIST_OUTPUT"] = str(listing_path)
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=self.dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines()

    @staticmethod
    def fields(stdout):
        return dict(
            line.split("=", 1) for line in stdout.splitlines() if "=" in line
        )

    def assert_no_build_activity(self):
        for call in self.calls():
            words = call.split()
            self.assertNotIn(words[0], ("build", "pull", "buildx"), call)
            for forbidden in ("filter", "flatten", "git", "clone", "mx",
                              "javac", "mvn"):
                self.assertNotIn(forbidden, words, call)

    def test_default_image_is_versioned_prebuilt_ghcr_image(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(f"ANALYZER_GRAAL_VERSION={GRAAL_VERSION}", text)
        self.assertIn("PROTOS_IGV_ANALYZER_IMAGE", text)
        result = self.run_wrapper("inspect", str(self.bgv),
                                  listing=LISTING_WITH_ROOT)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["ANALYZER_GRAAL_VERSION"], GRAAL_VERSION)
        self.assertEqual(fields["ANALYZER_IMAGE"], DEFAULT_IMAGE)
        self.assertNotIn(":latest", text)

    def test_help_exposes_commands(self):
        result = self.run_wrapper("--help")
        self.assertEqual(result.returncode, 0)
        for command in ("pull", "inspect", "build", "smoke", "list",
                        "filter", "flatten"):
            self.assertIn(command, result.stdout)

    def test_inspect_rejects_missing_file(self):
        result = self.run_wrapper("inspect", str(self.dir / "absent.bgv"),
                                  SELECTOR)
        self.assertNotEqual(result.returncode, 0)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["BGV_READABLE"], "FAIL")
        self.assertEqual(fields["SELECTED_ROOT_PRESENT"], "FAIL")
        self.assertEqual(self.calls(), [])

    def test_inspect_rejects_empty_file(self):
        self.bgv.write_bytes(b"")
        result = self.run_wrapper("inspect", str(self.bgv))
        self.assertNotEqual(result.returncode, 0)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["BGV_READABLE"], "FAIL")
        self.assertEqual(fields["SELECTED_ROOT_PRESENT"], "NOT_REQUESTED")
        self.assertEqual(self.calls(), [])

    def test_inspect_rejects_malformed_selector(self):
        result = self.run_wrapper("inspect", str(self.bgv),
                                  "protos-root:ABC")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_inspect_uses_only_igvutil_list_offline(self):
        result = self.run_wrapper("inspect", str(self.bgv), SELECTOR,
                                  listing=LISTING_WITH_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(calls[0], f"image inspect {DEFAULT_IMAGE}")
        runs = [c for c in calls if c.startswith("run ")]
        self.assertEqual(len(runs), 1)
        self.assertIn("--network none", runs[0])
        self.assertTrue(runs[0].endswith(f"{DEFAULT_IMAGE} list input.bgv"),
                        runs[0])
        self.assert_no_build_activity()

    def test_inspect_missing_image_fails_without_build_or_pull(self):
        result = self.run_wrapper("inspect", str(self.bgv),
                                  listing=LISTING_WITH_ROOT,
                                  image_present=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("scripts/igv_analyzer.sh pull", result.stderr)
        self.assertEqual(self.calls(), [f"image inspect {DEFAULT_IMAGE}"])

    def test_selector_match_and_after_truffle_tier_pass(self):
        result = self.run_wrapper("inspect", str(self.bgv), SELECTOR,
                                  listing=LISTING_WITH_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["BGV_READABLE"], "PASS")
        self.assertEqual(fields["SELECTED_ROOT_PRESENT"], "PASS")
        self.assertEqual(fields["AFTER_TRUFFLE_TIER_PRESENT"], "PASS")
        self.assertEqual(fields["IGV_INSPECT"], "PASS")

    def test_selector_not_requested(self):
        result = self.run_wrapper("inspect", str(self.bgv),
                                  listing=LISTING_WITH_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["SELECTED_ROOT_PRESENT"], "NOT_REQUESTED")
        self.assertEqual(fields["IGV_INSPECT"], "PASS")

    def test_selector_miss_fails(self):
        result = self.run_wrapper("inspect", str(self.bgv),
                                  "protos-root:fedcba9876543210",
                                  listing=LISTING_WITH_ROOT)
        self.assertNotEqual(result.returncode, 0)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["SELECTED_ROOT_PRESENT"], "FAIL")
        self.assertEqual(fields["AFTER_TRUFFLE_TIER_PRESENT"], "PASS")
        self.assertEqual(fields["IGV_INSPECT"], "FAIL")

    def test_after_truffle_tier_miss_fails(self):
        listing = LISTING_WITH_ROOT.replace("After TruffleTier",
                                            "After Inlining")
        result = self.run_wrapper("inspect", str(self.bgv), SELECTOR,
                                  listing=listing)
        self.assertNotEqual(result.returncode, 0)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["SELECTED_ROOT_PRESENT"], "PASS")
        self.assertEqual(fields["AFTER_TRUFFLE_TIER_PRESENT"], "FAIL")
        self.assertEqual(fields["IGV_INSPECT"], "FAIL")

    def test_unreadable_bgv_fails(self):
        result = self.run_wrapper("inspect", str(self.bgv), SELECTOR,
                                  listing="", run_status=1)
        self.assertNotEqual(result.returncode, 0)
        fields = self.fields(result.stdout)
        self.assertEqual(fields["BGV_READABLE"], "FAIL")
        self.assertEqual(fields["SELECTED_ROOT_PRESENT"], "FAIL")
        self.assertEqual(fields["AFTER_TRUFFLE_TIER_PRESENT"], "FAIL")

    def test_list_filter_flatten_preserved_without_build(self):
        for command in ("list", "filter", "flatten"):
            self.log.write_text("", encoding="utf-8")
            result = self.run_wrapper(command, "x.bgv")
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = self.calls()
            self.assertEqual(calls[0], f"image inspect {DEFAULT_IMAGE}")
            self.assertTrue(
                calls[1].endswith(f"{DEFAULT_IMAGE} {command} x.bgv"),
                calls[1],
            )
            self.assertIn("--network none", calls[1])
            self.assertEqual(len(calls), 2)

    def test_list_missing_image_does_not_run(self):
        result = self.run_wrapper("list", "x.bgv", image_present=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [f"image inspect {DEFAULT_IMAGE}"])

    def test_pull_is_explicit_and_versioned(self):
        result = self.run_wrapper("pull")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [f"pull {DEFAULT_IMAGE}"])

    def test_image_override_is_preserved(self):
        env_image = "example.invalid/analyzer:test"
        env = dict(os.environ, DOCKER=str(self.docker),
                   FAKE_DOCKER_LOG=str(self.log),
                   PROTOS_IGV_ANALYZER_IMAGE=env_image)
        subprocess.run([str(SCRIPT), "pull"], cwd=self.dir, env=env,
                       check=True, stdout=subprocess.PIPE)
        self.assertEqual(self.calls(), [f"pull {env_image}"])


class IgvAnalyzerContractTest(unittest.TestCase):
    def test_dockerfile_pins_current_toolchain(self):
        dockerfile = (
            ROOT / "docker" / "igv-analyzer" / "Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "GRAAL_REV=95ce1499c8c96ab7d5a6697c5b4bf42160f3b68b",
            dockerfile,
        )
        self.assertIn(
            "MX_REV=22381992c7322f661498cd6101144f0f49c72ae1",
            dockerfile,
        )
        self.assertIn(f"GRAALVM_VERSION={GRAAL_VERSION}", dockerfile)
        self.assertIn(
            "ghcr.io/graalvm/graalvm-community:"
            "25i4-25.0.4.1.1-ol10-20260922@sha256:"
            "a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5",
            dockerfile,
        )
        self.assertNotIn("25.3.4.1", dockerfile)
        self.assertIn("GRAAL_IGVUTIL", dockerfile)
        self.assertIn("eclipse-temurin:21.0.12_8-jre-jammy", dockerfile)

    def test_dockerfile_selftests_real_upstream_bgv(self):
        dockerfile = (
            ROOT / "docker" / "igv-analyzer" / "Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertIn("-name 'bigv-3.0.bgv'", dockerfile)
        self.assertIn("IgvUtility list fixture.bgv", dockerfile)
        self.assertIn("IgvUtility filter fixture.bgv", dockerfile)
        self.assertIn("json.load", dockerfile)
        # The final image must depend on the self-test stage output.
        final = dockerfile.split("AS runtime\n", 1)[1]
        self.assertIn("COPY --from=selftest-verify", final)
        self.assertNotIn("/opt/graal", final)
        self.assertNotIn("/opt/mx", final)

    def test_publication_workflow_contract(self):
        workflow = (
            ROOT / ".github" / "workflows" / "igv-analyzer-image.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("docker/igv-analyzer/**", workflow)
        self.assertIn("file: docker/igv-analyzer/Dockerfile", workflow)
        self.assertIn(
            "IMAGE: ghcr.io/guillermomolina/protos-benchmarks/igv-analyzer",
            workflow,
        )
        self.assertIn(f"ANALYZER_GRAAL_VERSION: {GRAAL_VERSION}", workflow)
        self.assertNotIn("latest", workflow)
        self.assertNotIn("igv-analyzer24", workflow)

    def test_default_and_historical_analyzers_are_explicit(self):
        current_docker = ROOT / "docker" / "igv-analyzer"
        historical_docker = ROOT / "docker" / "igv-analyzer24"
        historical_script = ROOT / "scripts" / "igv_analyzer24.sh"

        self.assertTrue(current_docker.is_dir())
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(historical_docker.is_dir())
        self.assertTrue(historical_script.is_file())

        current_text = SCRIPT.read_text(encoding="utf-8")
        historical_text = historical_script.read_text(encoding="utf-8")

        self.assertIn(f"graal-$ANALYZER_GRAAL_VERSION", current_text)
        self.assertNotIn("graal-24.0.0", current_text)
        self.assertNotIn("25.3.4.1", current_text)
        self.assertIn("graal-24.0.0", historical_text)
        self.assertIn("protos-benchmarks/igv-analyzer24:graal-24.0.0",
                      historical_text)

    def test_analyzer_contract_has_no_machine_local_checkout_path(self):
        paths = (
            ROOT / "docker" / "igv-analyzer" / "Dockerfile",
            ROOT / "docker" / "igv-analyzer24" / "Dockerfile",
            ROOT / "scripts" / "igv_analyzer.sh",
            ROOT / "scripts" / "igv_analyzer24.sh",
            ROOT / ".github" / "workflows" / "igv-analyzer-image.yml",
            ROOT / "BENCHMARKING.md",
        )
        forbidden_patterns = (
            re.compile(r"/home/[^/\\s]+/"),
            re.compile(r"/Users/[^/\\s]+/"),
            re.compile(r"~/(?:[^/\\s]+/)+"),
            re.compile(r"protos-benchmarks-igv[0-9]+"),
            re.compile(r"/workspaces/protos(?:/|\s|$)", re.M),
        )
        for path in paths:
            content = path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                self.assertIsNone(pattern.search(content), str(path))


if __name__ == "__main__":
    unittest.main()
