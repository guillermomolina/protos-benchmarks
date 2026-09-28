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
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runner/upstream003_platform_comparison.py"
spec = importlib.util.spec_from_file_location("upstream003_platform_comparison", MODULE_PATH)
upstream003 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(upstream003)


class Upstream003ContractTest(unittest.TestCase):
    def test_static_contract(self):
        cfg = upstream003.validate()
        self.assertEqual("UPSTREAM003-B", cfg["slice"])
        self.assertEqual(
            "44690b1fc8c9aed023600c6d5731f969c4507e27",
            cfg["protos"]["revision"],
        )
        self.assertEqual("0.3.106-SNAPSHOT", cfg["protos"]["version"])
        self.assertFalse(cfg["timing_comparison"]["automatic_adoption_classification"])
        self.assertFalse(cfg["historical_evidence_used_as_side_a"])

    def test_signed_delta(self):
        self.assertEqual(
            {"absolute_delta_ns": 25.0, "relative_delta_percent": 25.0},
            upstream003.signed_delta(100.0, 125.0),
        )

    def test_overlay_diff_scope_parser(self):
        text = (
            "diff --git a/pom.xml b/pom.xml\n"
            "diff --git a/toolchain.json b/toolchain.json\n"
            "diff --git a/dist/build_portable.py b/dist/build_portable.py\n"
        )
        self.assertEqual(
            ("dist/build_portable.py", "pom.xml", "toolchain.json"),
            upstream003.parse_overlay_diff_paths(text),
        )

    def test_trace_parser_distinguishes_unavailable_from_absent(self):
        parsed = upstream003.trace_summary("[engine] opt done\n", "micro/closure-call.protos")
        self.assertEqual(1, parsed["successful_compilations"])
        self.assertEqual("UNAVAILABLE_FROM_TRACE", parsed["guest_call_frequency"]["status"])
        self.assertEqual(
            "UNAVAILABLE_FROM_TRACE",
            parsed["direct_vs_indirect_call_survival"]["status"],
        )

    def test_config_has_four_independent_workload_probes(self):
        cfg = json.loads(
            (ROOT / "config/upstream003-platform-comparison.json").read_text(encoding="utf-8")
        )
        self.assertEqual(4, len(cfg["controls"]))
        self.assertEqual(
            {
                "micro/slot-read",
                "micro/closure-call",
                "micro/method-call",
                "runtime/monomorphic-dispatch",
            },
            {item["id"] for item in cfg["controls"]},
        )


if __name__ == "__main__":
    unittest.main()
