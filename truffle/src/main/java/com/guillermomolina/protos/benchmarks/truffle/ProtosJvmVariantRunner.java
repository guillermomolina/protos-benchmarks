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

/**
 * Exact-revision Protos runner using the dynamic top-level API.
 *
 * <p>This class is compiled against the common pinned Protos artifact, which
 * predates the prepared top-level API, so it must not reference that API. The
 * prepared runner lives in a separate source root and reuses {@link #measure}
 * so both run modes share one timed loop and one correctness check.
 */
public final class ProtosJvmVariantRunner {
    private ProtosJvmVariantRunner() {}

    @FunctionalInterface
    public interface Invocation {
        ProtosExecutionOutcome invoke() throws Exception;
    }

    public record Arguments(
            Path coreRoot,
            Path source,
            int warmupIterations,
            int steadyIterations,
            int sampleCalls) {

        public static Arguments parse(String[] args) {
            if (args.length != 4 && args.length != 5) {
                throw new IllegalArgumentException(
                        "usage: <core-root> <source> <warmup> <steady> "
                                + "[sample-calls]");
            }

            return new Arguments(
                    Path.of(args[0]).toAbsolutePath().normalize(),
                    Path.of(args[1]).toAbsolutePath().normalize(),
                    Integer.parseInt(args[2]),
                    Integer.parseInt(args[3]),
                    args.length == 5 ? positiveInt(args[4]) : 1);
        }
    }

    public static void main(String[] args) throws Exception {
        Arguments arguments = Arguments.parse(args);

        long setupStart = System.nanoTime();

        try (ProtosStandaloneHostedSession session = openSession(arguments)) {
            long setupNs = System.nanoTime() - setupStart;

            measure(
                    "dynamic",
                    arguments,
                    setupNs,
                    () -> session.invokeTopLevel("run"));
        }
    }

    public static ProtosStandaloneHostedSession openSession(
            Arguments arguments) throws Exception {
        ProtosStandaloneHostedSession session =
                ProtosStandaloneHostedSession.open(
                        arguments.coreRoot(),
                        arguments.source());

        ProtosExecutionOutcome initial = session.initialOutcome();

        if (initial.state() != ProtosExecutionOutcome.State.COMPLETED) {
            session.close();
            throw new IllegalStateException(
                    "initial source execution did not complete: "
                            + initial.state());
        }

        return session;
    }

    /**
     * Times the cold call, then warmup and steady samples of
     * {@code sampleCalls} invocations each. Session opening and any
     * preparation happen before this method is entered.
     */
    public static void measure(
            String runMode,
            Arguments arguments,
            long setupNs,
            Invocation invocation) throws Exception {
        long started = System.nanoTime();
        String expected = value(invocation.invoke());
        long coldNs = System.nanoTime() - started;

        System.out.println("mode=jvm");
        System.out.println("language=protos");
        System.out.println("run_mode=" + runMode);
        System.out.println("source=" + arguments.source());
        System.out.println(
                "warmup_iterations=" + arguments.warmupIterations());
        System.out.println(
                "steady_iterations=" + arguments.steadyIterations());
        System.out.println("sample_calls=" + arguments.sampleCalls());
        System.out.println("setup_ns=" + setupNs);
        System.out.println(
                "sample phase=cold iteration=1 elapsed_ns=" + coldNs);

        for (int i = 1; i <= arguments.warmupIterations(); i++) {
            started = System.nanoTime();
            invokeRepeated(invocation, expected, arguments.sampleCalls());
            long elapsed = System.nanoTime() - started;

            System.out.println(
                    "sample phase=warmup iteration="
                            + i
                            + " elapsed_ns="
                            + elapsed);
        }

        for (int i = 1; i <= arguments.steadyIterations(); i++) {
            started = System.nanoTime();
            invokeRepeated(invocation, expected, arguments.sampleCalls());
            long elapsed = System.nanoTime() - started;

            System.out.println(
                    "sample phase=steady iteration="
                            + i
                            + " elapsed_ns="
                            + elapsed);
        }

        System.out.println("result=" + expected);
    }

    private static void invokeRepeated(
            Invocation invocation,
            String expected,
            int count) throws Exception {
        for (int i = 0; i < count; i++) {
            requireSame(expected, value(invocation.invoke()));
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

    private static int positiveInt(String value) {
        int parsed = Integer.parseInt(value);

        if (parsed <= 0) {
            throw new IllegalArgumentException(
                    "sample-calls must be positive: " + value);
        }

        return parsed;
    }
}
