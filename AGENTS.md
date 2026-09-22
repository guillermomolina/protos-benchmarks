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

## Adding or extending benchmark harnesses

These rules apply whenever a new benchmark harness is created, or an existing
one is substantially changed (new container base, new language/JDK helper,
new profiling/JFR capture path, new measurement mechanism). They make durable
the recurring failure modes seen in past harness work; treat each point as a
precondition to check before considering the implementation done, not as a
retrospective explanation of any one past incident.

**Toolchain and container drift.** When a harness installs packages inside a
container, do not assume a package name is stable across base-image
generations. Verify each required package against the image actually in use;
do not infer availability from an older image. Prefer the canonical package
form for the current pinned toolchain. If a build-arg parameterizes package
selection for historical compatibility, document its default and the value
the current configuration actually uses. (Conceptual pattern, not a fixed
dependency of any one benchmark: a package named one way in an older base
image and another way in a newer one — e.g. `python39` vs `python3` across
Oracle Linux major versions.)

**Exact JDK/API compatibility.** Java helpers and JFR-based instrumentation
MUST compile against the exact JDK the harness pins, using only types,
exceptions, modules, and methods that JDK version actually provides. Do not
assume APIs from a different JDK, and do not resolve an incompatibility by
silently changing which JDK the harness targets. Compiling successfully
against a locally installed JDK is not evidence of compatibility with the
pinned harness JDK.

**Define the evidence unit first.** Before implementing a measurement
harness, define what one evidence unit is: exact Protos revision, exact
benchmark revision, workload, canonical/control variant, toolchain identity,
host/resource policy, correctness result, measurement policy, and raw
artifact identity, as applicable (see `AGENTS.work/REPRODUCIBILITY.md` for
the full identity/retention requirements — do not re-derive them here).
Do not start producing results and decide afterward what a unit of evidence
means.

**Measurement phase boundaries.** Startup, warmup, and steady-state are
distinct measurement classes (`AGENTS.work/PERFORMANCE.md`). A capture MUST
NOT be labelled steady-state if its capture mechanism can also include
bootstrap or warmup without an objective boundary. For profiling/JFR
captures, the phase boundary MUST be implemented in the harness itself, not
left to a later, ad hoc interpretation by whoever analyzes the data; if
analysis needs to filter by timestamp or phase marker, that mechanism must be
unambiguous and reproducible.

**Profiling depth and causal evidence.** When the investigation question is
causal and depends on call paths, do not reduce profiling to top-frame
histograms; retain the stack depth needed to answer the question, bounded to
a reasonable limit, and retain enough raw evidence to reconstruct the
analysis. Hotspot frequency is not causal attribution: a figure such as "35%
of samples land in frame X" does not by itself establish what work happens
inside that frame.

**Correctness before timing.** This restates and applies
`AGENTS.work/PERFORMANCE.md`'s correctness-before-timing rule to harness work
specifically, including diagnostics: correctness MUST be PASS for the same
variant and workload being measured before any timing or profile is accepted
as evidence. If correctness fails, there is no timing, no performance claim,
and no retained performance evidence — this applies to profiling/diagnostic
captures as much as to wall-clock benchmarks.

**Uncommitted iteration.** This restates the Universal repository workflow
commit-timing rule above as it applies to harness work: the edit → build/test
→ fix loop stays uncommitted while a harness is being implemented or
repaired. Do not create intermediate commits merely to checkpoint a failure,
a compilation fix, a package-name correction, a test fix, or another
in-progress harness adjustment. Commit only once the requested slice is
complete, required validation has passed, the changed-file set has been
reviewed, and the diff is coherent — normally one coherent commit per slice.
This does not change Human-executor mode: the human still runs
builds/tests/benchmarks and still performs `add`/`commit`/push.

### Benchmark-harness precheck

Before editing a new or substantially changed benchmark harness:

- [ ] Read `AGENTS.md`, `AGENTS.work/PERFORMANCE.md`, and
      `AGENTS.work/REPRODUCIBILITY.md`.
- [ ] Verify the actual container/toolchain identity in use.
- [ ] Verify every required OS package against the actual base image.
- [ ] Compile new Java helpers against the exact pinned JDK.
- [ ] Define the evidence unit before implementing the harness.
- [ ] Define startup/warmup/steady-state boundaries before adding profiling.
- [ ] Preserve the stack depth required for causal attribution.
- [ ] Require correctness PASS before accepting timing/profile evidence.
- [ ] Keep the implementation slice uncommitted while iterating.
- [ ] Do not reuse historical measurements as current-`main` evidence.

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
