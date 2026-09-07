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

## IGV diagnostic analyzer

IdealGraphVisualizer analysis is deliberately isolated from benchmark runtime
images. `docker/igv-analyzer/Dockerfile` pins the Graal `vm-24.0.0` commit
`78238a5ee6e4ae827059c70549e286ae730b7730` and the matching mx `6.27.1` commit
`d0d6d6cd2f70bb384dfba9f3f66f3dab21392ae4`.

That Graal revision uses NetBeans 14 for IGV and its build still contains Java 7
release targets. JDK 22 rejects `javac --release 7`, so the analyzer image uses
JDK 17 exclusively for building and running the diagnostic exporter. This is a
tooling compatibility boundary, not a change to the JDK/GraalVM used by the
measured Protos runtime.

Build the tool with `make igv-analyzer-build` and verify it with
`make igv-analyzer-smoke`. Convert a BGV file from the directory containing it,
or from the repository root, with for example:

```sh
./scripts/igv_analyzer.sh analyze results/example.bgv > results/example.json
```

Runtime analysis uses `--network none`. The current working directory is mounted
at `/work` so input paths and any explicitly requested output paths remain host
artifacts rather than being trapped inside the diagnostic container.

## PERF003-A external compilability diagnostic

`PERF003-A` uses a non-timing external diagnostic gate against exact Protos
revision `d66841adb0b820047ed079f0bc7d643873f23194`
(`0.2.180-SNAPSHOT`). The diagnostic reuses the already-published Protos
diagnostic runtime image construction from PERF001-E but changes no historical
PERF001 evidence.

The two targeted canonical workloads are `collections/array-reduce` and
`collections/array-sort`. Each must first produce its exact observable result in
both interpreter and optimizing-Truffle execution. A separate
`TraceCompilation=true` run then retains raw compiler output and counts
successful compilations, failed compilations, `GraphTooBig`,
`FrameWithoutBoxing`, deep-inlining, `StackOverflowError`, and
`BootstrapMethodError` findings.

The PERF003-A external closure gate is zero optimizing failures and zero known
bailout/runtime failure classes for both workloads. A remaining bailout does
not invalidate the run when observable execution is correct: the negative result
is retained as diagnostic evidence and PERF003-A remains open.

If the gate remains blocked, subsequent investigation must use structural
attribution (including the separately isolated IGV analyzer where useful) rather
than continuing threshold-driven source micro-edits without a causal hypothesis.
This diagnostic publishes no timing claim.

## PERF003-A structural Graal/IGV diagnostic

After the source-level `Array.reduce` refinements converged close to Graal's
graph-size limit, PERF003-A stops treating further incidental source deletion as
a justified optimization strategy. The structural diagnostic is a separate
non-timing run pinned to Protos
`d66841adb0b820047ed079f0bc7d643873f23194` (`0.2.180-SNAPSHOT`) and the same
GraalVM Community JDK 22 / external Truffle 24.0.0 family used by the PERF003
investigation.

`scripts/perf003a_structural.sh` first requires exact `array-reduce` correctness
(`528`), then enables Truffle/Graal compilation tracing, method/node expansion
statistics at the `peTier`, node source positions, performance warnings, and
`-Djdk.graal.Dump=Truffle:2`. The measured runtime writes BGV files; those files
are analyzed only afterwards by the isolated JDK 17 IGV analyzer. JDK 17 is
therefore diagnostic-tool implementation detail and never becomes the measured
Protos runtime.

The run retains compact attribution evidence: BGV/JSON hashes and sizes, IGV
graph identities, the compressed raw structural trace, expansion rankings, and
occurrence counts for the current architectural suspects
(`ProtosParameterBindingNode`, `OptimizedCallTarget`, closure execution/invocation,
activation, call-target and invocation machinery). Occurrence or expansion size
is evidence for selecting a controlled experiment, not proof of causality.

Full BGV and JSON outputs remain under the ignored `.work/` run directory for
local reanalysis. Compressed BGV files are also included in published evidence
when their aggregate compressed size is at most 80 MiB; otherwise the published
manifest retains their exact hashes/sizes and reports the bounded-retention
decision.

If BGV capture has already completed but IGV export is interrupted,
`make perf003a-structural-resume WORK=<existing-run-dir>` resumes from those
existing BGV files without rebuilding or executing Protos and without capturing
new BGVs. Each source BGV receives an isolated `igv_json/<key>/` export directory
and an atomic completion marker, so an interrupted item can be retried without
invalidating completed items. A conservative per-BGV free-space guard stops the
resume before export when estimated JSON growth plus the configured reserve
would exhaust the filesystem. `--status` reports completion and storage state
without starting Docker. Compact attribution/final evidence remains a later
summary/publication phase rather than part of the resume path.

When full JSON materialization is not practical because the captured BGV set is
larger than available storage, `make perf003a-structural-compact
WORK=<existing-run-dir>` uses the same pinned IGV parser but retains only compact
per-BGV NDJSON evidence. For each accepted graph it records dump identity,
graph type/name and node/edge counts; it also records source BGV size/SHA-256 and
case-sensitive occurrence counts for the configured suspect terms across graph
identity, node properties/source stacks and edge metadata. This compact mode
does not materialize the full IGV JSON representation. Its occurrence metric is
therefore explicitly labelled IGV-object attribution rather than historical
IGV-JSON textual occurrence. Completed BGV summaries are independently marked
and resumable.

The completed PERF003-A compact structural evidence is published under `results/perf003-a/`. The published corpus is derived from all 316 preserved BGV captures through the compact summaries; raw BGV files remain local and are represented by their extractor-time SHA-256 manifest rather than being rehash-compressed during finalization. Full IGV JSON is not materialized.

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


## PERF001-D measurement methodology

PERF001-D establishes Protos-only startup, warmup-curve and steady-state
measurements after the PERF001-C correctness gate. It also records separate
non-timing Truffle compilation diagnostics.

The measurement intentionally pins the two revisions immediately around the
material PERF002 optimization:

- pre-PERF002: `8f363d0146164f99e72210eb44667f4efb7b88e7`, the exact publication
  baseline consumed by PERF002-A;
- post-PERF002: `3c93912a5579326374782a43527fbb51046f8f91`, the exact published
  PERF002-A implementation.

Using these adjacent optimization revisions isolates the PERF002 implementation
delta from later independent Standard Library/project changes. The historical
PERF001-C pin remains unchanged and continues to identify its cross-language
correctness evidence.

Both revisions use the same GraalVM Community JDK 22 / external
`truffle-runtime:24.0.0` environment, the same host, the same pinned CPU, and
`-Xss128m`. Networking is disabled for runtime measurements.

### Startup boundary

Each startup sample is a fresh child JVM launched by a driver that is already
running inside the prepared container. The sample begins immediately before
`ProcessBuilder.start()` and ends after the child exits successfully. It includes
process/JVM/runtime startup, Protos Core bootstrap, source loading,
parse/lower/CallTarget creation, guest execution, final-result validation, and
normal process termination.

Docker image construction and container creation/start are outside this timing
boundary. Ten raw startup samples are retained for every
revision/mode/workload combination.

### Warmup boundary

Warmup uses one JVM and one compiled Protos CallTarget. Core bootstrap, source
read and parse/lower occur before the iteration series. Each equivalent
iteration receives a fresh module activation so program-local mutations do not
leak between executions. Only `CallTarget.call(activation)` is timed; activation
construction and result rendering/validation occur outside the timed interval.

Twenty early iterations are retained in order as the warmup curve. They are not
merged into steady-state data.

### Steady-state boundary

The same JVM and CallTarget continue after the 20 retained warmup iterations.
Twenty further guest-call intervals are retained as steady-state samples. The
primary summary statistic is the median. MAD, minimum, maximum and nearest-rank
p95 remain secondary derived views; raw nanosecond samples are authoritative.

### Interpreter and Truffle modes

Both modes use the same external Truffle runtime. Interpreter mode explicitly
sets `polyglot.engine.Compilation=false`. Truffle mode enables compilation with
background compilation disabled for deterministic measurement sequencing.

Compilation tracing is deliberately absent from every timing run.

### Non-timing diagnostics

Each revision/workload also receives a separate Truffle run with
`TraceCompilation=true`. These diagnostic runs are never used as timing samples.
They retain raw stdout/stderr and counts for optimization successes/failures plus
the previously investigated `GraphTooBig`, `FrameWithoutBoxing`, deep-inlining,
`StackOverflowError`, and `BootstrapMethodError` classes.

The post-PERF002 diagnostic run must retain the compiler-health boundary already
established by PERF002: zero optimization failures and zero known bailout/runtime
failure guards. Pre-PERF002 diagnostics are evidence and may legitimately record
the failures that motivated PERF002.

### Interpretation

PERF001-D publishes per-workload, per-mode measurements and pre/post ratios.
Those ratios quantify observations for the exact pinned revisions only. They are
not evidence for a blanket claim about whole-language performance and do not
replace later PERF001 cross-language or broader-workload slices.


## PERF001-E sequential collections

PERF001-E extends the algorithm-equivalent suite with the six canonical
collection workloads published by Protos revision
`86b35d8bb2d7ab2ad54bc2947e1bf7fbff1fca15`:

- `collections/array-map`;
- `collections/array-filter`;
- `collections/array-reduce`;
- `collections/array-sort`;
- `collections/map-lookup-update`;
- `collections/set-algebra`.

The Python and JavaScript implementations preserve the canonical explicit work
shape. In particular, Array sort uses an explicit stable merge sort in both
comparison languages rather than a host built-in sort, and Set algebra uses
ordered map-backed `key -> true` representations with explicit union,
intersection and difference loops rather than host bulk Set operations.

Correctness is a strict 18-case pre-timing gate: six workloads in Protos,
Python and JavaScript. Any mismatched final value invalidates the run.

Reference measurement uses the same host and one pinned CPU for all three
languages, with runtime networking disabled. Each language/workload records:

- 10 fresh-process startup samples measured by a driver already running inside
  the prepared container, so Docker start is outside the timing boundary;
- 20 retained same-process warmup iterations;
- 20 retained steady-state iterations after warmup.

Protos uses the exact pinned corpus revision above with GraalVM Community JDK
22, external `truffle-runtime:24.0.0`, optimizing Truffle with background
compilation disabled, and `-Xss128m`. Python is pinned to 3.14.7 and JavaScript
to Node.js 24.20.0 with its recorded stack configuration.

Truffle compilation tracing is absent from timing. Six separate non-timing
diagnostic runs retain optimizer events and reject optimization failures,
`GraphTooBig`, `FrameWithoutBoxing`, deep-inlining failures,
`StackOverflowError`, or `BootstrapMethodError`.

The retained evidence records the exact Protos revision, exact harness revision,
runtime image identities, host environment, raw samples and derived
median/MAD/min/max/p95 statistics. Per-workload language ratios are observations
for those exact revisions only and are not whole-language performance claims.
Canonical PERF001-E closure remains owned by the Protos status ledger.
