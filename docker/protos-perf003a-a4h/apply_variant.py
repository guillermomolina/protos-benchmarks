#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. See LICENSE.TXT.
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / "src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java"
text = path.read_text(encoding="utf-8")

old = """    public static Object invokeImmediateMethod(
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

"""

new = """    public static Object invokeImmediateMethod(
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

        ProtosActivation activation;
        if (caller.task().isPresent()) {
            activation =
                    prepareImmediateMethodTaskActivation(
                            closure,
                            receiver,
                            methodHome,
                            supplied,
                            caller,
                            caller.task().orElseThrow());
        } else {
            activation =
                    prepareImmediateMethodDirectActivation(
                            closure, receiver, methodHome, supplied, caller);
        }
        return invokePrepared(closure, supplied, activation);
    }

    private static ProtosActivation prepareImmediateMethodDirectActivation(
            ProtosClosureValue closure,
            Object receiver,
            ProtosObjectValue methodHome,
            List<?> supplied,
            ProtosActivation caller) {
        ProtosActivation activation =
                ProtosActivation.forImmediateMethodInvocation(
                        closure,
                        supplied,
                        receiver,
                        methodHome,
                        caller.prelude().orElse(null),
                        caller.actorModuleState(),
                        caller.currentModuleKey().orElse(null),
                        caller.executionDomain());
        activation.inheritDynamicControlState(caller);
        return activation;
    }

    private static ProtosActivation prepareImmediateMethodTaskActivation(
            ProtosClosureValue closure,
            Object receiver,
            ProtosObjectValue methodHome,
            List<?> supplied,
            ProtosActivation caller,
            com.guillermomolina.protos.runtime.ProtosTask task) {
        com.guillermomolina.protos.runtime.ProtosPrelude fallbackPrelude =
                caller.prelude().orElse(null);
        java.util.function.Supplier<ProtosActivation> activationFactory =
                () ->
                        ProtosActivation.forImmediateMethodInvocation(
                                closure,
                                supplied,
                                receiver,
                                methodHome,
                                fallbackPrelude,
                                caller.actorModuleState(),
                                caller.currentModuleKey().orElse(null),
                                caller.executionDomain());
        ProtosActivation activation =
                task.evaluatorContinuation().invocationActivation(activationFactory);
        activation.attachTask(task);
        return activation;
    }

"""

if text.count(old) != 1:
    raise SystemExit("A4H1_PRECONDITION: pinned invokeImmediateMethod body mismatch")
text = text.replace(old, new, 1)

sig = "    private static Object invokePrepared(ProtosClosureValue closure, List<?> supplied, ProtosActivation activation) {"
ann = "    @com.oracle.truffle.api.CompilerDirectives.TruffleBoundary\n"
if text.count(sig) != 1:
    raise SystemExit("A4H1_PRECONDITION: invokePrepared signature mismatch")
text = text.replace(sig, ann + sig, 1)
path.write_text(text, encoding="utf-8")

check = path.read_text(encoding="utf-8")
if check.count("@com.oracle.truffle.api.CompilerDirectives.TruffleBoundary") != 1:
    raise SystemExit("A4H1_VERIFY: expected exactly one generated boundary")
for x in (
    "prepareImmediateMethodDirectActivation(",
    "prepareImmediateMethodTaskActivation(",
    "activation.inheritDynamicControlState(caller);",
    "task.evaluatorContinuation().invocationActivation(activationFactory)",
    "activation.attachTask(task);",
):
    if x not in check:
        raise SystemExit("A4H1_VERIFY: missing " + x)
direct = check[check.index("    private static ProtosActivation prepareImmediateMethodDirectActivation("):
               check.index("    private static ProtosActivation prepareImmediateMethodTaskActivation(")]
for x in ("Supplier", "evaluatorContinuation", "attachTask", "caller.task"):
    if x in direct:
        raise SystemExit("A4H1_VERIFY: direct path contains task machinery: " + x)

print("A4H1_SYNC_TASK_SPLIT: PASS")
print("A4H1_DIRECT_PATH_TASK_MACHINERY: NONE")
print("A4H1_DIAGNOSTIC_BOUNDARY: PASS count=1")
