/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure.protos;

import com.guillermomolina.protos.benchmarks.measure.MeasurementEngine;
import java.nio.file.Files;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Source;
import org.graalvm.polyglot.Value;

/**
 * Surface {@code canonical}: standard Polyglot embedding, identical in shape
 * to the GraalJS/GraalPy peer surface. The source is evaluated with
 * {@code context.eval(source)} and its {@code run} member is acquired once
 * through {@code context.getBindings("protos").getMember("run")} before
 * timing; each timed call is exactly {@code run.execute()}. The Polyglot
 * result is normalized exactly as the peer surface normalizes its result.
 */
public final class ProtosCanonicalSurface {
    private ProtosCanonicalSurface() {}

    public static void main(String[] args) throws Exception {
        MeasurementEngine.Arguments arguments = MeasurementEngine.Arguments.parse(args);

        Source source =
                Source.newBuilder(
                                "protos",
                                Files.readString(arguments.source()),
                                arguments.source().toString())
                        .build();

        long setupStart = System.nanoTime();

        try (Context context =
                Context.newBuilder("protos")
                        .allowExperimentalOptions(true)
                        .option("protos.CoreRoot", arguments.requireCoreRoot().toString())
                        .build()) {
            context.eval(source);

            Value run = context.getBindings("protos").getMember("run");

            if (run == null || !run.canExecute()) {
                throw new IllegalStateException("workload does not expose executable run");
            }

            long setupNs = System.nanoTime() - setupStart;

            MeasurementEngine.run(
                    "canonical",
                    "protos",
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
