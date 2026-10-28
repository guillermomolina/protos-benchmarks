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

Reference evidence must identify the exact source state and Git revision of
the selected Protos checkout and benchmark producer. The driver records the
Protos project version, relevant GraalVM/JDK identity, host CPU and affinity,
measurement policy and producer source hashes. A dirty product checkout is
not eligible for reference timing unless explicitly allowed for diagnostics.
Versions of Protos, GraalJS, and GraalPy must be considered separately when
constructing the final version-aware result key.

## Correctness before timing

Before measuring a workload, run the same adapter and implementation in
correctness mode and compare the observable result with the catalog. A failed
correctness check invalidates the case and produces no accepted timing.
Raw output, failure reasons and measurement metadata are retained for review.

## Timing, warmup and instrumentation

`harness/policy/cases.json` defines the smoke/reference timing policies,
warmup counts, steady samples, admission rules and JFR options. Smoke verifies
the path cheaply; it is not accepted as reference performance evidence.
Warmup and steady-state samples remain distinguishable. Reference admission
checks stability and rejects invalid measurements rather than silently
publishing them. Optional JFR and compilation diagnostics can perturb timing
and must not be mistaken for uninstrumented reference measurements.

**Cold and hot are distinct measurements**, not synonyms for the `smoke` and
`reference` stages. A complete implementation must define their JVM and
warmup boundaries explicitly. The cold/hot selection and exact
version-discriminated reuse matrix are still being finalized.

## Container and result boundaries

`benchmark.py` is the single Linux-host entry point. It invokes Podman
without automatically pulling or building images. Use `make help` to inspect
its current commands; `make validate` checks the catalog and policies without
launching a JVM. Image preparation is always explicit.

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
