# PERF004-B1 Protos mechanism profiles

- Harness revision: `bce9a836909cdd34d9569ea46c5dd22c58347044`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- Baseline evidence revision: `5e8ff21f966c6c506652eef79c684d8b286bb546`
- Runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Diagnostic-only: yes
- This report does not select an optimization and does not claim whole-language performance.

| workload | execution samples | top frame | top-frame share | JDK deopts | Truffle deopts |
| --- | ---: | --- | ---: | ---: | ---: |
| micro/slot-read | 995 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 33.970% | 9086 | 9057 |
| micro/slot-write | 1194 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 41.457% | 12578 | 12555 |
| micro/closure-call | 1086 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 35.635% | 9604 | 9578 |
| micro/method-call | 1000 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 33.000% | 11357 | 11338 |
| micro/object-creation | 1012 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 37.055% | 21475 | 11452 |
| micro/delegation-shallow | 967 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 30.817% | 11323 | 11302 |
| micro/delegation-deep | 954 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 33.753% | 11729 | 11706 |
| runtime/monomorphic-dispatch | 1024 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 35.449% | 12893 | 12871 |
| runtime/polymorphic-dispatch | 1110 | `com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt` | 37.658% | 14394 | 14368 |

The raw JFR-derived profiles in `raw.json` are authoritative for this diagnostic slice.
Top-frame concentration is evidence of where sampled execution time was observed; it is not by itself proof of causality.
PERF004-B must combine these profiles with the exact PERF004-A steady-state ratios and targeted counterfactual/contrast experiments before assigning a mechanism as causal.
