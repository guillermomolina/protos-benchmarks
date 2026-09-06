# PERF001-E collection benchmark evidence

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
