/*
 * Copyright (c) 2026 Guillermo Adrián Molina
 * Licensed under the Adaptive Public License 1.0.
 */

function factorial(n) {
    let result = 1n;

    if (n > 1n) {
        result = n * factorial(n - 1n);
    }

    return result;
}

function run() {
    return factorial(20n);
}

globalThis.truffleRun = run;
