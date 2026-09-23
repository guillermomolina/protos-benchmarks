# PERF010-A causal ablation (PERF010A_GUARDED_CALL, causal-guarded-monomorphic-composed-send-experiment)

- Harness revision: `3275c108aa9b04d35a67fbe9be1c13e6fe94c58a`
- Protos revision (baseline and ablation; single checkout, patched in-build for the ablation image only): `2b3a88389da7228caed231a90b14091cf2841115`
- Ablation patch: `docker/protos-perf010a/guarded-call.patch` (SHA256 `a1845b3125abd80631e9d201c09359a43b4fdb4088a74b242fb0484e0c38f83c`); never applied to or published in `guillermomolina/protos`.
- Runtime (baseline): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Runtime (ablation): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- GraalVM release: `25.3.4.1`
- Container image: `ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825`
- CPU policy: cpuset-cpus=`0`; network disabled; no explicit memory limit.
- N=10,000. Warmup=20, steady=100.
- TIMING run: `Perf010aTimingDriver`, no JFR (steady-state wall-clock nanoseconds; median/MAD/p95/min/max derived from the retained raw per-iteration samples).
- STRUCTURAL run: `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (reused unmodified from `docker/protos-perf006d3`), steady-state-only JFR, bounded full call stacks (depth <= 32).

## Result

PERF010A_GUARDED_CALL = VALID

Per workload:

| workload | PERF010A_GUARDED_CALL | structural confirmed | baseline steady median (ns) | ablation steady median (ns) | removed (ns) | removed fraction of baseline |
|---|---|---|---|---|---|---|
| micro/slot-read | VALID | True | 51800017 | 50674566 | 1125450 | 0.0217 |
| micro/closure-call | VALID | True | 66624690 | 65610295 | 1014396 | 0.0152 |
| micro/method-call | VALID | True | 54676845 | 59768788 | -5091943 | -0.0931 |
| runtime/monomorphic-dispatch | VALID | True | 53004841 | 57091641 | -4086800 | -0.0771 |

## EXTERNAL_BASELINE_COST

`results/perf004-a` retains a same-workload cross-language (Python/JavaScript) steady-state baseline, but at a different Protos revision (`4a03efc15620b37b2e418b3df30b4a26486446ec`) and a different container base image (`ol8`, not this harness's `ol10`). Per `AGENTS.work/REPRODUCIBILITY.md`'s revision-pinning discipline, it is retained here only as a labelled historical reference and is **not** combined with this Evidence Unit's PROTOS_BASELINE_COST/PROTOS_ABLATION_COST into EXCESS_COST or ATTRIBUTABLE_FRACTION.

```
ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED
```

REMOVED_COST / baseline speedup per workload is reported above and does not require the external baseline. Establishing ATTRIBUTABLE_FRACTION requires a current-revision, current-host external (Python/JavaScript) measurement under this same Evidence Unit, which this reference run does not include.

## Continuations

None of the four workloads (`micro/slot-read`, `micro/closure-call`, `micro/method-call`, `runtime/monomorphic-dispatch`) suspend: they contain no I/O, actor messaging, or other operation that produces a `ContinuationResult`. `ProtosBytecodeTaskExecution`'s continuation-forwarding logic is generic over any `ContinuationResult`-returning `CallTarget` and does not itself branch on `ProtosSemanticBytecodeRootNode` vs. the bare helper root, so the ablation does not change observable continuation behavior for this measured experiment.

## Scope of the guarded-call experiment

`guarded-call.patch` touches exactly one file, `ProtosBytecodeRootNode.java`, and is almost purely additive: it adds one new leading `@Specialization` (`performGuardedOrdinaryComposedSend`) to the `PrepareSendArguments` Operation - the constant-selector, ordinary composed-send Bytecode operation reached from a plain `receiver.selector(args)` send - plus three new private helper methods. The pre-existing single specialization, `perform`, keeps its exact body and becomes a `@Specialization(replaces = "performGuardedOrdinaryComposedSend")` fallback; the only removed line in the whole patch is its bare `@Specialization` annotation.

The new specialization's guard re-runs the exact authoritative `ProtosValueLookup.lookup(receiver, selector, prelude)` call on every single invocation (three independent call sites in the new helpers), so D013 lookup itself is unmodified and a slot replacement, removal, or delegation change is always observed before the guard is trusted. The guard only takes the fast arm when that fresh lookup still selects the exact same (Closure identity, methodHome identity) pair this call site cached, and it only ever caches a Closure whose `nativeBody()` is empty (a `final` field, so this fact never changes for a given Closure instance).

On a hit it reuses `ProtosActivation.forImmediateMethodInvocation` and `attachTaskOrInheritDynamicControlState` exactly as the generic path (`prepareImmediateMethodCall`) already does, resolves the effective Bytecode execution plan via the pre-existing, unmodified `taskOwnedBytecodePlan` helper - the same helper the retained `prepareTaskOwnedSelectedCallIfBytecode` precedent already uses in production for the Task-owned path - and either builds the `PreparedClosureCall` directly, bypassing `finishPreparingComposedCallByImplementation`'s 16 implementation/category classifiers and the subsequent 19 structured-dispatch predicates, or falls back to that exact, unmodified method when the plan cannot be resolved (a source-less context-local projection). Skipping those classifiers is provably safe rather than merely likely safe: `finishPreparingComposedCall`'s own structured-flags branch already requires every one of them to be false whenever the selected Closure is non-native, which is the only case this specialization ever caches. A guard miss - a different Closure/methodHome, a native Closure, or a lookup failure - falls through to the unchanged `perform` specialization, i.e. the exact current generic path.

`ProtosStandardImportProtocol.selectedRuntimeForBytecodeIntrinsic`'s check (run by the generic path before this experiment's target, `prepareImmediateMethodCall`) can only select a non-null runtime when the selected Closure's `nativeBody()` is present and holds a `StandardImportBody`; since this specialization only ever caches a Closure whose `nativeBody()` is empty, that check is provably unreachable (always null) for any Closure the fast arm can take, so omitting it changes no observable behavior.

`ProtosActivation.java`, `ProtosClosureValue.java`, `ProtosObjectValue.java`, `ProtosValueLookup.java`, `CanonicalToBytecodeLowerer.java`, the RootTag topology, the continuation machinery, the `CallTarget` architecture, and source/debugger identity are all untouched by this patch. This is a diagnostic causal experiment, not (by itself) a production optimization change; per this slice's scope, no change is made to `guillermomolina/protos` regardless of this experiment's outcome. Never published to `guillermomolina/protos`.

Because the new specialization method exists only in the guarded image's source (the baseline image's `PrepareSendArguments` class has exactly one, byte-for-byte unchanged, `perform` specialization), structural confirmation is source-derived, like ablations 3/4: `source_structural_probe_guarded`/`structural_contract_confirmed_guarded` reads `/opt/protos-source` and confirms, as one per-image contract, that the guarded image's `PrepareSendArguments` class contains `performGuardedOrdinaryComposedSend` and the `PERF010A_GUARDED_CALL` marker, that the baseline image's `PrepareSendArguments` class does not, and that the rest of `ProtosBytecodeRootNode.java` is byte-for-byte identical between the two images.
