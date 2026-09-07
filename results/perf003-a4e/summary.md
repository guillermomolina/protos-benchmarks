# PERF003-A4e residual dynamic-control falsification

- Harness revision: `fe249e414ceb1766605b98f5943b612eac90e2ac`
- A4e1b revision: `fe249e414ceb1766605b98f5943b612eac90e2ac`
- Execution base: `fe249e414ceb1766605b98f5943b612eac90e2ac`
- Protos revision: `d66841adb0b820047ed079f0bc7d643873f23194`
- Workload/result: `collections/array-reduce => 528`
- Diagnostic iterations: 20
- Experimental boundaries: `ProtosClosureInvoker.invokePrepared, ProtosActivation.inheritDynamicControlState`
- A4a reference GraphTooBig: 40
- A4a reference shape: `48153:150001:150000`
- Control GraphTooBig: 40
- Control shape: `50681:150026:150000`
- Boundary GraphTooBig: 40
- Boundary shape: `50290:150037:150000`
- Hypothesis: **INCONCLUSIVE**
- Reason: dynamic-control boundary changed the A4a residual diagnostics without a directional result
- Timing evidence: NO
- Protos repository changed: NO

The conclusion was independently recomputed from the retained TraceCompilation streams and cross-checked against the harness-produced conclusion.
