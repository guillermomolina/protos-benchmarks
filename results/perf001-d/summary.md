# PERF001-D Protos startup, warmup and steady-state measurements

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
