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

## Current host-side Podman runner

The cross-Truffle harness runs directly from a Linux host using Podman.
Its standalone image provides Java, Maven, and the benchmark JVMs, so no
VS Code Dev Container or host-installed JDK is required.

Build the pinned image:

```sh
make -C truffle podman-build
```

Run a correctness smoke for the canonical Protos surface:

```sh
make -C truffle podman-measure LANGUAGE=protos WORKLOAD=primitive-return-literal STAGE=smoke PROFILE=none CPU=0 PODMAN_OUTPUT=results/local/podman-smoke/protos
```

Set `LANGUAGE=js` or `LANGUAGE=python` for the GraalJS and GraalPy peer
surfaces. For Protos, the default product checkout is the sibling
`protos-1` directory; an absolute `PROTOS_CHECKOUT` selects another checkout.

The image pins GraalVM CE 25.4.4.1.1 / JDK 25.0.4.1.1 and Maven 3.9.9.
Maven dependencies persist in `.work/runner-m2`; outputs stay under
`results/`. A dirty Protos checkout requires `ALLOW_DIRTY_PRODUCT=1`, and
such a run is not reference-eligible. Smoke runs validate correctness and
infrastructure, not steady-state performance.

See [BENCHMARKING.md](BENCHMARKING.md) for benchmark methodology and
equivalence requirements.

## License

Protos Benchmarks is licensed under the Adaptive Public License 1.0 (APL-1.0).
See [LICENSE.TXT](LICENSE.TXT).
