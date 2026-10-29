# Copyright (c) 2026 Guillermo Adrián Molina
# Licensed under the Adaptive Public License 1.0.

def factorial(n):
    result = 1

    if n > 1:
        result = n * factorial(n - 1)

    return result

def run():
    return factorial(20)

truffleRun = run
