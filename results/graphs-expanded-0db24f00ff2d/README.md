# Corrected recursive graph evidence

Protos revision: `0db24f00ff2d92d642351d7f7535517fe01a55ce`.

This directory supersedes the Protos graph totals for `fibonacci`
and `factorial` in `results/graphs-full-0db24f00ff2d/`.

The original graph-accounting policy did not follow `Expanded`
compilation edges and therefore omitted separately compiled
recursive callees.

Corrected, stable, After-TruffleTier BGV totals:

| Workload | Primary | Recursive callee | Total |
| --- | ---: | ---: | ---: |
| fibonacci | 393 | 26433 | 26826 |
| factorial | 393 | 21415 | 21808 |

Both results have two accounted compilation units, correctness PASS,
stable compilation and successful BGV analysis.

The original captures remain preserved for provenance. Other
workloads retain their original evidence. These graph measurements
are not execution-time measurements.
