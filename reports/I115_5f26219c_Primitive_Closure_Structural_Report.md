# I115 — `primitive-closure-call` Structural Report at `5f26219c`

**Campaign date:** 2 November 2026  
**Measured product:** [`guillermomolina/protos` `5f26219c06bb8ea382da28eaf56dfefbfbf752ab`](https://github.com/guillermomolina/protos/commit/5f26219c06bb8ea382da28eaf56dfefbfbf752ab) (`I115`; product version `0.3.403-SNAPSHOT`)  
**Harness:** [`guillermomolina/protos-benchmarks` `20855fe29e8ec7bf274e3f22b78d0b733b3e9bb3`](https://github.com/guillermomolina/protos-benchmarks/commit/20855fe29e8ec7bf274e3f22b78d0b733b3e9bb3)  
**Workload:** `primitive-closure-call`, Protos **only**, `canonical` surface, expected result `1`  
**Compilation graph phase:** `After TruffleTier`  
**Historical comparators:** [I115-C6 published report](https://github.com/guillermomolina/protos-benchmarks/blob/main/reports/I115-C6_Structural_Report.md), GraalPy 25.4.4.1.1 (existing measurement only; no new GraalPy execution)  
**Excluded:** timings, throughput, other workloads/languages, and any remeasurement of GraalPy.

> **Purpose.** Determine the structural status of the I115 `run` root after the root/context lookup changes, at a fixed product SHA, retaining separate evidence for bytecode execution, cold Tier 1/2 roots, and the stabilized Tier 2 guest-root metric. Node counts are not speed measurements. The C6/GraalPy observations are historical comparator values, **not** observations from this producer.

## 1. Executive findings

1. **The stabilized guest `run` graph is 340 nodes**, one valid Tier 2 language-owned unit, versus **193** in Protos C6 (**+147; +76.2%**) and **50** in historical GraalPy (**+290; +580%**). Stabilization agrees structurally at reference budgets 16,000 and 64,000; the correct guest result was `1`.
2. **Two Java call targets survive** in the 340-node `run` graph: `ProtosLanguageContext.existingBytecodeExecutionPlan` and `ProtosLanguageContext.bytecodeExecutionPlanForDefinitionMiss` (one each). The C6 stable graph contained one distinct residual target: `ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate`. Thus the residual call path has changed, but the presence of a target does not prove that it executes in the steady-state normal branch.
3. **The DSL call opcode has changed:** in C6, `CallUnaryMethod` executed 5 times and `CallUnaryMethod$CallPFunction` 96 times; the current `run` root records `CallUnaryMethod` **101 times**, with **no** `$CallPFunction` specialization reported. This demonstrates a diagnostic opcode/quickening difference; it does **not** by itself prove that the nested Truffle DSL call dispatcher was unspecialized or indirect.
4. **The `run` bytecode is larger:** 132 bytes / 36 static instructions versus C6's 106 bytes / 28. The `identity` bytecode remains 70 bytes / 18 instructions. Dynamic `run` execution expands from 1,212 to 1,616 instruction executions, while `identity` remains 707.
5. The independently collected cold census contains three compiled targets in both Tiers with no unavailable roots. The structural generator calls the tier-to-tier pairing **COMPLETE** and producer-compatible; Java physical identity across *different* JVMs is not implied.

## 2. Identity, correctness and evidence admission

| Field | Verified value |
|---|---|
| Product commit | `5f26219c06bb8ea382da28eaf56dfefbfbf752ab` |
| Product source-state SHA-256 | `bb265beaaaec8374ab0f0302c76b583f182abf11d062968c0698230fad7568ea` |
| Harness commit | `20855fe29e8ec7bf274e3f22b78d0b733b3e9bb3` |
| Product and harness clean before/after captures | **YES** |
| Workload source SHA-256 | `60c558345a43a5283e8f7ac95b518fed14d80164e52e1b907b83fb4c432d2ed4` (same in DSL and reference; also in cold producer manifests) |
| Product version recorded | `0.3.403-SNAPSHOT` (version label only; commit SHA is authoritative) |
| GraalVM / Java runtime | GraalVM CE `25.4.4.1.1`; Java `25.0.4.1.1+1-jvmci-25.4-b23` |
| Host CPU | `Intel(R) Xeon(R) Platinum 8362 CPU @ 2.80GHz`; x86_64, affinity CPU `0` |
| Kernel | `7.2.14-arch1-1` |
| Reference surface / result | `canonical` / `PASS`, actual `1` |
| Cold capture Tier 1 / Tier 2 | `capture_valid=true` / `true`, 3 compiled roots each, 0 unavailable |
| Interpreter bytecode diagnostic | `capture_valid=true`; histogram and bytecode-size observations available |
| Stable reference | `evidence_valid=true`; `STABLE`, budgets `16,000` / `64,000`, selected Tier `2` |
| Generated structural pairing | `COMPLETE`, pairing `COMPLETE`; compatible producer identities |
| Scope | Observed compiled call targets; full interpreted-root coverage **not established** |
| Timing evidence | **NONE** |

The input archive contains eight derived JSON records, not their referenced raw `.bgv.gz` and interpreter log artifacts; its embedded checks and analysis statuses are verified, but BGV graphs were **not independently re-parsed here**. The source archive SHA-256 is `0dd0f02ac0e9a47c8f10f5b20b1b9d7c05579429e78773f8c1b97c495ddc27f2`. Raw graphs and logs remain in the user's existing harness output directories.

## 3. Comparable stabilized Tier 2 reference

| Producer | `run` Tier 2 nodes | Current I115 difference |
| --- | --- | --- |
| Protos H10 (historical) | 106 | +234 vs H10 |
| Protos C6 (historical) | 193 | +147 vs C6 |
| Protos I115 `5f26219c06bb` | 340 | current |
| GraalPy 25.4.4.1.1 (historical) | 50 | +290 current vs Py |

The **340-node** selected graph is the *single guest primary compilation* (`ProtosBytecodeRootNodeGen@292b965c`, compilation id `2813`). The historical C6 metric similarly selects one guest unit (193); do not add current `identity` (123) or the host Polyglot adapter (939) to the 340-node metric. The historical GraalPy `run` value (50) is reused from the C6 comparison, without rerunning GraalPy or inventing a current GraalPy histogram.

### 3.1 Selected-class breakdown of `run`: I115-C6 vs current I115

The C6 column below contains **only the classes explicitly enumerated** in the published C6 report; missing C6 classes in the companion full CSV must not be assumed zero. The complete current node histogram is supplied in the accompanying CSV and Appendix A.

| Graal node class | C6 (published subset) | Current | Delta |
| --- | --- | --- | --- |
| `ConstantNode` | 32 | 44 | +12 |
| `FrameState` | 29 | 58 | +29 |
| `BeginNode` | 11 | 34 | +23 |
| `EndNode` | 10 | 25 | +15 |
| `IfNode` | 5 | 16 | +11 |
| `FixedGuardNode` | 11 | 11 | 0 |
| `DeoptimizeNode` | 1 | 2 | +1 |
| `VirtualObjectState` | 11 | 20 | +9 |
| `VirtualArrayNode` | 4 | 8 | +4 |
| `VirtualInstanceNode` | 3 | 5 | +2 |
| `PiNode` | 10 | 18 | +8 |
| `LoadFieldNode` | 13 | 18 | +5 |
| `LoadIndexedNode` | 5 | 5 | 0 |
| `AllocatedObjectNode` | 2 | 2 | 0 |
| `CommitAllocationNode` | 2 | 2 | 0 |
| `InvokeWithExceptionNode` | 1 | 2 | +1 |
| `MethodCallTargetNode` | 1 | 2 | +1 |
| `ExceptionObjectNode` | 1 | 2 | +1 |
| `StateSplitProxyNode` | 5 | 4 | -1 |
| `ValuePhiNode` | 4 | 7 | +3 |
| `InstanceOfNode` | 2 | 2 | 0 |
| `BoxNode$AllocatingBoxNode` | 1 | 1 | 0 |

The selected changes include +29 `FrameState`, +23 `BeginNode`, +15 `EndNode`, +11 `IfNode`, +9 `VirtualObjectState`, +8 `PiNode`, and +5 `LoadFieldNode`. They describe the resulting graph shape but cannot be causally attributed to one helper or one branch on the basis of counts alone.

### 3.2 Current `run` residual Java invocation targets

| Invoke target | Recorded graph targets |
| --- | --- |
| `ProtosLanguageContext.bytecodeExecutionPlanForDefinitionMiss` | 1 |
| `ProtosLanguageContext.existingBytecodeExecutionPlan` | 1 |

The stable graph has `InvokeWithExceptionNode=2`, `MethodCallTargetNode=2`, `ExceptionObjectNode=2`, `DeoptimizeNode=2`. The two invoke targets are `@TruffleBoundary` helpers in [`ProtosLanguageContext.java`](https://github.com/guillermomolina/protos/blob/5f26219c06bb8ea382da28eaf56dfefbfbf752ab/src/main/java/com/guillermomolina/protos/execution/host/embedding/ProtosLanguageContext.java): `existingBytecodeExecutionPlan` reads a Context-owned map, and `bytecodeExecutionPlanForDefinitionMiss` rebuilds a projection only after a miss. **Important:** graph presence includes exceptional/uncommon branches; the captured JSON does not establish which branch executes on each normal call.

The code path worth auditing is [`ProtosFunctionCallDispatchers.FunctionCachedCallNode.functionRootOrNull`](https://github.com/guillermomolina/protos/blob/5f26219c06bb8ea382da28eaf56dfefbfbf752ab/src/main/java/com/guillermomolina/protos/execution/bytecode/activation/ProtosFunctionCallDispatchers.java) → `ProtosClosureCallPreparation.functionCallTarget` (when the prepared local-root checks do not prove a direct return) → `ProtosLanguageContext.bytecodeExecutionPlanForDefinition`. In contrast, [GraalPy 25.4.4 `CallDispatchers`](https://github.com/oracle/graalpython/blob/graal-25.4.4/graalpython/com.oracle.graal.python/src/com/oracle/graal/python/nodes/call/CallDispatchers.java) uses a `PFunction.getCode().getRootNode()` guard at its code-root cache. **This is an actionable source-level divergence hypothesis, not yet a proven explanation for all 147 extra nodes.**

## 4. Cold Tier 1 and Tier 2 root census (independent capture JVMs)

| Semantic root | Tier 1 comp ID | Tier 1 nodes | Tier 2 comp ID | Tier 2 nodes | T2 − T1 |
| --- | --- | --- | --- | --- | --- |
| run | 2797 | 387 | 2927 | 340 | -47 |
| identity | 2834 | 182 | 2932 | 123 | -59 |
| host adapter | 2742 | 674 | 2906 | 939 | 265 |

The matching is based on source-root labels unique within each capture, including `run` source span `1050+46` and `identity` `1073+5`. Both full-census captures classify 3/3 observed compiled targets as available, 0 missing; the generated structural pairing status is **COMPLETE**. The cross-JVM match is **semantic/normalized-root matching**, not the reuse of Java `@hex` object identities. Neither `run` nor `identity` is equated to the host adapter. No Tier 1/2 cold count is substituted for the *stable* Tier 2 reference total without explicit qualification.

### 4.1 Cold comparison with the published C6 diagnostics

| Metric | C6 | Current | Difference |
| --- | --- | --- | --- |
| Stable reference `run` T2 | 193 | 340 | +147 (+76.2%) |
| Cold `run` T1 | 358 | 387 | +29 (+8.1%) |
| Cold `run` T2 | 193 | 340 | +147 (+76.2%) |
| Cold `identity` T1 | 108 | 182 | +74 (+68.5%) |
| Cold `identity` T2 | 51 | 123 | +72 (+141.2%) |
| Cold host-adapter T2 (excluded) | 331 | 939 | +608 (excluded) |

The host adapter's own graph is excluded from the guest-root reference metric. Cold graphs are diagnostics at independent compiler thresholds (`Tier 1: first=100, last=1,000,000`; `Tier 2: first=100, last=1,000`) with 2,000 post-warmup invocations, zero warmup calls, and separate JVMs.

### 4.2 Current cold residual invoke targets

| Root | Tier | Nodes | Invoke targets |
| --- | --- | --- | --- |
| run | 1 | 387 | `OptimizedCallTarget.callBoundary` ×1; `OptimizedCallTarget.lastTierCompile` ×1; `ProtosLanguageContext.bytecodeExecutionPlanForDefinitionMiss` ×1; `ProtosLanguageContext.existingBytecodeExecutionPlan` ×1 |
| identity | 1 | 182 | `OptimizedCallTarget.lastTierCompile` ×1 |
| host adapter | 1 | 674 | `Number.longValue` ×1; `OptimizedCallTarget.callBoundary` ×1; `OptimizedCallTarget.lastTierCompile` ×1; `PolyglotContextImpl.enterThreadChanged` ×1; `PolyglotContextImpl.leaveThreadChanged` ×1; `ProtosEmbeddedProcess.concurrentEntryRejected` ×1; `ProtosEmbeddedProcess.outermostEntryFailed` ×1; `ProtosEmbeddedProcess.terminated` ×2; `ProtosHostExecutableClosure.admitHostTextOrReject` ×1 |
| run | 2 | 340 | `ProtosLanguageContext.bytecodeExecutionPlanForDefinitionMiss` ×1; `ProtosLanguageContext.existingBytecodeExecutionPlan` ×1 |
| identity | 2 | 123 | — |
| host adapter | 2 | 939 | `Number.longValue` ×1; `PolyglotContextImpl.enterThreadChanged` ×1; `PolyglotContextImpl.leaveThreadChanged` ×1; `ProtosEmbeddedProcess.concurrentEntryRejected` ×1; `ProtosEmbeddedProcess.outermostEntryFailed` ×1; `ProtosEmbeddedProcess.terminated` ×2; `ProtosHostExecutableClosure.admitHostTextOrReject` ×1; `ProtosLanguageContext.bytecodeExecutionPlanForDefinitionMiss` ×1; `ProtosLanguageContext.existingBytecodeExecutionPlan` ×1 |

The Tier 1 `run` path retains compilation-runtime targets (`OptimizedCallTarget.callBoundary`, `lastTierCompile`) as well as Context projection helpers. The Tier 2 guest `run` retains only the two Context projection helpers; `identity` has no residual invoke in Tier 2. Runtime compilation and host adapter invokes must not be conflated with source-level calls.

## 5. Executed Bytecode DSL and physical-root attribution

The diagnostic executes **100 requested benchmark calls** and records **101 executions** of the guest `run` and `identity` roots in total, including the diagnostic driver's own call. The histogram covers Core initialization and auxiliary roots, so aggregated dynamic operations are *not* the cost of one compiled `run`.

### 5.1 Call work versus C6

| Metric | C6 | Current | Difference |
| --- | --- | --- | --- |
| DSL total executed instructions | 3820 | 4224 | +404 (+10.6%) |
| DSL `run` executed instructions | 1212 | 1616 | +404 (+33.3%) |
| DSL `identity` executed instructions | 707 | 707 | 0 |
| `run` cached bytecode bytes | 106 | 132 | +26 (+24.5%) |
| `run` cached bytecode instructions | 28 | 36 | +8 (+28.6%) |
| `identity` cached bytecode bytes | 70 | 70 | 0 |
| `identity` cached bytecode instructions | 18 | 18 | 0 |

The current diagnostic has **4,224 total DSL operation executions** across all roots versus **3,820 in C6** (+404); the aggregate increase is **numerically equal** to the `run`-root increase (1,616 − 1,212 = +404), while `identity` remains at 707. This does not separately prove that every remaining bootstrap root is unchanged between campaigns. This does not imply the 404 additional interpreter operations survive JIT compilation.

### 5.2 Current `run` DSL operation histogram (1,616 executions)

| Bytecode DSL operation | Executed |
| --- | --- |
| `load.constant` | 207 |
| `load.local$generic` | 192 |
| `store.local$generic` | 192 |
| `c.CallUnaryMethod` | 101 |
| `c.EnterRoot` | 101 |
| `c.EpilogForReturn` | 101 |
| `c.MaterializeCurrentClosure` | 101 |
| `return` | 101 |
| `tag.enter` | 101 |
| `load.constant$Long` | 96 |
| `load.local$Long` | 96 |
| `store.local$Long$Long` | 96 |
| `tag.leave$generic` | 96 |
| `load.local` | 15 |
| `store.local` | 15 |
| `tag.leave` | 5 |

The call opcode `c.CallUnaryMethod` is reported **101 times** without a `$CallPFunction` suffix. C6 recorded `c.CallUnaryMethod=5` plus `c.CallUnaryMethod$CallPFunction=96` for 101 call executions. Therefore the current bytecode histogram exposes **no quickened call-opcode label** for this site. A separate check of the nested dispatcher specialization and generated code is required before concluding a lost Graal/Truffle call cache.

### 5.3 Current `identity` DSL operation histogram (707 executions)

| Bytecode DSL operation | Executed |
| --- | --- |
| `c.CopyArguments` | 101 |
| `c.EnterRoot` | 101 |
| `c.EpilogForReturn` | 101 |
| `return` | 101 |
| `tag.enter` | 101 |
| `load.local$Long` | 96 |
| `tag.leave$generic` | 96 |
| `load.local` | 5 |
| `tag.leave` | 5 |

All 101 `c.CopyArguments` operations occur in `identity`, **not in the `run` call-site root**. The same attribution held in C6. This prevents incorrectly charging argument copying as a separate Bytecode DSL operator inside `run`.

### 5.4 Static bytecode size (source-semantic root attribution)

| Root | Interpreter state | Bytes | Instructions |
| --- | --- | --- | --- |
| `run` | UNCACHED | 132 | 36 |
| `run` | CACHED | 132 | 36 |
| `identity` | UNCACHED | 70 | 18 |
| `identity` | CACHED | 70 | 18 |

**Attribution qualification.** The generated report records per-compiled-root size evidence as `AVAILABLE` for `run` and `identity` using the stable normalized source-root label. Its stronger `physical_root_attribution` status is `PARTIAL` because the histogram uses stable names but size observations use ephemeral `ProtosBytecodeRootNodeGen@hex` identifiers; a strict physical-object join cannot be claimed. Both roots' numerical size observations are nevertheless retained; the framework/host root is not a guest Bytecode DSL root.

## 6. Investigation and next steps (no unmeasured performance claims)

1. **Inspect generated `CallUnaryMethod` behavior before adding any patch.** The dynamic DSL site shows 101 generic op labels rather than C6's 5 generic + 96 `$CallPFunction`. Compare the generator/specialization and the `CallNode` wrapper to GraalPy `CallNode` / `FunctionCachedCallNode`. Establish whether this is a naming/quickening change or an actual longer invocation path. Do not restore D013 `call` slot selection to hide this difference.
2. **Trace why `run`'s compiler graph retains the projection helpers.** Audit the prepared-root branch, `requiresContextLocalExecutionProjectionForRuntime`, the plan's language identity, and the `functionRootOrNull` guard. The two residual targets are a specific source-level area to investigate. Check exceptional/deopt paths in the retained raw BGV before proposing an optimization; the current derived JSON alone does not prove they are invoked in the hot path.
3. **Source-to-source convergence with GraalPy:** retain the existing direct/indirect dispatch architecture and single/multi-context semantics. Compare GraalPy's root-identity guard and Protos' additional prepared-plan/projection checks, not just the 340 vs 50 node totals. Do not break capability or context isolation semantics merely to reduce a graph.
4. **Only after an explicit causal hypothesis and a new product revision, re-capture this same Protos workload.** Keep GraalPy as a historical reference and use the same workload/source SHA, toolchain, phase, and root attribution. Do not remeasure GraalPy, other workloads, or timing for this structural investigation.

## 7. Evidence inventory and limitations

The eight uploaded files are all internally validated by their producer status fields. The prepared sidecar data files in this report package are derived without a new guest execution:

- `I115_5f26219c_compiled_roots.csv` — six independent cold root observations plus the stable reference.
- `I115_5f26219c_run_node_classes.csv` — the *complete current* `run` histogram, and only the selected old classes published in C6.
- `I115_5f26219c_DSL_ops_by_root.csv` — each captured per-source-root dynamic opcode count, including bootstrap roots.
- `I115_5f26219c_manifest.json` — identities and SHA-256 for this input and report.

**Limitations:** The upload contains derived JSON but not BGV/log source bytes; raw graph topology, branch-path execution, inlining decisions, per-root physical object identity across JVMs, and a complete GraalPy node-class distribution cannot be established from it. Cold root matching and stable-reference matching have distinct validity rules; their equal 340 totals do not constitute an exact same-object proof. Historic data is not rerun and should not be mistaken for newly captured evidence. No timing or throughput conclusions are made.

## Appendix A — Complete current stable `run` graph node histogram

| Node class | Current count |
| --- | --- |
| `AllocatedObjectNode` | 2 |
| `BeginNode` | 34 |
| `BoxNode$AllocatingBoxNode` | 1 |
| `CommitAllocationNode` | 2 |
| `ConstantNode` | 44 |
| `DeoptimizeNode` | 2 |
| `EndNode` | 25 |
| `ExceptionObjectNode` | 2 |
| `FixedGuardNode` | 11 |
| `FrameState` | 58 |
| `IfNode` | 16 |
| `InstanceOfNode` | 2 |
| `IntegerEqualsNode` | 4 |
| `InvokeWithExceptionNode` | 2 |
| `IsNullNode` | 13 |
| `LoadFieldNode` | 18 |
| `LoadIndexedNode` | 5 |
| `MergeNode` | 9 |
| `MethodCallTargetNode` | 2 |
| `ObjectEqualsNode` | 11 |
| `ParameterNode` | 1 |
| `PiArrayNode` | 1 |
| `PiNode` | 18 |
| `ReturnNode` | 1 |
| `ShortCircuitOrNode` | 4 |
| `StartNode` | 1 |
| `StateSplitProxyNode` | 4 |
| `StoreFieldNode` | 2 |
| `TrufflePreserveFrameStateNode` | 1 |
| `ValuePhiNode` | 7 |
| `VirtualArrayNode` | 8 |
| `VirtualBoxingNode` | 4 |
| `VirtualInstanceNode` | 5 |
| `VirtualObjectState` | 20 |

**Histogram total:** 340 nodes, exactly equal to the selected reference graph `node_count`.
