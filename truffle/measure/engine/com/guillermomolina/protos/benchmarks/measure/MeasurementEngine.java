/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure;

import java.nio.file.Path;

/**
 * Revision-independent timing engine shared by every measurement surface.
 *
 * <p>This class depends only on the JDK. Each surface adapter is compiled
 * together with it against the exact classpath of the runtime being measured,
 * performs its own setup before timing, and hands the engine one minimal
 * {@link Invocation} that performs exactly the surface-specific call and
 * returns its normalized observable result. Every timed call is checked
 * against the first observed result; the orchestrator then checks that result
 * against the workload's documented expected value.
 *
 * <p>Output is line-oriented and compatible with the generic JVM matrix parser:
 * {@code setup_ns}, {@code sample phase=<cold|warmup|steady> ...} and
 * {@code result=}.
 *
 * <p>When a JFR destination is given, a recording is started immediately
 * before the first steady iteration and stopped immediately after the last
 * one, so the recording boundary is the steady-state phase boundary itself.
 * The JFR API is only loaded in that case.
 */
public final class MeasurementEngine {
    private MeasurementEngine() {}

    @FunctionalInterface
    public interface Invocation {
        String invoke() throws Exception;
    }

    public enum Mode {
        CORRECTNESS,
        MEASURE
    }

    public record Arguments(
            Mode mode,
            Path coreRoot,
            Path source,
            int warmupIterations,
            int steadyIterations,
            int sampleCalls,
            Path jfrDestination) {

        /**
         * {@code correctness <core-root|-> <source>} or
         * {@code measure <core-root|-> <source> <warmup> <steady>
         * <sample-calls> <jfr-destination|->}.
         */
        public static Arguments parse(String[] args) {
            if (args.length == 3 && "correctness".equals(args[0])) {
                return new Arguments(
                        Mode.CORRECTNESS,
                        optionalPath(args[1]),
                        Path.of(args[2]).toAbsolutePath().normalize(),
                        0,
                        0,
                        1,
                        null);
            }

            if (args.length == 7 && "measure".equals(args[0])) {
                return new Arguments(
                        Mode.MEASURE,
                        optionalPath(args[1]),
                        Path.of(args[2]).toAbsolutePath().normalize(),
                        nonNegativeInt(args[3], "warmup"),
                        positiveInt(args[4], "steady"),
                        positiveInt(args[5], "sample-calls"),
                        optionalPath(args[6]));
            }

            throw new IllegalArgumentException(
                    "usage: correctness <core-root|-> <source>\n"
                            + "   or: measure <core-root|-> <source> <warmup> "
                            + "<steady> <sample-calls> <jfr-destination|->");
        }

        public Path requireCoreRoot() {
            if (coreRoot == null) {
                throw new IllegalArgumentException("core root is required");
            }
            return coreRoot;
        }
    }

    /**
     * Runs the selected mode. Surface setup (session opening, preparation,
     * executable acquisition) must already be complete and is reported as
     * {@code setupNs}; nothing in this method performs setup.
     */
    public static void run(
            String surface,
            String language,
            Arguments arguments,
            long setupNs,
            Invocation invocation) throws Exception {
        if (arguments.mode() == Mode.CORRECTNESS) {
            System.out.println("surface=" + surface);
            System.out.println("language=" + language);
            System.out.println("result=" + invocation.invoke());
            return;
        }

        System.out.println("mode=jvm");
        System.out.println("surface=" + surface);
        System.out.println("language=" + language);
        System.out.println("run_mode=" + surface);
        System.out.println("source=" + arguments.source());
        System.out.println("warmup_iterations=" + arguments.warmupIterations());
        System.out.println("steady_iterations=" + arguments.steadyIterations());
        System.out.println("sample_calls=" + arguments.sampleCalls());
        System.out.println("setup_ns=" + setupNs);

        long started = System.nanoTime();
        String expected = invocation.invoke();
        long elapsed = System.nanoTime() - started;
        sample("cold", 1, elapsed);

        for (int i = 1; i <= arguments.warmupIterations(); i++) {
            started = System.nanoTime();
            invokeRepeated(invocation, expected, arguments.sampleCalls());
            elapsed = System.nanoTime() - started;
            sample("warmup", i, elapsed);
        }

        SteadyRecording recording =
                arguments.jfrDestination() == null
                        ? null
                        : SteadyRecording.start();

        for (int i = 1; i <= arguments.steadyIterations(); i++) {
            started = System.nanoTime();
            invokeRepeated(invocation, expected, arguments.sampleCalls());
            elapsed = System.nanoTime() - started;
            sample("steady", i, elapsed);
        }

        if (recording != null) {
            recording.stopAndDump(arguments.jfrDestination());
            System.out.println("jfr_scope=steady");
            System.out.println("jfr_file=" + arguments.jfrDestination());
        }

        System.out.println("result=" + expected);
    }

    private static void invokeRepeated(
            Invocation invocation,
            String expected,
            int count) throws Exception {
        for (int i = 0; i < count; i++) {
            String actual = invocation.invoke();
            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                        "benchmark result drift: expected "
                                + expected
                                + ", got "
                                + actual);
            }
        }
    }

    private static void sample(String phase, int iteration, long elapsedNs) {
        System.out.println(
                "sample phase="
                        + phase
                        + " iteration="
                        + iteration
                        + " elapsed_ns="
                        + elapsedNs);
    }

    private static Path optionalPath(String value) {
        if ("-".equals(value)) {
            return null;
        }
        return Path.of(value).toAbsolutePath().normalize();
    }

    private static int positiveInt(String value, String name) {
        int parsed = Integer.parseInt(value);
        if (parsed <= 0) {
            throw new IllegalArgumentException(name + " must be > 0");
        }
        return parsed;
    }

    private static int nonNegativeInt(String value, String name) {
        int parsed = Integer.parseInt(value);
        if (parsed < 0) {
            throw new IllegalArgumentException(name + " must be >= 0");
        }
        return parsed;
    }

    /** Isolated so jdk.jfr is loaded only for profiling runs. */
    private static final class SteadyRecording {
        private final jdk.jfr.Recording recording;

        private SteadyRecording(jdk.jfr.Recording recording) {
            this.recording = recording;
        }

        static SteadyRecording start() throws Exception {
            jdk.jfr.Recording recording =
                    new jdk.jfr.Recording(
                            jdk.jfr.Configuration.getConfiguration("profile"));
            recording.setName("protos-benchmarks-steady");
            recording.start();
            System.out.println("jfr_boundary=steady-start");
            return new SteadyRecording(recording);
        }

        void stopAndDump(Path destination) throws Exception {
            recording.stop();
            System.out.println("jfr_boundary=steady-stop");
            recording.dump(destination);
            recording.close();
        }
    }
}
