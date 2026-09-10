# PERF001 baseline report

Status: REPRODUCIBILITY PASS

This report closes the PERF001-G reporting question using the owner-approved bounded exact-pin replay. It does **not** create replacement timing samples or compare incompatible benchmark generations. Timing values below are derived views of the already-retained PERF001-D/E/F evidence and remain scoped to their exact historical revisions and environments.

## Reproducibility gate

- PERF001-D exact historical correctness replay: `44/44` PASS.
- PERF001-E exact historical correctness replay: `18/18` PASS.
- PERF001-F exact H3 non-retained smoke: `12/12` PASS with `2 startup / 2 warmup / 2 steady`; replay timings retained: **NO**.
- Retained D/E/F result subtree identity against companion evidence commit `f34e37da11f209aa9f9ea84465822c3362fc4da0`: PASS.
- Timing drift threshold: **NONE**; timing values are observations, not reproducibility pass/fail criteria.

## Provenance

- PERF001-D harness: `0a406373c497df1173ff26a3ed4fcada015e0879`.
- PERF001-E harness: `280173d743b2ed838a89be0ad930b20828d89558`.
- PERF001-F H3 harness: `b8a9eeca85c241f544512a02a6fa29d935f240ef`.
- PERF001-F H4 / D+E+F retained evidence authority: `f34e37da11f209aa9f9ea84465822c3362fc4da0`.
- PERF001-G harness: `2fad6741b429c3e8d69683806e3aadc64f0812cf`.

## PERF001-D — Protos pre/post PERF002

Source authority: `results/perf001-d/summary.md`.

Status: PUBLISHED_AWAITING_PROTOS_LEDGER

- Harness revision: `0a406373c497df1173ff26a3ed4fcada015e0879`
- Pre-PERF002 Protos revision: `8f363d0146164f99e72210eb44667f4efb7b88e7`
- Post-PERF002 Protos revision: `3c93912a5579326374782a43527fbb51046f8f91`
- Stack: `-Xss128m`
- CPU set: `0`
- Startup samples: `10` per workload/mode/revision
- Warmup curve: `20` retained iterations
- Steady samples: `20` after warmup
- Truffle compilation tracing: separate non-timing diagnostic runs only

## Steady-state medians and pre/post ratios

| Workload | Mode | Pre median ns | Post median ns | Pre/Post |
|---|---|---:|---:|---:|
| `micro/slot-read` | interpreter | 40373591.5 | 35884723.5 | 1.125 |
| `micro/slot-read` | truffle | 32789252.0 | 40128963.0 | 0.817 |
| `micro/slot-write` | interpreter | 43901976.0 | 37802422.0 | 1.161 |
| `micro/slot-write` | truffle | 45275378.0 | 39804769.5 | 1.137 |
| `micro/closure-call` | interpreter | 48174091.0 | 80955281.5 | 0.595 |
| `micro/closure-call` | truffle | 35412167.0 | 39939345.5 | 0.887 |
| `micro/method-call` | interpreter | 41683547.5 | 38884890.0 | 1.072 |
| `micro/method-call` | truffle | 33850516.5 | 39594726.5 | 0.855 |
| `micro/object-creation` | interpreter | 39512541.5 | 36053504.0 | 1.096 |
| `micro/object-creation` | truffle | 36300274.5 | 32488986.5 | 1.117 |
| `micro/delegation-shallow` | interpreter | 35461949.0 | 27316577.5 | 1.298 |
| `micro/delegation-shallow` | truffle | 54765230.5 | 33048407.0 | 1.657 |
| `micro/delegation-deep` | interpreter | 39678448.5 | 33873358.5 | 1.171 |
| `micro/delegation-deep` | truffle | 40639219.0 | 41574901.5 | 0.977 |
| `runtime/monomorphic-dispatch` | interpreter | 36690834.0 | 32058433.0 | 1.144 |
| `runtime/monomorphic-dispatch` | truffle | 32900012.5 | 40781320.5 | 0.807 |
| `runtime/polymorphic-dispatch` | interpreter | 34483786.0 | 37288730.5 | 0.925 |
| `runtime/polymorphic-dispatch` | truffle | 37746242.5 | 42163489.0 | 0.895 |
| `algorithms/factorial/recursive` | interpreter | 384534.0 | 509739.0 | 0.754 |
| `algorithms/factorial/recursive` | truffle | 325129.5 | 199015.0 | 1.634 |
| `algorithms/fibonacci/recursive` | interpreter | 4536038342.0 | 4217816610.5 | 1.075 |
| `algorithms/fibonacci/recursive` | truffle | 4447850321.0 | 4711400384.5 | 0.944 |

## Truffle diagnostics

| Revision | Workload | rc | opt done | opt failed | GraphTooBig | Frame escape | Deep inlining | Stack overflow | Bootstrap error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pre-perf002 | `micro/slot-read` | 0 | 6 | 3 | 0 | 3 | 0 | 0 | 0 |
| post-perf002 | `micro/slot-read` | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `micro/slot-write` | 0 | 6 | 3 | 0 | 3 | 0 | 0 | 0 |
| post-perf002 | `micro/slot-write` | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `micro/closure-call` | 0 | 8 | 4 | 0 | 4 | 0 | 0 | 0 |
| post-perf002 | `micro/closure-call` | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `micro/method-call` | 0 | 8 | 4 | 0 | 4 | 0 | 0 | 0 |
| post-perf002 | `micro/method-call` | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `micro/object-creation` | 0 | 6 | 4 | 0 | 4 | 0 | 0 | 0 |
| post-perf002 | `micro/object-creation` | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `micro/delegation-shallow` | 0 | 6 | 3 | 0 | 3 | 0 | 0 | 0 |
| post-perf002 | `micro/delegation-shallow` | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `micro/delegation-deep` | 0 | 6 | 3 | 0 | 3 | 0 | 0 | 0 |
| post-perf002 | `micro/delegation-deep` | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `runtime/monomorphic-dispatch` | 0 | 8 | 4 | 0 | 4 | 0 | 0 | 0 |
| post-perf002 | `runtime/monomorphic-dispatch` | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `runtime/polymorphic-dispatch` | 0 | 8 | 4 | 0 | 4 | 0 | 0 | 0 |
| post-perf002 | `runtime/polymorphic-dispatch` | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `algorithms/factorial/recursive` | 0 | 1 | 1 | 0 | 1 | 0 | 0 | 0 |
| post-perf002 | `algorithms/factorial/recursive` | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| pre-perf002 | `algorithms/fibonacci/recursive` | 0 | 4 | 2 | 0 | 2 | 0 | 0 | 0 |
| post-perf002 | `algorithms/fibonacci/recursive` | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |

Raw samples, per-class schema-compatible result JSON, environment/image identity,
and diagnostic stdout/stderr are retained alongside this report.

The pre/post ratios are intentionally scoped to each exact workload and runtime
mode. They must not be generalized into a whole-language speed claim.

## PERF001-E — Sequential collections cross-language

Source authority: `results/perf001-e/summary.md`.

- Protos revision: `86b35d8bb2d7ab2ad54bc2947e1bf7fbff1fca15`
- Harness revision: `280173d743b2ed838a89be0ad930b20828d89558`
- Correctness: PASS 18/18 (6 workloads × Protos/Python/JavaScript)
- Startup: 10 fresh-process samples per language/workload
- Warmup: 20 retained same-process iterations
- Steady state: 20 retained samples after warmup
- Protos: GraalVM Community JDK 22 + external Truffle 24.0.0 + `-Xss128m`
- Python: 3.14.7
- JavaScript: Node.js 24.20.0
- CPU set: `0`; runtime networking disabled
- Protos compilation diagnostics are separate from timing.
- Optimization findings: 2 workload(s); compiler bailouts with correct execution are retained as baseline evidence rather than hidden or treated as correctness failures.

## Truffle diagnostic observations

| Workload | rc | opt done | opt failed | GraphTooBig | FrameWithoutBoxing | Deep inlining | Stack overflow | Bootstrap error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `collections/array-map` | 0 | 100 | 0 | 0 | 0 | 0 | 0 | 0 |
| `collections/array-filter` | 0 | 291 | 0 | 0 | 0 | 0 | 0 | 0 |
| `collections/array-reduce` | 0 | 236 | 40 | 40 | 0 | 0 | 0 | 0 |
| `collections/array-sort` | 0 | 650 | 40 | 40 | 0 | 0 | 0 | 0 |
| `collections/map-lookup-update` | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| `collections/set-algebra` | 0 | 246 | 0 | 0 | 0 | 0 | 0 | 0 |

A non-zero compiler-bailout count with `rc=0` is a performance finding, not a failed correctness case.

## Steady-state medians

| Workload | Protos ns | Python ns | JavaScript ns |
|---|---:|---:|---:|
| `collections/array-map` | 1715189524.0 | 210635.0 | 28065.0 |
| `collections/array-filter` | 9142870650.0 | 140435.0 | 17445.0 |
| `collections/array-reduce` | 2546874664.0 | 510195.0 | 25310.0 |
| `collections/array-sort` | 14939214996.5 | 3332775.0 | 314685.0 |
| `collections/map-lookup-update` | 7338772.5 | 132316.0 | 41500.0 |
| `collections/set-algebra` | 1699809287.0 | 703761.5 | 388031.0 |

These are observations for the exact pinned revisions/runtime identities only.
No row is generalized into a claim that one whole language is faster than another.

## PERF001-F — Future/P/Actor focused concurrency

Source authority: `results/perf001-f/summary.md`.

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
