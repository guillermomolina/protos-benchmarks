/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.truffle;

import com.guillermomolina.protos.execution.ProtosExecutionOutcome;
import com.guillermomolina.protos.execution.ProtosStandaloneHostedSession;
import com.guillermomolina.protos.runtime.ProtosIntegerValue;
import java.nio.file.Path;

public final class ProtosJvmVariantRunner {
    private ProtosJvmVariantRunner() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                    "usage: <core-root> <source> <warmup> <steady>");
        }

        Path coreRoot = Path.of(args[0]).toAbsolutePath().normalize();
        Path source = Path.of(args[1]).toAbsolutePath().normalize();
        int warmupIterations = Integer.parseInt(args[2]);
        int steadyIterations = Integer.parseInt(args[3]);

        long setupStart = System.nanoTime();

        try (ProtosStandaloneHostedSession session =
                ProtosStandaloneHostedSession.open(coreRoot, source)) {
            ProtosExecutionOutcome initial = session.initialOutcome();

            if (initial.state() != ProtosExecutionOutcome.State.COMPLETED) {
                throw new IllegalStateException(
                        "initial source execution did not complete: "
                                + initial.state());
            }

            long setupNs = System.nanoTime() - setupStart;

            long started = System.nanoTime();
            String expected = value(session.invokeTopLevel("run"));
            long coldNs = System.nanoTime() - started;

            System.out.println("mode=jvm");
            System.out.println("language=protos");
            System.out.println("source=" + source);
            System.out.println("warmup_iterations=" + warmupIterations);
            System.out.println("steady_iterations=" + steadyIterations);
            System.out.println("setup_ns=" + setupNs);
            System.out.println(
                    "sample phase=cold iteration=1 elapsed_ns=" + coldNs);

            for (int i = 1; i <= warmupIterations; i++) {
                started = System.nanoTime();
                String actual = value(session.invokeTopLevel("run"));
                long elapsed = System.nanoTime() - started;

                requireSame(expected, actual);

                System.out.println(
                        "sample phase=warmup iteration="
                                + i
                                + " elapsed_ns="
                                + elapsed);
            }

            for (int i = 1; i <= steadyIterations; i++) {
                started = System.nanoTime();
                String actual = value(session.invokeTopLevel("run"));
                long elapsed = System.nanoTime() - started;

                requireSame(expected, actual);

                System.out.println(
                        "sample phase=steady iteration="
                                + i
                                + " elapsed_ns="
                                + elapsed);
            }

            System.out.println("result=" + expected);
        }
    }

    private static String value(ProtosExecutionOutcome outcome) {
        if (outcome.state() != ProtosExecutionOutcome.State.COMPLETED) {
            throw new IllegalStateException(
                    "benchmark invocation did not complete: "
                            + outcome.state());
        }

        if (!(outcome.value() instanceof ProtosIntegerValue integer)) {
            throw new IllegalStateException(
                    "benchmark result is not an Integer: "
                            + outcome.value());
        }

        return integer.value().toString();
    }

    private static void requireSame(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "benchmark result drift: expected "
                            + expected
                            + ", got "
                            + actual);
        }
    }
}
