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

IdealGraphVisualizer (BGV) analysis is deliberately isolated from benchmark
runtime images. The current/default analyzer is the official headless
`GRAAL_IGVUTIL` utility (`org.graalvm.igvutil.IgvUtility`) from GraalVM
25.4.4.1.1: `docker/igv-analyzer/Dockerfile` pins oracle/graal `vm-25.4.4.1.1`
commit `95ce1499c8c96ab7d5a6697c5b4bf42160f3b68b`, mx `7.83.0` commit
`22381992c7322f661498cd6101144f0f49c72ae1`, and the builder image by tag and
digest. Only the collected runtime jars are shipped on a neutral Java 21 JRE.

The analyzer is consumed as a prebuilt, versioned image:

```text
ghcr.io/guillermomolina/protos-benchmarks/igv-analyzer:graal-25.4.4.1.1
```

Its operations are deliberately separated:

- **Build/publish (rare, maintainer):** `.github/workflows/igv-analyzer-image.yml`
  builds and pushes the image on `workflow_dispatch` or when the analyzer
  Dockerfile/workflow changes on `main`. `scripts/igv_analyzer.sh build` is the
  equivalent local maintainer command. Only this step clones Graal/mx and runs
  `mx build`. The build fails unless the shipped jars, on the shipped runtime,
  `list` and `filter` (valid JSON) the upstream `bigv-3.0.bgv` fixture from the
  exact pinned Graal checkout; the fixture is not shipped.
- **Pull (one-time setup):** `scripts/igv_analyzer.sh pull`. This is the only
  wrapper command that contacts a registry.
- **Analyze (normal, cheap, offline):** `inspect`, `list`, `filter`, `flatten`
  and `smoke` only run the already-present image with `--network none`. They
  never build, clone, run mx or pull; a missing image fails with the pull
  command.

`inspect` is the cheap acceptance/triage surface for an existing BGV:

```sh
./scripts/igv_analyzer.sh inspect results/example.bgv protos-root:0123456789abcdef
```

It requires a non-empty file, runs only `IgvUtility list` (no JSON export),
and reports `BGV_READABLE`, `SELECTED_ROOT_PRESENT` (`NOT_REQUESTED` without a
selector) and `AFTER_TRUFFLE_TIER_PRESENT`, exiting nonzero unless all
requested checks pass. The optional `protos-root:<16 lowercase hex>` selector is
an opaque string located in the listing; the analyzer does not depend on a
Protos checkout. `inspect` performs no causal graph interpretation.

The low-level `list`, `filter` and `flatten` commands pass their arguments to
`IgvUtility` with the current working directory mounted at `/work`, so input
and explicitly requested output paths remain host artifacts.
`PROTOS_IGV_ANALYZER_IMAGE` overrides the image reference.

Historical Graal 24.0.0 PERF003 tooling remains isolated and unchanged under
`docker/igv-analyzer24/` and `scripts/igv_analyzer24.sh`.

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

## PERF003-A4a controlled closure-invocation boundary experiment

The published PERF003-A structural evidence leaves the residual
`collections/array-reduce` bailout only 26 graph-size units above Graal's
150000 limit and attributes substantial graph presence to closure/invocation
runtime machinery. Presence is not causality, so the next step is a controlled
falsification experiment rather than another Standard Library source micro-edit.

The A4a harness builds two images from the exact same Protos
`d66841adb0b820047ed079f0bc7d643873f23194` source revision. The control image is
unchanged. The experimental image applies `@TruffleBoundary` only to the private
host helper `ProtosClosureInvoker.invokePrepared` inside the diagnostic image
before building Protos. Both variants must preserve exact `array-reduce` result
`528` under the same GraalVM/Truffle 24.0.0 runtime, `-Xss128m`, CPU affinity and
TraceCompilation policy.

This boundary is diagnostic only. A result that removes or reduces
`GraphTooBig` supports the hypothesis that expansion through this helper owns a
material part of the graph, but does not establish that the boundary is an
acceptable production optimization. A no-change result falsifies this broad
ownership hypothesis and is retained as useful evidence. No timing claim is
made.

The retained A4a comparison is published under `results/perf003-a4a/`. It contains both raw TraceCompilation stderr streams, correctness outputs, runtime-class checks, exact Docker image metadata, the machine-readable comparison summary, and the harness-produced hypothesis conclusion.

## PERF003-A4b closure invoke-entry boundary experiment

PERF003-A4a showed that a diagnostic-only boundary at
`ProtosClosureInvoker.invokePrepared` reduces the deterministic failing
`array-reduce` graph from 150026 to 150001 while preserving exact result `528`.
That leaves one graph-size unit above the 150000 limit.

A4b tests the immediately wider host boundary:
`ProtosClosureInvoker.invoke(ProtosClosureValue,List,ProtosActivation)`. This is
the ordinary Closure receiver path used by standard `Object.call`; it includes
closure activation preparation before entering `invokePrepared`.

The prediction is intentionally narrow: if the remaining graph-size unit is
owned by this activation/preparation prefix, the wider diagnostic boundary
should take the failing graph below 150000 and eliminate `GraphTooBig`. The
boundary remains falsification instrumentation only and is not a production
optimization proposal. No timing claim is made.

The retained A4b comparison is published under `results/perf003-a4b/`. It contains the raw control/boundary TraceCompilation streams, exact correctness outputs, runtime-class checks, Docker image metadata, the machine-readable comparison summary, and the harness-produced hypothesis conclusion.

## PERF003-A4c immediate-method boundary experiment

PERF003-A4a established a deterministic control failure at graph size 150026
and showed that a diagnostic-only boundary at
`ProtosClosureInvoker.invokePrepared` reduces that failing graph to 150001 while
preserving exact result `528`. A4b then falsified the generic three-argument
closure entry: its graph remained identical to control.

Canonical method dispatch instead reaches
`ProtosClosureInvoker.invokeImmediateMethod` through `ProtosInvocation`.
A4c therefore tests that immediate-method path under the exact same pinned
Protos revision, workload, runtime, stack, CPU-affinity and TraceCompilation
policy.

The prediction is narrow: if immediate-method activation/preparation is the
causal prefix feeding the `invokePrepared` expansion seen in A4a, the diagnostic
boundary should materially reduce the failing graph and may eliminate
`GraphTooBig`. This remains controlled falsification instrumentation, not a
proposed production boundary or a timing claim.

The retained A4c comparison is published under `results/perf003-a4c/`. It contains raw control and boundary TraceCompilation streams, exact correctness outputs, runtime/Docker identity, and an independently recomputed comparison summary. Publication recovery reused the successful retained run and did not rerun the experiment.

## PERF003-A4d immediate-activation boundary experiment

PERF003-A4c established that a diagnostic-only boundary at
`ProtosClosureInvoker.invokeImmediateMethod` eliminates all 40 deterministic
`GraphTooBig` bailouts while preserving `collections/array-reduce => 528`.
A4d narrows that supported result to activation construction alone.

The experimental variant places a diagnostic-only `TruffleBoundary` on
`ProtosActivation.forImmediateMethodInvocation`. Everything else remains pinned:
the exact Protos revision, Graal/Truffle runtime, stack, CPU-affinity policy,
workload, correctness result, and 20-iteration TraceCompilation policy.

If this narrower boundary materially reduces or eliminates the bailout, activation
construction is a causal graph-growth owner. If it does not, the remaining
A4c-specific contribution lies elsewhere in immediate-method preparation. This
is falsification instrumentation only; it is not a production boundary or timing
claim.

The retained A4d comparison is published under `results/perf003-a4d/`. It contains the raw control/boundary TraceCompilation streams, exact correctness outputs, runtime-class checks, Docker image metadata, the machine-readable comparison summary, and the harness-produced hypothesis conclusion.

## PERF003-A4e residual dynamic-control boundary experiment

A4a reduced the deterministic failing graph from `150026` to `150001` by placing a diagnostic-only boundary at `ProtosClosureInvoker.invokePrepared`. A4c showed that the wider `invokeImmediateMethod` boundary eliminates all 40 bailouts, while A4d showed that isolating activation construction alone does not explain the residual threshold contribution.

A4e therefore preserves the A4a `invokePrepared` boundary and adds exactly one second diagnostic boundary at `ProtosActivation.inheritDynamicControlState`. This directly tests whether dynamic-control inheritance owns the single graph-size unit left after A4a.

The experiment keeps the exact Protos revision, workload, runtime, stack, CPU-affinity policy and correctness result fixed. These boundaries are falsification instrumentation only, not production proposals or timing claims.

The A4e conclusion is evaluated against the retained A4a reference: `40` bailouts at `48153:150001:150000`, not merely against the original control. An unchanged A4a residual is `NOT_SUPPORTED`; elimination or a directional reduction relative to A4a is `SUPPORTED`.

The retained A4e comparison is published under `results/perf003-a4e/`. It contains raw control and boundary TraceCompilation streams, exact correctness outputs, runtime-class checks, Docker image metadata, the retained A4a reference, and an independently recomputed residual conclusion.

## PERF003-A4f residual replay-activation boundary experiment

A4a left a deterministic residual at `48153:150001:150000` after isolating `ProtosClosureInvoker.invokePrepared`. A4d showed that activation construction alone does not explain that residual, and A4e showed that additionally bounding `ProtosActivation.inheritDynamicControlState` changes the graph non-directionally to `50290:150037:150000`.

A4f retains the supported `invokePrepared` boundary and adds only a boundary at `ProtosEvaluatorContinuation.invocationActivation`. This isolates replay-stable task activation management, including the Supplier-consuming continuation path, from the residual A4a graph.

The exact Protos revision, workload, result, runtime, stack, affinity and 20-iteration TraceCompilation policy remain fixed. A4f is controlled falsification instrumentation only; it is not a production boundary or timing claim.


## PERF003-A4g immediate-method preparation-unit transform

A4g stops isolating existing helper methods one by one. Its diagnostic transform
extracts the existing `invokeImmediateMethod` activation-preparation prefix into
`prepareImmediateMethodActivation(...)` without changing statement order or
observable behavior. The five public-entry `Objects.requireNonNull` checks remain
at `invokeImmediateMethod`.

A4g1 validates and publishes only this source transform plus its exact fixture.
It does not build the Docker experiment and does not execute TraceCompilation.

A4g2 adds the Docker/Truffle smoke harness for this transform. It verifies both diagnostic boundaries inside the built image, requires an optimizing `HotSpotTruffleRuntime`, and checks `collections/array-reduce => 528`. TraceCompilation remains deferred to A4g3.

The retained A4g comparison is published under `results/perf003-a4g/`. The exact A4a residual reference is `48153:150001:150000` with `GraphTooBig=40`; the control reproduced `50681:150026:150000` with `GraphTooBig=40`, and the preparation-unit variant produced `NONE` with `GraphTooBig=0`. The independently cross-checked conclusion is `SUPPORTED`: immediate-preparation boundary eliminated the A4a residual GraphTooBig. This remains non-timing causal evidence and does not by itself authorize a production boundary or semantic/runtime change.

## PERF003-A4h production-shaped sync/task split transform

A4g eliminated all 40 deterministic GraphTooBig bailouts when the complete immediate-method preparation unit and invokePrepared were bounded. A4h tests a production-shaped alternative before any canonical Protos change: direct synchronous activation preparation is physically separated from task/replay preparation. The direct helper has no Supplier, evaluator-continuation, task attachment, or task-state branch. Neither preparation helper is bounded; only the already-characterized invokePrepared diagnostic boundary is retained. A4h1 publishes only this exact transform and fixture.

A4h2 adds the Docker/Truffle smoke harness for this production-shaped transform. The built image retains exactly one diagnostic boundary at `invokePrepared`, preserves a direct helper with no task/replay machinery, runs on `HotSpotTruffleRuntime`, and returns exact result `528`. TraceCompilation remains deferred to A4h3.

A4h3 executes the retained 20-iteration controlled diagnostic from exact harness revision `041a6b821387494e6299c93334d72ecd8b3ce494`. Control reproduces `GraphTooBig=40` with shape `50681:150026:150000`. The production-shaped sync/task split variant records `GraphTooBig=40` with shape `48823:150002:150000` while preserving result `528`. Hypothesis: **INCONCLUSIVE** — sync/task split changed the A4a residual diagnostics without a directional result. This remains non-timing diagnostic evidence and does not itself publish a canonical Protos implementation change or a production Truffle boundary.

## PERF003-A4i preparation-boundary decision

A4i is the final narrow partial-evaluation localization experiment after A4g and A4h. It bounds only immediate-method activation preparation and leaves `invokePrepared` fully optimizable. The exact control reproduced GraphTooBig=40 (50681:150026:150000); the preparation-boundary-only variant produced GraphTooBig=40 (51502:150053:150000). Separate no-trace steady-state medians were 9950715696 ns control and 5752923868 ns boundary (ratio 0.5781). Decision: **NOT_SUFFICIENT** — preparation boundary alone did not eliminate all deterministic GraphTooBig bailouts. Next: close this boundary-localization line; no further PE microexperiments. No canonical Protos repository change is made by this evidence slice.

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


## PERF001-F companion harness foundation

The first companion-harness phase for `PERF001-F` consumes the exact canonical
concurrency corpus published by Protos revision
`faa1714523d68650447047a05d184ab17a747c06`. It does not copy or translate that
corpus: runtime correctness executes the six files directly from the pinned
Protos checkout.

`config/perf001f.json` records the six approved workload identifiers, exact
observable results, fixed-cost versus strong-scaling classification, the
`1/2/4/8` candidate physical-core widths and the established `10/20/20`
startup/warmup/steady sample policy. This phase does not publish timing evidence.

Unlike historical PERF001-C/D/E runtime definitions, the PERF001-F runner does
not carry a forward-copied GraalVM/Truffle pin. It fetches the exact measured
Protos revision, reads that revision's repository-owned `toolchain.json`, rejects
a floating primary runtime, runs Maven at the declared version inside the exact declared GraalVM container
image, and uses that same primary-runtime image as the final runtime stage. Historical JDK 22 / Truffle 24 evidence remains
unchanged and authoritative only for its own pinned revisions.

The PERF001-F image is built through the measured revision's own
`dist/build_portable.py` contract and validates that portable archive with the
repository-owned optimizing-runtime smoke before copying the distribution into
the benchmark image. The final `/opt/protos/bin/protos` therefore runs in the
supported distribution mode with `lib/protos.jar`, `RUNTIME.txt`, and the exact
`lib/runtime/*` closure, including `HotSpotTruffleRuntime`. It does not preserve
the historical direct `ProtosSourceCompiler` measurement entry. The concurrency
corpus uses iterative `while` work rather than the deep recursive PERF001-C
workload family, so this harness also does not inherit the historical `-Xss128m`
recursion accommodation as an unrelated concurrency-runtime setting.

CPU topology is audited on the Linux host through the current process affinity
and `/sys/devices/system/cpu/*/topology`. The primary series chooses at most one
logical CPU representative for each distinct `(physical package, core)` pair and
materializes only available widths from `1, 2, 4, 8`. SMT siblings are retained
in the topology record but are not silently substituted for additional physical
cores.

Before any later timing is accepted, `perf001f-prepare` builds the toolchain-
aligned portable Protos image, probes the final image for the exact
`HotSpotTruffleRuntime`, and runs every fixed-cost workload at one physical core
and every strong-scaling workload at each available approved physical-core
width, with Docker networking disabled. Standalone file execution intentionally
does not render its final expression, so the correctness gate creates an
ephemeral observation copy of each exact canonical source in which only the
terminal `run()` becomes `print(run())`. Canonical and observation SHA-256 values
are retained. These wrappers are correctness-only and are never the later timing
source. Every configuration must produce its exact canonical result. The
resulting `.work/perf001f/correctness.json` is local correctness/topology
evidence, not reference timing evidence.

A later PERF001-F harness phase owns persistent production-hosted warmup and
steady-state timing, raw-sample retention and statistical finalization. The final
retained reference run remains gated by the Protos-side
`I026-A4B3_RELEVANT_PRODUCTION_ENTRY_RETIREMENT` condition recorded by the
canonical PERF001-F methodology.


## PERF001-F persistent production-hosted driver

PERF001-F H2 advances the measured Protos pin from the corpus-publication revision
`faa1714523d68650447047a05d184ab17a747c06` to
`a08844c7ba59f4a213e4d318bcf3bee32393c2a9`, the first exact revision that also
closes the approved `I026-A4B3_RELEVANT_PRODUCTION_ENTRY_RETIREMENT` gate. This
minimizes unrelated post-gate drift while retaining the exact canonical six-workload
concurrency corpus.

Warmup and steady-state measurement no longer launch a fresh CLI process or parse
the benchmark for every iteration. The external `Perf001fPersistentDriver` builds
Core, one semantic Process and one Process-scoped Polyglot Context, then derives an
untimed setup projection by changing only the canonical source's terminal `run()` to
`run`. Executing that projection as a real RootActor task creates the ordinary
`run` Closure and performs benchmark bootstrap, including Actor spawn/readiness,
without consuming an unretained benchmark invocation before warmup[0].

The driver then reads that exact `run` Closure once. Every retained iteration creates
a fresh RootActor-local task and invokes the retained Closure through
`ProtosClosureInvoker.invokeInTask` while dispatching inside the same production
Process Context. The timed interval begins before task creation and ends after
semantic task completion. It therefore includes task creation/scheduling/dispatch,
the guest workload and completion, but excludes Core/Process/Context bootstrap,
source parsing, initial Actor setup and result serialization.

H2 publication runs only a two-warmup/two-steady smoke for every eligible
workload/physical-core configuration. Those local samples validate the driver and
are explicitly not reference timing evidence. The later reference-evidence slice
must execute the approved 20 warmup + 20 steady policy from the exact published H2
harness revision and retain raw samples plus exact Protos/harness/runtime/host
identity.

## PERF001-F H3 reference-evidence runner

H3 keeps the six-workload corpus publication at `faa1714523d68650447047a05d184ab17a747c06` and repins the
measured runtime from the original post-I026 revision `a08844c7ba59f4a213e4d318bcf3bee32393c2a9` to
`0372a58addc63f305c911811659edd9b2b508420`. The latter is the published PLAT010/PLAT011 carrier cutover
that closed PERF001-F blocker #239. The original
`reference_gate_satisfied_by=a08844c7ba59f4a213e4d318bcf3bee32393c2a9` value remains the provenance of the
I026 production-entry gate rather than being rewritten to a later revision.

Fresh startup and persistent warmup/steady measurements share the same
production-hosted `Perf001fPersistentDriver`. The fresh-startup controller runs
inside an already-started Docker container and launches one fresh JVM per startup
sample with `warmup=0` and `steady=1`. The outer startup interval includes fresh
JVM launch, Core/Process/Polyglot-Context bootstrap, canonical-source setup, one
real RootActor-local invocation, semantic completion and child serialization.
Docker container creation/start and parent-side result parsing remain outside
that interval.

Each fresh child is bounded to 120 seconds. Child stdout/stderr are redirected
to temporary regular files rather than pipes; timeout destroys the child,
escalating to `destroyForcibly()` when necessary. The Python reference
controller also bounds each Docker startup or persistent case to 600 seconds and
removes the named container on timeout or interruption. Progress is emitted per
reference case and per startup sample.

H3 publication validates the complete runner with a `2 startup / 2 warmup /
2 steady` non-retained smoke. The smoke deliberately executes Actor fan-out
width 8 first because that configuration exposed #239. These samples validate
the harness only and MUST NOT be published as PERF001-F reference timings.

H4 is the retained evidence execution. It must run from the exact clean,
published H3 harness SHA, use the configured `10/20/20` policy, and retain
`evidence.json`, `run-metadata.json`, `summary.tsv`, `summary.md` and
`MANIFEST.sha256`. Raw ordered samples are authoritative. Median, MAD,
nearest-rank p95, min and max are derived for startup, warmup and steady classes;
steady-state speedup and efficiency are derived only for
`parallel-array-map` and `actor-fanout-requests`.

## PERF001-G final reproducibility and baseline reporting

PERF001-G uses the project-owner-approved **bounded exact-pin reproducibility replay**. The retained PERF001-D, PERF001-E and PERF001-F timing corpora remain the sole timing authority; G does not rerun them as replacement baselines and does not define a timing-drift pass/fail threshold.

The final replay reconstructs the exact historical PERF001-D harness `0a406373c497df1173ff26a3ed4fcada015e0879` and executes its complete 44-case correctness matrix across both pre/post PERF002 revisions and interpreter/Truffle modes. It separately reconstructs exact PERF001-E harness `280173d743b2ed838a89be0ad930b20828d89558` and executes its complete 18-case Protos/Python/JavaScript correctness matrix. PERF001-F is replayed through exact H3 harness `b8a9eeca85c241f544512a02a6fa29d935f240ef` using its already-published non-retained `2 startup / 2 warmup / 2 steady` smoke path across the 12 approved configurations.

Before replay, G verifies that the retained `results/perf001-d`, `results/perf001-e` and `results/perf001-f` subtrees are byte-identical to their state at companion evidence commit `f34e37da11f209aa9f9ea84465822c3362fc4da0`. The replay records current host/runtime/container identities and PASS counts but retains no replacement timing samples.

The final baseline report presents the existing D/E/F summaries as separate benchmark generations. It does not normalize, rank, or infer a whole-language comparison across incompatible historical revisions or environments. G1 publishes only this harness and its static/integrity validation. The real replay and retained `results/perf001-g/` publication occur only from the exact published G1 harness revision in G2.

## PERF006-D current-runtime optimizer/fallback evidence

`PERF006-D` is a current-generation runtime-integrity measurement track owned by
`guillermomolina/protos#487`. It does not replace or rewrite PERF001/PERF003
evidence.

### D1 — current runtime contract

D1 pins Protos `4a03efc15620b37b2e418b3df30b4a26486446ec`
(`0.2.492-SNAPSHOT`) and its exact canonical toolchain:

```text
GraalVM Community 25.3.4.1
JDK 25.0.4.1
Graal/Truffle 25.3.4.1
Maven 3.9.9
container ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol8-20260825
```

The executable content had already passed PERF006-C3 full validation at
`428e46523e8fa0b3f0260b5a6e76c198725c041b`; the pinned D1 source additionally
contains the documentation-only C4 closure evidence.

D1 defines two diagnostic variants from the **same** portable bundle:

- optimizer: the complete canonical `lib/runtime` projection;
- fallback: a byte-identical projection for every retained jar except the
  `truffle-runtime` and `truffle-compiler` jars, which are deliberately omitted.

The fallback control changes no Protos source and does not suppress
`WarnInterpreterOnly`. Its expected runtime is
`com.oracle.truffle.api.impl.DefaultTruffleRuntime`; the optimizer must be
`com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`.

D1 correctness-gates five canonical guest-heavy workloads under both variants:
closure call, method call, monomorphic dispatch, polymorphic dispatch and
recursive Fibonacci. This is 10 correctness cases plus exact runtime identity.
D1 publishes **no timing claim**.

D2 owns reference timing. Startup, warmup and steady-state remain separate
measurement classes; heavy compiler/IGV diagnostics remain outside reference
timing. The informal historical observation that a later full Maven suite took
roughly 8 minutes rather than roughly 20 minutes is not a controlled
optimizer-vs-fallback result and must not be promoted into one.

## PERF006-D2 timing harness publication

D2 uses a two-publication retained-evidence pattern.

`PERF006-D2A` publishes the timing runner and proves it with a non-retained
1-startup / 1-fork / 2-warmup / 2-steady smoke over `micro/closure-call` in both
runtime variants. D2A publishes no performance claim.

`PERF006-D2B` must execute the retained reference run from the exact published
D2A harness SHA. It uses the D1 contract unchanged: 10 fresh-JVM startup samples
per variant/workload, five independent persistent JVM forks, 20 warmup
iterations per fork and 20 steady-state samples per fork.

The persistent driver reads the canonical source once, retains one
RuntimeHost/Process/Polyglot Context per fork, and creates a fresh module
Activation for each execution. Source text is not projected or rewritten.
Startup samples are timed by a controller inside an already-running Docker
container, so Docker creation/start is outside the timing interval.

Reference timing contains no TraceCompilation, IGV dump or other heavyweight
compiler diagnostics. Those belong to D3.

## PERF006-D2 retained controlled timing evidence

The retained D2 optimizer/fallback corpus was measured from exact published
harness `1a752e92569b4ed42d3f9f55f67d1a7447eae308`. The harness and measurement contract were not changed by
the evidence publication.

The retained policy is 10 fresh-JVM startup samples per runtime/workload plus
five persistent JVM forks per runtime/workload, with 20 warmup and 20
steady-state iterations per fork. Raw ordered samples, runtime/host/image
identity, deterministic summaries and the five fallback/optimizer ratios are
published under `results/perf006-d2/`.

Heavy compiler/JFR/IGV diagnostics are intentionally excluded from these timing
runs and belong to PERF006-D3. Historical pre-C′ replay evidence is
interpretation-only and is not used as an absolute performance comparison.

## PERF006-D3 current structural diagnostics

D3 is diagnostic-only and is deliberately separate from retained D2 timing.

D3A publishes the exact JFR/TraceCompilation harness. Its smoke output is not
retained as a performance or diagnostic conclusion. D3B must run from the exact
published D3A SHA.

The current real-workload profile is `bin/protos test --jobs 2` on exact Protos
`4a03efc15620b37b2e418b3df30b4a26486446ec` with the optimizing runtime. JFR uses the JDK 25 `profile` settings,
10 ms `jdk.ExecutionSample`, explicit `jdk.Deoptimization`, and requests the
Graal/Truffle deoptimization event by its historical name when available.

The recovered pre-C′ evidence is structural historical context only:

```text
wall                         ~471.985 s
ExecutionSample              44,568
HashMap$KeyIterator.next     41,092 / 92.201%
thread main                  43,913 / 98.530%
jdk.Deoptimization           1,824,883
Truffle Deoptimization       1,824,544
```

Its known source hotspot was
`ProtosEvaluatorContinuation.compactCompletedChildExecution()` repeatedly
scanning `invocationActivations.keySet().removeIf(...)`. D3 must not reintroduce
or optimize that retired replay path. It records whether the exact historical
symbol remains hot, current thread concentration, current deoptimization
behavior, a static audit for the old path, and any new dominant hotspot.

Current-toolchain TraceCompilation is run separately on
`micro/method-call.protos`. The historical Graal-24/JDK-17 IGV analyzer is not
used by D3A/D3B unless separately re-ratified for current 25.3.4.1 output.

## PERF006-D3 retained current structural diagnostics

The retained D3 structural profile was produced from exact published D3A
harness `297ccb4fc94a0f0b0c9e0a65422aba2e223c4a83`. No production optimization or reference-timing change was
made.

Current diagnostic headline:

```text
main_thread_percent=39.411481
top_frame=com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt
top_frame_percent=32.995658
HashMap$KeyIterator.next_percent=0.000000
jdk_deoptimizations=191
truffle_deoptimizations=6
compactCompletedChildExecution_present=FALSE
invocationActivations.keySet().removeIf_present=FALSE
trace_successful_compilations=12
trace_failed_markers=6
trace_bailout_markers=15
```

These values are compared structurally with the recovered historical pre-C′
profile, not as an absolute wall-time speedup claim. D4 owns final causal
interpretation and any decision to create a separate PERF item for a new
dominant hotspot.

The D3B publication launcher normalized trailing horizontal whitespace in
`jfr-summary.txt` and `test-tool-output-tail.txt` after the completed diagnostic
run. `result.json`, `current-profile.json`, and `trace-compilation.log` retain
their exact measured SHA-256 identities; no diagnostic was rerun.

## IGV analyzer generations

The unsuffixed analyzer path always denotes the current supported diagnostic
generation. New PERF work MUST use `docker/igv-analyzer/`,
`scripts/igv_analyzer.sh`, and the generic `igv-analyzer-*` Makefile targets
unless a retained historical harness explicitly pins another generation.

The current default is Graal `25.3.4.1`. Its builder pins Graal commit
`7b025988a922a73286d1326e1eddc1ca39d3f569` and mx commit
`22381992c7322f661498cd6101144f0f49c72ae1`, builds upstream
`GRAAL_IGVUTIL`, and copies only its runtime classpath into a neutral JRE 21
image. The neutral runtime avoids the module/classpath collision with the
`jdk.graal.compiler` module embedded in GraalVM 25 while preserving the exact
Graal 25.3.4.1 BGV parser and graph model.

The default analyzer exposes upstream `igvutil` operations `list`, `filter`,
and `flatten`.

```text
make igv-analyzer-build
make igv-analyzer-smoke
make igv-analyzer-smoke BGV=/path/to/sample.bgv
```

Graal `24.0.0` tooling is historical-only and lives under the explicit
`docker/igv-analyzer24/` and `scripts/igv_analyzer24.sh` names. It exists only
for retained PERF003 replay paths that require the old `analyze`/`summarize`
contract. Generic analyzer targets and new PERF harnesses do not build or
depend on it. The exact benchmark-harness revision recorded with historical
evidence remains the authoritative reproduction identity.

Repository tooling and retained evidence MUST remain independent of developer
checkout locations. Local clone/worktree paths are execution details and are
not part of analyzer contracts or evidence identity.

## PERF010-A causal semantic/helper-dispatch ablation

`PERF010-A` (`guillermomolina/protos#691`, child of `#680`) is a diagnostic
ablation experiment, not a production optimization. `docker/protos-perf010a/`
builds two images — `baseline` (unmodified Protos) and `ablation`
(`docker/protos-perf010a/ablation.patch` applied at build time only, never
published to `guillermomolina/protos`) — from the exact same pinned revision,
and reuses the PERF004-B2-D/PERF008 four-workload canonical/control matrix
unchanged (`micro/slot-read`, `micro/closure-call`, `micro/method-call`,
`runtime/monomorphic-dispatch`; N=10,000; warmup=20; steady=100).

The ablation patch bypasses `ProtosSemanticBytecodeRootNode.wrap(...)` at both
of its call sites in the pinned revision — `ProtosSourceCompiler.compileBytecode`
(the top-level module root) and `ProtosBytecodeClosureExecutionPlan`'s
constructor (the closure/method activation root, which is what all four
workloads' hot loop actually calls repeatedly) — and widens
`ProtosRootTaskExecution.isProductionBytecodeRoot` to accept the resulting bare
helper root. `ProtosBytecodeRootNode` and `CanonicalToBytecodeLowerer` are
untouched. See `runner/perf010a.py` and `results/perf010a-*/README.md` for the
full experimental design, structural-ablation verification, and timing
methodology (separate JFR-free timing runs vs. steady-state-only JFR structural
runs, per the diagnostic-instrumentation/timing separation rule in
`AGENTS.work/REPRODUCIBILITY.md`).

### Maven install method

`docker/protos-perf010a/Dockerfile` installs Maven with `microdnf install
maven` from the base image's own OS package repository (Oracle Linux 10
AppStream), rather than downloading an `archive.apache.org` tarball as the
older `docker/protos-perf006d*` Dockerfiles do. Investigation in the `protos`
devcontainer established that this base image's packaged Maven
(`maven-3.9.9-3.el10_1`) is a compatible, usable `3.9.9` build that already
runs under the image's own `JAVA_HOME` (GraalVM), matching the version pinned
by `toolchain.json`/`EXPECTED_MAVEN_VERSION` exactly; the Dockerfile still
asserts `mvn -version` against `EXPECTED_MAVEN_VERSION` at build time so a
future OS-image bump that changes the packaged Maven version is caught rather
than silently drifting. This applies to the PERF010-A image only; other
retained-evidence Dockerfiles keep their existing pinned-tarball install
mechanism unless a later PERF item explicitly re-audits and migrates them.

## PERF016 post-Step-3 controlled timing comparator

`PERF016` (`guillermomolina/protos#727`, child of `PERF010-B` /
`guillermomolina/protos#722`) owns the controlled timing checkpoint that follows
two product changes: PERF015 (guarded represented selection for canonical
`true`/`false` on the existing Boolean control behaviors) and the PERF016
semantic Integer-family guarded represented selection (the common driver sends
`count > 0` and `count - 1`). Both are already structurally validated in the
product repository and are not under test here. This comparator measures their
**combined** effect on the retained common benchmark driver and on the four
common canonical workloads.

### Endpoints and toolchain

```text
CONTROL       2e3f56fae3a500d3e4193e3345d8a82c35e4590e  0.3.117-SNAPSHOT  pre-PERF015
INTERVENTION  696b0f9797ebc8ced80009fb583027513852f55c  0.3.119-SNAPSHOT  post-PERF016
```

Both endpoints are ordinary unpatched `baseline` products on the canonical
post-adoption 25.4 toolchain: GraalVM/Graal/Truffle `25.4.4.1.1`, JDK
`25.0.4.1.1`, JVMCI `25.4-b23`, runtime
`com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`, container
`ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5`.
Exactly two product commits separate them — PERF015 (`453f2b00…`) and PERF016
(`696b0f97…`) — and no unrelated product commit. That lineage is supplied input
recorded in `config/perf016-post-step3.json`; the harness cannot re-derive it.
Per built image it does verify the revision label, the `pom.xml` version, the
toolchain/runtime identity (both images must prove the same, including JVMCI)
and, for every workload, that the canonical and generated workload-control
sources are byte-identical between the two images.

The image, runtime probe and driver are the DIST006-D ones
(`docker/protos-dist006d/`, reached through `runner/dist006d_baseline.py`),
reused unchanged. PERF014 contributes measurement discipline only: its 25.3.4.1
toolchain, product revisions and retained evidence are untouched. The retained
`results/dist006d-baseline/` was measured at another revision and is **not** the
control measurement; both endpoints are built and measured in the same run.

### Design

- Workloads: `micro/slot-read`, `micro/closure-call`, `micro/method-call` and
  `runtime/monomorphic-dispatch`, each expected `42`. Each is timed as a
  canonical variant and a workload-control variant that replaces the
  workload-specific operation with `sink = 42` and keeps the common driver.
- 10,000 operations; 120 warmup and 100 steady iterations per timed unit,
  recorded separately in a fresh JVM per unit; one CPU pinned with
  `--cpuset-cpus`; `--network none`; 64 timed units. No JFR, compiler tracing,
  IGV, allocation profiling, source instrumentation or Test Tool diagnostics.
- Deterministic A,B,A,B counterbalancing: block A times CONTROL first, block B
  INTERVENTION first; within a role the canonical and workload-control variants
  are adjacent. Block identity is retained in the raw evidence.

### Retained views

Every effect is CONTROL minus INTERVENTION, so a positive value means the
INTERVENTION is faster. Each is retained per block and aggregated per workload
(median, MAD, min, max); the four workload-controls are never merged.

- `control_variant_effect` (`SHARED_DRIVER_TIMING_EFFECT`) — **primary for the
  common driver**: `control_workload_control_median_ns -
  intervention_workload_control_median_ns`, and that as a percentage of CONTROL.
  PERF015/PERF016 optimize work in the shared driver itself, so this movement is
  a measured effect, not noise to subtract away.
- `canonical_effect` (`COMMON_WORKLOAD_TIMING_EFFECTS`): the same difference for
  each canonical workload. A microbenchmark result, not a whole-language claim.
- `paired_control_effect` — **secondary discriminator**, the established PERF014
  residual: `canonical_effect - control_variant_effect`. A near-zero value is not
  evidence that Step 3 had no effect; if Step 3 improves the shared driver
  equally in both variants the subtraction removes that common improvement.

Order effects reuse the PERF014 range-separation method (DETECTED when the A-order
and B-order block ranges do not overlap) independently for each view. Every
100-sample steady unit also retains a first-quarter versus last-quarter
stationarity diagnostic. Neither is thresholded and no block is discarded.

### Correctness before timing

Before any timing, `reference` reads every workload's canonical source bytes from
both images and fails closed (`WORKLOAD_SOURCE_IDENTITY_MISMATCH`) on any
SHA-256 difference, then requires the correct result `42` for every role,
workload and variant. The driver additionally checks every warmup and steady
iteration. Reference evidence also requires the exact clean published harness
SHA, is written only once complete, and is re-verified so that every derived
number is reproducible from the retained raw samples.

### No automatic classification

The harness collects and summarizes objective measurements only.
`STEP_3_TIMING_CLASS` and `STEP3_NEXT_ROUTING` are emitted as `NOT_CLASSIFIED`,
no numeric threshold exists anywhere in the harness, and `validate` rejects any
attempt to add one. Classification is a later interpretation of the retained raw
evidence, routed through `PERF010-B` / `guillermomolina/protos#722`.

### Commands and evidence status

```sh
make perf016-post-step3-validate
make perf016-post-step3-smoke
make perf016-post-step3-reference HARNESS_REVISION=<published-harness-SHA>
```

`validate` is static (no Docker, no timing) and self-tests the fail-closed
contract, the sign conventions and the analysis with synthetic data. `smoke`
builds and probes both exact products and runs the correctness matrix plus a
tiny-scale pass of the reference code path (warmup 1, steady 2); it prints and
retains no timing. `reference` alone writes retained evidence to
`results/perf016-post-step3/`: `raw.json` (authoritative), `summary.tsv`,
`blocks.tsv`, `stationarity.tsv`, `README.md`, `SHA256SUMS` and per-unit `logs/`.

This publication is harness capability only. The retained reference run is a
separate later slice executed from the exact published harness SHA.

## PERF025 reusable-call dynamic/prepared A/B

PERF025 measures the reusable top-level call path across four exact Protos
revisions on the PERF024 primitive workloads `primitive-return-literal`,
`primitive-closure-call`, and `primitive-method-call` (catalog
`jvm_sample_calls=100`).

| Role  | Protos revision                            | Version          | Run mode |
|-------|--------------------------------------------|------------------|----------|
| PRE_A | `f3c44554ddfb9004c43dbde5197b9805990f8a4a` | 0.3.129-SNAPSHOT | dynamic  |
| A     | `d0045353d834257b5fb80581846b32aebd43c7e6` | 0.3.130-SNAPSHOT | dynamic  |
| B     | `6811d0cef3735d39ffd3801b3bae6ef48318bb66` | 0.3.131-SNAPSHOT | prepared |
| FINAL | `19d7426a5b8f0e3b93d36f56aee33377a4ee9985` | 0.3.143-SNAPSHOT | prepared |

Timed region: `dynamic` opens the session and times
`session.invokeTopLevel("run")`; `prepared` opens the session, calls
`session.prepareTopLevel("run")` outside every timed sample (reported as
`prepare_ns`), and times `prepared.invoke()`. Both modes share
`ProtosJvmVariantRunner.measure`: the cold sample is the first invocation
alone, and each warmup/steady sample is 100 invocations, each result checked.

Compilation boundary: `ProtosJvmVariantRunner` is built by Maven against the
common pinned `0.3.128-SNAPSHOT` artifact, which has no prepared API. The
prepared runner lives in `truffle/src/prepared/java` and is compiled by
`perf025_ab.py` with `javac` only against the B and FINAL variant classpaths.
No reflection is used; `javap` structural checks fail closed on the call
sites and on preparation ordering.

Identity: `measurement_definition=jvm-protos-session-ab-v2` includes role,
`run_mode`, harness revision/dirty state, Protos revision/version/Core hash,
GraalVM (`25.4.4.1.1`, verified from the dependency classpath), Java, CPU
identity, warmup/steady, `sample_calls`, and the admission policy. The full
identity is the local cache key.

Admission reuses `jvm_matrix.reference_admission` unchanged (warmup 60,
steady 10). A `NOT_STABLE` observation is written to
`results/local/truffle-rejected/`, is not cached, and is not retried.

Interpretation (per workload, on steady amortized per-call p50; negative means
the candidate took less time):

- `A_DELTA`: A/dynamic vs PRE_A/dynamic
- `B_DELTA`: B/prepared vs A/dynamic
- `COMBINED_PRE_A_TO_POST_B_DELTA`: B/prepared vs PRE_A/dynamic
- `FINAL_CURRENT_STATE`: FINAL/prepared, contextual only; it does not
  attribute A or B.

No aggregate across workloads or cross-language conclusion is produced.

Commands (`make -C truffle ...`): `perf025-d2-validate` (static only),
`perf025-d2-prepare` (exact checkouts under `.work/protos-ab/perf025-*`),
`perf025-d2-smoke` (12 cases, warmup 2/steady 3, no cache, no timing
interpretation), and `perf025-reference` (clean harness required).
Retention of the 12 accepted reference observations uses
`retain-results RETENTION_PROFILE=perf025 WORK_ITEM=PERF025-D3`
into `results/perf025-d3/`; the default `perf023` profile is unchanged.

## Generic JVM cross-Truffle harness: version-independent Protos authority

The generic JVM harness is intentionally independent of any particular Protos
release. Historical PERF experiments retain their exact pinned revisions and
measurement definitions, but the ordinary `correctness`, `jvm-smoke`,
`jvm-benchmark`, `jvm-jfr`, and `jvm-igv` entrypoints select a Protos checkout
at execution time.

`PROTOS_CHECKOUT` identifies the checkout and defaults to
`/workspaces/protos`. The selected checkout must be a clean Git checkout,
including no non-ignored untracked files. The harness records its exact HEAD
revision, project version, Core SHA-256, `pom.xml` SHA-256, dependency
classpath identity, runner source/classes identity, requested run mode and
resolved run mode. Ignored build output may exist, but source/configuration
drift that is not represented by the recorded Git revision is rejected.

`PROTOS_RUN_MODE` accepts `auto`, `dynamic`, or `prepared` and defaults to
`auto`:

- `auto` selects `prepared` when the selected checkout exposes
  `ProtosStandaloneHostedSession.PreparedTopLevel`;
- otherwise `auto` selects the historical `dynamic` surface;
- explicit `prepared` on a checkout without that API fails closed rather than
  silently falling back.

The Protos runner is compiled directly against the selected checkout's classes
and dependency classpath. GraalJS and GraalPy use a separate
`TrufflePeerJvmRunner` compiled only against the pinned Graal Polyglot/JS/Python
dependencies; the peer runner has no Protos compile-time or runtime dependency.
This removes the old generic-path dependency on the historical
`com.guillermomolina:protos:0.3.128-SNAPSHOT` declaration in `truffle/pom.xml`.
That declaration remains available to historical harness code that explicitly
depends on the old pinned baseline.

The generic matrix measurement definition is
`jvm-cross-truffle-generic-v3`. Correctness is checked before any accepted
timing or diagnostic output. `jvm-benchmark` retains the existing clean-harness
reference gate and stability admission rules; changing the selected Protos
checkout changes the evidence identity and therefore the cache key.

Typical current-checkout commands are:

```sh
make -C truffle correctness WORKLOAD=primitive-return-literal
make -C truffle jvm-smoke WORKLOAD=primitive-return-literal
make -C truffle jvm-benchmark WORKLOAD=primitive-return-literal
```

A different compatible checkout is selected without changing harness source:

```sh
make -C truffle correctness   WORKLOAD=primitive-return-literal   PROTOS_CHECKOUT=/path/to/protos   PROTOS_RUN_MODE=auto
```

### Generic JFR and IGV diagnostics

`jvm-jfr` and `jvm-igv` use the same version-independent runtime authority and
the same resolved Protos run mode as the generic correctness/matrix paths.
Diagnostic identity records the exact selected product/runtime identity and the
diagnostic workload policy. Diagnostic timing is explicitly non-primary.

Examples:

```sh
make -C truffle jvm-jfr   LANGUAGE=protos   WORKLOAD=primitive-return-literal

make -C truffle jvm-igv   LANGUAGE=protos   WORKLOAD=primitive-return-literal

make -C truffle jvm-igv   LANGUAGE=js   WORKLOAD=primitive-return-literal
```

`DIAGNOSTIC_WARMUP`, `DIAGNOSTIC_STEADY`, and
`DIAGNOSTIC_SAMPLE_CALLS` may override the diagnostic work shape. JFR defaults
to the workload catalog's sample-call count. IGV requires an optimizing
compilation before a BGV can exist, so when `DIAGNOSTIC_SAMPLE_CALLS` is not
specified it applies a 10,000-call minimum compilation floor. This floor is a
diagnostic-capture policy, not timing evidence.

The version-independent path was capability-validated across both sides of the
prepared-API transition: Protos `f0791896c3c022a747b4d47af629227da58acfab`
(`0.3.128-SNAPSHOT`) resolves to `dynamic`, while
`cfc0fb433e82f0478c9fff9cc965c3fc506fabc9` (`0.3.169-SNAPSHOT`) resolves to
`prepared`; forcing `prepared` on the former fails closed. Both revisions
produced correctness-passing JFR recordings and IGV BGV output for
`primitive-return-literal`. The same current harness also produced
correctness-passing JFR and BGV output for GraalJS on that workload. These
runs establish harness capability only and are not retained performance
evidence.

## PERF024 current cross-Truffle re-baseline

Owner: `guillermomolina/protos#756`. Re-baselines current Protos against the
pinned GraalJS/GraalPy JVM peers after PERF025-C1c/PLAT042 B-prime,
PERF025-C2B and PERF026 removed the helper/callback root topology. Historical
endpoint `f0791896c3c0` (`0.3.128-SNAPSHOT`) is context only and is not rerun.

Measurement definition `jvm-cross-truffle-current-v3` (the historical
`jvm-cross-truffle-v2` meaning and its evidence are unchanged). It supersedes:

- `jvm-cross-truffle-current-v1` (reference at harness `ca34b345`, not
  admitted, 5/9 NOT_STABLE): peer samples were generally undersized because
  every language used Protos' per-call `sample_calls`, so JS/Python samples
  lasted ~1 ms and were dominated by millisecond-scale background-compilation
  stalls on the single pinned CPU (a non-retained diagnostic showed GC was not
  the cause).
- `jvm-cross-truffle-current-v2` (reference at harness `272a7974`, not
  admitted): per-language sizing corrected most cases, but factorial JS/Python
  samples were still only ~6-8 ms and JS factorial was NOT_STABLE.

v3 raises only the factorial peer `sample_calls` (JS 3,000 -> 20,000, Python
3,000 -> 25,000) to bring those samples into the intended tens-of-milliseconds
range. Thresholds, warmup/steady counts, CPU policy and the no-retry policy
are unchanged. v1/v2 rejected raw stays local and is not evidence; v2 ratios
are not reported.

- CURRENT Protos `19d7426a5b8f0e3b93d36f56aee33377a4ee9985`
  (`0.3.143-SNAPSHOT`), exact managed checkout
  `.work/protos-ab/perf024-current`, `ProtosPreparedVariantRunner`:
  `session.prepareTopLevel("run")` before timing, `prepared.invoke()` timed.
- GraalJS / GraalPy: `TruffleJvmRunner` prepared executable `truffleRun`
  `Value`, `run.execute()` timed.
- All three run as plain `taskset -c <cpu> java -cp ... <main>` processes on
  GraalVM 25.4.4.1.1 / JDK 25.0.4.1.1 with no JVM options; the peers no
  longer run inside `mvn exec:java`.

Workloads and policy (50 warmup + 10 steady samples, steady-only admission
with the unchanged `jvm_matrix` thresholds). `sample_calls` is fixed per
workload and language so each steady sample lasts roughly 50 ms:

| Class | Workload | Protos | JS | Python | Evidence unit |
| --- | --- | --- | --- | --- | --- |
| EMBEDDING_FLOOR | `primitive-return-literal` | 10,000 | 500,000 | 500,000 | ns per reusable prepared invocation |
| GUEST_DOMINATED_CURRENT_STATE | `fibonacci` | 10 | 500 | 500 | ns per complete top-level `run()` |
| GUEST_DOMINATED_CURRENT_STATE | `factorial` | 20 | 20,000 | 25,000 | ns per complete top-level `run()` |

Ratios compare the per-call amortized p50, so different `sample_calls` per
language do not change the evidence unit.

The historical loop workloads `integer-loop` and `method-call` are
intentionally excluded: they use the standard Closure selector `while`, which
D180 renamed to `whileTrue` without a compatibility alias, so they fail on
CURRENT before timing. Historical workload sources are not rewritten.

The embedding floor includes the Protos dedicated guest carrier; it is part
of the current embedding architecture. Results are per-workload
`PROTOS_VS_JS_RATIO` / `PROTOS_VS_PYTHON_RATIO` (Protos time / peer time);
there is no aggregate score, the floor is never subtracted from other
workloads, `fibonacci`/`factorial` are algorithm-equivalent workloads, not
mechanism-isolating, and no whole-language ranking is implied. A NOT_STABLE
observation is kept as rejected local raw, excluded from ratios, fails the
reference, and is never re-measured for the same identity.

Commands (`make -C truffle ...`): `perf024-rebaseline-validate` (static),
`perf024-rebaseline-prepare`, `perf024-rebaseline-smoke` (9 cases, warmup
1/steady 2 at the reference `sample_calls`, `timing_interpretation=NONE-smoke`,
and a sample-size gate that fails if any steady sample is shorter than 20 ms)
and
`perf024-rebaseline-reference` (clean published harness required). Retention
uses `retain-results RETENTION_PROFILE=perf024-rebaseline
WORK_ITEM=PERF024-REBASELINE EXPECTED_RETAINED=9` into
`results/perf024-rebaseline/`.

## PERF025-E3 carrier transport A/B

Owner: `guillermomolina/protos#758`. Purpose: isolate the PERF025-E2 guest
carrier transport delta (per-call `Object[1]`/`Throwable[1]`/`boolean[1]`
holders, queued lambda and `synchronized`/`wait`/`notifyAll` replaced by one
typed `CarrierCall<T>` request completed with `LockSupport.park`/`unpark`;
dedicated carrier, 16 MiB guest stack, `LinkedBlockingQueue`, serialization
and multi-caller safety unchanged).

Measurement definition `jvm-protos-carrier-e2-ab-v1`. Both points run the
unchanged `ProtosPreparedVariantRunner` (`prepareTopLevel("run")` once,
outside timing; `PreparedTopLevel.invoke()` timed; no reflection, no dynamic
`invokeTopLevel`) on GraalVM 25.4.4.1.1:

| Role   | Protos revision                            | Version          | Run mode |
|--------|--------------------------------------------|------------------|----------|
| PRE_E2 | `c1eb2c2e1a811d70fcf09f5526217c1aaf14d141` | 0.3.144-SNAPSHOT | prepared |
| E2     | `ff618f0dd8ef680f7884c9145552f77912f040a2` | 0.3.145-SNAPSHOT | prepared |

PRE_E2 is E2's exact parent, so the unrelated BUG014 commit is present in
both comparison ancestry points. PERF025-D3 FINAL
(`19d7426a5b8f`) is deliberately not the baseline because it would mix BUG014
into the E2 causal delta.

Workloads (3): `primitive-return-literal`, `primitive-closure-call`,
`primitive-method-call`. Reference policy is the final PERF025-D3 policy
unchanged: `sample_calls=10000`, warmup 50, steady 10, steady-only admission
with the unchanged `jvm_matrix` thresholds (window 5, median drift 15%, MAD
20%, max internal gap 20%, min gap cluster 3), single pinned CPU, no retry.
Expected reference observations: 2 x 3 = 6.

Interpretation, per workload only:
`E2_DELTA = (E2 steady_amortized_p50 / PRE_E2 steady_amortized_p50 - 1) * 100`;
negative means E2 took less time.

Commands (`make -C truffle ...`): `perf025-e3-validate` (static contract,
identity, historical D3/PERF023/PERF024 evidence and profile drift),
`perf025-e3-prepare` (exact checkouts `.work/protos-ab/perf025-e3-pre-e2` and
`.work/protos-ab/perf025-e3-e2`, prepared runner compiled per exact classpath
under `.work/perf025-e3/prepared-runner/` and `javap`-checked), `perf025-e3-smoke`
(6 cases, warmup 2/steady 3 at 100 calls, no cache,
`timing_interpretation=NONE-smoke`) and `perf025-e3-reference` (clean
published harness required). Retention uses `retain-results
RETENTION_PROFILE=perf025-e3 WORK_ITEM=PERF025-E3 EXPECTED_RETAINED=6` into
`results/perf025-e3/` and selects only `jvm-carrier-e2-ab-v1-reference`
observations with the exact clean producer revision, `correctness=PASS`,
admission PASS, `run_mode=prepared`, one of the two pinned revisions and one
of the three workloads.

PERF025-E3A publishes harness capability only and contains no reference
result; the single reference and its retention are PERF025-E3B.

### PERF025-E3B retained reference

Single reference from exact clean harness
`3fb036ce86b6c452588230b5322967f55aaf0160`, retained byte-for-byte in
`results/perf025-e3/` (profile `perf025-e3`, 6/6
`jvm-carrier-e2-ab-v1-reference`, all `correctness=PASS`, steady-only
admission PASS, `harness_dirty=false`, CPU 0, GraalVM 25.4.4.1.1). No
observation was rejected or retried.

| Workload | PRE_E2 ns/call | E2 ns/call | E2_DELTA |
|----------|---------------:|-----------:|---------:|
| `primitive-return-literal` | 6692.7 | 6173.2 | -7.76% |
| `primitive-closure-call`   | 7522.6 | 7181.6 | -4.53% |
| `primitive-method-call`    | 7013.6 | 6589.4 | -6.05% |

Values are steady amortized per-call p50 (median of 10 steady samples of
10,000 `PreparedTopLevel.invoke()` calls). On this host and policy, E2 took
less time than its exact parent on all three workloads. This is a single
admitted reference per workload: it attributes the per-workload
difference to the E2 carrier transport change only within this embedding
call path, makes no claim about guest-dominated workloads, and is not
aggregated across workloads.

## Revision-independent Protos measurement driver (PERF033)

`truffle/measure_protos.py` is the normal path for current and future
measurements. The harness is a measuring instrument and a Protos revision is
data: advancing Protos never requires editing harness source.

    python3 truffle/measure_protos.py \
        --dir ../protos \
        --surface canonical \
        --workload primitive-return-literal \
        --profile jfr \
        --output results/<protos-version>

### Product selection

`--dir` is authoritative: the driver measures exactly the files in that
checkout. There is no option to select a revision, commit, tag or checkout,
and the driver runs only read-only Git commands (`rev-parse`, `status`,
`diff`, `ls-files`, `show`). It never clones, fetches, checks out or resets
anything. Building the product into its ignored `target/` output is the only
write to the checkout.

Immediately before the batch it records the absolute directory, HEAD, the
`pom.xml` version and GraalVM version, the clean/dirty state, a digest of all
tracked and untracked source state, and the Core hash. After the complete
batch it recomputes them (plus the hash of the built `target/classes`); any
difference produces `MEASUREMENT_VALID=NO`,
`REASON=PRODUCT_CHANGED_DURING_MEASUREMENT`. A dirty checkout is refused
unless `--allow-dirty-product` is given, and such a run is never
`reference_eligible`.

### Historical data policy

Saved results are the only historical source of truth. A past Protos revision
that was not measured while current has no measurement; the driver has no
mechanism to reconstruct one. The historical PERF-specific exact-revision
harnesses (`perf024_rebaseline.py`, `perf025_*.py`, `jvm_protos_ab.py`) and
their retained evidence remain as immutable historical artifacts and are not
used by this driver.

### Surfaces and adapters

`truffle/measure/cases.json` lists the surfaces. Each surface is a small
stable Java adapter compiled together with the JDK-only
`MeasurementEngine` against the exact classpath of the selected checkout
(`target/classes` plus `mvn dependency:build-classpath`). Requesting one
surface never compiles another.

| Surface | Setup before timing | Timed call |
| --- | --- | --- |
| `dynamic` | open session | `session.invokeTopLevel("run")` |
| `prepared` | `prepareTopLevel("run")` | `prepared.invoke()` |
| `canonical` | `prepareTopLevel("run")`, `executable()` | `executable.execute()` |
| `executable-value` (GraalJS/GraalPy) | eval, `getMember("truffleRun")` | `run.execute()` |

The canonical timed path takes no session gate and performs no
`PreparedTopLevel.invoke()`, `invokeTopLevel()` or Context enter/leave.
Polyglot results (canonical and peers) are normalized identically:
`fitsInBigInteger()` → `asBigInteger().toString()`, otherwise `toString()`.
Every timed call is checked against the first result, which is checked
against the workload's expected value.

If an adapter does not compile against the selected checkout the driver
reports `SURFACE_SUPPORTED=NO`, `SURFACE=<name>`, `REASON=<javac error>` and
exits 3; it never falls back to another surface. Adding a genuinely new
surface is an allowed harness change; a new revision using an existing
surface is not.

Peers use `--language js|python` (no `--dir` needed) with the GraalJS/GraalPy
version pinned by `truffle/pom.xml`; that runtime identity is recorded.

### Compiled adapter cache

Compiled adapters live in `.work/embedded/<protos-sha>/<surface>/<adapter-source-hash>/`
with an `identity.json` covering the Protos revision and source-state digest,
built product classes hash, dependency classpath hash, adapter source hash
and Java home/runtime version. An entry is reused only when that identity
matches exactly, otherwise it is recompiled. The cache is an optimization:
deleting `.work/embedded` loses no evidence, and it is never consumed as a
result.

### Measurement policy

Policy is data. `cases.json` holds default and per-workload `reference` and
`smoke` policy for `timing` and `jfr`; timing `sample_calls` falls back to the
workload catalog's `jvm_sample_calls`. Timing policy also declares
`admission_scope`: `warmup-and-steady` by default, and `steady-only` with
10,000 calls/sample and 50 warmup + 10 steady iterations for the
primitive embedding workloads, matching the established PERF025-D3 policy
(sub-millisecond samples are dominated by isolated GC/compilation pauses).
`primitive-return-literal` uses 1,000,000 calls/sample and 60 warmup + 10
steady iterations (still `steady-only`): ultra-small primitive reference
workloads need a per-sample call count long enough that periodic runtime/host
events are amortized rather than producing alternating timing populations,
and enough total warmup calls to pass the final compilation transition.
10,000 calls (~1 ms samples) produced alternating populations on the
GraalJS/GraalPy peers; 100,000 calls removed them but left samples near 10 ms
and 6M warmup calls, still short of final tiering on Protos. The policy
is selected only by workload, stage and kind, so Protos and every peer
language measure the same sample unit. `--warmup`, `--steady` and
`--sample-calls` are diagnostic overrides: such runs record
`source=cli-override` and are not `reference_eligible`.

Order within a batch: correctness (single call, must equal the expected
value) → timing run without instrumentation (reference stage requires the
existing stability admission over the policy's `admission_scope`) → optional JFR run. The JFR run uses
the same checkout, adapter, workload and case; the engine starts a
`jdk.jfr.Recording` (`profile` settings, stack depth 256) immediately before
the first steady iteration and stops it after the last, so the recording is
bounded to steady state by the harness itself.

### Results

`--output` is a directory owned by the driver (marked by
`.measure-protos-output`; the driver refuses a non-empty directory it did
not create, which protects retained PERF result trees). Each run is written
to `<output>/.staging/` and promoted only when complete to
`<output>/<language>-<surface>--<workload>--<stage>-<profile>/<run-id>/`:

- `metadata.json` — authoritative: `measurement_valid`, product identity
  before/after, surface/workload/expected result, policy, harness Git HEAD,
  `harness_dirty`, the exact SHA-256 of every harness source file that
  produced the run, adapter source hash, compiled-adapter cache identity,
  Java/GraalVM, OS/kernel/architecture, CPU and affinity, correctness.
- `summary.json` — timing statistics and admission, JFR artifact hash.
- `raw/` — product build, correctness, timing and JFR process logs.
- `jfr/steady.jfr` when `--profile jfr`.

Failed runs are promoted to `<run-id>.invalid` with
`measurement_valid=false` and a reason, and are never reused. If a valid run
with the same result key (product revision and source state, language,
surface, workload, stage, profile, policy) exists, the driver prints
`RESULT_ALREADY_EXISTS=YES` and measures nothing; `--remeasure` adds a new
run and keeps the old one.

### Dirty harness and publication

The harness does not need to be committed before measuring. A dirty harness
is recorded (`harness_dirty`) together with the exact producer source hashes,
which are re-checked after the batch (`HARNESS_CHANGED_DURING_MEASUREMENT`
invalidates it). Before publishing results, check that the files being
committed are byte-identical to the producer:

    python3 truffle/measure_protos.py --verify-producer <run-dir>

`WORKING_TREE_MATCHES_PRODUCER=YES` before committing (and
`HEAD_MATCHES_PRODUCER=YES` after) means the committed harness produced the
run; otherwise either keep the exact producer bytes or remeasure.

## Cross-Truffle compiled-graph structural parity (PERF032-F)

`truffle/measure_graphs.py` records the *structure* of the compiled Graal
graphs that one steady prepared `Value.execute()` operation runs, for Protos
and the GraalJS/GraalPy peers, on the same surfaces as the timing driver
(Protos `canonical` `prepared.executable().execute()`, peer
`executable-value` `truffleRun.execute()`). It produces no timing: graph
instrumentation is never a timing run.

### Selected graph and metric

The selected phase is the Graal `StructuredGraph` **`After TruffleTier`**:
after Truffle partial evaluation and Truffle-tier cleanup, before generic
high/mid/low-tier optimization. The primary metric is

    relevant_graph_nodes_total_after_truffle_tier

the sum of the exact IR node counts of that graph over every relevant
language-owned compilation unit of one steady operation, always reported with
`primary_guest_graph_nodes`, `graph_count` and
`additional_language_owned_compiled_units`. Each dump also contains a
same-named non-IR view (the `AST` group's `After TruffleTier`,
`graph_type=defaultType`); only `graph_type=StructuredGraph` graphs are
candidates, and exactly one must match or the case fails closed
(`PHASE_MISSING`/`PHASE_AMBIGUOUS`). The TraceCompilation `AST` count is not a
graph-size metric; its `IR <after-truffle-tier>/<final>` value is retained as
a cross-check, and in the PERF032-F matrix it equals the BGV node count.

Secondary, per selected graph: the node-class histogram and the families
derived from it (`invokes`, `control_flow_splits`, `allocations` including
boxing, `guards_deopts`, `loads`, `loops`), surviving `Invoke` target
methods, and the `TraceNodeExpansion` truffleTier table (Count, Size, Cycles,
Ifs, Loops, Invokes, Allocs) with the largest-own-count expansion rows as
language/runtime attribution.

### Capture options

Policy is data in `truffle/measure/graphs.json`:

    -Dpolyglot.engine.AllowExperimentalOptions=true
    -Dpolyglot.engine.TraceCompilation=true
    -Dpolyglot.engine.BackgroundCompilation=false
    -Dpolyglot.compiler.TraceNodeExpansion=truffleTier
    -Dpolyglot.compiler.TraceInlining=true
    -Djdk.graal.Dump=Truffle:1
    -Djdk.graal.DumpPath=<case>/budget-<n>/dumps

`CompileImmediately` and `Dump=Truffle:2` are not used; they are later
escalation tools only. `TraceInlining` is needed for unit accounting.

### Relevant compilation units

Fully generic (`truffle/graph_evidence.py`); a language contributes only data
(framework-label pattern, primary-label pattern):

- **Lifecycle.** Compilations are grouped per CallTarget (`engine`, `id`).
  The final compilation of a target is its last `opt done`; earlier tier
  versions and retries are superseded and never summed. An invalidation
  (`opt inval.`, `opt deopt … Invalidated true`) or failure after the final
  compilation makes the unit unstable.
- **Primary unit.** The framework entry root
  (`org.graalvm.polyglot.Value<…>.execute`, common to all languages, never
  counted) has exactly one depth-1 callee in its inlining trees; that is the
  primary guest unit. It must match the language's primary-label pattern
  (`run`, `<bytecode run at …>`, `Protos…RootNode…@…` or
  `protos-root:<16 hex>`); GraalJS additionally must point `Src` at the
  workload file.
- **Additional units.** A callee that remains a call (`Cutoff`, `Indirect`,
  `BailedOut`) in the final compilation of a counted unit, and is a
  separately compiled language-owned target, is counted once, transitively.
  Inlined callees are already in the caller's graph and are never added; a
  callee that remains a call but was never compiled makes the run unstable.
- Roots not reachable from the primary unit (setup, module evaluation,
  GraalPy import machinery) are listed as `unattributed_language_targets` and
  never counted.

### Natural warmup and stabilization

Each budget (`1,000`, `4,000`, `16,000`, `64,000`, `256,000` calls) is one
fresh JVM running the engine `measure` mode with 0 warmup and 1 steady
iteration of that many result-checked calls. A run is a stable candidate when
every unit is at the final tier (2), was not invalidated or failed after its
final compilation, and the trace parsed with no rejected option or unknown
lifecycle event. The case is `STABLE` at the first two consecutive budgets
with identical signatures (units, tier, IR count, truffleTier expansion
totals). `summarize` re-confirms the pair on the BGVs (identical node count
and histogram per unit) or reports `GRAPH_NOT_STABLE`. With no pair by 256k
the case is `GRAPH_NOT_STABLE` and its evidence is kept, but no graph is
chosen.

### Comparison

Per rung: Protos/JS/Python totals, graph counts and additional units. The
peers are the structural reference: `PEER_REFERENCE=UNRESOLVED` when either
peer has no valid stable evidence, when their `graph_count` differs, or when
they disagree on the presence of invokes, allocations or loops. Otherwise
`CONVERGED`, and their observed `[min, max]` band and spread form the envelope
(no fixed tolerance). With converged peers, Protos is `STRUCTURAL_EXCESS`
when it has an additional compiled unit, an excess over the peer maximum
larger than the peer spread, or a family absent in both peers; otherwise
`STRUCTURALLY_CONVERGED`. If Protos never stabilizes while the peers converge,
the rung is `PROTOS_STABILIZATION=GRAPH_NOT_STABLE`,
`PROTOS_STRUCTURAL_STATUS=DIVERGED_BEFORE_GRAPH_PARITY`, `PROTOS_NODE_TOTAL=N/A`,
`PEER_NODE_COMPARISON=SKIPPED`, plus the final compilation state and
lifecycle facts re-derived from the retained trace. Both kinds of status
count as divergences for `first_divergent_rung`. These are findings, not
acceptance constants; no optimization follows from them inside this
harness.

### Commands and hosts

Capture needs the JVMs; BGV analysis needs Docker and uses only
`scripts/igv_analyzer.sh` with the published GraalVM 25.4.4.1.1 IgvUtility
image (see IGV analyzer generations). The two may run on different hosts
that share the working tree.

    make -C truffle graphs-test                       # unit/static tests
    make -C truffle graphs-smoke                      # 1 budget, return-literal, 3 languages
    make -C truffle graphs-capture PROTOS_CHECKOUT=…  # reference capture
    make -C truffle graphs-analyze                    # Docker host: IgvUtility filter
    make -C truffle graphs-summarize                  # unit.json + matrix.json
    make -C truffle graphs-verify                     # producer hashes vs tree/HEAD

`GRAPH_WORKLOAD` (default `ladder`), `GRAPH_LANGUAGE` (default `all`) and
`GRAPH_OUTPUT` (default `results/perf032-f`) select the scope. A smoke admits
the pipeline on one budget and is labelled `stage=smoke`; it is never
evidence.

### Retained evidence

`<output>/<workload>/<language>/`:

- `capture.json` — authoritative capture record: evidence-unit definition,
  Protos identity before/after, exact producer source hashes and harness HEAD,
  Java/GraalVM, host/CPU affinity, graph JVM options, correctness, every
  budget's lifecycle assessment, resolved units, and the name/size/SHA-256
  inventory of every BGV dump produced.
- `budget-<n>/trace.log.gz` — raw trace of every budget run.
- `budget-<n>/bgv/*.bgv.gz` — raw BGVs of the selected units of the stable
  pair (or of the last two budgets when not stable), and the
  `*.filter.json.gz` IgvUtility output next to each.
- `raw/` — product build and correctness logs.
- `unit.json` — the derived evidence unit (selected budget/tier/units,
  per-unit graph metrics, totals, validity).
- `<output>/matrix.json` — rung comparison and `first_divergent_rung`.

### PERF032-F primitive ladder result

Protos `c0ac98971df115d64b7bc9f146e8b02e11da30e6`, GraalVM CE 25.4.4.1.1
(`25.0.4.1.1+1-jvmci-25.4-b23`), single pinned CPU, `results/perf032-f/`.
All 24 cases passed correctness. 23 stabilized at the `[16000, 64000]` pair;
`primitive-object-slot-write`/Protos did not stabilize by 256k. Every valid
case has `graph_count=1`.

| Rung | Protos | GraalJS | GraalPy | Peer band (spread) | Protos status |
| --- | ---: | ---: | ---: | --- | --- |
| primitive-return-literal | 282 | 13 | 49 | 13–49 (36) | STRUCTURAL_EXCESS |
| primitive-local-read | 1283 | 13 | 49 | 13–49 (36) | STRUCTURAL_EXCESS |
| primitive-local-write | 2343 | 13 | 49 | 13–49 (36) | STRUCTURAL_EXCESS |
| primitive-integer-add | 4595 | 14 | 49 | 14–49 (35) | STRUCTURAL_EXCESS |
| primitive-object-slot-read | 583 | 36 | 103 | 36–103 (67) | STRUCTURAL_EXCESS |
| primitive-object-slot-write | N/A | 100 | 159 | 100–159 (59) | DIVERGED_BEFORE_GRAPH_PARITY |
| primitive-closure-call | 4741 | 13 | 50 | 13–50 (37) | STRUCTURAL_EXCESS |
| primitive-method-call | 2139 | 34 | 74 | 34–74 (40) | STRUCTURAL_EXCESS |

The peers converge on every rung. **The first divergent rung is
`primitive-return-literal`**, the baseline callable entry: the Protos
After-TruffleTier graph has 282 nodes against a 13–49 peer band, with
Protos-only surviving invokes (`ProtosBytecodeRootNode.selectGuestHandlerOnRootCrossing`,
`ProtosFrameArguments.materializeCompactActivation`, `List.size`),
control-flow splits (12) and guards/deoptimization checks (15). The largest
own-count expansion rows are the generated
`ProtosSemanticBytecodeRootNodeGen$CachedBytecodeNode`. The excess grows with
local bindings (local-read adds `ProtosLexicalBindingAuthority*`/
`ProtosLexicalFallback.readByName` invokes; local-write, integer-add,
object-slot-read, closure-call and method-call also carry a Protos-only
surviving loop).

`primitive-object-slot-write`/Protos is `GRAPH_NOT_STABLE`: the primary root
is invalidated after every Tier-1 compilation (100 compilations, 200
invalidation events at 256k), fails with `Maximum compilation count 100
reached.`, and the framework root then records it as `BailedOut`; no
Protos graph is compared on that rung. Both peers are stable there.

No rung needs an additional Protos compiled unit: the earlier double-Bytecode
helper CallTarget does not appear on these primitive paths
(`DOUBLE_BYTECODE_DISPATCH_CURRENTLY_ESTABLISHED=NO` for this ladder). The
Protos excess lies inside the single primary semantic-Bytecode graph. These
are structural findings only; no Protos product change, semantic change or
microoptimization is part of PERF032-F.
