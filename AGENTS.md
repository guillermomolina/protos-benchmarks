# Repository instructions

These instructions apply to the entire `guillermomolina/protos-benchmarks`
repository.

## Role of this repository

This repository is the companion benchmark harness and evidence store for the
Protos project. The canonical Protos implementation, specification, and
`PERFxxx` work-item lifecycle remain owned by `guillermomolina/protos`.

Do not create an independent lifecycle here that can contradict the canonical
Protos project ledger. When work is performed for a Protos `PERFxxx` item, use
the identifier and state published by the current Protos repository.

## Semantic firewall

Performance work MUST NOT redefine, weaken, bypass, or special-case observable
Protos semantics, correctness requirements, conformance requirements,
capability boundaries, or error behavior.

If a proposed benchmark or optimization requires a semantic change, stop the
performance work and route that change through the applicable Protos
specification/design/implementation process first.

Benchmark-specific hidden semantics, privileged guest objects, correctness
shortcuts, or implementation paths that exist only to improve a score are not
allowed.

## Reproducibility

Reference benchmark evidence MUST pin the exact Protos Git revision and exact
benchmark-harness Git revision. It MUST also record materially relevant runtime
and host information, including runtime/JDK/GraalVM versions where applicable,
container image identity, CPU/architecture, kernel, resource/CPU affinity, and
the declared warmup and measurement policy.

Floating branch names such as `main` are not sufficient identities for retained
reference results.

Raw measurements MUST be retained. Human-readable tables and reports are
derived views, not replacements for raw evidence.

## Correctness before timing

Every benchmark implementation MUST produce and validate its documented
observable result before its timing is accepted. A wrong result invalidates the
measurement; it is not a performance result.

Cross-language comparisons MUST use materially equivalent algorithms, inputs,
work amounts, and observable results. Idiomatic/library-accelerated comparisons
may be added as a separately labelled category, but MUST NOT be mixed with the
primary algorithm-equivalent comparison.

No single microbenchmark may be generalized into a claim that one complete
language is faster than another.

## Measurement classes

Startup, warmup, and steady-state execution are separate measurement classes.
For JIT-capable runtimes, early warmup iterations MUST NOT be silently merged
into steady-state results.

When containers are used, container creation/start latency is outside the
language-startup timing boundary unless a benchmark explicitly states that
container startup itself is the subject being measured.

Diagnostic instrumentation such as compilation tracing SHOULD be kept separate
from timing when it materially perturbs execution.

## Containers and host control

Docker/container execution is an accepted reproducibility mechanism on Linux.
Compared runtimes in a reference comparison SHOULD execute on the same host.
CPU-focused measurements SHOULD prefer explicit CPU affinity/cpuset over CPU
quota as the primary CPU-isolation mechanism. Parallel benchmarks MUST record
the CPU set available to the workload.

Networking SHOULD be disabled for workloads that do not require it. Filesystem,
network, process-creation, and other environment-heavy benchmarks require an
explicit methodology that states which container/host effects are in scope.

## Repository and Git workflow

Work directly from the current `origin/main`; other agents may publish
concurrently. Before modifying tracked work, fetch the remote and re-read
applicable repository instructions.

Do not force-push. Do not use temporary remote branches unless the user
explicitly requests them. Before publishing, validate the exact intended changed
file set and stage only those paths; do not use `git add .` or `git add -A` in
automated publication scripts.

Repository bootstrap is a special one-time case: the initial commit may be
created only while both the local repository and the remote repository have no
commits. If another initial commit appears remotely, abort instead of reconciling
or replacing it automatically.

## Licensing

The repository is licensed under APL-1.0. `LICENSE.TXT` is authoritative and
contains the Protos Benchmarks-specific Exhibit A.

New source-code and executable-script files MUST carry the APL license notice
from Part 5 of Exhibit A unless their format makes an inline notice impractical;
in that case place the notice where a user would reasonably look for it and keep
the exception explicit.

Documentation and metadata files do not require a repeated source-code header
unless the license or their format specifically requires one.

## Language

Repository documentation, code, comments, commit messages, benchmark identifiers,
and generated report labels are written in English unless a benchmark explicitly
requires another language as test data.
