# Protos Benchmarks

Reproducible performance benchmarking infrastructure for
[Protos](https://github.com/guillermomolina/protos).

The repository contains several benchmark harnesses and retained experimental
infrastructure rather than one benchmark implementation.

## Harnesses

- [`truffle/`](truffle/) — reusable cross-Truffle benchmark harness for Protos,
  GraalJS, and GraalPy.
- [`docker/`](docker/) — historical container-based benchmark infrastructure
  and compatibility entry points used by earlier PERF work.
- [`runner/`](runner/), [`scripts/`](scripts/), [`config/`](config/),
  [`workloads/`](workloads/), and [`results/`](results/) — retained shared and
  historical benchmark infrastructure.

The root `Makefile` preserves the existing targets and delegates newer harnesses
to their owning directories.

See [BENCHMARKING.md](BENCHMARKING.md) for benchmark methodology and
equivalence requirements.

## License

Protos Benchmarks is licensed under the Adaptive Public License 1.0 (APL-1.0).
See [LICENSE.TXT](LICENSE.TXT).
