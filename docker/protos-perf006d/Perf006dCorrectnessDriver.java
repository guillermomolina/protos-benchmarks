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
import com.guillermomolina.protos.runtime.ProtosEncodingValue;
import com.guillermomolina.protos.runtime.ProtosEnvironmentValue;
import com.guillermomolina.protos.runtime.ProtosIntegerValue;
import com.guillermomolina.protos.runtime.ProtosPrelude;
import com.guillermomolina.protos.runtime.ProtosProcessStandardStreamBinding;
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

public final class Perf006dCorrectnessDriver {
    private Perf006dCorrectnessDriver() {}

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
        if (args.length != 2) {
            System.err.println(
                    "usage: Perf006dCorrectnessDriver <source> <expected-integer>");
            System.exit(2);
        }

        Path sourcePath = Path.of(args[0]).toAbsolutePath().normalize();
        BigInteger expected = new BigInteger(args[1]);
        if (!Files.isRegularFile(sourcePath)) {
            throw new IllegalArgumentException("benchmark source does not exist: " + sourcePath);
        }

        String homeText = System.getenv("PROTOS_HOME");
        if (homeText == null || homeText.isBlank()) {
            throw new IllegalStateException("PROTOS_HOME is required");
        }
        Path home = Path.of(homeText).toAbsolutePath().normalize();
        Path core = home.resolve("protos/lib/core");

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

        try (ProtosPolyglotRuntimeHost runtimeHost = ProtosPolyglotRuntimeHost.open()) {
            ProtosPolyglotProcessContext processContext =
                    runtimeHost.hostProcess(
                            bootstrap.process(),
                            InputStream.nullInputStream(),
                            OutputStream.nullOutputStream(),
                            OutputStream.nullOutputStream());
            try {
                ProtosExecutionOutcome outcome =
                        processContext.execute(source, bootstrap.activation());
                if (outcome.state() != ProtosExecutionOutcome.State.COMPLETED) {
                    throw new IllegalStateException(
                            "benchmark did not complete: " + outcome.state());
                }
                if (!(outcome.value() instanceof ProtosIntegerValue integer)) {
                    throw new IllegalStateException(
                            "benchmark result is not Integer: "
                                    + outcome.value().getClass().getName());
                }
                if (!integer.value().equals(expected)) {
                    throw new IllegalStateException(
                            "result mismatch: expected="
                                    + expected
                                    + " observed="
                                    + integer.value());
                }
                System.out.println(integer.value());
            } finally {
                bootstrap.process().requestTerminationForRuntime();
            }
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

    private static boolean nativeEnvironmentNameMatches(
            String captured, String query) {
        Map<String, String> probe = new ProcessBuilder().environment();
        probe.clear();
        try {
            probe.put(captured, "");
            return probe.containsKey(query);
        } catch (IllegalArgumentException | NullPointerException invalid) {
            return false;
        }
    }
}
