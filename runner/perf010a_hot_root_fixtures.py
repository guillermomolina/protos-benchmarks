# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
# THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
# OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
# THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
# FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

"""Synthetic compiler-trace logs in the exact GraalVM 25.4 record format.

Used by `runner/perf010a_hot_root.py validate` and by the unit tests, so the parser contract is
proven without Docker or a real compiler run. Every builder line has the shape of a record retained
in results/upstream003-platform-comparison/diagnostic/logs; only the ids, hashes and CompIds are
invented, and they are run-local values that no assertion may treat as durable.
"""

from __future__ import annotations

from typing import Any, Callable

UTC = "|UTC 2026-09-28T08:57:45.629|Src n/a"
PHASES = ("startup", "warmup", "steady", "closing", "end")
PERMANENT_CHAIN = (
    "jdk.graal.compiler.core.common.PermanentBailoutException:jdk.graal.compiler.core.common."
    "GraalBailoutException:jdk.vm.ci.code.BailoutException:java.lang.RuntimeException:java.lang.Exception:"
)
TEMPORARY_CHAIN = (
    "jdk.graal.compiler.core.common.RetryableBailoutException:jdk.vm.ci.code.BailoutException:"
    "java.lang.RuntimeException:java.lang.Exception:"
)
PERMANENT_REASON = (
    "jdk.graal.compiler.core.common.PermanentBailoutException: Too deep inlining, probably caused by recursive inlining."
)
TEMPORARY_REASON = "jdk.vm.ci.code.BailoutException: node source positions changed, retrying"


def label(name: str, suffix: str) -> str:
    return f"{name}@{suffix}"


class LogBuilder:
    def __init__(self, engine: int = 2) -> None:
        self.engine = engine
        self.lines: list[str] = [
            "WARNING: A terminally deprecated method in sun.misc.Unsafe has been called",
            "[To redirect Truffle log output to a file use one of the following options:",
            "* '-Dpolyglot.log.file=<path>' if the option is passed using the host Java launcher.]",
        ]

    def mark(self, phase: str) -> "LogBuilder":
        self.lines.append(f"PERF010A_HOTROOT_MARK phase={phase}")
        return self

    def raw(self, text: str) -> "LogBuilder":
        self.lines.append(text)
        return self

    def _opt(self, verb: str, ident: int, name: str, rest: str) -> None:
        self.lines.append(f"[engine] opt {verb.ljust(7)}engine={self.engine}  id={ident}   {name.ljust(44)}{rest}")

    def queued(self, ident: int, name: str, tier: int = 1) -> "LogBuilder":
        self._opt("queued", ident, name, f"|Tier {tier}|Count/Thres        400/      400|Queue: Size    1 Change +1  Load  1.00 Time     0us{UTC}")
        return self

    def start(self, ident: int, name: str, tier: int = 1) -> "LogBuilder":
        self._opt("start", ident, name, f"|Tier {tier}|Priority    373523|Rate 1.490158|Queue: Size    0 Change +0  Load  1.00 Time     0us{UTC}|Bonuses first tier")
        return self

    def done(self, ident: int, name: str, tier: int, comp_id: int) -> "LogBuilder":
        self._opt("done", ident, name, f"|Tier {tier}|Time   359( 335+24  )ms|AST    2|Inlined   0Y   0N|IR    150/   221|CodeSize    1037|Addr 0x7ff0c655ec00|CompId {comp_id}   {UTC}")
        return self

    def failed(self, ident: int, name: str, tier: int, *, permanent: bool = True) -> "LogBuilder":
        reason = PERMANENT_REASON if permanent else TEMPORARY_REASON
        self._opt("failed", ident, name, f"|Tier {tier}|Time   662( 662+0   )ms|Reason: {reason}")
        self.lines += [
            "== Inlined methods ordered by inlining frequency:",
            "java.util.Locale.getInstance(String, String, String, String, LocaleExtensions) [33]",
            "com.oracle.truffle.runtime.OptimizedCallTarget.profiledPERoot(OptimizedCallTarget.java:725)" + UTC,
        ]
        self.lines.append(f"[engine] opt fail     {name.ljust(44)}|AST      2")
        self.lines += [PERMANENT_CHAIN if permanent else TEMPORARY_CHAIN, reason]
        return self

    def dequeued(self, ident: int, name: str, tier: int = 1, reason: str = "Stale compilation task") -> "LogBuilder":
        self._opt("unque.", ident, name, f"|Tier {tier}|Count/Thres      10000/      400|Queue: Size    4 Change  0  Load  1.00 Time     0us{UTC}|Reason {reason}")
        return self

    def deopt(self, ident: int, name: str, *, invalidated: bool = True, reason: str = "uncommon trap", times: int = 1) -> "LogBuilder":
        for _ in range(times):
            self._opt("deopt", ident, name, f"|Invalidated  {'true' if invalidated else 'false'}|{' ' * 40}{UTC}|Reason {reason}")
        return self

    def perf_warn(self, name: str, target: str, frames: list[str]) -> "LogBuilder":
        self.lines.append(
            f"[engine] perf warn    {name.ljust(44)}|Partial evaluation could not inline the virtual runtime call Interface to HotSpotMethod<{target}> (1149|MethodCallTarget)."
        )
        self.lines.append("  Approximated stack trace for [1149|MethodCallTarget] (append --vm.XX:+UnlockDiagnosticVMOptions):")
        self.lines += [f"    at {frame}" for frame in frames]
        return self

    def dump(self, comp_id: int, name: str, directory: str = "/diag-out/graal_dumps") -> "LogBuilder":
        self.lines.append(f"Dumping debug output to '{directory}/TruffleHotSpotCompilation-{comp_id}[{name}].bgv'")
        return self

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def run(body: Callable[[LogBuilder], None], *, phases: tuple[str, ...] = PHASES) -> str:
    """A complete run: the driver's phase markers around `body`, which runs in the steady phase
    unless it places its own markers."""
    builder = LogBuilder()
    builder.mark(phases[0])
    builder.mark(phases[1])
    body(builder)
    for phase in phases[2:]:
        builder.mark(phase)
    return builder.text()


A = label("ProtosBytecodeRootNodeGen", "6326d182")
B = label("ProtosSemanticBytecodeRootNodeGen", "4ae9cfc1")


def _never_compiled(b: LogBuilder) -> None:
    b.queued(1, A).dequeued(1, A)


def _first_tier_only(b: LogBuilder) -> None:
    b.queued(1, A).start(1, A).done(1, A, 1, 2585)


def _final_tier_stable(b: LogBuilder) -> None:
    b.queued(1, A).start(1, A).done(1, A, 1, 2585).queued(1, A, 2).start(1, A, 2).done(1, A, 2, 2600)


def _permanent_failure(b: LogBuilder) -> None:
    b.queued(1, A).start(1, A).failed(1, A, 1, permanent=True)


def _temporary_failure_retry(b: LogBuilder) -> None:
    b.queued(1, A).start(1, A).failed(1, A, 1, permanent=False)
    b.queued(1, A).start(1, A).done(1, A, 1, 2700).queued(1, A, 2).start(1, A, 2).done(1, A, 2, 2710)


def _invalidated_not_recompiled(b: LogBuilder) -> None:
    _final_tier_stable(b)
    b.deopt(1, A, times=5000)


def _recompiled_successfully(b: LogBuilder) -> None:
    _final_tier_stable(b)
    b.deopt(1, A, times=3).queued(1, A, 2).start(1, A, 2).done(1, A, 2, 2900)


def _generic_replacement(b: LogBuilder) -> None:
    _final_tier_stable(b)
    b.deopt(1, A, reason="Node replaced by generic specialization")


def _unresolved_pending(b: LogBuilder) -> None:
    b.queued(1, A).queued(1, A, 2).start(1, A, 2).done(1, A, 2, 2600)


def _unknown_record(b: LogBuilder) -> None:
    _final_tier_stable(b)
    b.raw(f"[engine] opt reprofile engine=2  id=1   {A.ljust(44)}|Tier 2{UTC}")


def _two_roots_and_warnings(b: LogBuilder) -> None:
    b.queued(1, A).start(1, A)
    b.perf_warn(A, "Map.put(Object, Object)", ["java.util.HashMap.put(HashMap.java:619)", "com.guillermomolina.protos.runtime.ProtosObjectValue.createLocalSlot(ProtosObjectValue.java:208)"])
    b.done(1, A, 1, 2585).dump(2585, A)
    b.queued(2, B).start(2, B).done(2, B, 1, 2586).dump(2586, B)


# name -> (builder body, expected root A fields)
LIFECYCLE_SCENARIOS: dict[str, tuple[Callable[[LogBuilder], None], dict[str, Any]]] = {
    "never_compiled": (_never_compiled, {"OPTIMIZATION_STATE": "NOT_TRIGGERED", "STABLE_FINAL_OPTIMIZED_STATE": "NO", "classes": {"never_compiled": True}}),
    "first_tier_only": (_first_tier_only, {"OPTIMIZATION_STATE": "OPT_DONE", "TIER_REACHED": "1", "STABLE_FINAL_OPTIMIZED_STATE": "NO", "classes": {"first_tier_only": True, "final_tier_done": False}}),
    "final_tier_done": (_final_tier_stable, {"OPTIMIZATION_STATE": "OPT_DONE", "TIER_REACHED": "1,2", "INVALIDATION_OR_RECOMPILATION": "ABSENT", "STABLE_FINAL_OPTIMIZED_STATE": "YES", "classes": {"final_tier_done": True, "stable_final_state": True}}),
    "permanent_failure": (_permanent_failure, {"OPTIMIZATION_STATE": "OPT_FAILED", "STABLE_FINAL_OPTIMIZED_STATE": "NO", "classes": {"permanent_bailout": True, "never_compiled": True}}),
    "temporary_failure_retry": (_temporary_failure_retry, {"OPTIMIZATION_STATE": "OPT_DONE", "STABLE_FINAL_OPTIMIZED_STATE": "YES", "classes": {"temporary_failure_retry": True, "permanent_bailout": False}}),
    "invalidate": (_invalidated_not_recompiled, {"INVALIDATION_OR_RECOMPILATION": "PRESENT", "STABLE_FINAL_OPTIMIZED_STATE": "NO", "classes": {"compiled_then_invalidated": True, "compiled_then_recompiled": False}}),
    "recompile_success": (_recompiled_successfully, {"INVALIDATION_OR_RECOMPILATION": "PRESENT", "STABLE_FINAL_OPTIMIZED_STATE": "YES", "classes": {"compiled_then_invalidated": True, "compiled_then_recompiled": True}}),
    "generic_replacement": (_generic_replacement, {"STABLE_FINAL_OPTIMIZED_STATE": "NO", "classes": {"compiled_then_replaced_by_generic_specialization": True}}),
    "stable_final_state": (_final_tier_stable, {"STABLE_FINAL_OPTIMIZED_STATE": "YES", "classes": {"stable_final_state": True}}),
    "unresolved_pending": (_unresolved_pending, {"STABLE_FINAL_OPTIMIZED_STATE": "INCONCLUSIVE"}),
    "unknown_record": (_unknown_record, {"STABLE_FINAL_OPTIMIZED_STATE": "INCONCLUSIVE", "OPTIMIZATION_STATE": "INCONCLUSIVE"}),
}
