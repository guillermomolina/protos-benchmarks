#!/usr/bin/env python3
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

from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: apply_boundary.py <protos-root>")

root = Path(sys.argv[1])
path = root / "src/main/java/com/guillermomolina/protos/execution/ProtosClosureInvoker.java"
text = path.read_text(encoding="utf-8")

signature = """    public static Object invoke(
            ProtosClosureValue closure,
            List<?> supplied,
            ProtosActivation caller) {"""
annotation = "    @com.oracle.truffle.api.CompilerDirectives.TruffleBoundary\n"

if annotation + signature in text:
    raise SystemExit("BOUNDARY_PATCH_PRECONDITION: annotation already present at target")
if text.count(signature) != 1:
    raise SystemExit(
        "BOUNDARY_PATCH_PRECONDITION: expected exactly one three-argument invoke signature"
    )

path.write_text(text.replace(signature, annotation + signature, 1), encoding="utf-8")
check = path.read_text(encoding="utf-8")
if check.count(annotation + signature) != 1:
    raise SystemExit("BOUNDARY_PATCH_VERIFY: FAIL")

print("BOUNDARY_PATCH_VERIFY: PASS")
print("BOUNDARY_TARGET=ProtosClosureInvoker.invoke(ProtosClosureValue,List,ProtosActivation)")
