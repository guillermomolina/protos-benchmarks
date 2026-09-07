# PERF003-A4d controlled immediate-activation boundary experiment

- Harness revision: `06a5620a94e6cee95134d95bc22b1424c077e3c8`
- A4d1 revision: `06a5620a94e6cee95134d95bc22b1424c077e3c8`
- Execution base: `06a5620a94e6cee95134d95bc22b1424c077e3c8`
- Protos revision: `d66841adb0b820047ed079f0bc7d643873f23194`
- Workload: `collections/array-reduce`
- Expected result: `528`
- Diagnostic iterations: 20
- Experimental boundary: `ProtosActivation.forImmediateMethodInvocation`
- Control GraphTooBig: 40
- Control graph shapes: `50681:150026:150000`
- Boundary GraphTooBig: 40
- Boundary graph shapes: `50562:150051:150000`
- Hypothesis: **INCONCLUSIVE**
- Reason: immediate-activation boundary changed diagnostics without a directional result
- Timing evidence: NO
- Protos repository changed: NO

This is controlled falsification evidence. A supported result attributes material graph growth to immediate-method activation construction; it does not by itself justify a production TruffleBoundary or semantic/runtime change.
