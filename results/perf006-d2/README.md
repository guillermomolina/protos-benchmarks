# PERF006-D2 controlled fallback/optimizer timing evidence

Exact-source comparison of the D1-proven runtime variants.

- harness revision: `1a752e92569b4ed42d3f9f55f67d1a7447eae308`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- implementation version: `0.2.492-SNAPSHOT`
- optimizer: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- fallback control: `com.oracle.truffle.api.impl.DefaultTruffleRuntime`
- ratio definition: `fallback median / optimizer median`
- ratio > 1 means optimizer is faster
- heavy compiler diagnostics: excluded from reference timing and deferred to D3
- historical ~20 min -> ~8 min full-suite observation: not used as a benchmark claim

| workload | startup ratio | warmup ratio | steady ratio |
| --- | ---: | ---: | ---: |
| micro/closure-call | 0.4718 | 1.3827 | 1.3662 |
| micro/method-call | 0.4835 | 1.3761 | 1.7325 |
| runtime/monomorphic-dispatch | 0.4627 | 1.2808 | 1.4366 |
| runtime/polymorphic-dispatch | 0.5357 | 0.9745 | 1.5049 |
| algorithms/fibonacci/recursive | 0.8555 | 1.0806 | 1.0561 |

See `raw.json` for every ordered sample and `summary.json` for
median/MAD/min/max/p95 summaries and per-iteration medians.
