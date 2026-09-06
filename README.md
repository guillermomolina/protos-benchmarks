# Protos Benchmarks

Reproducible performance benchmarking infrastructure for
[Protos](https://github.com/guillermomolina/protos).

This companion repository is intended to contain benchmark harnesses,
containerized runtime environments, materially equivalent cross-language
workloads, raw measurements, and generated performance reports for Protos.

## Project ownership

The canonical Protos language/runtime implementation and the canonical
`PERFxxx` lifecycle live in `guillermomolina/protos`. This repository provides
execution infrastructure and evidence; it does not define Protos semantics and
is not a competing project-status ledger.

The canonical Protos-language benchmark corpus remains in
`guillermomolina/protos/protos/benchmarks/`. Benchmark runs in this repository
must identify the exact Protos Git revision they consume rather than silently
forking those sources.

## Benchmark principles

- Correctness is validated before performance is measured.
- Retained runs identify exact source and harness revisions.
- Cross-language comparisons use materially equivalent work and inputs.
- Startup, warmup, and steady-state measurements remain distinct.
- Container startup is not reported as language startup.
- Raw measurements and the environment needed to interpret them are retained.
- Performance work must never redefine, relax, or bypass Protos semantics.

## PERF001-B harness

PERF001-B adds the first executable harness: pinned Docker runtime definitions,
exact Protos revision consumption, machine/runtime inventory capture, CPU-affinity
policy, a raw-result schema, and correctness smoke validation. It deliberately
does not publish performance timings; later PERF001 slices add comparable workload
execution and measurement.

Run the complete PERF001-B validation with:

```sh
python3 runner/bench.py all
```

See [BENCHMARKING.md](BENCHMARKING.md) for methodology and boundaries.

## License

Protos Benchmarks is licensed under the Adaptive Public License 1.0 (APL-1.0).
See [LICENSE.TXT](LICENSE.TXT) for the complete license and the Protos
Benchmarks-specific Exhibit A.
