# PERF002-B Truffle validation evidence

Status: PUBLISHED_AWAITING_PROTOS_LEDGER
Timing results: NO

- Protos revision: `3c93912a5579326374782a43527fbb51046f8f91`
- Protos implementation version: `0.2.162-SNAPSHOT`
- Harness revision: `224ce852f550a7d9126fad9f5923a9a2fd8194cc`
- Graal base: `ghcr.io/graalvm/jdk-community:22.0.0`
- Truffle runtime: `24.0.0`
- Runtime class: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Stack: `-Xss128m`
- Validation cpuset: `0`
- Semantic smoke: PASS
- Canonical 11x2 correctness: PASS
- Known Truffle bailout/runtime guard: PASS
- Truffle opt-done total: `238`
- Truffle opt-failed total: `0`

This is non-timing evidence for PERF002-B. Raw stdout/stderr and compilation
diagnostics are retained under `raw/`. Canonical PERF002 lifecycle state remains
owned by `guillermomolina/protos`; the enclosing evidence commit must be recorded
there before PERF002-B and PERF002 are canonically CLOSED.
