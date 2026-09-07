# PERF003-A4c controlled immediate-method boundary experiment

- Validated harness revision: `970ce2d2e1aadc445e41598a61577d1001300f4f`
- Execution base: `970ce2d2e1aadc445e41598a61577d1001300f4f`
- Protos revision: `d66841adb0b820047ed079f0bc7d643873f23194`
- Workload: `collections/array-reduce`
- Expected result: `528`
- Diagnostic iterations: 20
- Experimental boundary: `ProtosClosureInvoker.invokeImmediateMethod`
- Control GraphTooBig: 40
- Control shapes: `50681:150026:150000`
- Boundary GraphTooBig: 0
- Boundary shapes: `NONE`
- Hypothesis: **SUPPORTED**
- Reason: immediate-method boundary eliminated GraphTooBig
- Timing evidence: NO
- Protos repository changed: NO

Publication recovery reused the already successful retained run; the experiment was not rerun. The malformed original conclusion file was reconstructed only after independently recomputing the result from the raw traces.
