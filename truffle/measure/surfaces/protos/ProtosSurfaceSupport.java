/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure.protos;

import com.guillermomolina.protos.execution.ProtosExecutionOutcome;
import com.guillermomolina.protos.execution.ProtosStandaloneHostedSession;
import com.guillermomolina.protos.runtime.ProtosIntegerValue;
import com.oracle.truffle.api.interop.InteropLibrary;
import com.oracle.truffle.api.interop.UnsupportedMessageException;
import com.guillermomolina.protos.benchmarks.measure.MeasurementEngine;

/**
 * Session opening and outcome normalization shared by the Protos surfaces
 * that return {@link ProtosExecutionOutcome}. Uses only the long-standing
 * standalone hosted session API.
 */
final class ProtosSurfaceSupport {
    private ProtosSurfaceSupport() {}

    static ProtosStandaloneHostedSession openCompleted(
            MeasurementEngine.Arguments arguments) throws Exception {
        ProtosStandaloneHostedSession session =
                ProtosStandaloneHostedSession.open(
                        arguments.requireCoreRoot(), arguments.source());

        ProtosExecutionOutcome initial = session.initialOutcome();

        if (initial.state() != ProtosExecutionOutcome.State.COMPLETED) {
            session.close();
            throw new IllegalStateException(
                    "initial source execution did not complete: "
                            + initial.state());
        }

        return session;
    }

    static String integerOutcome(ProtosExecutionOutcome outcome) {
        if (outcome.state() != ProtosExecutionOutcome.State.COMPLETED) {
            throw new IllegalStateException(
                    "benchmark invocation did not complete: " + outcome.state());
        }

        if (!(outcome.value() instanceof ProtosIntegerValue integer)) {
            throw new IllegalStateException(
                    "benchmark result is not an Integer: " + outcome.value());
        }

        // Both the historical BigInteger-backed and current long-only
        // representations export their exact value through Truffle interop.
        try {
            return InteropLibrary.getUncached().asBigInteger(integer).toString();
        } catch (UnsupportedMessageException exception) {
            throw new IllegalStateException(
                    "benchmark Integer has no exact BigInteger interop projection",
                    exception);
        }
    }
}
