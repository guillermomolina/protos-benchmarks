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
