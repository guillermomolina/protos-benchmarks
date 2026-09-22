# PERF010-A causal ablation (PERF010A_ABLATION_3, causal-lexical-slot-read-ablation)

- Harness revision: `de3a4acbd2b1bfbb9e9b4d762e8d44bb2be269d6`
- Protos revision (baseline and ablation; single checkout, patched in-build for the ablation image only): `6e7d89194925ba9fa2cd9c5c45aefa72d9939621`
- Ablation patch: `docker/protos-perf010a/ablation-3.patch` (SHA256 `9a53e3a0209463696b6d5495e948ce57ef7054982f19a3a873f32c0d1c67537a`); never applied to or published in `guillermomolina/protos`.
- Runtime (baseline): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Runtime (ablation): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- GraalVM release: `25.3.4.1`
- Container image: `ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825`
- CPU policy: cpuset-cpus=`0`; network disabled; no explicit memory limit.
- N=10,000. Warmup=20, steady=100.
- TIMING run: `Perf010aTimingDriver`, no JFR (steady-state wall-clock nanoseconds; median/MAD/p95/min/max derived from the retained raw per-iteration samples).
- STRUCTURAL run: `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (reused unmodified from `docker/protos-perf006d3`), steady-state-only JFR, bounded full call stacks (depth <= 32).

## Result

PERF010A_ABLATION_3 = INVALID (see per-workload results below; at least one workload's structural ablation was not confirmed and/or failed correctness, so its timing is not interpreted as attributable to the ablated mechanism)

Per workload:

| workload | PERF010A_ABLATION_3 | structural confirmed | baseline steady median (ns) | ablation steady median (ns) | removed (ns) | removed fraction of baseline |
|---|---|---|---|---|---|---|
| micro/slot-read | INVALID | False | 47121852 | 44623480 | 2498373 | 0.0530 |
| micro/closure-call | INVALID | False | 56038634 | 60252002 | -4213368 | -0.0752 |
| micro/method-call | INVALID | False | 60865152 | 57166836 | 3698316 | 0.0608 |
| runtime/monomorphic-dispatch | INVALID | False | 54491520 | 52069492 | 2422028 | 0.0444 |

## EXTERNAL_BASELINE_COST

`results/perf004-a` retains a same-workload cross-language (Python/JavaScript) steady-state baseline, but at a different Protos revision (`4a03efc15620b37b2e418b3df30b4a26486446ec`) and a different container base image (`ol8`, not this harness's `ol10`). Per `AGENTS.work/REPRODUCIBILITY.md`'s revision-pinning discipline, it is retained here only as a labelled historical reference and is **not** combined with this Evidence Unit's PROTOS_BASELINE_COST/PROTOS_ABLATION_COST into EXCESS_COST or ATTRIBUTABLE_FRACTION.

```
ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED
```

REMOVED_COST / baseline speedup per workload is reported above and does not require the external baseline. Establishing ATTRIBUTABLE_FRACTION requires a current-revision, current-host external (Python/JavaScript) measurement under this same Evidence Unit, which this reference run does not include.

## Continuations

None of the four workloads (`micro/slot-read`, `micro/closure-call`, `micro/method-call`, `runtime/monomorphic-dispatch`) suspend: they contain no I/O, actor messaging, or other operation that produces a `ContinuationResult`. `ProtosBytecodeTaskExecution`'s continuation-forwarding logic is generic over any `ContinuationResult`-returning `CallTarget` and does not itself branch on `ProtosSemanticBytecodeRootNode` vs. the bare helper root, so the ablation does not change observable continuation behavior for this measured experiment.

## Scope of the ablation

`ProtosObjectValue.readLocalSlot` (called from `ProtosActivation.lookup`'s own local context and captured-lexical-context walk, and from many other production call sites throughout the codebase) is the single method transformed by `ablation-3.patch`: the redundant `localSlots.containsKey(name)` probe followed by a second `localSlots.get(name)` read is replaced with a single `localSlots.get(name)`, discriminating ABSENT from any stored value via `localSlots`' own invariant that no local slot value is ever null (`createLocalSlot`/`assignLocalSlot` both require `Objects.requireNonNull(value, ...)`; `composeLocalSlotsFrom` only copies values already subject to that invariant from another `ProtosObjectValue`).

Unlike ablations 1 and 2, this is **not** a call-site bypass: `readLocalSlot` is called from exactly the same sites, in exactly the same order, with exactly the same fully-qualified name, in both variants. `ProtosActivation.lookup`'s local-context-then-captured-lexical-contexts-then-receiver/prelude-fallback traversal, lexical precedence, shadowing, and missing-name behavior are all untouched by this patch (`ProtosActivation.java` is not one of `ablation-3.patch`'s targets). This transformation is therefore claimed to be semantically equivalent by construction, not diagnostic-only-and-expected-to-fail-closed like ablation 2.

Because `readLocalSlot`'s call sites and frame name are unchanged, this ablation's structural confirmation is source-derived rather than JFR-derived: `java.util.LinkedHashMap.containsKey`/`get` are simple enough to be JIT-inlined and are not a reliable sampled-frame signal either way. `source_structural_probe` reads `/opt/protos-source` (the exact patched-or-unmodified source tree the image was built from) and confirms, scoped to `readLocalSlot`'s own method body: the diagnostic marker comment is present, the redundant `containsKey` probe is absent, the single `get(name)` read is present (ablation variant only), and `ProtosActivation.lookup`'s captured-lexical-context traversal loop is present, byte-for-byte unchanged, in both variants.

`ProtosActivation.java`, `ProtosBytecodeRootNode.java`, `CanonicalToBytecodeLowerer.java`, the RootTag topology, the continuation machinery, the `CallTarget` architecture, and source/debugger identity are all untouched by this patch. This is a diagnostic ablation, not (by itself) a production optimization change; per this slice's scope, no change is made to `guillermomolina/protos` regardless of this experiment's outcome. Never published to `guillermomolina/protos`.
