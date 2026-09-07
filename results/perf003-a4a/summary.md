# PERF003-A4a controlled boundary experiment

- Harness revision: `da44b819f29aa26ba7d88a7ba1d3751b1d80b592`
- Protos revision: `d66841adb0b820047ed079f0bc7d643873f23194`
- Workload: `collections/array-reduce`
- Expected result: `528`
- Diagnostic iterations: 20
- Experimental boundary: `ProtosClosureInvoker.invokePrepared`
- Control `opt_failed`: 40
- Control `GraphTooBig`: 40
- Boundary `opt_failed`: 40
- Boundary `GraphTooBig`: 40
- Hypothesis: **SUPPORTED**
- Reason: boundary reduced failing graph size
- Timing evidence: NO
- Protos repository changed: NO

This is controlled falsification evidence. A SUPPORTED result attributes a material portion of graph growth to expansion through the selected host helper, but does not by itself justify retaining the diagnostic boundary as a production optimization.
