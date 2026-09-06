# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
# THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
# OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
# THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
# FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.


import importlib.util
from pathlib import Path
import subprocess
import sys
import time

def last_nonempty(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""

def load_run(path):
    spec = importlib.util.spec_from_file_location("perf001e_workload", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise RuntimeError("workload has no run()")
    return module.run

def startup(path, expected, samples):
    for i in range(1, samples + 1):
        start = time.perf_counter_ns()
        completed = subprocess.run(
            [sys.executable, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        elapsed = time.perf_counter_ns() - start
        actual = last_nonempty(completed.stdout)
        if completed.returncode != 0 or actual != expected:
            raise RuntimeError(f"startup failed rc={completed.returncode} expected={expected} actual={actual}")
        print(f"STARTUP\t{i}\t{elapsed}\t{actual}")

def execution(path, expected, warmup, steady):
    run = load_run(path)
    for i in range(1, warmup + steady + 1):
        start = time.perf_counter_ns()
        result = run()
        elapsed = time.perf_counter_ns() - start
        actual = str(result)
        if actual != expected:
            raise RuntimeError(f"result mismatch expected={expected} actual={actual}")
        if i <= warmup:
            print(f"WARMUP\t{i}\t{elapsed}\t{actual}")
        else:
            print(f"STEADY\t{i-warmup}\t{elapsed}\t{actual}")

if len(sys.argv) < 2:
    raise SystemExit("usage: timing_driver.py startup|execution ...")
mode = sys.argv[1]
if mode == "startup" and len(sys.argv) == 5:
    startup(sys.argv[2], sys.argv[3], int(sys.argv[4]))
elif mode == "execution" and len(sys.argv) == 6:
    execution(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
else:
    raise SystemExit("invalid arguments")
