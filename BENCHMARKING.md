# Benchmarking methodology

This repository is execution infrastructure and evidence for Protos performance
work. Canonical `PERFxxx` lifecycle state remains in `guillermomolina/protos`.

## PERF001-B scope

PERF001-B established the reproducible harness: Docker runtime images, exact
Protos revision pinning, host/runtime inventory capture, CPU-affinity policy, a
raw-result schema, and correctness smoke validation. It did not publish
benchmark timing results.

## PERF001-C scope

PERF001-C integrates the complete existing sequential corpus selected by the
canonical Protos `protos/benchmarks/` tree: seven `micro` workloads, two
`runtime` dispatch workloads, and two recursive algorithms. The companion
repository supplies Python and JavaScript implementations for each workload.

`config/suite.json` is the auditable mapping from canonical Protos source to
comparison-language source. Every entry records its exact expected stdout and a
short work-shape description. The correctness runner executes all three
languages and rejects the suite on the first mismatch. The resulting
`.work/perf001c-correctness.json` file is validation evidence, not a performance
measurement.

Python uses language-native classes/inheritance for the delegation analogues;
JavaScript uses direct prototype chains. That representation difference is
explicit rather than hidden. Both retain the same chain depth, recursive repeat
count, dispatch count, logical inputs, and observable result. Recursive repeat
workloads preserve recursion in both comparison languages. Protos runs with a recorded `-Xss64m` JVM thread stack, Python raises its
recursion limit to 50,000, and Node uses `--stack-size=32768`. These are runtime
configuration choices, not workload rewrites: the canonical 10,000-step recursive
work shape remains intact in all three implementations.

PERF001-C does not introduce idiomatic/library-accelerated variants and does not
publish timings. Measurement policy remains owned by later PERF001 slices.

## Source identity

Every retained result must identify both an exact 40-character Protos Git SHA
and an exact 40-character benchmark-harness Git SHA. Floating branch names are
not reference identities. The canonical Protos workload corpus is consumed from
`protos/benchmarks/` at the pinned Protos revision.

The PERF001-C corpus mapping is audited against Protos revision
`42b8264a36254dafbd97d80f5181790e28b9de12`. That revision exposes benchmark correctness through each program's
final expression value rather than an unqualified `print` dependency, while
preserving the original recursive workload shape. Future slices may deliberately
advance the Protos pin, but must revalidate corpus equivalence when they do.

## Correctness gate

Correctness precedes timing. A runtime or comparison implementation must produce
the documented observable result before samples can be accepted. Incorrect
output invalidates the run; it is never reported as a performance result.

The lightweight harness smoke (`-e "1 + 1"`, expected output `2`) remains a
separate infrastructure gate. PERF001-C additionally executes every mapped
canonical workload under Protos, Python, and JavaScript.

## Cross-language equivalence

The primary suite is algorithm-equivalent. It preserves explicit recursive
control flow, call counts, lookup/dispatch depth, logical inputs, and observable
results. It does not substitute built-in factorial/Fibonacci functions,
memoization, vectorized operations, or library shortcuts for the canonical
work.

Language object models are not pretended to be identical. JavaScript prototype
lookup is the nearest direct comparison for Protos delegation. Python
inheritance is retained as a separately identifiable native lookup analogue.
Results from a single workload or mechanism must not be generalized into a
whole-language performance claim.

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
records the actual Docker image ID and any repository digests resolved by
Docker, so the concrete image used by the host is preserved in the evidence.

## Graal/Truffle compatibility

The Protos runtime uses GraalVM Community for JDK 22 (`22.0.0`). That GraalVM
generation carries the Graal/Truffle 24.0.0 line used by the pinned Protos Maven
dependencies. Later PERF work must re-audit this compatibility when Protos
changes its Truffle dependency.

## Raw evidence

`schemas/result.schema.json` defines the minimum identity, environment, runtime,
and measurement fields for retained timing results.
`schemas/correctness.schema.json` defines the shape of the local PERF001-C
correctness record. Local validation artifacts under `.work/` are not reference
performance results. Reference timing publication is introduced only by later
PERF001 slices.


## PERF002-B external Truffle validation

`PERF002-B` is the companion-repository validation slice for the Protos-side
optimization published as `PERF002-A`. The canonical Protos ledger remains the
only owner of PERF002 lifecycle state.

This slice pins Protos revision
`3c93912a5579326374782a43527fbb51046f8f91` (`0.2.162-SNAPSHOT`) and does not
change the historical PERF001-C pin or comparison-language corpus.

PERF002-B is deliberately **non-timing evidence**. It validates the published
optimization under the optimizing Truffle runtime before later PERF001 timing
work proceeds. It records:

- the exact Protos revision;
- the exact harness commit whose files were executed;
- GraalVM Community JDK 22 image identity;
- external `truffle-runtime:24.0.0` identity/configuration;
- host CPU, architecture, kernel, memory and validation cpuset;
- direct observable results for the two PERF002 semantic regression cases;
- all 11 canonical PERF001 workloads in interpreter and optimizing-Truffle modes;
- raw stdout/stderr and compilation traces;
- ten consecutive optimizing-Truffle executions of the canonical polymorphic-dispatch workload at `-Xss128m`, all of which must pass;
- counts/guards for Truffle compilation success/failure and the previously
  observed `GraphTooBig`, `FrameWithoutBoxing`, deep-inlining,
  `StackOverflowError`, and `BootstrapMethodError` failure classes.

The Protos distributable remains unchanged by the companion harness:
`truffle-runtime` is supplied only by the external validation image. The runtime
uses `-Xss128m`, preserving the canonical 10,000-step recursive workload shape
using the first headroom value that passed 20/20 consecutive polymorphic-dispatch Truffle runs after `-Xss96m` was shown to fail intermittently.

A successful companion publication does not independently close PERF002. Its
exact evidence commit is subsequently recorded in
`guillermomolina/protos/docs/project/IMPLEMENTATION_STATUS.md`, where PERF002-B
and the parent PERF002 can be closed.
