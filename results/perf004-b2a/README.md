# PERF004-B2-A work-scaling contrast

- Harness revision: `d2cdc37529eac9f3333750a5274879895c727701`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- PERF004-A evidence: `5e8ff21f966c6c506652eef79c684d8b286bb546`
- PERF004-B1 evidence: `d73a982be26a6661d934727035afad0f459c3c26`
- Runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`

This is a diagnostic contrast, not a performance claim.
Each variant changes exactly one canonical `repeat(10000,` literal to
`repeat(N,` inside the benchmark container. Observable results remain 42.

A roughly stable time-per-operation across N supports a per-operation
cost interpretation; a large fixed intercept suggests execution/setup
cost that is not proportional to guest work. Neither result alone proves
a specific hotspot is causal.
