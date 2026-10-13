# PERF043 — Published Integer-add graph evidence

## Identity

- Product: `guillermomolina/protos`
- Product commit: `8f7e5ea5b7ad75f8052adf7ce51945539348b4a1`
- Product version: `0.3.344-SNAPSHOT`
- Benchmark harness producer: `99ba341d88091b5bf0c76f18039e18912e1f611c`
- Workload: `primitive-integer-add`
- Phase: `After TruffleTier`
- Compilation tier: 2
- Evidence type: compiled Truffle graph, not timing

## Final Protos capture

- Correctness: PASS
- Capture: VALID
- Stabilization: STABLE
- Graphs: 1
- Relevant nodes: **42**
- Workload source SHA-256: `ae8ba162beb092793920a40655bc10d1ff57b4dc62edbae370ad86c0d1e97aff`
- Product source-state SHA-256: `8c84caf84fa88fe87e466e92eecc64fed942d7351ecb4260d7f9f14b35fb4fce`

The original `capture.json`, `unit.json`, retained trace logs,
analyzed BGV files and derived `matrix.json` are preserved
under `primitive-integer-add/protos/`.

## Historical comparison references

| Language | Nodes | Source |
| --- | ---: | --- |
| Protos 0.3.344 | 42 | This capture |
| GraalJS | 14 | `results/global-20261008-graphs/primitive-integer-add/js/` |
| GraalPy | 49 | `results/global-20261008-graphs/primitive-integer-add/python/` |

The peer reference producer is `98abc9af7a05a45a7d4056b72f36aef5889cb76f`
and its recorded Protos revision is `d59da442fd9bc6cf590fb9b2c82d3ff55c0391ae`.

Peers were not recaptured against the current product revision.
Therefore the standalone matrix reports peer comparison
`UNRESOLVED` / `NOT_EVALUATED`; the node counts above are
descriptive historical references, not a new matched experiment.

No steady-state timing improvement is claimed.

## Validation

- `make test`: PASS (maintainer reported)
- `make check`: PASS (maintainer reported)
- Graph analysis failures: 0
- Graph invalid units: 0
- Producer verification: working tree YES, HEAD YES
