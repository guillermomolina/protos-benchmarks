/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.truffle;

import com.guillermomolina.protos.execution.ProtosExecutionOutcome;
import com.guillermomolina.protos.execution.ProtosStandaloneHostedSession;
import com.guillermomolina.protos.runtime.ProtosIntegerValue;

import java.nio.file.Files;
import java.nio.file.Path;

import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Source;
import org.graalvm.polyglot.Value;

public final class TruffleJvmRunner {
    private static final Path PROTOS_CORE =
            Path.of("/workspaces/protos/protos/lib/core");

    private TruffleJvmRunner() {
    }

    @FunctionalInterface
    private interface Invocation {
        String invoke() throws Exception;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            throw new IllegalArgumentException(
                    "usage: TruffleJvmRunner correctness <protos|js|python> <source>\n"
                    + "   or: TruffleJvmRunner measure <protos|js|python> <source> "
                    + "<warmup-iterations> <steady-iterations>");
        }

        String command = args[0];
        String language = args[1];
        Path sourcePath = Path.of(args[2]).toAbsolutePath();

        switch (command) {
            case "correctness" -> {
                if (args.length != 3) {
                    throw new IllegalArgumentException(
                            "correctness requires exactly <language> <source>");
                }
                System.out.println(runCorrectness(language, sourcePath));
            }
            case "measure" -> {
                if (args.length != 5) {
                    throw new IllegalArgumentException(
                            "measure requires <language> <source> "
                            + "<warmup-iterations> <steady-iterations>");
                }

                int warmupIterations = positiveInt(args[3], "warmup-iterations");
                int steadyIterations = positiveInt(args[4], "steady-iterations");

                runMeasurement(
                        language,
                        sourcePath,
                        warmupIterations,
                        steadyIterations);
            }
            default -> throw new IllegalArgumentException(
                    "unsupported command: " + command);
        }
    }

    private static String runCorrectness(
            String language,
            Path sourcePath) throws Exception {
        if ("protos".equals(language)) {
            try (ProtosStandaloneHostedSession session =
                    ProtosStandaloneHostedSession.open(PROTOS_CORE, sourcePath)) {
                return normalize(session.invokeTopLevel("run"));
            }
        }

        String sourceText = Files.readString(sourcePath);
        Source source = source(language, sourceText, sourcePath);

        try (Context context = newContext(language)) {
            context.eval(source);
            Value run = executableRun(context, language);
            return normalize(run.execute());
        }
    }

    private static void runMeasurement(
            String language,
            Path sourcePath,
            int warmupIterations,
            int steadyIterations) throws Exception {

        System.out.println("mode=jvm");
        System.out.println("language=" + language);
        System.out.println("source=" + sourcePath);
        System.out.println("warmup_iterations=" + warmupIterations);
        System.out.println("steady_iterations=" + steadyIterations);

        if ("protos".equals(language)) {
            long setupStart = System.nanoTime();

            try (ProtosStandaloneHostedSession session =
                    ProtosStandaloneHostedSession.open(PROTOS_CORE, sourcePath)) {

                long setupNanos = System.nanoTime() - setupStart;
                System.out.println("setup_ns=" + setupNanos);

                Invocation invocation =
                        () -> normalize(session.invokeTopLevel("run"));

                measureInvocations(
                        invocation,
                        warmupIterations,
                        steadyIterations);
            }
            return;
        }

        String sourceText = Files.readString(sourcePath);
        Source source = source(language, sourceText, sourcePath);

        long setupStart = System.nanoTime();

        try (Context context = newContext(language)) {
            context.eval(source);
            Value run = executableRun(context, language);

            long setupNanos = System.nanoTime() - setupStart;
            System.out.println("setup_ns=" + setupNanos);

            Invocation invocation = () -> normalize(run.execute());

            measureInvocations(
                    invocation,
                    warmupIterations,
                    steadyIterations);
        }
    }

    private static void measureInvocations(
            Invocation invocation,
            int warmupIterations,
            int steadyIterations) throws Exception {

        long start = System.nanoTime();
        String expected = invocation.invoke();
        long elapsed = System.nanoTime() - start;

        printSample("cold", 1, elapsed);

        for (int i = 1; i <= warmupIterations; i++) {
            start = System.nanoTime();
            String result = invocation.invoke();
            elapsed = System.nanoTime() - start;

            requireSameResult(expected, result);
            printSample("warmup", i, elapsed);
        }

        for (int i = 1; i <= steadyIterations; i++) {
            start = System.nanoTime();
            String result = invocation.invoke();
            elapsed = System.nanoTime() - start;

            requireSameResult(expected, result);
            printSample("steady", i, elapsed);
        }

        System.out.println("result=" + expected);
    }

    private static void printSample(
            String phase,
            int iteration,
            long elapsedNanos) {
        System.out.println(
                "sample phase=" + phase
                + " iteration=" + iteration
                + " elapsed_ns=" + elapsedNanos);
    }

    private static void requireSameResult(
            String expected,
            String actual) {
        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "result changed during measurement: expected "
                    + expected + " but got " + actual);
        }
    }

    private static Source source(
            String language,
            String sourceText,
            Path sourcePath) throws Exception {
        return switch (language) {
            case "js" ->
                    Source.newBuilder("js", sourceText, sourcePath.toString())
                            .build();
            case "python" ->
                    Source.newBuilder("python", sourceText, sourcePath.toString())
                            .build();
            default -> throw new IllegalArgumentException(
                    "unsupported language: " + language);
        };
    }

    private static Context newContext(String language) {
        return Context.newBuilder(language)
                .allowExperimentalOptions(true)
                .build();
    }

    private static Value executableRun(
            Context context,
            String language) {
        Value run = context.getBindings(language).getMember("truffleRun");

        if (run == null || !run.canExecute()) {
            throw new IllegalStateException(
                    "workload does not expose executable truffleRun");
        }

        return run;
    }

    private static String normalize(ProtosExecutionOutcome outcome) {
        if (outcome.value() instanceof ProtosIntegerValue integerValue) {
            return integerValue.value().toString();
        }

        return String.valueOf(outcome.value());
    }

    private static String normalize(Value value) {
        if (value.fitsInBigInteger()) {
            return value.asBigInteger().toString();
        }

        return value.toString();
    }

    private static int positiveInt(
            String value,
            String name) {
        int parsed = Integer.parseInt(value);

        if (parsed <= 0) {
            throw new IllegalArgumentException(name + " must be > 0");
        }

        return parsed;
    }
}
