# PERF010-A causal ablation (PERF010A_ABLATION_2, causal-activation-lookup-ablation)

- Harness revision: `318e991b7c8bb21d01f24102b2ca03d549d546c6`
- Protos revision (baseline and ablation; single checkout, patched in-build for the ablation image only): `bc0471184bf6dbbf03d0c6b09ef7b9e28aede014`
- Ablation patch: `docker/protos-perf010a/ablation-2.patch` (SHA256 `4297f019c35cd8ac7725fedf92ea980d8974e4f9f17dd09bc223b0c4c47d4293`); never applied to or published in `guillermomolina/protos`.
- Runtime (baseline): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Runtime (ablation): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- GraalVM release: `25.3.4.1`
- Container image: `ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825`
- CPU policy: cpuset-cpus=`0`; network disabled; no explicit memory limit.
- N=10,000. Warmup=20, steady=100.
- TIMING run: `Perf010aTimingDriver`, no JFR (steady-state wall-clock nanoseconds; median/MAD/p95/min/max derived from the retained raw per-iteration samples).
- STRUCTURAL run: `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (reused unmodified from `docker/protos-perf006d3`), steady-state-only JFR, bounded full call stacks (depth <= 32).

## Result

PERF010A_ABLATION_2 = INVALID (see per-workload results below; at least one workload's structural ablation was not confirmed and/or failed correctness, so its timing is not interpreted as attributable to the ablated mechanism)

Per workload:

| workload | PERF010A_ABLATION_2 | structural confirmed | baseline steady median (ns) | ablation steady median (ns) | removed (ns) | removed fraction of baseline |
|---|---|---|---|---|---|---|
| micro/slot-read | INVALID | False | 46154014 | NA (correctness FAIL) | NA (correctness FAIL) | NA (correctness FAIL) |
| micro/closure-call | INVALID | False | 57418802 | NA (correctness FAIL) | NA (correctness FAIL) | NA (correctness FAIL) |
| micro/method-call | INVALID | False | 55776207 | NA (correctness FAIL) | NA (correctness FAIL) | NA (correctness FAIL) |
| runtime/monomorphic-dispatch | INVALID | False | 59249438 | NA (correctness FAIL) | NA (correctness FAIL) | NA (correctness FAIL) |

## Correctness failures

Per this slice's fail-closed contract, the diagnostic bypass was not adjusted to make any of the following pass; each is recorded here exactly as observed (`raw.json`'s `matrix[].variants.ablation[mode].execution_failure` carries the full, untruncated detail) and its workload is reported `INVALID` above with no timing claimed for the ablation variant.

- `micro/slot-read` (canonical, timing stage):
  ```
  timing failed micro__slot-read-ablation-canonical returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```
- `micro/slot-read` (control, timing stage):
  ```
  timing failed micro__slot-read-ablation-control returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```
- `micro/closure-call` (canonical, timing stage):
  ```
  timing failed micro__closure-call-ablation-canonical returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```
- `micro/closure-call` (control, timing stage):
  ```
  timing failed micro__closure-call-ablation-control returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```
- `micro/method-call` (canonical, timing stage):
  ```
  timing failed micro__method-call-ablation-canonical returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```
- `micro/method-call` (control, timing stage):
  ```
  timing failed micro__method-call-ablation-control returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```
- `runtime/monomorphic-dispatch` (canonical, timing stage):
  ```
  timing failed runtime__monomorphic-dispatch-ablation-canonical returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```
- `runtime/monomorphic-dispatch` (control, timing stage):
  ```
  timing failed runtime__monomorphic-dispatch-ablation-control returncode=1
  stdout:
  
  stderr:
  me/org.graalvm.truffle.truffle-runtime-25.3.4.1.jar)
  WARNING: Please consider reporting this to the maintainers of class com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime
  WARNING: sun.misc.Unsafe::objectFieldOffset will be removed in a future release
  Exception in thread "main" java.lang.IllegalStateException: standard Error taxonomy is unavailable before Core prelude bootstrap
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.lambda$requirePrelude$0(ProtosCoreErrors.java:55)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.requirePrelude(ProtosCoreErrors.java:54)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.prototype(ProtosCoreErrors.java:62)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newOccurrence(ProtosCoreErrors.java:70)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newSlotNotFound(ProtosCoreErrors.java:82)
  	at com.guillermomolina.protos.runtime.ProtosCoreErrors.newUnqualifiedLookupError(ProtosCoreErrors.java:90)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.lambda$perform$0(ProtosBytecodeRootNode.java:280)
  	at java.base/java.util.Optional.orElseThrow(Optional.java:403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$Lookup.perform(ProtosBytecodeRootNode.java:277)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$Lookup_Node.execute(ProtosBytecodeRootNodeGen.java:28454)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleLookup_(ProtosBytecodeRootNodeGen.java:6403)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5347)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callDirect(OptimizedCallTarget.java:573)
  	at com.oracle.truffle.runtime.OptimizedDirectCallNode.call(OptimizedDirectCallNode.java:94)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNode$EnterObjectConstruction.direct(ProtosBytecodeRootNode.java:530)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.executeAndSpecialize(ProtosBytecodeRootNodeGen.java:28836)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$EnterObjectConstruction_Node.execute(ProtosBytecodeRootNodeGen.java:28876)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.handleEnterObjectConstruction_(ProtosBytecodeRootNodeGen.java:6586)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen$CachedBytecodeNode.continueAt(ProtosBytecodeRootNodeGen.java:5399)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.continueAt(ProtosBytecodeRootNodeGen.java:2165)
  	at com.guillermomolina.protos.execution.ProtosBytecodeRootNodeGen.execute(ProtosBytecodeRootNodeGen.java:2157)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.executeRootNode(OptimizedCallTarget.java:808)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:722)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.callBoundary(OptimizedCallTarget.java:641)
  	at com.oracle.truffle.runtime.OptimizedCallTarget.doInvoke(OptimizedCallTarget.java:625)
  ```

## EXTERNAL_BASELINE_COST

`results/perf004-a` retains a same-workload cross-language (Python/JavaScript) steady-state baseline, but at a different Protos revision (`4a03efc15620b37b2e418b3df30b4a26486446ec`) and a different container base image (`ol8`, not this harness's `ol10`). Per `AGENTS.work/REPRODUCIBILITY.md`'s revision-pinning discipline, it is retained here only as a labelled historical reference and is **not** combined with this Evidence Unit's PROTOS_BASELINE_COST/PROTOS_ABLATION_COST into EXCESS_COST or ATTRIBUTABLE_FRACTION.

```
ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED
```

REMOVED_COST / baseline speedup per workload is reported above and does not require the external baseline. Establishing ATTRIBUTABLE_FRACTION requires a current-revision, current-host external (Python/JavaScript) measurement under this same Evidence Unit, which this reference run does not include.

## Continuations

None of the four workloads (`micro/slot-read`, `micro/closure-call`, `micro/method-call`, `runtime/monomorphic-dispatch`) suspend: they contain no I/O, actor messaging, or other operation that produces a `ContinuationResult`. `ProtosBytecodeTaskExecution`'s continuation-forwarding logic is generic over any `ContinuationResult`-returning `CallTarget` and does not itself branch on `ProtosSemanticBytecodeRootNode` vs. the bare helper root, so the ablation does not change observable continuation behavior for this measured experiment.

## Scope of the ablation

`ProtosBytecodeRootNode.Lookup.perform` (the unqualified-name-lookup Bytecode operation) is the single call site bypassed by `ablation-2.patch`: `activation.lookup(name)` (activation's own local context, then captured lexical contexts, then the receiver/prelude member fallback - `ProtosActivation.lookup(String)`) is replaced with `activation.context().readLocalSlot(name)` (`ProtosObjectValue.readLocalSlot`), reading only the activation's own local context slot directly.

This diagnostic bypass is **not** claimed to be semantically equivalent to `activation.lookup(name)` in the general language: it silently drops the captured-lexical-context walk and the receiver/prelude member fallback that `lookup` performs for any name not bound as a direct local slot of the activation's own context. It is expected to fail closed (a `ProtosSignalException` from the unchanged `orElseThrow(...)` below the bypass, surfacing as a non-`COMPLETED` execution outcome and a driver-level correctness failure) for any workload whose unqualified-name lookups are not resolved by the activation's own local context - which is the case for all four PERF010-A workloads' hot-path references to their top-level module bindings (`repeat`, `sink`, `holder`, `identity`, `receiver`), captured into each closure's `capturedLexicalContexts` rather than its own fresh, per-invocation `context`. Per `AGENTS.work/PERFORMANCE.md`'s and this slice's own correctness-before-timing rule, a workload that fails this way contributes no timing evidence and is reported `INVALID`, not adjusted to pass.

`ProtosBytecodeRootNode`, `CanonicalToBytecodeLowerer`, the RootTag topology, the continuation machinery, the `CallTarget` architecture, and source/debugger identity are all untouched by this patch. This is a diagnostic ablation, not a production optimization candidate. Never published to `guillermomolina/protos`.
