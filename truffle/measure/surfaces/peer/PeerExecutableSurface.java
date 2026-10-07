/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure.peer;

import com.guillermomolina.protos.benchmarks.measure.MeasurementEngine;
import java.nio.file.Files;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Source;
import org.graalvm.polyglot.Value;

/**
 * Peer surface {@code executable-value} for GraalJS and GraalPy: the workload
 * is evaluated and its {@code truffleRun} member acquired once before timing;
 * each timed call is exactly {@code run.execute()}. Same semantics and result
 * normalization as the existing peer runner. The guest language is taken from
 * the {@code protos.benchmarks.peer.language} system property so that one
 * stable adapter serves every peer language.
 */
public final class PeerExecutableSurface {
    private PeerExecutableSurface() {}

    public static void main(String[] args) throws Exception {
        MeasurementEngine.Arguments arguments = MeasurementEngine.Arguments.parse(args);
        String language = System.getProperty("protos.benchmarks.peer.language", "");

        if (!"js".equals(language) && !"python".equals(language)) {
            throw new IllegalArgumentException("unsupported peer language: " + language);
        }

        Source source =
                Source.newBuilder(
                                language,
                                Files.readString(arguments.source()),
                                arguments.source().toString())
                        .build();

        long setupStart = System.nanoTime();

        try (Context context =
                Context.newBuilder(language).allowExperimentalOptions(true).build()) {
            context.eval(source);

            Value run = context.getBindings(language).getMember("truffleRun");

            if (run == null || !run.canExecute()) {
                throw new IllegalStateException("workload does not expose executable truffleRun");
            }

            long setupNs = System.nanoTime() - setupStart;

            MeasurementEngine.run(
                    "executable-value",
                    language,
                    arguments,
                    setupNs,
                    () -> normalize(run.execute()));
        }
    }

    private static String normalize(Value value) {
        if (value.fitsInBigInteger()) {
            return value.asBigInteger().toString();
        }
        return value.toString();
    }
}
