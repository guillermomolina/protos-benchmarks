/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure.protos;

import com.guillermomolina.protos.execution.ProtosStandaloneHostedSession;
import com.guillermomolina.protos.benchmarks.measure.MeasurementEngine;

/**
 * Surface {@code prepared}: {@code session.prepareTopLevel("run")} once before
 * timing, then each timed call is {@code prepared.invoke()}.
 */
public final class ProtosPreparedSurface {
    private ProtosPreparedSurface() {}

    public static void main(String[] args) throws Exception {
        MeasurementEngine.Arguments arguments = MeasurementEngine.Arguments.parse(args);

        long setupStart = System.nanoTime();

        try (ProtosStandaloneHostedSession session =
                ProtosSurfaceSupport.openCompleted(arguments)) {
            ProtosStandaloneHostedSession.PreparedTopLevel prepared =
                    session.prepareTopLevel("run");
            long setupNs = System.nanoTime() - setupStart;

            MeasurementEngine.run(
                    "prepared",
                    "protos",
                    arguments,
                    setupNs,
                    () -> ProtosSurfaceSupport.integerOutcome(prepared.invoke()));
        }
    }
}
