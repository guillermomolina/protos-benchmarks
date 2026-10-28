/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */

package com.guillermomolina.benchmarks.instrument;

import com.oracle.truffle.api.Option;
import com.oracle.truffle.api.bytecode.BytecodeNode;
import com.oracle.truffle.api.bytecode.BytecodeRootNode;
import com.oracle.truffle.api.bytecode.Instruction;
import com.oracle.truffle.api.frame.VirtualFrame;
import com.oracle.truffle.api.instrumentation.EventContext;
import com.oracle.truffle.api.instrumentation.ExecutionEventListener;
import com.oracle.truffle.api.instrumentation.SourceSectionFilter;
import com.oracle.truffle.api.instrumentation.StandardTags;
import com.oracle.truffle.api.instrumentation.TruffleInstrument;
import com.oracle.truffle.api.nodes.RootNode;

import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.IdentityHashMap;
import java.util.Map;

import org.graalvm.options.OptionCategory;
import org.graalvm.options.OptionKey;
import org.graalvm.options.OptionDescriptors;

@TruffleInstrument.Registration(
        id = "bench-bytecode-size",
        name = "Benchmark Bytecode Size",
        version = "1.0")
public final class BytecodeSizeInstrument extends TruffleInstrument {

    @Option(
            name = "",
            help = "Capture actual Bytecode DSL instruction sizes.",
            category = OptionCategory.INTERNAL)
    static final OptionKey<Boolean> ENABLED = new OptionKey<>(false);

    @Override
    protected OptionDescriptors getOptionDescriptors() {
        return new BytecodeSizeInstrumentOptionDescriptors();
    }

    private final Map<RootNode, Integer> rootIds =
            new IdentityHashMap<>();

    private final Map<RootNode, String> lastSnapshots =
            new IdentityHashMap<>();

    private int nextRootId = 1;
    private PrintWriter output;

    @Override
    protected void onCreate(Env env) {
        if (!env.getOptions().get(ENABLED)) {
            return;
        }

        output = new PrintWriter(
                new OutputStreamWriter(
                        env.err(),
                        StandardCharsets.UTF_8),
                true);

        SourceSectionFilter filter = SourceSectionFilter
                .newBuilder()
                .tagIs(StandardTags.RootTag.class)
                .build();

        env.getInstrumenter().attachExecutionEventListener(
                filter,
                new ExecutionEventListener() {

                    @Override
                    public void onEnter(
                            EventContext context,
                            VirtualFrame frame) {
                        observe(context);
                    }

                    @Override
                    public void onReturnValue(
                            EventContext context,
                            VirtualFrame frame,
                            Object result) {
                        observe(context);
                    }

                    @Override
                    public void onReturnExceptional(
                            EventContext context,
                            VirtualFrame frame,
                            Throwable exception) {
                        observe(context);
                    }
                });
    }

    private synchronized void observe(EventContext context) {
        RootNode root = context
                .getInstrumentedNode()
                .getRootNode();

        if (!(root instanceof BytecodeRootNode)) {
            return;
        }

        BytecodeNode bytecode =
                ((BytecodeRootNode) root).getBytecodeNode();

        if (bytecode == null) {
            return;
        }

        int instructionCount = 0;
        int firstBci = -1;
        int previousEnd = -1;
        long totalBytes = 0;

        for (Instruction instruction : bytecode.getInstructions()) {
            int bci = instruction.getBytecodeIndex();
            int length = instruction.getLength();

            if (length <= 0) {
                throw new IllegalStateException(
                        "Invalid Bytecode DSL instruction length");
            }

            if (instructionCount == 0) {
                firstBci = bci;
            } else if (bci != previousEnd) {
                throw new IllegalStateException(
                        "Non-contiguous Bytecode DSL instructions");
            }

            previousEnd = Math.addExact(bci, length);
            totalBytes += length;
            instructionCount++;
        }

        if (instructionCount == 0) {
            return;
        }

        if (totalBytes != (long) previousEnd - firstBci) {
            throw new IllegalStateException(
                    "Inconsistent Bytecode DSL size");
        }

        Integer rootId = rootIds.get(root);

        if (rootId == null) {
            rootId = nextRootId++;
            rootIds.put(root, rootId);
        }

        String name = root.getName();

        if (name == null || name.isEmpty()) {
            name = root.getClass().getName();
        }

        String encodedName = Base64.getEncoder()
                .encodeToString(
                        name.getBytes(StandardCharsets.UTF_8));

        String physicalRootLabel =
                root.getClass().getSimpleName() + "@"
                + Integer.toHexString(System.identityHashCode(root));

        String encodedPhysicalRootLabel = Base64.getEncoder()
                .encodeToString(
                        physicalRootLabel.getBytes(StandardCharsets.UTF_8));

        String snapshot =
                encodedName + "\t"
                + rootId + "\t"
                + bytecode.getTier().name() + "\t"
                + instructionCount + "\t"
                + totalBytes + "\t"
                + firstBci + "\t"
                + previousEnd + "\t"
                + encodedPhysicalRootLabel;

        if (!snapshot.equals(lastSnapshots.get(root))) {
            output.println(
                    "BENCH_BYTECODE_SIZE_V2\t" + snapshot);
            lastSnapshots.put(root, snapshot);
        }
    }

    @Override
    protected void onDispose(Env env) {
        if (output != null) {
            output.flush();
        }
    }
}
