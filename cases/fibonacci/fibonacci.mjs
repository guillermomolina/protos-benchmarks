/*
 * Copyright (c) 2026 Guillermo Adrián Molina
 * Licensed under the Adaptive Public License 1.0.
 */

function fibonacci(n) {
    let result = n;

    if (n >= 2) {
        result = fibonacci(n - 1) + fibonacci(n - 2);
    }

    return result;
}

function run() {
    return fibonacci(20);
}

globalThis.truffleRun = run;
