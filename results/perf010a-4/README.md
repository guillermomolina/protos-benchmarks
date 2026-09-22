# PERF010-A causal ablation (PERF010A_ABLATION_4, causal-duplicate-native-body-projection-ablation)

- Harness revision: `9cb377cec8f25cf6ed3db459d69dfa85c21f3f88`
- Protos revision (baseline and ablation; single checkout, patched in-build for the ablation image only): `4c4aa95a5852119bd280ceb40483871d5d2cbb82`
- Ablation patch: `docker/protos-perf010a/ablation-4.patch` (SHA256 `d796ef2b59ed0d35e250aeebfe7d1d0acf392b252085cad97cdd0d552592e903`); never applied to or published in `guillermomolina/protos`.
- Runtime (baseline): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Runtime (ablation): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- GraalVM release: `25.3.4.1`
- Container image: `ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825`
- CPU policy: cpuset-cpus=`0`; network disabled; no explicit memory limit.
- N=10,000. Warmup=20, steady=100.
- TIMING run: `Perf010aTimingDriver`, no JFR (steady-state wall-clock nanoseconds; median/MAD/p95/min/max derived from the retained raw per-iteration samples).
- STRUCTURAL run: `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (reused unmodified from `docker/protos-perf006d3`), steady-state-only JFR, bounded full call stacks (depth <= 32).

## Result

PERF010A_ABLATION_4 = VALID

Per workload:

| workload | PERF010A_ABLATION_4 | structural confirmed | baseline steady median (ns) | ablation steady median (ns) | removed (ns) | removed fraction of baseline |
|---|---|---|---|---|---|---|
| micro/slot-read | VALID | True | 48057331 | 50589520 | -2532190 | -0.0527 |
| micro/closure-call | VALID | True | 68856396 | 66070455 | 2785940 | 0.0405 |
| micro/method-call | VALID | True | 60225028 | 67064194 | -6839166 | -0.1136 |
| runtime/monomorphic-dispatch | VALID | True | 55869246 | 60807671 | -4938426 | -0.0884 |

## EXTERNAL_BASELINE_COST

`results/perf004-a` retains a same-workload cross-language (Python/JavaScript) steady-state baseline, but at a different Protos revision (`4a03efc15620b37b2e418b3df30b4a26486446ec`) and a different container base image (`ol8`, not this harness's `ol10`). Per `AGENTS.work/REPRODUCIBILITY.md`'s revision-pinning discipline, it is retained here only as a labelled historical reference and is **not** combined with this Evidence Unit's PROTOS_BASELINE_COST/PROTOS_ABLATION_COST into EXCESS_COST or ATTRIBUTABLE_FRACTION.

```
ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED
```

REMOVED_COST / baseline speedup per workload is reported above and does not require the external baseline. Establishing ATTRIBUTABLE_FRACTION requires a current-revision, current-host external (Python/JavaScript) measurement under this same Evidence Unit, which this reference run does not include.

## Continuations

None of the four workloads (`micro/slot-read`, `micro/closure-call`, `micro/method-call`, `runtime/monomorphic-dispatch`) suspend: they contain no I/O, actor messaging, or other operation that produces a `ContinuationResult`. `ProtosBytecodeTaskExecution`'s continuation-forwarding logic is generic over any `ContinuationResult`-returning `CallTarget` and does not itself branch on `ProtosSemanticBytecodeRootNode` vs. the bare helper root, so the ablation does not change observable continuation behavior for this measured experiment.

## Scope of the ablation

`ablation-4.patch` touches exactly one method: `ProtosBytecodeRootNode.finishPreparingComposedCall`. Its native branch currently projects `ProtosClosureValue.nativeBody()` twice - once for `closure.nativeBody().isPresent()`, once for `closure.nativeBody().orElseThrow()` - even though both projections observe the same value (`nativeBody()` is `Optional.ofNullable(nativeBody)` over a `final` field). The patch introduces a single local `java.util.Optional<ProtosNativeClosureBody> nativeBodyProjection = closure.nativeBody();` and reuses it for both the `isPresent()` check and the `orElseThrow()` projection, removing only the second, redundant call.

Every other `nativeBody()` call site in `ProtosBytecodeRootNode` (there are five: two `isPresent()`/`isEmpty()` pairs at two other call-preparation entry points, plus one more `isPresent()` check) is untouched, and `ProtosClosureValue.java` itself - including `nativeBody()`'s own `Optional.ofNullable(nativeBody)` body and the `nativeBody` field's `final` declaration - is not modified at all.

This transformation preserves the same native/source classification and the same `ProtosNativeClosureBody` reference on every call, so it is claimed to be semantically equivalent by construction, not diagnostic-only-and-expected-to-fail-closed like ablation 2. It does not change lookup, receiver/delegation, method binding, closure capture, arguments, activation identity, return home, errors, nonlocal return, continuations, RootTag/source/debugger identity, interop, or native execution.

Because both variants call the same fully-qualified `ProtosClosureValue.nativeBody()` method at the retained call site, a JFR-sampled-frame count cannot distinguish one call from two, so this ablation's structural confirmation is source-derived rather than JFR-derived, exactly like ablation 3: `source_structural_probe_4`/`structural_contract_confirmed_ablation_4` reads `/opt/protos-source` (the exact patched-or-unmodified source tree the image was built from) and confirms, as one per-image contract: the baseline image's `finishPreparingComposedCall` body calls `closure.nativeBody()` exactly twice with no `nativeBodyProjection` local; the ablation image's body calls it exactly once, reusing a single `nativeBodyProjection` local for both uses, carrying the `PERF010A_ABLATION_4` marker comment; the rest of `ProtosBytecodeRootNode.java` outside that one method body is byte-for-byte identical across both images; and `ProtosClosureValue.java` is byte-for-byte identical across both images.

`ProtosBytecodeRootNode.finishPreparingComposedCallByImplementation`, `ProtosActivation.java`, `ProtosValueLookup.java`, `CanonicalToBytecodeLowerer.java`, the RootTag topology, the continuation machinery, the `CallTarget` architecture, and source/debugger identity are all untouched by this patch. This is a diagnostic ablation, not (by itself) a production optimization change; per this slice's scope, no change is made to `guillermomolina/protos` regardless of this experiment's outcome. Never published to `guillermomolina/protos`.
