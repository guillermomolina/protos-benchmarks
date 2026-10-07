/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure.protos;

import com.guillermomolina.protos.execution.ProtosStandaloneHostedSession;
import com.guillermomolina.protos.benchmarks.measure.MeasurementEngine;

/** Surface {@code dynamic}: each timed call is {@code session.invokeTopLevel("run")}. */
public final class ProtosDynamicSurface {
    private ProtosDynamicSurface() {}

    public static void main(String[] args) throws Exception {
        MeasurementEngine.Arguments arguments = MeasurementEngine.Arguments.parse(args);

        long setupStart = System.nanoTime();

        try (ProtosStandaloneHostedSession session =
                ProtosSurfaceSupport.openCompleted(arguments)) {
            long setupNs = System.nanoTime() - setupStart;

            MeasurementEngine.run(
                    "dynamic",
                    "protos",
                    arguments,
                    setupNs,
                    () -> ProtosSurfaceSupport.integerOutcome(
                            session.invokeTopLevel("run")));
        }
    }
}
