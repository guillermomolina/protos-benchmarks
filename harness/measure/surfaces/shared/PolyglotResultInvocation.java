/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.measure.shared;

import com.guillermomolina.protos.benchmarks.measure.MeasurementEngine;
import java.math.BigInteger;
import org.graalvm.polyglot.Value;

/**
 * Shared Polyglot invocation and per-call result verification.
 *
 * <p>The cold invocation establishes the expected observable result.
 * Integer results are subsequently compared numerically without formatting
 * or allocating a result String on every invocation. Other result types
 * retain the existing normalized textual comparison behavior.
 *
 * <p>Every invocation executes the guest callable exactly once and verifies
 * its result. The cached text is returned only after verification succeeds.
 */
public final class PolyglotResultInvocation
        implements MeasurementEngine.Invocation {

    private final Value run;
    private boolean initialized;
    private boolean integerMode;
    private BigInteger expectedInteger;
    private String expectedText;

    public PolyglotResultInvocation(Value run) {
        if (run == null || !run.canExecute()) {
            throw new IllegalArgumentException(
                    "expected an executable Polyglot value");
        }
        this.run = run;
    }

    @Override
    public String invoke() {
        Value value = run.execute();

        if (!initialized) {
            integerMode = value.fitsInBigInteger();

            if (integerMode) {
                expectedInteger = value.asBigInteger();
                expectedText = expectedInteger.toString();
            } else {
                expectedText = value.toString();
            }

            initialized = true;
            return expectedText;
        }

        if (integerMode) {
            if (!value.fitsInBigInteger()) {
                throw new IllegalStateException(
                        "benchmark result drift: expected an Integer");
            }

            BigInteger actual = value.asBigInteger();

            if (!expectedInteger.equals(actual)) {
                throw new IllegalStateException(
                        "benchmark result drift: expected "
                                + expectedInteger
                                + ", got "
                                + actual);
            }
        } else {
            String actual =
                    value.fitsInBigInteger()
                            ? value.asBigInteger().toString()
                            : value.toString();

            if (!expectedText.equals(actual)) {
                throw new IllegalStateException(
                        "benchmark result drift: expected "
                                + expectedText
                                + ", got "
                                + actual);
            }
        }

        return expectedText;
    }
}
