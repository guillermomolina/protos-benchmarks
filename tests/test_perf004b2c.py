# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN
# THE LICENSE. A COPY OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED
# "LICENSE.TXT" ACCOMPANYING THE CONTENTS OF THIS FILE.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    return json.loads(
        (ROOT / "config/perf004b2c.json").read_text(encoding="utf-8")
    )


def test_contract():
    cfg = load()

    assert cfg["slice"] == "PERF004-B2-C"
    assert cfg["operation_count"] == 10000
    assert cfg["warmup_iterations"] == 20
    assert cfg["steady_iterations"] == 50
    assert len(cfg["controls"]) == 4
    assert cfg["diagnostic_claim"] is False


def test_controls_are_exactly_one_operation_replacement():
    cfg = load()

    expected = {
        "micro/slot-read": (
            "sink = holder.value",
            "sink = 42",
        ),
        "micro/closure-call": (
            "sink = identity(42)",
            "sink = 42",
        ),
        "micro/method-call": (
            "sink = receiver.identity(42)",
            "sink = 42",
        ),
        "runtime/monomorphic-dispatch": (
            "sink = receiver.run()",
            "sink = 42",
        ),
    }

    for item in cfg["controls"]:
        assert (item["replace"], item["with"]) == expected[item["id"]]
