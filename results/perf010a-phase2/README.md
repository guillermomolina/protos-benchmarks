# PERF010-A Phase 2 clean two-product-revision causal comparator Evidence Unit

does correcting the accidentally polymorphic/megamorphic call-site identity produce a causal runtime speedup, and is it potentially relevant to the large PERF010-A performance gap under investigation?

- Harness revision: `952cfd1290023a04108854163da30ba48b18b3c6`
- Control Protos revision (VARIANT=baseline): `2b3a88389da7228caed231a90b14091cf2841115`
- Intervention Protos revision (VARIANT=baseline): `3e8e6b565c95eb5098c2168d241536ba13ad19e9`
- Patches applied to either image: NONE (see `patches_applied` and `PHASE2_BOTH_IMAGES_ABLATION_SLICE_NONE` in the run log).
- Built image identity: `{"control": {"id": "sha256:db2359af416d83d5f34153433b9ac576848fe841f7e2167d54b52095f5a2ad0c", "repo_digests": [], "tag": "protos-benchmarks-perf010a-ablation0-phase2-baseline:2b3a88389da7"}, "intervention": {"id": "sha256:2a828e7558782a2fe1a338115f3a3609575c6c881a333d1e8d4a4d2cf1312df4", "repo_digests": [], "tag": "protos-benchmarks-perf010a-ablation0-phase2-baseline:3e8e6b565c95"}}`
- Block order: `['A', 'B', 'A', 'B']` (A: control first; B: intervention first).
- N=10000. Warmup=120, steady=100.
- Full four-workload matrix: YES.
- Evidence status: `RETAINED`.

`canonical_improvement = control_canonical_median_ns - intervention_canonical_median_ns; control_movement = control_workload_control_median_ns - intervention_workload_control_median_ns; paired_control_effect = canonical_improvement - control_movement. A positive paired_control_effect means INTERVENTION is faster than CONTROL once the workload-control's own measured movement between the two revisions/images has been subtracted out.`

## Per-workload paired-control effect (descriptive only)

| workload | samples | min % | max % | median % | MAD % | order effect |
|---|---|---|---|---|---|---|
| micro/slot-read | 4 | -3.5386 | 7.3428 | -0.8099 | 1.8959 | DETECTED |
| micro/closure-call | 4 | -3.6938 | 4.4621 | 0.6864 | 2.3153 | DETECTED |
| micro/method-call | 4 | 4.9668 | 21.8355 | 8.0144 | 2.4655 | NOT_DETECTED |
| runtime/monomorphic-dispatch | 4 | 9.4429 | 21.5429 | 11.2206 | 1.5371 | NOT_DETECTED |

## Stationarity (first-quarter vs. last-quarter of each 100-sample steady timed unit)

See `stationarity.tsv` for the full per-timed-unit table (raw `raw.json` remains authoritative).

## CAUSAL_RUNTIME_SPEEDUP = NOT_MEASURED
## DOMINANT_GAP_CAUSE = NOT_ESTABLISHED
## ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED

This implementation slice deliberately does not classify any of the three fields above, and does not decide REAL_BUT_SMALL vs. MATERIAL vs. ORDER_OF_MAGNITUDE_RELEVANT - see AGENTS.work/PERFORMANCE.md and config/perf010a-phase2.json's `not_decided_by_this_evidence_unit`. The next investigation slice classifies them from this Evidence Unit's raw retained data.

