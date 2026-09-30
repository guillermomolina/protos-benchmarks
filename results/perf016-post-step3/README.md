# PERF016 post-Step-3 controlled timing Evidence Unit

What is the combined steady-state timing effect of PERF015 + PERF016 on (a) the retained common benchmark driver, observed through each workload's workload-control variant, and (b) each common canonical workload, when the exact pre-PERF015 product (CONTROL) and the exact post-PERF016 product (INTERVENTION) are built as ordinary unpatched baselines on the canonical post-adoption GraalVM 25.4.4.1.1 toolchain and timed as canonical/workload-control pairs in a counterbalanced A,B,A,B block design on one pinned CPU? This Evidence Unit collects and summarizes objective measurements only; it does not classify Step 3 (STEP_3_TIMING_CLASS) or route the result (STEP3_NEXT_ROUTING).

- Work item: `PERF016` / `guillermomolina/protos#727` (parent `PERF010-B` / `guillermomolina/protos#722`), slice `POST_STEP3_CONTROLLED_TIMING`.
- Harness revision: `ac59110d23cb4724e4aa438a2a5781aaf1b31a77`.
- CONTROL Protos revision (baseline, no patch): `2e3f56fae3a500d3e4193e3345d8a82c35e4590e` (`0.3.117-SNAPSHOT`).
- INTERVENTION Protos revision (baseline, no patch): `696b0f9797ebc8ced80009fb583027513852f55c` (`0.3.119-SNAPSHOT`).
- Product commits between the endpoints (supplied input, not re-derived by the harness): `453f2b00ae2bd0af1cd2761474549e85ff1cb8b6` PERF015: admit canonical Boolean to guarded structured selection; `696b0f9797ebc8ced80009fb583027513852f55c` PERF016: admit semantic Integer family to guarded represented selection.
- Toolchain: GraalVM/Graal/Truffle `25.4.4.1.1`, JDK `25.0.4.1.1`, JVMCI `25.4-b23`; runtime `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`.
- Container base image: `ghcr.io/graalvm/graalvm-community:25i4-25.0.4.1.1-ol10@sha256:a7b4810d7c755e9627feaa1459eb5a93338643b16d745d4f3fc86db71e5da7f5` (image id `sha256:6ff7aca7c34fc43d1e67216620550325809bb974eb8cbf5e5fe5de4bfbddce97`).
- Built image ids: control `sha256:086b86965db8d1694afafa59e75ae3d3f315999bdc38181493edc78da4ecc17e`, intervention `sha256:cdddb64b6928c11d4e80df4ce1d49a942625ff1d0e2c29b01394f8735a8f5aaf`.
- Host: `Linux-7.2.7-zen1-1-zen-x86_64-with-glibc2.44`, CPU `AMD Ryzen 7 3700X 8-Core Processor`.
- CPU affinity: `--cpuset-cpus 0` (allowed set `0-15`); network `none`.
- Operation count `10000`; warmup `120`; steady `100`.
- Block order `A,B,A,B` (A: CONTROL first, INTERVENTION second; B: INTERVENTION first, CONTROL second).
- Workload source identity `PASS`: canonical and generated workload-control sources are byte-identical between the two images (`workload_source_sha256` in `raw.json`).
- Correctness gate `PASS` for every role, workload and variant before any timing.
- Timing contains no JFR, compiler tracing, IGV, allocation profiling, source instrumentation or Test Tool diagnostics.

`raw.json` is authoritative. `summary.tsv`, `blocks.tsv`, `stationarity.tsv` and this file are derived from it. Every effect below is CONTROL minus INTERVENTION, so a positive value means the INTERVENTION is faster.

## Shared-driver / workload-control effect (SHARED_DRIVER_TIMING_EFFECT, PRIMARY for the common driver)

Formula: `control_variant_effect_ns = control_workload_control_median_ns - intervention_workload_control_median_ns; control_variant_effect_percent = 100 * control_variant_effect_ns / control_workload_control_median_ns`

| workload | blocks | median ns | MAD ns | min ns | max ns | median % | MAD % | min % | max % | order effect |
|---|---|---|---|---|---|---|---|---|---|---|
| micro/slot-read | 4 | 3341326.0 | 1313632.5 | 1774084.5 | 4830520.0 | 5.3537 | 2.0960 | 3.0041 | 7.7805 | NOT_DETECTED |
| micro/closure-call | 4 | 827228.5 | 2718379.5 | -3865584.5 | 5485431.5 | 1.2583 | 3.9088 | -6.3286 | 7.8972 | NOT_DETECTED |
| micro/method-call | 4 | 2089541.0 | 2968260.8 | -5917424.5 | 5114963.0 | 3.3384 | 4.8086 | -9.6557 | 8.3231 | DETECTED |
| runtime/monomorphic-dispatch | 4 | 128892.0 | 702448.8 | -665350.0 | 4457013.5 | 0.1797 | 1.1902 | -1.2031 | 7.0066 | DETECTED |

## Canonical common-workload effect (COMMON_WORKLOAD_TIMING_EFFECTS)

Formula: `canonical_effect_ns = control_canonical_median_ns - intervention_canonical_median_ns; canonical_effect_percent = 100 * canonical_effect_ns / control_canonical_median_ns`

| workload | blocks | median ns | MAD ns | min ns | max ns | median % | MAD % | min % | max % | order effect |
|---|---|---|---|---|---|---|---|---|---|---|
| micro/slot-read | 4 | -3807006.8 | 3570539.8 | -8907427.0 | 2377381.5 | -6.8125 | 6.4289 | -15.6266 | 3.8404 | DETECTED |
| micro/closure-call | 4 | -4020270.0 | 3411503.8 | -10150719.0 | 20607923.5 | -6.0053 | 5.2902 | -15.5951 | 23.0163 | NOT_DETECTED |
| micro/method-call | 4 | 2801558.2 | 3631391.0 | -11659659.5 | 8464953.0 | 3.7213 | 4.5112 | -17.7760 | 10.7761 | NOT_DETECTED |
| runtime/monomorphic-dispatch | 4 | 299751.5 | 1322051.2 | -6587401.0 | 1687379.0 | 0.4835 | 1.9833 | -10.7069 | 2.4693 | NOT_DETECTED |

## Paired-control residual (SECONDARY discriminator)

Formula: `canonical_improvement_ns = canonical_effect_ns; control_movement_ns = control_variant_effect_ns; paired_control_effect_ns = canonical_improvement_ns - control_movement_ns; paired_control_effect_percent = 100 * paired_control_effect_ns / control_canonical_median_ns`

| workload | blocks | median ns | MAD ns | min ns | max ns | median % | MAD % | min % | max % | order effect |
|---|---|---|---|---|---|---|---|---|---|---|
| micro/slot-read | 4 | -5795676.5 | 2584306.0 | -13386824.0 | -2453138.5 | -10.1862 | 5.0936 | -23.4849 | -3.9628 | DETECTED |
| micro/closure-call | 4 | -4830759.2 | 1471114.5 | -6318613.0 | 15122492.0 | -7.2338 | 2.2841 | -9.6562 | 16.8898 | NOT_DETECTED |
| micro/method-call | 4 | -224239.8 | 4510486.8 | -5742235.0 | 5222504.0 | -0.6383 | 6.1461 | -8.7545 | 6.7509 | NOT_DETECTED |
| runtime/monomorphic-dispatch | 4 | -2232952.8 | 2204683.2 | -6105637.5 | 2221576.5 | -3.3498 | 3.6346 | -9.9239 | 3.5250 | NOT_DETECTED |

## Per-block effects (percent of CONTROL; positive = INTERVENTION faster)

| block | order | workload | shared-driver % | canonical % | paired-control % |
|---|---|---|---|---|---|
| 0 | A | micro/slot-read | 7.1962 | -15.6266 | -23.4849 |
| 0 | A | micro/closure-call | 7.8972 | 23.0163 | 16.8898 |
| 0 | A | micro/method-call | -9.6557 | -17.7760 | -8.7545 |
| 0 | A | runtime/monomorphic-dispatch | 7.0066 | 2.4643 | -4.0449 |
| 1 | B | micro/slot-read | 7.7805 | 3.8404 | -3.9628 |
| 1 | B | micro/closure-call | 0.0796 | -5.0147 | -5.0881 |
| 1 | B | micro/method-call | 8.3231 | 1.7537 | -5.5412 |
| 1 | B | runtime/monomorphic-dispatch | -1.2031 | 2.4693 | 3.5250 |
| 2 | A | micro/slot-read | 3.0041 | -10.8563 | -14.1500 |
| 2 | A | micro/closure-call | -6.3286 | -15.5951 | -9.6562 |
| 2 | A | micro/method-call | -1.2941 | 5.6889 | 6.7509 |
| 2 | A | runtime/monomorphic-dispatch | 1.1772 | -1.4973 | -2.6547 |
| 3 | B | micro/slot-read | 3.5112 | -2.7687 | -6.2223 |
| 3 | B | micro/closure-call | 2.4371 | -6.9958 | -9.3795 |
| 3 | B | micro/method-call | 7.9708 | 10.7761 | 4.2646 |
| 3 | B | runtime/monomorphic-dispatch | -0.8178 | -10.7069 | -9.9239 |

## Stationarity

Largest absolute last-quarter-versus-first-quarter change over 64 steady timed units: `22.7265` %. See `stationarity.tsv` for every unit. This is reported only: no threshold is applied and no block is discarded.

## STEP_3_TIMING_CLASS = NOT_CLASSIFIED
## STEP3_NEXT_ROUTING = NOT_CLASSIFIED

This Evidence Unit deliberately does not classify Step 3. No threshold for MATERIAL_LARGE_FACTOR_IMPROVEMENT, MATERIAL_PARTIAL_IMPROVEMENT, ESSENTIALLY_UNCHANGED exists in this harness; classification is a later interpretation step performed against the retained raw evidence. A near-zero paired-control effect is not evidence that Step 3 had no effect, and no microbenchmark here supports a whole-language claim.
