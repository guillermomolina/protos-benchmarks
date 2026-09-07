# PERF003-A4g immediate-method preparation-unit falsification

- Harness revision: `7c701e767f7f676b3af7f78fa99ecc93dafc4410`
- A4g2 revision: `de74bc4d16ec4f5b1d1c404c57bdff9a1b9408ff`
- Protos revision: `d66841adb0b820047ed079f0bc7d643873f23194`
- Workload/result: `collections/array-reduce => 528`
- Diagnostic iterations: 20
- Experimental boundaries: `ProtosClosureInvoker.prepareImmediateMethodActivation, ProtosClosureInvoker.invokePrepared`
- A4a reference: `48153:150001:150000`, GraphTooBig=40
- Control: `50681:150026:150000`, GraphTooBig=40
- Boundary: `NONE`, GraphTooBig=0
- Hypothesis: **SUPPORTED**
- Reason: immediate-preparation boundary eliminated the A4a residual GraphTooBig
- Timing evidence: NO
- Protos repository changed: NO
