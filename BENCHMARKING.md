# Benchmarking methodology

This repository is execution infrastructure and evidence for Protos performance
work. Canonical `PERFxxx` lifecycle state remains in `guillermomolina/protos`.

## PERF001-B scope

PERF001-B establishes the reproducible harness only. It provides Docker runtime
images, exact Protos revision pinning, host/runtime inventory capture, CPU
affinity policy, a raw-result schema, and correctness smoke validation. It does
not publish benchmark timing results.

## Source identity

Every retained result must identify both an exact 40-character Protos Git SHA
and an exact 40-character harness Git SHA. Floating branch names are not
reference identities. The canonical Protos workload corpus is consumed from
`protos/benchmarks/` at the pinned Protos revision.

## Correctness gate

Correctness precedes timing. A runtime or comparison implementation must produce
the documented observable result before samples can be accepted. Incorrect
output invalidates the run; it is never reported as a performance result.

PERF001-B uses a minimal CLI smoke (`-e "1 + 1"`, expected output `2`) plus a
probe that confirms the canonical benchmark corpus is present in the pinned
Protos checkout. Full corpus execution belongs to PERF001-C after workload
equivalence is audited.

## Measurement classes

Startup, warmup, and steady state are independent measurement classes. Container
creation and container start latency are outside the Protos language-startup
timing boundary. JIT diagnostic instrumentation must be kept separate from
reference timings when it perturbs execution.

## Docker and CPU control

Reference comparisons run on the same Linux host. CPU-focused single-threaded
measurements should use `--cpuset-cpus` rather than scheduler quota as the
primary CPU-isolation mechanism. Parallel workloads must record their complete
CPU set. Runtime containers execute with networking disabled unless a workload
explicitly requires network access.

Runtime configurations use exact release tags. Each retained run additionally
records the actual Docker image ID and any repository digests resolved by Docker,
so the concrete image used by the host is preserved in the evidence.

## Graal/Truffle compatibility

The PERF001-B Protos runtime uses GraalVM Community for JDK 22 (`22.0.0`). That
GraalVM generation carries the Graal/Truffle 24.0.0 line used by the pinned
Protos Maven dependencies. Later PERF work must re-audit this compatibility when
Protos changes its Truffle dependency.

## Raw evidence

`schemas/result.schema.json` defines the minimum identity, environment, runtime,
and measurement fields for retained timing results. Local validation artifacts
are written under `.work/` and are not reference results. Reference result
publication is introduced only by later PERF001 slices.
