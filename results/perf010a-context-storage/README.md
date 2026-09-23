# PERF010-A Tier-B execution-context storage causal Evidence Unit

Harness revision: `67002c702fe293b869ba8bda34814be6b7076136`
Protos revision: `3e8e6b565c95eb5098c2168d241536ba13ad19e9`
CONTROL is clean; INTERVENTION is the same Protos revision plus the diagnostic context-storage patch.
Structural and correctness gates passed before timing. No JFR/compiler tracing/IGV was used.

| workload | blocks % | median % | MAD % |
|---|---|---:|---:|
| micro/slot-read | -3.4494, -19.9263, -38.9760, -13.1197 | -16.5230 | 8.2384 |
| micro/closure-call | 3.5848, -1.8570, -3.1761, 11.7683 | 0.8639 | 3.3804 |
| micro/method-call | -7.4609, -4.0431, 1.9584, -5.5428 | -4.7930 | 1.7089 |
| runtime/monomorphic-dispatch | -2.7512, -0.3411, 6.2401, -3.4121 | -1.5462 | 1.5355 |

PRIMARY_EFFECT_SCALE=NO_CLEAR_EFFECT
TIER_B_CONTEXT_STORAGE_BIG_COST=NO
CANDIDATE_DISPOSITION=NO_MATERIAL_CAUSAL_EFFECT

