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
import java.util.LinkedHashMap;
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

/**
 * Streaming PERF006-D3 / PERF008 JFR structural analyzer.
 *
 * <p>Schema version 1 fields (event totals, thread shares, leaf-frame {@code top_frames},
 * deoptimization breakdowns) are computed exactly as before and MUST NOT change value for the
 * same input recording. Schema version 2 adds a bounded full call stack per {@code
 * jdk.ExecutionSample} (see {@link #MAX_STACK_DEPTH}), a ranked {@code call_paths} table, and a
 * {@code continueAt}/{@code Builder} relationship section answering caller/callee/co-occurrence
 * questions that a leaf-only frame count cannot answer.
 */
public final class Perf006d3JfrAnalyzer {
    private static final String EXECUTION_SAMPLE = "jdk.ExecutionSample";
    private static final String DEOPT = "jdk.Deoptimization";
    private static final String TRUFFLE_DEOPT = "jdk.graal.compiler.truffle.Deoptimization";
    private static final String HISTORICAL_SYMBOL = "java.util.HashMap$KeyIterator.next";

    /** Bounded stack depth retained per execution sample (leaf-first). Deliberately finite. */
    private static final int MAX_STACK_DEPTH = 32;

    private static final int CALL_PATHS_LIMIT = 200;
    private static final int CONTINUE_AT_RANKED_LIMIT = 100;

    /**
     * Method-and-declaring-type markers whose ancestor/descendant relationship to {@code
     * CachedBytecodeNode.continueAt} is reported explicitly, rather than assumed from top-frame
     * percentages. Order is preserved verbatim in the output.
     */
    private static final List<String> CONTINUE_AT_MARKERS =
            List.of(
                    "Unsafe.putObject",
                    "FrameExtensionsUnsafe",
                    "ProtosObjectValue.readLocalSlot",
                    "ProtosActivation.lookup",
                    "CallTarget");

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

        Map<String, Long> callPaths = new HashMap<>();
        long continueAtAnyDepth = 0;
        long continueAtLeaf = 0;
        Map<String, Long> continueAtCallers = new HashMap<>();
        Map<String, Long> continueAtCallees = new HashMap<>();
        Map<String, Long> continueAtStacks = new HashMap<>();
        Map<String, long[]> continueAtMarkerStats = new LinkedHashMap<>();
        for (String marker : CONTINUE_AT_MARKERS) {
            continueAtMarkerStats.put(marker, new long[3]);
        }
        long builderAnyDepth = 0;
        long builderLeaf = 0;
        long builderCoOccursWithContinueAt = 0;

        try (RecordingFile recording = new RecordingFile(input)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();
                switch (type) {
                    case EXECUTION_SAMPLE -> {
                        executionSamples++;
                        String thread = sampledThreadName(event);
                        threadSamples.merge(thread, 1L, Long::sum);
                        List<String> stack = boundedStackFrames(event);
                        String frame = stack.isEmpty() ? "<no-stack>" : stack.get(0);
                        topFrames.merge(frame, 1L, Long::sum);

                        String signature = pathSignature(stack);
                        callPaths.merge(signature, 1L, Long::sum);

                        int continueAtIndex = indexOfMatch(stack, Perf006d3JfrAnalyzer::isContinueAtFrame);
                        int builderIndex = indexOfMatch(stack, Perf006d3JfrAnalyzer::isBuilderFrame);

                        if (continueAtIndex >= 0) {
                            continueAtAnyDepth++;
                            if (continueAtIndex == 0) continueAtLeaf++;
                            String caller =
                                    (continueAtIndex + 1 < stack.size())
                                            ? stack.get(continueAtIndex + 1)
                                            : "<root>";
                            String callee = (continueAtIndex > 0) ? stack.get(continueAtIndex - 1) : "<leaf>";
                            continueAtCallers.merge(caller, 1L, Long::sum);
                            continueAtCallees.merge(callee, 1L, Long::sum);
                            continueAtStacks.merge(signature, 1L, Long::sum);
                            for (String marker : CONTINUE_AT_MARKERS) {
                                long[] counts = continueAtMarkerStats.get(marker);
                                boolean any = false;
                                boolean ancestor = false;
                                boolean descendant = false;
                                for (int i = 0; i < stack.size(); i++) {
                                    if (!stack.get(i).contains(marker)) continue;
                                    any = true;
                                    if (i > continueAtIndex) ancestor = true;
                                    else if (i < continueAtIndex) descendant = true;
                                }
                                if (any) counts[0]++;
                                if (ancestor) counts[1]++;
                                if (descendant) counts[2]++;
                            }
                            if (builderIndex >= 0) builderCoOccursWithContinueAt++;
                        }
                        if (builderIndex >= 0) {
                            builderAnyDepth++;
                            if (builderIndex == 0) builderLeaf++;
                        }
                    }
                    case DEOPT -> {
                        deoptimizations++;
                        deoptReasons.merge(stringField(event, "reason"), 1L, Long::sum);
                        deoptActions.merge(stringField(event, "action"), 1L, Long::sum);
                        deoptMethods.merge(methodField(event, "method"), 1L, Long::sum);
                    }
                    case TRUFFLE_DEOPT -> truffleDeoptimizations++;
                    default -> {
                        // D3/PERF008 only aggregate events required by the contract.
                    }
                }
            }
        }

        StringBuilder json = new StringBuilder(65536);
        json.append("{\n");
        json.append("  \"schema_version\": 2,\n");
        json.append("  \"recording\": ").append(quote(input.getFileName().toString())).append(",\n");
        json.append("  \"stack_depth_limit\": ").append(MAX_STACK_DEPTH).append(",\n");
        json.append("  \"stack_semantics\": {\n");
        json.append(
                "    \"frame_order\": \"index 0 is the leaf (currently executing) frame; "
                        + "increasing index moves toward the call-chain root\",\n");
        json.append(
                "    \"multiple_occurrences_policy\": \"when a matched method appears more than "
                        + "once in one bounded stack, caller/callee/marker-position statistics use "
                        + "its shallowest (leaf-closest) occurrence\"\n");
        json.append("  },\n");
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
        json.append("    \"call_paths\": ");
        appendRanked(json, callPaths, executionSamples, CALL_PATHS_LIMIT);
        json.append(",\n");
        long historicalCount = topFrames.getOrDefault(HISTORICAL_SYMBOL, 0L);
        json.append("    \"historical_hashmap_keyiterator_next\": {\"count\": ")
                .append(historicalCount)
                .append(", \"percent\": ")
                .append(percent(historicalCount, executionSamples))
                .append("}\n");
        json.append("  },\n");
        json.append("  \"continue_at\": {\n");
        json.append(
                "    \"matcher\": \"method named 'continueAt' declared on a type whose name "
                        + "contains 'CachedBytecodeNode'\",\n");
        json.append("    \"leaf_count\": ").append(continueAtLeaf).append(",\n");
        json.append("    \"leaf_percent\": ").append(percent(continueAtLeaf, executionSamples)).append(",\n");
        json.append("    \"any_depth_count\": ").append(continueAtAnyDepth).append(",\n");
        json.append("    \"any_depth_percent\": ")
                .append(percent(continueAtAnyDepth, executionSamples))
                .append(",\n");
        json.append("    \"callers\": ");
        appendRanked(json, continueAtCallers, continueAtAnyDepth, CONTINUE_AT_RANKED_LIMIT);
        json.append(",\n");
        json.append("    \"callees\": ");
        appendRanked(json, continueAtCallees, continueAtAnyDepth, CONTINUE_AT_RANKED_LIMIT);
        json.append(",\n");
        json.append("    \"stacks\": ");
        appendRanked(json, continueAtStacks, continueAtAnyDepth, CONTINUE_AT_RANKED_LIMIT);
        json.append(",\n");
        json.append("    \"co_occurring_markers\": ");
        appendMarkerCoOccurrence(json, CONTINUE_AT_MARKERS, continueAtMarkerStats, continueAtAnyDepth);
        json.append("\n");
        json.append("  },\n");
        json.append("  \"builder\": {\n");
        json.append("    \"matcher\": \"type name contains '$Builder'\",\n");
        json.append("    \"leaf_count\": ").append(builderLeaf).append(",\n");
        json.append("    \"leaf_percent\": ").append(percent(builderLeaf, executionSamples)).append(",\n");
        json.append("    \"any_depth_count\": ").append(builderAnyDepth).append(",\n");
        json.append("    \"any_depth_percent\": ").append(percent(builderAnyDepth, executionSamples)).append(",\n");
        json.append("    \"co_occurs_with_continue_at_count\": ")
                .append(builderCoOccursWithContinueAt)
                .append(",\n");
        json.append("    \"co_occurs_with_continue_at_percent_of_builder\": ")
                .append(percent(builderCoOccursWithContinueAt, builderAnyDepth))
                .append("\n");
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
        System.out.println("PERF006D3_STACK_DEPTH_LIMIT=" + MAX_STACK_DEPTH);
        System.out.println("PERF006D3_CONTINUE_AT_ANY_DEPTH_SAMPLES=" + continueAtAnyDepth);
        System.out.println("PERF006D3_BUILDER_ANY_DEPTH_SAMPLES=" + builderAnyDepth);
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

    /** Leaf-first bounded stack, capped at {@link #MAX_STACK_DEPTH} frames. Empty if unavailable. */
    private static List<String> boundedStackFrames(RecordedEvent event) {
        RecordedStackTrace stack = event.getStackTrace();
        if (stack == null || stack.getFrames().isEmpty()) {
            return List.of();
        }
        List<RecordedFrame> frames = stack.getFrames();
        int depth = Math.min(frames.size(), MAX_STACK_DEPTH);
        List<String> symbols = new ArrayList<>(depth);
        for (int index = 0; index < depth; index++) {
            symbols.add(frameSymbol(frames.get(index)));
        }
        return symbols;
    }

    private static String frameSymbol(RecordedFrame frame) {
        RecordedMethod method = frame.getMethod();
        if (method == null) {
            return "<no-method>";
        }
        String type = method.getType() == null ? "<no-type>" : method.getType().getName();
        return type + "." + method.getName();
    }

    private static String pathSignature(List<String> stack) {
        return stack.isEmpty() ? "<no-stack>" : String.join(" -> ", stack);
    }

    private static boolean isContinueAtFrame(String symbol) {
        return symbol.endsWith(".continueAt") && symbol.contains("CachedBytecodeNode");
    }

    private static boolean isBuilderFrame(String symbol) {
        return symbol.contains("$Builder");
    }

    private static int indexOfMatch(List<String> stack, java.util.function.Predicate<String> matcher) {
        for (int index = 0; index < stack.size(); index++) {
            if (matcher.test(stack.get(index))) {
                return index;
            }
        }
        return -1;
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

    private static void appendMarkerCoOccurrence(
            StringBuilder out, List<String> markers, Map<String, long[]> stats, long continueAtTotal) {
        out.append("[");
        for (int index = 0; index < markers.size(); index++) {
            if (index != 0) out.append(",");
            String marker = markers.get(index);
            long[] counts = stats.getOrDefault(marker, new long[3]);
            out.append("\n      {\"marker\": ")
                    .append(quote(marker))
                    .append(", \"co_occurring_count\": ")
                    .append(counts[0])
                    .append(", \"co_occurring_percent_of_continue_at\": ")
                    .append(percent(counts[0], continueAtTotal))
                    .append(", \"ancestor_count\": ")
                    .append(counts[1])
                    .append(", \"descendant_count\": ")
                    .append(counts[2])
                    .append("}");
        }
        if (!markers.isEmpty()) out.append("\n    ");
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
