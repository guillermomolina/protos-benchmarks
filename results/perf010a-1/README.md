# PERF010-A causal semantic/helper-dispatch ablation

- Harness revision: `3244101cf8c61c94ea5f3a165851a02e5f1870dd`
- Protos revision (baseline and ablation; single checkout, patched in-build for the ablation image only): `bc0471184bf6dbbf03d0c6b09ef7b9e28aede014`
- Ablation patch: `docker/protos-perf010a/ablation.patch` (SHA256 `3ee971366edf8dc2e3cf5d6c1dfc2885a8edc1258b76ab674ac12b567ba3dc79`); never applied to or published in `guillermomolina/protos`.
- Runtime (baseline): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Runtime (ablation): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- GraalVM release: `25.3.4.1`
- Container image: `ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825`
- CPU policy: cpuset-cpus=`0`; network disabled; no explicit memory limit.
- N=10,000. Warmup=20, steady=100.
- TIMING run: `Perf010aTimingDriver`, no JFR (steady-state wall-clock nanoseconds; median/MAD/p95/min/max derived from the retained raw per-iteration samples).
- STRUCTURAL run: `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (reused unmodified from `docker/protos-perf006d3`), steady-state-only JFR, bounded full call stacks (depth <= 32).

## Result

PERF010A_ABLATION_1 = VALID

Per workload:

| workload | PERF010A_ABLATION_1 | structural confirmed | baseline steady median (ns) | ablation steady median (ns) | removed (ns) | removed fraction of baseline |
|---|---|---|---|---|---|---|
| micro/slot-read | VALID | True | 48557167 | 47094106 | 1463061 | 0.0301 |
| micro/closure-call | VALID | True | 58985733 | 55436564 | 3549169 | 0.0602 |
| micro/method-call | VALID | True | 58744288 | 56920628 | 1823660 | 0.0310 |
| runtime/monomorphic-dispatch | VALID | True | 56311082 | 53793518 | 2517564 | 0.0447 |

## EXTERNAL_BASELINE_COST

`results/perf004-a` retains a same-workload cross-language (Python/JavaScript) steady-state baseline, but at a different Protos revision (`4a03efc15620b37b2e418b3df30b4a26486446ec`) and a different container base image (`ol8`, not this harness's `ol10`). Per `AGENTS.work/REPRODUCIBILITY.md`'s revision-pinning discipline, it is retained here only as a labelled historical reference and is **not** combined with this Evidence Unit's PROTOS_BASELINE_COST/PROTOS_ABLATION_COST into EXCESS_COST or ATTRIBUTABLE_FRACTION.

```
ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED
```

REMOVED_COST / baseline speedup per workload is reported above and does not require the external baseline. Establishing ATTRIBUTABLE_FRACTION requires a current-revision, current-host external (Python/JavaScript) measurement under this same Evidence Unit, which this reference run does not include.

## Continuations

None of the four workloads (`micro/slot-read`, `micro/closure-call`, `micro/method-call`, `runtime/monomorphic-dispatch`) suspend: they contain no I/O, actor messaging, or other operation that produces a `ContinuationResult`. `ProtosBytecodeTaskExecution`'s continuation-forwarding logic is generic over any `ContinuationResult`-returning `CallTarget` and does not itself branch on `ProtosSemanticBytecodeRootNode` vs. the bare helper root, so the ablation does not change observable continuation behavior for this measured experiment.

## Scope of the ablation

The semantic/helper wrapper (`ProtosSemanticBytecodeRootNode.wrap(...)`) is created at two call sites, both bypassed by `ablation.patch`:

1. `ProtosSourceCompiler.compileBytecode` - the top-level module/program root (executed once per process in these workloads).
2. `ProtosBytecodeClosureExecutionPlan`'s constructor - the activation root for every closure and method value (`repeat`, `operation`, `identity`, `receiver.identity`, `receiver.run`), which is what the 10,000-iteration hot loop actually calls repeatedly in all four workloads. Ablating only the top-level compiler entry point would leave this call site - and therefore the measured hot path - unchanged; both were confirmed present in the pinned revision before the patch was written (see `docker/protos-perf010a/ablation.patch` inline comments).

`ProtosRootTaskExecution.isProductionBytecodeRoot` is widened to accept the bare helper `ProtosBytecodeRootNode` in addition to the semantic wrapper; without this, every root-task execution in the ablation build throws `IllegalArgumentException` before producing any result, since compiled roots stop being `ProtosSemanticBytecodeRootNode` instances. `ProtosBytecodeRootNode` and `CanonicalToBytecodeLowerer` themselves are untouched.

This is a diagnostic ablation, not a production optimization candidate; it is acceptable (and expected) that the ablation build loses the RootTag the semantic shell provides. Never published to `guillermomolina/protos`.
