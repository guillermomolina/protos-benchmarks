# Protos HEAD campaign — 2026-11-25

- Protos commit: `510a2c71e9c62cc3c147dea447c70d26e18d9d36` (`0.4.213-SNAPSHOT`)
- Benchmark harness commit: `9d7ece250bfb2ea4ce7157f3cd959b25c7e71323`
- Scope: 21 Protos workloads only; no peer reruns.
- GraalVM: 25.5.5.0.3.
- Host: AMD Ryzen 7 3700X, CPU 1.
- Correctness: 21/21 PASS.
- Cold and hot reference timing: 21/21 valid.
- Tier 1: 47 compiled roots.
- Tier 2: 47 compiled roots.
- Bytecode DSL: 21/21 captures.
- Structural reports: 21/21 COMPLETE.
- Raw evidence and original metadata preserved.
- Captured roots do not establish interpreted-root coverage.
- Cross-runtime comparisons must identify toolchain differences.
