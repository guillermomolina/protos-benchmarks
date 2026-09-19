# PERF004-A retained cross-language baseline

- Harness revision: `60dbce7faf5510bd1bd6867a866aa7ca69c48637`
- Protos revision: `4a03efc15620b37b2e418b3df30b4a26486446ec`
- Protos implementation: `0.2.492-SNAPSHOT`
- Languages: Protos, Python, JavaScript.
- Classification: algorithm-equivalent.
- Correctness: PASS 33/33.
- Startup: 10 fresh language-process samples per language/workload.
- Persistent forks: 5 per language/workload.
- Warmup: 20 iterations per fork.
- Steady state: 20 samples per fork.
- Docker creation/start is excluded from startup timing.
- Heavy compiler diagnostics are excluded from reference timing.
- Ratio definition in summary.json: Protos median duration / comparison median duration.
- Material-gap classification is deferred to PERF004-B.
- No row is generalized into a whole-language performance claim.

Raw ordered samples are authoritative in `raw.json`; `summary.json` and
`summary.tsv` are derived views.
