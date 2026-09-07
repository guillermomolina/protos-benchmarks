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

old = '''    public static Object invokeImmediateMethod(
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

new = '''    public static Object invokeImmediateMethod(
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
    raise SystemExit("A4G1_PRECONDITION: expected exactly one pinned invokeImmediateMethod body")
text = text.replace(old, new, 1)

invoke_prepared = (
    "    private static Object invokePrepared("
    "ProtosClosureValue closure, List<?> supplied, ProtosActivation activation) {"
)
annotation = "    @com.oracle.truffle.api.CompilerDirectives.TruffleBoundary\n"
if text.count(invoke_prepared) != 1:
    raise SystemExit("A4G1_PRECONDITION: expected exactly one invokePrepared signature")
if annotation + invoke_prepared in text:
    raise SystemExit("A4G1_PRECONDITION: invokePrepared already bounded")
text = text.replace(invoke_prepared, annotation + invoke_prepared, 1)

path.write_text(text, encoding="utf-8")
check = path.read_text(encoding="utf-8")

if check.count("@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary") != 2:
    raise SystemExit("A4G1_VERIFY: expected exactly two diagnostic boundaries")
if "private static ProtosActivation prepareImmediateMethodActivation(" not in check:
    raise SystemExit("A4G1_VERIFY: helper missing")
if "task.evaluatorContinuation().invocationActivation(activationFactory)" not in check:
    raise SystemExit("A4G1_VERIFY: replay branch missing")
if "activation.attachTask(task);" not in check:
    raise SystemExit("A4G1_VERIFY: attachTask missing")

entry_start = check.index("    public static Object invokeImmediateMethod(")
helper_start = check.index("    private static ProtosActivation prepareImmediateMethodActivation(")
entry = check[entry_start:helper_start]
for required in (
    'Objects.requireNonNull(closure, "closure");',
    'Objects.requireNonNull(receiver, "receiver");',
    'Objects.requireNonNull(methodHome, "methodHome");',
    'Objects.requireNonNull(supplied, "supplied");',
    'Objects.requireNonNull(caller, "caller");',
):
    if required not in entry:
        raise SystemExit(f"A4G1_VERIFY: public entry lost check: {required}")

print("A4G1_PREPARATION_REFACTOR: PASS")
print("A4G1_BOUNDARY_PLACEMENT: PASS count=2")
