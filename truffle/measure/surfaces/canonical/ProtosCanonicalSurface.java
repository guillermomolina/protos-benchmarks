/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure.protos;

import com.guillermomolina.protos.execution.ProtosStandaloneHostedSession;
import com.guillermomolina.protos.benchmarks.measure.MeasurementEngine;
import org.graalvm.polyglot.Value;

/**
 * Surface {@code canonical}: {@code session.prepareTopLevel("run")} and
 * {@code prepared.executable()} happen exactly once before timing; each timed
 * call is exactly {@code executable.execute()}, with no session gate, no
 * {@code PreparedTopLevel.invoke()}, no {@code invokeTopLevel()} and no
 * explicit Context enter/leave. The Polyglot result is normalized exactly as
 * the GraalJS/GraalPy peer surface normalizes its result.
 */
public final class ProtosCanonicalSurface {
    private ProtosCanonicalSurface() {}

    public static void main(String[] args) throws Exception {
        MeasurementEngine.Arguments arguments = MeasurementEngine.Arguments.parse(args);

        long setupStart = System.nanoTime();

        try (ProtosStandaloneHostedSession session =
                ProtosSurfaceSupport.openCompleted(arguments)) {
            ProtosStandaloneHostedSession.PreparedTopLevel prepared =
                    session.prepareTopLevel("run");
            Value executable = prepared.executable();

            if (executable == null || !executable.canExecute()) {
                throw new IllegalStateException(
                        "prepared top-level executable is not executable");
            }

            long setupNs = System.nanoTime() - setupStart;

            MeasurementEngine.run(
                    "canonical",
                    "protos",
                    arguments,
                    setupNs,
                    () -> normalize(executable.execute()));
        }
    }

    private static String normalize(Value value) {
        if (value.fitsInBigInteger()) {
            return value.asBigInteger().toString();
        }
        return value.toString();
    }
}
