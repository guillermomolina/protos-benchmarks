# PERF004-B2-B steady-state mechanism profiles

- Harness revision: `a5a49ed055a2bf856928aa11ec64e434dec573d4`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- PERF004-A evidence: `5e8ff21f966c6c506652eef79c684d8b286bb546`
- PERF004-B1 evidence: `d73a982be26a6661d934727035afad0f459c3c26`
- PERF004-B2-A evidence: `8d8e1c6cce843d0d64c9e0b740ba13df04b3effb`
- Runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Operation count: 10,000.
- Warmup: 20 iterations.
- Steady: 100 iterations.
- JFR execution-sample period: 10 ms.
- Diagnostic-only; no causal or language-wide performance claim.

| workload | samples | top frame | top-frame share | JDK deopts | Truffle deopts |
| --- | ---: | --- | ---: | ---: | ---: |
| micro/slot-read | 1151 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 38.141% | 11622 | 11596 |
| micro/closure-call | 1006 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 37.078% | 9305 | 9283 |
| micro/method-call | 1030 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 30.874% | 9156 | 9131 |
| runtime/monomorphic-dispatch | 1283 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 40.140% | 20278 | 10351 |

Raw JFR-derived profiles in `raw.json` are authoritative.
Hot-frame concentration is diagnostic evidence, not proof of causality.
Interpretation must be combined with PERF004-B2-A scaling evidence.
