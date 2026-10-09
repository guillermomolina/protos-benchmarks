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

"""Generic compiled-graph evidence logic (truffle/graph_evidence.py)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "truffle"))

import graph_evidence as ge  # noqa: E402

POLICY = json.loads((ROOT / "truffle" / "measure" / "graphs.json").read_text())
FW = "org.graalvm.polyglot.Value<InteropBoundFunction>.execute"
JS_SRC = "/w/truffle/workloads/primitive-closure-call/primitive-closure-call.mjs"

# Verbatim GraalVM 25.4.4.1.1 records (PERF032-F discovery run, GraalPy label
# with spaces and the `opt inval.` verb).
REAL = """\
[engine] Inline start <bytecode run at 2cbc655a>                                  |Frequency     1.00|Recursion Depth      0|IR Nodes    163|Graph Size     -1|Truffle Callees      0|Explore/inline ratio     1.00|Depth      0|Forced false
[engine] Inlined        <bytecode run.<locals>.identity at 795e9a6f>              |Frequency     1.00|Recursion Depth      0|IR Nodes     59|Graph Size     -1|Truffle Callees      0|Explore/inline ratio      NaN|Depth      1|Forced false
[engine] Inline done  <bytecode run at 2cbc655a>                                  |Frequency     1.00|Recursion Depth      0|IR Nodes    163|Graph Size     -1|Truffle Callees      0|Explore/inline ratio     1.00|Depth      0|Forced false
[engine] Expansion tree for <bytecode run at 2cbc655a> after truffleTier:
Name                                                        Frequency | Count    Size  Cycles   Ifs Loops Invokes Allocs | Self Count  Size Cycles   Ifs Loops Invokes Allocs | IRNode ASTNode Lang:File:Line:Chars
<call-root>                                                      1.00 |    50      87      61     0     0       0      1 |         43    73     50     0     0       0      0 |      0
 FunctionRootNode                                                1.00 |     7      14      11     0     0       0      1 |          7    14     11     0     0       0      1 |    292       0 js:18:1033-1114

[engine] opt done   engine=1  id=466   <bytecode run at 2cbc655a>                         |Tier 2|Time    21(  16+5   )ms|AST    4|Inlined   1Y   0N|IR     50/    69|CodeSize     318|Addr 0x7fef66408c00|CompId 5115   |UTC 2026-10-07T16:28:26.204|Src n/a
[engine] opt inval. engine=1  id=85    <bytecode ModuleSpec.parent at 742838a1>                                                                                                                                          |UTC 2026-10-07T16:28:25.000|Src n/a
"""


def inline(label, decisions, depth0=0):
    head = f"|Frequency     1.00|Depth      {depth0}|Forced false"
    lines = [f"[engine] Inline start {label}    {head}"]
    for verb, callee, depth in decisions:
        lines.append(f"[engine] {verb}        {callee}    |Frequency     1.00|Depth      {depth}|Forced false")
    lines.append(f"[engine] Inline done  {label}    {head}")
    return lines


def expansion(label, count):
    return [
        f"[engine] Expansion tree for {label} after truffleTier:",
        "Name    Frequency | Count    Size  Cycles   Ifs Loops Invokes Allocs | Self Count  Size Cycles   Ifs Loops Invokes Allocs | IRNode ASTNode Lang:File:Line:Chars ",
        f"<call-root>    1.00 |   {count}  1  1  0  0  0  0 |   {count}  1  1  0  0  0  0 |      0     ",
        "",
    ]


def done(label, target, tier, comp_id, ir, src="n/a"):
    return (
        f"[engine] opt done   engine=1  id={target}   {label}   |Tier {tier}|Time    1(  1+0  )ms|AST    4"
        f"|Inlined   0Y   0N|IR    {ir}/   99|CodeSize     1|Addr 0x1|CompId {comp_id}   |UTC 2026-10-07T00:00:00.000|Src {src}"
    )


def compile_(label, target, tier, comp_id, ir, decisions=(), src="n/a"):
    return [*inline(label, decisions), *expansion(label, ir), done(label, target, tier, comp_id, ir, src)]


def js_trace(run_tier2_edge="Inlined", invalidate_run=False, run_src=JS_SRC + ":18 0x1"):
    lines = [
        *compile_(FW, 212, 1, 2463, 276, [("Cutoff", "run", 1)]),
        *compile_("run", 259, 1, 2531, 125, [("Cutoff", "identity", 1)], src=run_src),
        *compile_("identity", 260, 1, 2566, 73, src=JS_SRC + ":19 0x1"),
        *compile_(FW, 212, 2, 2630, 184, [("Inlined", "run", 1), ("Inlined", "identity", 2)]),
        *compile_("run", 259, 2, 2658, 13, [(run_tier2_edge, "identity", 1)], src=run_src),
        *compile_("identity", 260, 2, 2668, 15, src=JS_SRC + ":19 0x1"),
    ]
    if invalidate_run:
        lines.append("[engine] opt deopt  engine=1  id=259   run   |Invalidated  true|   |UTC x|Src n/a|Reason test")
    return "\n".join(lines) + "\n"


def resolve(text, language="js", source=JS_SRC):
    return ge.resolve_units(ge.parse_trace(text), POLICY, POLICY["languages"][language], source)


class TraceParsingTest(unittest.TestCase):
    def test_real_records_with_spaces_and_inval(self):
        parsed = ge.parse_trace(REAL)
        self.assertEqual([], parsed["unknown_lifecycle_events"])
        (compilation,) = parsed["compilations"]
        self.assertEqual("<bytecode run at 2cbc655a>", compilation["label"])
        self.assertEqual((2, 5115, "1:466"), (compilation["tier"], compilation["comp_id"], compilation["target"]))
        self.assertEqual((50, 69), (compilation["ir_after_truffle_tier"], compilation["ir_final"]))
        self.assertEqual(
            [{"verb": "Inlined", "label": "<bytecode run.<locals>.identity at 795e9a6f>", "depth": 1}],
            compilation["inline_tree"],
        )
        root = compilation["expansion"]["root"]
        self.assertEqual((50, 0, 0, 1), (root["count"], root["ifs"], root["invokes"], root["allocs"]))
        self.assertEqual("js:18:1033-1114", compilation["expansion"]["rows"][1]["location"])
        (invalidation,) = parsed["invalidations"]
        self.assertEqual("<bytecode ModuleSpec.parent at 742838a1>", invalidation["label"])

    def test_option_rejection_is_reported(self):
        parsed = ge.parse_trace("Could not find option with name compiler.Bogus.\n")
        self.assertTrue(parsed["option_rejections"])
        self.assertIn("OPTION_REJECTED", ge.assess_run(parsed, None, 2)["problems"])

    def test_unterminated_inlining_trace_fails_closed(self):
        text = "\n".join([*inline("run", [])[:-1], done("run", 1, 1, 1, 5)]) + "\n"
        with self.assertRaises(ge.EvidenceError) as caught:
            ge.parse_trace(text)
        self.assertEqual("INLINING_TRACE_UNTERMINATED", caught.exception.reason)


class LifecycleTest(unittest.TestCase):
    def test_superseded_tier_versions_are_not_final(self):
        targets = ge.target_lifecycles(ge.parse_trace(js_trace()))
        run = targets["1:259"]
        self.assertEqual(2658, run["final"]["comp_id"])
        self.assertEqual([2531], run["superseded_comp_ids"])
        self.assertFalse(run["invalidated_after_final"])

    def test_invalidation_after_final_marks_unit_unstable(self):
        parsed = ge.parse_trace(js_trace(invalidate_run=True))
        resolution = ge.resolve_units(parsed, POLICY, POLICY["languages"]["js"], JS_SRC)
        assessment = ge.assess_run(parsed, resolution, 2)
        self.assertEqual(ge.NOT_STABLE, assessment["status"])
        self.assertIn("UNIT_INVALIDATED_AFTER_FINAL", assessment["problems"])


class UnitAccountingTest(unittest.TestCase):
    def test_inlined_callee_is_not_added(self):
        resolution = resolve(js_trace())
        self.assertEqual(["run"], [u["label"] for u in resolution["units"]])
        self.assertEqual(2658, resolution["units"][0]["comp_id"])
        self.assertEqual(["identity"], resolution["units"][0]["inlined"])
        self.assertEqual(["identity"], resolution["unattributed_language_targets"])
        self.assertEqual([FW], resolution["framework_targets"])

    def test_cutoff_callee_is_a_separate_unit_counted_once(self):
        resolution = resolve(js_trace(run_tier2_edge="Cutoff"))
        self.assertEqual(["primary", "additional"], [u["role"] for u in resolution["units"]])
        self.assertEqual(["run", "identity"], [u["label"] for u in resolution["units"]])
        self.assertEqual(("run", "Cutoff"), (resolution["units"][1]["via"], resolution["units"][1]["edge"]))
        self.assertEqual(2668, resolution["units"][1]["comp_id"])

    def test_expanded_callee_is_counted_separately(self):
        resolution = resolve(js_trace(run_tier2_edge="Expanded"))

        self.assertEqual(
            ["run", "identity"],
            [unit["label"] for unit in resolution["units"]],
        )
        self.assertEqual("Expanded", resolution["units"][1]["edge"])
        self.assertEqual([], resolution["unattributed_language_targets"])

    def test_expanded_recursive_callee_is_counted_once(self):
        sample = "\n".join([
            *compile_(
                FW, 1, 2, 10, 40,
                [("Inlined", "run", 1),
                 ("Expanded", "recursive", 2)],
            ),
            *compile_(
                "run", 2, 2, 11, 393,
                [("Expanded", "recursive", 1)],
                src=JS_SRC + ":1",
            ),
            *compile_(
                "recursive", 3, 2, 12, 200,
                [("Cutoff", "recursive", 1)],
                src=JS_SRC + ":2",
            ),
        ]) + "\n"

        resolution = resolve(sample)

        self.assertEqual(
            ["primary", "additional"],
            [unit["role"] for unit in resolution["units"]],
        )
        self.assertEqual(
            ["run", "recursive"],
            [unit["label"] for unit in resolution["units"]],
        )
        self.assertEqual([], resolution["unattributed_language_targets"])
        self.assertEqual([], resolution["uncompiled_callees"])

    def test_uncompiled_cutoff_callee_is_not_stable(self):
        text = "\n".join([
            *compile_(FW, 1, 2, 10, 50, [("Cutoff", "run", 1)]),
            *compile_("run", 2, 2, 11, 20, [("Cutoff", "helper", 1)], src=JS_SRC + ":1"),
        ]) + "\n"
        parsed = ge.parse_trace(text)
        resolution = ge.resolve_units(parsed, POLICY, POLICY["languages"]["js"], JS_SRC)
        self.assertEqual(["helper"], resolution["uncompiled_callees"])
        self.assertIn("UNCOMPILED_CALLEE", ge.assess_run(parsed, resolution, 2)["problems"])

    def test_setup_roots_are_never_counted(self):
        python_fw = "org.graalvm.polyglot.Value<PFunction>.execute"
        run = "<bytecode run at 2cbc655a>"
        text = "\n".join([
            *compile_("<bytecode ModuleSpec.parent at 742838a1>", 85, 2, 4553, 197),
            *compile_(python_fw, 419, 2, 5100, 297, [("Inlined", run, 1)]),
            *compile_(run, 466, 2, 5115, 50),
        ]) + "\n"
        resolution = resolve(text, "python", "/w/x.py")
        self.assertEqual([run], [u["label"] for u in resolution["units"]])
        self.assertEqual(["<bytecode ModuleSpec.parent at 742838a1>"], resolution["unattributed_language_targets"])

    def test_framework_callee_is_never_a_unit(self):
        text = "\n".join([
            *compile_(FW, 1, 2, 10, 50, [("Cutoff", "run", 1)]),
            *compile_("run", 2, 2, 11, 20, [("Cutoff", FW, 1)], src=JS_SRC + ":1"),
        ]) + "\n"
        self.assertEqual(1, len(resolve(text)["units"]))


class RootMatchingTest(unittest.TestCase):
    def test_protos_primary_matches_root_identity(self):
        fw = "org.graalvm.polyglot.Value<ProtosHostExecutableClosure>.execute"
        root = "ProtosSemanticBytecodeRootNodeGen@5f250922"
        text = "\n".join([*compile_(fw, 81, 2, 1, 9, [("Inlined", root, 1)]), *compile_(root, 48, 2, 2, 8)]) + "\n"
        resolution = resolve(text, "protos", "/w/x.protos")
        self.assertEqual(root, resolution["primary_label"])
        self.assertEqual("ProtosSemanticBytecodeRootNodeGen@*", resolution["units"][0]["normalized_label"])

    def test_stable_protos_root_identity_is_accepted(self):
        fw = "org.graalvm.polyglot.Value<ProtosHostExecutableClosure>.execute"
        root = "protos-root:0123456789abcdef"
        text = "\n".join([*compile_(fw, 81, 2, 1, 9, [("Cutoff", root, 1)]), *compile_(root, 48, 2, 2, 8)]) + "\n"
        self.assertEqual(root, resolve(text, "protos", "/w/x.protos")["primary_label"])

    def test_missing_framework_entry(self):
        text = "\n".join(compile_("run", 2, 2, 11, 20, src=JS_SRC + ":1")) + "\n"
        with self.assertRaises(ge.EvidenceError) as caught:
            resolve(text)
        self.assertEqual("FRAMEWORK_ENTRY_NOT_COMPILED", caught.exception.reason)

    def test_ambiguous_entry(self):
        text = "\n".join([
            *compile_(FW, 1, 1, 10, 50, [("Cutoff", "run", 1)]),
            *compile_(FW, 1, 2, 12, 50, [("Cutoff", "other", 1)]),
        ]) + "\n"
        with self.assertRaises(ge.EvidenceError) as caught:
            resolve(text)
        self.assertEqual("PRIMARY_ENTRY_AMBIGUOUS", caught.exception.reason)

    def test_identity_mismatch_and_source_mismatch(self):
        text = "\n".join([*compile_(FW, 1, 2, 10, 50, [("Cutoff", "main", 1)]), *compile_("main", 2, 2, 11, 9)]) + "\n"
        with self.assertRaises(ge.EvidenceError) as caught:
            resolve(text)
        self.assertEqual("PRIMARY_IDENTITY_MISMATCH", caught.exception.reason)
        with self.assertRaises(ge.EvidenceError) as caught:
            resolve(js_trace(run_src="/elsewhere/other.mjs:3 0x1"))
        self.assertEqual("PRIMARY_SOURCE_MISMATCH", caught.exception.reason)

    def test_missing_inlining_trace(self):
        text = "\n".join([*expansion(FW, 5), done(FW, 1, 2, 10, 5)]) + "\n"
        with self.assertRaises(ge.EvidenceError) as caught:
            resolve(text)
        self.assertEqual("INLINING_TRACE_MISSING", caught.exception.reason)

    def test_new_language_needs_only_policy(self):
        policy = {**POLICY, "framework_label_patterns": [r"^entry$"]}
        text = "\n".join([*compile_("entry", 1, 2, 1, 5, [("Cutoff", "fn main", 1)]), *compile_("fn main", 2, 2, 2, 7)]) + "\n"
        resolution = ge.resolve_units(
            ge.parse_trace(text), policy, {"primary_label_pattern": "^fn main$"}, "/x.lang"
        )
        self.assertEqual("fn main", resolution["primary_label"])


class StabilizationTest(unittest.TestCase):
    def run_(self, budget, text):
        parsed = ge.parse_trace(text)
        resolution = ge.resolve_units(parsed, POLICY, POLICY["languages"]["js"], JS_SRC)
        return {"budget": budget, "assessment": ge.assess_run(parsed, resolution, 2)}

    def test_first_identical_stable_pair(self):
        tier1_only = "\n".join([
            *compile_(FW, 212, 1, 1, 276, [("Cutoff", "run", 1)]),
            *compile_("run", 259, 1, 2, 125, src=JS_SRC + ":18"),
        ]) + "\n"
        runs = [self.run_(1000, tier1_only), self.run_(4000, js_trace()), self.run_(16000, js_trace()),
                self.run_(64000, js_trace())]
        self.assertEqual(ge.NOT_STABLE, runs[0]["assessment"]["status"])
        self.assertEqual({"status": ge.STABLE, "pair": [4000, 16000]}, ge.stabilize(runs))

    def test_changing_structure_is_not_stable(self):
        runs = [self.run_(1000, js_trace()), self.run_(4000, js_trace(run_tier2_edge="Cutoff"))]
        self.assertEqual(ge.GRAPH_NOT_STABLE, ge.stabilize(runs)["status"])


def graph(name, classes, graph_type="StructuredGraph"):
    return {"name": name, "graph_type": graph_type,
            "nodes": [{"id": i, "properties": {"class": c}} for i, c in enumerate(classes)]}


class PhaseSelectionTest(unittest.TestCase):
    DOC = {
        "name": "TruffleHotSpotCompilation-1[run]",
        "groups": [{
            "name": "run",
            "graphs": [
                graph("0: Before TruffleTier", ["StartNode"] * 9),
                graph("1: After TruffleTier", ["StartNode", "jdk.graal.compiler.nodes.InvokeNode", "IfNode",
                                               "NewInstanceNode", "FixedGuardNode", "LoadFieldNode",
                                               "LoopBeginNode", "ReturnNode"]),
                graph("2: After PartialEscape", ["StartNode"]),
            ],
        }, {
            "name": "AST",
            "elements": [graph("0: After TruffleTier", ["ASTNode"] * 4, graph_type="defaultType")],
        }],
    }

    def test_selects_exactly_after_truffle_tier(self):
        selected = ge.select_unit_graph(self.DOC, "After TruffleTier")
        self.assertEqual("1: After TruffleTier", selected["graph_name"])
        self.assertEqual(["TruffleHotSpotCompilation-1[run]", "run"], selected["group_path"])
        self.assertEqual(8, selected["node_count"])
        self.assertTrue(selected["histogram_available"])
        for family in ge.FAMILIES:
            self.assertEqual(1, selected[family], family)
        self.assertEqual(1, selected["node_class_histogram"]["InvokeNode"])
        self.assertEqual("StructuredGraph", selected["graph_type"])

    def test_real_25_4_layout_and_boxing_allocation(self):
        # Layout of IgvUtility filter output for TruffleHotSpotCompilation-2574[run].
        node = lambda i, cls: (str(i), {"id": i, "name": "n", "class": "jdk.graal.compiler.nodes." + cls})
        doc = {"elements": [{"name": "TruffleIR.Tier2.run()", "elements": [
            {"id": 0, "name": "0: After PE Tier", "graph_type": "StructuredGraph", "nodes": dict([node(0, "StartNode")])},
            {"name": "Call Tree", "elements": [{"name": "0: Before Inline", "graph_type": "defaultType", "nodes": {}}]},
            {"id": 1, "name": "1: After TruffleTier", "graph_type": "StructuredGraph", "nodes": dict([
                node(0, "StartNode"), node(1, "extended.BoxNode$AllocatingBoxNode"),
                node(2, "java.LoadIndexedNode"), node(3, "FrameState"), node(4, "ReturnNode")])},
            {"name": "AST", "elements": [{"name": "0: After TruffleTier", "graph_type": "defaultType",
                                          "nodes": {"0": {"id": 0}}}]},
        ]}]}
        selected = ge.select_unit_graph(doc, "After TruffleTier")
        self.assertEqual(("1: After TruffleTier", 5), (selected["graph_name"], selected["node_count"]))
        self.assertEqual((1, 1), (selected["allocations"], selected["loads"]))
        self.assertEqual(["TruffleIR.Tier2.run()"], selected["group_path"])

    def test_missing_and_ambiguous_phase(self):
        missing = {"graphs": [graph("Before TruffleTier", ["A"])]}
        with self.assertRaises(ge.EvidenceError) as caught:
            ge.select_unit_graph(missing, "After TruffleTier")
        self.assertEqual("PHASE_MISSING", caught.exception.reason)
        twice = {"graphs": [graph("After TruffleTier", ["A"]), graph("3: After TruffleTier", ["A"])]}
        only_ast = {"graphs": [graph("0: After TruffleTier", ["A"], graph_type="defaultType"),
                               graph("0: After PE Tier", ["A"])]}
        with self.assertRaises(ge.EvidenceError) as caught:
            ge.select_unit_graph(only_ast, "After TruffleTier")
        self.assertEqual("PHASE_MISSING", caught.exception.reason)
        with self.assertRaises(ge.EvidenceError) as caught:
            ge.select_unit_graph(twice, "After TruffleTier")
        self.assertEqual("PHASE_AMBIGUOUS", caught.exception.reason)
        with self.assertRaises(ge.EvidenceError) as caught:
            ge.select_unit_graph({"name": "empty"}, "After TruffleTier")
        self.assertEqual("BGV_NO_GRAPHS", caught.exception.reason)

    def test_unknown_node_class_is_flagged(self):
        metrics = ge.graph_metrics({"nodes": [{"id": 1}]})
        self.assertFalse(metrics["histogram_available"])

    def test_dump_matching_by_comp_id(self):
        names = ["TruffleHotSpotCompilation-2658[run].bgv", "TruffleHotSpotCompilation-26580[x].bgv"]
        self.assertEqual(["TruffleHotSpotCompilation-2658[run].bgv"], ge.dumps_for(2658, names))
        self.assertEqual([], ge.dumps_for(1, names))


def unit(role, label, classes):
    return {"role": role, "label": label, "via": "run" if role != "primary" else None, "edge": "Cutoff",
            "graph": ge.graph_metrics({"nodes": [{"class": c} for c in classes]})}


def summary(*units):
    return ge.case_summary(list(units))


class ComparisonTest(unittest.TestCase):
    def test_multi_unit_total(self):
        s = summary(unit("primary", "run", ["A"] * 10), unit("additional", "identity", ["A"] * 5))
        self.assertEqual((15, 10, 2), (s["relevant_graph_nodes_total_after_truffle_tier"],
                                       s["primary_guest_graph_nodes"], s["graph_count"]))
        self.assertEqual("identity", s["additional_language_owned_compiled_units"][0]["label"])

    def test_converged(self):
        rung = ge.compare_rung("w", "m", {
            "js": summary(unit("primary", "run", ["A"] * 10)),
            "python": summary(unit("primary", "run", ["A"] * 14)),
            "protos": summary(unit("primary", "r", ["A"] * 17)),
        })
        self.assertEqual((ge.PEER_CONVERGED, 4, [10, 14]), (rung["peer_reference"], rung["peer_spread"], rung["peer_band"]))
        self.assertEqual(ge.STRUCTURALLY_CONVERGED, rung["protos_status"])
        self.assertEqual((ge.COMPARISON_PERFORMED, ge.STABLE), (rung["peer_node_comparison"], rung["protos_stabilization"]))

    def test_excess_signals(self):
        rung = ge.compare_rung("w", "m", {
            "js": summary(unit("primary", "run", ["A"] * 10)),
            "python": summary(unit("primary", "run", ["A"] * 14)),
            "protos": summary(unit("primary", "r", ["A"] * 10 + ["NewInstanceNode"]),
                              unit("additional", "h", ["A"] * 8)),
        })
        self.assertEqual(ge.STRUCTURAL_EXCESS, rung["protos_status"])
        self.assertEqual(
            ["ADDITIONAL_PROTOS_COMPILED_UNIT", "NODE_EXCESS_BEYOND_PEER_SPREAD", "PROTOS_ONLY_ALLOCATIONS"],
            rung["protos_signals"],
        )
        self.assertEqual({"workload": "w", "mechanism": "m", "protos_status": ge.STRUCTURAL_EXCESS,
                          "signals": rung["protos_signals"]}, ge.first_divergent([rung]))

    def test_peer_disagreement_is_unresolved(self):
        rung = ge.compare_rung("w", "m", {
            "js": summary(unit("primary", "run", ["A"] * 10)),
            "python": summary(unit("primary", "run", ["A"] * 10), unit("additional", "h", ["A"])),
            "protos": summary(unit("primary", "r", ["A"] * 999)),
        })
        self.assertEqual(ge.PEER_UNRESOLVED, rung["peer_reference"])
        self.assertIn("PEER_TOPOLOGY_DISAGREES", rung["peer_reasons"])
        self.assertEqual(ge.NOT_EVALUATED, rung["protos_status"])
        self.assertIsNone(ge.first_divergent([rung]))

    def test_unstable_protos_graph_is_reported_and_divergent(self):
        peers = {"js": summary(unit("primary", "run", ["A"] * 10)),
                 "python": summary(unit("primary", "run", ["A"] * 12))}
        fw = "org.graalvm.polyglot.Value<ProtosHostExecutableClosure>.execute"
        root = "ProtosSemanticBytecodeRootNodeGen@29e0ba54"
        lines = compile_(fw, 81, 1, 1, 9, [("Cutoff", root, 1)])
        for comp_id in range(2, 5):
            lines += compile_(root, 47, 1, comp_id, 8)
            lines.append(f"[engine] opt inval. engine=1  id=47    {root}     |UTC x|Src n/a")
        lines.append(f"[engine] opt failed engine=1  id=47    {root}   |Tier 1|Time    10(  10+0   )ms"
                     "|Reason: Maximum compilation count 100 reached.|UTC x|Src n/a")
        lines += compile_(fw, 81, 2, 9, 9, [("BailedOut", root, 1)])
        evidence = ge.instability_evidence(ge.parse_trace("\n".join(lines) + "\n"), POLICY, root)
        self.assertEqual((3, 3, "BailedOut", True), (evidence["primary_compilations"],
                         evidence["primary_invalidation_events"], evidence["final_compilation_state"],
                         evidence["maximum_compilation_count_reached"]))
        problems = ["UNIT_INVALIDATED_AFTER_FINAL", "UNIT_NOT_AT_FINAL_TIER", "UNIT_RECOMPILATION_FAILED"]
        rung = ge.compare_rung("w", "m", {**peers, "protos": None}, {"problems": problems, "evidence": evidence})
        self.assertEqual(
            (ge.PEER_CONVERGED, ge.GRAPH_NOT_STABLE, ge.DIVERGED_BEFORE_GRAPH_PARITY, "N/A", ge.COMPARISON_SKIPPED, "BailedOut"),
            (rung["peer_reference"], rung["protos_stabilization"], rung["protos_status"], rung["protos_node_total"],
             rung["peer_node_comparison"], rung["final_compilation_state"]),
        )
        self.assertEqual(problems + ["FINAL_COMPILATION_STATE_BAILED_OUT", "MAXIMUM_COMPILATION_COUNT_REACHED"],
                         rung["protos_signals"])
        self.assertIsNone(rung["secondary_deltas_vs_peer_max"])
        self.assertEqual(ge.DIVERGED_BEFORE_GRAPH_PARITY, ge.first_divergent([rung])["protos_status"])

    def test_missing_peer_evidence(self):
        rung = ge.compare_rung("w", "m", {"js": None, "python": None, "protos": None})
        self.assertEqual(["PEER_EVIDENCE_MISSING"], rung["peer_reasons"])


if __name__ == "__main__":
    unittest.main()
