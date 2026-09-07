# PERF003-A4b controlled invoke-entry boundary experiment

- Harness revision: `dcad088781e7348e1e40a389768f8ca7b836cf18`
- Protos revision: `d66841adb0b820047ed079f0bc7d643873f23194`
- Workload: `collections/array-reduce`
- Expected result: `528`
- Diagnostic iterations: 20
- Experimental boundary: `ProtosClosureInvoker.invoke(ProtosClosureValue,List,ProtosActivation)`
- Control `opt_failed`: 40
- Control `GraphTooBig`: 40
- Boundary `opt_failed`: 40
- Boundary `GraphTooBig`: 40
- Hypothesis: **NOT_SUPPORTED**
- Reason: invoke-entry boundary left GraphTooBig count and graph shape unchanged
- Timing evidence: NO
- Protos repository changed: NO

This is controlled falsification evidence. A SUPPORTED result identifies the wider closure invoke-entry path as structurally causal, but does not by itself justify retaining the diagnostic boundary in production.
