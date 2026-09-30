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

import com.oracle.truffle.api.instrumentation.Instrumenter;
import com.oracle.truffle.api.instrumentation.LoadSourceSectionEvent;
import com.oracle.truffle.api.instrumentation.SourceSectionFilter;
import com.oracle.truffle.api.instrumentation.TruffleInstrument;
import com.oracle.truffle.api.nodes.RootNode;
import com.oracle.truffle.api.source.SourceSection;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;
import org.graalvm.options.OptionCategory;
import org.graalvm.options.OptionDescriptor;
import org.graalvm.options.OptionDescriptors;
import org.graalvm.options.OptionKey;
import org.graalvm.options.OptionStability;

/**
 * PERF010-A hot-root lifecycle discriminator: per-root source identity (harness-local, not
 * published to {@code guillermomolina/protos}).
 *
 * <p>This is the root-aware superset of {@link Perf010aSourceIdentityInstrument}, whose mechanism
 * it reuses unchanged: real Truffle instrumentation, through public API only
 * ({@code Instrumenter#attachLoadSourceSectionListener}), forces the Bytecode DSL to materialize
 * optional source information for the generated {@code ProtosBytecodeRootNode} helper roots and
 * {@code ProtosSemanticBytecodeRootNode} semantic roots without any Protos source change and
 * without discarding {@code CallTarget} identity. The historical record kept the observed source
 * section and only the root's class name; that cannot tell two roots of one class apart, so this
 * record additionally keeps, per distinct root object, the root's own source section and every
 * node source section observed inside it, together with the run-local root label
 * ({@code SimpleName@identityHashHex}, the label the compiler traces print). The label and the
 * identity hash are run-local correlation keys only. The durable identity of a root is derived
 * later from its source section, never from the label.
 *
 * <p>Scope stays deliberately narrow, exactly like the historical instrument: the listener's
 * {@link SourceSectionFilter} matches one Source name, selected through
 * {@link #TARGET_SOURCE_NAME_PROPERTY}, so it cannot silently widen into a general "materialize
 * everything" mechanism. It is inert unless {@code -Dpolyglot.perf010aHotRootIdentity=true} is
 * passed, it registers no execution binding and it reads no compilation option.
 *
 * <p>The option is {@link OptionStability#STABLE} (an experimental option would need
 * {@code allowExperimentalOptions(true)} on the embedder's Context builder, a Protos-internal call
 * this harness must not touch) and the load-bearing {@code @Registration} annotation lives on the
 * Provider class, as established for the historical instrument.
 */
@TruffleInstrument.Registration(
        id = Perf010aHotRootIdentityInstrument.ID,
        name = "PERF010-A Hot Root Identity Diagnostic",
        version = "1.0")
public final class Perf010aHotRootIdentityInstrument extends TruffleInstrument {

    /** Also this instrument's boolean enable-option name. */
    public static final String ID = "perf010aHotRootIdentity";

    public static final String TARGET_SOURCE_NAME_PROPERTY = "perf010a.hotRoot.targetSource";

    public static String targetSourceName() {
        return System.getProperty(TARGET_SOURCE_NAME_PROPERTY, "");
    }

    private static final OptionKey<Boolean> ENABLED = new OptionKey<>(false);

    private static final Object LOCK = new Object();
    private static final IdentityHashMap<RootNode, RootRecord> BY_ROOT = new IdentityHashMap<>();
    private static final List<RootRecord> ORDER = new ArrayList<>();

    /** One observed source section (the historical record fields, minus the source name). */
    public record SectionSnapshot(
            int startOffset, int endOffset, int length, int line, int column, String text) {}

    public record NodeSnapshot(SectionSnapshot section, String nodeClassName) {}

    /** One distinct root object, in first-observation order. */
    public record RootSnapshot(
            String rootNodeClassName,
            String simpleName,
            int identityHash,
            String toStringValue,
            SectionSnapshot rootSection,
            List<NodeSnapshot> nodes) {}

    private static final class RootRecord {
        final RootNode root;
        SectionSnapshot rootSection;
        final List<NodeSnapshot> nodes = new ArrayList<>();
        final Set<String> seen = new HashSet<>();

        RootRecord(RootNode root) {
            this.root = root;
        }
    }

    private static SectionSnapshot snapshotOf(SourceSection section) {
        return new SectionSnapshot(
                section.getCharIndex(),
                section.getCharIndex() + section.getCharLength(),
                section.getCharLength(),
                section.getStartLine(),
                section.getStartColumn(),
                section.getCharacters().toString());
    }

    /** Snapshot of every root observed so far. Call after the measured run has finished. */
    public static List<RootSnapshot> snapshot() {
        synchronized (LOCK) {
            List<RootSnapshot> out = new ArrayList<>(ORDER.size());
            for (RootRecord record : ORDER) {
                String toStringValue;
                try {
                    toStringValue = String.valueOf(record.root);
                } catch (RuntimeException failure) {
                    toStringValue = "";
                }
                out.add(
                        new RootSnapshot(
                                record.root.getClass().getName(),
                                record.root.getClass().getSimpleName(),
                                System.identityHashCode(record.root),
                                toStringValue,
                                record.rootSection,
                                List.copyOf(record.nodes)));
            }
            return List.copyOf(out);
        }
    }

    /** Clears prior observations; called by the driver before its measured run. */
    public static void resetForNewMeasurement() {
        synchronized (LOCK) {
            BY_ROOT.clear();
            ORDER.clear();
        }
    }

    private static void observe(RootNode root, SourceSection section, String nodeClassName) {
        synchronized (LOCK) {
            RootRecord record = BY_ROOT.get(root);
            if (record == null) {
                record = new RootRecord(root);
                BY_ROOT.put(root, record);
                ORDER.add(record);
            }
            if (record.rootSection == null) {
                try {
                    SourceSection own = root.getSourceSection();
                    if (own != null && own.isAvailable()) {
                        record.rootSection = snapshotOf(own);
                    }
                } catch (RuntimeException failure) {
                    record.rootSection = null;
                }
            }
            SectionSnapshot snapshot = snapshotOf(section);
            String key = snapshot.startOffset() + ":" + snapshot.endOffset() + ":" + nodeClassName;
            if (record.seen.add(key)) {
                record.nodes.add(new NodeSnapshot(snapshot, nodeClassName));
            }
        }
    }

    @Override
    protected OptionDescriptors getOptionDescriptors() {
        return OptionDescriptors.create(
                List.of(
                        OptionDescriptor.newBuilder(ENABLED, ID)
                                .category(OptionCategory.USER)
                                .stability(OptionStability.STABLE)
                                .help(
                                        "PERF010-A hot-root discriminator diagnostic: record per-root "
                                                + "source identity for the selected Source by attaching a "
                                                + "Truffle instrumentation source-section listener. "
                                                + "Diagnostic-only; never used by timing evidence.")
                                .build()));
    }

    @Override
    protected void onCreate(Env env) {
        Instrumenter instrumenter = env.getInstrumenter();
        SourceSectionFilter filter =
                SourceSectionFilter.newBuilder()
                        .sourceIs(
                                source ->
                                        source != null
                                                && !targetSourceName().isEmpty()
                                                && targetSourceName().equals(source.getName()))
                        .build();
        instrumenter.attachLoadSourceSectionListener(
                filter,
                (LoadSourceSectionEvent event) -> {
                    SourceSection section = event.getSourceSection();
                    if (section == null || !section.isAvailable() || event.getNode() == null) {
                        return;
                    }
                    RootNode root = event.getNode().getRootNode();
                    if (root == null) {
                        return;
                    }
                    observe(root, section, event.getNode().getClass().getName());
                },
                true);
    }
}
