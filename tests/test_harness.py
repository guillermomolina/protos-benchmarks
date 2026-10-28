# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Host harness contracts; no container or JVM execution."""

import contextlib
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import benchmark as h


class CatalogTest(unittest.TestCase):
    def test_catalog_is_complete(self):
        data = h.load_catalog()
        self.assertEqual(len(data["workloads"]), 17)

        for item in data["workloads"]:
            self.assertEqual(
                set(item["sources"]),
                {"protos", "js", "python"},
            )

    def test_validate_is_static(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            h.validate()

        self.assertIn("CATALOG_VALID=YES", output.getvalue())
        self.assertIn("MEASUREMENT_POLICY=VALID", output.getvalue())
        self.assertIn("GRAPH_POLICY=VALID", output.getvalue())

    def test_language_and_workload_selection(self):
        self.assertEqual(
            h.selected_languages("all"),
            ("protos", "js", "python"),
        )
        self.assertEqual(
            h.selected_languages("js"),
            ("js",),
        )
        self.assertEqual(
            h.selected_cases("factorial"),
            ["factorial"],
        )

        with self.assertRaises(h.HarnessError):
            h.selected_cases("nonexistent")

        with self.assertRaises(h.HarnessError):
            h.selected_languages("java")


class PodmanContractTest(unittest.TestCase):
    def test_missing_image_fails_without_build_or_pull(self):
        result = subprocess.CompletedProcess(
            ["podman", "image", "inspect"],
            1, "", "image not known",
        )

        with mock.patch.object(
            h.subprocess, "run", return_value=result
        ) as run:
            with self.assertRaisesRegex(
                h.HarnessError, "IMAGE_NOT_AVAILABLE"
            ):
                h.require_image("podman", h.DEFAULT_IMAGE)

        command = run.call_args.args[0]
        self.assertEqual(command[:3], [
            "podman", "image", "inspect"
        ])
        self.assertNotIn("build", command)
        self.assertNotIn("pull", command)

    def test_container_uses_offline_podman(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = pathlib.Path(tmp)
            result = subprocess.CompletedProcess([], 0)

            with (
                mock.patch.object(h, "ROOT", fake_root),
                mock.patch.object(h, "require_image"),
                mock.patch.object(
                    h.subprocess, "run", return_value=result
                ) as run,
            ):
                code = h.run_container(
                    "podman",
                    h.DEFAULT_IMAGE,
                    None,
                    ["harness/measure_protos.py", "--help"],
                )

            self.assertEqual(code, 0)

            command = run.call_args.args[0]
            self.assertEqual(command[:2], ["podman", "run"])
            self.assertIn("--pull=never", command)
            self.assertIn("--network=none", command)
            self.assertIn("--userns=keep-id", command)
            self.assertIn("--entrypoint", command)
            self.assertIn("/usr/bin/python3", command)
            self.assertNotIn("java", command)
            self.assertNotIn("mvn", command)

    def test_correctness_routes_to_existing_engine(self):
        args = h.parse_args([
            "correctness",
            "--case", "factorial",
            "--language", "js",
        ])

        with (
            mock.patch.object(
                h, "podman_binary", return_value="podman"
            ),
            mock.patch.object(h, "require_image"),
            mock.patch.object(
                h, "run_container", return_value=0
            ) as run,
        ):
            code = h.run_measurement(args, "correctness")

        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 1)

        command = run.call_args.args[3]
        self.assertIn("--correctness-only", command)
        self.assertIn("--workload", command)
        self.assertIn("factorial", command)
        self.assertIn("smoke", command)
        self.assertIn("js", command)

    def test_graph_analysis_does_not_use_runner_image(self):
        args = h.parse_args(["graphs-analyze"])
        result = subprocess.CompletedProcess([], 0)

        with (
            mock.patch.object(
                h.subprocess, "run", return_value=result
            ) as run,
            mock.patch.object(
                h, "podman_binary",
                side_effect=AssertionError("unexpected runner"),
            ),
        ):
            code = h.run_graphs(args)

        self.assertEqual(code, 0)
        command = run.call_args.args[0]
        self.assertIn("measure_graphs.py", command[1])
        self.assertIn("analyze", command)
        self.assertNotIn("podman", command)

    def test_image_build_is_explicit(self):
        args = [
            "image-build",
            "--image", h.DEFAULT_IMAGE,
        ]
        result = subprocess.CompletedProcess([], 0)

        with (
            mock.patch.object(
                h, "podman_binary", return_value="podman"
            ),
            mock.patch.object(
                h.subprocess, "run", return_value=result
            ) as run,
        ):
            code = h.main(args)

        self.assertEqual(code, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["podman", "build"])


class MakefileContractTest(unittest.TestCase):
    def test_root_makefile_uses_one_harness(self):
        content = (ROOT / "Makefile").read_text(
            encoding="utf-8"
        )

        self.assertIn("HARNESS := benchmark.py", content)
        self.assertNotIn("include docker/Makefile", content)

        for target in (
            "help:",
            "validate:",
            "correctness:",
            "measure:",
            "smoke:",
            "graphs-capture:",
            "graphs-analyze:",
            "graphs-summarize:",
            "graphs-verify:",
            "image-status:",
            "image-build:",
        ):
            self.assertIn(target, content)


class ColdHostContractTest(unittest.TestCase):
    def test_cold_capture_is_routed_through_podman(self):
        args = h.parse_args([
            "cold-capture",
            "--case", "factorial",
            "--language", "js",
            "--tier", "1",
            "--root", "run",
            "--warmup-calls", "25",
            "--invocations", "500",
        ])

        with (
            mock.patch.object(
                h, "podman_binary",
                return_value="podman",
            ),
            mock.patch.object(h, "require_image"),
            mock.patch.object(
                h, "product_directory",
                return_value=pathlib.Path("/fake/protos"),
            ),
            mock.patch.object(
                h, "run_container",
                return_value=0,
            ) as run,
        ):
            code = h.run_cold(args)

        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 1)

        command = run.call_args.args[3]
        self.assertIn("harness/measure_graphs.py", command)
        self.assertIn("cold", command)
        self.assertIn("--tier", command)
        self.assertIn("1", command)
        self.assertIn("--root", command)
        self.assertIn("run", command)
        self.assertIn("--warmup-calls", command)
        self.assertIn("25", command)
        self.assertIn("--invocations", command)
        self.assertIn("500", command)

    def test_cold_capture_requires_one_language(self):
        args = h.parse_args([
            "cold-capture",
            "--case", "factorial",
        ])

        with self.assertRaises(h.HarnessError):
            h.run_cold(args)

    def test_cold_analysis_runs_on_host(self):
        result = subprocess.CompletedProcess([], 0)

        for action in ("cold-analyze", "cold-summarize"):
            args = h.parse_args([action])

            with (
                mock.patch.object(
                    h.subprocess, "run",
                    return_value=result,
                ) as run,
                mock.patch.object(
                    h, "podman_binary",
                    side_effect=AssertionError(
                        "unexpected runner"
                    ),
                ),
            ):
                code = h.run_cold(args)

            self.assertEqual(code, 0)
            command = run.call_args.args[0]
            self.assertIn("measure_graphs.py", command[1])


if __name__ == "__main__":
    unittest.main()
