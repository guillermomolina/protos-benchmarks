#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Single host entry point for the Protos/GraalJS/GraalPy harness."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "harness"
RESULTS = ROOT / "results"
CONTAINER_ROOT = "/workspaces/protos-benchmarks"
CONTAINER_PRODUCT = "/workspaces/protos"

LANGUAGES = ("protos", "js", "python")
DEFAULT_IMAGE = (
    "localhost/protos-bench-runner:"
    "graal25.4.4.1.1-standalone"
)

COMMANDS = (
    "validate",
    "correctness",
    "measure",
    "smoke",
    "graphs-capture",
    "graphs-analyze",
    "graphs-summarize",
    "graphs-verify",
    "cold-capture",
    "bytecode-capture",
    "cold-analyze",
    "cold-summarize",
    "structural-report",
    "image-status",
    "image-build",
    "peer-prepare",
    "product-prepare",
    "bytecode-prepare",
)


class HarnessError(Exception):
    pass


def load_catalog():
    path = ROOT / "cases" / "catalog.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("schema") != 1:
        raise HarnessError("Unsupported workload catalog schema")

    workloads = data.get("workloads")
    if not isinstance(workloads, list) or not workloads:
        raise HarnessError("Empty or invalid workload catalog")

    seen = set()

    for case in workloads:
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise HarnessError("Workload without identifier")
        if identifier in seen:
            raise HarnessError(f"Duplicate workload: {identifier}")

        seen.add(identifier)

        expected = case.get("expected")
        if not isinstance(expected, str):
            raise HarnessError(f"Invalid expected result: {identifier}")

        sources = case.get("sources")
        if not isinstance(sources, dict):
            raise HarnessError(f"Invalid sources: {identifier}")
        if set(sources) != set(LANGUAGES):
            raise HarnessError(
                f"{identifier}: exactly protos, js and python required"
            )

        for language, relative in sources.items():
            path = ROOT / "cases" / relative
            if not path.is_file():
                raise HarnessError(
                    f"Missing {language} source for {identifier}: {relative}"
                )

    return data


def validate():
    data = load_catalog()

    cases = json.loads(
        (HARNESS_DIR / "policy" / "cases.json").read_text(
            encoding="utf-8"
        )
    )
    graphs = json.loads(
        (HARNESS_DIR / "policy" / "graphs.json").read_text(
            encoding="utf-8"
        )
    )

    if cases.get("schema") != 1 or graphs.get("schema") != 1:
        raise HarnessError("Invalid measurement policy schema")

    ids = {item["id"] for item in data["workloads"]}

    policy = cases["policy"]
    for stage in ("smoke", "reference"):
        for kind in ("timing", "jfr"):
            values = policy["default"][stage][kind]
            for key in ("warmup_iterations", "steady_iterations"):
                if not isinstance(values.get(key), int):
                    raise HarnessError(
                        f"Invalid {stage}/{kind}/{key}"
                    )

    for identifier in policy.get("workloads", {}):
        if identifier not in ids:
            raise HarnessError(
                f"Unknown policy workload: {identifier}"
            )

    for ladder in graphs.get("ladders", {}).values():
        for rung in ladder:
            if rung["workload"] not in ids:
                raise HarnessError(
                    f"Unknown graph workload: {rung['workload']}"
                )

    print(f"CATALOG_VALID=YES")
    print(f"WORKLOADS={len(ids)}")
    print("LANGUAGES=protos,js,python")
    print("MEASUREMENT_POLICY=VALID")
    print("GRAPH_POLICY=VALID")


def selected_cases(selector):
    ids = [item["id"] for item in load_catalog()["workloads"]]
    if selector == "all":
        return ids
    if selector not in ids:
        raise HarnessError(f"Unknown workload: {selector}")
    return [selector]


def selected_languages(selector):
    if selector == "all":
        return LANGUAGES
    if selector not in LANGUAGES:
        raise HarnessError(f"Unknown language: {selector}")
    return (selector,)


def output_path(requested, category):
    if requested:
        candidate = Path(requested)
        path = (candidate if candidate.is_absolute()
                else ROOT / candidate).resolve()
    else:
        path = (RESULTS / "local" / "harness" / category).resolve()

    if not path.is_relative_to(RESULTS.resolve()):
        raise HarnessError(
            "Output must be inside the repository results directory"
        )

    return path


def container_output(path):
    return f"{CONTAINER_ROOT}/{path.relative_to(ROOT)}"


def podman_binary():
    binary = os.environ.get("PODMAN", "").strip() or "podman"
    if shutil.which(binary) is None:
        raise HarnessError(
            f"PODMAN_NOT_AVAILABLE: {binary}. "
            "The Linux host needs Podman, not Java or Maven."
        )
    return binary


def image_present(binary, image):
    result = subprocess.run(
        [binary, "image", "inspect", image],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode == 0


def require_image(binary, image):
    if not image_present(binary, image):
        raise HarnessError(
            f"IMAGE_NOT_AVAILABLE: {image}. "
            "The image is not available locally. "
            "Use 'make image-build' only when explicitly authorized. "
            "No automatic build or pull is performed."
        )


def image_identity(binary, image):
    """Resolve the immutable ID of an already-present local image."""
    result = subprocess.run(
        [
            binary, "image", "inspect",
            "--format", "{{.Id}}", image,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    raw = result.stdout.strip().removeprefix("sha256:")

    if result.returncode or not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise HarnessError(
            f"IMAGE_ID_UNAVAILABLE: {image}. "
            "Cannot identify the local image; measurement refused."
        )

    return "sha256:" + raw


def product_directory(value):
    path = Path(value).expanduser().resolve()
    if not (path / "pom.xml").is_file():
        raise HarnessError(
            f"Invalid Protos checkout: {path}. "
            "Specify PROTOS_REPO=/path/to/protos."
        )
    return path


def run_container(binary, image, product, arguments, *, allow_network=False):
    require_image(binary, image)

    cache = ROOT / ".work" / "runner-m2"
    cache.mkdir(parents=True, exist_ok=True)

    command = [
        binary,
        "run",
        "--rm",
        "--pull=never",
        *([] if allow_network else ["--network=none"]),
        "--userns=keep-id",
        "--volume",
        f"{ROOT}:{CONTAINER_ROOT}:rw",
        "--volume",
        f"{cache}:/home/vscode/.m2:rw",
    ]

    if product is not None:
        command.extend([
            "--volume",
            f"{product}:{CONTAINER_PRODUCT}:rw",
        ])

    command.extend([
        "--workdir",
        CONTAINER_ROOT,
        "--entrypoint",
        "/usr/bin/python3",
        image,
        *arguments,
    ])

    return subprocess.run(command, cwd=ROOT, check=False).returncode


def run_measurement(args, command):
    if command == "correctness" and args.temperature != "hot":
        raise HarnessError(
            "--temperature is only applicable to timed measurements"
        )

    selector = args.case or (
        "primitive-return-literal" if command == "smoke" else "all"
    )
    workloads = selected_cases(selector)
    languages = selected_languages(args.language)
    output = output_path(
        args.output,
        "correctness" if command == "correctness"
        else "measure",
    )

    binary = podman_binary()
    require_image(binary, args.image)
    runtime_image_id = image_identity(binary, args.image)

    host_hostname = platform.node().strip()
    if not host_hostname:
        raise HarnessError(
            "HOST_ID_UNAVAILABLE: cannot determine the host hostname"
        )

    product = (
        product_directory(args.product)
        if "protos" in languages else None
    )

    requested_versions = {
        "protos": args.protos_version,
        "js": args.js_version,
        "python": args.python_version,
    }

    for workload in workloads:
        for language in languages:
            arguments = [
                "harness/measure_protos.py",
                "--language", language,
                "--workload", workload,
                "--stage",
                "smoke" if command in ("smoke", "correctness")
                else args.stage,
                "--profile",
                "none" if command in ("smoke", "correctness")
                else args.profile,
                "--output", container_output(output),
                "--container-image-id", runtime_image_id,
                "--host-hostname", host_hostname,
                "--temperature", args.temperature,
            ]

            if language == "protos":
                arguments.extend([
                    "--dir", CONTAINER_PRODUCT,
                    "--surface", args.surface,
                ])

            requested_version = requested_versions[language]
            if requested_version is not None:
                arguments.extend(["--version", requested_version])

            if args.cpu is not None:
                arguments.extend(["--cpu", str(args.cpu)])

            if command == "correctness":
                arguments.append("--correctness-only")

            if args.remeasure:
                arguments.append("--remeasure")

            code = run_container(
                binary, args.image, product, arguments
            )
            if code:
                return code

    return 0



def run_bytecode_prepare(args):
    """Explicit online processor preparation in the existing runner.

    The host never invokes Maven. The prepared artifact is retained in
    the runner Maven cache and checked again with network disabled.
    """
    import xml.etree.ElementTree as ET

    version = args.bytecode_version

    if version is None:
        pom = ET.parse(HARNESS_DIR / "pom.xml").getroot()

        namespace = ""
        if pom.tag.startswith("{"):
            namespace = pom.tag.split("}", 1)[0] + "}"

        properties = pom.find(
            f"{namespace}properties"
        )

        if properties is None:
            raise HarnessError(
                "BYTECODE_GRAALVM_VERSION_UNAVAILABLE"
            )

        version = properties.findtext(
            f"{namespace}graal.languages.version",
            "",
        ).strip()

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
        version or "",
    ):
        raise HarnessError(
            f"Invalid bytecode processor version: {version!r}"
        )

    binary = podman_binary()
    require_image(binary, args.image)

    prepare_arguments = [
        "harness/bytecode_size_runtime.py",
        "prepare",
        "--version",
        version,
    ]

    code = run_container(
        binary,
        args.image,
        None,
        prepare_arguments,
        allow_network=True,
    )

    if code:
        return code

    check_arguments = [
        "harness/bytecode_size_runtime.py",
        "check",
        "--version",
        version,
    ]

    return run_container(
        binary,
        args.image,
        None,
        check_arguments,
        allow_network=False,
    )



def run_product_prepare(args):
    """Prepare Protos dependencies outside all measurement JVMs."""
    binary = podman_binary()
    require_image(binary, args.image)

    product = product_directory(args.product)

    arguments = [
        "harness/measure_protos.py",
        "--prepare-product",
        "--language", "protos",
        "--dir", CONTAINER_PRODUCT,
    ]

    if args.protos_version is not None:
        arguments.extend([
            "--version", args.protos_version,
        ])

    return run_container(
        binary,
        args.image,
        product,
        arguments,
        allow_network=True,
    )


def run_peer_prepare(args):
    """Explicit peer preparation; no benchmark execution."""
    if args.language == "protos":
        raise HarnessError(
            "PEER_PREPARE_LANGUAGE: select js, python or all"
        )

    languages = (
        ("js", "python") if args.language == "all"
        else (args.language,)
    )

    binary = podman_binary()
    require_image(binary, args.image)

    for language in languages:
        arguments = [
            "harness/measure_protos.py",
            "--prepare-peer",
            "--language", language,
        ]

        version = (
            args.js_version if language == "js"
            else args.python_version
        )

        if version:
            arguments.extend(["--version", version])

        code = run_container(
            binary,
            args.image,
            None,
            arguments,
            allow_network=True,
        )

        if code:
            return code

    return 0



def run_bytecode(args):
    """Host launcher for the separate Bytecode DSL diagnostic."""
    if not args.case or args.case == "all":
        raise HarnessError("Select exactly one CASE")

    selected_cases(args.case)

    if args.language == "all":
        raise HarnessError("Select exactly one LANGUAGE")

    if not 1 <= args.bytecode_calls <= 1000000:
        raise HarnessError("Invalid BYTECODE_CALLS")

    binary = podman_binary()
    require_image(binary, args.image)

    product = (
        product_directory(args.product)
        if args.language == "protos"
        else None
    )

    output = output_path(args.output, "bytecode")

    arguments = [
        "harness/measure_graphs.py",
        "bytecode",
        "--output", container_output(output),
        "--language", args.language,
        "--workload", args.case,
        "--calls", str(args.bytecode_calls),
    ]

    if args.language == "protos":
        arguments.extend(["--dir", CONTAINER_PRODUCT])

    version = {
        "protos": args.protos_version,
        "js": args.js_version,
        "python": args.python_version,
    }[args.language]

    if version is not None:
        arguments.extend(["--version", version])

    if args.cpu is not None:
        arguments.extend(["--cpu", str(args.cpu)])

    return run_container(
        binary, args.image, product, arguments
    )


def run_cold(args):
    """Host orchestration; Graal JVM execution stays inside Podman."""
    import re

    safe_root = re.sub(
        r"[^A-Za-z0-9_.-]", "_", args.root
    )
    if not safe_root:
        raise HarnessError("Invalid root selector")

    category = f"cold/tier-{args.tier}/{safe_root}"
    output = output_path(args.output, category)

    if args.command == "cold-capture":
        if not args.case or args.case == "all":
            raise HarnessError(
                "Cold capture requires exactly one CASE"
            )
        selected_cases(args.case)

        if args.language == "all":
            raise HarnessError(
                "Cold capture requires exactly one LANGUAGE"
            )

        binary = podman_binary()
        require_image(binary, args.image)
        product = product_directory(args.product)

        last_threshold = (
            args.last_threshold
            if args.last_threshold is not None
            else (1000000 if args.tier == 1 else 1000)
        )

        arguments = [
            "harness/measure_graphs.py",
            "cold",
            "--dir", CONTAINER_PRODUCT,
            "--output", container_output(output),
            "--language", args.language,
            "--workload", args.case,
            "--tier", str(args.tier),
            "--root", args.root,
            "--warmup-calls", str(args.warmup_calls),
            "--invocations", str(args.invocations),
            "--first-threshold", str(args.first_threshold),
            "--last-threshold", str(last_threshold),
        ]

        if args.cpu is not None:
            arguments.extend(["--cpu", str(args.cpu)])

        for option in args.jvm_option:
            arguments.extend(["--jvm-option", option])

        return run_container(
            binary, args.image, product, arguments
        )

    operation = (
        "analyze"
        if args.command == "cold-analyze"
        else "cold-summarize"
    )

    return subprocess.run(
        [
            sys.executable,
            str(HARNESS_DIR / "measure_graphs.py"),
            operation,
            "--output", str(output),
        ],
        cwd=ROOT,
        check=False,
    ).returncode



def run_structural_report(args):
    """Generate a derived report without running a guest JVM."""
    bytecode = output_path(
        args.bytecode_dir, "bytecode"
    )
    tier1 = output_path(
        args.tier1_dir, "cold/tier-1/all"
    )
    tier2 = output_path(
        args.tier2_dir, "cold/tier-2/all"
    )
    destination = output_path(
        args.output, "structural"
    )

    for source in (tier1, tier2, bytecode):
        if (
            destination == source
            or destination.is_relative_to(source)
            or source.is_relative_to(destination)
        ):
            raise HarnessError(
                "Structural report output overlaps capture inputs"
            )

    return subprocess.run(
        [
            sys.executable,
            str(HARNESS_DIR / "measure_graphs.py"),
            "structural-report",
            "--tier1", str(tier1),
            "--tier2", str(tier2),
            "--bytecode", str(bytecode),
            "--output", str(destination),
            "--workload", args.case or "all",
            "--language", args.language,
        ],
        cwd=ROOT,
        check=False,
    ).returncode


def run_graphs(args):
    output = output_path(args.output, "graphs")

    if args.command == "graphs-capture":
        load_catalog()
        selector = args.case or "ladder"

        if selector not in ("ladder", "all"):
            selected_cases(selector)

        binary = podman_binary()
        require_image(binary, args.image)
        product = product_directory(args.product)

        arguments = [
            "harness/measure_graphs.py",
            "capture",
            "--dir", CONTAINER_PRODUCT,
            "--output", container_output(output),
            "--language", args.language,
            "--workload", selector,
            "--stage", args.stage,
        ]

        if args.cpu is not None:
            arguments.extend(["--cpu", str(args.cpu)])

        if args.remeasure:
            arguments.append("--remeasure")

        return run_container(
            binary, args.image, product, arguments
        )

    action = args.command.removeprefix("graphs-")

    command = [
        sys.executable,
        str(HARNESS_DIR / "measure_graphs.py"),
        action,
        "--output",
        str(output),
    ]

    return subprocess.run(
        command, cwd=ROOT, check=False
    ).returncode


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Protos/GraalJS/GraalPy Podman benchmark harness"
    )
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--case")
    parser.add_argument(
        "--language", choices=(*LANGUAGES, "all"), default="all"
    )
    parser.add_argument(
        "--stage", choices=("smoke", "reference"),
        default="reference",
    )
    parser.add_argument(
        "--profile", choices=("none", "jfr"),
        default="none",
    )
    parser.add_argument("--surface", default="canonical")
    parser.add_argument(
        "--temperature",
        choices=("cold", "hot", "both"),
        default="hot",
        help="cold: first guest call; hot: warmed steady samples; "
        "both: report both observations from the same run",
    )
    parser.add_argument("--bytecode-version")
    parser.add_argument("--protos-version")
    parser.add_argument("--js-version")
    parser.add_argument("--python-version")
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--output")
    parser.add_argument("--remeasure", action="store_true")
    parser.add_argument(
        "--product",
        default=str(ROOT.parent / "protos"),
    )
    parser.add_argument("--bytecode-dir")
    parser.add_argument("--tier1-dir")
    parser.add_argument("--tier2-dir")
    parser.add_argument("--tier", type=int, choices=(1, 2), default=2)
    parser.add_argument("--root", default="primary")
    parser.add_argument("--warmup-calls", type=int, default=0)
    parser.add_argument("--invocations", type=int, default=2000)
    parser.add_argument("--bytecode-calls", type=int, default=100)
    parser.add_argument("--first-threshold", type=int, default=100)
    parser.add_argument("--last-threshold", type=int)
    parser.add_argument("--jvm-option", action="append", default=[])
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        if args.command == "validate":
            validate()
            return 0

        if args.command == "image-status":
            binary = podman_binary()
            if image_present(binary, args.image):
                print(f"IMAGE_AVAILABLE=YES")
                print(f"IMAGE={args.image}")
                return 0
            print(f"IMAGE_AVAILABLE=NO")
            print(f"IMAGE={args.image}")
            print(
                "Build explicitly with make image-build "
                "when authorized."
            )
            return 3

        if args.command == "image-build":
            binary = podman_binary()
            return subprocess.run(
                [
                    binary, "build",
                    "--pull=missing",
                    "--file", str(HARNESS_DIR / "Containerfile"),
                    "--tag", args.image,
                    str(HARNESS_DIR),
                ],
                cwd=ROOT,
                check=False,
            ).returncode

        if args.command == "peer-prepare":
            return run_peer_prepare(args)

        if args.command == "product-prepare":
            return run_product_prepare(args)

        if args.command == "bytecode-prepare":
            return run_bytecode_prepare(args)

        if args.command == "structural-report":
            return run_structural_report(args)

        if args.command in ("correctness", "measure", "smoke"):
            return run_measurement(args, args.command)

        if args.command == "bytecode-capture":
            return run_bytecode(args)

        if args.command.startswith("cold-"):
            return run_cold(args)

        return run_graphs(args)

    except (HarnessError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
