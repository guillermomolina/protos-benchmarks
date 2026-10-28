# Current benchmarking methodology

This document describes the single active GraalVM harness. Historical
PERF-specific runners, Docker images, results and one-off investigations are
available from Git history, not from active executable entry points.

## Workloads and observable equivalence

`cases/catalog.json` owns the case identifiers, expected results,
and Protos/GraalJS/GraalPy sources. All three implementations must preserve
the declared observable result and comparable logical operations. Differences
between Protos message sends, JavaScript prototypes, and Python's object
model must not be disguised as identical runtime mechanisms. Comparisons of
one operation or workload must not be presented as whole-language rankings.

The active surface definitions reside in `harness/policy/cases.json`:

| Implementation | Surface | Timed operation |
| --- | --- | --- |
| Protos | `canonical` | Execute the prepared Polyglot `run` value |
| GraalJS | `executable-value` | Execute the Polyglot `run` value |
| GraalPy | `executable-value` | Execute the Polyglot `run` value |

The adapters share result normalization and the measurement engine. The
retired `dynamic` and `prepared` Protos adapters are not selectable.

## Source, runtime and host identity

Reference evidence identifies the exact source state and Git revision of
the selected Protos checkout and benchmark producer. Independent Protos,
GraalJS and GraalPy version selectors feed the exact result identity; the
Protos version must match its real checkout. The key also includes the
immutable local Podman image ID (not only the image tag), Java identity,
host/CPU identity, workload, measurement policy, benchmark Git revision
and producer source hashes, including `benchmark.py`. A dirty product
checkout is not eligible for reference timing unless explicitly allowed
for diagnostics.

## Correctness before timing

Before measuring a workload, run the same adapter and implementation in
correctness mode and compare the observable result with the catalog. A failed
correctness check invalidates the case and produces no accepted timing.
Raw output, failure reasons and measurement metadata are retained for review.

## Timing, warmup and instrumentation

`harness/policy/cases.json` defines the smoke/reference timing policy,
fixed warmup and steady sample counts, and JFR options. Smoke checks the
path cheaply; it is not accepted as reference performance evidence.
Warmup and steady samples remain distinguishable. For hot reference
timing, the selected value is the minimum observed elapsed time divided
by calls per sample among the steady samples. This selection neither waits
for convergence nor rejects a run for lack of timing stability; all raw
samples remain available for interpretation. Wrong results or invalid
evidence still fail the correctness and validity checks. Optional JFR
and compilation diagnostics can perturb timing and are separate from
uninstrumented reference measurements.

Cold and hot are distinct phases, not the `smoke` and `reference` stages:
`--temperature cold|hot|both` selects the requested reported phase. Cold
is the first guest invocation after Polyglot context setup; it is not
process/JVM startup. Hot uses the separate steady samples after the fixed
warmup. A single timing capture contains both phases, so a compatible
validated run can be reused for either phase without repeating timing.

## Container and result boundaries

`benchmark.py` is the single Linux-host entry point. Measurement uses
Podman with networking disabled and Maven in offline mode; it never pulls
or builds an image automatically. `peer-prepare` is an explicit separate
operation that may use the network to resolve a chosen GraalJS or GraalPy
version before measurement. Use `make help` for commands and `make validate`
to check the catalog/policies without launching a JVM. Image preparation
and any image pull remain explicit operations.

The active measurement driver keeps run records under the selected output
directory. Results with an exact compatible existing identity are reused
unless remeasurement was requested; incomplete or invalid evidence cannot
stand in for a valid measurement. `results/local/` is ignored by Git. The
retained peer baseline manifest and archive under `results/peer-baselines/`
remain available as historical comparators, not automatically accepted new
results for a different version or host.

## Graph evidence

`harness/policy/graphs.json` defines compilation graph policy. The optional
graph pipeline uses `harness/measure_graphs.py`,
`harness/graph_evidence.py`, and the host-side Podman IGV analyzer. Graph
instrumentation does not produce timing results and must be evaluated
separately. Captures, analyses and derived summaries retain their producer
identities so that different revisions cannot be silently compared as one.

## Binding rules

For required correctness gates and defensible performance interpretation,
see `AGENTS.work/PERFORMANCE.md`. For reproducible evidence and exact identity
requirements, see `AGENTS.work/REPRODUCIBILITY.md`.
