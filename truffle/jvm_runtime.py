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
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUFFLE = ROOT / "truffle"
WORK = ROOT / ".work" / "jvm-runtime"

DEFAULT_PROTOS_CHECKOUT = Path("/workspaces/protos")

PACKAGE = "com.guillermomolina.protos.benchmarks.truffle"
PACKAGE_PATH = PACKAGE.replace(".", "/")

PROTOS_DYNAMIC_CLASS = f"{PACKAGE}.ProtosJvmVariantRunner"
PROTOS_PREPARED_CLASS = f"{PACKAGE}.ProtosPreparedVariantRunner"
PEER_CLASS = f"{PACKAGE}.TrufflePeerJvmRunner"

PROTOS_DYNAMIC_SOURCE = (
    TRUFFLE
    / "src/main/java"
    / PACKAGE_PATH
    / "ProtosJvmVariantRunner.java"
)

PROTOS_PREPARED_SOURCE = (
    TRUFFLE
    / "src/prepared/java"
    / PACKAGE_PATH
    / "ProtosPreparedVariantRunner.java"
)

PEER_SOURCE = (
    TRUFFLE
    / "src/peer/java"
    / PACKAGE_PATH
    / "TrufflePeerJvmRunner.java"
)

PREPARED_API_CLASS = (
    "com/guillermomolina/protos/execution/"
    "ProtosStandaloneHostedSession$PreparedTopLevel.class"
)

_PROTOS_RUNTIME = {}
_PEER_RUNTIME = None


def capture(*command: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()

    for item in sorted(
        item for item in path.rglob("*") if item.is_file()
    ):
        digest.update(str(item.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")

    return digest.hexdigest()


def project_properties(repo: Path) -> tuple[str, str]:
    pom = repo / "pom.xml"

    if not pom.is_file():
        raise RuntimeError(f"Protos pom.xml missing: {pom}")

    root = ET.parse(pom).getroot()
    namespace = ""

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    version = root.findtext(
        f"{namespace}version",
        "",
    ).strip()

    properties = root.find(f"{namespace}properties")
    graalvm_version = ""

    if properties is not None:
        graalvm_version = properties.findtext(
            f"{namespace}graalvm.version",
            "",
        ).strip()

    if not version:
        raise RuntimeError(
            f"cannot resolve Protos project version from {pom}"
        )

    return version, graalvm_version


def harness_graalvm_version() -> str:
    pom = TRUFFLE / "pom.xml"
    root = ET.parse(pom).getroot()
    namespace = ""

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    properties = root.find(f"{namespace}properties")

    if properties is None:
        raise RuntimeError(
            "truffle/pom.xml has no properties"
        )

    version = properties.findtext(
        f"{namespace}graal.languages.version",
        "",
    ).strip()

    if not version:
        raise RuntimeError(
            "cannot resolve graal.languages.version"
        )

    return version


def protos_checkout() -> Path:
    value = os.environ.get(
        "PROTOS_CHECKOUT",
        str(DEFAULT_PROTOS_CHECKOUT),
    )

    path = Path(value).expanduser()

    if path.is_absolute():
        return path.resolve()

    return (ROOT / path).resolve()


def requested_protos_run_mode() -> str:
    mode = os.environ.get(
        "PROTOS_RUN_MODE",
        "auto",
    ).strip().lower()

    if mode not in {
        "auto",
        "dynamic",
        "prepared",
    }:
        raise RuntimeError(
            "PROTOS_RUN_MODE must be "
            "auto, dynamic or prepared"
        )

    return mode


def describe_protos_checkout(
    repo: Path,
) -> dict[str, object]:
    if not (repo / ".git").exists():
        raise RuntimeError(
            f"not a Git checkout: {repo}"
        )

    dirty = capture(
        "git",
        "status",
        "--porcelain",
        "--untracked-files=all",
        cwd=repo,
    )

    if dirty:
        raise RuntimeError(
            "Protos checkout has tracked or untracked changes:\n"
            + dirty
        )

    revision = capture(
        "git",
        "rev-parse",
        "HEAD",
        cwd=repo,
    )

    version, graalvm_version = (
        project_properties(repo)
    )

    core = repo / "protos" / "lib" / "core"

    if not core.is_dir():
        raise RuntimeError(
            f"Protos Core missing: {core}"
        )

    return {
        "repo": repo,
        "revision": revision,
        "version": version,
        "graalvm_version": graalvm_version,
        "core": core,
        "core_sha256": sha256_tree(core),
        "pom_sha256": sha256_file(
            repo / "pom.xml"
        ),
    }


def ensure_protos_product_classes(
    item: dict[str, object],
) -> tuple[Path, str]:
    repo = Path(str(item["repo"]))

    subprocess.run(
        [
            "mvn",
            "-q",
            "-f",
            str(repo / "pom.xml"),
            "-DskipTests",
            "compile",
        ],
        cwd=ROOT,
        check=True,
    )

    classes = repo / "target" / "classes"

    if not classes.is_dir():
        raise RuntimeError(
            "Protos target/classes missing "
            f"after compile: {classes}"
        )

    cp_dir = (
        WORK
        / "protos"
        / "classpath"
    )
    cp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    cp_file = (
        cp_dir
        / f"{item['revision']}.txt"
    )

    if not cp_file.is_file():
        subprocess.run(
            [
                "mvn",
                "-q",
                "-f",
                str(repo / "pom.xml"),
                "dependency:build-classpath",
                f"-Dmdep.outputFile={cp_file}",
            ],
            cwd=ROOT,
            check=True,
        )

    dependency_cp = cp_file.read_text(
        encoding="utf-8"
    ).strip()

    if not dependency_cp:
        raise RuntimeError(
            "empty Protos dependency "
            f"classpath: {cp_file}"
        )

    return classes, dependency_cp


def resolve_protos_run_mode(
    classes: Path,
    requested: str,
) -> str:
    has_prepared_api = (
        classes
        / PREPARED_API_CLASS
    ).is_file()

    if (
        requested == "prepared"
        and not has_prepared_api
    ):
        raise RuntimeError(
            "PROTOS_RUN_MODE=prepared requested "
            "but selected Protos checkout does "
            "not expose PreparedTopLevel"
        )

    if requested == "auto":
        if has_prepared_api:
            return "prepared"

        return "dynamic"

    return requested


def compile_protos_runner(
    item: dict[str, object],
    classes: Path,
    dependency_cp: str,
    run_mode: str,
) -> tuple[Path, str, str]:
    revision = str(item["revision"])

    target = (
        WORK
        / "protos"
        / "runner"
        / revision
        / run_mode
    )

    stamp = target / "identity.json"

    sources = [
        PROTOS_DYNAMIC_SOURCE,
    ]

    if run_mode == "prepared":
        sources.append(
            PROTOS_PREPARED_SOURCE
        )

    source_identity = {
        str(source.relative_to(ROOT)):
            sha256_file(source)
        for source in sources
    }

    expected = {
        "revision": revision,
        "run_mode": run_mode,
        "dependency_classpath_sha256":
            sha256_text(dependency_cp),
        "sources": source_identity,
    }

    main_class = (
        PROTOS_PREPARED_CLASS
        if run_mode == "prepared"
        else PROTOS_DYNAMIC_CLASS
    )

    class_name = (
        main_class.rsplit(".", 1)[1]
        + ".class"
    )

    class_file = (
        target
        / PACKAGE_PATH
        / class_name
    )

    reusable = False

    if (
        stamp.is_file()
        and class_file.is_file()
    ):
        try:
            reusable = (
                json.loads(
                    stamp.read_text(
                        encoding="utf-8"
                    )
                )
                == expected
            )
        except json.JSONDecodeError:
            reusable = False

    if not reusable:
        shutil.rmtree(
            target,
            ignore_errors=True,
        )

        target.mkdir(
            parents=True,
            exist_ok=True,
        )

        compile_cp = os.pathsep.join(
            [
                str(classes),
                dependency_cp,
            ]
        )

        subprocess.run(
            [
                "javac",
                "-proc:none",
                "-d",
                str(target),
                "-cp",
                compile_cp,
                *map(str, sources),
            ],
            cwd=ROOT,
            check=True,
        )

        if not class_file.is_file():
            raise RuntimeError(
                "compiled Protos runner "
                f"missing: {class_file}"
            )

        stamp.write_text(
            json.dumps(
                expected,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return (
        target,
        main_class,
        sha256_text(
            json.dumps(
                source_identity,
                sort_keys=True,
            )
        ),
    )


def protos_runtime() -> dict[str, object]:
    repo = protos_checkout()
    requested = (
        requested_protos_run_mode()
    )

    cache_key = (
        str(repo),
        requested,
    )

    cached = _PROTOS_RUNTIME.get(
        cache_key
    )

    if cached is not None:
        return cached

    item = describe_protos_checkout(
        repo
    )

    classes, dependency_cp = (
        ensure_protos_product_classes(
            item
        )
    )

    run_mode = resolve_protos_run_mode(
        classes,
        requested,
    )

    (
        runner_dir,
        main_class,
        runner_source_sha256,
    ) = compile_protos_runner(
        item,
        classes,
        dependency_cp,
        run_mode,
    )

    classpath = os.pathsep.join(
        [
            str(runner_dir),
            str(classes),
            dependency_cp,
        ]
    )

    result = {
        **item,
        "requested_run_mode":
            requested,
        "run_mode":
            run_mode,
        "classes":
            classes,
        "dependency_classpath":
            dependency_cp,
        "dependency_classpath_sha256":
            sha256_text(dependency_cp),
        "runner_dir":
            runner_dir,
        "runner_classes_sha256":
            sha256_tree(runner_dir),
        "runner_source_sha256":
            runner_source_sha256,
        "main_class":
            main_class,
        "classpath":
            classpath,
    }

    _PROTOS_RUNTIME[
        cache_key
    ] = result

    return result


def protos_identity(
    runtime: dict[str, object] | None = None,
) -> dict[str, object]:
    item = (
        runtime
        if runtime is not None
        else protos_runtime()
    )

    return {
        "version":
            item["version"],
        "revision":
            item["revision"],
        "graalvm_version":
            item["graalvm_version"],
        "core_sha256":
            item["core_sha256"],
        "pom_sha256":
            item["pom_sha256"],
        "requested_run_mode":
            item["requested_run_mode"],
        "run_mode":
            item["run_mode"],
        "dependency_classpath_sha256":
            item[
                "dependency_classpath_sha256"
            ],
        "runner_source_sha256":
            item["runner_source_sha256"],
        "runner_classes_sha256":
            item["runner_classes_sha256"],
    }


def protos_measure_command(
    runtime: dict[str, object],
    source: Path,
    warmup: int,
    steady: int,
    sample_calls: int,
    cpu: int | None,
) -> list[str]:
    command = [
        "java",
        "-cp",
        str(runtime["classpath"]),
        str(runtime["main_class"]),
        str(runtime["core"]),
        str(source),
        str(warmup),
        str(steady),
        str(sample_calls),
    ]

    if cpu is None:
        return command

    return [
        "taskset",
        "-c",
        str(cpu),
        *command,
    ]


def peer_pom(version: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.guillermomolina</groupId>
  <artifactId>protos-benchmarks-peer-runtime</artifactId>
  <version>1.0-SNAPSHOT</version>
  <dependencies>
    <dependency>
      <groupId>org.graalvm.polyglot</groupId>
      <artifactId>polyglot</artifactId>
      <version>{version}</version>
    </dependency>
    <dependency>
      <groupId>org.graalvm.polyglot</groupId>
      <artifactId>js</artifactId>
      <version>{version}</version>
      <type>pom</type>
    </dependency>
    <dependency>
      <groupId>org.graalvm.polyglot</groupId>
      <artifactId>python</artifactId>
      <version>{version}</version>
      <type>pom</type>
    </dependency>
  </dependencies>
</project>
"""


def peer_runtime() -> dict[str, object]:
    global _PEER_RUNTIME

    if _PEER_RUNTIME is not None:
        return _PEER_RUNTIME

    version = harness_graalvm_version()

    peer_root = (
        WORK
        / "peer"
        / version
    )

    peer_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    pom = peer_root / "pom.xml"
    expected_pom = peer_pom(
        version
    )

    if (
        not pom.is_file()
        or pom.read_text(
            encoding="utf-8"
        )
        != expected_pom
    ):
        pom.write_text(
            expected_pom,
            encoding="utf-8",
        )

    cp_file = (
        peer_root
        / "classpath.txt"
    )

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

    dependency_cp = cp_file.read_text(
        encoding="utf-8"
    ).strip()

    if not dependency_cp:
        raise RuntimeError(
            "empty peer dependency "
            f"classpath: {cp_file}"
        )

    classes = (
        peer_root
        / "classes"
    )

    stamp = (
        classes
        / "identity.json"
    )

    source_sha256 = sha256_file(
        PEER_SOURCE
    )

    expected = {
        "graalvm_version":
            version,
        "dependency_classpath_sha256":
            sha256_text(dependency_cp),
        "runner_source_sha256":
            source_sha256,
    }

    class_file = (
        classes
        / PACKAGE_PATH
        / "TrufflePeerJvmRunner.class"
    )

    reusable = False

    if (
        stamp.is_file()
        and class_file.is_file()
    ):
        try:
            reusable = (
                json.loads(
                    stamp.read_text(
                        encoding="utf-8"
                    )
                )
                == expected
            )
        except json.JSONDecodeError:
            reusable = False

    if not reusable:
        shutil.rmtree(
            classes,
            ignore_errors=True,
        )

        classes.mkdir(
            parents=True,
            exist_ok=True,
        )

        subprocess.run(
            [
                "javac",
                "--release",
                "21",
                "-proc:none",
                "-d",
                str(classes),
                "-cp",
                dependency_cp,
                str(PEER_SOURCE),
            ],
            cwd=ROOT,
            check=True,
        )

        if not class_file.is_file():
            raise RuntimeError(
                "compiled peer runner "
                f"missing: {class_file}"
            )

        stamp.write_text(
            json.dumps(
                expected,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    classpath = os.pathsep.join(
        [
            str(classes),
            dependency_cp,
        ]
    )

    _PEER_RUNTIME = {
        "graalvm_version":
            version,
        "dependency_classpath":
            dependency_cp,
        "dependency_classpath_sha256":
            sha256_text(dependency_cp),
        "runner_source_sha256":
            source_sha256,
        "runner_classes_sha256":
            sha256_tree(classes),
        "classes":
            classes,
        "main_class":
            PEER_CLASS,
        "classpath":
            classpath,
    }

    return _PEER_RUNTIME


def peer_identity(
    runtime: dict[str, object] | None = None,
) -> dict[str, object]:
    item = (
        runtime
        if runtime is not None
        else peer_runtime()
    )

    return {
        "graalvm_version":
            item["graalvm_version"],
        "dependency_classpath_sha256":
            item[
                "dependency_classpath_sha256"
            ],
        "runner_source_sha256":
            item["runner_source_sha256"],
        "runner_classes_sha256":
            item["runner_classes_sha256"],
    }


def peer_correctness_command(
    runtime: dict[str, object],
    language: str,
    source: Path,
) -> list[str]:
    return [
        "java",
        "-cp",
        str(runtime["classpath"]),
        str(runtime["main_class"]),
        "correctness",
        language,
        str(source),
    ]


def peer_measure_command(
    runtime: dict[str, object],
    language: str,
    source: Path,
    warmup: int,
    steady: int,
    sample_calls: int,
    cpu: int | None,
) -> list[str]:
    command = [
        "java",
        "-cp",
        str(runtime["classpath"]),
        str(runtime["main_class"]),
        "measure",
        language,
        str(source),
        str(warmup),
        str(steady),
        str(sample_calls),
    ]

    if cpu is None:
        return command

    return [
        "taskset",
        "-c",
        str(cpu),
        *command,
    ]
