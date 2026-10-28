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

    def test_image_identity_reads_immutable_local_id(self):
        identifier = "sha256:" + "a" * 64
        result = subprocess.CompletedProcess(
            [], 0, identifier + "\n", "",
        )

        with mock.patch.object(
            h.subprocess, "run", return_value=result
        ) as run:
            self.assertEqual(
                h.image_identity("podman", h.DEFAULT_IMAGE),
                identifier,
            )

        command = run.call_args.args[0]
        self.assertEqual(
            command[:3], ["podman", "image", "inspect"]
        )
        self.assertIn("--format", command)
        self.assertNotIn("pull", command)
        self.assertNotIn("build", command)

    def test_image_identity_rejects_unresolved_image(self):
        result = subprocess.CompletedProcess(
            [], 1, "", "image not found",
        )

        with mock.patch.object(
            h.subprocess, "run", return_value=result
        ):
            with self.assertRaisesRegex(
                h.HarnessError, "IMAGE_ID_UNAVAILABLE"
            ):
                h.image_identity("podman", h.DEFAULT_IMAGE)

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
                h, "image_identity",
                return_value="sha256:" + "a" * 64,
            ),
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
        self.assertIn("--container-image-id", command)
        self.assertIn("sha256:" + "a" * 64, command)

    def test_host_hostname_is_forwarded_to_measurement(self):
        args = h.parse_args([
            "measure",
            "--case", "factorial",
            "--language", "js",
        ])

        with (
            mock.patch.object(
                h, "podman_binary", return_value="podman"
            ),
            mock.patch.object(h, "require_image"),
            mock.patch.object(
                h, "image_identity",
                return_value="sha256:" + "a" * 64,
            ),
            mock.patch.object(
                h.platform, "node", return_value="home-workstation"
            ),
            mock.patch.object(
                h, "run_container", return_value=0
            ) as run,
        ):
            code = h.run_measurement(args, "measure")

        self.assertEqual(code, 0)
        command = run.call_args.args[3]
        self.assertEqual(
            command[command.index("--host-hostname") + 1],
            "home-workstation",
        )

    def test_versions_are_routed_per_language(self):
        args = h.parse_args([
            "measure",
            "--case", "factorial",
            "--protos-version", "0.3.1-SNAPSHOT",
            "--js-version", "25.4.4.1.1",
            "--python-version", "25.3.0",
        ])

        with (
            mock.patch.object(
                h, "podman_binary", return_value="podman"
            ),
            mock.patch.object(h, "require_image"),
            mock.patch.object(
                h, "image_identity",
                return_value="sha256:" + "a" * 64,
            ),
            mock.patch.object(
                h, "product_directory",
                return_value=pathlib.Path("/fake/protos"),
            ),
            mock.patch.object(
                h, "run_container", return_value=0
            ) as run,
        ):
            code = h.run_measurement(args, "measure")

        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 3)

        expected_versions = {
            "protos": "0.3.1-SNAPSHOT",
            "js": "25.4.4.1.1",
            "python": "25.3.0",
        }

        for call in run.call_args_list:
            command = call.args[3]
            language = command[command.index("--language") + 1]
            version = command[command.index("--version") + 1]
            self.assertEqual(version, expected_versions[language])

    def test_temperature_is_forwarded_to_measurement(self):
        args = h.parse_args([
            "measure",
            "--case", "factorial",
            "--language", "js",
            "--temperature", "cold",
        ])

        with (
            mock.patch.object(
                h, "podman_binary", return_value="podman"
            ),
            mock.patch.object(h, "require_image"),
            mock.patch.object(
                h, "image_identity",
                return_value="sha256:" + "a" * 64,
            ),
            mock.patch.object(
                h, "run_container", return_value=0
            ) as run,
        ):
            code = h.run_measurement(args, "measure")

        self.assertEqual(code, 0)

        command = run.call_args.args[3]
        self.assertEqual(
            command[command.index("--temperature") + 1],
            "cold",
        )

    def test_correctness_rejects_temperature_selection(self):
        args = h.parse_args([
            "correctness",
            "--temperature", "cold",
        ])

        with self.assertRaises(h.HarnessError):
            h.run_measurement(args, "correctness")

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

    def test_explicit_peer_container_can_use_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.CompletedProcess([], 0)

            with (
                mock.patch.object(h, "ROOT", pathlib.Path(tmp)),
                mock.patch.object(h, "require_image"),
                mock.patch.object(
                    h.subprocess, "run", return_value=result
                ) as run,
            ):
                code = h.run_container(
                    "podman", h.DEFAULT_IMAGE, None,
                    ["harness/measure_protos.py", "--prepare-peer"],
                    allow_network=True,
                )

        self.assertEqual(code, 0)
        command = run.call_args.args[0]
        self.assertIn("--pull=never", command)
        self.assertNotIn("--network=none", command)
        self.assertNotIn("build", command)

    def test_peer_prepare_routes_both_versions(self):
        args = h.parse_args([
            "peer-prepare",
            "--language", "all",
            "--js-version", "25.4.4.1.1",
            "--python-version", "25.4.4.1.1",
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
            code = h.run_peer_prepare(args)

        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 2)

        for language, call in zip(
            ("js", "python"), run.call_args_list
        ):
            arguments = call.args[3]
            self.assertIn("--prepare-peer", arguments)
            self.assertEqual(
                arguments[arguments.index("--language") + 1],
                language,
            )
            self.assertEqual(
                arguments[arguments.index("--version") + 1],
                "25.4.4.1.1",
            )
            self.assertTrue(call.kwargs["allow_network"])

    def test_peer_prepare_rejects_protos(self):
        args = h.parse_args([
            "peer-prepare", "--language", "protos"
        ])

        with self.assertRaisesRegex(
            h.HarnessError, "PEER_PREPARE_LANGUAGE"
        ):
            h.run_peer_prepare(args)


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
