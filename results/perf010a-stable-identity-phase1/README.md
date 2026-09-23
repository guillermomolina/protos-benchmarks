# PERF010-A Phase 1 stable-identity measurement-system-admission Evidence Unit

This is measurement-system admission, not a causal ablation and not the Phase 2 two-product-revision comparison. Like the historical warmup=20 no-op discrimination experiment it is derived from, the executed Protos runtime path cannot differ between its 'baseline' and 'ablation' (no-op) images (see `PHASE1_NOOP_RUNTIME_PATH_EQUIVALENCE` and `raw.json`), so any movement reported below is measurement movement, never a Protos runtime effect.

- Harness revision: `43cc0ba7b70b624cf30d30d2be2bd27144223b5d`
- Protos revision (baseline and noop; single checkout, empty patch applied in-build for the noop image only): `4c4aa95a5852119bd280ceb40483871d5d2cbb82`
- Built image identity: `{"ablation": {"id": "sha256:e19263a02d50733276b5277efd10b779a7a5042aed726ee25bfb02503492569c", "repo_digests": [], "tag": "protos-benchmarks-perf010a-ablation0-phase1-ablation:4c4aa95a5852"}, "baseline": {"id": "sha256:e93df254f93acf363dd9dd2a371dd0921af87af34a614c3d48dcb9371e99d521", "repo_digests": [], "tag": "protos-benchmarks-perf010a-ablation0-phase1-baseline:4c4aa95a5852"}}`
- Block order: `['A', 'B', 'A', 'B']`.
- N=10000. Warmup=120, steady=100 (warmup changed from the historical 20; steady unchanged).
- Full four-workload matrix: YES.
- Evidence status: `RETAINED`.

## Per-workload no-op discrimination envelope (descriptive only)

| workload | samples | min % | max % | median % | MAD % | floor % | order effect |
|---|---|---|---|---|---|---|---|
| micro/slot-read | 4 | -18.0369 | 1.2636 | -3.6378 | 4.3087 | 18.0369 | NOT_DETECTED |
| micro/closure-call | 4 | -22.0052 | 13.7317 | 4.9642 | 8.4149 | 22.0052 | NOT_DETECTED |
| micro/method-call | 4 | -20.7861 | 12.6580 | 2.3226 | 6.8021 | 20.7861 | DETECTED |
| runtime/monomorphic-dispatch | 4 | -10.2675 | 18.3575 | 1.9121 | 8.7433 | 18.3575 | DETECTED |

## Stationarity (first-quarter vs. last-quarter of each 100-sample steady timed unit)

See `stationarity.tsv` for the full per-timed-unit table (raw `raw.json` remains authoritative).

## WARMUP_120_STABILITY_HYPOTHESIS = PENDING_NEXT_SLICE
## MEASUREMENT_GATE = PENDING_NEXT_SLICE

This implementation slice deliberately does not classify either field above - see AGENTS.work/PERFORMANCE.md and the readiness record this Evidence Unit implements (guillermomolina/protos-project-docs@67bd25de851f68d82ab571efab0453f9e34f717a). The next investigation slice classifies them from this Evidence Unit's raw retained data.

This Evidence Unit does not select a production optimization and does not implement or execute the separate Phase 2 two-product-revision comparison.

