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
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import jdk.jfr.EventType;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedMethod;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

/** Streaming PERF006-D3 JFR structural analyzer. */
public final class Perf006d3JfrAnalyzer {
    private static final String EXECUTION_SAMPLE = "jdk.ExecutionSample";
    private static final String DEOPT = "jdk.Deoptimization";
    private static final String TRUFFLE_DEOPT = "jdk.graal.compiler.truffle.Deoptimization";
    private static final String HISTORICAL_SYMBOL = "java.util.HashMap$KeyIterator.next";

    private Perf006d3JfrAnalyzer() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: Perf006d3JfrAnalyzer <input.jfr> <output.json>");
            System.exit(2);
        }
        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(input)) {
            throw new IllegalArgumentException("JFR input does not exist: " + input);
        }

        Set<String> availableTypes = new HashSet<>();
        try (RecordingFile metadata = new RecordingFile(input)) {
            for (EventType type : metadata.readEventTypes()) {
                availableTypes.add(type.getName());
            }
        }

        long executionSamples = 0;
        long deoptimizations = 0;
        long truffleDeoptimizations = 0;
        Map<String, Long> threadSamples = new HashMap<>();
        Map<String, Long> topFrames = new HashMap<>();
        Map<String, Long> deoptReasons = new HashMap<>();
        Map<String, Long> deoptActions = new HashMap<>();
        Map<String, Long> deoptMethods = new HashMap<>();

        try (RecordingFile recording = new RecordingFile(input)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();
                switch (type) {
                    case EXECUTION_SAMPLE -> {
                        executionSamples++;
                        String thread = sampledThreadName(event);
                        threadSamples.merge(thread, 1L, Long::sum);
                        String frame = topFrameSymbol(event);
                        topFrames.merge(frame, 1L, Long::sum);
                    }
                    case DEOPT -> {
                        deoptimizations++;
                        deoptReasons.merge(stringField(event, "reason"), 1L, Long::sum);
                        deoptActions.merge(stringField(event, "action"), 1L, Long::sum);
                        deoptMethods.merge(methodField(event, "method"), 1L, Long::sum);
                    }
                    case TRUFFLE_DEOPT -> truffleDeoptimizations++;
                    default -> {
                        // D3 only aggregates events required by the contract.
                    }
                }
            }
        }

        StringBuilder json = new StringBuilder(32768);
        json.append("{\n");
        json.append("  \"schema_version\": 1,\n");
        json.append("  \"recording\": ").append(quote(input.getFileName().toString())).append(",\n");
        json.append("  \"event_type_available\": {\n");
        json.append("    \"jdk.ExecutionSample\": ").append(availableTypes.contains(EXECUTION_SAMPLE)).append(",\n");
        json.append("    \"jdk.Deoptimization\": ").append(availableTypes.contains(DEOPT)).append(",\n");
        json.append("    \"jdk.graal.compiler.truffle.Deoptimization\": ")
                .append(availableTypes.contains(TRUFFLE_DEOPT)).append("\n");
        json.append("  },\n");
        json.append("  \"execution_samples\": {\n");
        json.append("    \"total\": ").append(executionSamples).append(",\n");
        json.append("    \"threads\": ");
        appendRanked(json, threadSamples, executionSamples, 50);
        json.append(",\n");
        json.append("    \"top_frames\": ");
        appendRanked(json, topFrames, executionSamples, 100);
        json.append(",\n");
        long historicalCount = topFrames.getOrDefault(HISTORICAL_SYMBOL, 0L);
        json.append("    \"historical_hashmap_keyiterator_next\": {\"count\": ")
                .append(historicalCount)
                .append(", \"percent\": ")
                .append(percent(historicalCount, executionSamples))
                .append("}\n");
        json.append("  },\n");
        json.append("  \"deoptimizations\": {\n");
        json.append("    \"jdk_total\": ").append(deoptimizations).append(",\n");
        json.append("    \"truffle_total\": ").append(truffleDeoptimizations).append(",\n");
        json.append("    \"jdk_reasons\": ");
        appendRanked(json, deoptReasons, deoptimizations, 50);
        json.append(",\n");
        json.append("    \"jdk_actions\": ");
        appendRanked(json, deoptActions, deoptimizations, 50);
        json.append(",\n");
        json.append("    \"jdk_methods\": ");
        appendRanked(json, deoptMethods, deoptimizations, 50);
        json.append("\n");
        json.append("  }\n");
        json.append("}\n");

        Files.createDirectories(output.getParent());
        Files.writeString(output, json.toString(), StandardCharsets.UTF_8);

        System.out.println("PERF006D3_JFR_ANALYZER=PASS");
        System.out.println("PERF006D3_EXECUTION_SAMPLES=" + executionSamples);
        System.out.println("PERF006D3_JDK_DEOPTIMIZATIONS=" + deoptimizations);
        System.out.println("PERF006D3_TRUFFLE_DEOPTIMIZATIONS=" + truffleDeoptimizations);
        System.out.println("PERF006D3_HISTORICAL_HASHMAP_SAMPLES=" + historicalCount);
    }

    private static String sampledThreadName(RecordedEvent event) {
        RecordedThread thread = null;
        if (hasField(event, "sampledThread")) {
            Object value = event.getValue("sampledThread");
            if (value instanceof RecordedThread recorded) {
                thread = recorded;
            }
        }
        if (thread == null) {
            thread = event.getThread();
        }
        if (thread == null) {
            return "<unknown>";
        }
        String javaName = thread.getJavaName();
        return javaName == null ? "<unnamed>" : javaName;
    }

    private static String topFrameSymbol(RecordedEvent event) {
        RecordedStackTrace stack = event.getStackTrace();
        if (stack == null || stack.getFrames().isEmpty()) {
            return "<no-stack>";
        }
        RecordedFrame frame = stack.getFrames().get(0);
        RecordedMethod method = frame.getMethod();
        if (method == null) {
            return "<no-method>";
        }
        String type = method.getType() == null ? "<no-type>" : method.getType().getName();
        return type + "." + method.getName();
    }

    private static String methodField(RecordedEvent event, String name) {
        if (!hasField(event, name)) return "<absent>";
        Object value = event.getValue(name);
        if (value instanceof RecordedMethod method) {
            String type = method.getType() == null ? "<no-type>" : method.getType().getName();
            return type + "." + method.getName();
        }
        return value == null ? "<null>" : value.toString();
    }

    private static String stringField(RecordedEvent event, String name) {
        if (!hasField(event, name)) return "<absent>";
        Object value = event.getValue(name);
        return value == null ? "<null>" : value.toString();
    }

    private static boolean hasField(RecordedEvent event, String name) {
        for (ValueDescriptor field : event.getFields()) {
            if (field.getName().equals(name)) {
                return true;
            }
        }
        return false;
    }

    private static void appendRanked(
            StringBuilder out, Map<String, Long> values, long total, int limit) {
        List<Map.Entry<String, Long>> entries = new ArrayList<>(values.entrySet());
        entries.sort(
                Comparator.<Map.Entry<String, Long>>comparingLong(Map.Entry::getValue)
                        .reversed()
                        .thenComparing(Map.Entry::getKey));
        out.append("[");
        int count = Math.min(limit, entries.size());
        for (int index = 0; index < count; index++) {
            if (index != 0) out.append(",");
            Map.Entry<String, Long> entry = entries.get(index);
            out.append("\n      {\"name\": ")
                    .append(quote(entry.getKey()))
                    .append(", \"count\": ")
                    .append(entry.getValue())
                    .append(", \"percent\": ")
                    .append(percent(entry.getValue(), total))
                    .append("}");
        }
        if (count != 0) out.append("\n    ");
        out.append("]");
    }

    private static String percent(long value, long total) {
        if (total <= 0) return "0.0";
        return String.format(java.util.Locale.ROOT, "%.6f", value * 100.0 / total);
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder(value.length() + 16);
        out.append('"');
        for (int index = 0; index < value.length(); index++) {
            char ch = value.charAt(index);
            switch (ch) {
                case '\\' -> out.append("\\\\");
                case '"' -> out.append("\\\"");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        out.append(String.format(java.util.Locale.ROOT, "\\u%04x", (int) ch));
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        out.append('"');
        return out.toString();
    }
}
