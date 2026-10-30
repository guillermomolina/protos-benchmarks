# I115-H6 — Recovered graph summaries

> EXPERIMENTAL: Protos I115-H6 may diverge from normative
> language semantics. GraalPy 25.4.4.1.1 is the reference.

This directory supplements the original I115-H6 results.

Eight previously unavailable guest-root graphs were recovered:
six Protos graphs and two GraalPy graphs.

The recovery selected observed compilations without subsequent
invalidation or failure in their retained compiler traces.
Their After TruffleTier node counts were verified against BGVs.

## Files

- `recovered-nodes.csv`: structural counts and evidence identities.
- `node-histograms.csv`: per-node-class counts.
- `manifest.json`: original and recovery provenance.
- `SHA256SUMS`: checksums for the published summaries.

## Limitations

The original capture admission results remain unchanged.
Recovered graphs do not retroactively validate rejected captures.

Some recoveries use separate JVM executions from the original
campaign, so their compilation IDs, Final IR and machine-code
sizes may differ. These observations must not be silently
combined into original-run totals.

BGVs, raw compiler traces and full IGV JSON exports are NOT
published. Their SHA-256 digests identify locally retained
evidence, not publicly downloadable artifacts.

These are structural compiler measurements, not timing
benchmarks or evidence of whole-language performance parity.

The original results and CSVs remain unmodified.
