# PERF010-A causal ablation (PERF010A_ABLATION_3, causal-lexical-slot-read-ablation)

- Harness revision: `fd22a347d24b2d3ae697846a5679c4dbd2a1e8bf`
- Protos revision (baseline and ablation; single checkout, patched in-build for the ablation image only): `6e7d89194925ba9fa2cd9c5c45aefa72d9939621`
- Ablation patch: `docker/protos-perf010a/ablation-3.patch` (SHA256 `f376123a1bcf5aa6de4163e8740ea9cf8f3d99e7f47aa9a146a5b91dc36169a9`); never applied to or published in `guillermomolina/protos`.
- Runtime (baseline): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Runtime (ablation): `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- GraalVM release: `25.3.4.1`
- Container image: `ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825`
- CPU policy: cpuset-cpus=`0`; network disabled; no explicit memory limit.
- N=10,000. Warmup=20, steady=100.
- TIMING run: `Perf010aTimingDriver`, no JFR (steady-state wall-clock nanoseconds; median/MAD/p95/min/max derived from the retained raw per-iteration samples).
- STRUCTURAL run: `Perf008SteadyStateDriver` + `Perf006d3JfrAnalyzer` (reused unmodified from `docker/protos-perf006d3`), steady-state-only JFR, bounded full call stacks (depth <= 32).

## Result

PERF010A_ABLATION_3 = VALID

Per workload:

| workload | PERF010A_ABLATION_3 | structural confirmed | baseline steady median (ns) | ablation steady median (ns) | removed (ns) | removed fraction of baseline |
|---|---|---|---|---|---|---|
| micro/slot-read | VALID | True | 46977712 | 45813334 | 1164378 | 0.0248 |
| micro/closure-call | VALID | True | 55228029 | 54478524 | 749506 | 0.0136 |
| micro/method-call | VALID | True | 54948155 | 53993482 | 954672 | 0.0174 |
| runtime/monomorphic-dispatch | VALID | True | 55123283 | 55378282 | -254998 | -0.0046 |

## EXTERNAL_BASELINE_COST

`results/perf004-a` retains a same-workload cross-language (Python/JavaScript) steady-state baseline, but at a different Protos revision (`4a03efc15620b37b2e418b3df30b4a26486446ec`) and a different container base image (`ol8`, not this harness's `ol10`). Per `AGENTS.work/REPRODUCIBILITY.md`'s revision-pinning discipline, it is retained here only as a labelled historical reference and is **not** combined with this Evidence Unit's PROTOS_BASELINE_COST/PROTOS_ABLATION_COST into EXCESS_COST or ATTRIBUTABLE_FRACTION.

```
ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED
```

REMOVED_COST / baseline speedup per workload is reported above and does not require the external baseline. Establishing ATTRIBUTABLE_FRACTION requires a current-revision, current-host external (Python/JavaScript) measurement under this same Evidence Unit, which this reference run does not include.

## Continuations

None of the four workloads (`micro/slot-read`, `micro/closure-call`, `micro/method-call`, `runtime/monomorphic-dispatch`) suspend: they contain no I/O, actor messaging, or other operation that produces a `ContinuationResult`. `ProtosBytecodeTaskExecution`'s continuation-forwarding logic is generic over any `ContinuationResult`-returning `CallTarget` and does not itself branch on `ProtosSemanticBytecodeRootNode` vs. the bare helper root, so the ablation does not change observable continuation behavior for this measured experiment.

## Scope of the ablation

`ablation-3.patch` adds a new diagnostic-only `ProtosObjectValue.readLocalSlotSingleProbe` helper (a single `localSlots.get(name)`, discriminating ABSENT from any stored value via `localSlots`' own invariant that no local slot value is ever null - `createLocalSlot`/`assignLocalSlot` both require `Objects.requireNonNull(value, ...)`; `composeLocalSlotsFrom` only copies values already subject to that invariant from another `ProtosObjectValue`) and redirects **exactly** the two lexical local-slot-read call sites inside `ProtosActivation.lookup` - the current activation context, then each captured lexical context in `capturedLexicalContexts` - to it. The ordinary `ProtosObjectValue.readLocalSlot` method (its redundant `containsKey(name)` + `get(name)` probe-then-read) is **not** modified and stays byte-for-byte unchanged; it remains the path used by every other caller, including `ProtosValueLookup`'s receiver/delegation member lookup (the fallback `ProtosActivation.lookup` reaches via `ProtosValueLookup.readMember` when neither lexical position resolves the name) and every interop/other production call site.

This is narrower than an earlier, invalid execution of this same slice, which instead transformed `readLocalSlot`'s own body globally - changing every caller, not just the two established lexical call sites - and was rejected by this harness's exact-scope validation (`ABLATION_3_PATCH_SCOPE_MATCH`) as measuring more than the established causal component, even though it was semantically equivalent by construction. That invalid attempt is retained as historical evidence of an invalid intent, not as a valid measurement.

Unlike ablations 1 and 2, this is **not** a call-site bypass in the sense of dropping a step: `ProtosActivation.lookup`'s local-context-then-captured-lexical-contexts-then-receiver/prelude-fallback traversal, lexical precedence, shadowing, and missing-name behavior are all preserved, in the same order, in both variants - only which `ProtosObjectValue` reader method the two lexical positions call differs. This transformation is therefore claimed to be semantically equivalent by construction, not diagnostic-only-and-expected-to-fail-closed like ablation 2.

Because both variants still call a `ProtosObjectValue` reader method with a resolvable frame name at the same call sites, and `java.util.LinkedHashMap.containsKey`/`get` are simple enough to be JIT-inlined, this ablation's structural confirmation is source-derived rather than JFR-derived: `source_structural_probe`/`structural_contract_confirmed_ablation_3` reads `/opt/protos-source` (the exact patched-or-unmodified source tree the image was built from) and confirms, as one per-image contract: the diagnostic helper exists only in the ablation image; `readLocalSlot`'s own body is byte-for-byte identical across both images; the diagnostic helper is called at both of `ProtosActivation.lookup`'s lexical positions in the ablation image and ordinary `readLocalSlot` is called at those same two positions in the baseline image; the captured-lexical-context traversal loop and the `ProtosValueLookup` fallback are present, unchanged, in both; and `ProtosValueLookup`'s own receiver/delegation member-lookup call site still calls ordinary `readLocalSlot` in both images.

`ProtosBytecodeRootNode.java`, `CanonicalToBytecodeLowerer.java`, the RootTag topology, the continuation machinery, the `CallTarget` architecture, and source/debugger identity are all untouched by this patch. This is a diagnostic ablation, not (by itself) a production optimization change; per this slice's scope, no change is made to `guillermomolina/protos` regardless of this experiment's outcome. Never published to `guillermomolina/protos`.
