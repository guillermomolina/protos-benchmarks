# Copyright (c) 2026 Guillermo Adrián Molina
# Licensed under the Adaptive Public License 1.0.

def factorial(n):
    if n <= 1:
        return 1

    return n * factorial(n - 1)

def run():
    return factorial(20)

truffleRun = run
