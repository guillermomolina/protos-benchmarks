# I115-C6 — Complete Protos/GraalPy Structural Comparison and Call-Lowering Audit

**Campaign date:** 31 October 2026  
**Measured Protos product:** `I115` HEAD, `a185d7b1f3e9d2d7c8b98929db48ced02108337e`  
**Benchmark harness commit:** `b77efb62c25a9a6b05c6ec4d2c9f31721dd059f6`  
**Measured languages in this campaign:** Protos only  
**Workloads:** 17/17; stable Tier 2 reference graphs and independent Tier 1/Tier 2 root censuses; 17/17 Bytecode DSL diagnostics  
**Phase:** `After TruffleTier`; **historical comparison:** I115-H10 and GraalPy 25.4.4.1.1  
**Scope exclusions:** no timing, throughput, memory benchmark, GraalJS or GraalPy remeasurement  

> **Purpose.** Determine what changed at the current I115-C6 HEAD in the compiler graphs of method and closure calls, while reporting all 17 workloads. The primary graph metric is the stable, **language-owned** `relevant_graph_nodes_total_after_truffle_tier` used by H10. Independent cold Tier 1/2 observations and executed Bytecode DSL operations are reported separately, never added to the stable graph total. Historical H10 and GraalPy figures are comparisons, **not** C6 measurements.

## 1. Scope, producer identity, and admission rules

- **Exact C6 producer identity:** product HEAD `a185d7b1f3e9d2d7c8b98929db48ced02108337e`; both the stable-reference and Bytecode DSL capture manifests report a clean Protos checkout, the same product source-state fingerprint and the same harness Git HEAD. Protos declares GraalVM 25.4.4.1.1 and Maven compiler release 21 in the captured product identity.
- **Source identity cross-check:** the Protos workload source SHA-256 in every stable `unit.json` equals the corresponding captured DSL workload `source_sha256` (17/17). Thus the two measurement protocols used the same case sources, not merely the same case names.
- **Workload correctness:** PASS for all 17 stable-reference workloads; 17 reference captures are valid; 17 `unit.json` records are `evidence_valid=true`; all 17 stabilize (`STABLE`) with selected compiler Tier 2; graph analysis phase is exactly `After TruffleTier`.
- **DSL:** 17 captures are valid; all histogram statuses are `AVAILABLE`. Histograms count executed interpreter operations over the diagnostic calls and include compilation-independent initialization/root activity. They do not count graph nodes or static source instructions.
- **Tier 1 and Tier 2:** 34 earlier cold-summary files are supplied with the HEAD evidence bundle, each with observed compiled targets and `After TruffleTier` node histograms. They are *diagnostic cold captures*, with a different compilation selection and run protocol from the stabilized reference campaign. The bundle lacks their original cold `capture.json` manifests; therefore their exact product SHA is not independently revalidated from those 34 summary files alone, although they were supplied from the same C6 local campaign.
- **Harness working tree:** the product was clean; the harness manifests mark their working tree `dirty=true` because report files were edited/removed locally. The measured source hashes and harness commit are retained; do not confuse harness-tree cleanliness with Protos product cleanliness.
- **Comparison admission:** historical H10 and GraalPy values are the Tier 2 nodes reproduced in the provided H10 report. Stable C6 `unit.json` is compared directly against those historical per-workload totals; guest-root counts from `cold-summary.json` are **never** substituted for that metric.

## 2. Full 17-workload matrix: current C6 vs H10 and historical GraalPy

All graph columns refer to **Tier 2 `After TruffleTier` language-owned stabilized units**. `ΔH10` = C6 − H10; `ΔPy` = C6 − the historical GraalPy reference. Both percentages use their respective comparator as denominator. A positive delta is a larger graph, not proof of slower execution. The `Executed DSL ops` column is a different diagnostic run, not a graph measurement.

| Workload | C6 reference roots | C6 nodes | H10 nodes | ΔH10 | GraalPy nodes | ΔPy | Executed DSL ops |
|---|---|---|---|---|---|---|---|
| `fibonacci` | 2 | 4,432 | 4,141 | +291 (+7.0%) | 2,865 | +1,567 (+54.7%) | 42,011,038 |
| `factorial` | 2 | 743 | 545 | +198 (+36.3%) | 975 | -232 (-23.8%) | 44,427 |
| `method-call` | 1 | 90 | 127 | -37 (-29.1%) | 119 | -29 (-24.4%) | 2,629,345 |
| `integer-loop` | 1 | 74 | 74 | +0 (+0.0%) | 79 | -5 (-6.3%) | 1,316,315 |
| `primitive-return-literal` | 1 | 47 | 47 | +0 (+0.0%) | 49 | -2 (-4.1%) | 2,507 |
| `primitive-local-read` | 1 | 47 | 47 | +0 (+0.0%) | 49 | -2 (-4.1%) | 2,709 |
| `primitive-local-write` | 1 | 47 | 47 | +0 (+0.0%) | 49 | -2 (-4.1%) | 2,911 |
| `primitive-integer-add` | 1 | 47 | 47 | +0 (+0.0%) | 49 | -2 (-4.1%) | 3,113 |
| `primitive-object-slot-read` | 1 | 72 | 72 | +0 (+0.0%) | 103 | -31 (-30.1%) | 2,635 |
| `primitive-object-slot-write` | 1 | 122 | 122 | +0 (+0.0%) | 159 | -37 (-23.3%) | 3,039 |
| `primitive-closure-call` | 1 | 193 | 106 | +87 (+82.1%) | 50 | +143 (+286.0%) | 3,820 |
| `primitive-method-call` | 1 | 64 | 99 | -35 (-35.4%) | 82 | -18 (-21.9%) | 3,850 |
| `primitive-if-true` | 1 | 47 | 47 | +0 (+0.0%) | 49 | -2 (-4.1%) | 3,113 |
| `primitive-if-false` | 1 | 47 | 47 | +0 (+0.0%) | 49 | -2 (-4.1%) | 2,709 |
| `primitive-while-zero` | 1 | 47 | 47 | +0 (+0.0%) | 49 | -2 (-4.1%) | 2,709 |
| `primitive-while-once` | 1 | 68 | 68 | +0 (+0.0%) | 73 | -5 (-6.8%) | 4,022 |
| `primitive-while-counted` | 1 | 69 | 69 | +0 (+0.0%) | 74 | -5 (-6.8%) | 10,385 |

**C6 vs H10:** 12/17 Tier 2 reference totals are unchanged; two decrease (`method-call` and `primitive-method-call`); three increase (`primitive-closure-call`, `factorial`, and `fibonacci`). The two method cases each have one stable compiled guest unit, as in H10. `factorial`/`fibonacci` each have two stable guest units, so per-root matching across historical revisions is not inferred.

### 2.1 Changes prioritized by absolute graph-node delta

| Workload | H10 | C6 | Δ nodes | Δ% |
|---|---|---|---|---|
| `fibonacci` | 4,141 | 4,432 | +291 | +7.0% |
| `factorial` | 545 | 743 | +198 | +36.3% |
| `primitive-closure-call` | 106 | 193 | +87 | +82.1% |
| `method-call` | 127 | 90 | -37 | -29.1% |
| `primitive-method-call` | 99 | 64 | -35 | -35.4% |

**Historical GraalPy reference:** GraalPy was not run for C6. The snapshot is valuable for node-count comparison, not for proving identical inlining or bytecode semantics. Neither total-node differences nor differences across workloads are a throughput index.

## 3. C6 Tier 1 / Tier 2 independent root census (not the H10 comparison metric)

Cold captures classify guest `ProtosBytecodeRootNodeGen@…` roots separately from the polyglot `Value<ProtosHostExecutableClosure>.execute` adapter. Cells show **individual observed guest-root sizes**; they are not paired across JVMs or implicitly matched to the reference unit. A missing/ambiguous compilation is shown explicitly rather than treated as zero.

| Workload | Tier 1 observed Protos roots | Tier 2 observed Protos roots | Stable Tier 2 ref | Excluded Tier 2 host nodes |
|---|---|---|---|---|
| `fibonacci` | 284 + 411 | 2,120 + 2,312 | 4,432 | 2,506 |
| `factorial` | 177 + 328 | 309 + 434 | 743 | 575 |
| `method-call` | 94 + 1 unavailable | 36 + 90 | 90 | 289 |
| `integer-loop` | none + 1 unavailable | 74 | 74 | 268 |
| `primitive-return-literal` | 104 | 47 | 47 | 185 |
| `primitive-local-read` | 104 | 47 | 47 | 185 |
| `primitive-local-write` | 104 | 47 | 47 | 185 |
| `primitive-integer-add` | 104 | 47 | 47 | 220 |
| `primitive-object-slot-read` | 129 | 72 | 72 | 211 |
| `primitive-object-slot-write` | 181 | 122 | 122 | 284 |
| `primitive-closure-call` | 108 + 358 | 51 + 193 | 193 | 331 |
| `primitive-method-call` | 94 + 149 | 36 + 64 | 64 | 241 |
| `primitive-if-true` | 104 | 47 | 47 | 185 |
| `primitive-if-false` | 104 | 47 | 47 | 185 |
| `primitive-while-zero` | 104 | 47 | 47 | 185 |
| `primitive-while-once` | 176 | 68 | 68 | 262 |
| `primitive-while-counted` | 177 | 69 | 69 | 263 |

**Critical exclusions:** Tier 2 cold guest roots for the three call cases are `51, 193` (closure), `36, 64` (primitive method), and `36, 90` (method loop). The C6/H10 comparable reference values are **193**, **64**, and **90**, not guest-root sums of 244, 100 and 126. The additional host polyglot graph is also excluded. This is why earlier all-roots totals were not comparable with H10.

**Cross-tier pairing is limited:** identical normalized `ProtosBytecodeRootNodeGen@*` labels can refer to different roots across independent JVMs. The earlier structural reports marked six workload-level pairings partial; `method-call` and `integer-loop` also include Tier 1 unavailable compilation evidence. The cold-summary bundle does not authorize constructing arbitrary root-level Tier 1→Tier 2 deltas.

## 4. Call lowering: stable graph outcomes and historical comparison

| Workload | H10 | C6 HEAD | Δ C6−H10 | GraalPy | Δ C6−Py | Stable graphs | Invokes |
|---|---|---|---|---|---|---|---|
| `method-call` | 127 | 90 | -37 | 119 | -29 | 1 | 0 |
| `primitive-method-call` | 99 | 64 | -35 | 82 | -18 | 1 | 0 |
| `primitive-closure-call` | 106 | 193 | +87 | 50 | +143 | 1 | 1 |

- **`method-call`:** 90 nodes vs 127 H10 (**−37, −29.1%**), 119 GraalPy (**−29**). The one stable reference graph has zero residual invokes; it retains the benchmark loop (`LoopBeginNode=1`, `IfNode=1`) and has `FrameState=8`.
- **`primitive-method-call`:** 64 nodes vs 99 H10 (**−35, −35.4%**), 82 GraalPy (**−18**). Its one stable graph has zero invokes, zero `IfNode`, six `FrameState` and four `FixedGuardNode`.
- **`primitive-closure-call`:** 193 nodes vs 106 H10 (**+87, +82.1%**), 50 GraalPy (**+143**). The stable guest graph has one `InvokeWithExceptionNode` and a recorded target `ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate`. Its graph contains 29 `FrameState`, 11 `FixedGuardNode`, five `IfNode`, two `InstanceOfNode`, and two `AllocatedObjectNode`.

**Interpretation.** The two method workloads exhibit **smaller stable compiler graphs** on C6. The closure graph is larger and carries a real Java invoke edge that warrants investigation. These are structural facts. They do *not* establish that the entire +87 closure delta is caused by the certificate call or that method dispatch is faster in wall-clock time.

### 4.1 Stable reference root details

| Workload | Comp ID | Tier | Nodes | FrameState | FixedGuard | If | Deopt | Alloc. family | Invokes | Residual target |
|---|---|---|---|---|---|---|---|---|---|---|
| `method-call` | 2855 | 2 | 90 | 8 | 6 | 1 | 0 | 1 | 0 | — |
| `primitive-method-call` | 2844 | 2 | 64 | 6 | 4 | 0 | 0 | 1 | 0 | — |
| `primitive-closure-call` | 2927 | 2 | 193 | 29 | 11 | 5 | 1 | 5 | 1 | `ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate` ×1 |


### 4.2 Complete selected-class audit for the three stable call graphs

| Graal node class | `method-call` | `primitive-method-call` | `primitive-closure-call` |
|---|---|---|---|
| `ConstantNode` | 27 | 22 | 32 |
| `FrameState` | 8 | 6 | 29 |
| `FixedGuardNode` | 6 | 4 | 11 |
| `IfNode` | 1 | 0 | 5 |
| `BeginNode` | 1 | 0 | 11 |
| `EndNode` | 1 | 0 | 10 |
| `InstanceOfNode` | 0 | 0 | 2 |
| `DeoptimizeNode` | 0 | 0 | 1 |
| `VirtualObjectState` | 8 | 5 | 11 |
| `VirtualArrayNode` | 4 | 4 | 4 |
| `VirtualInstanceNode` | 1 | 1 | 3 |
| `MaterializedObjectState` | 0 | 0 | 1 |
| `AllocatedObjectNode` | 0 | 0 | 2 |
| `CommitAllocationNode` | 0 | 0 | 2 |
| `BoxNode$AllocatingBoxNode` | 1 | 1 | 1 |
| `BoxNode$TrustedBoxedValue` | 0 | 0 | 0 |
| `UnboxNode` | 0 | 0 | 0 |
| `PiNode` | 3 | 4 | 10 |
| `LoadFieldNode` | 1 | 1 | 13 |
| `LoadIndexedNode` | 6 | 6 | 5 |
| `GuardedUnsafeLoadNode` | 1 | 1 | 0 |
| `IntegerEqualsNode` | 1 | 1 | 3 |
| `IntegerLessThanNode` | 1 | 0 | 0 |
| `IntegerAddExactNode` | 2 | 0 | 0 |
| `IntegerAddExactOverflowNode` | 2 | 0 | 0 |
| `LoopBeginNode` | 1 | 0 | 0 |
| `LoopEndNode` | 1 | 0 | 0 |
| `LoopExitNode` | 1 | 0 | 0 |
| `InvokeWithExceptionNode` | 0 | 0 | 1 |
| `MethodCallTargetNode` | 0 | 0 | 1 |
| `ExceptionObjectNode` | 0 | 0 | 1 |
| `StateSplitProxyNode` | 0 | 0 | 5 |
| `ValuePhiNode` | 2 | 0 | 4 |

These are **actual counts from the stable compiler graph**, not inferred bytecode operation costs. Some Graal classes counted under the broad `allocations`/`guards_deopts` families differ from the simple class-name sum. The complete node-class histogram for every retained root is in `I115-C6_HEAD_graal_node_classes.csv`.

### 4.3 Independent Tier 1 and Tier 2 call-root diagnostic details

| Workload | Tier | Cold comp ID | Nodes | FrameState | FixedGuard | If | Deopt | Invokes | Invoke targets |
|---|---|---|---|---|---|---|---|---|---|
| `method-call` | 1 | 2678 | 94 | 15 | 0 | 4 | 1 | 1 | OptimizedCallTarget.lastTierCompile |
| `method-call` | 2 | 2800 | 36 | 6 | 0 | 0 | 0 | 0 | — |
| `method-call` | 2 | 2865 | 90 | 8 | 6 | 1 | 0 | 0 | — |
| `primitive-method-call` | 1 | 2764 | 94 | 15 | 0 | 4 | 1 | 1 | OptimizedCallTarget.lastTierCompile |
| `primitive-method-call` | 1 | 2740 | 149 | 24 | 4 | 4 | 2 | 2 | OptimizedCallTarget.callBoundary, OptimizedCallTarget.lastTierCompile |
| `primitive-method-call` | 2 | 2906 | 36 | 6 | 0 | 0 | 0 | 0 | — |
| `primitive-method-call` | 2 | 2898 | 64 | 6 | 4 | 0 | 0 | 0 | — |
| `primitive-closure-call` | 1 | 2738 | 108 | 15 | 1 | 4 | 1 | 1 | OptimizedCallTarget.lastTierCompile |
| `primitive-closure-call` | 1 | 2718 | 358 | 53 | 12 | 18 | 4 | 4 | OptimizedCallTarget.callBoundary, OptimizedCallTarget.lastTierCompile, ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate, ProtosTailCallContinuation.deferred |
| `primitive-closure-call` | 2 | 2972 | 51 | 6 | 1 | 0 | 0 | 0 | — |
| `primitive-closure-call` | 2 | 2963 | 193 | 29 | 11 | 5 | 1 | 1 | ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate |

These are separately compiled cold roots, **not a Tier 1→Tier 2 matched-root time series**. In particular, `method-call` has one additional unavailable Tier 1 guest root (`TIER_COMPILATION_AMBIGUOUS`). The Tier 1 closure roots contain additional runtime compilation/boundary invokes (including `OptimizedCallTarget.lastTierCompile`), which must not be mistaken for calls left in the stabilized Tier 2 closure graph. The full host-adapter diagnostic and every node class are retained in the CSVs.

### 4.4 Other changed paths: `factorial` and `fibonacci`

`factorial` measures 743 stable Tier 2 nodes in two guest compilations (309 + 434) versus 545 H10 (**+198**) and 975 historical GraalPy (**−232**). `fibonacci` measures 4,432 (2,120 + 2,312), versus 4,141 H10 (**+291**) and 2,865 GraalPy (**+1,567**). Both workload correctness checks pass and both stable reference budgets are [16,000, 64,000]. Without a paired per-semantic-root H10 histogram, these deltas cannot be attributed to closure dispatch or recursion exclusively.

### 4.5 Unchanged basic, object-slot, and control-flow cases

Object-slot read remains **72** nodes against **103** GraalPy (−31); object-slot write **122** against **159** (−37). The four basic return/local/arithmetic primitives remain at 47; `if-true`, `if-false`, `while-zero` also remain at 47; `while-once` at 68; `while-counted` at 69; and `integer-loop` at 74. These are stable C6 results, equal to H10; identical totals do not establish identical node-class distributions across versions.

## 5. Bytecode DSL physical-root audit: specialization, CopyArguments, and bytecode sizes

### 5.1 Exact executed operations in the three workloads

| Workload | CallBinary generic | CallBinary$Direct | GetMethod generic | GetMethod$Cached | CallUnary generic | CallUnary$CallPFunction | CopyArguments | All DSL ops |
|---|---|---|---|---|---|---|---|---|
| `method-call` | 5 | 100,995 | 5 | 100,995 | 0 | 0 | 101,000 | 2,629,345 |
| `primitive-method-call` | 5 | 96 | 5 | 96 | 0 | 0 | 101 | 3,850 |
| `primitive-closure-call` | 0 | 0 | 0 | 0 | 5 | 96 | 101 | 3,820 |

The observed method specialization ratio is **100,995 / 101,000 = 99.995%** in `method-call`, and **96 / 101 ≈ 95.05%** in each primitive call case. These are interpreter execution counts in one diagnostic profile, not a claim that the compiler emitted those operations as separate machine-code instructions.

### 5.2 Identify the physical call root, the argument-copy root, and static sizes

| Workload | Within diagnostic JVM | Physical root | Executed ops in root | Call ops | CopyArguments | UNCACHED bytes / instr. | CACHED bytes / instr. |
|---|---|---|---|---|---|---|---|
| `method-call` | call-site root | `ProtosBytecodeRootNodeGen@2baa8d82` | 1,920,414 | 101000 | 0 | 254 B / 62 instr. | 254 B / 62 instr. |
| `method-call` | argument-copy/callee root | `ProtosBytecodeRootNodeGen@66971f6b` | 707,000 | 0 | 101000 | 70 B / 18 instr. | 70 B / 18 instr. |
| `primitive-method-call` | call-site root | `ProtosBytecodeRootNodeGen@644c78d4` | 1,212 | 101 | 0 | 120 B / 28 instr. | 120 B / 28 instr. |
| `primitive-method-call` | argument-copy/callee root | `ProtosBytecodeRootNodeGen@a7e2d9d` | 707 | 0 | 101 | 70 B / 18 instr. | 70 B / 18 instr. |
| `primitive-closure-call` | argument-copy/callee root | `ProtosBytecodeRootNodeGen@4b6166aa` | 707 | 0 | 101 | 70 B / 18 instr. | 70 B / 18 instr. |
| `primitive-closure-call` | call-site root | `ProtosBytecodeRootNodeGen@7997b197` | 1,212 | 101 | 0 | 106 B / 28 instr. | 106 B / 28 instr. |

**Important attribution:** `c.CopyArguments` executes on a **different physical root** from the specialized `CallUnaryMethod`/`CallBinaryMethod` instruction in each of these diagnostics. Do not interpret its aggregated count as `CopyArguments` executed inside the call-site root, and do not equate interpreter instruction frequency with an un-inlined JIT invocation. The root sizes are matched by exact physical label **within each diagnostic JVM**; these ephemeral labels are not matched to Tier 1/Tier 2 compiler targets.

### 5.3 Detailed call-site DSL instruction histograms (actual counts, including quickenings)

#### `method-call` — call-site root `ProtosBytecodeRootNodeGen@2baa8d82`

**Executed interpreter instructions in this physical root:** 1,920,414. **Distinct operation labels:** 29.

| Bytecode DSL operation | Executed count |
|---|---|
| `load.constant$Int` | 202,289 |
| `load.local$Int$unboxed` | 202,091 |
| `load.local$Int` | 202,090 |
| `store.local$Int$Int` | 101,193 |
| `branch.false` | 101,101 |
| `c.Lt$II` | 101,096 |
| `c.NumberInPlaceAdd` | 101,005 |
| `branch.backward` | 101,000 |
| `dup` | 101,000 |
| `load.stackvalue` | 101,000 |
| `store.stackvalue` | 101,000 |
| `c.CallBinaryMethod$Direct` | 100,995 |
| `c.GetMethod$Cached` | 100,995 |
| `c.NumberInPlaceAdd$II$unboxed` | 100,995 |
| `c.ReadGlobal$ReadCached` | 100,995 |
| `store.local$Int` | 100,995 |
| `c.EnterRoot` | 101 |
| `c.EpilogForReturn` | 101 |
| `return` | 101 |
| `tag.enter` | 101 |
| `tag.leave$generic` | 100 |
| `load.local` | 21 |
| `load.constant` | 14 |
| `store.local` | 14 |
| `c.CallBinaryMethod` | 5 |
| `c.GetMethod` | 5 |
| `c.Lt` | 5 |
| `c.ReadGlobal` | 5 |
| `tag.leave` | 1 |


#### `primitive-method-call` — call-site root `ProtosBytecodeRootNodeGen@644c78d4`

**Executed interpreter instructions in this physical root:** 1,212. **Distinct operation labels:** 16.

| Bytecode DSL operation | Executed count |
|---|---|
| `c.EnterRoot` | 101 |
| `c.EpilogForReturn` | 101 |
| `dup` | 101 |
| `load.constant` | 101 |
| `load.stackvalue` | 101 |
| `return` | 101 |
| `store.stackvalue` | 101 |
| `tag.enter` | 101 |
| `c.CallBinaryMethod$Direct` | 96 |
| `c.GetMethod$Cached` | 96 |
| `c.ReadGlobal$ReadCached` | 96 |
| `tag.leave$generic` | 96 |
| `c.CallBinaryMethod` | 5 |
| `c.GetMethod` | 5 |
| `c.ReadGlobal` | 5 |
| `tag.leave` | 5 |


#### `primitive-closure-call` — call-site root `ProtosBytecodeRootNodeGen@7997b197`

**Executed interpreter instructions in this physical root:** 1,212. **Distinct operation labels:** 14.

| Bytecode DSL operation | Executed count |
|---|---|
| `load.constant` | 303 |
| `c.EnterRoot` | 101 |
| `c.EpilogForReturn` | 101 |
| `c.MaterializeCurrentClosure` | 101 |
| `return` | 101 |
| `tag.enter` | 101 |
| `c.CallUnaryMethod$CallPFunction` | 96 |
| `load.local$generic` | 96 |
| `store.local$generic` | 96 |
| `tag.leave$generic` | 96 |
| `c.CallUnaryMethod` | 5 |
| `load.local` | 5 |
| `store.local` | 5 |
| `tag.leave` | 5 |


### 5.4 Residual invokes and interpretation of the closure overhead

C6 stable reference graph invokes:

| Workload | Compiler invoke nodes | Invoke target | Compiler graph size |
|---|---|---|---|
| `method-call` | 0 | None | 90 |
| `primitive-method-call` | 0 | None | 64 |
| `primitive-closure-call` | 1 | ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate | 193 |

The closure target `ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate` is a **concrete investigation candidate**, not a demonstrated cause for all guards, frame states or allocations. Check correctness, certificate validity, invalidation and inlining effects before proposing an optimization. Both method graphs show no such residual Java invoke within their *selected stable guest graphs*; that does not mean no call occurs anywhere in the host adapter or runtime.

## 6. Validation, coverage and methodological limitations

| Admission / scope field | Observed status |
|---|---|
| Workloads in bundle | 17 / 17 |
| JSON files provided | 85 (17 reference units + 17 reference captures + 17 DSL captures + 34 cold summaries) |
| Stable reference `STABLE` / Tier 2 | 17 / 17 |
| Reference correctness PASS | 17 / 17 |
| Reference `evidence_valid` | 17 / 17 |
| DSL `capture_valid` and histogram AVAILABLE | 17 / 17 |
| Unique recorded product revisions | 1 — a185d7b1f3e9d2d7c8b98929db48ced02108337e |
| Protos product clean at capture | YES; before and after |
| Harness working tree clean | NO; report working-tree changes recorded |
| Cold root Tier 1 missing compilation evidence | `integer-loop`: 1 root; `method-call`: 1 root |
| Historical H10 and GraalPy recaptured | NO |
| Tier 1/Tier 2 individual-root matching | Not established where normalized labels collide |
| All interpreted guest roots represented by compiled targets | NOT ESTABLISHED |
| Wall-clock performance or compilation times | NOT MEASURED |


**Evidence validation boundary:** The 85-file upload contains the derived JSON summaries and source manifests, not the raw `.bgv.gz` graphs nor bytecode execution log files. I can validate JSON internal structure and producer metadata and use the harness-certified `evidence_valid`/`capture_valid` flags, but cannot independently re-run IgvUtility or parse raw Bytecode DSL traces from this archive. The older cold summaries likewise lack their original `capture.json` producer identity manifests in this particular ZIP.

**Topology caveat:** `primitive-closure-call` and `primitive-method-call` each select one guest reference compilation in the stabilized comparison, despite cold Tier 2 capturing two separate compiled guest roots. These modes answer different questions and must remain separate. An isolated lower graph node count is not sufficient to infer faster code or equivalent control-flow and inlining semantics.

## 7. Conclusions and next investigation priorities for I115-C6

1. **The method-path graph reductions are independently supported:** `method-call` is 90 versus 127 H10 (**−37 nodes**), and `primitive-method-call` is 64 versus 99 (**−35 nodes**), on Tier 2 stable guest graphs with no residual Java invoke targets in the selected graphs.
2. **Closure calls remain the central structural regression candidate:** `primitive-closure-call` is **193 versus 106 H10 (+87)** and **193 versus 50 historical GraalPy (+143)**. It retains one `ProtosStandardObjectProtocol.rebuildCanonicalRootCallCertificate` invoke and higher counts of `FrameState`, branches and guards. Attribution of the +87 requires a same-workload physical graph comparison; these counts alone do not prove causality.
3. **Bytecode specializations are measurably active:** `c.GetMethod$Cached` and `c.CallBinaryMethod$Direct` fire 100,995 times each on the method loop; both fire 96 times on the primitive method case; `c.CallUnaryMethod$CallPFunction` fires 96 times on the closure case. Five generic occurrences remain in each corresponding call diagnostic.
4. **Do not misattribute `CopyArguments`:** the 101,000/101/101 diagnostic execution counts belong to distinct physical roots from the call-site roots, so they cannot by themselves explain the selected compiled caller-graph size.
5. **Two recursion workloads also grow:** `factorial` +198 nodes and `fibonacci` +291 relative to H10. Their stable references each contain two guest graphs; per-root source-level responsibility is not established from aggregate historical H10 totals.
6. **Twelve other stable graph totals are unchanged.** This includes all basic local, object-slot and simple control-flow primitives; preserved node totals do not automatically imply identical graph topology.
7. **Measure only when a new producer revision or a new experiment warrants it:** the submitted HEAD already has complete reference and interpreter capture coverage; further work should examine the specific closure certificate invoke and source-level call semantics, without redrawing conclusions from the host-adapter graph.

## 8. Sources, retained evidence, and reproducibility

- **Measured input:** `i115-c6-head-evidence.zip` (85 JSON files), supplied directly for this report. Directory groups: `reference/<workload>/protos/{capture.json,unit.json}`, `dsl/<workload>/protos/capture.json`, and `tier{1,2}/<workload>/protos/cold-summary.json`.
- **Protos source:** [`guillermomolina/protos` at `a185d7b1f3e9`](https://github.com/guillermomolina/protos/commit/a185d7b1f3e9d2d7c8b98929db48ced02108337e).
- **Harness source:** [`guillermomolina/protos-benchmarks` at `b77efb62c25a`](https://github.com/guillermomolina/protos-benchmarks/commit/b77efb62c25a9a6b05c6ec4d2c9f31721dd059f6).
- **Historical H10 source:** *I115-H10 — Comparación completa de Protos y GraalPy*, shared earlier in this conversation (30 October 2026); Tier 2 reference table only. The H10 producer SHA is not asserted here because it was not present in the historical summary.
- **Historical GraalPy:** GraalPy 25.4.4.1.1 Tier 2 table reproduced from the same H10 report; that report in turn cites [the reference campaign comparison](https://github.com/guillermomolina/protos-benchmarks/blob/main/reports/I115-H6_vs_H7-R5_Comparacion_completa_Protos_GraalPy.md). No fresh GraalPy work was run.
- **Audit CSVs in accompanying bundle:** `I115-C6_HEAD_case_matrix.csv`, `I115-C6_HEAD_compiled_roots.csv`, `I115-C6_HEAD_graal_node_classes.csv`, `I115-C6_HEAD_DSL_opcodes_by_root.csv`, `I115-C6_HEAD_DSL_opcodes_aggregate.csv`, `I115-C6_HEAD_bytecode_sizes.csv`. Every CSV row is derived exclusively from the supplied HEAD JSON records, except the explicitly labeled historical H10/GraalPy comparator columns in the case matrix.

---

*This is a read-only analysis of the recorded C6 HEAD. No program was executed, no compilation capture was rerun, and no source repository was changed to produce this report.*
