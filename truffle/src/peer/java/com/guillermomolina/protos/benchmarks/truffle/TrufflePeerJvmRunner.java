/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.truffle;

import java.nio.file.Files;
import java.nio.file.Path;

import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Source;
import org.graalvm.polyglot.Value;

public final class TrufflePeerJvmRunner {
    private TrufflePeerJvmRunner() {}

    @FunctionalInterface
    private interface Invocation {
        String invoke() throws Exception;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            throw new IllegalArgumentException(
                    "usage: TrufflePeerJvmRunner "
                            + "correctness <js|python> <source>\n"
                            + "   or: TrufflePeerJvmRunner "
                            + "measure <js|python> <source> "
                            + "<warmup> <steady> [sample-calls]");
        }

        String command = args[0];
        String language = args[1];
        Path sourcePath =
                Path.of(args[2]).toAbsolutePath();

        requirePeerLanguage(language);

        switch (command) {
            case "correctness" -> {
                if (args.length != 3) {
                    throw new IllegalArgumentException(
                            "correctness requires "
                                    + "<language> <source>");
                }

                System.out.println(
                        runCorrectness(
                                language,
                                sourcePath));
            }

            case "measure" -> {
                if (
                        args.length != 5
                        && args.length != 6
                ) {
                    throw new IllegalArgumentException(
                            "measure requires "
                                    + "<language> <source> "
                                    + "<warmup> <steady> "
                                    + "[sample-calls]");
                }

                int warmup =
                        nonNegativeInt(
                                args[3],
                                "warmup");

                int steady =
                        positiveInt(
                                args[4],
                                "steady");

                int sampleCalls =
                        args.length == 6
                                ? positiveInt(
                                        args[5],
                                        "sample-calls")
                                : 1;

                runMeasurement(
                        language,
                        sourcePath,
                        warmup,
                        steady,
                        sampleCalls);
            }

            default ->
                    throw new IllegalArgumentException(
                            "unsupported command: "
                                    + command);
        }
    }

    private static String runCorrectness(
            String language,
            Path sourcePath)
            throws Exception {

        String text =
                Files.readString(sourcePath);

        Source source =
                source(
                        language,
                        text,
                        sourcePath);

        try (
                Context context =
                        newContext(language)
        ) {
            context.eval(source);

            Value run =
                    executableRun(
                            context,
                            language);

            return normalize(
                    run.execute());
        }
    }

    private static void runMeasurement(
            String language,
            Path sourcePath,
            int warmup,
            int steady,
            int sampleCalls)
            throws Exception {

        System.out.println("mode=jvm");
        System.out.println(
                "language=" + language);
        System.out.println(
                "run_mode=prepared");
        System.out.println(
                "source=" + sourcePath);
        System.out.println(
                "warmup_iterations="
                        + warmup);
        System.out.println(
                "steady_iterations="
                        + steady);
        System.out.println(
                "sample_calls="
                        + sampleCalls);

        String text =
                Files.readString(sourcePath);

        Source source =
                source(
                        language,
                        text,
                        sourcePath);

        long setupStart =
                System.nanoTime();

        try (
                Context context =
                        newContext(language)
        ) {
            context.eval(source);

            Value run =
                    executableRun(
                            context,
                            language);

            long setupNanos =
                    System.nanoTime()
                            - setupStart;

            System.out.println(
                    "setup_ns="
                            + setupNanos);

            Invocation invocation =
                    () -> normalize(
                            run.execute());

            measureInvocations(
                    invocation,
                    warmup,
                    steady,
                    sampleCalls);
        }
    }

    private static void measureInvocations(
            Invocation invocation,
            int warmup,
            int steady,
            int sampleCalls)
            throws Exception {

        long start =
                System.nanoTime();

        String expected =
                invocation.invoke();

        long elapsed =
                System.nanoTime()
                        - start;

        printSample(
                "cold",
                1,
                elapsed);

        for (
                int i = 1;
                i <= warmup;
                i++
        ) {
            start =
                    System.nanoTime();

            invokeRepeated(
                    invocation,
                    expected,
                    sampleCalls);

            elapsed =
                    System.nanoTime()
                            - start;

            printSample(
                    "warmup",
                    i,
                    elapsed);
        }

        for (
                int i = 1;
                i <= steady;
                i++
        ) {
            start =
                    System.nanoTime();

            invokeRepeated(
                    invocation,
                    expected,
                    sampleCalls);

            elapsed =
                    System.nanoTime()
                            - start;

            printSample(
                    "steady",
                    i,
                    elapsed);
        }

        System.out.println(
                "result=" + expected);
    }

    private static void invokeRepeated(
            Invocation invocation,
            String expected,
            int count)
            throws Exception {

        for (
                int i = 0;
                i < count;
                i++
        ) {
            requireSameResult(
                    expected,
                    invocation.invoke());
        }
    }

    private static void printSample(
            String phase,
            int iteration,
            long elapsedNanos) {

        System.out.println(
                "sample phase="
                        + phase
                        + " iteration="
                        + iteration
                        + " elapsed_ns="
                        + elapsedNanos);
    }

    private static void requireSameResult(
            String expected,
            String actual) {

        if (!expected.equals(actual)) {
            throw new IllegalStateException(
                    "result changed during "
                            + "measurement: expected "
                            + expected
                            + " but got "
                            + actual);
        }
    }

    private static Source source(
            String language,
            String sourceText,
            Path sourcePath)
            throws Exception {

        return switch (language) {
            case "js" ->
                    Source.newBuilder(
                                    "js",
                                    sourceText,
                                    sourcePath.toString())
                            .build();

            case "python" ->
                    Source.newBuilder(
                                    "python",
                                    sourceText,
                                    sourcePath.toString())
                            .build();

            default ->
                    throw new IllegalArgumentException(
                            "unsupported peer language: "
                                    + language);
        };
    }

    private static Context newContext(
            String language) {

        return Context.newBuilder(language)
                .allowExperimentalOptions(true)
                .build();
    }

    private static Value executableRun(
            Context context,
            String language) {

        Value run =
                context
                        .getBindings(language)
                        .getMember("truffleRun");

        if (
                run == null
                || !run.canExecute()
        ) {
            throw new IllegalStateException(
                    "workload does not expose "
                            + "executable truffleRun");
        }

        return run;
    }

    private static String normalize(
            Value value) {

        if (value.fitsInBigInteger()) {
            return value
                    .asBigInteger()
                    .toString();
        }

        return value.toString();
    }

    private static void requirePeerLanguage(
            String language) {

        if (
                !"js".equals(language)
                && !"python".equals(language)
        ) {
            throw new IllegalArgumentException(
                    "unsupported peer language: "
                            + language);
        }
    }

    private static int positiveInt(
            String value,
            String name) {

        int parsed =
                Integer.parseInt(value);

        if (parsed <= 0) {
            throw new IllegalArgumentException(
                    name + " must be > 0");
        }

        return parsed;
    }

    private static int nonNegativeInt(
            String value,
            String name) {

        int parsed =
                Integer.parseInt(value);

        if (parsed < 0) {
            throw new IllegalArgumentException(
                    name + " must be >= 0");
        }

        return parsed;
    }
}
