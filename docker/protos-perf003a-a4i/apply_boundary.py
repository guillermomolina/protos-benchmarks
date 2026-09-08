#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. See LICENSE.TXT.
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: apply_boundary.py <protos-root>")

root = Path(sys.argv[1])
path = root / "src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java"
text = path.read_text(encoding="utf-8")

old = r'''    public static Object invokeImmediateMethod(
            ProtosClosureValue closure,
            Object receiver,
            ProtosObjectValue methodHome,
            List<?> supplied,
            ProtosActivation caller) {
        Objects.requireNonNull(closure, "closure");
        Objects.requireNonNull(receiver, "receiver");
        Objects.requireNonNull(methodHome, "methodHome");
        Objects.requireNonNull(supplied, "supplied");
        Objects.requireNonNull(caller, "caller");

        com.guillermomolina.protos.runtime.ProtosPrelude fallbackPrelude =
                caller.prelude().orElse(null);
        java.util.function.Supplier<ProtosActivation> activationFactory =
                () -> {
                    ProtosActivation created =
                            ProtosActivation.forImmediateMethodInvocation(
                                    closure,
                                    supplied,
                                    receiver,
                                    methodHome,
                                    fallbackPrelude,
                                    caller.actorModuleState(),
                                    caller.currentModuleKey().orElse(null),
                                    caller.executionDomain());
                    if (caller.task().isEmpty()) {
                        created.inheritDynamicControlState(caller);
                    }
                    return created;
                };

        ProtosActivation activation;
        if (caller.task().isPresent()) {
            com.guillermomolina.protos.runtime.ProtosTask task = caller.task().orElseThrow();
            activation = task.evaluatorContinuation().invocationActivation(activationFactory);
            activation.attachTask(task);
        } else {
            activation = activationFactory.get();
        }
        return invokePrepared(closure, supplied, activation);
    }

'''

new = r'''    public static Object invokeImmediateMethod(
            ProtosClosureValue closure,
            Object receiver,
            ProtosObjectValue methodHome,
            List<?> supplied,
            ProtosActivation caller) {
        Objects.requireNonNull(closure, "closure");
        Objects.requireNonNull(receiver, "receiver");
        Objects.requireNonNull(methodHome, "methodHome");
        Objects.requireNonNull(supplied, "supplied");
        Objects.requireNonNull(caller, "caller");

        ProtosActivation activation =
                prepareImmediateMethodActivation(
                        closure, receiver, methodHome, supplied, caller);
        return invokePrepared(closure, supplied, activation);
    }

    @com.oracle.truffle.api.CompilerDirectives.TruffleBoundary
    private static ProtosActivation prepareImmediateMethodActivation(
            ProtosClosureValue closure,
            Object receiver,
            ProtosObjectValue methodHome,
            List<?> supplied,
            ProtosActivation caller) {
        com.guillermomolina.protos.runtime.ProtosPrelude fallbackPrelude =
                caller.prelude().orElse(null);
        java.util.function.Supplier<ProtosActivation> activationFactory =
                () -> {
                    ProtosActivation created =
                            ProtosActivation.forImmediateMethodInvocation(
                                    closure,
                                    supplied,
                                    receiver,
                                    methodHome,
                                    fallbackPrelude,
                                    caller.actorModuleState(),
                                    caller.currentModuleKey().orElse(null),
                                    caller.executionDomain());
                    if (caller.task().isEmpty()) {
                        created.inheritDynamicControlState(caller);
                    }
                    return created;
                };

        ProtosActivation activation;
        if (caller.task().isPresent()) {
            com.guillermomolina.protos.runtime.ProtosTask task = caller.task().orElseThrow();
            activation = task.evaluatorContinuation().invocationActivation(activationFactory);
            activation.attachTask(task);
        } else {
            activation = activationFactory.get();
        }
        return activation;
    }

'''

if text.count(old) != 1:
    raise SystemExit("A4I_PRECONDITION: pinned invokeImmediateMethod body mismatch")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
check = path.read_text(encoding="utf-8")
if check.count("@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary") != 1:
    raise SystemExit("A4I_VERIFY: expected exactly one boundary")
prep = check.index("private static ProtosActivation prepareImmediateMethodActivation(")
inv = check.index("private static Object invokePrepared(")
if "@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary" not in check[max(0, prep-120):prep]:
    raise SystemExit("A4I_VERIFY: preparation helper is not bounded")
if "@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary" in check[max(0, inv-120):inv]:
    raise SystemExit("A4I_VERIFY: invokePrepared must remain unbounded")
for required in (
    "task.evaluatorContinuation().invocationActivation(activationFactory)",
    "activation.attachTask(task);",
    "created.inheritDynamicControlState(caller);",
):
    if required not in check:
        raise SystemExit("A4I_VERIFY: missing semantic preparation statement: " + required)
print("A4I_PREPARATION_BOUNDARY_ONLY: PASS")
print("PREPARATION_BOUNDARY_COUNT=1")
print("INVOKE_PREPARED_BOUNDARY_COUNT=0")
