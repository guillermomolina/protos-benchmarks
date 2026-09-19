# PERF004-B2-C causal control contrast

- Harness revision: `8be0dca8a1d2b7203663f409c35159a5bd5998b5`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- PERF004-A evidence: `5e8ff21f966c6c506652eef79c684d8b286bb546`
- PERF004-B2-A evidence: `8d8e1c6cce843d0d64c9e0b740ba13df04b3effb`
- PERF004-B2-B evidence: `cf9974970b4102d3e58191667b64d2981132c4bf`
- Runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Operation count: 10,000.
- Warmup: 20 iterations.
- Steady: 50 iterations.

Canonical and control variants retain the same outer repeat and
activation structure. Only the selected guest operation is replaced
with `sink = 42`.

This is a causal-control experiment, not a claim that the measured
difference is the whole cross-language performance gap.
