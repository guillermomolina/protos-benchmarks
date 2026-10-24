# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Architecture tests for the revision-independent measure_protos.py driver.

Product checkouts are temporary Git repositories; javac, Maven and the JVM
are replaced by fakes so the tests prove orchestration, identity, caching and
result-retention behaviour without building or measuring anything.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "truffle"))

import measure_protos as mp  # noqa: E402

WORKLOAD = "primitive-return-literal"
EXPECTED = "1"


def sh(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout.strip()


def make_product(parent: Path, name: str, version: str) -> Path:
    repo = parent / name
    (repo / "protos" / "lib" / "core").mkdir(parents=True)
    (repo / "protos" / "lib" / "core" / "core.protos").write_text("core\n")
    (repo / ".gitignore").write_text("/target/\n")
    (repo / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        f"<version>{version}</version>"
        "<properties><graalvm.version>25.4.4.1.1</graalvm.version>"
        "<maven.compiler.release>21</maven.compiler.release></properties>"
        "</project>\n"
    )
    sh(repo, "init", "-q")
    sh(repo, "add", "pom.xml", ".gitignore", "protos")
    sh(repo, "commit", "-q", "-m", "init")
    return repo


class Fakes:
    """Replaces javac/Maven/JVM with deterministic stand-ins."""

    def __init__(self, test: "DriverTest") -> None:
        self.test = test
        self.javac_calls: list[list[Path]] = []
        self.java_calls: list[list[str]] = []
        self.unsupported: set[str] = set()
        self.on_timing = None
        self.result = EXPECTED

    def build_product(self, repo: Path, log: Path):
        classes = repo / "target" / "classes"
        classes.mkdir(parents=True, exist_ok=True)
        (classes / "Product.class").write_bytes(b"product:" + mp.git(repo, "rev-parse", "HEAD").encode())
        log.write_text("fake build\n")
        return classes, "/fake/dependency.jar"

    def run_javac(self, classpath: str, sources: list[Path], destination: Path):
        self.javac_calls.append(list(sources))
        names = {path.name for path in sources}

        for surface in self.unsupported:
            definition = mp.load_cases()["surfaces"][surface]
            if Path(definition["sources"][-1]).name in names:
                return subprocess.CompletedProcess(
                    [], 1,
                    "X.java:30: error: cannot find symbol\n"
                    "  symbol:   method executable()\n"
                    "  location: class PreparedTopLevel\n",
                )

        for surface, definition in mp.load_cases()["surfaces"].items():
            if Path(definition["sources"][-1]).name in names:
                target = mp.class_file(destination, definition["main_class"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"adapter")

        return subprocess.CompletedProcess([], 0, "")

    def run_logged(self, command: list[str], log: Path):
        self.java_calls.append(command)
        mode_index = next(i for i, part in enumerate(command) if part in {"correctness", "measure"})
        mode = command[mode_index]

        if mode == "correctness":
            out = f"surface=x\nresult={self.result}\n"
        else:
            warmup, steady, calls, jfr = command[mode_index + 3: mode_index + 7]
            if jfr == "-" and self.on_timing is not None:
                self.on_timing()
            lines = [f"sample_calls={calls}", "setup_ns=1000", "sample phase=cold iteration=1 elapsed_ns=500"]
            lines += [f"sample phase=warmup iteration={i} elapsed_ns=100" for i in range(1, int(warmup) + 1)]
            lines += [f"sample phase=steady iteration={i} elapsed_ns=100" for i in range(1, int(steady) + 1)]
            if jfr != "-":
                Path(jfr).write_bytes(b"jfr")
                lines.append("jfr_scope=steady")
            if "-Dprotos.benchmarks.measure.diagnostic=true" in command:
                lines.insert(0, "diagnostic_mode=ENABLED")
                for phase, count in (
                    ("cold", 1),
                    ("warmup", int(warmup)),
                    ("steady", int(steady)),
                ):
                    for iteration in range(1, count + 1):
                        lines.extend([
                            f"thread_cpu phase={phase} iteration={iteration} elapsed_ns=50",
                            f"ctx_switch phase={phase} iteration={iteration} "
                            "voluntary=0 nonvoluntary=0",
                            f"gc_sample phase={phase} iteration={iteration} "
                            "count_delta=0 time_ms_delta=0",
                        ])
            for option in command:
                prefix = "-Dprotos.benchmarks.measure.jitJfr="
                if option.startswith(prefix):
                    destination = Path(option[len(prefix):])
                    destination.write_bytes(b"simulated-jfr")
                    lines.append("diagnostic_jfr_scope=all-samples")
            for option in command:
                prefix = "-Dprotos.benchmarks.measure.affinityProfile="
                if option.startswith(prefix):
                    profile = option[len(prefix):]
                    initial = "0-1" if profile == "C" else "0"
                    lines.extend([
                        f"AFFINITY_PROFILE={profile}",
                        f"AFFINITY_INITIAL_MAIN={initial}",
                        "MEASURE_THREAD_TID=12345",
                        "MEASURE_THREAD_AFFINITY=0",
                        f"AFFINITY_SNAPSHOT phase=before aux=3 expected={initial}",
                        f"AFFINITY_SNAPSHOT phase=after aux=3 expected={initial}",
                    ])
            samples_prefix = (
                "sample phase=",
                "thread_cpu phase=",
                "ctx_switch phase=",
                "gc_sample phase=",
            )

            for option in command:
                prefix = "-Dprotos.benchmarks.measure.samplesFile="
                if not option.startswith(prefix):
                    continue

                destination = Path(option[len(prefix):])
                records = [
                    "setup_ns=1000",
                    f"sample_calls={calls}",
                    f"warmup_iterations={warmup}",
                    f"steady_iterations={steady}",
                    *(
                        line for line in lines
                        if line.startswith(samples_prefix)
                    ),
                    f"result={self.result}",
                ]
                destination.write_text(
                    "\n".join(records) + "\n",
                    encoding="utf-8",
                )
                lines = [
                    line for line in lines
                    if not line.startswith(samples_prefix)
                ]

            lines.append(f"result={self.result}")
            out = "\n".join(lines) + "\n"

        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(out)
        return 0, out


class DriverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="measure-protos-test-"))
        self.product = make_product(self.tmp, "protos", "0.3.1-SNAPSHOT")
        self.output = self.tmp / "results" / "current"
        self.fakes = Fakes(self)
        self.saved = {
            name: getattr(mp, name)
            for name in ("EMBEDDED_CACHE", "build_product", "run_javac", "run_logged", "java_identity", "producer_files", "peer_classpath")
        }
        mp.EMBEDDED_CACHE = self.tmp / "cache" / "embedded"
        mp.build_product = self.fakes.build_product
        mp.run_javac = self.fakes.run_javac
        mp.run_logged = self.fakes.run_logged
        mp.java_identity = lambda: {"java.home": "/fake/jdk", "java.runtime.version": "25+fake"}

    def tearDown(self) -> None:
        for name, value in self.saved.items():
            setattr(mp, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_driver(
        self,
        *extra: str,
        product: Path | None = None,
        surface: str = "canonical",
        workload: str = WORKLOAD,
    ):
        argv = [
            "--dir", str(product or self.product),
            "--surface", surface,
            "--workload", workload,
            "--stage", "smoke",
            "--output", str(self.output),
            *extra,
        ]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = mp.main(argv)
        lines = dict(
            line.split("=", 1) for line in buffer.getvalue().splitlines() if "=" in line
        )
        return code, lines

    def metadata(self, lines: dict[str, str]) -> dict:
        return json.loads((Path(lines["RESULT"]) / "metadata.json").read_text())

    def test_peer_classpath_recovers_missing_maven_jars(self):
        version = "test-graalvm"
        peer_root = mp.EMBEDDED_CACHE / "peer-classpath" / version
        peer_root.mkdir(parents=True)

        (peer_root / "pom.xml").write_text("<project/>")
        cp_file = peer_root / "classpath.txt"
        cp_file.write_text(str(self.tmp / "missing.jar"))

        jar = self.tmp / "maven-cache" / "polyglot.jar"
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"fake-jar")

        calls = []

        def fake_maven(command, **kwargs):
            calls.append(command)
            option = next(
                item for item in command
                if item.startswith("-Dmdep.outputFile=")
            )
            destination = Path(option.split("=", 1)[1])
            destination.write_text(str(jar))
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch.object(
                mp.jvm_runtime,
                "harness_graalvm_version",
                return_value=version,
            ),
            mock.patch.object(
                mp.jvm_runtime,
                "peer_pom",
                return_value="<project/>",
            ),
            mock.patch.object(
                mp.subprocess,
                "run",
                side_effect=fake_maven,
            ),
        ):
            self.assertEqual(
                mp.peer_classpath(), (version, str(jar))
            )
            self.assertEqual(
                mp.peer_classpath(), (version, str(jar))
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(cp_file.read_text(), str(jar))

    def test_peer_classpath_retries_after_changed_pom_maven_failure(self):
        version = "test-graalvm-refresh"
        peer_root = mp.EMBEDDED_CACHE / "peer-classpath" / version
        peer_root.mkdir(parents=True)

        pom = peer_root / "pom.xml"
        pom.write_text("<old/>")

        old_jar = self.tmp / "old.jar"
        old_jar.write_bytes(b"old")

        cp_file = peer_root / "classpath.txt"
        cp_file.write_text(str(old_jar))

        new_jar = self.tmp / "new.jar"
        new_jar.write_bytes(b"new")

        calls = []

        def fake_maven(command, **kwargs):
            calls.append(command)

            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, command)

            option = next(
                item for item in command
                if item.startswith("-Dmdep.outputFile=")
            )
            destination = Path(option.split("=", 1)[1])
            destination.write_text(str(new_jar))
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch.object(
                mp.jvm_runtime,
                "harness_graalvm_version",
                return_value=version,
            ),
            mock.patch.object(
                mp.jvm_runtime,
                "peer_pom",
                return_value="<project/>",
            ),
            mock.patch.object(
                mp.subprocess,
                "run",
                side_effect=fake_maven,
            ),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                mp.peer_classpath()

            self.assertEqual(pom.read_text(), "<old/>")
            self.assertEqual(cp_file.read_text(), str(old_jar))

            self.assertEqual(
                mp.peer_classpath(),
                (version, str(new_jar)),
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(pom.read_text(), "<project/>")
        self.assertEqual(cp_file.read_text(), str(new_jar))

    # A, B
    def test_measures_clean_checkout_without_modifying_it(self):
        before = sh(self.product, "status", "--porcelain", "--untracked-files=all")
        head = sh(self.product, "rev-parse", "HEAD")
        code, lines = self.run_driver()
        self.assertEqual(code, 0)
        self.assertEqual(lines["MEASUREMENT_VALID"], "YES")
        self.assertEqual(before, "")
        self.assertEqual(sh(self.product, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual(sh(self.product, "rev-parse", "HEAD"), head)
        metadata = self.metadata(lines)
        self.assertEqual(metadata["protos_revision"], head)
        self.assertEqual(metadata["protos_version"], "0.3.1-SNAPSHOT")
        self.assertTrue(metadata["protos_clean"])
        self.assertEqual(metadata["product_directory"], str(self.product.resolve()))
        self.assertEqual(metadata["correctness"]["result"], "PASS")
        self.assertTrue((Path(lines["RESULT"]) / "summary.json").is_file())
        self.assertTrue((Path(lines["RESULT"]) / "raw" / "timing.log").is_file())

    # C, D, E
    def test_adapter_compiled_reused_and_recompiled_after_cache_deletion(self):
        code, lines = self.run_driver()
        self.assertEqual(lines["ADAPTER_CACHE"], "compiled")
        self.assertEqual(len(self.fakes.javac_calls), 1)
        cache_path = Path(lines["ADAPTER_CACHE_PATH"])
        self.assertTrue(str(cache_path).startswith(str(mp.EMBEDDED_CACHE)))
        self.assertIn(sh(self.product, "rev-parse", "HEAD"), cache_path.parts)

        code, lines = self.run_driver("--remeasure")
        self.assertEqual(lines["ADAPTER_CACHE"], "reused")
        self.assertEqual(len(self.fakes.javac_calls), 1)

        shutil.rmtree(mp.EMBEDDED_CACHE)
        code, lines = self.run_driver("--remeasure")
        self.assertEqual(code, 0)
        self.assertEqual(lines["ADAPTER_CACHE"], "compiled")
        self.assertEqual(len(self.fakes.javac_calls), 2)
        self.assertEqual(self.fakes.javac_calls[0], self.fakes.javac_calls[1])
        self.assertEqual(len(list((self.output / mp.case_id("protos", "canonical", WORKLOAD, "smoke", "none")).iterdir())), 3)

    # F
    def test_switching_directory_needs_no_source_change(self):
        other = make_product(self.tmp, "protos-next", "0.3.2-SNAPSHOT")
        _, first = self.run_driver()
        _, second = self.run_driver(product=other)
        self.assertEqual(self.metadata(first)["protos_version"], "0.3.1-SNAPSHOT")
        self.assertEqual(self.metadata(second)["protos_version"], "0.3.2-SNAPSHOT")
        self.assertNotEqual(self.metadata(first)["protos_revision"], self.metadata(second)["protos_revision"])
        self.assertEqual(second["ADAPTER_CACHE"], "compiled")
        self.assertEqual(
            self.metadata(first)["adapter_source_sha256"],
            self.metadata(second)["adapter_source_sha256"],
        )
        self.assertEqual(
            self.metadata(first)["harness"]["source_sha256"],
            self.metadata(second)["harness"]["source_sha256"],
        )

    # G
    def test_surfaces_are_independent_cases(self):
        for surface in ("dynamic", "prepared", "canonical"):
            self.fakes.javac_calls.clear()
            code, lines = self.run_driver(surface=surface)
            self.assertEqual(code, 0, surface)
            self.assertEqual(self.metadata(lines)["surface"], surface)
            compiled = {path.name for path in self.fakes.javac_calls[0]}
            others = {"dynamic", "prepared", "canonical"} - {surface}
            for other in others:
                own = Path(mp.load_cases()["surfaces"][other]["sources"][-1]).name
                self.assertNotIn(own, compiled)

    # H
    def test_unsupported_surface_fails_without_fallback(self):
        self.fakes.unsupported.add("canonical")
        code, lines = self.run_driver()
        self.assertEqual(code, mp.EXIT_SURFACE_UNSUPPORTED)
        self.assertEqual(lines["SURFACE_SUPPORTED"], "NO")
        self.assertEqual(lines["SURFACE"], "canonical")
        self.assertIn("executable()", lines["REASON"])
        self.assertEqual(len(self.fakes.javac_calls), 1)
        self.assertEqual(self.fakes.java_calls, [])
        invalid = json.loads((Path(lines["INVALID_RECORD"]) / "metadata.json").read_text())
        self.assertFalse(invalid["measurement_valid"])
        self.assertEqual(invalid["invalid_reason"], "SURFACE_UNSUPPORTED")

    # I, J
    def test_product_movement_invalidates_batch(self):
        def move():
            (self.product / "new.txt").write_text("x")
            sh(self.product, "add", "new.txt")
            sh(self.product, "commit", "-q", "-m", "moved")

        self.fakes.on_timing = move
        code, lines = self.run_driver()
        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(lines["MEASUREMENT_VALID"], "NO")
        self.assertEqual(lines["REASON"], "PRODUCT_CHANGED_DURING_MEASUREMENT")
        record = Path(lines["INVALID_RECORD"])
        self.assertTrue(record.name.endswith(".invalid"))
        metadata = json.loads((record / "metadata.json").read_text())
        self.assertNotEqual(metadata["product_before"]["revision"], metadata["product_after"]["revision"])

    def test_product_dirtying_invalidates_batch(self):
        self.fakes.on_timing = lambda: (self.product / "scratch.protos").write_text("x")
        code, lines = self.run_driver()
        self.assertEqual(lines["REASON"], "PRODUCT_CHANGED_DURING_MEASUREMENT")

    def test_before_and_after_identity_recorded(self):
        _, lines = self.run_driver()
        metadata = self.metadata(lines)
        self.assertEqual(metadata["product_before"]["revision"], metadata["product_after"]["revision"])

    def test_dirty_product_refused_by_default(self):
        (self.product / "scratch.protos").write_text("x")
        code, _ = self.run_driver()
        self.assertEqual(code, mp.EXIT_USAGE)
        code, lines = self.run_driver("--allow-dirty-product")
        self.assertEqual(code, 0)
        self.assertFalse(self.metadata(lines)["reference_eligible"])

    # K, O
    def test_dirty_harness_allowed_and_producer_hashes_recorded(self):
        code, lines = self.run_driver()
        self.assertEqual(code, 0)
        metadata = self.metadata(lines)
        actual_dirty = bool(sh(ROOT, "status", "--porcelain", "--untracked-files=all"))
        self.assertEqual(metadata["harness_dirty"], actual_dirty)
        hashes = metadata["harness"]["source_sha256"]
        self.assertEqual(hashes["truffle/measure_protos.py"], mp.sha256_file(ROOT / "truffle/measure_protos.py"))
        self.assertIn("truffle/measure/surfaces/canonical/ProtosCanonicalSurface.java", hashes)
        self.assertIn("truffle/measure/cases.json", hashes)

    # L
    def test_harness_change_invalidates_batch(self):
        tracked = self.tmp / "producer.py"
        tracked.write_text("v1")
        original = self.saved["producer_files"]
        mp.producer_files = lambda *a: [*original(*a), tracked]
        self.fakes.on_timing = lambda: tracked.write_text("v2")
        code, lines = self.run_driver()
        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(lines["REASON"], "HARNESS_CHANGED_DURING_MEASUREMENT")

    # M
    def test_existing_result_not_remeasured(self):
        _, first = self.run_driver()
        calls = len(self.fakes.java_calls)
        code, second = self.run_driver()
        self.assertEqual(code, 0)
        self.assertEqual(second["RESULT_ALREADY_EXISTS"], "YES")
        self.assertEqual(second["RESULT"], first["RESULT"])
        self.assertEqual(len(self.fakes.java_calls), calls)

        _, third = self.run_driver("--remeasure")
        self.assertNotEqual(third["RESULT"], first["RESULT"])
        self.assertTrue((Path(first["RESULT"]) / "metadata.json").is_file())

    def test_invalid_result_is_not_reused(self):
        self.fakes.result = "2"
        code, lines = self.run_driver()
        self.assertEqual(lines["REASON"], "CORRECTNESS_FAILED")
        self.fakes.result = EXPECTED
        code, lines = self.run_driver()
        self.assertEqual(lines["RESULT_ALREADY_EXISTS"], "NO")
        self.assertEqual(lines["MEASUREMENT_VALID"], "YES")

    def test_correctness_failure_produces_no_timing(self):
        self.fakes.result = "2"
        code, lines = self.run_driver()
        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(len(self.fakes.java_calls), 1)
        self.assertIn("correctness", self.fakes.java_calls[0])

    # N
    def test_only_read_only_git_commands(self):
        with self.assertRaises(RuntimeError):
            mp.git(self.product, "checkout", "HEAD~1")
        for forbidden in ("reset", "clone", "fetch", "worktree", "switch", "restore", "clean", "stash"):
            self.assertNotIn(forbidden, mp.GIT_READ_ONLY)

        seen: list[list[str]] = []
        real_run = subprocess.run

        def spy(command, *args, **kwargs):
            if command and command[0] == "git":
                seen.append(list(command))
            return real_run(command, *args, **kwargs)

        mp.subprocess.run = spy
        try:
            self.run_driver()
        finally:
            mp.subprocess.run = real_run

        self.assertTrue(seen)
        for command in seen:
            self.assertIn(command[3], mp.GIT_READ_ONLY, command)

    def test_no_revision_selection_options(self):
        for option in ("--revision", "--commit", "--tag", "--checkout"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                mp.parse_args([option, "abc"])

    # P
    def test_refuses_foreign_output_directory(self):
        foreign = self.tmp / "results" / "perf999"
        foreign.mkdir(parents=True)
        (foreign / "retained.json").write_text("{}")
        self.output = foreign
        code, _ = self.run_driver()
        self.assertEqual(code, mp.EXIT_USAGE)
        self.assertEqual(sorted(p.name for p in foreign.iterdir()), ["retained.json"])

    def test_jfr_profile_uses_same_adapter_and_case(self):
        code, lines = self.run_driver("--profile", "jfr")
        self.assertEqual(code, 0)
        self.assertEqual(lines["JFR"], "RECORDED")
        summary = json.loads((Path(lines["RESULT"]) / "summary.json").read_text())
        self.assertEqual(summary["jfr"]["scope"], "steady")
        self.assertTrue((Path(lines["RESULT"]) / summary["jfr"]["file"]).is_file())
        measure_calls = [c for c in self.fakes.java_calls if "measure" in c]
        self.assertEqual(len(measure_calls), 2)
        main_classes = {c[c.index("-cp") + 2] for c in measure_calls}
        self.assertEqual(len(main_classes), 1)
        self.assertEqual(len(self.fakes.javac_calls), 1)
        self.assertTrue(any(o.startswith("-XX:FlightRecorderOptions") for o in measure_calls[1]))
        self.assertFalse(any(o.startswith("-XX:FlightRecorderOptions") for o in measure_calls[0]))

    def test_reference_policy_comes_from_case_data(self):
        cases = mp.load_cases()
        timing = mp.resolve_policy(cases, WORKLOAD, "reference", "timing", {})
        self.assertEqual(
            (timing["warmup_iterations"], timing["steady_iterations"], timing["sample_calls"], timing["source"]),
            (60, 10, 1_000_000, "case-policy"),
        )
        self.assertEqual(timing["admission_scope"], "steady-only")
        default = mp.resolve_policy(cases, "fibonacci", "reference", "timing", {})
        self.assertEqual(
            (default["warmup_iterations"], default["sample_calls"], default["admission_scope"]),
            (60, 1, "warmup-and-steady"),
        )
        jfr = mp.resolve_policy(cases, WORKLOAD, "reference", "jfr", {})
        self.assertEqual(jfr["sample_calls"], 1_000_000)
        override = mp.resolve_policy(cases, WORKLOAD, "reference", "timing", {"sample_calls": 7})
        self.assertEqual((override["sample_calls"], override["source"]), (7, "cli-override"))

    def test_reference_policy_is_selected_by_workload_stage_and_kind_only(self):
        # No language, surface or product revision can participate in selection.
        params = list(inspect.signature(mp.resolve_policy).parameters)
        self.assertEqual(params, ["cases", "workload", "stage", "kind", "overrides"])

    def test_same_reference_timing_policy_for_every_language(self):
        mp.peer_classpath = lambda: ("25.4.4.1.1", "/fake/peer.jar")
        older = make_product(self.tmp, "protos-older", "0.3.0-SNAPSHOT")
        runs = {
            "protos": ["--dir", str(self.product), "--surface", "canonical"],
            "protos-older": ["--dir", str(older), "--surface", "canonical"],
            "js": ["--language", "js"],
            "python": ["--language", "python"],
        }
        observed = {}
        for name, selector in runs.items():
            argv = [*selector, "--workload", WORKLOAD, "--stage", "reference",
                    "--output", str(self.tmp / "results" / name)]
            self.fakes.java_calls.clear()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mp.main(argv), 0, name)
            timing = [c for c in self.fakes.java_calls if "measure" in c][0]
            index = timing.index("measure")
            observed[name] = tuple(timing[index + 3: index + 6])
        self.assertEqual(set(observed.values()), {("60", "10", "1000000")}, observed)

    def test_smoke_policy_stays_cheap(self):
        cases = mp.load_cases()
        smoke = mp.resolve_policy(cases, WORKLOAD, "smoke", "timing", {})
        self.assertEqual(
            (smoke["warmup_iterations"], smoke["steady_iterations"], smoke["sample_calls"]),
            (2, 3, 1),
        )

    def test_other_primitive_reference_policies_unchanged(self):
        cases = mp.load_cases()
        for workload in cases["policy"]["workloads"]:
            if workload == WORKLOAD:
                continue
            timing = mp.resolve_policy(cases, workload, "reference", "timing", {})
            expected_warmup = (
                150 if workload == "primitive-while-zero" else 50
            )
            expected_calls = (
                1000000 if workload == "primitive-while-zero" else 10000
            )
            self.assertEqual(
                (timing["warmup_iterations"], timing["steady_iterations"], timing["sample_calls"], timing["admission_scope"]),
                (expected_warmup, 10, expected_calls, "steady-only"),
                workload,
            )

    def test_reference_stage_admits_and_is_eligible(self):
        code, lines = self.run_driver("--stage", "reference")
        self.assertEqual(code, 0)
        self.assertEqual(lines["STEADY_STATE_ADMISSION"], "PASS")
        self.assertTrue(self.metadata(lines)["reference_eligible"])

        summary = json.loads(
            (Path(lines["RESULT"]) / "summary.json").read_text()
        )
        admission = summary["timing"]["admission"]
        self.assertEqual(admission["scope"], "steady-only")
        self.assertEqual(
            admission["steady"]["extreme_sample_check"]["status"],
            "PASS",
        )
        self.assertEqual(
            admission["steady"]["extreme_sample_check"]["extreme_sample_count"],
            0,
        )
        self.assertEqual(
            admission["steady"]["extreme_sample_check"]["median_ns"],
            100.0,
        )

    def test_steady_only_admission_ignores_unsettled_warmup(self):
        original = self.fakes.run_logged

        def unsettled(command, log):
            code, out = original(command, log)
            lines = [
                line.replace("elapsed_ns=100", "elapsed_ns=900")
                if line.startswith("sample phase=warmup") and int(line.split("iteration=")[1].split()[0]) % 2
                else line
                for line in out.splitlines()
            ]
            return code, "\n".join(lines) + "\n"

        self.fakes.run_logged = unsettled
        mp.run_logged = unsettled
        code, lines = self.run_driver("--stage", "reference")
        self.assertEqual(code, 0)
        summary = json.loads((Path(lines["RESULT"]) / "summary.json").read_text())
        self.assertEqual(summary["timing"]["admission"]["scope"], "steady-only")
        self.assertEqual(summary["timing"]["admission"]["warmup"]["status"], "NOT_STABLE")
        self.assertEqual(summary["timing"]["admission"]["status"], "PASS")
        self.assertEqual(
            summary["timing"]["admission"]["warmup"]["extreme_sample_check"]["status"],
            "NOT_STABLE",
        )
        self.assertEqual(
            summary["timing"]["admission"]["steady"]["extreme_sample_check"]["status"],
            "PASS",
        )


    def test_extreme_steady_sample_retained_in_invalid_reference(self):
        original = self.fakes.run_logged

        def isolated_spike(command, log):
            code, out = original(command, log)

            if "measure" in command:
                before = (
                    "sample phase=steady iteration=10 elapsed_ns=100"
                )
                after = (
                    "sample phase=steady iteration=10 elapsed_ns=3000000"
                )
                self.assertIn(before, out)
                out = out.replace(before, after, 1)
                log.write_text(out)

            return code, out

        mp.run_logged = isolated_spike

        code, lines = self.run_driver("--stage", "reference")

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(lines["MEASUREMENT_VALID"], "NO")
        self.assertEqual(lines["REASON"], "NOT_STEADY_STATE_ADMITTED")

        record = Path(lines["INVALID_RECORD"])
        self.assertTrue(record.name.endswith(".invalid"))

        summary = json.loads((record / "summary.json").read_text())
        metadata = json.loads((record / "metadata.json").read_text())
        admission = summary["timing"]["admission"]
        extreme = admission["steady"]["extreme_sample_check"]

        self.assertFalse(summary["measurement_valid"])
        self.assertFalse(metadata["measurement_valid"])
        self.assertEqual(admission["scope"], "steady-only")
        self.assertEqual(admission["status"], "NOT_STABLE")
        self.assertEqual(admission["steady"]["shape"]["status"], "PASS")
        self.assertEqual(extreme["status"], "NOT_STABLE")
        self.assertEqual(extreme["reason"], "extreme-samples")
        self.assertEqual(extreme["extreme_sample_count"], 1)
        self.assertEqual(
            extreme["extreme_samples"],
            [{
                "index": 9,
                "value_ns": 3000000,
                "side": "above-double-median",
            }],
        )
        self.assertEqual(summary["timing"]["steady_ns"][-1], 3000000)
        self.assertIn(
            "iteration=10 elapsed_ns=3000000",
            (record / "raw" / "timing.log").read_text(),
        )

    def test_warmup_and_steady_rejects_unsettled_warmup(self):
        workload = "fibonacci"
        self.fakes.result = mp.workload_catalog.expected_result(workload)
        original = self.fakes.run_logged

        def warmup_spike(command, log):
            code, out = original(command, log)

            if "measure" in command:
                before = (
                    "sample phase=warmup iteration=60 elapsed_ns=100"
                )
                after = (
                    "sample phase=warmup iteration=60 elapsed_ns=900"
                )
                self.assertIn(before, out)
                out = out.replace(before, after, 1)
                log.write_text(out)

            return code, out

        mp.run_logged = warmup_spike

        code, lines = self.run_driver(
            "--stage", "reference", workload=workload
        )

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(lines["REASON"], "NOT_STEADY_STATE_ADMITTED")

        record = Path(lines["INVALID_RECORD"])
        summary = json.loads((record / "summary.json").read_text())
        admission = summary["timing"]["admission"]

        self.assertEqual(admission["scope"], "warmup-and-steady")
        self.assertEqual(admission["status"], "NOT_STABLE")
        self.assertEqual(admission["warmup"]["status"], "NOT_STABLE")
        self.assertEqual(
            admission["warmup"]["extreme_sample_check"]["status"],
            "NOT_STABLE",
        )
        self.assertEqual(admission["steady"]["status"], "PASS")
        self.assertEqual(
            admission["steady"]["extreme_sample_check"]["status"],
            "PASS",
        )
        self.assertEqual(summary["timing"]["warmup_ns"][-1], 900)

    def test_diagnostic_jvm_option_recorded_and_not_eligible(self):
        code, lines = self.run_driver("--stage", "reference", "--jvm-option=-Xlog:gc")
        self.assertEqual(code, 0)
        metadata = self.metadata(lines)
        self.assertEqual(metadata["result_key"]["diagnostic_jvm_options"], ["-Xlog:gc"])
        self.assertFalse(metadata["reference_eligible"])
        timing = [c for c in self.fakes.java_calls if "measure" in c][0]
        self.assertIn("-Xlog:gc", timing)

    def test_explicit_diagnostic_capture_is_non_reference(self):
        code, lines = self.run_driver(
            "--diagnostic", "--stage", "reference"
        )
        self.assertEqual(code, 0)
        self.assertEqual(lines["REFERENCE_ELIGIBLE"], "NO")
        self.assertEqual(lines["STEADY_STATE_ADMISSION"], "N/A")

        result = Path(lines["RESULT"])
        metadata = json.loads((result / "metadata.json").read_text())
        report = json.loads((result / "diagnostic.json").read_text())

        self.assertFalse(metadata["reference_eligible"])
        self.assertEqual(
            metadata["diagnostic_capture"],
            "thread-cpu-gc-ctx-v2-dedicated-file"
        )
        self.assertEqual(
            report["classification"], "DIAGNOSTIC_ONLY"
        )
        self.assertTrue(
            report["correctness"]["prior_gate_verified"]
        )
        self.assertTrue(
            report["phases"]["steady"]["thread_cpu_complete"]
        )
        self.assertTrue(
            report["phases"]["steady"]["context_switches_complete"]
        )
        self.assertTrue(
            report["phases"]["steady"]["gc_samples_complete"]
        )
        self.assertEqual(report["jit_maturity"], "NOT_PROVEN")
        self.assertEqual(
            report["source"]["path"],
            str((result / "raw" / "diagnostic-samples.log").resolve()),
        )

        correctness = [
            call for call in self.fakes.java_calls
            if "correctness" in call
        ][0]
        timing = [
            call for call in self.fakes.java_calls
            if "measure" in call
        ][0]
        option = "-Dprotos.benchmarks.measure.diagnostic=true"

        self.assertNotIn(option, correctness)
        self.assertIn(option, timing)

    def test_diagnostic_rejects_jfr_combination(self):
        code, lines = self.run_driver(
            "--diagnostic", "--profile", "jfr"
        )
        self.assertEqual(code, mp.EXIT_USAGE)
        self.assertEqual(self.fakes.java_calls, [])

    def test_diagnostic_rejects_missing_cpu_samples(self):
        original = self.fakes.run_logged

        def without_cpu(command, log):
            code, out = original(command, log)

            for option in command:
                prefix = "-Dprotos.benchmarks.measure.samplesFile="
                if option.startswith(prefix):
                    path = Path(option[len(prefix):])
                    contents = path.read_text()
                    path.write_text("".join(
                        line
                        for line in contents.splitlines(keepends=True)
                        if not line.startswith("thread_cpu ")
                    ))

            return code, out

        mp.run_logged = without_cpu
        code, lines = self.run_driver("--diagnostic")

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(
            lines["REASON"], "DIAGNOSTIC_CAPTURE_INCOMPLETE"
        )

        record = Path(lines["INVALID_RECORD"])
        self.assertTrue(record.is_dir())

        samples = (
            record / "raw" / "diagnostic-samples.log"
        ).read_text()

        self.assertIn("sample phase=steady", samples)
        self.assertIn("result=1", samples)
        self.assertNotIn("thread_cpu phase=", samples)

    def test_diagnostic_rejects_missing_gc_or_context_samples(self):
        original = self.fakes.run_logged

        for prefix in ("gc_sample ", "ctx_switch "):
            with self.subTest(prefix=prefix):
                def incomplete(command, log):
                    code, out = original(command, log)

                    for option in command:
                        key = "-Dprotos.benchmarks.measure.samplesFile="
                        if option.startswith(key):
                            path = Path(option[len(key):])
                            contents = path.read_text()
                            path.write_text("".join(
                                line
                                for line in contents.splitlines(keepends=True)
                                if not line.startswith(prefix)
                            ))

                    return code, out

                mp.run_logged = incomplete
                code, lines = self.run_driver("--diagnostic")

                self.assertEqual(code, mp.EXIT_INVALID)
                self.assertEqual(
                    lines["REASON"], "DIAGNOSTIC_CAPTURE_INCOMPLETE"
                )
                self.assertTrue(
                    Path(lines["INVALID_RECORD"]).is_dir()
                )

    def test_dedicated_samples_ignore_printcompilation_prefix(self):
        original = self.fakes.run_logged

        def noisy_stdout(command, log):
            code, out = original(command, log)

            if "measure" in command:
                out = (
                    "2944 sample phase=warmup iteration=1 "
                    "elapsed_ns=13615571\n" + out
                )
                log.write_text(out)

            return code, out

        mp.run_logged = noisy_stdout

        code, lines = self.run_driver("--diagnostic")
        self.assertEqual(code, 0)

        result = Path(lines["RESULT"])
        console = (result / "raw" / "timing.log").read_text()
        samples = (
            result / "raw" / "diagnostic-samples.log"
        ).read_text()
        report = json.loads(
            (result / "diagnostic.json").read_text()
        )

        self.assertIn(
            "2944 sample phase=warmup iteration=1", console
        )
        self.assertNotIn(
            "2944 sample phase=warmup iteration=1", samples
        )
        self.assertIn(
            "sample phase=warmup iteration=1 elapsed_ns=100",
            samples,
        )
        self.assertEqual(report["phases"]["warmup"]["samples"], 2)

    def test_missing_dedicated_samples_invalidates_run(self):
        original = self.fakes.run_logged

        def missing_file(command, log):
            code, out = original(command, log)

            for option in command:
                prefix = "-Dprotos.benchmarks.measure.samplesFile="
                if option.startswith(prefix):
                    Path(option[len(prefix):]).unlink()

            return code, out

        mp.run_logged = missing_file
        code, lines = self.run_driver("--diagnostic")

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(
            lines["REASON"], "DIAGNOSTIC_SAMPLES_MISSING"
        )
        self.assertTrue(
            Path(lines["INVALID_RECORD"]).is_dir()
        )

    def test_jit_capture_requires_diagnostic(self):
        code, _ = self.run_driver("--diagnostic-jit")
        self.assertEqual(code, mp.EXIT_USAGE)
        self.assertEqual(self.fakes.java_calls, [])

    def test_jit_capture_retains_separate_jfr(self):
        synthetic_timeline = {
            "schema": 1,
            "classification": "DIAGNOSTIC_ONLY",
            "event_sample_correlation": "TEMPORAL_OVERLAP_ONLY",
            "jit_maturity": "NOT_PROVEN",
            "windows": [],
        }
        with mock.patch(
            "jit_timeline.analyze_jfr",
            return_value=synthetic_timeline,
        ):
            code, lines = self.run_driver(
                "--diagnostic", "--diagnostic-jit",
                "--stage", "reference",
            )
        self.assertEqual(code, 0)
        self.assertEqual(lines["REFERENCE_ELIGIBLE"], "NO")

        result = Path(lines["RESULT"])
        metadata = json.loads((result / "metadata.json").read_text())
        report = json.loads((result / "diagnostic.json").read_text())
        jit = result / "raw" / "jit-timeline.jfr"

        self.assertTrue(jit.is_file())
        timeline_path = result / "jit-timeline.json"
        self.assertTrue(timeline_path.is_file())
        timeline = json.loads(timeline_path.read_text())
        self.assertEqual(
            timeline["event_sample_correlation"],
            "TEMPORAL_OVERLAP_ONLY",
        )
        self.assertEqual(
            metadata["diagnostic_jit"]["timeline_sha256"],
            __import__("hashlib").sha256(
                timeline_path.read_bytes()
            ).hexdigest(),
        )
        self.assertFalse(metadata["reference_eligible"])
        self.assertEqual(
            metadata["diagnostic_jit"]["sample_event"],
            "protos.benchmarks.SampleWindow",
        )
        self.assertEqual(
            report["jit_capture"]["event_correlation"],
            "TEMPORAL_OVERLAP_ONLY",
        )
        self.assertEqual(report["jit_maturity"], "NOT_PROVEN")

        import hashlib
        self.assertEqual(
            metadata["diagnostic_jit"]["sha256"],
            hashlib.sha256(jit.read_bytes()).hexdigest(),
        )

        correctness = [
            command for command in self.fakes.java_calls
            if "correctness" in command
        ][0]
        timing = [
            command for command in self.fakes.java_calls
            if "measure" in command
        ][0]

        self.assertNotIn("-XX:+PrintCompilation", correctness)
        self.assertIn("-XX:+PrintCompilation", timing)
        self.assertIn(
            "-Dpolyglot.engine.TraceCompilation=true", timing
        )

    def test_jit_capture_rejects_missing_jfr(self):
        original = self.fakes.run_logged

        def without_jfr(command, log):
            code, out = original(command, log)

            if "measure" in command:
                for option in command:
                    prefix = "-Dprotos.benchmarks.measure.jitJfr="
                    if option.startswith(prefix):
                        destination = Path(option[len(prefix):])
                        destination.unlink(missing_ok=True)

            return code, out

        mp.run_logged = without_jfr

        code, lines = self.run_driver(
            "--diagnostic", "--diagnostic-jit"
        )

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(
            lines["REASON"], "DIAGNOSTIC_JIT_JFR_MISSING"
        )
        self.assertTrue(
            Path(lines["INVALID_RECORD"]).is_dir()
        )

    def test_jit_capture_rejects_invalid_timeline(self):
        with mock.patch(
            "jit_timeline.analyze_jfr",
            side_effect=ValueError("JFR windows missing"),
        ):
            code, lines = self.run_driver(
                "--diagnostic", "--diagnostic-jit"
            )

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(
            lines["REASON"], "DIAGNOSTIC_JIT_TIMELINE_INVALID"
        )
        self.assertTrue(
            Path(lines["INVALID_RECORD"]).is_dir()
        )

    def test_affinity_requires_diagnostic_and_cpu_zero(self):
        with mock.patch.object(
            mp.os, "sched_getaffinity", return_value={0, 1}
        ):
            code, _ = self.run_driver(
                "--diagnostic-affinity", "A", "--cpu", "0"
            )
            self.assertEqual(code, mp.EXIT_USAGE)

            code, _ = self.run_driver(
                "--diagnostic",
                "--diagnostic-affinity", "A",
            )
            self.assertEqual(code, mp.EXIT_USAGE)

        self.assertEqual(self.fakes.java_calls, [])

    def test_affinity_profiles_launch_different_cpu_sets(self):
        with mock.patch.object(
            mp.os, "sched_getaffinity", return_value={0, 1}
        ):
            for profile, mask in (("A", "0"), ("C", "0,1")):
                with self.subTest(profile=profile):
                    code, lines = self.run_driver(
                        "--diagnostic", "--cpu", "0",
                        "--diagnostic-affinity", profile,
                    )

                    self.assertEqual(code, 0)

                    result = Path(lines["RESULT"])
                    metadata = json.loads(
                        (result / "metadata.json").read_text()
                    )
                    report = json.loads(
                        (result / "diagnostic.json").read_text()
                    )

                    self.assertFalse(metadata["reference_eligible"])
                    self.assertEqual(
                        metadata["diagnostic_affinity"]["profile"],
                        profile,
                    )
                    self.assertEqual(
                        report["affinity"]["status"], "VERIFIED"
                    )

                    timing = [
                        call for call in self.fakes.java_calls
                        if "measure" in call
                    ][-1]

                    self.assertEqual(timing[:3], [
                        "taskset", "-c", mask,
                    ])
                    self.assertIn(
                        "-Dprotos.benchmarks.measure.affinityProfile="
                        + profile,
                        timing,
                    )

    def test_affinity_c_requires_both_cpus(self):
        with mock.patch.object(
            mp.os, "sched_getaffinity", return_value={0}
        ):
            code, _ = self.run_driver(
                "--diagnostic", "--cpu", "0",
                "--diagnostic-affinity", "C",
            )

        self.assertEqual(code, mp.EXIT_USAGE)
        self.assertEqual(self.fakes.java_calls, [])

    def test_affinity_missing_proof_invalidates_run(self):
        original = self.fakes.run_logged

        def missing_proof(command, log):
            code, out = original(command, log)

            if "measure" in command:
                out = "".join(
                    line for line in out.splitlines(keepends=True)
                    if not line.startswith("MEASURE_THREAD_AFFINITY=")
                )
                log.write_text(out)

            return code, out

        mp.run_logged = missing_proof

        with mock.patch.object(
            mp.os, "sched_getaffinity", return_value={0, 1}
        ):
            code, lines = self.run_driver(
                "--diagnostic", "--cpu", "0",
                "--diagnostic-affinity", "C",
            )

        self.assertEqual(code, mp.EXIT_INVALID)
        self.assertEqual(
            lines["REASON"], "DIAGNOSTIC_AFFINITY_INVALID"
        )
        self.assertTrue(
            Path(lines["INVALID_RECORD"]).is_dir()
        )

    def test_peer_language_needs_no_product(self):
        argv = ["--language", "js", "--workload", WORKLOAD, "--stage", "smoke", "--output", str(self.output)]
        mp.peer_classpath = lambda: ("25.4.4.1.1", "/fake/peer.jar")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = mp.main(argv)
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("SURFACE=executable-value", buffer.getvalue())
        self.assertTrue(any("-Dprotos.benchmarks.peer.language=js" in c for c in self.fakes.java_calls))

    def test_verify_producer(self):
        _, lines = self.run_driver()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = mp.main(["--verify-producer", lines["RESULT"]])
        self.assertEqual(code, 0)
        self.assertIn("WORKING_TREE_MATCHES_PRODUCER=YES", buffer.getvalue())



class ExtremeSampleAdmissionTest(unittest.TestCase):
    def test_ten_samples_around_40_us_pass(self):
        samples = [
            39980, 39990, 40005, 40010, 39995,
            40000, 40015, 39985, 40020, 40002,
        ]
        original = samples.copy()

        result = mp.jvm_matrix.stability_window(samples)
        extreme = result["extreme_sample_check"]

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["shape"]["status"], "PASS")
        self.assertEqual(extreme["status"], "PASS")
        self.assertEqual(extreme["extreme_sample_count"], 0)
        self.assertEqual(samples, original)

    def test_isolated_3000_us_spike_rejected(self):
        samples = [
            39980, 39990, 40005, 40010, 39995,
            40000, 40015, 39985, 40020, 3000000,
        ]

        result = mp.jvm_matrix.stability_window(samples)
        extreme = result["extreme_sample_check"]

        self.assertEqual(result["shape"]["status"], "PASS")
        self.assertEqual(result["status"], "NOT_STABLE")
        self.assertEqual(extreme["status"], "NOT_STABLE")
        self.assertEqual(extreme["extreme_sample_count"], 1)
        self.assertEqual(extreme["extreme_samples"][0]["index"], 9)
        self.assertEqual(
            extreme["extreme_samples"][0]["value_ns"], 3000000
        )
        self.assertGreater(
            3000000, extreme["upper_bound_ns"]
        )

    def test_two_spikes_above_1200_ns_rejected(self):
        samples = [
            328, 332, 330, 329, 331,
            327, 334, 333, 1250, 1275,
        ]

        result = mp.jvm_matrix.stability_window(samples)
        extreme = result["extreme_sample_check"]

        self.assertEqual(result["status"], "NOT_STABLE")
        self.assertEqual(extreme["status"], "NOT_STABLE")
        self.assertEqual(extreme["extreme_sample_count"], 2)
        self.assertEqual(
            [item["value_ns"] for item in extreme["extreme_samples"]],
            [1250, 1275],
        )

    def test_two_distinct_performance_populations_rejected(self):
        samples = [
            1100000, 1100001, 1099999, 1100002, 1099998,
            40000, 40020, 39980, 40010, 39990,
        ]

        result = mp.jvm_matrix.stability_window(samples)
        extreme = result["extreme_sample_check"]

        self.assertEqual(result["status"], "NOT_STABLE")
        self.assertEqual(extreme["status"], "NOT_STABLE")
        self.assertEqual(extreme["extreme_sample_count"], 5)
        self.assertEqual(
            {item["side"] for item in extreme["extreme_samples"]},
            {"below-half-median"},
        )

    def test_stable_1100_us_is_not_compilation_evidence(self):
        samples = [
            1099980, 1100010, 1100005, 1099990, 1100020,
            1099995, 1100015, 1100000, 1099985, 1100002,
        ]

        result = mp.jvm_matrix.stability_window(samples)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(
            result["extreme_sample_check"]["status"], "PASS"
        )
        self.assertNotIn("compiled", result)
        self.assertNotIn("compilation_status", result)

    def test_empty_non_positive_and_insufficient_samples(self):
        check = mp.jvm_matrix.extreme_sample_check

        self.assertEqual(check([])["reason"], "empty-samples")
        self.assertEqual(
            check([100] * 9)["reason"],
            "insufficient-samples",
        )

        for samples in ([0] * 10, [-1] + [100] * 9):
            result = check(samples)
            self.assertEqual(result["status"], "NOT_STABLE")
            self.assertEqual(
                result["reason"],
                "non-positive-or-invalid-samples",
            )

            window = mp.jvm_matrix.stability_window(samples)
            self.assertEqual(window["status"], "NOT_STABLE")
            self.assertEqual(
                window["extreme_sample_check"]["status"],
                "NOT_STABLE",
            )

    def test_exact_ratio_boundaries_are_inclusive(self):
        samples = [100] * 8 + [50, 200]
        original = samples.copy()

        result = mp.jvm_matrix.extreme_sample_check(samples)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["median_ns"], 100.0)
        self.assertEqual(result["lower_bound_ns"], 50.0)
        self.assertEqual(result["upper_bound_ns"], 200.0)
        self.assertEqual(samples, original)


class StaticArchitectureTest(unittest.TestCase):
    def test_canonical_compiles_only_polyglot_adapter(self):
        cases = mp.load_cases()
        surfaces = cases["surfaces"]

        sources = mp.adapter_sources(
            cases, surfaces["canonical"]
        )
        names = {path.name for path in sources}

        self.assertEqual(
            names,
            {
                "MeasurementEngine.java",
                "ProtosCanonicalSurface.java",
                "PolyglotResultInvocation.java",
            },
        )

        support = (
            "measure/surfaces/protos/"
            "ProtosSurfaceSupport.java"
        )

        self.assertNotIn(
            support, surfaces["canonical"]["sources"]
        )
        self.assertIn(
            support, surfaces["dynamic"]["sources"]
        )
        self.assertIn(
            support, surfaces["prepared"]["sources"]
        )

    def test_canonical_adapter_timed_path(self):
        text = (ROOT / "truffle/measure/surfaces/canonical/ProtosCanonicalSurface.java").read_text()
        body = text.split("public static void main", 1)[1]
        self.assertIn('context.getBindings("protos").getMember("run")', body)
        self.assertIn("new PolyglotResultInvocation(run)", body)
        for forbidden in ("prepareTopLevel(", "invokeTopLevel(", "prepared.invoke(", ".enter(", ".leave(", "Lock", "synchronized", "AtomicBoolean", "compareAndSet"):
            self.assertNotIn(forbidden, body)

    def test_shared_polyglot_result_verification(self):
        shared = (
            ROOT
            / "truffle/measure/surfaces/shared/"
            "PolyglotResultInvocation.java"
        ).read_text()

        self.assertIn("Value value = run.execute()", shared)
        self.assertIn("value.fitsInBigInteger()", shared)
        self.assertIn("expectedInteger.equals(actual)", shared)
        self.assertIn("return expectedText;", shared)

        for relative in (
            "canonical/ProtosCanonicalSurface.java",
            "peer/PeerExecutableSurface.java",
        ):
            adapter = (
                ROOT / "truffle/measure/surfaces" / relative
            ).read_text()

            self.assertIn(
                "new PolyglotResultInvocation(run)", adapter
            )
            self.assertNotIn(
                "() -> normalize(run.execute())", adapter
            )

        cases = mp.load_cases()
        shared_source = (
            "measure/surfaces/shared/"
            "PolyglotResultInvocation.java"
        )

        for surface in ("canonical", "executable-value"):
            self.assertIn(
                shared_source,
                cases["surfaces"][surface]["sources"],
            )

        self.assertEqual(
            cases["policy"]["workloads"]["primitive-while-zero"]
            ["reference"]["timing"]["warmup_iterations"],
            150,
        )

    def test_no_reflection_in_adapters(self):
        for path in (ROOT / "truffle/measure").rglob("*.java"):
            text = path.read_text()
            for forbidden in ("java.lang.reflect", "Method.invoke", "MethodHandle", "getMethod("):
                self.assertNotIn(forbidden, text, path)

    def test_driver_has_no_history_machinery(self):
        text = (ROOT / "truffle/measure_protos.py").read_text()
        for forbidden in ('"checkout"', '"clone"', '"reset"', '"worktree"', '"fetch"', "protos-ab"):
            self.assertNotIn(forbidden, text)

    def test_measurement_code_has_no_work_item_branch(self):
        paths = [ROOT / "truffle/measure_protos.py", *(ROOT / "truffle/measure").rglob("*.java")]
        for path in paths:
            text = path.read_text().upper()
            self.assertNotRegex(text, r"PERF\d{3}", path)


if __name__ == "__main__":
    unittest.main()
