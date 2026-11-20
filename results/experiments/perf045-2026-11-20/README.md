# PERF045 — Array iteration: comparative evidence, 2026-11-20

**Status:** Derived structural and timing results; **incomplete raw-reference publication**. This report is not proof of causal optimization and does not replace the retained raw captures on the measurement host.

- Benchmark source revision (numeric `for`): `19b6638768bf7758af566a27e75cc56868a29312` (21 workloads).
- Earlier `sum` and `callback` source revision: `a9a5a1f52ba2536b1c6bbbcf852016486b166bd5`.
- Protos product revision: `2df251847ead94012f8d5a87c2b81d2d981882c7` (`0.4.186-SNAPSHOT`, clean checkout).
- Host: AMD Ryzen 7 3700X, x86_64; measurement machine ID `amd-ryzen-7-3700x-8-core-1e34718d`.
- Runtimes: Protos / GraalVM 25.5.5.0.3; GraalJS and GraalPy 25.4.4.1.1; TruffleRuby 40.0.0 on GraalVM 25.3.4.1. Comparisons are **not same-toolchain comparisons**.
- All three workloads traverse 64 values, produce `2080`; each measured workload reports correctness PASS. Numeric `for` reference timing uses the clean benchmark revision. Earlier cases were separately measured at `a9a5a1f`.

## Reference timing (hot, nanoseconds per prepared `run.execute()`)

| Workload | Protos | GraalJS | GraalPy | TruffleRuby |
| --- | ---: | ---: | ---: | ---: |
| `array-iteration-sum` (indexed while) | 403.369 | 317.579 | 283.559 | 199.519 |
| `array-iteration-callback` | 713.337 | 559.508 | 681.508 | 311.699 |
| `array-iteration-for` (numeric index) | **35424.772** | 258.639 | 269.449 | 396.319 |

The `for` measurement used stage `reference`, temperature `both`, profile `none`; `HARNESS_DIRTY=NO`, `MEASUREMENT_VALID=YES`, and `CORRECTNESS=PASS` for all four languages. These are **steady-state minimum observations**, not confidence intervals or multiple-run distributions. Raw timing samples were not provided to the assistant and are not contained in this publication.

The numeric `for` of Protos is **131.5×** GraalPy's observed time and **87.8×** Protos's earlier indexed `while` time. This is a substantial regression in the selected source patterns, not a general language-performance statement. The different loop protocols and toolchains must be considered.

## Compiled graph evidence: numeric `for`

Source: eight `capture.json` and eight `cold-summary.json` files from `perf045-for-summaries.tar.gz`, collected on the same host. Selected phase: `After TruffleTier`. Each capture is valid, each summary succeeded. Exact root-level metrics (including separate compilation units) are in [for-root-metrics.csv](for-root-metrics.csv).

| Language | T1 observed / unavailable roots | T2 observed / unavailable roots | `run` T1 nodes | `run` T2 nodes |
| --- | --- | --- | ---: | ---: |
| Protos | 11 / 2 | 13 / 0 | 2788 | 3441 |
| GraalJS | 2 / 0 | 2 / 0 | 163 | 80 |
| GraalPy | 4 / 1 | 3 / 2 | 378 | 271 |
| TruffleRuby | 19 / 5 | 4 / 19 | 332 | 225 |

Notable Protos graphs: `Range.protos` closure `4c403134cfcb3565` has **5131 nodes at T1**, **5796 at T2**; the external Polyglot entry `Value.execute` grows from **292 T1** to **3955 T2**; the guest `run` from **2788 T1** to **3441 T2**; six `ProtosBuiltinCallRootNode` units are observed per tier. A further guest callback root is observed at T2 (238 nodes). Roots may be compiled independently or during warmup and **must not be summed as if all executed per iteration**. Invalidation, unresolved roots, interpreted-only roots, and compilation call edges still need attribution.

The documented Protos `for(i, 0, n)` has the semantics of `Range(0,n).each(i => ...)`; standard `Range.each` delegates to `eachStep(1, block)`, which validates inputs and executes a `while`. These are **semantic and source observations**, not evidence that each underlying message remains executed after JIT compilation. The numeric iteration path merits optimization investigation under PERF045 without weakening dispatch, overrides, errors or non-local returns.

## Earlier source cases (primary `run` graph only)

| Case | Language | T1 nodes | T2 nodes |
| --- | --- | ---: | ---: |
| indexed `while` | Protos | 333 | 225 |
| indexed `while` | GraalPy | 350 | 243 |
| callback | Protos | 393 | 283 |
| callback | GraalPy | unavailable | 311 |

GraalPy's callback has its own compiled root (108 nodes T2) in that case; Protos did not show a separately compiled callback root. The absence of an observed root does not establish that no callback work exists.

## Evidence inventory and publication limit

This commit stores a lossless **derived metrics table**, these findings, and the SHA-256 inventory of the supplied `capture.json`/`cold-summary.json` archive in [evidence-manifest.json](evidence-manifest.json). The supplied archive contains **16 JSON files**; its SHA-256 is `c31ce484be7004db89f0323274d4884588b97f4c59d81dcd6287e13cacfcd133`. The archive of earlier two cases has SHA-256 `b168bec32f79c41cd1405113a47cdc3cad4c32c195ab3231705c01cd73b7a748`.

**Not yet published in Git:** original BGV graphs, trace logs, the full unabridged `capture.json` and `cold-summary.json` files, and the raw `measure/...` reference timing directories on `chaca`. These must be copied from `results/local/perf045/` and hash-validated before labeling this a complete, reproducible reference archive. Do not claim full raw-reference publication based on this document alone.

The open PERF045 question is why the numeric `Range.each` path retains multiple costly compilation units and ~35 µs per iteration-sum invocation, despite a much smaller index-based `while` baseline. Only verified language-implementation precedent (especially GraalPy) may justify production Java optimization.
