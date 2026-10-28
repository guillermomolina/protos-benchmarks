# Protos Benchmarks

Single GraalVM benchmarking harness for
[Protos](https://github.com/guillermomolina/protos), GraalJS, and GraalPy.

The host entry point is `truffle/harness.py`; the root `Makefile` forwards to
it. The workload catalog is `truffle/workloads/catalog.json` (currently 17
cases, with one source file per implementation and case). The current adapters
are Protos `canonical` and GraalJS/GraalPy `executable-value`, configured in
`truffle/measure/cases.json`.

The old Docker, runner, PERF-specific and A/B harnesses are not part of this
working tree. Their history remains recoverable in Git.

## Running on the Linux host

Podman is the container runtime. The harness never implicitly pulls or builds
an image during measurement. Image preparation is an explicit operation.
Podman must be installed on the host; the measurement JVM and toolchain run
inside the pinned runner image.

Inspect the available commands and validate the catalog without a container:

```sh
make help
make validate
```

For the complete command-line options:

```sh
python3 truffle/harness.py --help
```

The harness supports correctness, smoke/reference timing, optional JFR
profiling, and graph capture/analysis through the explicit commands shown by
`make help`. Select one case with `--case`, an implementation with
`--language protos|js|python|all`, and the Protos checkout with `--product`.
Outputs should be stored beneath the ignored `results/local/` directory.

The GraalVM language dependency version is pinned in `truffle/pom.xml`.
Correctness must pass before any timing is accepted. Existing valid timing
results may be reused unless remeasurement is explicitly requested.

**Work in progress:** explicit cold-versus-hot selection and a complete
implementation-version-aware no-repeat key are not yet finalized. The existing
`smoke` and `reference` stages must not be confused with cold and hot runs.

See [BENCHMARKING.md](BENCHMARKING.md) for the current methodology and
`AGENTS.work/` for the binding measurement and reproducibility rules.

## Retained evidence

`results/peer-baselines/` preserves the current GraalJS and GraalPy baseline
archive and its manifest. Historical PERF and graph experiment outputs have
been removed from the working tree; their committed history remains available
in Git. Local and newly generated results are not affected by that cleanup.

## License

Protos Benchmarks is licensed under the Adaptive Public License 1.0 (APL-1.0).
See [LICENSE.TXT](LICENSE.TXT).
