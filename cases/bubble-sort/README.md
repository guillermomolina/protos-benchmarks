# Bubble sort: algorithm-equivalent comparison

The four implementations use the same fixed permutation of the integers 1..64,
constructed as a fresh mutable array **inside every `run` call**. The same
seven locals (`values`, `n`, `i`, `j`, `temp`, `checksum`, `k`) are initialized in
the same order before the loops. There are no per-iteration local declarations,
helpers, built-in sorting methods, destructuring swaps, or early-exit flags.

Every call performs 63 outer passes, 2,016 adjacent comparisons, and 928 swaps.
The first two nested pre-test `while` loops perform bubble sort with the active
bound shrinking after each pass. Exactly one conditional implements the explicit
temporary-variable swap. The third pre-test `while` computes the weighted
checksum `sum((k+1)*values[k])`, `k=0..63`, returning `89440` for the correct
ascending result. Since the input contains each integer 1..64 exactly once,
this checksum reaches its unique maximum only for the correctly sorted order.

Protos must express a pre-test loop through `conditionClosure.whileTrue(body)`;
JavaScript, Python and Ruby use the language's `while` syntax. Protos's
contextual `if(condition) { ... }` lowers to `ifTrue`, whereas the peers use
native `if`. Indexing syntax is shared, but Protos indexing dispatches to its
`at` / `atPut` protocol. These runtime differences remain part of the
comparison, not a claim of identical bytecode or allocations.

The work measured per call **includes** fresh array construction, sorting and
the checksum. The `run` callable itself is obtained once by each language's
existing Polyglot adapter, outside the timed call.

The catalog uses the default `jvm_sample_calls = 1`, unlike the primitive
microbenchmarks. Follow `AGENTS.work/PERFORMANCE.md` and
`AGENTS.work/REPRODUCIBILITY.md`: require correctness PASS before accepting
smoke/reference timing, retain raw evidence, and pin runtime, benchmark
revision, product revision and container image identities.
