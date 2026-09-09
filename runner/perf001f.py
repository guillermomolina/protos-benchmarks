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

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "perf001f.json"
WORK = ROOT / ".work" / "perf001f"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_IDS = (
    "concurrency/future-roundtrip",
    "concurrency/future-fanout-all",
    "concurrency/parallel-roundtrip",
    "concurrency/parallel-array-map",
    "concurrency/actor-request-roundtrip",
    "concurrency/actor-fanout-requests",
)
EXPECTED_OPTIMIZING_RUNTIME = "com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime"
EXPECTED_CORPUS_PUBLICATION_REVISION = "faa1714523d68650447047a05d184ab17a747c06"
EXPECTED_REFERENCE_REVISION = "a08844c7ba59f4a213e4d318bcf3bee32393c2a9"
EXPECTED_RESULTS = (
    "1948000",
    "6233600",
    "38608200",
    "2128520",
    "2000",
    "4096",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def config() -> dict[str, Any]:
    return load_json(CONFIG_PATH)


def validate_revision(value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"expected exact lowercase 40-character Git SHA, got {value!r}")
    return value


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def checked_output(command: list[str], *, cwd: Path = ROOT) -> str:
    completed = run(command, cwd=cwd, capture=True)
    return completed.stdout.strip()


def last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def validate_config(*, announce: bool = True) -> dict[str, Any]:
    cfg = config()
    if cfg.get("schema_version") != 1:
        raise RuntimeError("unsupported PERF001-F harness configuration schema")
    if cfg.get("perf_item") != "PERF001" or cfg.get("slice") != "PERF001-F":
        raise RuntimeError("PERF001-F ownership metadata drift")
    revision = validate_revision(str(cfg.get("protos_revision", "")))
    if revision != EXPECTED_REFERENCE_REVISION:
        raise RuntimeError("PERF001-F reference revision drift")
    if cfg.get("corpus_publication_revision") != EXPECTED_CORPUS_PUBLICATION_REVISION:
        raise RuntimeError("PERF001-F corpus publication revision drift")
    if cfg.get("reference_gate_satisfied_by") != EXPECTED_REFERENCE_REVISION:
        raise RuntimeError("PERF001-F reference gate evidence drift")
    if cfg.get("canonical_corpus") != "protos/benchmarks/concurrency":
        raise RuntimeError("PERF001-F canonical corpus path drift")
    workloads = cfg.get("workloads")
    if not isinstance(workloads, list):
        raise RuntimeError("PERF001-F workload configuration is not a list")
    ids = tuple(str(entry.get("id")) for entry in workloads)
    expected = tuple(str(entry.get("expected")) for entry in workloads)
    if ids != EXPECTED_IDS:
        raise RuntimeError(f"PERF001-F workload identifier drift: {ids!r}")
    if expected != EXPECTED_RESULTS:
        raise RuntimeError(f"PERF001-F expected-result drift: {expected!r}")
    for entry in workloads:
        source = str(entry.get("source", ""))
        if not source.endswith(".protos") or "/" in source:
            raise RuntimeError(f"invalid canonical source leaf for {entry.get('id')}: {source!r}")
        widths = entry.get("cpu_widths")
        if entry.get("kind") == "fixed-cost" and widths != [1]:
            raise RuntimeError(f"fixed-cost workload must use width 1: {entry.get('id')}")
        if entry.get("kind") == "strong-scaling" and widths != [1, 2, 4, 8]:
            raise RuntimeError(f"strong-scaling width policy drift: {entry.get('id')}")
    policy = cfg.get("measurement_policy", {})
    if [policy.get("startup_samples"), policy.get("warmup_iterations"), policy.get("steady_samples")] != [10, 20, 20]:
        raise RuntimeError("PERF001-F sample-count policy drift")
    topology = cfg.get("topology_policy", {})
    if topology.get("candidate_physical_core_widths") != [1, 2, 4, 8]:
        raise RuntimeError("PERF001-F topology width policy drift")
    if topology.get("prefer_distinct_physical_cores_before_smt_siblings") is not True:
        raise RuntimeError("PERF001-F physical-core preference must remain enabled")
    if announce:
        print("PERF001F_CONFIG_VALIDATION: PASS")
    return cfg


def source_checkout(revision: str) -> Path:
    cfg = config()
    repository = str(cfg["protos_repository"])
    destination = WORK / "source" / revision
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "init", str(destination)], capture=True)
    run(["git", "-C", str(destination), "remote", "add", "origin", repository], capture=True)
    run(["git", "-C", str(destination), "fetch", "--depth", "1", "origin", revision], capture=True)
    run(["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"], capture=True)
    observed = checked_output(["git", "rev-parse", "HEAD"], cwd=destination)
    if observed != revision:
        raise RuntimeError(f"Protos source checkout mismatch: expected {revision}, got {observed}")
    return destination


def validate_toolchain_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "protos-toolchain-v1":
        raise RuntimeError("unsupported Protos toolchain schema")
    java = payload.get("java", {})
    graal = payload.get("graalvm", {})
    components = payload.get("graal_components", {})
    maven = payload.get("maven", {})
    policy = payload.get("policy", {})
    bytecode_release = java.get("bytecode_release")
    maven_version = str(maven.get("version", ""))
    graal_release = str(graal.get("release", ""))
    jdk_version = str(graal.get("jdk_version", ""))
    image = str(graal.get("container_image", ""))
    if not isinstance(bytecode_release, int) or bytecode_release < 21:
        raise RuntimeError("invalid Protos bytecode release")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", maven_version):
        raise RuntimeError("invalid pinned Maven version")
    if not graal_release or not jdk_version or not image:
        raise RuntimeError("incomplete GraalVM runtime identity")
    if str(components.get("version", "")) != graal_release:
        raise RuntimeError("Graal component/runtime version mismatch")
    if policy.get("floating_primary_runtime") is not False:
        raise RuntimeError("PERF001-F rejects a floating primary Protos runtime")
    if image.endswith(":latest") or ":latest-" in image:
        raise RuntimeError("PERF001-F rejects a floating GraalVM image")
    return {
        "schema": payload["schema"],
        "bytecode_release": bytecode_release,
        "maven_version": maven_version,
        "graalvm_release": graal_release,
        "jdk_feature": graal.get("jdk_feature"),
        "jdk_version": jdk_version,
        "graal_components_version": str(components["version"]),
        "container_channel": str(graal.get("container_channel", "")),
        "container_image": image,
    }


def read_toolchain(source: Path) -> dict[str, Any]:
    path = source / "toolchain.json"
    if not path.is_file():
        raise RuntimeError(f"measured Protos revision has no toolchain.json: {path}")
    return validate_toolchain_payload(load_json(path))


def image_tag(revision: str) -> str:
    return f"protos-benchmarks/protos:perf001f-{revision[:12]}"


def build_image(revision: str, source: Path, toolchain: dict[str, Any]) -> str:
    image = image_tag(revision)
    command = [
        "docker",
        "build",
        "--pull",
        "--build-arg",
        f"GRAAL_BASE={toolchain['container_image']}",
        "--build-arg",
        f"MAVEN_VERSION={toolchain['maven_version']}",
        "--build-arg",
        f"PROTOS_REPOSITORY={config()['protos_repository']}",
        "--build-arg",
        f"PROTOS_REVISION={revision}",
        "--label",
        f"org.opencontainers.image.revision={revision}",
        "-t",
        image,
        "-f",
        str(ROOT / "docker" / "protos-perf001f" / "Dockerfile"),
        ".",
    ]
    run(command)
    print(f"PERF001F_PROTOS_IMAGE_BUILD: PASS image={image}")
    return image


def parse_cpu_list(value: str) -> list[int]:
    cpus: set[int] = set()
    for part in value.strip().split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"descending CPU range: {part!r}")
            cpus.update(range(start, end + 1))
        else:
            cpus.add(int(part))
    return sorted(cpus)


def select_physical_core_series(
    records: Iterable[dict[str, int]], widths: Iterable[int]
) -> list[dict[str, Any]]:
    representatives: dict[tuple[int, int], int] = {}
    for record in records:
        key = (int(record["package"]), int(record["core"]))
        cpu = int(record["cpu"])
        current = representatives.get(key)
        if current is None or cpu < current:
            representatives[key] = cpu
    ordered = [
        cpu
        for _, cpu in sorted(
            representatives.items(), key=lambda item: (item[0][0], item[0][1], item[1])
        )
    ]
    series: list[dict[str, Any]] = []
    for width in widths:
        width = int(width)
        if width <= len(ordered):
            selected = ordered[:width]
            series.append(
                {
                    "width": width,
                    "cpus": selected,
                    "cpuset": ",".join(str(cpu) for cpu in selected),
                }
            )
    return series


def host_topology() -> dict[str, Any]:
    if not hasattr(os, "sched_getaffinity"):
        raise RuntimeError("PERF001-F topology audit requires Linux sched_getaffinity")
    allowed = sorted(os.sched_getaffinity(0))
    sysfs = Path("/sys/devices/system/cpu")
    records: list[dict[str, Any]] = []
    for cpu in allowed:
        base = sysfs / f"cpu{cpu}" / "topology"
        package_path = base / "physical_package_id"
        core_path = base / "core_id"
        siblings_path = base / "thread_siblings_list"
        if not package_path.is_file() or not core_path.is_file() or not siblings_path.is_file():
            raise RuntimeError(f"incomplete CPU topology for logical CPU {cpu}")
        package = int(package_path.read_text(encoding="utf-8").strip())
        core = int(core_path.read_text(encoding="utf-8").strip())
        siblings = [x for x in parse_cpu_list(siblings_path.read_text(encoding="utf-8")) if x in allowed]
        records.append(
            {
                "cpu": cpu,
                "package": package,
                "core": core,
                "allowed_thread_siblings": siblings,
            }
        )
    widths = config()["topology_policy"]["candidate_physical_core_widths"]
    series = select_physical_core_series(records, widths)
    if not series or series[0]["width"] != 1:
        raise RuntimeError("no eligible physical CPU core available for PERF001-F")
    physical_keys = {(int(r["package"]), int(r["core"])) for r in records}
    return {
        "allowed_logical_cpus": allowed,
        "eligible_physical_core_count": len(physical_keys),
        "logical_cpu_topology": records,
        "reference_series": series,
    }


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_observation_sources(source_checkout: Path) -> dict[str, dict[str, str]]:
    """Create correctness-only wrappers without changing canonical benchmark sources.

    Standalone file execution intentionally does not render its final expression.  Every
    canonical PERF001-F source ends in the exact terminal expression ``run()``; for the
    correctness gate only, replace that one terminal expression with ``print(run())`` so
    the production CLI exposes the already-defined result through ordinary program output.
    The canonical source and wrapper hashes are retained in correctness evidence.
    """
    cfg = config()
    canonical_root = source_checkout / cfg["canonical_corpus"]
    observed_root = WORK / "observed"
    if observed_root.exists():
        shutil.rmtree(observed_root)
    observed_root.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, str]] = {}
    for workload in cfg["workloads"]:
        leaf = str(workload["source"])
        canonical = canonical_root / leaf
        if not canonical.is_file():
            raise RuntimeError(f"missing canonical PERF001-F source: {canonical}")
        text = canonical.read_text(encoding="utf-8")
        body = text.rstrip()
        terminal = "run()"
        if not body.endswith(terminal):
            raise RuntimeError(f"canonical correctness source lacks terminal run(): {leaf}")
        prefix = body[: -len(terminal)]
        observed_text = prefix + "print(run())\n"
        observed = observed_root / leaf
        observed.write_text(observed_text, encoding="utf-8")
        result[leaf] = {
            "canonical_path": str(canonical.relative_to(source_checkout)),
            "canonical_sha256": sha256_text(text),
            "observation_path": str(observed.relative_to(ROOT)),
            "observation_sha256": sha256_text(observed_text),
            "observation_transform": "terminal run() -> print(run())",
        }
    return result


def runtime_probe(image: str, cpuset: str) -> str:
    completed = run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpuset-cpus",
            cpuset,
            "--entrypoint",
            "java",
            image,
            "--enable-native-access=ALL-UNNAMED",
            "-cp",
            "/opt/perf001f/probe:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
            "Dist001RuntimeProbe",
        ],
        capture=True,
        check=False,
    )
    observed = last_nonempty_line(completed.stdout or "")
    if completed.returncode != 0 or observed != EXPECTED_OPTIMIZING_RUNTIME:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(
            "PERF001-F optimizing runtime probe failed: "
            f"exit={completed.returncode} expected={EXPECTED_OPTIMIZING_RUNTIME!r} "
            f"observed={observed!r} stderr={stderr!r}"
        )
    print(f"PERF001F_OPTIMIZING_RUNTIME: PASS class={observed}")
    return observed


def image_identity(image: str) -> dict[str, Any]:
    raw = checked_output(["docker", "image", "inspect", image])
    payload = json.loads(raw)[0]
    return {
        "tag": image,
        "id": payload.get("Id", ""),
        "repo_digests": payload.get("RepoDigests") or [],
    }


def harness_revision() -> str:
    try:
        head = checked_output(["git", "rev-parse", "HEAD"])
        if not SHA_RE.fullmatch(head):
            return "WORKTREE_PRECOMMIT"
        dirty = checked_output(["git", "status", "--porcelain", "--untracked-files=all"])
        return head if not dirty else "WORKTREE_PRECOMMIT"
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        return "WORKTREE_PRECOMMIT"


def run_case(
    image: str, cpuset: str, observation_root: Path, source: str
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpuset-cpus",
            cpuset,
            "--mount",
            f"type=bind,src={observation_root.resolve()},dst=/opt/perf001f/observed,readonly",
            image,
            f"/opt/perf001f/observed/{source}",
        ],
        capture=True,
        check=False,
    )


def correctness(
    revision: str, source_checkout: Path, image: str, toolchain: dict[str, Any]
) -> dict[str, Any]:
    cfg = config()
    topology = host_topology()
    series_by_width = {int(entry["width"]): entry for entry in topology["reference_series"]}
    width_one = series_by_width.get(1)
    if width_one is None:
        raise RuntimeError("no width=1 CPU set available for optimizing runtime probe")
    optimizing_runtime = runtime_probe(image, str(width_one["cpuset"]))
    observations = prepare_observation_sources(source_checkout)
    observation_root = WORK / "observed"
    cases: list[dict[str, Any]] = []
    workload_passes = 0
    for workload in cfg["workloads"]:
        widths = [width for width in workload["cpu_widths"] if width in series_by_width]
        if not widths:
            raise RuntimeError(f"no eligible CPU width for {workload['id']}")
        workload_ok = True
        for width in widths:
            cpuset = str(series_by_width[width]["cpuset"])
            completed = run_case(image, cpuset, observation_root, str(workload["source"]))
            observed = last_nonempty_line(completed.stdout or "")
            expected = str(workload["expected"])
            case = {
                "id": workload["id"],
                "width": width,
                "cpuset": cpuset,
                "expected": expected,
                "observed": observed,
                "exit_status": completed.returncode,
                "status": "PASS" if completed.returncode == 0 and observed == expected else "FAIL",
                "observation": observations[str(workload["source"])],
            }
            cases.append(case)
            if case["status"] != "PASS":
                workload_ok = False
                stderr = (completed.stderr or "").strip()
                raise RuntimeError(
                    f"PERF001-F correctness failed for {workload['id']} width={width}: "
                    f"exit={completed.returncode} expected={expected!r} observed={observed!r} stderr={stderr!r}"
                )
            print(
                f"CORRECTNESS PASS {workload['id']} width={width} cpuset={cpuset} -> {observed}"
            )
        if workload_ok:
            workload_passes += 1
    payload = {
        "schema_version": 1,
        "purpose": "PERF001-F companion harness correctness/topology gate; not timing evidence",
        "protos_revision": revision,
        "harness_revision": harness_revision(),
        "toolchain": toolchain,
        "optimizing_runtime": optimizing_runtime,
        "topology": topology,
        "image": image_identity(image),
        "observation_sources": observations,
        "workloads_passed": workload_passes,
        "workloads_total": len(cfg["workloads"]),
        "cases": cases,
    }
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "correctness.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"PERF001F_WORKLOAD_CORRECTNESS: PASS {workload_passes}/{len(cfg['workloads'])}")
    print(f"PERF001F_CORRECTNESS_CONFIGURATIONS: PASS {len(cases)}/{len(cases)}")
    print(f"PERF001F_CORRECTNESS_EVIDENCE={path.relative_to(ROOT)}")
    return payload



# PERF001F-H2-PERSISTENT-DRIVER

def persistent_driver_command(
    image: str,
    cpuset: str,
    source: str,
    expected: str,
    warmup: int,
    steady: int,
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpuset-cpus",
        cpuset,
        "--entrypoint",
        "java",
        image,
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        "/opt/perf001f/driver:/opt/protos/lib/protos.jar:/opt/protos/lib/runtime/*",
        "Perf001fPersistentDriver",
        f"/opt/perf001f/corpus/{source}",
        expected,
        str(warmup),
        str(steady),
    ]


def run_persistent_driver_case(
    image: str,
    cpuset: str,
    workload: dict[str, Any],
    *,
    warmup: int,
    steady: int,
) -> dict[str, Any]:
    command = persistent_driver_command(
        image,
        cpuset,
        str(workload["source"]),
        str(workload["expected"]),
        warmup,
        steady,
    )
    completed = run(command, capture=True, check=False)
    stdout = completed.stdout or ""
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"persistent driver failed for {workload['id']}: "
            f"exit={completed.returncode} stderr={stderr!r} stdout={stdout!r}"
        )
    line = last_nonempty_line(stdout)
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"persistent driver emitted invalid JSON for {workload['id']}: {line!r}"
        ) from exc
    expected = str(workload["expected"])
    if payload.get("schema_version") != 1:
        raise RuntimeError("unsupported persistent-driver payload schema")
    if payload.get("expected") != expected:
        raise RuntimeError(f"persistent-driver expected-result identity mismatch for {workload['id']}")
    if payload.get("setup_run_binding_ready") is not True:
        raise RuntimeError(f"persistent-driver setup binding was not ready for {workload['id']}")
    if payload.get("setup_projection") != "terminal run() -> run":
        raise RuntimeError(f"persistent-driver setup projection drift for {workload['id']}")
    for flag in ("process_reused", "context_reused", "run_binding_reused"):
        if payload.get(flag) is not True:
            raise RuntimeError(f"persistent-driver reuse contract failed: {flag}")
    warmup_ns = payload.get("warmup_ns")
    steady_ns = payload.get("steady_ns")
    if not isinstance(warmup_ns, list) or len(warmup_ns) != warmup:
        raise RuntimeError(f"persistent-driver warmup count mismatch for {workload['id']}")
    if not isinstance(steady_ns, list) or len(steady_ns) != steady:
        raise RuntimeError(f"persistent-driver steady count mismatch for {workload['id']}")
    if any(not isinstance(value, int) or value <= 0 for value in warmup_ns + steady_ns):
        raise RuntimeError(f"persistent-driver non-positive sample for {workload['id']}")
    return payload


def persistent_smoke(
    revision: str,
    source_checkout: Path,
    image: str,
    toolchain: dict[str, Any],
) -> dict[str, Any]:
    cfg = config()
    topology = host_topology()
    series_by_width = {int(entry["width"]): entry for entry in topology["reference_series"]}
    width_one = series_by_width.get(1)
    if width_one is None:
        raise RuntimeError("no width=1 CPU set available for persistent-driver smoke")
    optimizing_runtime = runtime_probe(image, str(width_one["cpuset"]))
    cases: list[dict[str, Any]] = []
    for workload in cfg["workloads"]:
        widths = [width for width in workload["cpu_widths"] if width in series_by_width]
        if not widths:
            raise RuntimeError(f"no eligible CPU width for {workload['id']}")
        for width in widths:
            cpuset = str(series_by_width[width]["cpuset"])
            driver = run_persistent_driver_case(
                image,
                cpuset,
                workload,
                warmup=2,
                steady=2,
            )
            cases.append(
                {
                    "id": workload["id"],
                    "width": width,
                    "cpuset": cpuset,
                    "expected": str(workload["expected"]),
                    "driver": driver,
                }
            )
            print(
                f"PERSISTENT SMOKE PASS {workload['id']} width={width} cpuset={cpuset}"
            )
    payload = {
        "schema_version": 1,
        "purpose": "PERF001-F persistent production-hosted driver smoke; not reference timing evidence",
        "protos_revision": revision,
        "harness_revision": harness_revision(),
        "reference_gate": cfg["reference_gate"],
        "reference_gate_satisfied_by": cfg["reference_gate_satisfied_by"],
        "toolchain": toolchain,
        "optimizing_runtime": optimizing_runtime,
        "topology": topology,
        "image": image_identity(image),
        "driver_source_sha256": sha256_text(
            (ROOT / "docker/protos-perf001f/Perf001fPersistentDriver.java").read_text(encoding="utf-8")
        ),
        "cases": cases,
    }
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "persistent-smoke.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"PERF001F_PERSISTENT_DRIVER_SMOKE: PASS {len(cases)}/{len(cases)}")
    print("PERF001F_PERSISTENT_PROCESS_REUSE: PASS")
    print("PERF001F_PERSISTENT_CONTEXT_REUSE: PASS")
    print("PERF001F_PERSISTENT_RUN_BINDING_REUSE: PASS")
    print(f"PERF001F_PERSISTENT_SMOKE_EVIDENCE={path.relative_to(ROOT)}")
    print("PERF001F_REFERENCE_TIMING: NOT_RUN")
    return payload

def selected_revision(value: str | None) -> str:
    return validate_revision(value or str(config()["protos_revision"]))


def emit(payload: dict[str, Any], output: str | None) -> None:
    encoded = json.dumps(payload, indent=2) + "\n"
    if output:
        Path(output).write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="PERF001-F companion harness foundation")
    result.add_argument(
        "command", choices=["validate", "toolchain", "topology", "build", "correctness", "prepare", "persistent-smoke", "h2-prepare"]
    )
    result.add_argument("--protos-revision")
    result.add_argument("--output")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        cfg = validate_config(announce=args.command == "validate")
        if args.command == "validate":
            return 0
        revision = selected_revision(args.protos_revision)
        if args.command == "topology":
            emit(host_topology(), args.output)
            return 0
        source = source_checkout(revision)
        toolchain = read_toolchain(source)
        if args.command == "toolchain":
            emit(toolchain, args.output)
            return 0
        if args.command == "build":
            build_image(revision, source, toolchain)
            return 0
        image = image_tag(revision)
        if args.command == "correctness":
            correctness(revision, source, image, toolchain)
            return 0
        if args.command == "prepare":
            image = build_image(revision, source, toolchain)
            correctness(revision, source, image, toolchain)
            print("PERF001F_HARNESS_FOUNDATION: READY")
            print(f"PERF001F_REFERENCE_GATE: {cfg['reference_gate']}")
            print(f"PERF001F_REFERENCE_GATE_SATISFIED_BY: {cfg['reference_gate_satisfied_by']}")
            print("PERF001F_REFERENCE_TIMING: NOT_RUN")
            return 0
        if args.command == "persistent-smoke":
            persistent_smoke(revision, source, image, toolchain)
            return 0
        if args.command == "h2-prepare":
            image = build_image(revision, source, toolchain)
            correctness(revision, source, image, toolchain)
            persistent_smoke(revision, source, image, toolchain)
            print("PERF001F_H2_PERSISTENT_DRIVER: READY")
            print(f"PERF001F_REFERENCE_GATE_SATISFIED_BY: {cfg['reference_gate_satisfied_by']}")
            print("PERF001F_REFERENCE_TIMING: NOT_RUN")
            return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"PERF001-F harness error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
