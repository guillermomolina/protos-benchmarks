# PERF010-A Phase 2 clean two-product-revision causal comparator Evidence Unit

How much does performance change from PERF013 B1 to PERF013 B2 when the Protos revision is the only product variable?

- Harness revision: `2cc6cfe1216b154b629de77c8321753de51b857c`
- Control Protos revision (VARIANT=baseline): `c498f35a383447c21fa0b63c3414857e777e5300`
- Intervention Protos revision (VARIANT=baseline): `0af8960363a557dad1b87968cf8a632e4716ee8a`
- Patches applied to either image: NONE (see `patches_applied` and `PHASE2_BOTH_IMAGES_ABLATION_SLICE_NONE` in the run log).
- Built image identity: `{"control": {"id": "sha256:1c8aaf3f3881338ca719b41b16857463daf71bf0286833b0156f774b7e363419", "repo_digests": [], "tag": "protos-benchmarks-perf013b1-baseline:c498f35a3834"}, "intervention": {"id": "sha256:d6232fe09c5863f4b1a2a166819a6c0d01aa1cc68407834dce630c19be0bfc1c", "repo_digests": [], "tag": "protos-benchmarks-perf013-b2-gate:0af8960363a5"}}`
- Block order: `['A', 'B', 'A', 'B']` (A: control first; B: intervention first).
- N=10000. Warmup=120, steady=100.
- Full four-workload matrix: YES.
- Evidence status: `RETAINED`.

`canonical_improvement = control_canonical_median_ns - intervention_canonical_median_ns; control_movement = control_workload_control_median_ns - intervention_workload_control_median_ns; paired_control_effect = canonical_improvement - control_movement. A positive paired_control_effect means INTERVENTION is faster than CONTROL once the workload-control's own measured movement between the two revisions/images has been subtracted out.`

## Per-workload paired-control effect (descriptive only)

| workload | samples | min % | max % | median % | MAD % | order effect |
|---|---|---|---|---|---|---|
| micro/slot-read | 4 | -4.2264 | 7.6050 | -2.6010 | 1.4354 | NOT_DETECTED |
| micro/closure-call | 4 | -4.8287 | 4.1312 | -0.3920 | 2.8168 | NOT_DETECTED |
| micro/method-call | 4 | -1.2596 | 23.0845 | 18.8301 | 2.4379 | NOT_DETECTED |
| runtime/monomorphic-dispatch | 4 | 15.7889 | 24.4639 | 22.9525 | 1.3906 | NOT_DETECTED |

## Stationarity (first-quarter vs. last-quarter of each 100-sample steady timed unit)

See `stationarity.tsv` for the full per-timed-unit table (raw `raw.json` remains authoritative).

## CAUSAL_RUNTIME_SPEEDUP = NOT_MEASURED
## DOMINANT_GAP_CAUSE = NOT_ESTABLISHED
## ATTRIBUTABLE_FRACTION = NOT_ESTABLISHED

This implementation slice deliberately does not classify any of the three fields above, and does not decide REAL_BUT_SMALL vs. MATERIAL vs. ORDER_OF_MAGNITUDE_RELEVANT - see AGENTS.work/PERFORMANCE.md and config/perf010a-phase2.json's `not_decided_by_this_evidence_unit`. The next investigation slice classifies them from this Evidence Unit's raw retained data.

