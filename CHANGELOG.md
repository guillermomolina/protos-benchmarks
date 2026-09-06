# Changelog

All notable changes to Protos Benchmarks are documented in this file.

## Unreleased

### Added

- Established the `guillermomolina/protos-benchmarks` companion repository.
- Added repository governance and reproducibility rules for future Protos
  performance work.
- Adopted the Adaptive Public License 1.0 with a Protos Benchmarks-specific
  Exhibit A.
- Added the PERF001-B Docker benchmark harness with exact Protos revision
  pinning, runtime/host inventory capture, CPU-affinity policy, and a raw-result
  schema.
- Added correctness smoke validation for the Protos CLI, canonical corpus
  presence, and a Python control runtime without publishing timing results.
- Added the PERF001-C algorithm-equivalent manifest for all 11 canonical
  `micro`, `runtime`, and `algorithms` workloads.
- Added Python and JavaScript comparison implementations and a 33-case
  correctness gate that validates every Protos/Python/JavaScript observable
  result before any later timing work is permitted.
- Added a pinned Node.js comparison runtime and a correctness-evidence schema;
  PERF001-C still publishes no performance timings.
- Pinned PERF001-C to Protos `42b8264a36254dafbd97d80f5181790e28b9de12` and recorded the Protos `-Xss64m` JVM
  stack policy required to preserve the canonical 10,000-step recursive workload
  shape without rewriting benchmark control flow.
- Added the `PERF002-B` external optimizing-Truffle validation harness pinned to Protos `3c93912a5579326374782a43527fbb51046f8f91`, with an external `truffle-runtime:24.0.0` on GraalVM Community JDK 22 and the validated `-Xss128m` recursive-workload stack policy.
- Added retained non-timing PERF002 evidence for semantic call/extraction regressions and the canonical 11x2 interpreter/Truffle workload matrix, including raw compilation diagnostics and reproducibility metadata. Canonical PERF002 closure remains owned by the Protos ledger.
- Added the `PERF001-D` measurement harness for Protos startup, retained warmup curves, steady-state samples, and separate non-timing Truffle diagnostics. It pins the exact revisions immediately before and after PERF002-A (`8f363d0146164f99e72210eb44667f4efb7b88e7` and `3c93912a5579326374782a43527fbb51046f8f91`), uses the same GraalVM/Truffle 24.0.0 environment, `-Xss128m`, one pinned CPU, and networking disabled.
- PERF001-D retains 10 fresh-JVM startup samples, 20 ordered warmup samples and 20 steady-state samples for each of the 11 canonical workloads in interpreter and Truffle modes for both revisions. Compilation tracing is kept in separate diagnostic runs; raw samples/environment/runtime identity and derived median/MAD/min/max/p95 summaries are retained as reference evidence. Canonical PERF001-D closure remains owned by the Protos ledger.
