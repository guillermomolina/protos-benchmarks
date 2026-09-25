# PERF010-A post-I068 current cross-language baseline

- Harness revision: `d6d96f22775a743f604c1645731fa7ebf0ac7ca4`
- Product revision: `f1cee2d85858804ad3775adf43a9fab97664da2a`
- Product version: `0.3.87-SNAPSHOT`
- Historical comparison: `results/perf004-a` at harness `60dbce7faf5510bd1bd6867a866aa7ca69c48637` / Protos `4a03efc15620b37b2e418b3df30b4a26486446ec`.
- Historical comparison is descriptive, not causal attribution to I068.
- Persistent forks: 5 per language/workload.
- Warmup: 120 iterations per fork.
- Steady: 100 ordered samples per fork.
- Network: none. CPU: one explicit cpuset CPU. Same host for all compared runtimes.
- JFR/compiler tracing/IGV/allocation instrumentation: disabled for timing.
- Correctness: PASS 15/15 before reference timing.

Raw ordered samples are authoritative in `raw.json`; `summary.json`, `summary.tsv`, and this README are derived views.

## Primary common path

| workload | historical Protos/Node | current Protos/Node | historical Protos/Python | current Protos/Python | current Protos median ns | current Node median ns | current Python median ns |
|---|---:|---:|---:|---:|---:|---:|---:|
| micro/slot-read | 424.762469 | 1022.793547 | 31.245163 | 38.628826 | 60626087.5 | 59275.0 | 1569452.0 |
| micro/closure-call | 773.591568 | 1615.329446 | 38.250756 | 50.861539 | 88019301.5 | 54490.0 | 1730567.0 |
| micro/method-call | 438.509381 | 1385.502659 | 31.663089 | 49.722209 | 87286667.5 | 63000.0 | 1755486.5 |
| runtime/monomorphic-dispatch | 444.984786 | 1290.639089 | 31.169229 | 47.481349 | 84427156.0 | 65415.0 | 1778112.0 |

## Secondary recursive scale sentinel

The factorial row is retained only as a recursive scale sentinel and is not generalized into the common-overhead result.

| workload | historical Protos/Node | current Protos/Node | historical Protos/Python | current Protos/Python | current Protos median ns | current Node median ns | current Python median ns |
|---|---:|---:|---:|---:|---:|---:|---:|
| algorithms/factorial/recursive | 4821.166827 | 12203.756962 | 3798.495076 | 3708.064615 | 4820484.0 | 395.0 | 1300.0 |

## Descriptive gap movement

`summary.tsv` records `current gap / historical gap` separately for Node and Python on every workload. These are descriptive movements across many product revisions, not an I068 speedup or attributable fraction.

## Machine-readable conclusions

```text
PERF010A_POST_I068_BASELINE=ESTABLISHED
PRODUCT_REVISION=f1cee2d85858804ad3775adf43a9fab97664da2a
POST_I068_COMMON_GAP_SCALE=PER_WORKLOAD_RANGES_ONLY
POST_I068_COMMON_PROTOS_OVER_NODE_RANGE=1022.793547..1615.329446
POST_I068_COMMON_PROTOS_OVER_PYTHON_RANGE=38.628826..50.861539
POST_I068_FACTORIAL_PROTOS_OVER_NODE=12203.756962
POST_I068_FACTORIAL_PROTOS_OVER_PYTHON=3708.064615
HISTORICAL_COMPARISON_SOURCE=results/perf004-a
HISTORICAL_COMPARISON_CAUSAL=NO
I068_ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED
PERF010A_DOMINANT_CAUSE=NOT_ESTABLISHED
ATTRIBUTABLE_FRACTION=NOT_ESTABLISHED
PRODUCTION_OPTIMIZATION_SELECTED=NO
PERF010_READY=NO
```
