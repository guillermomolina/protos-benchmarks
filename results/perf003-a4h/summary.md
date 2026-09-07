# PERF003-A4h result

- Harness: `041a6b821387494e6299c93334d72ecd8b3ce494`
- Protos: `d66841adb0b820047ed079f0bc7d643873f23194` (`0.2.180-SNAPSHOT`)
- Workload/result: `collections/array-reduce => 528`
- Iterations: 20
- Control: GraphTooBig=40, shapes=50681:150026:150000
- Split: GraphTooBig=40, shapes=48823:150002:150000
- Control reproduction: PASS
- Hypothesis: **INCONCLUSIVE**
- Reason: sync/task split changed the A4a residual diagnostics without a directional result
- Timing evidence: NO
