/*
 * Copyright (c) 2026 Guillermo Adrián Molina
 * Licensed under the Adaptive Public License 1.0.
 */

function factorial(n) {
    if (n <= 1n) {
        return 1n;
    }

    return n * factorial(n - 1n);
}

function run() {
    return factorial(20n);
}

globalThis.truffleRun = run;
