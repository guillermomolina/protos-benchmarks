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
import java.lang.reflect.Constructor;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.graalvm.polyglot.Engine;

/**
 * PERF010-A hot-root lifecycle / compiled-shape discriminator driver (diagnostic, not timing).
 *
 * <p>Runs one workload Source through the exact production
 * {@code ProtosPolyglotProcessContext.execute(Source, ProtosActivation)} path (the same bootstrap
 * and per-iteration correctness enforcement as {@code Dist006dDriver}, which it duplicates by this
 * repository's small-standalone-driver convention) for a fixed number of warmup and steady
 * iterations, and additionally:
 *
 * <ul>
 *   <li>prints objective phase markers on <em>stderr</em>, the stream the Truffle compiler trace
 *       uses, so every compiler-trace record can be assigned to a phase by its position relative to
 *       the markers alone: {@code startup}, {@code warmup}, {@code steady}, {@code closing},
 *       {@code end}. {@code end} is printed last, after the engine has been closed, so its absence
 *       proves the process did not terminate normally;
 *   <li>after the engine is closed, writes the per-root source-identity inventory of
 *       {@link Perf010aHotRootIdentityInstrument} as JSON (schema
 *       {@code perf010a-hot-root-identity-v1}) to the given path, together with the SHA-256 of the
 *       exact source bytes it executed.
 * </ul>
 *
 * <p>It fails (uncaught exception, non-zero exit, no {@code end} marker) on any wrong result: a wrong
 * result is not diagnostic evidence.
 */
public final class Perf010aHotRootDriver {
    private Perf010aHotRootDriver() {}

    private static final String MARK_PREFIX = "PERF010A_HOTROOT_MARK phase=";

    private static final String ENGINE_OPTION_PROPERTY_PREFIX =
            "perf010a.hotRoot.engineOption.";

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
        if (args.length != 5) {
            usage();
        }
        Path sourcePath = Path.of(args[0]).toAbsolutePath().normalize();
        BigInteger expected = new BigInteger(args[1]);
        int warmupIterations = parseCount(args[2], "warmup");
        int steadyIterations = parseCount(args[3], "steady");
        Path identityOut = Path.of(args[4]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(sourcePath)) {
            throw new IllegalArgumentException("benchmark source does not exist: " + sourcePath);
        }

        String sourceName = sourcePath.getFileName().toString();
        String targetSourceName = Perf010aHotRootIdentityInstrument.targetSourceName();
        if (!sourceName.equals(targetSourceName)) {
            throw new IllegalArgumentException(
                    "source identity target mismatch: configured=" + targetSourceName
                            + " actual=" + sourceName);
        }
        byte[] sourceBytes = Files.readAllBytes(sourcePath);
        String sourceSha256 =
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(sourceBytes));

        String homeText = System.getenv("PROTOS_HOME");
        if (homeText == null || homeText.isBlank()) {
            throw new IllegalStateException("PROTOS_HOME is required");
        }
        Path home = Path.of(homeText).toAbsolutePath().normalize();
        Path core = home.resolve("protos/lib/core");
        if (!Files.isDirectory(core)) {
            throw new IllegalStateException("Protos Core directory is missing: " + core);
        }

        mark("startup");
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
                                sourceName)
                        .uri(sourcePath.toUri())
                        .mimeType(ProtosLanguage.MIME_TYPE)
                        .build();
        String runtimeClass = Truffle.getRuntime().getClass().getName();

        Perf010aHotRootIdentityInstrument.resetForNewMeasurement();

        try (ProtosPolyglotRuntimeHost runtimeHost = openDiagnosticRuntimeHost()) {
            ProtosPolyglotProcessContext processContext =
                    runtimeHost.hostProcess(
                            bootstrap.process(),
                            InputStream.nullInputStream(),
                            OutputStream.nullOutputStream(),
                            OutputStream.nullOutputStream());
            try {
                mark("warmup");
                runSeries(
                        processContext,
                        source,
                        bootstrap.activation(),
                        prelude,
                        expected,
                        warmupIterations,
                        "warmup");
                mark("steady");
                runSeries(
                        processContext,
                        source,
                        bootstrap.activation(),
                        prelude,
                        expected,
                        steadyIterations,
                        "steady");
                mark("closing");
            } finally {
                bootstrap.process().requestTerminationForRuntime();
            }
        }

        List<Perf010aHotRootIdentityInstrument.RootSnapshot> roots =
                Perf010aHotRootIdentityInstrument.snapshot();
        Files.writeString(
                identityOut,
                identityJson(sourceName, sourceSha256, sourceBytes.length, runtimeClass, roots),
                StandardCharsets.UTF_8);

        System.out.println(
                "{\"schema_version\":1,\"mode\":\"hot-root-diagnostic\",\"expected\":\""
                        + expected
                        + "\",\"observed\":\""
                        + expected
                        + "\",\"runtime\":"
                        + quote(runtimeClass)
                        + ",\"warmup_iterations\":"
                        + warmupIterations
                        + ",\"steady_iterations\":"
                        + steadyIterations
                        + ",\"source_name\":"
                        + quote(sourceName)
                        + ",\"source_sha256\":\""
                        + sourceSha256
                        + "\",\"roots\":"
                        + roots.size()
                        + ",\"timing_evidence\":false}");
        System.out.flush();
        mark("end");
    }

    /**
     * Creates the exact pinned Protos RuntimeHost around a diagnostic Engine.
     *
     * <p>The production product is not modified. Engine and instrument options are supplied
     * programmatically so experimental compiler diagnostics are admitted by the Engine.Builder
     * and are not reinterpreted later by Context.Builder as polyglot system properties.
     *
     * <p>The pinned product revision has no public diagnostic Engine-injection factory. This
     * harness therefore reflects only its private two-argument RuntimeHost constructor. The
     * constructor shape is checked exactly and fails closed on product drift. Guest execution
     * still enters through the ordinary RuntimeHost.hostProcess() path below.
     */
    private static ProtosPolyglotRuntimeHost openDiagnosticRuntimeHost() {
        Engine.Builder builder =
                Engine.newBuilder(ProtosLanguage.ID)
                        .allowExperimentalOptions(true);

        List<String> propertyNames =
                new ArrayList<>(System.getProperties().stringPropertyNames());
        propertyNames.sort(String::compareTo);

        for (String propertyName : propertyNames) {
            if (!propertyName.startsWith(ENGINE_OPTION_PROPERTY_PREFIX)) {
                continue;
            }

            String optionName =
                    propertyName.substring(ENGINE_OPTION_PROPERTY_PREFIX.length());
            String optionValue = System.getProperty(propertyName);

            if (optionName.isBlank() || optionValue == null) {
                throw new IllegalStateException(
                        "invalid diagnostic Engine option property: " + propertyName);
            }

            builder.option(optionName, optionValue);
        }

        Engine engine = builder.build();

        try {
            Constructor<?> selected = null;

            for (Constructor<?> candidate :
                    ProtosPolyglotRuntimeHost.class.getDeclaredConstructors()) {
                Class<?>[] parameterTypes = candidate.getParameterTypes();

                if (parameterTypes.length == 2
                        && parameterTypes[0] == Engine.class
                        && parameterTypes[1]
                                .getName()
                                .equals(
                                        "com.guillermomolina.protos.execution."
                                                + "ProtosGraalDapReadinessAdapter")) {
                    if (selected != null) {
                        throw new IllegalStateException(
                                "ambiguous pinned RuntimeHost constructor");
                    }
                    selected = candidate;
                }
            }

            if (selected == null) {
                throw new IllegalStateException(
                        "pinned RuntimeHost diagnostic constructor not found");
            }

            selected.setAccessible(true);

            return (ProtosPolyglotRuntimeHost)
                    selected.newInstance(engine, null);
        } catch (ReflectiveOperationException | RuntimeException failure) {
            try {
                engine.close();
            } catch (RuntimeException closeFailure) {
                failure.addSuppressed(closeFailure);
            }

            throw new IllegalStateException(
                    "cannot construct pinned diagnostic RuntimeHost",
                    failure);
        }
    }

    private static void mark(String phase) {
        System.err.println(MARK_PREFIX + phase);
        System.err.flush();
    }

    private static void usage() {
        System.err.println(
                "usage: Perf010aHotRootDriver <source> <expected-integer> <warmup> <steady>"
                        + " <identity-output.json>");
        System.exit(2);
    }

    private static void runSeries(
            ProtosPolyglotProcessContext processContext,
            Source source,
            ProtosActivation template,
            ProtosPrelude prelude,
            BigInteger expected,
            int count,
            String phase) {
        for (int index = 0; index < count; index++) {
            ProtosActivation activation = freshModuleActivation(prelude, template);
            ProtosExecutionOutcome outcome = processContext.execute(source, activation);
            requireCompletedInteger(outcome, expected, phase + "[" + index + "]");
        }
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
                    phase + " result mismatch: expected=" + expected + " observed=" + integer.value());
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
                    new ProtosEnvironmentValue.NativeEntry(entry.getKey(), entry.getValue()));
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

    private static String identityJson(
            String sourceName,
            String sourceSha256,
            int sourceBytes,
            String runtimeClass,
            List<Perf010aHotRootIdentityInstrument.RootSnapshot> roots) {
        StringBuilder out = new StringBuilder();
        out.append("{\"schema\":\"perf010a-hot-root-identity-v1\",");
        out.append("\"source_name\":").append(quote(sourceName)).append(',');
        out.append("\"source_sha256\":\"").append(sourceSha256).append("\",");
        out.append("\"source_bytes\":").append(sourceBytes).append(',');
        out.append("\"runtime_class\":").append(quote(runtimeClass)).append(',');
        out.append("\"roots\":[");
        boolean firstRoot = true;
        for (Perf010aHotRootIdentityInstrument.RootSnapshot root : roots) {
            if (!firstRoot) {
                out.append(',');
            }
            firstRoot = false;
            String hex = Integer.toHexString(root.identityHash());
            out.append('{');
            out.append("\"rootNodeClassName\":").append(quote(root.rootNodeClassName())).append(',');
            out.append("\"simpleName\":").append(quote(root.simpleName())).append(',');
            out.append("\"identityHash\":\"").append(hex).append("\",");
            out.append("\"label\":").append(quote(root.simpleName() + "@" + hex)).append(',');
            out.append("\"toString\":").append(quote(root.toStringValue())).append(',');
            out.append("\"rootSection\":");
            appendSection(out, root.rootSection());
            out.append(",\"nodes\":[");
            boolean firstNode = true;
            for (Perf010aHotRootIdentityInstrument.NodeSnapshot node : root.nodes()) {
                if (!firstNode) {
                    out.append(',');
                }
                firstNode = false;
                out.append("{\"section\":");
                appendSection(out, node.section());
                out.append(",\"nodeClassName\":").append(quote(node.nodeClassName())).append('}');
            }
            out.append("]}");
        }
        out.append("]}\n");
        return out.toString();
    }

    private static void appendSection(
            StringBuilder out, Perf010aHotRootIdentityInstrument.SectionSnapshot section) {
        if (section == null) {
            out.append("null");
            return;
        }
        out.append("{\"startOffset\":").append(section.startOffset());
        out.append(",\"endOffset\":").append(section.endOffset());
        out.append(",\"length\":").append(section.length());
        out.append(",\"line\":").append(section.line());
        out.append(",\"column\":").append(section.column());
        out.append(",\"text\":").append(quote(section.text())).append('}');
    }

    private static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder(value.length() + 2);
        out.append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\b':
                    out.append("\\b");
                    break;
                case '\f':
                    out.append("\\f");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        out.append('"');
        return out.toString();
    }
}
