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

For a causal ablation, establish from the implementation before building the
diagnostic variant that the intervention preserves the observable semantics
required by the workloads. A smoke run is a runtime backstop for that argument,
not a substitute for it. If static inspection already shows that the
intervention changes required semantics, stop before implementing or running
the ablation.

Cross-language comparisons MUST use materially equivalent algorithms, inputs,
work amounts, and observable results. Idiomatic/library-accelerated
comparisons may be added as a separately labelled category, but MUST NOT be
mixed with the primary algorithm-equivalent comparison.

No single microbenchmark may be generalized into a claim that one complete
language is faster than another.

## Validation and measurement stages

Validation, smoke, and reference runs have distinct purposes and SHOULD have
clearly different costs:

    validate << smoke << reference

Validation checks static/configuration/structural preconditions without trying
to measure performance.

A smoke run is an admission and correctness gate. It MUST exercise the
workloads and paths needed to establish that the experiment can execute with
the intended observable result, using the minimum practical work needed for
that purpose. It MUST NOT attempt to produce statistically meaningful
performance evidence, reproduce reference-scale warmup or steady-state work,
or collect expensive profiling evidence unless that evidence is itself needed
by the gate. Performance conclusions MUST NOT be drawn from smoke timing.

A reference run performs the full measurement policy required for retained
performance evidence.

If a smoke approaches reference-scale cost and a cheaper correctness gate is
practical, simplify the smoke rather than treating it as a shortened reference
run. A benchmark with an unavoidable high fixed startup cost may still have an
expensive smoke; the requirement is to avoid unnecessary measurement work, not
to satisfy an arbitrary runtime ratio.

## Measurement classes

Startup, warmup, and steady-state execution are separate measurement classes.
For JIT-capable runtimes, early warmup iterations MUST NOT be silently merged
into steady-state results.
