# PERF001-F reference evidence summary

- Evidence class: retained H4 reference evidence
- Protos revision: `0372a58addc63f305c911811659edd9b2b508420`
- Harness revision: `b8a9eeca85c241f544512a02a6fa29d935f240ef`
- Statistics: median, MAD, nearest-rank p95, min, max.
- Scaling speedup/efficiency: steady median only, strong-scaling workloads only.

| workload | width | startup median ns | steady median ns | speedup | efficiency |
| --- | ---: | ---: | ---: | ---: | ---: |
| `concurrency/future-roundtrip` | 1 | 1809157737.5 | 138067141.0 |  |  |
| `concurrency/future-fanout-all` | 1 | 2781615848.5 | 411950901.0 |  |  |
| `concurrency/parallel-roundtrip` | 1 | 1652860313.5 | 60405257.0 |  |  |
| `concurrency/parallel-array-map` | 1 | 3769023460.5 | 343126619.0 | 1.000 | 1.000 |
| `concurrency/parallel-array-map` | 2 | 2041081347.5 | 245557858.0 | 1.397 | 0.699 |
| `concurrency/parallel-array-map` | 4 | 1507932999.5 | 132915030.0 | 2.582 | 0.645 |
| `concurrency/parallel-array-map` | 8 | 1507119107.5 | 82315936.5 | 4.168 | 0.521 |
| `concurrency/actor-request-roundtrip` | 1 | 1607492596.5 | 78068353.5 |  |  |
| `concurrency/actor-fanout-requests` | 1 | 1780755521.5 | 72693617.5 | 1.000 | 1.000 |
| `concurrency/actor-fanout-requests` | 2 | 952406447.5 | 33505990.0 | 2.170 | 1.085 |
| `concurrency/actor-fanout-requests` | 4 | 702915585.5 | 30936657.5 | 2.350 | 0.587 |
| `concurrency/actor-fanout-requests` | 8 | 686726801.0 | 30977989.0 | 2.347 | 0.293 |

Raw ordered startup, warmup and steady samples remain authoritative in `evidence.json`.
