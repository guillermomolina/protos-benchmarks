# PERF008 steady-state full-stack JFR evidence

- Harness revision: `72a3310dfa192666bb1a35bb49df6ae9f7d23d9b`
- Protos revision (current): `529ab58c2cf57a2e4170dd5ffa972651e89ac92e`
- Historical Protos revision (PERF004-B2-D / PERF006-D3; not mixed with current-revision measurements): `4a03efc15620b37b2e418b3df30b4a26486446ec`
- Runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Java: `openjdk version "25.0.4.1" 2026-08-18`
- GraalVM release: `25.3.4.1`
- Graal/Truffle components version: `25.3.4.1`
- Container image: `ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825`
- CPU policy: cpuset-cpus=`0`; network disabled; no explicit memory limit.
- N=10,000.
- Warmup=20, steady=100.
- JFR ExecutionSample period=10 ms.
- JFR recording phase: **steady-state only** — `Recording.start()` immediately before the steady loop, `Recording.stop()` immediately after; bootstrap and warmup are excluded from the captured recording.
- Stack depth limit: 32 bounded, leaf-first frames retained per `jdk.ExecutionSample`.
- Diagnostic-only; no sole-cause claim; no Protos optimization applied.

Canonical/control pairs use the identical PERF004-B2-C-approved operation replacement as `results/perf004-b2d`. This evidence does not supersede `results/perf004-b2d` or `results/perf006-d3`; it is a same-matrix, current-revision, steady-state-only, full-bounded-stack capture meant to be read alongside them without merging revisions into one comparison.

See `raw.json` for the per-profile `continue_at` (leaf/any-depth share, callers, callees, ranked full paths, and marker co-occurrence with `Unsafe.putObject`, `FrameExtensionsUnsafe`, `ProtosObjectValue.readLocalSlot`, `ProtosActivation.lookup`, and `CallTarget`) and `builder` relationship sections, and `summary.tsv` for a flat per-workload overview.
