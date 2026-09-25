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

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/perf010a-post-i068-baseline.json"
SUITE = ROOT / "config/suite.json"
HISTORICAL_CONFIG = ROOT / "config/perf004a.json"
HISTORICAL_DIR = ROOT / "results/perf004-a"
EXPECTED_SLICE = "PERF010A_POST_I068_CURRENT_BASELINE_REMEASUREMENT"
EXPECTED_PRODUCT_REVISION = "f1cee2d85858804ad3775adf43a9fab97664da2a"
EXPECTED_PRODUCT_VERSION = "0.3.87-SNAPSHOT"
EXPECTED_HISTORICAL_HARNESS_REVISION = "60dbce7faf5510bd1bd6867a866aa7ca69c48637"
EXPECTED_HISTORICAL_PRODUCT_REVISION = "4a03efc15620b37b2e418b3df30b4a26486446ec"
EXPECTED_HISTORICAL_PRODUCT_VERSION = "0.2.492-SNAPSHOT"
EXPECTED_EQUIVALENCE_REVISION = "42b8264a36254dafbd97d80f5181790e28b9de12"
EXPECTED_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_IDS = (
    "micro/slot-read",
    "micro/closure-call",
    "micro/method-call",
    "runtime/monomorphic-dispatch",
    "algorithms/factorial/recursive",
)
PRIMARY_IDS = EXPECTED_IDS[:4]
SENTINEL_ID = EXPECTED_IDS[4]
LANGUAGES = ("protos", "python", "javascript")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FALLBACK_WARNING_RE = re.compile(
    r"No optimizing Truffle runtime found|fallback runtime that does not support runtime compilation|"
    r"does not support runtime compilation to native code|executed in interpreted mode only",
    re.IGNORECASE,
)


def run(
    command: list[str],
    *,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check,
    )


def output(command: list[str]) -> str:
    completed = run(command, capture=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "command failed: "
            + " ".join(command)
            + "\nstdout:\n"
            + (completed.stdout or "")[-6000:]
            + "\nstderr:\n"
            + (completed.stderr or "")[-6000:]
        )
    return (completed.stdout or "").strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def cfg() -> dict[str, Any]:
    return load_json(CONFIG)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_historical_manifest() -> None:
    manifest = HISTORICAL_DIR / "SHA256SUMS"
    if not manifest.is_file():
        raise RuntimeError("missing retained PERF004-A SHA256SUMS")
    required = {"README.md", "raw.json", "run-metadata.json", "summary.json", "summary.tsv"}
    seen: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError("invalid retained PERF004-A SHA256SUMS line")
        digest, name = parts
        name = name.lstrip("*")
        target = HISTORICAL_DIR / name
        if not target.is_file():
            raise RuntimeError("missing retained PERF004-A manifest member: " + name)
        if sha256_file(target) != digest:
            raise RuntimeError("retained PERF004-A manifest mismatch: " + name)
        seen.add(name)
    if not required.issubset(seen):
        raise RuntimeError("retained PERF004-A manifest does not cover required evidence files")


def historical_ratio_map() -> dict[str, dict[str, float]]:
    summary = load_json(HISTORICAL_DIR / "summary.json")
    result: dict[str, dict[str, float]] = {}
    for item in summary["ratios"]:
        workload = str(item["workload"])
        if workload not in EXPECTED_IDS:
            continue
        result[workload] = {
            "python": float(item["comparisons"]["python"]["steady"]),
            "javascript": float(item["comparisons"]["javascript"]["steady"]),
        }
    if tuple(workload for workload in EXPECTED_IDS if workload in result) != EXPECTED_IDS:
        raise RuntimeError("retained PERF004-A ratios do not cover the requested five workloads")
    return result


def suite_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    suite = load_json(SUITE)
    historical = load_json(HISTORICAL_CONFIG)
    pins = {str(item["id"]): str(item["source_blob_sha"]) for item in historical["workloads"]}
    suite_by_id = {str(item["id"]): item for item in suite["benchmarks"]}
    entries: list[dict[str, Any]] = []
    for requested in config["workloads"]:
        benchmark_id = str(requested["id"])
        item = suite_by_id[benchmark_id]
        entries.append(
            {
                "id": benchmark_id,
                "classification": str(requested["classification"]),
                "expected": str(item["expected_stdout"]),
                "protos": str(item["protos"]),
                "python": str(item["implementations"]["python"]),
                "javascript": str(item["implementations"]["javascript"]),
                "equivalence": str(item["equivalence"]),
                "historical_protos_blob_sha": pins[benchmark_id],
                "historical_python_blob_sha": str(
                    requested["historical_comparison_blob_shas"]["python"]
                ),
                "historical_javascript_blob_sha": str(
                    requested["historical_comparison_blob_shas"]["javascript"]
                ),
            }
        )
    return entries


def validate() -> dict[str, Any]:
    config = cfg()
    if config.get("schema_version") != 1:
        raise RuntimeError("unsupported post-I068 baseline config schema")
    if config.get("perf_item") != "PERF010-A" or config.get("parent_perf_item") != "PERF010":
        raise RuntimeError("PERF010-A identity drift")
    if config.get("slice") != EXPECTED_SLICE:
        raise RuntimeError("post-I068 slice identity drift")
    if config.get("phase") != "post-i068-current-cross-language-baseline":
        raise RuntimeError("post-I068 phase drift")
    if config.get("timing_claim") is not True or config.get("causal_claim") is not False:
        raise RuntimeError("post-I068 timing/causal claim boundary drift")
    if config.get("protos_revision") != EXPECTED_PRODUCT_REVISION:
        raise RuntimeError("post-I068 Protos revision drift")
    if config.get("protos_version") != EXPECTED_PRODUCT_VERSION:
        raise RuntimeError("post-I068 Protos version drift")

    historical = config["historical_comparison"]
    if historical != {
        "evidence_path": "results/perf004-a",
        "config_path": "config/perf004a.json",
        "harness_revision": EXPECTED_HISTORICAL_HARNESS_REVISION,
        "protos_revision": EXPECTED_HISTORICAL_PRODUCT_REVISION,
        "protos_version": EXPECTED_HISTORICAL_PRODUCT_VERSION,
        "causal": False,
    }:
        raise RuntimeError("historical PERF004-A comparison identity drift")

    toolchain = config["toolchain"]
    if toolchain != {
        "graalvm_release": "25.3.4.1",
        "jdk_version": "25.0.4.1",
        "graal_truffle_version": "25.3.4.1",
        "maven_version": "3.9.9",
        "container_image": "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825",
        "python_package": "python3",
    }:
        raise RuntimeError("post-I068 toolchain drift")

    runtimes = config["comparison_runtimes"]
    if runtimes["python"] != {
        "version": "3.14.7",
        "base": "python:3.14.7-slim-bookworm",
    }:
        raise RuntimeError("post-I068 Python runtime drift")
    if runtimes["javascript"] != {
        "runtime": "Node.js",
        "version": "24.20.0",
        "base": "node:24.20.0-bookworm-slim",
        "stack_kb": 32768,
    }:
        raise RuntimeError("post-I068 Node runtime drift")

    driver = config["protos_driver"]
    if driver != {
        "dockerfile": "docker/protos-perf010a/Dockerfile",
        "timing_driver": "Perf010aTimingDriver",
        "runtime_probe": "Perf006dRuntimeProbe",
        "diagnostic_dir": "/opt/perf010a/diagnostic",
        "runtime_dir": "/opt/protos/lib/runtime",
        "corpus_dir": "/opt/perf010a/corpus",
        "source_root": "/opt/protos-source",
        "expected_runtime": EXPECTED_RUNTIME,
        "variant": "baseline",
        "ablation_patch": "docker/protos-perf010a/noop.patch",
    }:
        raise RuntimeError("post-I068 Protos driver contract drift")

    policy = config["measurement_contract"]
    if policy != {
        "persistent_forks_per_language_workload": 5,
        "warmup_iterations_per_fork": 120,
        "steady_samples_per_fork": 100,
        "primary_statistic": "median",
        "dispersion": ["mad", "min", "max", "p95"],
        "correctness_before_timing": True,
        "network": "none",
        "cpu_affinity": "first CPU from current allowed cpuset",
        "same_host_for_all_languages": True,
        "language_order": ["protos", "python", "javascript"],
        "persistent_boundary": "source/module load and runtime bootstrap outside timed iterations; one process per fork",
        "jfr": False,
        "compiler_tracing": False,
        "igv": False,
        "allocation_instrumentation": False,
    }:
        raise RuntimeError("post-I068 measurement contract drift")

    if config["smoke"] != {
        "workload": "micro/method-call",
        "warmup_iterations": 1,
        "steady_iterations": 2,
        "retained": False,
    }:
        raise RuntimeError("post-I068 smoke contract drift")

    configured_ids = tuple(str(item["id"]) for item in config["workloads"])
    if configured_ids != EXPECTED_IDS:
        raise RuntimeError("post-I068 workload set/order drift")
    classifications = tuple(str(item["classification"]) for item in config["workloads"])
    if classifications != (
        "PRIMARY_COMMON_PATH",
        "PRIMARY_COMMON_PATH",
        "PRIMARY_COMMON_PATH",
        "PRIMARY_COMMON_PATH",
        "SECONDARY_RECURSIVE_SCALE_SENTINEL",
    ):
        raise RuntimeError("post-I068 workload classification drift")
    if config.get("reference_output") != "results/perf010a-post-i068-baseline":
        raise RuntimeError("post-I068 output-path drift")

    required_files = (
        CONFIG,
        SUITE,
        HISTORICAL_CONFIG,
        HISTORICAL_DIR / "README.md",
        HISTORICAL_DIR / "raw.json",
        HISTORICAL_DIR / "run-metadata.json",
        HISTORICAL_DIR / "summary.json",
        HISTORICAL_DIR / "summary.tsv",
        HISTORICAL_DIR / "SHA256SUMS",
        ROOT / "docker/protos-perf010a/Dockerfile",
        ROOT / "docker/protos-perf010a/Perf010aTimingDriver.java",
        ROOT / "docker/protos-perf010a/noop.patch",
        ROOT / "docker/protos-perf006d/Perf006dRuntimeProbe.java",
        ROOT / "docker/python-perf004a/Dockerfile",
        ROOT / "docker/python-perf004a/timing_driver.py",
        ROOT / "docker/node-perf004a/Dockerfile",
        ROOT / "docker/node-perf004a/timing_driver.mjs",
    )
    for path in required_files:
        if not path.is_file():
            raise RuntimeError("missing post-I068 harness dependency: " + str(path))

    old_config = load_json(HISTORICAL_CONFIG)
    if old_config.get("protos_revision") != EXPECTED_HISTORICAL_PRODUCT_REVISION:
        raise RuntimeError("historical PERF004-A config product revision drift")
    if old_config.get("protos_implementation_version") != EXPECTED_HISTORICAL_PRODUCT_VERSION:
        raise RuntimeError("historical PERF004-A config product version drift")
    if old_config.get("equivalence_source_revision") != EXPECTED_EQUIVALENCE_REVISION:
        raise RuntimeError("historical PERF004-A equivalence-source drift")

    historical_metadata = load_json(HISTORICAL_DIR / "run-metadata.json")
    if historical_metadata.get("harness_revision") != EXPECTED_HISTORICAL_HARNESS_REVISION:
        raise RuntimeError("retained PERF004-A harness revision drift")
    if historical_metadata.get("protos_revision") != EXPECTED_HISTORICAL_PRODUCT_REVISION:
        raise RuntimeError("retained PERF004-A product revision drift")
    if historical_metadata.get("protos_implementation_version") != EXPECTED_HISTORICAL_PRODUCT_VERSION:
        raise RuntimeError("retained PERF004-A product version drift")

    historical_summary = load_json(HISTORICAL_DIR / "summary.json")
    if historical_summary.get("harness_revision") != EXPECTED_HISTORICAL_HARNESS_REVISION:
        raise RuntimeError("retained PERF004-A summary harness revision drift")
    if historical_summary.get("protos_revision") != EXPECTED_HISTORICAL_PRODUCT_REVISION:
        raise RuntimeError("retained PERF004-A summary product revision drift")
    verify_historical_manifest()
    historical_ratio_map()

    suite = load_json(SUITE)
    if suite.get("classification") != "algorithm-equivalent":
        raise RuntimeError("cross-language suite must remain algorithm-equivalent")
    if suite.get("protos_corpus_revision") != EXPECTED_EQUIVALENCE_REVISION:
        raise RuntimeError("cross-language suite equivalence revision drift")
    suite_ids = {str(item["id"]) for item in suite["benchmarks"]}
    if any(workload not in suite_ids for workload in EXPECTED_IDS):
        raise RuntimeError("requested workload missing from algorithm-equivalent suite")

    entries = suite_entries(config)
    if tuple(item["id"] for item in entries) != EXPECTED_IDS:
        raise RuntimeError("resolved workload order drift")
    for item in entries:
        for language in ("protos", "python", "javascript"):
            key = f"historical_{language}_blob_sha"
            if not SHA_RE.fullmatch(item[key]):
                raise RuntimeError(f"historical {language} source blob identity is invalid")
        for language in ("python", "javascript"):
            source = ROOT / "workloads" / language / item[language]
            if not source.is_file():
                raise RuntimeError(f"missing comparison workload source: {source}")
            observed = git_blob_sha(source)
            expected = item[f"historical_{language}_blob_sha"]
            if observed != expected:
                raise RuntimeError(
                    f"comparison workload identity mismatch {item['id']} {language}: "
                    f"current={observed} historical={expected}"
                )

    timing_driver_text = (ROOT / "docker/protos-perf010a/Perf010aTimingDriver.java").read_text(
        encoding="utf-8"
    )
    if r'\"jfr_recording_phase\":\"none\"' not in timing_driver_text:
        raise RuntimeError("current Protos timing driver does not declare JFR-free timing")
    runner_text = Path(__file__).read_text(encoding="utf-8")
    for forbidden in (
        "Trace" + "Compilation",
        "Dump" + "=Truffle",
        "Perf008" + "SteadyStateDriver",
        "jfr" + "-java",
    ):
        if forbidden in runner_text:
            raise RuntimeError("profiling/compiler diagnostic leaked into post-I068 timing runner")

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in (
        "perf010a-post-i068-validate:",
        "perf010a-post-i068-smoke:",
        "perf010a-post-i068-reference:",
    ):
        if target not in makefile:
            raise RuntimeError("missing Makefile target: " + target[:-1])

    return config


def first_allowed_cpu() -> str:
    text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Cpus_allowed_list:\s*(.+)$", text, re.M)
    if not match:
        raise RuntimeError("cannot determine current Cpus_allowed_list")
    return match.group(1).strip().split(",")[0].split("-")[0]


def host_inventory(cpu: str) -> dict[str, Any]:
    cpu_model = ""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
                break
    return {
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "cpu_model": cpu_model,
        "cpu_count": os.cpu_count() or 1,
        "cpuset": cpu,
        "docker_server_version": output(["docker", "version", "--format", "{{.Server.Version}}"]),
    }


def image_tags(config: dict[str, Any]) -> dict[str, str]:
    short = config["protos_revision"][:12]
    return {
        "protos": f"protos-benchmarks-perf010a-post-i068-protos:{short}",
        "python": f"protos-benchmarks-perf010a-post-i068-python:{short}",
        "javascript": f"protos-benchmarks-perf010a-post-i068-node:{short}",
    }


def build_images(config: dict[str, Any]) -> dict[str, str]:
    tags = image_tags(config)
    toolchain = config["toolchain"]
    driver = config["protos_driver"]

    print("PERF010A_POST_I068_BUILD_BEGIN language=protos", flush=True)
    run(
        [
            "docker", "build",
            "--build-arg", "GRAAL_BASE=" + toolchain["container_image"],
            "--build-arg", "PROTOS_REPOSITORY=" + config["protos_repository"],
            "--build-arg", "PROTOS_REVISION=" + config["protos_revision"],
            "--build-arg", "VARIANT=baseline",
            "--build-arg", "ABLATION_PATCH=" + Path(driver["ablation_patch"]).name,
            "--build-arg", "ABLATION_SLICE=" + config["slice"],
            "--build-arg", "EXPECTED_GRAALVM_RELEASE=" + toolchain["graalvm_release"],
            "--build-arg", "EXPECTED_JDK_VERSION=" + toolchain["jdk_version"],
            "--build-arg", "EXPECTED_CONTAINER_IMAGE=" + toolchain["container_image"],
            "--build-arg", "EXPECTED_GRAAL_COMPONENTS_VERSION=" + toolchain["graal_truffle_version"],
            "--build-arg", "EXPECTED_MAVEN_VERSION=" + toolchain["maven_version"],
            "--build-arg", "PYTHON_PACKAGE=" + toolchain["python_package"],
            "--label", "org.opencontainers.image.revision=" + config["protos_revision"],
            "--label", "org.protos-benchmarks.perf010a.slice=" + config["slice"],
            "-t", tags["protos"],
            "-f", driver["dockerfile"],
            ".",
        ]
    )
    print("PERF010A_POST_I068_BUILD_PASS language=protos", flush=True)

    print("PERF010A_POST_I068_BUILD_BEGIN language=python", flush=True)
    run(
        [
            "docker", "build", "--pull",
            "--build-arg", "PYTHON_BASE=" + config["comparison_runtimes"]["python"]["base"],
            "-t", tags["python"],
            "-f", "docker/python-perf004a/Dockerfile",
            ".",
        ]
    )
    print("PERF010A_POST_I068_BUILD_PASS language=python", flush=True)

    print("PERF010A_POST_I068_BUILD_BEGIN language=javascript", flush=True)
    run(
        [
            "docker", "build", "--pull",
            "--build-arg", "NODE_BASE=" + config["comparison_runtimes"]["javascript"]["base"],
            "-t", tags["javascript"],
            "-f", "docker/node-perf004a/Dockerfile",
            ".",
        ]
    )
    print("PERF010A_POST_I068_BUILD_PASS language=javascript", flush=True)
    return tags


def docker_command(cpu: str, image: str, *args: str) -> list[str]:
    return [
        "docker", "run", "--rm",
        "--network", "none",
        "--cpuset-cpus", cpu,
        image,
        *args,
    ]


def docker_entrypoint(cpu: str, image: str, entrypoint: str, *args: str) -> subprocess.CompletedProcess[str]:
    completed = run(
        [
            "docker", "run", "--rm",
            "--network", "none",
            "--cpuset-cpus", cpu,
            "--entrypoint", entrypoint,
            image,
            *args,
        ],
        capture=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"container probe failed image={image} entrypoint={entrypoint} rc={completed.returncode}\n"
            f"stdout:\n{(completed.stdout or '')[-4000:]}\n"
            f"stderr:\n{(completed.stderr or '')[-4000:]}"
        )
    return completed


def image_identity(tag: str) -> dict[str, Any]:
    data = json.loads(output(["docker", "image", "inspect", tag]))[0]
    return {
        "tag": tag,
        "id": data.get("Id", ""),
        "repo_digests": data.get("RepoDigests") or [],
    }


def protos_runtime_probe(config: dict[str, Any], tag: str, cpu: str) -> str:
    driver = config["protos_driver"]
    completed = docker_entrypoint(
        cpu,
        tag,
        "java",
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        f"{driver['diagnostic_dir']}:/opt/protos/lib/protos.jar:{driver['runtime_dir']}/*",
        driver["runtime_probe"],
    )
    observed = next(
        (
            line.split("=", 1)[1].strip()
            for line in (completed.stdout or "").splitlines()
            if line.startswith("PERF006D_RUNTIME=")
        ),
        "",
    )
    if observed != EXPECTED_RUNTIME:
        raise RuntimeError(f"Protos runtime mismatch expected={EXPECTED_RUNTIME!r} observed={observed!r}")
    if FALLBACK_WARNING_RE.search(completed.stderr or ""):
        raise RuntimeError("Protos runtime probe emitted optimizing-runtime fallback warning")
    return observed


def product_revision_probe(config: dict[str, Any], tag: str, cpu: str) -> str:
    data = json.loads(output(["docker", "image", "inspect", tag]))[0]
    labels = (data.get("Config") or {}).get("Labels") or {}
    observed = labels.get("org.opencontainers.image.revision", "")
    if observed != config["protos_revision"]:
        raise RuntimeError(f"built Protos source revision mismatch: {observed!r}")
    return observed


def product_version_probe(config: dict[str, Any], tag: str, cpu: str) -> str:
    import xml.etree.ElementTree as E

    source_root = config["protos_driver"]["source_root"]
    completed = docker_entrypoint(cpu, tag, "cat", f"{source_root}/pom.xml")
    root = E.fromstring(completed.stdout or "")
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    version = root.find("m:version", ns)
    observed = version.text.strip() if version is not None and version.text else ""
    if observed != config["protos_version"]:
        raise RuntimeError(f"built Protos version mismatch: {observed!r}")
    return observed


def java_version_probe(config: dict[str, Any], tag: str, cpu: str) -> str:
    completed = docker_entrypoint(cpu, tag, "java", "-version")
    text = (completed.stderr or completed.stdout or "").strip()
    if config["toolchain"]["jdk_version"] not in text or "GraalVM" not in text:
        raise RuntimeError("built Protos Java/GraalVM runtime identity mismatch")
    return text


def runtime_version_probe(config: dict[str, Any], tags: dict[str, str], cpu: str) -> dict[str, str]:
    py = docker_entrypoint(cpu, tags["python"], "python3", "--version")
    py_text = ((py.stdout or "") + (py.stderr or "")).strip()
    if config["comparison_runtimes"]["python"]["version"] not in py_text:
        raise RuntimeError("Python runtime identity mismatch: " + py_text)

    node = docker_entrypoint(cpu, tags["javascript"], "node", "--version")
    node_text = ((node.stdout or "") + (node.stderr or "")).strip()
    expected_node = "v" + config["comparison_runtimes"]["javascript"]["version"]
    if node_text != expected_node:
        raise RuntimeError("Node runtime identity mismatch: " + node_text)
    return {"python": py_text, "javascript": node_text}


def variant_probe(config: dict[str, Any], tag: str, cpu: str) -> dict[str, str]:
    variant = docker_entrypoint(cpu, tag, "cat", "/opt/perf010a/variant.txt")
    ablation = docker_entrypoint(cpu, tag, "cat", "/opt/perf010a/ablation-slice.txt")
    variant_text = (variant.stdout or "").strip()
    ablation_text = (ablation.stdout or "").strip()
    if variant_text != "baseline" or ablation_text != "none":
        raise RuntimeError(
            f"post-I068 image must be unmodified baseline; variant={variant_text!r} ablation={ablation_text!r}"
        )
    return {"variant": variant_text, "ablation_slice": ablation_text}


def current_workload_identity_probe(
    config: dict[str, Any], tag: str, cpu: str, entries: list[dict[str, Any]]
) -> dict[str, str]:
    source_root = config["protos_driver"]["source_root"]
    result: dict[str, str] = {}
    for entry in entries:
        relative = "protos/benchmarks/" + entry["protos"]
        completed = docker_entrypoint(
            cpu,
            tag,
            "cat",
            f"{source_root}/{relative}",
        )
        content = (completed.stdout or "").encode("utf-8")
        header = f"blob {len(content)}\0".encode("ascii")
        observed = hashlib.sha1(header + content).hexdigest()
        expected = entry["historical_protos_blob_sha"]
        if observed != expected:
            raise RuntimeError(
                f"workload identity mismatch {entry['id']}: current={observed} historical={expected}"
            )
        result[entry["id"]] = observed
    return result


def build_and_probe_images(
    config: dict[str, Any], cpu: str, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    tags = build_images(config)
    probes = {
        "protos_runtime": protos_runtime_probe(config, tags["protos"], cpu),
        "protos_revision": product_revision_probe(config, tags["protos"], cpu),
        "protos_version": product_version_probe(config, tags["protos"], cpu),
        "java_version": java_version_probe(config, tags["protos"], cpu),
        "comparison_runtime_versions": runtime_version_probe(config, tags, cpu),
        "protos_variant": variant_probe(config, tags["protos"], cpu),
        "workload_blob_identity": current_workload_identity_probe(config, tags["protos"], cpu, entries),
    }
    return {
        "tags": tags,
        "images": {name: image_identity(tag) for name, tag in tags.items()},
        "probes": probes,
    }


def parse_json_last_line(text: str, label: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(label + " emitted no stdout")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(label + " emitted invalid JSON: " + lines[-1]) from exc
    if payload.get("schema_version") != 1:
        raise RuntimeError(label + " payload schema mismatch")
    return payload


def protos_source_path(config: dict[str, Any], entry: dict[str, Any]) -> str:
    return config["protos_driver"]["corpus_dir"] + "/" + entry["protos"]


def host_workload_path(language: str, entry: dict[str, Any]) -> str:
    return "/opt/benchmark/workloads/" + entry[language]


def timed_unit(
    config: dict[str, Any],
    tags: dict[str, str],
    cpu: str,
    language: str,
    entry: dict[str, Any],
    *,
    warmup: int,
    steady: int,
) -> tuple[dict[str, Any], str, str]:
    if language == "protos":
        driver = config["protos_driver"]
        completed = docker_entrypoint(
            cpu,
            tags["protos"],
            "java",
            "-Xss128m",
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            f"{driver['diagnostic_dir']}:/opt/protos/lib/protos.jar:{driver['runtime_dir']}/*",
            driver["timing_driver"],
            protos_source_path(config, entry),
            entry["expected"],
            str(warmup),
            str(steady),
        )
    elif language == "python":
        completed = run(
            docker_command(
                cpu,
                tags["python"],
                "/opt/benchmark/timing_driver.py",
                "execution",
                host_workload_path(language, entry),
                entry["expected"],
                str(warmup),
                str(steady),
            ),
            capture=True,
            check=False,
        )
    elif language == "javascript":
        completed = run(
            docker_command(
                cpu,
                tags["javascript"],
                "/opt/benchmark/timing_driver.mjs",
                "execution",
                host_workload_path(language, entry),
                entry["expected"],
                str(warmup),
                str(steady),
            ),
            capture=True,
            check=False,
        )
    else:
        raise ValueError("unknown language: " + language)

    if completed.returncode != 0:
        raise RuntimeError(
            f"timed unit failed language={language} workload={entry['id']} rc={completed.returncode}\n"
            f"stdout:\n{(completed.stdout or '')[-6000:]}\n"
            f"stderr:\n{(completed.stderr or '')[-6000:]}"
        )
    payload = parse_json_last_line(completed.stdout or "", f"{language} {entry['id']}")
    if str(payload.get("expected")) != entry["expected"]:
        raise RuntimeError("timed-unit expected-result identity mismatch")
    warmup_ns = payload.get("warmup_ns")
    steady_ns = payload.get("steady_ns")
    if not isinstance(warmup_ns, list) or len(warmup_ns) != warmup:
        raise RuntimeError("timed-unit warmup sample-count mismatch")
    if not isinstance(steady_ns, list) or len(steady_ns) != steady:
        raise RuntimeError("timed-unit steady sample-count mismatch")
    if any(not isinstance(value, int) or value <= 0 for value in list(warmup_ns) + list(steady_ns)):
        raise RuntimeError("timed-unit contains non-positive sample")

    if language == "protos":
        if payload.get("runtime") != EXPECTED_RUNTIME:
            raise RuntimeError("Protos timed-unit optimizing runtime identity mismatch")
        for flag in (
            "source_reused",
            "process_reused",
            "context_reused",
            "fresh_activation_per_iteration",
        ):
            if payload.get(flag) is not True:
                raise RuntimeError("Protos timed-unit hosting contract failed: " + flag)
        if payload.get("jfr_recording_phase") != "none":
            raise RuntimeError("JFR leaked into post-I068 Protos timing")
        if FALLBACK_WARNING_RE.search(completed.stderr or ""):
            raise RuntimeError("Protos timed-unit emitted optimizing-runtime fallback warning")
    else:
        for flag in ("module_reused", "run_binding_reused"):
            if payload.get(flag) is not True:
                raise RuntimeError(f"{language} timed-unit hosting contract failed: {flag}")

    return payload, completed.stdout or "", completed.stderr or ""


def summarize_ns(values: list[int]) -> dict[str, float | int]:
    if not values or any(not isinstance(value, int) or value <= 0 for value in values):
        raise ValueError("timing samples must be positive integers")
    ordered = sorted(values)
    median = float(statistics.median(ordered))
    deviations = [abs(float(value) - median) for value in ordered]
    p95_index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return {
        "count": len(ordered),
        "median_ns": median,
        "mad_ns": float(statistics.median(deviations)),
        "min_ns": ordered[0],
        "max_ns": ordered[-1],
        "p95_ns": ordered[p95_index],
    }


def stationarity(steady_ns: list[int]) -> dict[str, float]:
    if len(steady_ns) != 100:
        raise RuntimeError("stationarity diagnostics require exactly 100 steady samples")
    first = steady_ns[:25]
    last = steady_ns[75:]
    first_median = float(statistics.median(first))
    last_median = float(statistics.median(last))
    return {
        "first_quarter_median_ns": first_median,
        "last_quarter_median_ns": last_median,
        "last_quarter_vs_first_quarter_percent": 100.0 * (last_median - first_median) / first_median,
    }


def git_head() -> str:
    return output(["git", "rev-parse", "HEAD"])


def require_clean_exact_harness(revision: str) -> None:
    if not SHA_RE.fullmatch(revision):
        raise RuntimeError("harness revision must be an exact lowercase 40-character SHA")
    head = git_head()
    if head != revision:
        raise RuntimeError(f"harness revision mismatch: HEAD={head} expected={revision}")
    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise RuntimeError("reference requires a clean exact harness revision")


def correctness_gate(
    config: dict[str, Any], tags: dict[str, str], cpu: str, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    correctness: list[dict[str, Any]] = []
    for entry in entries:
        for language in LANGUAGES:
            payload, _, stderr = timed_unit(
                config,
                tags,
                cpu,
                language,
                entry,
                warmup=0,
                steady=1,
            )
            correctness.append(
                {
                    "workload": entry["id"],
                    "language": language,
                    "expected": entry["expected"],
                    "pass": True,
                    "runtime": payload.get("runtime", language),
                    "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
                }
            )
            print(f"CORRECTNESS PASS language={language} workload={entry['id']}", flush=True)
    return correctness


def smoke() -> None:
    config = validate()
    cpu = first_allowed_cpu()
    entries = suite_entries(config)
    build = build_and_probe_images(config, cpu, entries)
    entry = next(item for item in entries if item["id"] == config["smoke"]["workload"])
    for language in LANGUAGES:
        timed_unit(
            config,
            build["tags"],
            cpu,
            language,
            entry,
            warmup=int(config["smoke"]["warmup_iterations"]),
            steady=int(config["smoke"]["steady_iterations"]),
        )
        print(f"SMOKE PASS language={language} workload={entry['id']}", flush=True)
    print("PERF010A_POST_I068_SMOKE=PASS")
    print("PERF010A_POST_I068_SMOKE_RETAINED=NO")
    print("PERF010A_POST_I068_SMOKE_TIMING_INTERPRETATION=FORBIDDEN")


def write_summary_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "workload",
        "classification",
        "historical_protos_over_node_ratio",
        "current_protos_over_node_ratio",
        "historical_protos_over_python_ratio",
        "current_protos_over_python_ratio",
        "current_protos_median_ns",
        "current_node_median_ns",
        "current_python_median_ns",
        "current_node_gap_over_historical",
        "current_python_gap_over_historical",
    ]
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    str(row[column])
                    for column in columns
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def reference(harness_revision: str, output_dir: Path) -> None:
    config = validate()
    require_clean_exact_harness(harness_revision)
    expected_output = ROOT / config["reference_output"]
    if output_dir.resolve() != expected_output.resolve():
        raise RuntimeError(f"reference output must be {expected_output}, got {output_dir}")
    if output_dir.exists():
        raise RuntimeError("reference output already exists: " + str(output_dir))

    cpu = first_allowed_cpu()
    entries = suite_entries(config)
    historical = historical_ratio_map()
    build = build_and_probe_images(config, cpu, entries)
    tags = build["tags"]

    correctness = correctness_gate(config, tags, cpu, entries)

    policy = config["measurement_contract"]
    forks_count = int(policy["persistent_forks_per_language_workload"])
    warmup_count = int(policy["warmup_iterations_per_fork"])
    steady_count = int(policy["steady_samples_per_fork"])

    output_dir.mkdir(parents=True)
    logs_dir = output_dir / "logs"
    logs_dir.mkdir()

    raw_cases: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for entry in entries:
        by_language: dict[str, dict[str, Any]] = {}
        for language in LANGUAGES:
            steady_forks: list[list[int]] = []
            warmup_forks: list[list[int]] = []
            fork_records: list[dict[str, Any]] = []
            for fork_index in range(1, forks_count + 1):
                label = entry["id"].replace("/", "__") + f"--{language}--fork{fork_index}"
                print(
                    f"MEASURE BEGIN language={language} workload={entry['id']} "
                    f"fork={fork_index}/{forks_count} warmup={warmup_count} steady={steady_count}",
                    flush=True,
                )
                payload, stdout_text, stderr_text = timed_unit(
                    config,
                    tags,
                    cpu,
                    language,
                    entry,
                    warmup=warmup_count,
                    steady=steady_count,
                )
                warm_values = [int(value) for value in payload["warmup_ns"]]
                steady_values = [int(value) for value in payload["steady_ns"]]
                warmup_forks.append(warm_values)
                steady_forks.append(steady_values)
                stdout_path = logs_dir / f"{label}.stdout.log"
                stderr_path = logs_dir / f"{label}.stderr.log"
                stdout_path.write_text(stdout_text, encoding="utf-8")
                stderr_path.write_text(stderr_text, encoding="utf-8")
                fork_records.append(
                    {
                        "fork": fork_index,
                        "warmup_ns": warm_values,
                        "steady_ns": steady_values,
                        "stationarity": stationarity(steady_values),
                        "stdout_log": "logs/" + stdout_path.name,
                        "stderr_log": "logs/" + stderr_path.name,
                        "stdout_sha256": sha256_file(stdout_path),
                        "stderr_sha256": sha256_file(stderr_path),
                    }
                )
                print(
                    f"MEASURE PASS language={language} workload={entry['id']} fork={fork_index}/{forks_count}",
                    flush=True,
                )

            warm_flat = [value for fork in warmup_forks for value in fork]
            steady_flat = [value for fork in steady_forks for value in fork]
            item_summary = {
                "workload": entry["id"],
                "classification": entry["classification"],
                "language": language,
                "warmup": summarize_ns(warm_flat),
                "steady": summarize_ns(steady_flat),
                "fork_stationarity": [record["stationarity"] for record in fork_records],
            }
            summaries.append(item_summary)
            by_language[language] = item_summary
            raw_cases.append(
                {
                    "workload": entry["id"],
                    "classification": entry["classification"],
                    "language": language,
                    "expected": entry["expected"],
                    "equivalence": entry["equivalence"],
                    "historical_protos_blob_sha": entry["historical_protos_blob_sha"],
                    "historical_python_blob_sha": entry["historical_python_blob_sha"],
                    "historical_javascript_blob_sha": entry["historical_javascript_blob_sha"],
                    "forks": fork_records,
                }
            )

        protos_median = float(by_language["protos"]["steady"]["median_ns"])
        python_median = float(by_language["python"]["steady"]["median_ns"])
        node_median = float(by_language["javascript"]["steady"]["median_ns"])
        current_python = protos_median / python_median
        current_node = protos_median / node_median
        historical_python = historical[entry["id"]]["python"]
        historical_node = historical[entry["id"]]["javascript"]
        summary_rows.append(
            {
                "workload": entry["id"],
                "classification": entry["classification"],
                "historical_protos_over_node_ratio": historical_node,
                "current_protos_over_node_ratio": current_node,
                "historical_protos_over_python_ratio": historical_python,
                "current_protos_over_python_ratio": current_python,
                "current_protos_median_ns": protos_median,
                "current_node_median_ns": node_median,
                "current_python_median_ns": python_median,
                "current_node_gap_over_historical": current_node / historical_node,
                "current_python_gap_over_historical": current_python / historical_python,
            }
        )

    primary_rows = [row for row in summary_rows if row["workload"] in PRIMARY_IDS]
    sentinel_row = next(row for row in summary_rows if row["workload"] == SENTINEL_ID)
    node_range = (
        min(row["current_protos_over_node_ratio"] for row in primary_rows),
        max(row["current_protos_over_node_ratio"] for row in primary_rows),
    )
    python_range = (
        min(row["current_protos_over_python_ratio"] for row in primary_rows),
        max(row["current_protos_over_python_ratio"] for row in primary_rows),
    )

    metadata = {
        "schema_version": 1,
        "perf_item": "PERF010-A",
        "parent_perf_item": "PERF010",
        "slice": config["slice"],
        "phase": config["phase"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "harness_revision": harness_revision,
        "product_revision": config["protos_revision"],
        "product_version": config["protos_version"],
        "historical_comparison": config["historical_comparison"],
        "toolchain": config["toolchain"],
        "comparison_runtimes": config["comparison_runtimes"],
        "runtime_probes": build["probes"],
        "images": build["images"],
        "host": host_inventory(cpu),
        "cpu_policy": {"mechanism": "cpuset-cpus", "cpuset": cpu},
        "network": "none",
        "measurement_policy": policy,
        "correctness_cases": len(correctness),
        "profiling": False,
        "jfr": False,
        "compiler_tracing": False,
        "igv": False,
        "allocation_instrumentation": False,
    }
    raw_payload = {
        "schema_version": 1,
        "harness_revision": harness_revision,
        "product_revision": config["protos_revision"],
        "correctness": correctness,
        "cases": raw_cases,
    }
    summary_payload = {
        "schema_version": 1,
        "harness_revision": harness_revision,
        "product_revision": config["protos_revision"],
        "historical_comparison_source": "results/perf004-a",
        "historical_comparison_causal": False,
        "primary_statistic": "median",
        "per_language_workload_summaries": summaries,
        "comparison_rows": summary_rows,
        "primary_common_path": list(PRIMARY_IDS),
        "secondary_recursive_scale_sentinel": SENTINEL_ID,
        "post_i068_common_protos_over_node_range": list(node_range),
        "post_i068_common_protos_over_python_range": list(python_range),
        "post_i068_factorial_protos_over_node": sentinel_row["current_protos_over_node_ratio"],
        "post_i068_factorial_protos_over_python": sentinel_row["current_protos_over_python_ratio"],
        "machine_readable_conclusions": {
            "PERF010A_POST_I068_BASELINE": "ESTABLISHED",
            "PRODUCT_REVISION": config["protos_revision"],
            "POST_I068_COMMON_GAP_SCALE": "PER_WORKLOAD_RANGES_ONLY",
            "POST_I068_COMMON_PROTOS_OVER_NODE_RANGE": list(node_range),
            "POST_I068_COMMON_PROTOS_OVER_PYTHON_RANGE": list(python_range),
            "POST_I068_FACTORIAL_GAP_SCALE": {
                "PROTOS_OVER_NODE": sentinel_row["current_protos_over_node_ratio"],
                "PROTOS_OVER_PYTHON": sentinel_row["current_protos_over_python_ratio"],
            },
            "HISTORICAL_COMPARISON_SOURCE": "results/perf004-a",
            "HISTORICAL_COMPARISON_CAUSAL": "NO",
            "I068_ATTRIBUTABLE_FRACTION": "NOT_ESTABLISHED",
            "PERF010A_DOMINANT_CAUSE": "NOT_ESTABLISHED",
            "ATTRIBUTABLE_FRACTION": "NOT_ESTABLISHED",
            "PRODUCTION_OPTIMIZATION_SELECTED": "NO",
            "PERF010_READY": "NO",
        },
    }

    metadata_path = output_dir / "run-metadata.json"
    raw_path = output_dir / "raw.json"
    summary_path = output_dir / "summary.json"
    tsv_path = output_dir / "summary.tsv"
    readme_path = output_dir / "README.md"

    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raw_path.write_text(json.dumps(raw_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary_tsv(tsv_path, summary_rows)

    readme = [
        "# PERF010-A post-I068 current cross-language baseline",
        "",
        f"- Harness revision: `{harness_revision}`",
        f"- Product revision: `{config['protos_revision']}`",
        f"- Product version: `{config['protos_version']}`",
        f"- Historical comparison: `results/perf004-a` at harness `{EXPECTED_HISTORICAL_HARNESS_REVISION}` / Protos `{EXPECTED_HISTORICAL_PRODUCT_REVISION}`.",
        "- Historical comparison is descriptive, not causal attribution to I068.",
        f"- Persistent forks: {forks_count} per language/workload.",
        f"- Warmup: {warmup_count} iterations per fork.",
        f"- Steady: {steady_count} ordered samples per fork.",
        "- Network: none. CPU: one explicit cpuset CPU. Same host for all compared runtimes.",
        "- JFR/compiler tracing/IGV/allocation instrumentation: disabled for timing.",
        f"- Correctness: PASS {len(correctness)}/{len(correctness)} before reference timing.",
        "",
        "Raw ordered samples are authoritative in `raw.json`; `summary.json`, `summary.tsv`, and this README are derived views.",
        "",
        "## Primary common path",
        "",
        "| workload | historical Protos/Node | current Protos/Node | historical Protos/Python | current Protos/Python | current Protos median ns | current Node median ns | current Python median ns |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in primary_rows:
        readme.append(
            f"| {row['workload']} | {row['historical_protos_over_node_ratio']:.6f} | "
            f"{row['current_protos_over_node_ratio']:.6f} | "
            f"{row['historical_protos_over_python_ratio']:.6f} | "
            f"{row['current_protos_over_python_ratio']:.6f} | "
            f"{row['current_protos_median_ns']:.1f} | {row['current_node_median_ns']:.1f} | "
            f"{row['current_python_median_ns']:.1f} |"
        )
    readme += [
        "",
        "## Secondary recursive scale sentinel",
        "",
        "The factorial row is retained only as a recursive scale sentinel and is not generalized into the common-overhead result.",
        "",
        "| workload | historical Protos/Node | current Protos/Node | historical Protos/Python | current Protos/Python | current Protos median ns | current Node median ns | current Python median ns |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| {sentinel_row['workload']} | {sentinel_row['historical_protos_over_node_ratio']:.6f} | "
        f"{sentinel_row['current_protos_over_node_ratio']:.6f} | "
        f"{sentinel_row['historical_protos_over_python_ratio']:.6f} | "
        f"{sentinel_row['current_protos_over_python_ratio']:.6f} | "
        f"{sentinel_row['current_protos_median_ns']:.1f} | {sentinel_row['current_node_median_ns']:.1f} | "
        f"{sentinel_row['current_python_median_ns']:.1f} |",
        "",
        "## Descriptive gap movement",
        "",
        "`summary.tsv` records `current gap / historical gap` separately for Node and Python on every workload. These are descriptive movements across many product revisions, not an I068 speedup or attributable fraction.",
        "",
        "## Machine-readable conclusions",
        "",
        "```text",
        "PERF010A_POST_I068_BASELINE=ESTABLISHED",
        f"PRODUCT_REVISION={config['protos_revision']}",
        "POST_I068_COMMON_GAP_SCALE=PER_WORKLOAD_RANGES_ONLY",
        f"POST_I068_COMMON_PROTOS_OVER_NODE_RANGE={node_range[0]:.6f}..{node_range[1]:.6f}",
        f"POST_I068_COMMON_PROTOS_OVER_PYTHON_RANGE={python_range[0]:.6f}..{python_range[1]:.6f}",
        f"POST_I068_FACTORIAL_PROTOS_OVER_NODE={sentinel_row['current_protos_over_node_ratio']:.6f}",
        f"POST_I068_FACTORIAL_PROTOS_OVER_PYTHON={sentinel_row['current_protos_over_python_ratio']:.6f}",
        "HISTORICAL_COMPARISON_SOURCE=results/perf004-a",
        "HISTORICAL_COMPARISON_CAUSAL=NO",
        "I068_ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED",
        "PERF010A_DOMINANT_CAUSE=NOT_ESTABLISHED",
        "ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED",
        "PRODUCTION_OPTIMIZATION_SELECTED=NO",
        "PERF010_READY=NO",
        "```",
        "",
    ]
    readme_path.write_text("\n".join(readme), encoding="utf-8")

    manifest_files = [readme_path, raw_path, metadata_path, summary_path, tsv_path]
    manifest_files += sorted(path for path in logs_dir.iterdir() if path.is_file())
    manifest_lines = [
        f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}"
        for path in sorted(manifest_files)
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    print("PERF010A_POST_I068_REFERENCE=PASS")
    print("PERF010A_POST_I068_BASELINE=ESTABLISHED")
    print("PRODUCT_REVISION=" + config["protos_revision"])
    for row in summary_rows:
        print(
            f"WORKLOAD={row['workload']} "
            f"PROTOS_OVER_NODE={row['current_protos_over_node_ratio']:.6f} "
            f"PROTOS_OVER_PYTHON={row['current_protos_over_python_ratio']:.6f} "
            f"HISTORICAL_PROTOS_OVER_NODE={row['historical_protos_over_node_ratio']:.6f} "
            f"HISTORICAL_PROTOS_OVER_PYTHON={row['historical_protos_over_python_ratio']:.6f}"
        )
    print("POST_I068_COMMON_GAP_SCALE=PER_WORKLOAD_RANGES_ONLY")
    print(f"POST_I068_COMMON_PROTOS_OVER_NODE_RANGE={node_range[0]:.6f}..{node_range[1]:.6f}")
    print(f"POST_I068_COMMON_PROTOS_OVER_PYTHON_RANGE={python_range[0]:.6f}..{python_range[1]:.6f}")
    print(f"POST_I068_FACTORIAL_PROTOS_OVER_NODE={sentinel_row['current_protos_over_node_ratio']:.6f}")
    print(f"POST_I068_FACTORIAL_PROTOS_OVER_PYTHON={sentinel_row['current_protos_over_python_ratio']:.6f}")
    print("HISTORICAL_COMPARISON_SOURCE=results/perf004-a")
    print("HISTORICAL_COMPARISON_CAUSAL=NO")
    print("I068_ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED")
    print("PERF010A_DOMINANT_CAUSE=NOT_ESTABLISHED")
    print("ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED")
    print("PRODUCTION_OPTIMIZATION_SELECTED=NO")
    print("PERF010_READY=NO")
    print("PERF010A_POST_I068_OUTPUT=" + str(output_dir))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "smoke", "reference"))
    parser.add_argument("--harness-revision")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    if args.command == "validate":
        validate()
        print("PERF010A_POST_I068_VALIDATE=PASS")
        return 0
    if args.command == "smoke":
        smoke()
        return 0
    if not args.harness_revision:
        parser.error("reference requires --harness-revision")
    if not args.output_dir:
        parser.error("reference requires --output-dir")
    reference(args.harness_revision, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
