# PERF014 direct Closure-call final causal timing Evidence Unit

How much does the final PERF014 direct Closure-call implementation reduce the steady-state cost of a guest Closure call, once the workload-control's own measured movement between the two product revisions has been subtracted out? PERF014's structural validation passing does not by itself establish how much of the guest-call cost was actually recovered - this Evidence Unit is the causal-attribution owner for that question. The predeclared PERF014 prediction is that the closure-call-minus-workload-control guest-call increment falls by a clearly multiplicative factor once the intervention is in place; this harness retains the numbers needed to evaluate that prediction (see guest_call_increment_formula) but deliberately does not itself decide whether "clearly multiplicative" is satisfied - see timing_classification_note.

- Harness revision: `92f5dbcf7d54ac048763f85946c973a25fbde241`
- Control Protos revision (VARIANT=baseline): `0af8960363a557dad1b87968cf8a632e4716ee8a` (`0.3.102-SNAPSHOT`) - PERF013 B2.
- Intervention Protos revision (VARIANT=baseline): `bcf9eda164d840b0a0b4201753fe5289347afa8a` (`0.3.105-SNAPSHOT`) - final PERF014 product.
- Intervening unrelated revision in the intervention's ancestry (BUG010, not PERF014): `eab6a367c16dea0136e1aabb13a7da681c4839b0` (`0.3.104-SNAPSHOT`).
- Patches applied to either image: NONE (see `patches_applied` and `PERF014_BOTH_IMAGES_ABLATION_SLICE_NONE` in the run log).
- Built image identity: `{"control": {"id": "sha256:ec3d528a2c6a323e1aced942e553699e2a19333d701797c27fe047fc947b6ed1", "repo_digests": [], "tag": "protos-benchmarks-perf014-control:0af8960363a5"}, "intervention": {"id": "sha256:ed4f9f6bde284ba3f078b72ba9c0ad06243786a6dbfa41261ace67c15ac9a0df", "repo_digests": [], "tag": "protos-benchmarks-perf014-intervention:bcf9eda164d8"}}`
- Workload source SHA-256 identity (control == intervention for every workload): `{"micro/closure-call": {"control": "3abc1c42fb096be91cba81c407d5d10337ed9ee014fb85d3db49cc94951683c0", "intervention": "3abc1c42fb096be91cba81c407d5d10337ed9ee014fb85d3db49cc94951683c0"}, "micro/method-call": {"control": "f5bf5c66879fed0dcbd6a561677753c08d88567be257d4fd122c27d1b996cc2a", "intervention": "f5bf5c66879fed0dcbd6a561677753c08d88567be257d4fd122c27d1b996cc2a"}, "micro/slot-read": {"control": "e40309a8e581854b5d1dea938219c99d5439e2d7ed38c740a9b94a54e283bd5c", "intervention": "e40309a8e581854b5d1dea938219c99d5439e2d7ed38c740a9b94a54e283bd5c"}, "runtime/monomorphic-dispatch": {"control": "79d627cad46837f2a996a164adeee0ec46619edb838ce7601b65a630b15751b8", "intervention": "79d627cad46837f2a996a164adeee0ec46619edb838ce7601b65a630b15751b8"}}`
- Block order: `['A', 'B', 'A', 'B']` (A: control first; B: intervention first).
- N=10000. Warmup=120, steady=100.
- Full four-workload matrix: YES.
- Evidence status: `RETAINED`.

`canonical_improvement = control_canonical_median_ns - intervention_canonical_median_ns; control_movement = control_workload_control_median_ns - intervention_workload_control_median_ns; paired_control_effect = canonical_improvement - control_movement. A positive paired_control_effect means INTERVENTION is faster than CONTROL once the workload-control's own measured movement between the two revisions/images has been subtracted out. Reused unchanged from config/perf010a-post-i072-fprime.json's causal_formula.`

## Per-workload paired-control effect (descriptive only)

| workload | classification | samples | min % | max % | median % | MAD % | order effect |
|---|---|---|---|---|---|---|---|
| micro/slot-read | NEGATIVE_COVERAGE | 4 | -4.2230 | 3.3322 | -1.5693 | 2.5923 | NOT_DETECTED |
| micro/closure-call | PRIMARY | 4 | 1.3438 | 13.7850 | 6.0407 | 3.8416 | DETECTED |
| micro/method-call | NEGATIVE_COVERAGE | 4 | -4.8951 | 16.7029 | 0.8368 | 3.9933 | DETECTED |
| runtime/monomorphic-dispatch | NEGATIVE_COVERAGE | 4 | -6.5764 | 6.6640 | 2.8522 | 3.3233 | NOT_DETECTED |

## Guest-call increment (`micro/closure-call` only, PERF014-specific)

`PERF014-specific, micro/closure-call only, additional to and never a replacement for causal_formula's paired_control_effect. Per block: CONTROL_GUEST_CALL_INCREMENT = control_canonical_median_ns - control_workload_control_median_ns; INTERVENTION_GUEST_CALL_INCREMENT = intervention_canonical_median_ns - intervention_workload_control_median_ns; GUEST_CALL_INCREMENT_REDUCTION = CONTROL_GUEST_CALL_INCREMENT - INTERVENTION_GUEST_CALL_INCREMENT. GUEST_CALL_INCREMENT_RATIO = CONTROL_GUEST_CALL_INCREMENT / INTERVENTION_GUEST_CALL_INCREMENT only when both increments are strictly positive, else NOT_APPLICABLE. The retained Evidence Unit reports this both per block (so ratio/reduction stability can be inspected across the 4 blocks rather than trusted from a single aggregate quotient) and as an aggregate (median of the 4 per-block increments, with the ratio taken from the two aggregate medians).`

| quantity | median | MAD | min | max |
|---|---|---|---|---|
| control guest-call increment (ns) | 31476780.8 | 2015476.5 | 29381204.5 | 33528350.0 |
| intervention guest-call increment (ns) | 24077258.5 | 2879278.2 | 20965636.5 | 32221696.5 |
| guest-call increment reduction (ns) | 5362042.2 | - | 1234468.0 | 12562713.5 |

- Ratio of aggregate medians (control / intervention): `1.3073241187322053`.
- Per-block control increments (ns): `[29497397.0, 33528350.0, 33456164.5, 29381204.5]`.
- Per-block intervention increments (ns): `[26724193.0, 20965636.5, 32221696.5, 21430324.0]`.
- Per-block reductions (ns): `[2773204.0, 12562713.5, 1234468.0, 7950880.5]`.
- Per-block ratios: `[1.103771290680321, 1.5992049657066219, 1.0383117009372862, 1.3710107462677652]`.

## Stationarity (first-quarter vs. last-quarter of each 100-sample steady timed unit)

See `stationarity.tsv` for the full per-timed-unit table (raw `raw.json` remains authoritative).

## PERF014_TIMING_CLASSIFICATION = NOT_CLASSIFIED
## PERF014_CLEARLY_MULTIPLICATIVE = NOT_CLASSIFIED
## PERF015_AUTHORIZED = NO

This implementation slice deliberately does not classify the three fields above from the per-workload table or the guest-call increment summary - see AGENTS.work/PERFORMANCE.md and `config/perf014-direct-closure-call.json`'s `timing_classification_note`. No threshold (2x, 5x, 10x, ...) is hardcoded anywhere in this harness for that decision; the classification is a later interpretation step performed against this Evidence Unit's raw retained data, not part of this harness.

