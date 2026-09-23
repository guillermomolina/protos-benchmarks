/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
 * DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
 * DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
 * OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
 * THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
 * "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE.
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
 * the specific language governing rights and limitations under the License.
 */

import com.guillermomolina.protos.runtime.ProtosActivation;
import com.guillermomolina.protos.runtime.ProtosObjectValue;
import com.guillermomolina.protos.runtime.ProtosPrelude;
import com.oracle.truffle.api.interop.InteropLibrary;
import java.util.ArrayList;
import java.util.List;

/** PERF010-A Tier-B context-storage semantic gate; no timing is performed here. */
public final class Perf010aContextStorageCorrectnessProbe {
    private Perf010aContextStorageCorrectnessProbe() {}

    public static void main(String[] args) throws Exception {
        ProtosObjectValue root = ProtosObjectValue.rootObject();
        ProtosObjectValue contextPrototype = new ProtosObjectValue(root);
        ProtosObjectValue errorPrototype = new ProtosObjectValue(root);
        ProtosObjectValue bindings = new ProtosObjectValue(contextPrototype);
        bindings.createLocalSlot("Context", contextPrototype);
        bindings.createLocalSlot("Error", errorPrototype);
        bindings.freeze();
        ProtosPrelude prelude = new ProtosPrelude(bindings, contextPrototype);

        ProtosObjectValue first = prelude.newExecutionContext();
        ProtosObjectValue second = prelude.newExecutionContext();
        require(first != second, "fresh context identity across calls");
        require(first.getClass() == ProtosObjectValue.class, "context runtime class");
        require(second.getClass() == ProtosObjectValue.class, "context runtime class second");
        require(first.parent().orElse(null) == contextPrototype, "Context delegation");

        first.createLocalSlot("parameter", "bound");
        ProtosActivation parameterActivation = new ProtosActivation(first, List.of(), root);
        require("bound".equals(parameterActivation.lookup("parameter").orElse(null)),
                "parameter bind/read");

        first.createLocalSlot("local", "v1");
        require("v1".equals(first.readLocalSlot("local").orElse(null)), "local create/read");
        first.assignLocalSlot("local", "v2");
        require("v2".equals(first.readLocalSlot("local").orElse(null)), "local assign");
        require("v2".equals(first.removeLocalSlot("local")), "local remove result");
        require(first.readLocalSlot("local").isEmpty(), "local remove visibility");

        ProtosObjectValue closed = prelude.newExecutionContext();
        closed.createLocalSlot("x", "one");
        closed.close();
        closed.assignLocalSlot("x", "two");
        require("two".equals(closed.readLocalSlot("x").orElse(null)), "closed assign semantics");
        requireThrows(() -> closed.createLocalSlot("y", "no"), "closed create rejection");
        requireThrows(() -> closed.removeLocalSlot("x"), "closed remove rejection");
        closed.freeze();
        requireThrows(() -> closed.assignLocalSlot("x", "no"), "frozen assign rejection");

        ProtosObjectValue ordering = prelude.newExecutionContext();
        ordering.createLocalSlot("a", "1");
        ordering.createLocalSlot("b", "2");
        ordering.createLocalSlot("c", "3");
        require(new ArrayList<>(ordering.localSlotsSnapshot().keySet())
                        .equals(List.of("a", "b", "c")),
                "local snapshot insertion order");
        ordering.removeLocalSlot("b");
        ordering.createLocalSlot("b", "4");
        require(new ArrayList<>(ordering.localSlotsSnapshot().keySet())
                        .equals(List.of("a", "c", "b")),
                "remove/recreate insertion order");

        contextPrototype.createLocalSlot("fromContextPrototype", "prototype");
        ProtosObjectValue delegated = prelude.newExecutionContext();
        require("prototype".equals(delegated.readSlot("fromContextPrototype").orElse(null)),
                "Context prototype/delegation behavior");

        ProtosObjectValue captured = prelude.newExecutionContext();
        captured.createLocalSlot("name", "captured");
        ProtosObjectValue current = prelude.newExecutionContext();
        current.createLocalSlot("name", "current");
        ProtosActivation shadowing = new ProtosActivation(current, List.of(captured), root);
        require("current".equals(shadowing.lookup("name").orElse(null)), "local shadowing");
        current.removeLocalSlot("name");
        require("captured".equals(shadowing.lookup("name").orElse(null)),
                "captured lexical lookup");
        captured.assignLocalSlot("name", "mutated");
        require("mutated".equals(shadowing.lookup("name").orElse(null)),
                "captured lexical mutation visibility");
        require(shadowing.writableLexicalContext("name").orElse(null) == captured,
                "writable lexical target");

        ProtosObjectValue receiver = new ProtosObjectValue(root);
        receiver.createLocalSlot("receiverOnly", "receiver");
        ProtosActivation receiverFallback =
                new ProtosActivation(prelude.newExecutionContext(), List.of(), receiver);
        require("receiver".equals(receiverFallback.lookup("receiverOnly").orElse(null)),
                "receiver fallback after lexical miss");

        ProtosObjectValue methodHome = new ProtosObjectValue(root);
        ProtosObjectValue methodContext = prelude.newExecutionContext();
        ProtosActivation method =
                ProtosActivation.withMethodHome(methodContext, List.of(), receiver, methodHome);
        require(method.context() == methodContext, "context intrinsic identity");
        require(method.receiver() == receiver, "method receiver behavior");
        require(method.methodHome().orElse(null) == methodHome, "methodHome behavior");

        ProtosObjectValue closureOuter = prelude.newExecutionContext();
        closureOuter.createLocalSlot("shared", "before");
        ProtosActivation creator = new ProtosActivation(closureOuter, List.of(), root);
        List<ProtosObjectValue> capturedByClosure = creator.lexicalContextsForClosureCapture();
        require(capturedByClosure.size() == 1 && capturedByClosure.get(0) == closureOuter,
                "closure capture retains context by reference");
        ProtosActivation closureInvocation =
                new ProtosActivation(prelude.newExecutionContext(), capturedByClosure, root);
        closureOuter.assignLocalSlot("shared", "after");
        require("after".equals(closureInvocation.lookup("shared").orElse(null)),
                "closure capture by reference mutation visibility");

        ProtosObjectValue interopContext = prelude.newExecutionContext();
        interopContext.createLocalSlot("toolVisible", "yes");
        InteropLibrary interop = InteropLibrary.getUncached();
        require(interop.hasMembers(interopContext), "interop has members");
        require(interop.isMemberReadable(interopContext, "toolVisible"), "interop readable member");
        require("yes".equals(interop.readMember(interopContext, "toolVisible")),
                "interop/tooling-visible local slots");

        System.out.println("FRESH_CONTEXT_PER_INVOCATION=PASS");
        System.out.println("CONTEXT_OBJECT_IDENTITY_PRESERVED=PASS");
        System.out.println("CONTEXT_DELEGATION_PRESERVED=PASS");
        System.out.println("PARAMETER_BIND_READ=PASS");
        System.out.println("LOCAL_CREATE_READ_ASSIGN_REMOVE=PASS");
        System.out.println("LEXICAL_LOOKUP_ORDER_PRESERVED=PASS");
        System.out.println("CAPTURE_BY_REFERENCE_PRESERVED=PASS");
        System.out.println("RECEIVER_FALLBACK_PRESERVED=PASS");
        System.out.println("CONTEXT_INTEROP_LOCAL_SLOTS_PRESERVED=PASS");
        System.out.println("METHOD_RECEIVER_METHOD_HOME_PRESERVED=PASS");
        System.out.println("PERF010A_CONTEXT_STORAGE_CORRECTNESS=PASS");
    }

    private static void require(boolean condition, String description) {
        if (!condition) throw new IllegalStateException("correctness gate failed: " + description);
    }

    private static void requireThrows(Runnable action, String description) {
        try {
            action.run();
        } catch (IllegalStateException expected) {
            return;
        }
        throw new IllegalStateException("correctness gate failed: " + description);
    }
}
