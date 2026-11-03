# Protos Benchmarks

Single GraalVM benchmarking harness for
[Protos](https://github.com/guillermomolina/protos), GraalJS, GraalPy,
and TruffleRuby (GraalRuby).

The host entry point is `benchmark.py`; the root `Makefile` forwards to
it. The workload catalog is `cases/catalog.json` (currently 17
cases, with one source file per implementation and case). The current adapters
are Protos `canonical` and GraalJS/GraalPy/TruffleRuby `executable-value`, configured in
`harness/policy/cases.json`.

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
python3 benchmark.py --help
```

The harness supports correctness, smoke/reference timing, optional JFR
profiling, and graph capture/analysis through the explicit commands shown by
`make help`. Select one case with `--case`, an implementation with
`--language protos|js|python|ruby|all`, and the Protos checkout with `--product`.
Outputs should be stored beneath the ignored `results/local/` directory.

The harness accepts independent `--protos-version`, `--js-version`,
`--python-version`, and `--ruby-version` selectors. The Protos selector must
match the actual checkout. GraalJS and GraalPy still use explicit
`peer-prepare`; Ruby's version-pinned Maven runtime and Graal compiler are
baked into a separate, SHA-pinned Podman image during `image-build-ruby`.
Correctness must pass before timing is accepted.

The Ruby image is independent because TruffleRuby `40.0.0` requires
GraalVM/Truffle `25.3.4.1`, while the other implementations use `25.4.4.1.1`.
No manual host Ruby installation is used. Build and validate explicitly:

```sh
make image-build-ruby
make image-status-ruby
make peer-prepare LANGUAGE=ruby
make correctness CASE=primitive-closure-call LANGUAGE=ruby
make correctness CASE=all LANGUAGE=ruby
```

`LANGUAGE=all` dispatches Ruby into its own image for each execution; the
other languages remain on the original pinned image. Ruby source ends with
`method(:run)`; the guest callable is acquired once before measurement and
the timed operation remains `run.execute()` in the shared Java engine.
The Ruby guest method, any nested lambda, and Polyglot adapter are distinct
compilation units: do not combine their graph totals without call evidence.

Use `--temperature cold|hot|both` independently of `--stage smoke|reference`.
Cold is the first guest invocation after context initialization, not JVM
startup; hot selects the minimum observed per-call time among the steady
samples, without a convergence gate. Both phases and all raw samples are
captured together. Existing valid results are reused when the exact
implementation version, source/producer, immutable container image, Java,
host/CPU, case and measurement policy identities match, unless
remeasurement is explicitly requested.

For timing results, the harness automatically derives a readable
`machine_id` from the CPU model and a short hash of the real Linux host
hostname. The label is exposed in timing metadata and summaries.
The existing host/CPU identity prevents incompatible timing reuse,
while Podman container hostnames do not create artificial differences.
Graph structural measurements are not partitioned by `machine_id`.

See [BENCHMARKING.md](BENCHMARKING.md) for the current methodology and
`AGENTS.work/` for the binding measurement and reproducibility rules.

## Ruby compilation evidence

Use `cold-capture` with `COMPILATION_ROOT=all` to collect the actual Ruby
compiled roots in Tier 1 and Tier 2. The root label will be determined only from
the unique framework-callee trace in each capture; ambiguous or missing
compilations fail closed rather than invent a root. A missing Bytecode DSL histogram
is not a zero-node Graal graph. Ruby compiler counts are generated on its
pinned 25.3 toolchain and are not presented as identical-toolchain comparisons
with the 25.4 peers.

## Retained evidence

`results/peer-baselines/` preserves the current GraalJS and GraalPy baseline
archive and its manifest. Historical PERF and graph experiment outputs have
been removed from the working tree; their committed history remains available
in Git. Local and newly generated results are not affected by that cleanup.

## License

Protos Benchmarks is licensed under the Adaptive Public License 1.0 (APL-1.0).
See [LICENSE.TXT](LICENSE.TXT).
