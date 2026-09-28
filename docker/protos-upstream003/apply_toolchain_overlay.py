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

"""Apply the UPSTREAM003-B build-only Graal/Truffle 25.4 overlay.

The script is intentionally exact-string and exact-path based.  It runs only inside the
UPSTREAM003 Docker build, after the pinned Protos revision has been checked out.  It must never be
used as a Protos product patch.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

AUTHORIZED_PATHS = ("pom.xml", "toolchain.json", "dist/build_portable.py")

REPLACEMENTS = {
    "pom.xml": (
        (
            "<graalvm.version>25.3.4.1</graalvm.version>",
            "<graalvm.version>25.4.4.1.1</graalvm.version>",
        ),
    ),
    "toolchain.json": (
        ('"release": "25.3.4.1"', '"release": "25.4.4.1.1"'),
        ('"container_channel": "25i3"', '"container_channel": "25i4"'),
        (
            '"container_image": "ghcr.io/graalvm/graalvm-community:25i3-25.0.4.1-ol10-20260825"',
            '"container_image": "ghcr.io/graalvm/graalvm-community:25i4-ol10"',
        ),
        ('"version": "25.3.4.1"', '"version": "25.4.4.1.1"'),
    ),
    "dist/build_portable.py": (
        (
            'SUPPORTED_GRAALVM_RELEASE = "25.3.4.1"',
            'SUPPORTED_GRAALVM_RELEASE = "25.4.4.1.1"',
        ),
        (
            'EXPECTED_TRUFFLE_VERSION = "25.3.4.1"',
            'EXPECTED_TRUFFLE_VERSION = "25.4.4.1.1"',
        ),
    ),
}


def changed_paths() -> tuple[str, ...]:
    text = subprocess.run(
        ["git", "diff", "--name-only"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return tuple(sorted(line for line in text.splitlines() if line))


def main() -> None:
    if changed_paths():
        raise SystemExit("UPSTREAM003 overlay requires a clean checkout before application")

    for relative, replacements in REPLACEMENTS.items():
        path = Path(relative)
        text = path.read_text(encoding="utf-8")
        for old, new in replacements:
            count = text.count(old)
            if count != 1:
                raise SystemExit(
                    f"UPSTREAM003 overlay expected exactly one occurrence in {relative}: "
                    f"{old!r}; observed={count}"
                )
            text = text.replace(old, new, 1)
        path.write_text(text, encoding="utf-8")

    observed = changed_paths()
    expected = tuple(sorted(AUTHORIZED_PATHS))
    if observed != expected:
        raise SystemExit(
            f"UPSTREAM003 overlay scope mismatch: expected={expected!r} observed={observed!r}"
        )

    print("UPSTREAM003_B_TOOLCHAIN_OVERLAY=PASS")
    print("UPSTREAM003_B_TOOLCHAIN_OVERLAY_PATHS=" + ",".join(observed))


if __name__ == "__main__":
    main()
