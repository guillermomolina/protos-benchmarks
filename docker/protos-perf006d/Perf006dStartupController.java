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

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * PERF006-D2 fresh-JVM startup controller.
 *
 * <p>The Docker container running this controller is already created and started before timing.
 * Each sample launches one fresh JVM that executes Perf006dPersistentDriver with zero warmup and
 * exactly one semantic source execution. The outer interval therefore includes fresh JVM startup,
 * Protos Core/Process/Context bootstrap, one canonical source execution and child serialization,
 * while Docker container creation/start and parent-side JSON parsing remain outside the interval.
 */
public final class Perf006dStartupController {
    private static final Pattern EXPECTED_PATTERN =
            Pattern.compile("\\\"expected\\\":\\\"([^\\\"]+)\\\"");
    private static final Pattern RUNTIME_PATTERN =
            Pattern.compile("\\\"runtime\\\":\\\"([^\\\"]+)\\\"");
    private static final Pattern STEADY_PATTERN =
            Pattern.compile("\\\"steady_ns\\\":\\[(\\d+)\\]");

    private Perf006dStartupController() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 6) {
            System.err.println(
                    "usage: Perf006dStartupController <runtime-dir> <expected-runtime> "
                            + "<source> <expected-integer> <samples> <child-timeout-seconds>");
            System.exit(2);
        }

        String runtimeDir = args[0];
        String expectedRuntime = args[1];
        Path source = Path.of(args[2]).toAbsolutePath().normalize();
        String expected = args[3];
        int samples = parsePositiveCount(args[4], "samples");
        long timeoutSeconds = parsePositiveCount(args[5], "child-timeout-seconds");

        if (!runtimeDir.startsWith("/opt/")) {
            throw new IllegalArgumentException("runtime-dir must be an image path");
        }
        if (!Files.isRegularFile(source)) {
            throw new IllegalArgumentException("benchmark source does not exist: " + source);
        }

        ArrayList<Long> startupNs = new ArrayList<>(samples);
        for (int index = 0; index < samples; index++) {
            int display = index + 1;
            System.err.printf("STARTUP_SAMPLE_BEGIN index=%d/%d%n", display, samples);
            System.err.flush();

            Path stdout = Files.createTempFile("perf006d-startup-", ".stdout");
            Path stderr = Files.createTempFile("perf006d-startup-", ".stderr");
            Process child = null;
            try {
                ProcessBuilder builder =
                        new ProcessBuilder(
                                "java",
                                "-Xss128m",
                                "--enable-native-access=ALL-UNNAMED",
                                "-cp",
                                "/opt/perf006d/timing:/opt/protos/lib/protos.jar:"
                                        + runtimeDir
                                        + "/*",
                                "Perf006dPersistentDriver",
                                source.toString(),
                                expected,
                                "0",
                                "1");
                builder.redirectOutput(stdout.toFile());
                builder.redirectError(stderr.toFile());

                long started = System.nanoTime();
                child = builder.start();
                boolean exited = child.waitFor(timeoutSeconds, TimeUnit.SECONDS);
                long elapsed = System.nanoTime() - started;

                if (!exited) {
                    terminate(child);
                    throw new IllegalStateException(
                            "fresh JVM timed out at sample "
                                    + display
                                    + "/"
                                    + samples
                                    + diagnostic(stdout, stderr));
                }
                if (child.exitValue() != 0) {
                    throw new IllegalStateException(
                            "fresh JVM failed exit="
                                    + child.exitValue()
                                    + " sample="
                                    + display
                                    + "/"
                                    + samples
                                    + diagnostic(stdout, stderr));
                }

                validateChildPayload(
                        Files.readString(stdout, StandardCharsets.UTF_8),
                        expected,
                        expectedRuntime,
                        display);
                if (elapsed <= 0) {
                    throw new IllegalStateException("non-positive startup timing sample");
                }
                startupNs.add(elapsed);
                System.err.printf(
                        "STARTUP_SAMPLE_PASS index=%d/%d elapsed_ns=%d%n",
                        display, samples, elapsed);
                System.err.flush();
            } finally {
                if (child != null && child.isAlive()) {
                    terminate(child);
                }
                Files.deleteIfExists(stdout);
                Files.deleteIfExists(stderr);
            }
        }

        emitJson(expected, expectedRuntime, timeoutSeconds, startupNs);
    }

    private static void validateChildPayload(
            String text, String expected, String expectedRuntime, int sample) {
        String line = lastNonemptyLine(text);

        Matcher expectedMatcher = EXPECTED_PATTERN.matcher(line);
        if (!expectedMatcher.find() || !expected.equals(expectedMatcher.group(1))) {
            throw new IllegalStateException(
                    "fresh JVM result identity mismatch at sample " + sample + ": " + line);
        }

        Matcher runtimeMatcher = RUNTIME_PATTERN.matcher(line);
        if (!runtimeMatcher.find() || !expectedRuntime.equals(runtimeMatcher.group(1))) {
            throw new IllegalStateException(
                    "fresh JVM runtime identity mismatch at sample " + sample + ": " + line);
        }

        if (!line.contains("\"warmup_ns\":[]")) {
            throw new IllegalStateException(
                    "fresh JVM unexpectedly performed warmup at sample " + sample);
        }

        Matcher steadyMatcher = STEADY_PATTERN.matcher(line);
        if (!steadyMatcher.find() || Long.parseLong(steadyMatcher.group(1)) <= 0) {
            throw new IllegalStateException(
                    "fresh JVM did not report exactly one positive execution at sample "
                            + sample
                            + ": "
                            + line);
        }

        for (String required :
                List.of(
                        "\"source_reused\":true",
                        "\"process_reused\":true",
                        "\"context_reused\":true",
                        "\"fresh_activation_per_iteration\":true")) {
            if (!line.contains(required)) {
                throw new IllegalStateException(
                        "fresh JVM hosting contract failed at sample "
                                + sample
                                + ": missing "
                                + required);
            }
        }
    }

    private static void terminate(Process child) throws InterruptedException {
        child.destroy();
        if (!child.waitFor(2, TimeUnit.SECONDS)) {
            child.destroyForcibly();
            child.waitFor(5, TimeUnit.SECONDS);
        }
    }

    private static String diagnostic(Path stdout, Path stderr) {
        return " stdout=" + quoted(readBounded(stdout)) + " stderr=" + quoted(readBounded(stderr));
    }

    private static String readBounded(Path path) {
        try {
            String text = Files.readString(path, StandardCharsets.UTF_8);
            int limit = 8192;
            return text.length() <= limit ? text : text.substring(text.length() - limit);
        } catch (IOException failure) {
            return "<unreadable:" + failure.getClass().getSimpleName() + ">";
        }
    }

    private static String quoted(String value) {
        return "\""
                + value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
                + "\"";
    }

    private static String lastNonemptyLine(String text) {
        String[] lines = text.split("\\R");
        for (int index = lines.length - 1; index >= 0; index--) {
            String line = lines[index].trim();
            if (!line.isEmpty()) return line;
        }
        return "";
    }

    private static int parsePositiveCount(String text, String name) {
        int value = Integer.parseInt(text);
        if (value <= 0 || value > 100000) {
            throw new IllegalArgumentException(name + " out of range: " + value);
        }
        return value;
    }

    private static void emitJson(
            String expected, String runtime, long timeoutSeconds, List<Long> startupNs) {
        StringBuilder out = new StringBuilder();
        out.append('{');
        out.append("\"schema_version\":1,");
        out.append("\"expected\":\"").append(expected).append("\",");
        out.append("\"runtime\":\"").append(runtime).append("\",");
        out.append("\"fresh_jvm_per_sample\":true,");
        out.append("\"docker_start_outside_timing\":true,");
        out.append("\"child_timeout_seconds\":").append(timeoutSeconds).append(',');
        out.append("\"startup_ns\":[");
        for (int index = 0; index < startupNs.size(); index++) {
            if (index != 0) out.append(',');
            out.append(startupNs.get(index));
        }
        out.append("]}");
        System.out.println(out);
    }
}
