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

import com.guillermomolina.protos.execution.ProtosClosureInvoker;
import com.guillermomolina.protos.execution.ProtosCoreBootstrap;
import com.guillermomolina.protos.execution.ProtosExecutionOutcome;
import com.guillermomolina.protos.execution.ProtosLanguage;
import com.guillermomolina.protos.execution.ProtosPolyglotProcessContext;
import com.guillermomolina.protos.execution.ProtosPolyglotRuntimeHost;
import com.guillermomolina.protos.execution.ProtosStandaloneProcessBootstrap;
import com.guillermomolina.protos.execution.ProtosStandardLibraryModuleResolver;
import com.guillermomolina.protos.runtime.ProtosActivation;
import com.guillermomolina.protos.runtime.ProtosClosureValue;
import com.guillermomolina.protos.runtime.ProtosEncodingValue;
import com.guillermomolina.protos.runtime.ProtosEnvironmentValue;
import com.guillermomolina.protos.runtime.ProtosIntegerValue;
import com.guillermomolina.protos.runtime.ProtosPrelude;
import com.guillermomolina.protos.runtime.ProtosProcessStandardStreamBinding;
import com.guillermomolina.protos.runtime.ProtosTask;
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
 * PERF001-F host driver for warmup/steady-state measurement in one production-hosted Process.
 *
 * <p>An untimed setup projection changes only the canonical source's terminal {@code run()} to
 * {@code run}. Executing that projected source as a real RootActor task creates the ordinary
 * top-level {@code run} Closure and performs benchmark bootstrap (notably Actor spawn/readiness)
 * without consuming an unretained run invocation. Each retained iteration then invokes exactly that existing Closure as a
 * fresh RootActor-local task inside the same Process-scoped Polyglot Context. Source parsing, Core
 * bootstrap, Process bootstrap, Actor bootstrap and result serialization are outside the timed
 * interval. The timed interval includes task creation, scheduling/dispatch, guest execution and
 * semantic task completion.
 */
public final class Perf001fPersistentDriver {
    private Perf001fPersistentDriver() {}

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
                    "usage: Perf001fPersistentDriver <source> <expected-integer> <warmup> <steady>");
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

        String canonicalSource = Files.readString(sourcePath, StandardCharsets.UTF_8);
        String setupSource = setupProjection(canonicalSource);
        Source source =
                Source.newBuilder(
                                ProtosLanguage.ID,
                                setupSource,
                                sourcePath.getFileName().toString())
                        .uri(sourcePath.toUri())
                        .mimeType(ProtosLanguage.MIME_TYPE)
                        .build();

        try (ProtosPolyglotRuntimeHost runtimeHost = ProtosPolyglotRuntimeHost.open()) {
            ProtosPolyglotProcessContext processContext =
                    runtimeHost.hostProcess(
                            bootstrap.process(),
                            InputStream.nullInputStream(),
                            OutputStream.nullOutputStream(),
                            OutputStream.nullOutputStream());
            try {
                ProtosExecutionOutcome setup = processContext.execute(source, bootstrap.activation());
                if (setup.state() != ProtosExecutionOutcome.State.COMPLETED) {
                    throw new IllegalStateException("setup projection did not complete: " + setup.state());
                }

                Object runValue =
                        bootstrap.activation()
                                .context()
                                .readLocalSlot("run")
                                .orElseThrow(
                                        () ->
                                                new IllegalStateException(
                                                        "canonical benchmark did not publish top-level run"));
                if (!(runValue instanceof ProtosClosureValue runClosure)) {
                    throw new IllegalStateException("top-level run is not a Closure");
                }
                if (setup.value() != runClosure) {
                    throw new IllegalStateException(
                            "setup projection did not return the exact top-level run Closure");
                }

                List<Long> warmup =
                        measureSeries(
                                processContext,
                                bootstrap.activation(),
                                runClosure,
                                expected,
                                warmupIterations,
                                "warmup");
                List<Long> steady =
                        measureSeries(
                                processContext,
                                bootstrap.activation(),
                                runClosure,
                                expected,
                                steadySamples,
                                "steady");

                emitJson(expected, warmup, steady);
            } finally {
                bootstrap.process().requestTerminationForRuntime();
            }
        }
    }

    private static List<Long> measureSeries(
            ProtosPolyglotProcessContext processContext,
            ProtosActivation activation,
            ProtosClosureValue runClosure,
            BigInteger expected,
            int count,
            String phase) {
        ArrayList<Long> samples = new ArrayList<>(count);
        for (int index = 0; index < count; index++) {
            long started = System.nanoTime();
            ProtosTask task =
                    activation.executionDomain()
                            .createTask(
                                    null,
                                    null,
                                    created ->
                                            created.executeAction(
                                                    () ->
                                                            ProtosClosureInvoker.invokeInTask(
                                                                    runClosure,
                                                                    List.of(),
                                                                    activation,
                                                                    created)));
            processContext.callForRuntime(
                    () -> {
                        activation.executionDomain().dispatchUntilTerminal(task, () -> false);
                        return null;
                    });
            long elapsed = System.nanoTime() - started;
            requireCompletedInteger(task, expected, phase + "[" + index + "]");
            if (elapsed <= 0) {
                throw new IllegalStateException("non-positive timing sample in " + phase);
            }
            samples.add(elapsed);
        }
        return List.copyOf(samples);
    }

    private static void requireCompletedInteger(
            ProtosExecutionOutcome outcome, BigInteger expected, String phase) {
        if (outcome.state() != ProtosExecutionOutcome.State.COMPLETED) {
            throw new IllegalStateException(phase + " did not complete: " + outcome.state());
        }
        requireInteger(outcome.value(), expected, phase);
    }

    private static void requireCompletedInteger(
            ProtosTask task, BigInteger expected, String phase) {
        if (task.state() != ProtosTask.State.COMPLETED) {
            throw new IllegalStateException(phase + " task did not complete: " + task.state());
        }
        requireInteger(task.result().orElseThrow(), expected, phase);
    }

    private static void requireInteger(Object value, BigInteger expected, String phase) {
        if (!(value instanceof ProtosIntegerValue integer)) {
            throw new IllegalStateException(
                    phase + " result is not Integer: " + value.getClass().getName());
        }
        if (!integer.value().equals(expected)) {
            throw new IllegalStateException(
                    phase + " result mismatch: expected=" + expected + " observed=" + integer.value());
        }
    }

    private static ProtosEncodingValue utf8(ProtosPrelude prelude) {
        Object value =
                prelude.encodingPrototype()
                        .readLocalSlot("UTF8")
                        .orElseThrow(() -> new IllegalStateException("Core Encoding.UTF8 is missing"));
        if (!(value instanceof ProtosEncodingValue encoding)) {
            throw new IllegalStateException("Core Encoding.UTF8 is not an Encoding descriptor");
        }
        return encoding;
    }

    private static List<ProtosEnvironmentValue.NativeEntry> hostEnvironmentEntries() {
        ArrayList<ProtosEnvironmentValue.NativeEntry> entries = new ArrayList<>();
        for (Map.Entry<String, String> entry : System.getenv().entrySet()) {
            entries.add(new ProtosEnvironmentValue.NativeEntry(entry.getKey(), entry.getValue()));
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

    private static String setupProjection(String canonicalSource) {
        String body = canonicalSource.stripTrailing();
        String terminal = "run()";
        if (!body.endsWith(terminal)) {
            throw new IllegalArgumentException(
                    "canonical PERF001-F source lacks terminal run(): source cannot be projected");
        }
        return body.substring(0, body.length() - terminal.length()) + "run\n";
    }

    private static int parseCount(String text, String name) {
        int value = Integer.parseInt(text);
        if (value < 0 || value > 100000) {
            throw new IllegalArgumentException(name + " count out of range: " + value);
        }
        return value;
    }

    private static void emitJson(BigInteger expected, List<Long> warmup, List<Long> steady) {
        StringBuilder out = new StringBuilder();
        out.append('{');
        out.append("\"schema_version\":1,");
        out.append("\"expected\":\"").append(expected).append("\",");
        out.append("\"setup_run_binding_ready\":true,");
        out.append("\"setup_projection\":\"terminal run() -> run\",");
        out.append("\"process_reused\":true,");
        out.append("\"context_reused\":true,");
        out.append("\"run_binding_reused\":true,");
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
        for (int i = 0; i < values.size(); i++) {
            if (i != 0) out.append(',');
            out.append(values.get(i));
        }
        out.append(']');
    }
}
