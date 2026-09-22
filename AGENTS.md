# Repository instructions

These instructions apply to the entire `guillermomolina/protos-benchmarks`
repository.

## Role of this repository

This repository is the companion benchmark harness and evidence store for the
Protos project. The canonical Protos implementation, normative specification,
and formal `PERFxxx` live work-item lifecycle remain owned by
`guillermomolina/protos`.

Canonical durable, non-normative Protos project records live in
`guillermomolina/protos-project-docs:docs/project/**`.

Benchmark source, raw measurements, generated reports/artifacts, harness-local
reproducibility evidence, and benchmark implementation remain owned by this
repository.

Do not create an independent formal Protos lifecycle here that can contradict
the canonical Protos project Issue. When work is performed for a formal Protos
`PERFxxx` item, use the identifier and live state published by
`guillermomolina/protos`. When durable Protos project evidence is required,
publish the project record in `guillermomolina/protos-project-docs` and reference
the exact benchmark-repository revision or immutable artifact identity rather
than copying product-local evidence merely for convenience.

## Human-executor mode

This repository uses a human-executor workflow, matching the model already
established in `guillermomolina/protos`.

The agent investigates, reasons, and edits: it reads the applicable
instructions, inspects the repository, and creates or changes files.
Read-only inspection (file reads, searches, `git status`/`diff`/`log`, and a
non-mutating `git fetch`) is agent-executable at any time.

The human executes builds, benchmark runs, tests, validation commands, and
any Git operation that changes repository or remote state (`add`, `commit`,
merge, rebase, push, pull, or a `checkout`/`reset`/`clean` that discards
work). Never infer that a build, benchmark, test, or validation succeeded
because the change looks correct; hand over the smallest useful command and
wait for the reported result.

Live GitHub coordination (Issues, status, project boards) may remain a
governed exception under an explicit `AGENTS.work/` coordination instruction;
this repository does not currently define one. There is no standing
autonomous exception for repository-content publication: commit, push, and
publication are human-executed for every repository this work touches,
including `guillermomolina/protos-project-docs`.

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

## Instruction composition

This file is a binding floor: a work-type file may add detail but never
weaken it. Before starting work, read the file that matches the task's
nature:

- Benchmark methodology, correctness gates, microbenchmark interpretation,
  and cross-language comparison rules: `AGENTS.work/PERFORMANCE.md`.
- Reproducibility and measurement-evidence policy — exact revision pinning,
  runtime/host/container identity, CPU affinity, and raw-measurement
  retention: `AGENTS.work/REPRODUCIBILITY.md`.

`BENCHMARKING.md` holds the detailed benchmark-by-benchmark methodology, exact
commands, and result narratives; the two files above hold the binding
agent-facing rules, not the full write-up.

There is currently no dedicated implementation or GitHub-coordination
work-type file. Generic implementation discipline is covered by Universal
repository workflow below, and GitHub coordination follows the Human-executor
mode exception rule above until this repository defines its own
`AGENTS.work/COORDINATION.md`. Add a scoped file, and a line here, only when
one of these genuinely grows enough to need its own instruction.

## Universal repository workflow

Work directly from the current `origin/main`; other agents may publish
concurrently. Before modifying tracked work, fetch the remote and re-read
applicable repository instructions. Keep changes scoped to the requested
task, and preserve any unrelated tracked or untracked work already present
rather than deleting or overwriting it.

Do not force-push and do not rewrite published history. Do not use temporary
remote branches unless the user explicitly requests them. Before publishing,
validate the exact intended changed file set and stage only those paths; do
not use `git add .` or `git add -A` in automated publication scripts.

Do not commit an implementation slice while it is still being iterated. Keep
the working tree uncommitted while builds, tests, benchmarks, and validation
are being used to discover or repair implementation defects; under
Human-executor mode above, the human already runs each of those and reports
the result back, so nothing about this rule changes who runs `add`/`commit`.
Commit only once the requested slice is complete, the required validation
passes, the intended changed-file set has been reviewed, and the final diff
is coherent. A single implementation slice SHOULD normally result in one
coherent commit; intermediate repair commits are not required and MUST NOT
be used merely to checkpoint failed or incomplete iterations — defects
discovered while validating a slice are repaired within that same slice, not
published as separate commits.

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
