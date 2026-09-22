# PERF010-A measurement-discrimination investigation (#691 follow-up)

This is not a causal ablation. It measures this harness's own discrimination capability using a source-equivalent no-op variant (`PERF010A_NOOP`); any movement reported below is measurement movement/drift, never a Protos runtime effect, because the executed Protos runtime code cannot differ between the two variants compared here (see `NOOP_RUNTIME_PATH_EQUIVALENCE` and `raw.json`).

- Harness revision: `57cb307baad3346758d34aa3da1eda01997a4208`
- Protos revision (baseline and noop; single checkout, empty patch applied in-build for the noop image only): `4c4aa95a5852119bd280ceb40483871d5d2cbb82`
- Block order: `('A', 'B', 'A', 'B')` (deterministic AB/BA counterbalance; BASELINE_FIRST_ONLY=ABSENT).
- N=10,000. Warmup=20, steady=100 (unchanged reference scale).

## Per-workload no-op discrimination envelope

| workload | samples | min % | max % | median % | MAD % | floor % | order effect | Ablation 5 gate |
|---|---|---|---|---|---|---|---|---|
| micro/slot-read | 4 | -38.9049 | 11.7933 | -6.4728 | 11.9613 | 38.9049 | NOT_DETECTED | CLOSED |
| micro/closure-call | 4 | -34.8335 | 8.2006 | -6.3426 | 11.6344 | 34.8335 | DETECTED | CLOSED |
| micro/method-call | 4 | -10.8286 | -3.2091 | -5.2771 | 2.0532 | 10.8286 | DETECTED | CLOSED |
| runtime/monomorphic-dispatch | 4 | 0.9862 | 2.0901 | 1.1407 | 0.1078 | 2.0901 | NOT_DETECTED | OPEN |

## Existing ablations vs. this floor (descriptive only; historical conclusions unchanged)

| ablation | vs. floor |
|---|---|
| Ablation 1 | MIXED |
| Ablation 3 | MIXED |
| Ablation 4 | MIXED |

## ABLATION_5_MEASUREMENT_GATE = CLOSED

Minimum next methodological change: process/container lifecycle isolation between blocks, plus more counterbalanced blocks (extend block_order beyond AABB) to confirm whether the detected order effect is stable before trusting any paired-control comparison built on this fixed-order harness

This investigation does not select a production optimization, does not measure the already-established next causal candidate (invocation-time second `List.copyOf` of closure `capturedLexicalContexts`), and does not authorize Ablation 5 by itself.

