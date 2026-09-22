# Reproducibility and measurement evidence

These instructions apply to any retained benchmark result and to the harness
work that produces one. They regulate evidence identity and collection, not
benchmark methodology — see `AGENTS.work/PERFORMANCE.md` for correctness and
measurement-class rules, and `BENCHMARKING.md` for the detailed per-item
methodology and worked evidence.

## Revision and environment identity

Reference benchmark evidence MUST pin the exact Protos Git revision and exact
benchmark-harness Git revision. Floating branch names such as `main` are not
sufficient identities for retained reference results.

Evidence MUST also record materially relevant runtime and host information,
including runtime/JDK/GraalVM versions where applicable, container image
identity, CPU/architecture, kernel, resource/CPU affinity, and the declared
warmup and measurement policy.

Raw measurements MUST be retained. Human-readable tables and reports are
derived views, not replacements for raw evidence.

## Container, CPU, and diagnostic boundaries

Docker/container execution is an accepted reproducibility mechanism on Linux.
Compared runtimes in a reference comparison SHOULD execute on the same host.
Container creation/start latency is outside the language-startup timing
boundary unless a benchmark explicitly states that container startup itself
is the subject being measured.

CPU-focused measurements SHOULD prefer explicit CPU affinity/cpuset over CPU
quota as the primary CPU-isolation mechanism. Parallel benchmarks MUST record
the CPU set available to the workload. Networking SHOULD be disabled for
workloads that do not require it. Filesystem, network, process-creation, and
other environment-heavy benchmarks require an explicit methodology that
states which container/host effects are in scope.

Diagnostic instrumentation such as compilation tracing SHOULD be kept separate
from timing when it materially perturbs execution.
