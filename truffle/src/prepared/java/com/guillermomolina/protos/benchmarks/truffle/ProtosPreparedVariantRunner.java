/*
 * THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
 * ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
 * See LICENSE.TXT at the repository root.
 */
package com.guillermomolina.protos.benchmarks.truffle;

import com.guillermomolina.protos.execution.ProtosStandaloneHostedSession;

/**
 * Exact-revision Protos runner using the prepared top-level API.
 *
 * <p>This source root is not part of the Maven build: the common pinned
 * Protos artifact predates {@code prepareTopLevel}. jvm_protos_ab.py compiles
 * it only against PERF025-B-and-later variant classpaths. Preparation happens
 * before {@link ProtosJvmVariantRunner#measure} is entered, so the cold
 * observation is the first {@code prepared.invoke()} alone.
 */
public final class ProtosPreparedVariantRunner {
    private ProtosPreparedVariantRunner() {}

    public static void main(String[] args) throws Exception {
        ProtosJvmVariantRunner.Arguments arguments =
                ProtosJvmVariantRunner.Arguments.parse(args);

        long setupStart = System.nanoTime();

        try (ProtosStandaloneHostedSession session =
                ProtosJvmVariantRunner.openSession(arguments)) {
            long setupNs = System.nanoTime() - setupStart;

            long prepareStart = System.nanoTime();
            ProtosStandaloneHostedSession.PreparedTopLevel prepared =
                    session.prepareTopLevel("run");
            long prepareNs = System.nanoTime() - prepareStart;

            System.out.println("prepare_ns=" + prepareNs);

            ProtosJvmVariantRunner.measure(
                    "prepared",
                    arguments,
                    setupNs,
                    () -> prepared.invoke());
        }
    }
}
