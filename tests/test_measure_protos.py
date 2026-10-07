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

    def run_driver(self, *extra: str, product: Path | None = None, surface: str = "canonical"):
        argv = [
            "--dir", str(product or self.product),
            "--surface", surface,
            "--workload", WORKLOAD,
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
            self.assertEqual(
                (timing["warmup_iterations"], timing["steady_iterations"], timing["sample_calls"], timing["admission_scope"]),
                (50, 10, 10000, "steady-only"),
                workload,
            )

    def test_reference_stage_admits_and_is_eligible(self):
        code, lines = self.run_driver("--stage", "reference")
        self.assertEqual(code, 0)
        self.assertEqual(lines["STEADY_STATE_ADMISSION"], "PASS")
        self.assertTrue(self.metadata(lines)["reference_eligible"])

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

    def test_diagnostic_jvm_option_recorded_and_not_eligible(self):
        code, lines = self.run_driver("--stage", "reference", "--jvm-option=-Xlog:gc")
        self.assertEqual(code, 0)
        metadata = self.metadata(lines)
        self.assertEqual(metadata["result_key"]["diagnostic_jvm_options"], ["-Xlog:gc"])
        self.assertFalse(metadata["reference_eligible"])
        timing = [c for c in self.fakes.java_calls if "measure" in c][0]
        self.assertIn("-Xlog:gc", timing)

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


class StaticArchitectureTest(unittest.TestCase):
    def test_canonical_adapter_timed_path(self):
        text = (ROOT / "truffle/measure/surfaces/canonical/ProtosCanonicalSurface.java").read_text()
        body = text.split("public static void main", 1)[1]
        self.assertIn("prepared.executable()", body)
        self.assertIn("() -> normalize(executable.execute())", body)
        for forbidden in ("invokeTopLevel(", "prepared.invoke(", ".enter(", ".leave(", "Lock", "synchronized", "AtomicBoolean", "compareAndSet"):
            self.assertNotIn(forbidden, body)

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
