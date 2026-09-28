# DIST006-D canonical post-adoption 25.4 baseline

Single-platform retained baseline for the canonical DIST006 GraalVM/Graal/Truffle 25.4.4.1.1 toolchain.

- Protos revision: `7aaaec6923265c99723ce5bca064e5b3ab52b8c4`
- Harness revision: `1e4a286f5f8fa43f96a5857818b8bf5d834ca8db`
- Runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- Container selector: `ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5`
- CPU affinity: `--cpuset-cpus 0`
- Network: `none`
- Warmup iterations: `120`
- Steady iterations: `100`
- Timing contains no JFR, compiler tracing, IGV, allocation profiling, source instrumentation, or Test Tool diagnostics.
- This is not a recreated 25.3-vs-25.4 comparison and contains no paired-platform formula.

`raw.json` is authoritative; `summary.tsv` is a derived view.
