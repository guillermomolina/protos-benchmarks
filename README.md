# Protos Benchmarks

Reproducible performance benchmarking infrastructure for
[Protos](https://github.com/guillermomolina/protos).

This companion repository contains benchmark harnesses, containerized runtime
environments, materially equivalent cross-language workloads, raw measurements,
and generated performance reports for Protos.

## Project ownership

The canonical Protos language/runtime implementation and the canonical
`PERFxxx` lifecycle live in `guillermomolina/protos`. This repository provides
execution infrastructure and evidence; it does not define Protos semantics and
is not a competing project-status ledger.

The canonical Protos-language benchmark corpus remains in
`guillermomolina/protos/protos/benchmarks/`. Benchmark runs in this repository
identify the exact Protos Git revision they consume rather than silently forking
those sources.

## Benchmark principles

- Correctness is validated before performance is measured.
- Retained runs identify exact source and harness revisions.
- Cross-language comparisons use materially equivalent work and inputs.
- Startup, warmup, and steady-state measurements remain distinct.
- Container startup is not reported as language startup.
- Raw measurements and the environment needed to interpret them are retained.
- Performance work must never redefine, relax, or bypass Protos semantics.

## PERF001-B harness

PERF001-B added the first executable harness: pinned Docker runtime definitions,
exact Protos revision consumption, machine/runtime inventory capture, CPU-affinity
policy, a raw-result schema, and correctness smoke validation.

## PERF001-C corpus correctness

PERF001-C adds materially equivalent Python and JavaScript implementations for
all 11 canonical Protos workloads currently under `micro/`, `runtime/`, and
`algorithms/`. `config/suite.json` is the companion mapping from each canonical
`.protos` source to comparison-language source and expected observable result.

The suite pins Protos revision `42b8264a36254dafbd97d80f5181790e28b9de12`. Recursive 10,000-step workloads retain
their canonical recursion; the Protos container records `-Xss64m`, Python records
a 50,000 recursion limit, and Node records `--stack-size=32768` so host default
stack limits do not silently change the workload.

Run the full validation, image build, smoke gate, and 33-case cross-language
correctness suite with:

```sh
python3 runner/bench.py all
```

Run only the corpus correctness gate after images have been built with:

```sh
python3 runner/bench.py correctness
```

PERF001-C does not publish timing measurements. Startup, warmup, steady-state,
and interpreter-versus-compilation measurement remain later PERF001 work.

See [BENCHMARKING.md](BENCHMARKING.md) for methodology and equivalence
boundaries.

## License

Protos Benchmarks is licensed under the Adaptive Public License 1.0 (APL-1.0).
See [LICENSE.TXT](LICENSE.TXT) for the complete license and the Protos
Benchmarks-specific Exhibit A.
