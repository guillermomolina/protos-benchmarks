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

from runner import perf004b2


def test_b2a_contract():
    cfg = perf004b2.validate()
    assert cfg["slice"] == "PERF004-B2-A"
    assert cfg["comparison"]["operation_counts"] == [100, 1000, 10000]
    assert len(cfg["workloads"]) == 4


def test_only_repeat_count_is_declared_variant():
    cfg = perf004b2.load()
    assert cfg["comparison"]["variant_transform"] == (
        "replace exactly one repeat(10000, occurrence with repeat(N,)"
    )
