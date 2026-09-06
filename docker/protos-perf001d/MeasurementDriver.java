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

package com.guillermomolina.protos.cli;

import com.guillermomolina.protos.execution.ProtosCoreBootstrap;
import com.guillermomolina.protos.execution.ProtosSourceCompiler;
import com.guillermomolina.protos.runtime.ProtosActivation;
import com.guillermomolina.protos.runtime.ProtosActorExecutionDomain;
import com.guillermomolina.protos.runtime.ProtosActorModuleState;
import com.guillermomolina.protos.runtime.ProtosPrelude;
import java.nio.file.Files;
import java.nio.file.Path;

public final class MeasurementDriver {
    private MeasurementDriver() {}

    private static ProtosActivation newActivation(ProtosPrelude prelude) {
        return prelude.newModuleActivation(
                new ProtosActorModuleState(),
                null,
                prelude.newExecutionContext(),
                new ProtosActorExecutionDomain());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "usage: MeasurementDriver <source.protos> <expected> <warmup> <steady>");
        }

        Path sourcePath = Path.of(args[0]);
        String expected = args[1];
        int warmup = Integer.parseInt(args[2]);
        int steady = Integer.parseInt(args[3]);
        if (warmup < 0 || steady < 0) {
            throw new IllegalArgumentException("iteration counts must be non-negative");
        }

        String source = Files.readString(sourcePath);
        ProtosPrelude prelude =
                new ProtosCoreBootstrap().bootstrap(Path.of("/opt/protos/protos/lib/core"));

        // Bootstrap, source read, parse/lower and CallTarget creation are deliberately
        // outside each iteration timing. The same CallTarget is reused to expose
        // warmup/JIT behavior. Each iteration gets a fresh module activation so
        // program-local mutations do not leak across equivalent executions.
        var target = new ProtosSourceCompiler().compile(source);
        ProtosValueRenderer renderer = new ProtosValueRenderer();

        for (int i = 1; i <= warmup + steady; i++) {
            ProtosActivation activation = newActivation(prelude);
            long start = System.nanoTime();
            Object result = target.call(activation);
            long elapsed = System.nanoTime() - start;

            String actual = renderer.render(result);
            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                        "result mismatch: expected=" + expected + " actual=" + actual);
            }

            if (i <= warmup) {
                System.out.println("WARMUP\t" + i + "\t" + elapsed + "\t" + actual);
            } else {
                System.out.println(
                        "STEADY\t" + (i - warmup) + "\t" + elapsed + "\t" + actual);
            }
        }
    }
}
