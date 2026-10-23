/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure;

import java.io.IOException;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

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

        if (Boolean.getBoolean("protos.benchmarks.measure.diagnostic")) {
            if (arguments.jfrDestination() != null) {
                throw new IllegalArgumentException(
                        "diagnostic capture cannot share the JFR timing run");
            }
            runDiagnostic(arguments, invocation);
            return;
        }

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


    /**
     * Diagnostic-only execution. Never called by ordinary reference timing.
     * Supporting counter reads and output happen outside the wall interval.
     */
    private static void runDiagnostic(
            Arguments arguments, Invocation invocation) throws Exception {
        DiagnosticSampler sampler = new DiagnosticSampler();
        DiagnosticJfr jit = DiagnosticJfr.startIfRequested();

        try {
            DiagnosticSnapshot before = sampler.before();
            DiagnosticSampleEvent event =
                    beginSample(jit, "cold", 1, 1);

            long started = System.nanoTime();
            long cpuStarted = sampler.cpuNow();
            String expected = invocation.invoke();
            long cpuElapsed = sampler.cpuNow() - cpuStarted;
            long elapsed = System.nanoTime() - started;

            endSample(event);
            DiagnosticSnapshot after = sampler.after();

            sample("cold", 1, elapsed);
            sampler.report("cold", 1, before, after, cpuElapsed);

            for (int i = 1; i <= arguments.warmupIterations(); i++) {
                diagnosticRepeated(
                        invocation, expected, arguments.sampleCalls(),
                        "warmup", i, sampler, jit);
            }

            for (int i = 1; i <= arguments.steadyIterations(); i++) {
                diagnosticRepeated(
                        invocation, expected, arguments.sampleCalls(),
                        "steady", i, sampler, jit);
            }

            System.out.println("result=" + expected);
        } finally {
            if (jit != null) {
                jit.finish();
            }
        }
    }

    private static void diagnosticRepeated(
            Invocation invocation,
            String expected,
            int calls,
            String phase,
            int iteration,
            DiagnosticSampler sampler,
            DiagnosticJfr jit) throws Exception {
        DiagnosticSnapshot before = sampler.before();
        DiagnosticSampleEvent event =
                beginSample(jit, phase, iteration, calls);

        long started = System.nanoTime();
        long cpuStarted = sampler.cpuNow();
        invokeRepeated(invocation, expected, calls);
        long cpuElapsed = sampler.cpuNow() - cpuStarted;
        long elapsed = System.nanoTime() - started;

        endSample(event);
        DiagnosticSnapshot after = sampler.after();

        sample(phase, iteration, elapsed);
        sampler.report(phase, iteration, before, after, cpuElapsed);
    }

    private static DiagnosticSampleEvent beginSample(
            DiagnosticJfr jit,
            String phase,
            int iteration,
            int calls) {
        if (jit == null) {
            return null;
        }

        DiagnosticSampleEvent event = new DiagnosticSampleEvent();
        event.phase = phase;
        event.iteration = iteration;
        event.sampleCalls = calls;
        event.begin();
        return event;
    }

    private static void endSample(DiagnosticSampleEvent event) {
        if (event != null) {
            event.end();
            event.commit();
        }
    }

    @jdk.jfr.Name("protos.benchmarks.SampleWindow")
    @jdk.jfr.Label("Protos Benchmark Sample Window")
    @jdk.jfr.StackTrace(false)
    public static final class DiagnosticSampleEvent
            extends jdk.jfr.Event {
        @jdk.jfr.Label("Phase")
        public String phase;

        @jdk.jfr.Label("Iteration")
        public int iteration;

        @jdk.jfr.Label("Sample Calls")
        public int sampleCalls;
    }

    private static final class DiagnosticJfr {
        private final jdk.jfr.Recording recording;
        private final Path destination;

        private DiagnosticJfr(
                jdk.jfr.Recording recording,
                Path destination) {
            this.recording = recording;
            this.destination = destination;
        }

        static DiagnosticJfr startIfRequested() throws Exception {
            String value = System.getProperty(
                    "protos.benchmarks.measure.jitJfr");

            if (value == null) {
                return null;
            }

            if (value.isBlank()) {
                throw new IllegalArgumentException(
                        "JIT JFR destination must not be empty");
            }

            Path destination = Path.of(value)
                    .toAbsolutePath().normalize();

            jdk.jfr.Recording recording =
                    new jdk.jfr.Recording(
                            jdk.jfr.Configuration.getConfiguration(
                                    "profile"));

            recording.setName("protos-benchmarks-jit-diagnostic");

            recording.enable(DiagnosticSampleEvent.class)
                    .withThreshold(java.time.Duration.ZERO)
                    .withoutStackTrace();

            recording.enable("jdk.Compilation")
                    .withThreshold(java.time.Duration.ZERO);

            recording.enable("jdk.Deoptimization");
            recording.enable("jdk.GarbageCollection");

            recording.start();

            System.out.println("diagnostic_jfr_mode=ENABLED");

            return new DiagnosticJfr(recording, destination);
        }

        void finish() throws Exception {
            try {
                recording.stop();
                recording.dump(destination);
            } finally {
                recording.close();
            }

            System.out.println("diagnostic_jfr_scope=all-samples");
        }
    }

    private record DiagnosticSnapshot(
            long voluntary,
            long involuntary,
            long gcCount,
            long gcTimeMs) {}

    private static final class DiagnosticSampler {
        private final ThreadMXBean cpu =
                ManagementFactory.getThreadMXBean();

        private final List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        DiagnosticSampler() {
            if (!cpu.isCurrentThreadCpuTimeSupported()) {
                throw new IllegalStateException(
                        "current-thread CPU timing is unsupported");
            }
            if (!cpu.isThreadCpuTimeEnabled()) {
                cpu.setThreadCpuTimeEnabled(true);
            }

            System.out.println("diagnostic_mode=ENABLED");
            System.out.println(
                    "diagnostic_thread_id="
                            + Thread.currentThread().threadId());
        }

        DiagnosticSnapshot before() {
            long[] switches = readSwitches();
            long[] gc = readGc();
            return new DiagnosticSnapshot(
                    switches[0], switches[1], gc[0], gc[1]);
        }

        DiagnosticSnapshot after() {
            return before();
        }

        long cpuNow() {
            return cpu.getCurrentThreadCpuTime();
        }

        void report(
                String phase,
                int iteration,
                DiagnosticSnapshot before,
                DiagnosticSnapshot after,
                long cpuElapsedNs) {
            System.out.println(
                    "thread_cpu phase=" + phase
                            + " iteration=" + iteration
                            + " elapsed_ns=" + cpuElapsedNs);

            if (before.voluntary >= 0 && after.voluntary >= 0
                    && before.involuntary >= 0 && after.involuntary >= 0) {
                System.out.println(
                        "ctx_switch phase=" + phase
                                + " iteration=" + iteration
                                + " voluntary="
                                + (after.voluntary - before.voluntary)
                                + " nonvoluntary="
                                + (after.involuntary - before.involuntary));
            }

            if (before.gcCount >= 0 && after.gcCount >= 0
                    && before.gcTimeMs >= 0 && after.gcTimeMs >= 0) {
                System.out.println(
                        "gc_sample phase=" + phase
                                + " iteration=" + iteration
                                + " count_delta="
                                + (after.gcCount - before.gcCount)
                                + " time_ms_delta="
                                + (after.gcTimeMs - before.gcTimeMs));
            }
        }

        private long[] readGc() {
            long count = 0;
            long millis = 0;

            for (GarbageCollectorMXBean collector : collectors) {
                long c = collector.getCollectionCount();
                long t = collector.getCollectionTime();

                if (c < 0 || t < 0) {
                    return new long[] {-1, -1};
                }

                count += c;
                millis += t;
            }

            return new long[] {count, millis};
        }

        private static long[] readSwitches() {
            Path status = Path.of("/proc/thread-self/status");

            if (!Files.isReadable(status)) {
                return new long[] {-1, -1};
            }

            long voluntary = -1;
            long involuntary = -1;

            try {
                for (String line : Files.readAllLines(status)) {
                    if (line.startsWith("voluntary_ctxt_switches:")) {
                        voluntary = parseCounter(line);
                    } else if (line.startsWith(
                            "nonvoluntary_ctxt_switches:")) {
                        involuntary = parseCounter(line);
                    }
                }
            } catch (IOException | NumberFormatException e) {
                return new long[] {-1, -1};
            }

            return new long[] {voluntary, involuntary};
        }

        private static long parseCounter(String line) {
            return Long.parseLong(
                    line.substring(line.indexOf(':') + 1).trim());
        }
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
