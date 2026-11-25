# TruffleRuby reference campaign — 2026-11-25

- TruffleRuby: 40.0.0.
- GraalVM: 25.3.4.1.
- Harness: c36d89afd4a17b479206b22e223b6e1dbe8b9f2f.
- Host: AMD Ryzen 7 3700X, CPU 1.
- Scope: 21 Ruby workloads only.
- Correctness: 21/21 PASS.
- Cold and hot timing: 21/21 valid.
- Tier 1: 348 compiled roots.
- Tier 2: 51 compiled roots.
- Graph analysis: 399 graphs, zero failures.
- Structural reports: 21 generated, 21 incomplete.
- Object#run and Value.execute observed at both tiers
  for all workloads.
- Bytecode DSL: not applicable.
- Raw evidence and original metadata preserved.
- Incomplete tier pairing must not be treated as
  complete structural coverage.
- Cross-runtime comparisons use different toolchains.
