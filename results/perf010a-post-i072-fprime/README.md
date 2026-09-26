# PERF010-A post-I072 Candidate F' causal two-revision comparator Evidence Unit

What is the causal steady-state runtime effect of the complete I072 F' implementation on the established common-path workloads? I072's structural success (Phases A-E landing) does not by itself establish how much performance was recovered - this Evidence Unit is the causal-attribution owner for that question.

- Harness revision: `113949a1aebc0eb769a16b35368a8738f38102a4`
- Control Protos revision (VARIANT=baseline): `2d8f04a8a01ff8639e98e03fba9a176170d54936` (`0.3.89-SNAPSHOT`)
- Intervention Protos revision (VARIANT=baseline): `cf9b39b25dc9a3c4cd1c538749c3a363760ae45b` (`0.3.96-SNAPSHOT`)
- Patches applied to either image: NONE (see `patches_applied` and `POST_I072_FPRIME_BOTH_IMAGES_ABLATION_SLICE_NONE` in the run log).
- Built image identity: `{"control": {"id": "sha256:6c84d5958f2ecc913ff0d5ac7c480dfb6ae4f84d1352675270bc525c05d34c52", "repo_digests": [], "tag": "protos-benchmarks-perf010a-post-i072-fprime-control:2d8f04a8a01f"}, "intervention": {"id": "sha256:1f9b7d1fca47a05f35a7e0291fb89ad5c456a7ed7758bf092a39c526f77a8f50", "repo_digests": [], "tag": "protos-benchmarks-perf010a-post-i072-fprime-intervention:cf9b39b25dc9"}}`
- Workload source SHA-256 identity (control == intervention for every workload): `{"micro/closure-call": {"control": "3abc1c42fb096be91cba81c407d5d10337ed9ee014fb85d3db49cc94951683c0", "intervention": "3abc1c42fb096be91cba81c407d5d10337ed9ee014fb85d3db49cc94951683c0"}, "micro/method-call": {"control": "f5bf5c66879fed0dcbd6a561677753c08d88567be257d4fd122c27d1b996cc2a", "intervention": "f5bf5c66879fed0dcbd6a561677753c08d88567be257d4fd122c27d1b996cc2a"}, "micro/slot-read": {"control": "e40309a8e581854b5d1dea938219c99d5439e2d7ed38c740a9b94a54e283bd5c", "intervention": "e40309a8e581854b5d1dea938219c99d5439e2d7ed38c740a9b94a54e283bd5c"}, "runtime/monomorphic-dispatch": {"control": "79d627cad46837f2a996a164adeee0ec46619edb838ce7601b65a630b15751b8", "intervention": "79d627cad46837f2a996a164adeee0ec46619edb838ce7601b65a630b15751b8"}}`
- Block order: `['A', 'B', 'A', 'B']` (A: control first; B: intervention first).
- N=10000. Warmup=120, steady=100.
- Full four-workload matrix: YES.
- Evidence status: `RETAINED`.

`canonical_improvement = control_canonical_median_ns - intervention_canonical_median_ns; control_movement = control_workload_control_median_ns - intervention_workload_control_median_ns; paired_control_effect = canonical_improvement - control_movement. A positive paired_control_effect means INTERVENTION is faster than CONTROL once the workload-control's own measured movement between the two revisions/images has been subtracted out. Reused unchanged from config/perf010a-phase2.json's causal_formula.`

## Per-workload paired-control effect (descriptive only)

| workload | classification | samples | min % | max % | median % | MAD % | order effect |
|---|---|---|---|---|---|---|---|
| micro/slot-read | NEGATIVE_COVERAGE | 4 | -0.2892 | 31.5646 | 8.6025 | 5.7131 | DETECTED |
| micro/closure-call | PRIMARY | 4 | -3.7263 | 0.5080 | -0.9754 | 0.9588 | DETECTED |
| micro/method-call | PRIMARY | 4 | -4.3103 | 1.1318 | -2.3899 | 1.4878 | NOT_DETECTED |
| runtime/monomorphic-dispatch | PRIMARY | 4 | -6.6638 | 0.7208 | -4.4496 | 1.7341 | DETECTED |

## Stationarity (first-quarter vs. last-quarter of each 100-sample steady timed unit)

See `stationarity.tsv` for the full per-timed-unit table (raw `raw.json` remains authoritative).

## I072_FPRIME_CAUSAL_EFFECT = NOT_CLASSIFIED
## I072_FPRIME_BIG_COST = NOT_CLASSIFIED
## PERF010A_DOMINANT_CAUSE = NOT_ESTABLISHED
## ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED
## NEXT_CAUSAL_BOUNDARY = NOT_ESTABLISHED
## PRODUCTION_OPTIMIZATION_SELECTED = NO

This implementation slice deliberately does not classify the six fields above from the per-workload table - see AGENTS.work/PERFORMANCE.md and `config/perf010a-post-i072-fprime.json`'s `scale_classification_note`. The scale classification (LARGE_MULTI_X / MATERIAL_PERCENT_SCALE / SMALL_PERCENT_SCALE / NEAR_ZERO / REGRESSION / INCONCLUSIVE) is a later interpretation step performed against this Evidence Unit's raw retained data, not part of this harness.

