#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Explicit preparation and offline compilation of Bytecode DSL diagnostics.

This module is never imported or invoked by the timed measurement engine.
It does not change the product checkout, measurement adapters or results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (
    ROOT / "harness/instruments/BytecodeSizeInstrument.java"
)
CACHE = ROOT / ".work/embedded/bytecode-size-instrument"

VERSION_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
)


class InstrumentError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024), b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


def runtime_truffle_version(classpath: str) -> str:
    """Read the exact Truffle API version from resolved runtime jars."""
    versions = set()

    for entry in classpath.split(os.pathsep):
        name = Path(entry).name

        if name.startswith("truffle-api-") and name.endswith(".jar"):
            versions.add(name[len("truffle-api-"):-4])

    if len(versions) != 1:
        raise InstrumentError(
            "TRUFFLE_API_VERSION_UNRESOLVED: "
            f"{sorted(versions)}"
        )

    version = next(iter(versions))

    if not VERSION_PATTERN.fullmatch(version):
        raise InstrumentError(
            f"INVALID_TRUFFLE_VERSION: {version!r}"
        )

    return version


def processor_jar(
    version: str,
    repository: Path | None = None,
) -> Path:
    """Resolve an already-prepared exact-version processor jar."""
    if not VERSION_PATTERN.fullmatch(version):
        raise InstrumentError(
            f"INVALID_TRUFFLE_VERSION: {version!r}"
        )

    repository = (
        repository
        if repository is not None
        else Path.home() / ".m2/repository"
    )

    jar = (
        repository
        / "org/graalvm/truffle/truffle-dsl-processor"
        / version
        / f"truffle-dsl-processor-{version}.jar"
    )

    if not jar.is_file():
        raise InstrumentError(
            "BYTECODE_PROCESSOR_NOT_PREPARED: "
            f"{jar}"
        )

    return jar


def prepare_processor(version: str) -> Path:
    """Explicit online preparation, never called by compilation."""
    if not VERSION_PATTERN.fullmatch(version):
        raise InstrumentError(
            f"INVALID_TRUFFLE_VERSION: {version!r}"
        )

    command = [
        "mvn",
        "-q",
        "-f",
        str(ROOT / "harness/pom.xml"),
        "org.apache.maven.plugins:maven-dependency-plugin:3.9.0:get",
        (
            "-Dartifact="
            "org.graalvm.truffle:truffle-dsl-processor:"
            + version
        ),
        "-Dtransitive=true",
    ]

    subprocess.run(command, cwd=ROOT, check=True)

    return processor_jar(version)


def compile_instrument(runtime_classpath: str) -> dict[str, object]:
    """Compile the diagnostic-only instrument without network access."""
    version = runtime_truffle_version(runtime_classpath)
    processor = processor_jar(version)

    runtime_entries = runtime_classpath.split(os.pathsep)

    if not runtime_entries or any(
        not Path(entry).exists() for entry in runtime_entries
    ):
        raise InstrumentError(
            "RUNTIME_CLASSPATH_NOT_READY"
        )

    if not SOURCE.is_file():
        raise InstrumentError(
            "BYTECODE_INSTRUMENT_SOURCE_MISSING"
        )

    truffle_jars = [
        Path(entry)
        for entry in runtime_entries
        if Path(entry).name == f"truffle-api-{version}.jar"
    ]

    if len(truffle_jars) != 1:
        raise InstrumentError(
            "TRUFFLE_API_JAR_AMBIGUOUS"
        )

    identity = {
        "truffle_version": version,
        "source_sha256": sha256_file(SOURCE),
        "processor_sha256": sha256_file(processor),
        "truffle_api_sha256": sha256_file(truffle_jars[0]),
        "runtime_classpath": runtime_classpath,
    }

    identity_bytes = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    cache_key = hashlib.sha256(identity_bytes).hexdigest()
    cache_entry = CACHE / cache_key
    classes = cache_entry / "classes"

    instrument_class = (
        classes
        / "com/guillermomolina/benchmarks/instrument"
        / "BytecodeSizeInstrument.class"
    )

    services = (
        classes
        / "META-INF/services"
        / "com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider"
    )

    if instrument_class.is_file() and services.is_file():
        return {
            "status": "REUSED",
            "classes": classes,
            "version": version,
            "cache_key": cache_key,
            "processor_sha256": identity["processor_sha256"],
        }

    if cache_entry.exists():
        raise InstrumentError(
            "INCOMPLETE_INSTRUMENT_CACHE: "
            f"{cache_entry}"
        )

    CACHE.mkdir(parents=True, exist_ok=True)

    building = Path(
        tempfile.mkdtemp(
            prefix="bytecode-instrument-",
            dir=CACHE,
        )
    )

    compiled_classes = building / "classes"
    generated_sources = building / "generated"

    compiled_classes.mkdir()
    generated_sources.mkdir()

    processor_path = os.pathsep.join([
        str(processor),
        runtime_classpath,
    ])

    command = [
        "javac",
        "--release",
        "21",
        "-proc:full",
        "-cp",
        runtime_classpath,
        "-processorpath",
        processor_path,
        "-d",
        str(compiled_classes),
        "-s",
        str(generated_sources),
        str(SOURCE),
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    (building / "compile.log").write_text(
        "$ " + " ".join(command) + "\n" + result.stdout,
        encoding="utf-8",
    )

    generated_class = (
        compiled_classes
        / "com/guillermomolina/benchmarks/instrument"
        / "BytecodeSizeInstrument.class"
    )

    generated_services = (
        compiled_classes
        / "META-INF/services"
        / "com.oracle.truffle.api.instrumentation.provider.TruffleInstrumentProvider"
    )

    if result.returncode != 0:
        raise InstrumentError(
            "BYTECODE_INSTRUMENT_COMPILATION_FAILED: "
            f"{building / 'compile.log'}"
        )

    if not generated_class.is_file():
        raise InstrumentError(
            "BYTECODE_INSTRUMENT_CLASS_MISSING"
        )

    if not generated_services.is_file():
        raise InstrumentError(
            "BYTECODE_INSTRUMENT_PROVIDER_MISSING"
        )

    (building / "identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    building.rename(cache_entry)

    return {
        "status": "COMPILED",
        "classes": classes,
        "version": version,
        "cache_key": cache_key,
        "processor_sha256": identity["processor_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("prepare", "check", "compile-peer"),
    )
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    if args.command == "compile-peer":
        from measure_protos import peer_classpath

        peer_version, runtime_cp = peer_classpath(
            args.version
        )

        if peer_version != args.version:
            raise InstrumentError(
                "PEER_VERSION_MISMATCH"
            )

        built = compile_instrument(runtime_cp)

        print("BYTECODE_INSTRUMENT_COMPILED=YES")
        print(f"BYTECODE_INSTRUMENT_STATUS={built['status']}")
        print(f"BYTECODE_INSTRUMENT_VERSION={built['version']}")
        print(f"BYTECODE_INSTRUMENT_CACHE_KEY={built['cache_key']}")
        print(f"BYTECODE_INSTRUMENT_CLASSES={built['classes']}")
        return

    if args.command == "prepare":
        jar = prepare_processor(args.version)
        print("BYTECODE_PROCESSOR_PREPARED=YES")
    else:
        jar = processor_jar(args.version)
        print("BYTECODE_PROCESSOR_AVAILABLE=YES")

    print(f"BYTECODE_PROCESSOR_JAR={jar}")
    print(f"BYTECODE_PROCESSOR_SHA256={sha256_file(jar)}")


if __name__ == "__main__":
    main()
