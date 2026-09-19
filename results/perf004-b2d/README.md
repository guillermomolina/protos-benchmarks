# PERF004-B2-D paired JFR canonical/control

- Harness revision: `da2c8acaf3471601734e96085a967c78c32d0fe0`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- PERF004-A evidence: `5e8ff21f966c6c506652eef79c684d8b286bb546`
- PERF004-B2-A evidence: `8d8e1c6cce843d0d64c9e0b740ba13df04b3effb`
- PERF004-B2-B evidence: `cf9974970b4102d3e58191667b64d2981132c4bf`
- PERF004-B2-C evidence: `8899ec163d6c0c7133b15ffa9c323447b683dbf2`
- Runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- N=10,000.
- Warmup=20, steady=100.
- JFR ExecutionSample period=10 ms.
- Diagnostic-only; no sole-cause claim.

Canonical/control pairs differ only by the approved B2-C operation replacement.
