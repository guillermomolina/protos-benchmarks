/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
 * DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
 * DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
 * OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
 * THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
 * OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
 * THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
 * FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
 * https://github.com/guillermomolina/protos-benchmarks
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
 * the specific language governing rights and limitations under the License.
 */

package com.guillermomolina.protos.benchmarks.perf010a;

import com.guillermomolina.protos.runtime.ProtosExecutionContextValue;
import com.guillermomolina.protos.runtime.ProtosObjectValue;
import com.guillermomolina.protos.runtime.ProtosReturnHome;
import java.lang.management.ManagementFactory;

public final class Perf010aContextMaterializationProbe {
    private static volatile Object blackhole;

    private Perf010aContextMaterializationProbe() {}

    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "usage: Perf010aContextMaterializationProbe <warmup> <steady>");
        }

        int warmup = Integer.parseInt(args[0]);
        int steady = Integer.parseInt(args[1]);

        var bean =
                (com.sun.management.ThreadMXBean)
                        ManagementFactory.getThreadMXBean();

        if (!bean.isThreadAllocatedMemorySupported()) {
            throw new IllegalStateException(
                    "thread allocated-memory measurement is unsupported");
        }

        if (!bean.isThreadAllocatedMemoryEnabled()) {
            bean.setThreadAllocatedMemoryEnabled(true);
        }

        measure(bean, "execution-context", warmup, steady);
        measure(bean, "ordinary-object", warmup, steady);
        measure(bean, "return-home", warmup, steady);
    }

    private static void measure(
            com.sun.management.ThreadMXBean bean,
            String kind,
            int warmup,
            int steady) {

        run(kind, warmup);

        long threadId = Thread.currentThread().threadId();
        long bytesBefore = bean.getThreadAllocatedBytes(threadId);
        long started = System.nanoTime();

        run(kind, steady);

        long elapsed = System.nanoTime() - started;
        long allocated =
                bean.getThreadAllocatedBytes(threadId) - bytesBefore;

        System.out.printf(
                "CASE=%s ITERATIONS=%d BYTES_PER_OP=%.6f NS_PER_OP=%.6f%n",
                kind,
                steady,
                (double) allocated / steady,
                (double) elapsed / steady);
    }

    private static void run(String kind, int iterations) {
        Object parent = ProtosObjectValue.rootObject();

        for (int i = 0; i < iterations; i++) {
            blackhole =
                    switch (kind) {
                        case "execution-context" ->
                                new ProtosExecutionContextValue(parent);
                        case "ordinary-object" ->
                                new ProtosObjectValue(parent);
                        case "return-home" ->
                                new ProtosReturnHome();
                        default ->
                                throw new IllegalArgumentException(
                                        "unknown case: " + kind);
                    };
        }
    }
}
