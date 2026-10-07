#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Revision-independent Protos measurement driver.

The harness is a measuring instrument; a Protos revision is data. This driver
measures exactly the checkout given by ``--dir`` and never obtains another
product revision: it has no revision/commit/tag/checkout option and runs only
read-only Git commands (see ``GIT_READ_ONLY``).

Flow for one batch:

    identify product (HEAD, version, clean state, Core hash)
      -> identify harness producer (Git HEAD, dirty, exact source hashes)
      -> skip if an equivalent valid result already exists (unless --remeasure)
      -> build product classes / resolve classpath
      -> compile the selected surface adapter against that classpath
         (cached under .work/embedded; the cache is never evidence)
      -> correctness -> timing -> optional steady-bounded JFR
      -> re-verify product and harness identity
      -> atomically promote a staging directory into the output

Surfaces, workloads and measurement policy are data (``measure/cases.json``
and ``workloads/catalog.json``). A new Protos revision never requires editing
this file or any adapter source.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import jvm_matrix
import jvm_runtime
import workload_catalog

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
CASES = TRUFFLE / "measure" / "cases.json"
EMBEDDED_CACHE = ROOT / ".work" / "embedded"

SCHEMA_VERSION = 1
OUTPUT_MARKER = ".measure-protos-output"
STAGING = ".staging"
STAGES = ("reference", "smoke")
PROFILES = ("none", "jfr")
PEER_LANGUAGES = ("js", "python")
ADMISSION_SCOPES = ("warmup-and-steady", "steady-only")

# The only Git subcommands this driver may run. None of them changes a
# working tree, an index or a ref; in particular checkout, reset, clone,
# fetch, worktree, switch, restore, stash and clean are impossible here.
GIT_READ_ONLY = frozenset({"rev-parse", "status", "diff", "ls-files", "show"})

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_SURFACE_UNSUPPORTED = 3


class UsageError(Exception):
    pass


class SurfaceUnsupported(Exception):
    def __init__(self, surface: str, reason: str) -> None:
        super().__init__(reason)
        self.surface = surface
        self.reason = reason


class InvalidMeasurement(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------------------
# Small helpers


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return jvm_runtime.sha256_file(path)


def sha256_json(value: object) -> str:
    return sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def emit(key: str, value: object) -> None:
    print(f"{key}={value}", flush=True)


def git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    if not args or args[0] not in GIT_READ_ONLY:
        raise RuntimeError(
            "refusing non-read-only git command: git " + " ".join(args)
        )

    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if binary:
        return result.stdout

    return result.stdout.decode("utf-8", "replace").strip()


def capture_text(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Case catalog and policy (data, not code)


def load_cases() -> dict[str, object]:
    data = json.loads(CASES.read_text(encoding="utf-8"))

    if data.get("schema") != 1:
        raise RuntimeError(f"unsupported cases schema in {CASES}")

    return data


def surface_definition(
    cases: dict[str, object],
    surface: str,
) -> dict[str, object]:
    surfaces = cases["surfaces"]
    assert isinstance(surfaces, dict)

    if surface not in surfaces:
        raise UsageError(
            f"unknown surface {surface!r}; expected one of "
            + ", ".join(sorted(surfaces))
        )

    return surfaces[surface]


def resolve_policy(
    cases: dict[str, object],
    workload: str,
    stage: str,
    kind: str,
    overrides: dict[str, int | None],
) -> dict[str, object]:
    """Merges default and per-workload policy for one stage/kind.

    ``sample_calls`` falls back to the workload catalog's
    ``jvm_sample_calls`` when the case policy does not set it.
    """
    policy = cases["policy"]
    assert isinstance(policy, dict)

    merged: dict[str, object] = {}
    merged.update(policy["default"][stage][kind])
    merged.update(
        policy.get("workloads", {})
        .get(workload, {})
        .get(stage, {})
        .get(kind, {})
    )

    if "sample_calls" not in merged:
        merged["sample_calls"] = workload_catalog.jvm_sample_calls(workload)

    source = "case-policy"

    for name, value in overrides.items():
        if value is not None:
            merged[name] = value
            source = "cli-override"

    for name in ("warmup_iterations", "steady_iterations", "sample_calls"):
        value = merged.get(name)
        minimum = 0 if name == "warmup_iterations" else 1

        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise UsageError(f"invalid {kind} policy {name}={value!r}")

    result = {
        "warmup_iterations": merged["warmup_iterations"],
        "steady_iterations": merged["steady_iterations"],
        "sample_calls": merged["sample_calls"],
        "source": source,
    }

    if kind == "timing":
        scope = merged.get("admission_scope", "warmup-and-steady")

        if scope not in ADMISSION_SCOPES:
            raise UsageError(f"invalid timing policy admission_scope={scope!r}")

        result["admission_scope"] = scope

    return result


# ---------------------------------------------------------------------------
# Product identity


def maven_project(repo: Path) -> dict[str, str]:
    version, graalvm_version = jvm_runtime.project_properties(repo)

    root = ET.parse(repo / "pom.xml").getroot()
    namespace = root.tag.split("}", 1)[0] + "}" if root.tag.startswith("{") else ""
    release = root.findtext(
        f"{namespace}properties/{namespace}maven.compiler.release", ""
    ).strip()

    return {
        "version": version,
        "graalvm_version": graalvm_version,
        "maven_compiler_release": release,
    }


def source_state(repo: Path) -> dict[str, object]:
    """Tracked and untracked source state of a checkout.

    Ignored build output (for example ``target/``) is outside this state, so
    building the product does not change it.
    """
    head = str(git(repo, "rev-parse", "HEAD"))
    porcelain = str(git(repo, "status", "--porcelain", "--untracked-files=all"))
    tracked_diff = git(repo, "diff", "HEAD", "--binary", binary=True)
    untracked = [
        line
        for line in str(
            git(repo, "ls-files", "--others", "--exclude-standard")
        ).splitlines()
        if line
    ]

    digest = hashlib.sha256()
    digest.update(head.encode() + b"\0")
    digest.update(porcelain.encode() + b"\0")
    digest.update(tracked_diff + b"\0")

    for name in sorted(untracked):
        digest.update(name.encode() + b"\0")
        path = repo / name

        if path.is_file():
            digest.update(path.read_bytes())

        digest.update(b"\0")

    return {
        "head": head,
        "clean": not porcelain,
        "porcelain": porcelain,
        "state_sha256": digest.hexdigest(),
    }


def product_identity(repo: Path) -> dict[str, object]:
    if not (repo / ".git").exists():
        raise UsageError(f"--dir is not a Git checkout: {repo}")

    if not (repo / "pom.xml").is_file():
        raise UsageError(f"--dir has no pom.xml: {repo}")

    core = repo / "protos" / "lib" / "core"

    if not core.is_dir():
        raise UsageError(f"--dir has no Protos Core at {core}")

    state = source_state(repo)

    return {
        "directory": str(repo),
        "revision": state["head"],
        "clean": state["clean"],
        "porcelain": state["porcelain"],
        "source_state_sha256": state["state_sha256"],
        **maven_project(repo),
        "pom_sha256": sha256_file(repo / "pom.xml"),
        "core_root": str(core),
        "core_sha256": jvm_runtime.sha256_tree(core),
    }


def compare_product(
    before: dict[str, object],
    after: dict[str, object],
) -> list[str]:
    return [
        name
        for name in (
            "revision",
            "source_state_sha256",
            "version",
            "pom_sha256",
            "core_sha256",
        )
        if before.get(name) != after.get(name)
    ]


# ---------------------------------------------------------------------------
# Harness producer identity


def producer_files(
    cases: dict[str, object],
    surface_def: dict[str, object],
    workload: str,
    language: str,
) -> list[Path]:
    files = [
        Path(__file__).resolve(),
        TRUFFLE / "jvm_matrix.py",
        TRUFFLE / "jvm_runtime.py",
        TRUFFLE / "workload_catalog.py",
        TRUFFLE / "workloads" / "catalog.json",
        CASES,
        *(TRUFFLE / item for item in cases["engine_sources"]),
        *(TRUFFLE / item for item in surface_def["sources"]),
        workload_catalog.source_for(workload, language),
    ]

    if surface_def["classpath"] == "peer":
        files.append(TRUFFLE / "pom.xml")

    return sorted(set(path.resolve() for path in files))


def producer_name(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def producer_hashes(files: list[Path]) -> dict[str, str]:
    return {producer_name(path): sha256_file(path) for path in files}


def harness_identity(files: list[Path]) -> dict[str, object]:
    status = str(git(ROOT, "status", "--porcelain", "--untracked-files=all"))

    return {
        "git_head": str(git(ROOT, "rev-parse", "HEAD")),
        "dirty": bool(status),
        "porcelain": status,
        "source_sha256": producer_hashes(files),
    }


# ---------------------------------------------------------------------------
# Runtime and host identity


def java_identity() -> dict[str, str]:
    version = capture_text(["java", "-version"])
    settings = capture_text(["java", "-XshowSettings:properties", "-version"])
    properties: dict[str, str] = {}

    for line in settings.splitlines():
        stripped = line.strip()

        if " = " in stripped:
            name, value = stripped.split(" = ", 1)

            if name in {
                "java.home",
                "java.runtime.version",
                "java.vendor.version",
                "java.vm.name",
                "java.vm.version",
            }:
                properties[name] = value

    return {"version_output": version, **properties}


def choose_cpu(requested: int | None) -> tuple[int, list[int], list[int]]:
    allowed = sorted(os.sched_getaffinity(0))

    if requested is None:
        cpu = allowed[0]
    elif requested not in allowed:
        raise UsageError(f"--cpu {requested} is outside affinity {allowed}")
    else:
        cpu = requested

    siblings_file = Path(
        f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list"
    )
    siblings = (
        sorted(jvm_matrix.parse_cpu_list(siblings_file.read_text()))
        if siblings_file.exists()
        else [cpu]
    )

    return cpu, siblings, allowed


def host_identity(cpu: int, siblings: list[int], allowed: list[int]) -> dict[str, object]:
    return {
        "os": platform.system(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
        "cpu_model": jvm_matrix.cpu_model(),
        "cpu": cpu,
        "cpu_siblings": siblings,
        "process_affinity": allowed,
        "affinity_policy": "taskset -c <cpu>",
        "container": Path("/.dockerenv").exists()
        or Path("/run/.containerenv").exists(),
    }


# ---------------------------------------------------------------------------
# Classpaths and adapter compilation


def build_product(repo: Path, log: Path) -> tuple[Path, str]:
    """Compiles product classes into the checkout's ignored target/ output
    and resolves its dependency classpath. Never edits tracked files."""
    with log.open("a", encoding="utf-8") as stream:
        result = subprocess.run(
            ["mvn", "-q", "-f", str(repo / "pom.xml"), "-DskipTests", "compile"],
            cwd=ROOT,
            text=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )

    if result.returncode != 0:
        raise InvalidMeasurement("PRODUCT_BUILD_FAILED", str(log))

    classes = repo / "target" / "classes"

    if not classes.is_dir():
        raise InvalidMeasurement("PRODUCT_CLASSES_MISSING", str(classes))

    cp_file = (
        EMBEDDED_CACHE
        / "classpath"
        / f"{sha256_file(repo / 'pom.xml')}.txt"
    )

    if not cp_file.is_file():
        cp_file.parent.mkdir(parents=True, exist_ok=True)
        partial = cp_file.with_suffix(".partial")

        with log.open("a", encoding="utf-8") as stream:
            result = subprocess.run(
                [
                    "mvn",
                    "-q",
                    "-f",
                    str(repo / "pom.xml"),
                    "dependency:build-classpath",
                    f"-Dmdep.outputFile={partial}",
                ],
                cwd=ROOT,
                text=True,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )

        if result.returncode != 0 or not partial.is_file():
            raise InvalidMeasurement("PRODUCT_CLASSPATH_FAILED", str(log))

        partial.replace(cp_file)

    dependency_cp = cp_file.read_text(encoding="utf-8").strip()

    if not dependency_cp:
        raise InvalidMeasurement("PRODUCT_CLASSPATH_EMPTY", str(cp_file))

    return classes, dependency_cp


def peer_classpath() -> tuple[str, str]:
    """Dependency classpath of the harness-pinned GraalJS/GraalPy peers."""
    version = jvm_runtime.harness_graalvm_version()
    peer_root = EMBEDDED_CACHE / "peer-classpath" / version
    peer_root.mkdir(parents=True, exist_ok=True)

    pom = peer_root / "pom.xml"
    expected = jvm_runtime.peer_pom(version)

    if not pom.is_file() or pom.read_text(encoding="utf-8") != expected:
        pom.write_text(expected, encoding="utf-8")

    cp_file = peer_root / "classpath.txt"

    if not cp_file.is_file():
        subprocess.run(
            [
                "mvn",
                "-q",
                "-f",
                str(pom),
                "dependency:build-classpath",
                f"-Dmdep.outputFile={cp_file}",
            ],
            cwd=ROOT,
            check=True,
        )

    dependency_cp = cp_file.read_text(encoding="utf-8").strip()

    if not dependency_cp:
        raise InvalidMeasurement("PEER_CLASSPATH_EMPTY", str(cp_file))

    return version, dependency_cp


def adapter_sources(
    cases: dict[str, object],
    surface_def: dict[str, object],
) -> list[Path]:
    return [
        TRUFFLE / item
        for item in [*cases["engine_sources"], *surface_def["sources"]]
    ]


def adapter_source_sha256(sources: list[Path]) -> str:
    return sha256_json(
        {str(path.relative_to(TRUFFLE)): sha256_file(path) for path in sources}
    )


def run_javac(classpath: str, sources: list[Path], destination: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "javac",
            "-proc:none",
            "-d",
            str(destination),
            "-cp",
            classpath,
            *map(str, sources),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def class_file(classes: Path, main_class: str) -> Path:
    return classes / (main_class.replace(".", "/") + ".class")


def compile_adapter(
    surface: str,
    surface_def: dict[str, object],
    sources: list[Path],
    owner: str,
    compile_classpath: str,
    identity: dict[str, object],
) -> dict[str, object]:
    """Returns the cache entry for one surface adapter, compiling it when
    the exact entry is absent or does not validate.

    ``owner`` is the Protos revision (or a peer runtime label); ``identity``
    holds every material input. The cache is disposable: deleting it loses
    no evidence, and it never holds product sources.
    """
    source_sha = adapter_source_sha256(sources)
    entry = EMBEDDED_CACHE / owner / surface / source_sha
    classes = entry / "classes"
    stamp = entry / "identity.json"
    expected = {
        **identity,
        "surface": surface,
        "adapter_source_sha256": source_sha,
        "main_class": surface_def["main_class"],
    }
    main_class_file = class_file(classes, str(surface_def["main_class"]))

    if stamp.is_file() and main_class_file.is_file():
        try:
            if json.loads(stamp.read_text(encoding="utf-8")) == expected:
                return {
                    "status": "reused",
                    "path": str(entry),
                    "classes": classes,
                    "identity_sha256": sha256_json(expected),
                    "adapter_source_sha256": source_sha,
                    "classes_sha256": jvm_runtime.sha256_tree(classes),
                }
        except json.JSONDecodeError:
            pass

    shutil.rmtree(entry, ignore_errors=True)
    entry.mkdir(parents=True, exist_ok=True)
    building = entry / "classes.partial"
    building.mkdir()

    result = run_javac(compile_classpath, sources, building)

    if result.returncode != 0:
        shutil.rmtree(entry, ignore_errors=True)
        errors = [
            line.strip()
            for line in result.stdout.splitlines()
            if "error:" in line or "symbol:" in line or "location:" in line
        ]
        raise SurfaceUnsupported(
            surface,
            " | ".join(errors[:6]) or result.stdout.strip()[:500],
        )

    building.rename(classes)

    if not main_class_file.is_file():
        raise InvalidMeasurement("ADAPTER_CLASS_MISSING", str(main_class_file))

    write_json(stamp, expected)

    return {
        "status": "compiled",
        "path": str(entry),
        "classes": classes,
        "identity_sha256": sha256_json(expected),
        "adapter_source_sha256": source_sha,
        "classes_sha256": jvm_runtime.sha256_tree(classes),
    }


# ---------------------------------------------------------------------------
# Process execution


def java_command(
    runtime_classpath: str,
    main_class: str,
    system_properties: list[str],
    jvm_options: list[str],
    arguments: list[str],
    cpu: int | None,
) -> list[str]:
    command = [
        "java",
        *jvm_options,
        *system_properties,
        "-cp",
        runtime_classpath,
        main_class,
        *arguments,
    ]

    if cpu is None:
        return command

    return ["taskset", "-c", str(cpu), *command]


def run_logged(command: list[str], log: Path) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "$ " + " ".join(command) + "\n" + result.stdout,
        encoding="utf-8",
    )
    return result.returncode, result.stdout


def output_result(output: str) -> str | None:
    value = None

    for line in output.splitlines():
        if line.startswith("result="):
            value = line.split("=", 1)[1]

    return value


def timing_summary(parsed: dict[str, object]) -> dict[str, object]:
    steady = [int(value) for value in parsed["steady_ns"]]
    sample_calls = int(parsed["sample_calls"])
    p50 = float(statistics.median(steady))

    return {
        "setup_ns": parsed["setup_ns"],
        "cold_ns": parsed["cold_ns"],
        "warmup_ns": parsed["warmup_ns"],
        "steady_ns": steady,
        "sample_calls": sample_calls,
        "steady_p50_ns": p50,
        "steady_min_ns": min(steady),
        "steady_max_ns": max(steady),
        "steady_amortized_p50_ns_per_call": p50 / sample_calls,
    }


# ---------------------------------------------------------------------------
# Output directory management


def prepare_output(output: Path) -> None:
    marker = output / OUTPUT_MARKER

    if output.exists():
        if not output.is_dir():
            raise UsageError(f"--output is not a directory: {output}")

        if any(output.iterdir()) and not marker.is_file():
            raise UsageError(
                "--output exists, is not empty and was not created by "
                f"measure_protos.py; refusing to write into it: {output}"
            )

    output.mkdir(parents=True, exist_ok=True)

    if not marker.is_file():
        marker.write_text(
            "Created by truffle/measure_protos.py. "
            "Each <case>/<run-id>/metadata.json is authoritative.\n",
            encoding="utf-8",
        )


def case_id(language: str, surface: str, workload: str, stage: str, profile: str) -> str:
    return f"{language}-{surface}--{workload}--{stage}-{profile}"


def find_existing(output: Path, case: str, result_key: dict[str, object]) -> Path | None:
    case_dir = output / case

    if not case_dir.is_dir():
        return None

    for run_dir in sorted(case_dir.iterdir()):
        metadata_file = run_dir / "metadata.json"

        if run_dir.name.endswith(".invalid") or not metadata_file.is_file():
            continue

        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        if (
            metadata.get("measurement_valid") is True
            and metadata.get("result_key") == result_key
        ):
            return run_dir

    return None


def promote(staging: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    final = destination
    suffix = 1

    while final.exists():
        suffix += 1
        final = destination.with_name(f"{destination.name}-{suffix}")

    staging.rename(final)
    return final


# ---------------------------------------------------------------------------
# Producer verification for publication


def verify_producer(run_dir: Path) -> int:
    if not (run_dir / "metadata.json").is_file():
        raise UsageError(f"not a measurement run directory: {run_dir}")

    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    recorded = metadata["harness"]["source_sha256"]
    working_mismatch = []
    head_mismatch = []

    for relative, expected in sorted(recorded.items()):
        path = ROOT / relative

        if not path.is_file() or sha256_file(path) != expected:
            working_mismatch.append(relative)

        try:
            blob = git(ROOT, "show", f"HEAD:{relative}", binary=True)
        except subprocess.CalledProcessError:
            head_mismatch.append(relative)
            continue

        if sha256_bytes(blob) != expected:
            head_mismatch.append(relative)

    emit("RUN", run_dir)
    emit("MEASUREMENT_VALID", "YES" if metadata.get("measurement_valid") else "NO")
    emit("PRODUCER_FILES", len(recorded))
    emit("WORKING_TREE_MATCHES_PRODUCER", "NO" if working_mismatch else "YES")

    for relative in working_mismatch:
        emit("WORKING_TREE_MISMATCH", relative)

    emit("HEAD_MATCHES_PRODUCER", "NO" if head_mismatch else "YES")

    for relative in head_mismatch:
        emit("HEAD_MISMATCH", relative)

    return EXIT_OK if not working_mismatch else EXIT_INVALID


# ---------------------------------------------------------------------------
# Batch


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="measure_protos.py",
        description=(
            "Measure exactly the Protos checkout given by --dir. "
            "There is deliberately no option to select a Protos revision."
        ),
    )
    parser.add_argument("--dir", type=Path, help="Protos checkout to measure")
    parser.add_argument("--output", type=Path, help="result directory")
    parser.add_argument(
        "--language",
        default="protos",
        choices=("protos", *PEER_LANGUAGES),
    )
    parser.add_argument(
        "--surface",
        help="Protos surface (dynamic, prepared, canonical); "
        "peers always use executable-value",
    )
    parser.add_argument("--workload")
    parser.add_argument("--stage", default="reference", choices=STAGES)
    parser.add_argument("--profile", default="none", choices=PROFILES)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--warmup", type=int, help="diagnostic override")
    parser.add_argument("--steady", type=int, help="diagnostic override")
    parser.add_argument("--sample-calls", type=int, help="diagnostic override")
    parser.add_argument(
        "--jvm-option",
        action="append",
        default=[],
        help="diagnostic JVM option for the timing run (repeatable; "
        "recorded; never reference-eligible)",
    )
    parser.add_argument(
        "--remeasure",
        action="store_true",
        help="measure again even if an equivalent valid result exists; "
        "the existing result is kept",
    )
    parser.add_argument(
        "--allow-dirty-product",
        action="store_true",
        help="allow a dirty Protos checkout (never reference-eligible)",
    )
    parser.add_argument(
        "--verify-producer",
        type=Path,
        metavar="RUN_DIR",
        help="only check that the harness files match a run's producer hashes",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if args.verify_producer is not None:
            return verify_producer(args.verify_producer.resolve())

        return measure(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except SurfaceUnsupported as exc:
        emit("SURFACE_SUPPORTED", "NO")
        emit("SURFACE", exc.surface)
        emit("REASON", exc.reason)
        return EXIT_SURFACE_UNSUPPORTED


def measure(args: argparse.Namespace) -> int:
    if args.output is None or args.workload is None:
        raise UsageError("--output and --workload are required")

    cases = load_cases()

    try:
        workload_catalog.select_workloads(args.workload)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc

    if args.workload == "all":
        raise UsageError("--workload must name exactly one workload")

    language = args.language

    if language == "protos":
        surface = args.surface or "canonical"
        surface_def = surface_definition(cases, surface)

        if surface_def["language"] != "protos":
            raise UsageError(f"surface {surface!r} is not a Protos surface")

        if args.dir is None:
            raise UsageError("--dir is required for --language protos")
    else:
        surface = args.surface or "executable-value"
        surface_def = surface_definition(cases, surface)

        if surface_def["language"] != "peer":
            raise UsageError(f"surface {surface!r} is not a peer surface")

    product_dir = args.dir.expanduser().resolve() if args.dir is not None else None
    output = args.output.expanduser().resolve()
    overrides = {
        "warmup_iterations": args.warmup,
        "steady_iterations": args.steady,
        "sample_calls": args.sample_calls,
    }
    timing_policy = resolve_policy(cases, args.workload, args.stage, "timing", overrides)
    jfr_policy = (
        resolve_policy(cases, args.workload, args.stage, "jfr", overrides)
        if args.profile == "jfr"
        else None
    )
    expected = workload_catalog.expected_result(args.workload)
    source_language = "protos" if language == "protos" else language
    workload_source = workload_catalog.source_for(args.workload, source_language)

    # Product identity immediately before the batch.
    product_before = product_identity(product_dir) if product_dir is not None else None

    if product_before is not None and not product_before["clean"] and not args.allow_dirty_product:
        raise UsageError(
            "Protos checkout is dirty; accepted reference evidence requires a "
            "clean checkout (use --allow-dirty-product only for diagnostics):\n"
            + str(product_before["porcelain"])
        )

    files = producer_files(cases, surface_def, args.workload, source_language)
    harness_before = harness_identity(files)

    result_key = {
        "language": language,
        "surface": surface,
        "workload": args.workload,
        "stage": args.stage,
        "profile": args.profile,
        "protos_revision": product_before["revision"] if product_before else None,
        "protos_source_state_sha256": (
            product_before["source_state_sha256"] if product_before else None
        ),
        "timing_policy": timing_policy,
        "jfr_policy": jfr_policy,
        "diagnostic_jvm_options": list(args.jvm_option),
    }

    prepare_output(output)
    case = case_id(language, surface, args.workload, args.stage, args.profile)
    existing = find_existing(output, case, result_key)

    emit("PRODUCT_DIRECTORY", product_dir or "-")

    if product_before is not None:
        emit("PROTOS_REVISION", product_before["revision"])
        emit("PROTOS_VERSION", product_before["version"])
        emit("PROTOS_CLEAN", "YES" if product_before["clean"] else "NO")

    emit("LANGUAGE", language)
    emit("SURFACE", surface)
    emit("WORKLOAD", args.workload)
    emit("STAGE", args.stage)
    emit("PROFILE", args.profile)
    emit("HARNESS_GIT_HEAD", harness_before["git_head"])
    emit("HARNESS_DIRTY", "YES" if harness_before["dirty"] else "NO")

    if existing is not None and not args.remeasure:
        emit("RESULT_ALREADY_EXISTS", "YES")
        emit("RESULT", existing)
        return EXIT_OK

    emit("RESULT_ALREADY_EXISTS", "YES (remeasuring)" if existing else "NO")

    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ")
    staging = output / STAGING / f"{case}--{run_id}"
    staging.mkdir(parents=True)
    raw = staging / "raw"
    raw.mkdir()

    cpu, siblings, allowed = choose_cpu(args.cpu)
    metadata: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "measurement_valid": False,
        "measurement_timestamp": started.isoformat(),
        "run_id": run_id,
        "case": case,
        "result_key": result_key,
        "product_directory": str(product_dir) if product_dir else None,
        "product_before": product_before,
        "protos_revision": result_key["protos_revision"],
        "protos_version": product_before["version"] if product_before else None,
        "protos_clean": product_before["clean"] if product_before else None,
        "language": language,
        "surface": surface,
        "surface_timed_call": surface_def["timed_call"],
        "workload": args.workload,
        "workload_source": producer_name(workload_source),
        "expected_result": expected,
        "stage": args.stage,
        "profile": args.profile,
        "timing_policy": timing_policy,
        "jfr_policy": jfr_policy,
        "harness": harness_before,
        "harness_git_head": harness_before["git_head"],
        "harness_dirty": harness_before["dirty"],
        "java": java_identity(),
        "host": host_identity(cpu, siblings, allowed),
    }
    summary: dict[str, object] = {"case": case, "expected_result": expected}

    try:
        metadata["reference_eligible"] = (
            args.stage == "reference"
            and timing_policy["source"] == "case-policy"
            and not args.jvm_option
            and (product_before is None or bool(product_before["clean"]))
        )

        # Classpath of the exact runtime being measured.
        if language == "protos":
            assert product_dir is not None and product_before is not None
            classes, dependency_cp = build_product(product_dir, raw / "product-build.log")
            product_classes_sha = jvm_runtime.sha256_tree(classes)
            compile_cp = os.pathsep.join([str(classes), dependency_cp])
            owner = str(product_before["revision"])
            cache_identity = {
                "protos_revision": product_before["revision"],
                "protos_source_state_sha256": product_before["source_state_sha256"],
                "product_classes_sha256": product_classes_sha,
                "dependency_classpath_sha256": sha256_bytes(dependency_cp.encode()),
                "java_home": metadata["java"].get("java.home"),
                "java_runtime_version": metadata["java"].get("java.runtime.version"),
            }
            metadata["product_classes_sha256"] = product_classes_sha
            metadata["dependency_classpath_sha256"] = cache_identity[
                "dependency_classpath_sha256"
            ]
            system_properties: list[str] = []
            core_arg = str(product_before["core_root"])
        else:
            peer_version, dependency_cp = peer_classpath()
            classes = None
            compile_cp = dependency_cp
            owner = f"peer-{peer_version}"
            cache_identity = {
                "peer_graalvm_version": peer_version,
                "dependency_classpath_sha256": sha256_bytes(dependency_cp.encode()),
                "java_home": metadata["java"].get("java.home"),
                "java_runtime_version": metadata["java"].get("java.runtime.version"),
            }
            metadata["peer_runtime"] = {
                "graalvm_version": peer_version,
                "dependency_classpath_sha256": cache_identity[
                    "dependency_classpath_sha256"
                ],
                "protos_graalvm_version": (
                    product_before["graalvm_version"] if product_before else None
                ),
            }
            system_properties = [f"-Dprotos.benchmarks.peer.language={language}"]
            core_arg = "-"

        sources = adapter_sources(cases, surface_def)
        adapter = compile_adapter(
            surface, surface_def, sources, owner, compile_cp, cache_identity
        )
        emit("SURFACE_SUPPORTED", "YES")
        emit("ADAPTER_CACHE", adapter["status"])
        emit("ADAPTER_CACHE_PATH", adapter["path"])
        metadata["adapter_source_sha256"] = adapter["adapter_source_sha256"]
        metadata["compiled_driver_cache"] = {
            "status": adapter["status"],
            "path": adapter["path"],
            "identity": {**cache_identity, "surface": surface},
            "identity_sha256": adapter["identity_sha256"],
            "classes_sha256": adapter["classes_sha256"],
            "is_evidence": False,
        }

        runtime_cp = os.pathsep.join(
            [str(adapter["classes"]), *([str(classes)] if classes else []), dependency_cp]
        )
        main_class = str(surface_def["main_class"])

        # 1. Correctness, before any timing.
        code, out = run_logged(
            java_command(
                runtime_cp,
                main_class,
                system_properties,
                [],
                ["correctness", core_arg, str(workload_source)],
                None,
            ),
            raw / "correctness.log",
        )
        actual = output_result(out) if code == 0 else None
        correctness = "PASS" if actual == expected else "FAIL"
        metadata["correctness"] = {"result": correctness, "actual": actual, "exit_code": code}
        emit("CORRECTNESS", correctness)

        if correctness != "PASS":
            raise InvalidMeasurement(
                "CORRECTNESS_FAILED", f"expected {expected}, got {actual!r}"
            )

        # 2. Timing, without instrumentation unless diagnostic options
        # were requested explicitly.
        code, out = run_logged(
            java_command(
                runtime_cp,
                main_class,
                system_properties,
                list(args.jvm_option),
                [
                    "measure",
                    core_arg,
                    str(workload_source),
                    str(timing_policy["warmup_iterations"]),
                    str(timing_policy["steady_iterations"]),
                    str(timing_policy["sample_calls"]),
                    "-",
                ],
                cpu,
            ),
            raw / "timing.log",
        )
        parsed = jvm_matrix.parse_output(out) if code == 0 else None

        if parsed is None or parsed["result"] != expected:
            raise InvalidMeasurement("TIMING_RUN_FAILED", str(raw / "timing.log"))

        timing = timing_summary(parsed)

        if args.stage == "reference":
            scope = timing_policy["admission_scope"]
            admission = jvm_matrix.reference_admission(
                timing["warmup_ns"], timing["steady_ns"]
            )

            if scope == "steady-only":
                admission["status"] = admission["steady"]["status"]

            admission["scope"] = scope
        else:
            admission = {"status": "N/A", "reason": "smoke-stage"}

        timing["admission"] = admission
        summary["timing"] = timing
        emit("STEADY_P50_NS_PER_CALL", f"{timing['steady_amortized_p50_ns_per_call']:.3f}")
        emit("STEADY_STATE_ADMISSION", admission["status"])

        if args.stage == "reference" and admission["status"] != "PASS":
            raise InvalidMeasurement("NOT_STEADY_STATE_ADMITTED")

        # 3. Optional profile: same checkout, adapter, workload and case.
        if jfr_policy is not None:
            jfr_dir = staging / "jfr"
            jfr_dir.mkdir()
            recording = jfr_dir / "steady.jfr"
            jfr_options = list(cases.get("jfr_jvm_options", []))
            code, out = run_logged(
                java_command(
                    runtime_cp,
                    main_class,
                    system_properties,
                    jfr_options,
                    [
                        "measure",
                        core_arg,
                        str(workload_source),
                        str(jfr_policy["warmup_iterations"]),
                        str(jfr_policy["steady_iterations"]),
                        str(jfr_policy["sample_calls"]),
                        str(recording),
                    ],
                    cpu,
                ),
                raw / "jfr.log",
            )

            if (
                code != 0
                or output_result(out) != expected
                or "jfr_scope=steady" not in out
                or not recording.is_file()
            ):
                raise InvalidMeasurement("JFR_RUN_FAILED", str(raw / "jfr.log"))

            summary["jfr"] = {
                "file": str(recording.relative_to(staging)),
                "sha256": sha256_file(recording),
                "scope": "steady",
                "boundary": "engine starts jdk.jfr.Recording before the first "
                "steady iteration and stops it after the last",
                "jvm_options": jfr_options,
                "policy": jfr_policy,
                "timing_is_separate_run": True,
            }
            emit("JFR", "RECORDED")

        # 4. Identity after the complete batch.
        if product_dir is not None:
            product_after = product_identity(product_dir)
            metadata["product_after"] = product_after
            changed = compare_product(product_before, product_after)

            if language == "protos":
                classes_after = jvm_runtime.sha256_tree(classes)

                if classes_after != metadata["product_classes_sha256"]:
                    changed.append("product_classes_sha256")

            if changed:
                raise InvalidMeasurement(
                    "PRODUCT_CHANGED_DURING_MEASUREMENT", ",".join(changed)
                )

        harness_after = producer_hashes(files)
        metadata["harness_after_source_sha256"] = harness_after

        if harness_after != harness_before["source_sha256"]:
            changed = sorted(
                name
                for name in set(harness_after) | set(harness_before["source_sha256"])
                if harness_after.get(name) != harness_before["source_sha256"].get(name)
            )
            raise InvalidMeasurement(
                "HARNESS_CHANGED_DURING_MEASUREMENT", ",".join(changed)
            )

        finished = utc_now()
        metadata["measurement_finished"] = finished.isoformat()
        metadata["measurement_valid"] = True
        summary["measurement_valid"] = True
        write_json(staging / "summary.json", summary)
        write_json(staging / "metadata.json", metadata)
        final = promote(staging, output / case / run_id)
        emit("MEASUREMENT_VALID", "YES")
        emit("RESULT", final)
        return EXIT_OK

    except (InvalidMeasurement, SurfaceUnsupported) as exc:
        if isinstance(exc, SurfaceUnsupported):
            reason, detail = "SURFACE_UNSUPPORTED", exc.reason
        else:
            reason, detail = exc.reason, exc.detail

        metadata["measurement_valid"] = False
        metadata["invalid_reason"] = reason
        metadata["invalid_detail"] = detail
        summary["measurement_valid"] = False
        summary["invalid_reason"] = reason
        write_json(staging / "summary.json", summary)
        write_json(staging / "metadata.json", metadata)
        final = promote(staging, output / case / f"{run_id}.invalid")
        emit("MEASUREMENT_VALID", "NO")
        emit("REASON", reason)

        if detail:
            emit("DETAIL", detail)

        emit("INVALID_RECORD", final)

        if isinstance(exc, SurfaceUnsupported):
            raise

        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
