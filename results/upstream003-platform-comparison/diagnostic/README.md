# UPSTREAM003 GraalVM / Truffle platform comparison — compiler diagnostic

This is a separate diagnostic evidence unit. It is not timing evidence.

The raw TraceCompilation/TraceCompilationDetails/TraceCompilationCallTree streams are retained under `logs/`. Parsed fields are observational only. Fields that the emitted trace does not expose are explicitly `UNAVAILABLE_FROM_TRACE`; a missing textual marker is never treated as proof that a compiler structure is absent.

Primary diagnostic workloads: micro/closure-call, micro/method-call, runtime/monomorphic-dispatch.
