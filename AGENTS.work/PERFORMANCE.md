# Benchmark and performance work

These instructions apply to benchmark implementation, timing measurement, and
performance-investigation work in this repository, including formal `PERFxxx`
work performed here. They regulate how this repository measures and compares
Protos performance; they do not redefine the repository-root `AGENTS.md`, and
they never grant permission to change observable Protos semantics — see
Semantic firewall there.

Reproducibility and measurement-evidence requirements (revision pinning,
host/runtime identity, container/CPU control, raw-measurement retention) are
governed separately by `AGENTS.work/REPRODUCIBILITY.md`; apply both together
for any retained benchmark result. Detailed benchmark-by-benchmark
methodology, exact commands, and per-item result narratives live in
`BENCHMARKING.md`; this file holds the binding rule, not the full write-up.

## Correctness before timing

Every benchmark implementation MUST produce and validate its documented
observable result before its timing is accepted. A wrong result invalidates
the measurement; it is not a performance result.

Cross-language comparisons MUST use materially equivalent algorithms, inputs,
work amounts, and observable results. Idiomatic/library-accelerated
comparisons may be added as a separately labelled category, but MUST NOT be
mixed with the primary algorithm-equivalent comparison.

No single microbenchmark may be generalized into a claim that one complete
language is faster than another.

## Measurement classes

Startup, warmup, and steady-state execution are separate measurement classes.
For JIT-capable runtimes, early warmup iterations MUST NOT be silently merged
into steady-state results.
