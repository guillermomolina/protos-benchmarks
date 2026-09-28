# UPSTREAM003 GraalVM / Truffle platform comparison — clean timing

What changes when the upstream GraalVM/Graal/Truffle platform changes from 25.3.4.1 to 25.4.4.1.1, with the Protos product, workload sources, machine, CPU policy, warmup and measurement protocol unchanged?

- Harness revision: `4620cb3e95155298f3cc1e6966f0b140dfabcca4`
- Protos revision: `44690b1fc8c9aed023600c6d5731f969c4507e27`
- Protos version: `0.3.106-SNAPSHOT`
- Platform A: `25.3.4.1`.
- Platform B: `25.4.4.1.1`.
- `SOURCE_GIT_REVISION_SAME=YES`.
- `EXECUTABLE_LANGUAGE_SOURCE_SAME=YES`.
- `BUILD_TOOLCHAIN_METADATA_OVERLAY_B=YES`.
- Clean timing contains no JFR/compiler tracing/IGV/source instrumentation.
- Signed delta is `platform_b - platform_a`; no accept/reject or better/worse classification is produced by this harness.
- No four-workload aggregate is produced; every workload is reported independently.

See `summary.tsv`, `stationarity.tsv`, and authoritative `raw.json`.
