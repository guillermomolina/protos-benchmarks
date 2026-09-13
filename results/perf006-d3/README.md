# PERF006-D3 current structural diagnostics

- exact diagnostic harness: `297ccb4fc94a0f0b0c9e0a65422aba2e223c4a83`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- runtime: `com.oracle.truffle.runtime.hotspot.HotSpotTruffleRuntime`
- real workload: `bin/protos test --jobs 2`
- CPU set: `0,1`
- diagnostic wall time: `77.613 s`
- historical absolute performance comparison: **not allowed**
- production optimization applied: **no**
- IGV-24 analyzer used: **no**

The recovered pre-C′ profile is retained as historical structural context, not
as an absolute timing comparator. D3 records current CPU/thread concentration,
the exact historical `java.util.HashMap$KeyIterator.next` symbol share,
standard and Truffle deoptimization counts where available, a static audit for
the retired replay cleanup path, and bounded current-toolchain TraceCompilation
evidence.

Current headline observations are machine-readable in `result.json`. D4 owns the
final causal interpretation and any decision to open a separate PERF item for a
new dominant hotspot.
