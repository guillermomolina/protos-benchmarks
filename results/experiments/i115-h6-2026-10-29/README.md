# I115-H6 — Experimental Protos vs GraalPy Structural Results

> EXPERIMENTAL: These measurements describe the I115-H6 experimental Protos implementation, not a stable Protos release.

## Versions

- Protos: 0.3.403-SNAPSHOT, revision 493cf1394fd88efa07c5740541a5873d1ba45e44
- Protos status: experimental I115-H6; normative semantic divergences may exist.
- GraalPy: 25.4.4.1.1 (reference implementation).
- Benchmark harness: b41c60cd368a1fac7509305ea255150d8560a03d.

## Measurements

- Scope: 17 workloads, Protos and GraalPy.
- DSL: static Bytecode DSL instruction count for the guest run root.
- Tier 1 and Tier 2: observed compiled guest roots only.
- Graph metrics: After TruffleTier nodes and Final IR nodes.
- Multiple compiled guest roots are summed; inlining may duplicate graph content.
- Missing values indicate unavailable observations, never zero nodes.
- These are structural measurements, not execution-time benchmarks.

## Limitations

- integer-loop/protos Tier 2: NO_REQUESTED_TIER_BGV_AVAILABLE.
- Some Tier 1 captures have no observable compiled guest graph.
- method-call Tier 1 guest roots are not identity-matched across languages.
- Structural reports with INCOMPLETE status have root-attribution limitations.
- The included ZIP archives retain metadata and structural reports, not all original BGV graphs.
- Results are unsuitable for whole-language performance rankings.

## Files

- protos/nodes.csv: experimental Protos structural results.
- graalpy/nodes.csv: GraalPy structural reference results.
- comparison.csv: complete cross-language comparison.
- cold-metadata.zip: compilation capture metadata and summaries.
- structural-reports.zip: structural analysis reports.
- SHA256SUMS: archive integrity checksums.

## Post-hoc recovered graph summaries

See [recovery/](recovery/) for eight recovered guest-root graph summaries and node-class histograms, covering Protos and GraalPy. Original captures and result CSVs remain unchanged. No raw BGVs or IGV exports are published.
