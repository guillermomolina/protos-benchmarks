# Protos HEAD campaign — 2026-11-20

- Protos commit: `2df251847ead94012f8d5a87c2b81d2d981882c7` (`0.4.186-SNAPSHOT`)
- Benchmark harness commit: `51b1f3fa137f3db1ab2498afde320ca8242b8785`
- Scope: 18 Protos workloads only; no peer reruns.
- Evidence: `timing/` (raw reference timing and per-run correctness admission), `correctness/` (standalone records if available), `bytecode/` (raw DSL histograms), `cold/tier-1/` and `cold/tier-2/` (raw compiled graphs), `structural/` (derived reports), `manifest.json` (SHA-256 per file).
- Capture and analysis outputs were valid; `structural-report.json` status COMPLETE for all 18 workloads.
- Captured compiled roots do not prove coverage of interpreted-only roots.
- Protos and GraalPy use different pinned GraalVM versions; do not present cross-runtime numbers as same-toolchain parity.
