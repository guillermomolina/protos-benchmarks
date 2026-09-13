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

import com.guillermomolina.protos.execution.ProtosCoreBootstrap;
import com.guillermomolina.protos.execution.ProtosExecutionOutcome;
import com.guillermomolina.protos.execution.ProtosLanguage;
import com.guillermomolina.protos.execution.ProtosPolyglotProcessContext;
import com.guillermomolina.protos.execution.ProtosPolyglotRuntimeHost;
import com.guillermomolina.protos.execution.ProtosStandaloneProcessBootstrap;
import com.guillermomolina.protos.execution.ProtosStandardLibraryModuleResolver;
import com.guillermomolina.protos.runtime.ProtosActivation;
import com.guillermomolina.protos.runtime.ProtosEncodingValue;
import com.guillermomolina.protos.runtime.ProtosEnvironmentValue;
import com.guillermomolina.protos.runtime.ProtosIntegerValue;
import com.guillermomolina.protos.runtime.ProtosObjectValue;
import com.guillermomolina.protos.runtime.ProtosPrelude;
import com.guillermomolina.protos.runtime.ProtosProcessStandardStreamBinding;
import com.oracle.truffle.api.Truffle;
import com.oracle.truffle.api.source.Source;
import java.io.InputStream;
import java.io.OutputStream;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * PERF006-D2 persistent-process timing driver.
 *
 * <p>The canonical source is read and materialized as one Truffle Source once. One Protos Process,
 * RuntimeHost and Polyglot Context are retained for the complete warmup/steady series. Every
 * iteration receives a fresh module Activation so task identity and top-level mutable slots do not
 * leak between samples. The source text is never rewritten.
 *
 * <p>The timed interval is exactly processContext.execute(source, freshActivation). JVM startup,
 * Core bootstrap, Process bootstrap, source file I/O and result serialization are outside it.
 */
public final class Perf006dPersistentDriver {
    private Perf006dPersistentDriver() {}

    private static final ProtosProcessStandardStreamBinding.ReadableBackend EOF_STDIN =
            (maxBytes, completion) -> {
                completion.eof();
                return () -> {};
            };

    private static final ProtosProcessStandardStreamBinding.WritableBackend DISCARD_OUTPUT =
            (bytes, completion) -> {
                completion.succeeded();
                return () -> {};
            };

    private static final ProtosEnvironmentValue.NativeNameDomain HOST_ENVIRONMENT_NAME_DOMAIN =
            new ProtosEnvironmentValue.NativeNameDomain() {
                @Override
                public boolean sameCapturedName(String left, String right) {
                    return nativeEnvironmentNameMatches(left, right);
                }

                @Override
                public boolean isQueryRepresentable(String name) {
                    Map<String, String> probe = new ProcessBuilder().environment();
                    probe.clear();
                    try {
                        probe.put(name, "");
                        return probe.size() == 1 && probe.containsKey(name);
                    } catch (IllegalArgumentException | NullPointerException invalid) {
                        return false;
                    }
                }

                @Override
                public boolean matchesQuery(String captured, String query) {
                    return nativeEnvironmentNameMatches(captured, query);
                }
            };

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println(
                    "usage: Perf006dPersistentDriver <source> <expected-integer> <warmup> <steady>");
            System.exit(2);
        }

        Path sourcePath = Path.of(args[0]).toAbsolutePath().normalize();
        BigInteger expected = new BigInteger(args[1]);
        int warmupIterations = parseCount(args[2], "warmup");
        int steadySamples = parseCount(args[3], "steady");
        if (!Files.isRegularFile(sourcePath)) {
            throw new IllegalArgumentException("benchmark source does not exist: " + sourcePath);
        }

        String homeText = System.getenv("PROTOS_HOME");
        if (homeText == null || homeText.isBlank()) {
            throw new IllegalStateException("PROTOS_HOME is required");
        }
        Path home = Path.of(homeText).toAbsolutePath().normalize();
        Path core = home.resolve("protos/lib/core");
        if (!Files.isDirectory(core)) {
            throw new IllegalStateException("Protos Core directory is missing: " + core);
        }

        ProtosPrelude prelude =
                new ProtosCoreBootstrap()
                        .bootstrap(core, new ProtosStandardLibraryModuleResolver(core.getParent()));
        ProtosEncodingValue utf8 = utf8(prelude);
        ProtosStandaloneProcessBootstrap.Result bootstrap =
                ProtosStandaloneProcessBootstrap.create(
                        prelude,
                        List.of(),
                        HOST_ENVIRONMENT_NAME_DOMAIN,
                        hostEnvironmentEntries(),
                        EOF_STDIN,
                        DISCARD_OUTPUT,
                        DISCARD_OUTPUT,
                        utf8,
                        utf8,
                        utf8,
                        null);

        Source source =
                Source.newBuilder(
                                ProtosLanguage.ID,
                                Files.readString(sourcePath, StandardCharsets.UTF_8),
                                sourcePath.getFileName().toString())
                        .uri(sourcePath.toUri())
                        .mimeType(ProtosLanguage.MIME_TYPE)
                        .build();

        String runtimeClass = Truffle.getRuntime().getClass().getName();

        try (ProtosPolyglotRuntimeHost runtimeHost = ProtosPolyglotRuntimeHost.open()) {
            ProtosPolyglotProcessContext processContext =
                    runtimeHost.hostProcess(
                            bootstrap.process(),
                            InputStream.nullInputStream(),
                            OutputStream.nullOutputStream(),
                            OutputStream.nullOutputStream());
            try {
                List<Long> warmup =
                        measureSeries(
                                processContext,
                                source,
                                bootstrap.activation(),
                                prelude,
                                expected,
                                warmupIterations,
                                "warmup");
                List<Long> steady =
                        measureSeries(
                                processContext,
                                source,
                                bootstrap.activation(),
                                prelude,
                                expected,
                                steadySamples,
                                "steady");
                emitJson(expected, runtimeClass, warmup, steady);
            } finally {
                bootstrap.process().requestTerminationForRuntime();
            }
        }
    }

    private static List<Long> measureSeries(
            ProtosPolyglotProcessContext processContext,
            Source source,
            ProtosActivation template,
            ProtosPrelude prelude,
            BigInteger expected,
            int count,
            String phase) {
        ArrayList<Long> samples = new ArrayList<>(count);
        for (int index = 0; index < count; index++) {
            ProtosActivation activation = freshModuleActivation(prelude, template);
            long started = System.nanoTime();
            ProtosExecutionOutcome outcome = processContext.execute(source, activation);
            long elapsed = System.nanoTime() - started;
            requireCompletedInteger(outcome, expected, phase + "[" + index + "]");
            if (elapsed <= 0) {
                throw new IllegalStateException("non-positive timing sample in " + phase);
            }
            samples.add(elapsed);
        }
        return List.copyOf(samples);
    }

    private static ProtosActivation freshModuleActivation(
            ProtosPrelude prelude, ProtosActivation template) {
        ProtosObjectValue context = prelude.newExecutionContext();
        return prelude.newModuleActivation(
                template.actorModuleState(),
                template.currentModuleKey().orElse(null),
                context,
                template.executionDomain());
    }

    private static void requireCompletedInteger(
            ProtosExecutionOutcome outcome, BigInteger expected, String phase) {
        if (outcome.state() != ProtosExecutionOutcome.State.COMPLETED) {
            throw new IllegalStateException(phase + " did not complete: " + outcome.state());
        }
        if (!(outcome.value() instanceof ProtosIntegerValue integer)) {
            throw new IllegalStateException(
                    phase + " result is not Integer: " + outcome.value().getClass().getName());
        }
        if (!integer.value().equals(expected)) {
            throw new IllegalStateException(
                    phase
                            + " result mismatch: expected="
                            + expected
                            + " observed="
                            + integer.value());
        }
    }

    private static ProtosEncodingValue utf8(ProtosPrelude prelude) {
        Object value =
                prelude.encodingPrototype()
                        .readLocalSlot("UTF8")
                        .orElseThrow(
                                () -> new IllegalStateException("Core Encoding.UTF8 is missing"));
        if (!(value instanceof ProtosEncodingValue encoding)) {
            throw new IllegalStateException("Core Encoding.UTF8 is not Encoding");
        }
        return encoding;
    }

    private static List<ProtosEnvironmentValue.NativeEntry> hostEnvironmentEntries() {
        ArrayList<ProtosEnvironmentValue.NativeEntry> entries = new ArrayList<>();
        for (Map.Entry<String, String> entry : System.getenv().entrySet()) {
            entries.add(
                    new ProtosEnvironmentValue.NativeEntry(
                            entry.getKey(), entry.getValue()));
        }
        return List.copyOf(entries);
    }

    private static boolean nativeEnvironmentNameMatches(String captured, String query) {
        Map<String, String> probe = new ProcessBuilder().environment();
        probe.clear();
        try {
            probe.put(captured, "");
            return probe.containsKey(query);
        } catch (IllegalArgumentException | NullPointerException invalid) {
            return false;
        }
    }

    private static int parseCount(String text, String name) {
        int value = Integer.parseInt(text);
        if (value < 0 || value > 100000) {
            throw new IllegalArgumentException(name + " count out of range: " + value);
        }
        return value;
    }

    private static void emitJson(
            BigInteger expected, String runtimeClass, List<Long> warmup, List<Long> steady) {
        StringBuilder out = new StringBuilder();
        out.append('{');
        out.append("\"schema_version\":1,");
        out.append("\"expected\":\"").append(expected).append("\",");
        out.append("\"runtime\":\"").append(runtimeClass).append("\",");
        out.append("\"source_reused\":true,");
        out.append("\"process_reused\":true,");
        out.append("\"context_reused\":true,");
        out.append("\"fresh_activation_per_iteration\":true,");
        out.append("\"warmup_ns\":");
        appendLongArray(out, warmup);
        out.append(',');
        out.append("\"steady_ns\":");
        appendLongArray(out, steady);
        out.append('}');
        System.out.println(out);
    }

    private static void appendLongArray(StringBuilder out, List<Long> values) {
        out.append('[');
        for (int index = 0; index < values.size(); index++) {
            if (index != 0) out.append(',');
            out.append(values.get(index));
        }
        out.append(']');
    }
}
