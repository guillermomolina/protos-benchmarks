# Copyright (c) 2026 Guillermo Adrián Molina
# Licensed under the Adaptive Public License 1.0.

def fibonacci(n):
    if n < 2:
        return n

    return fibonacci(n - 1) + fibonacci(n - 2)

def run():
    return fibonacci(20)

truffleRun = run
