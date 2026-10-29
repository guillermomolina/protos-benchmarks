# GraalJS and GraalPy peer measurements

Capture date: 2026-10-29.

These measurements cover the five peer workloads modified
by harness commit `6688145`.

## Scope

- Languages: GraalJS and GraalPy.
- Runtime version: 25.4.4.1.1.
- Harness revision: `6688145f15b982f0315416aa964fdca757547cf1`.
- CPU affinity: CPU 1.
- Stage: reference.
- Profile: none.
- Temperature: both.
- Ten steady samples per capture.
- No Protos performance measurements were executed.

The original metadata, summaries, correctness logs and
timing logs are preserved under `runs/`.

The manifest records the SHA-256 of each original file.

## Measurement results

The following hot timings are in nanoseconds per call.

| Workload | Language | Minimum | Median | Max/min |
| --- | --- | ---: | ---: | ---: |
| factorial | js | 91770.000 | 103186.500 | 78.28 |
| factorial | python | 107992.000 | 117038.500 | 1.26 |
| fibonacci | js | 225890.000 | 266300.500 | 29.23 |
| fibonacci | python | 312547.000 | 455213.000 | 20.38 |
| integer-loop | js | 22668.000 | 23918.000 | 257.34 |
| integer-loop | python | 19876.000 | 20269.500 | 1.12 |
| method-call | js | 34286.000 | 35131.000 | 1.09 |
| method-call | python | 37054.000 | 52894.500 | 227.57 |
| primitive-method-call | js | 28.488 | 32.898 | 11.85 |
| primitive-method-call | python | 154.851 | 348.000 | 3.27 |

## Interpretation

All ten captures reported correctness PASS and
MEASUREMENT_VALID=YES.

All ten were marked reference eligible.

Reference eligibility does not establish statistical
stability.

Seven of the ten captures have a maximum steady sample
more than twice their minimum.

The harness reports the minimum observed steady time per
call after fixed warmup. It does not require convergence.

These records preserve experimental evidence. They must
not be treated as a statistically established performance
baseline or used for unqualified language rankings.

Cold timings represent the first guest invocation after
Polyglot context setup, not JVM or process startup.

The original raw samples and environment identities
remain available in each capture.

## Reproducibility

Refer to `manifest.json` and each capture's
`metadata.json` for exact producer, runtime, container,
host and measurement-policy identities.
