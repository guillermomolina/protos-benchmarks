# Changelog

All notable changes to Protos Benchmarks are documented in this file.

## Unreleased

### Fixed

- Recovered the pinned Graal 24 IGV `bgv2json` path used by PERF003-A: the analyzer now compiles the pinned `JSONExporter` against the complete built IGV distribution, bounds physical JSON filenames with a deterministic full-identity fingerprint, preserves graph metadata in JSON, and validates the path with a real BGV-to-JSON smoke test.

### Added

- Added a storage-bounded PERF003-A compact IGV extraction path for large BGV captures. It parses each BGV with the pinned IGV data model, records BGV SHA-256, graph identities, node/edge counts and configured suspect-term occurrences, and resumes per BGV without materializing the full JSON export.
- Added resumable PERF003-A IGV export for already-captured structural BGV evidence. The resume path processes BGVs sequentially into isolated per-source directories, uses atomic completion markers, cleans only incomplete item output, guards free disk space before each export, and never rebuilds or re-executes the Protos structural capture.
- Added `PERF003-A` structural Truffle/Graal diagnostics for the residual `array-reduce` `GraphTooBig` investigation. The diagnostic captures `Truffle:2` BGV dumps plus method/node expansion evidence from the pinned JDK 22 runtime, converts BGV with the separately isolated JDK 17 IGV analyzer, and publishes bounded attribution summaries without changing Protos semantics or treating occurrence counts as causal proof.
- Added a correctness-first `PERF003-A` external compilability diagnostic pinned to Protos `d66841adb0b820047ed079f0bc7d643873f23194` (`0.2.180-SNAPSHOT`). It rechecks `array-reduce` and `array-sort` under interpreter and optimizing Truffle execution, retains raw TraceCompilation evidence, and treats remaining compiler bailouts as publishable diagnostic findings rather than correctness failures.
- Added a dedicated IGV `bgv2json` diagnostic container pinned to Graal `vm-24.0.0` (`78238a5ee6e4ae827059c70549e286ae730b7730`) and mx `6.27.1` (`d0d6d6cd2f70bb384dfba9f3f66f3dab21392ae4`). Its JDK 17 build environment is isolated from benchmark runtime images because that IGV revision uses NetBeans 14 components that still require `javac --release 7`; analysis runs with networking disabled.
- Added the `PERF001-E` sequential-collections comparison harness pinned to exact Protos corpus revision `86b35d8bb2d7ab2ad54bc2947e1bf7fbff1fca15`. The six canonical workloads receive explicit algorithm-equivalent Python and JavaScript implementations; stable Array sort remains a manual merge sort and map-backed Set algebra remains explicit rather than using host bulk collection primitives.
- PERF001-E publishes correctness-gated startup, retained warmup and steady-state measurements across Protos/Python/JavaScript on one pinned CPU with networking disabled. Protos uses GraalVM Community JDK 22, external `truffle-runtime:24.0.0` and `-Xss128m`; compilation tracing is isolated in separate non-timing diagnostics whose compiler bailouts are retained as baseline findings rather than correctness failures. Exact harness/evidence commits, raw samples, runtime image identities and environment metadata are retained for later canonical Protos ledger reconciliation.
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
