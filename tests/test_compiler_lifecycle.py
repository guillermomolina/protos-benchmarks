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
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_runner(name):
    key = "pb_" + name
    module = sys.modules.get(key)
    if module is None:
        spec = importlib.util.spec_from_file_location(key, ROOT / "runner" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return module


trace = load_runner("compiler_trace")
lifecycle = load_runner("compiler_lifecycle")
fixtures = load_runner("perf010a_hot_root_fixtures")

REAL_LOG = (
    ROOT
    / "results/upstream003-platform-comparison/diagnostic/logs/micro__closure-call-platform_b.stderr.log"
)

# Verbatim records from the retained GraalVM 25.4.4.1.1 diagnostic log above.
REAL_DONE = (
    "[engine] opt done   engine=2  id=149   ProtosSemanticBytecodeRootNodeGen@4ae9cfc1         "
    "|Tier 1|Time   359( 335+24  )ms|AST    2|Inlined   0Y   0N|IR    150/   221|CodeSize    1037"
    "|Addr 0x7ff0c655ec00|CompId 2585   |UTC 2026-09-28T08:57:46.014|Src n/a"
)
REAL_DEOPT = (
    "[engine] opt deopt  engine=2  id=149   ProtosSemanticBytecodeRootNodeGen@4ae9cfc1         "
    "|Invalidated  true|" + " " * 108 + "|UTC 2026-09-28T08:57:49.124|Src n/a|Reason uncommon trap"
)
REAL_UNQUEUE = (
    "[engine] opt unque. engine=2  id=153   ProtosSemanticBytecodeRootNodeGen@52b56a3e         "
    "|Tier 1|Count/Thres      10000/      400|Queue: Size    4 Change  0  Load  1.00 Time     0us"
    + " " * 35
    + "|UTC 2026-09-28T08:57:50.199|Src n/a|Reason Stale compilation task"
)


def normalize(text, *, completed=True, phases=fixtures.PHASES):
    records = trace.split_records(text)
    return records, lifecycle.normalize_lifecycle(
        records, first_tier=1, final_tier=2, required_phases=phases, process_completed=completed
    )


def root(result, label):
    return result["roots"][result["label_index"][label][0]]


class TraceRecordTest(unittest.TestCase):
    def test_real_25_4_records_parse(self):
        done, deopt, unque = trace.split_records("\n".join((REAL_DONE, REAL_DEOPT, REAL_UNQUEUE)) + "\n")
        self.assertEqual(trace.OPT_DONE, done.kind)
        self.assertEqual((2, 149, 1, 2585), (done.fields["engine"], done.fields["id"], done.fields["tier"], done.fields["comp_id"]))
        self.assertEqual("ProtosSemanticBytecodeRootNodeGen@4ae9cfc1", done.fields["label"])
        self.assertEqual(trace.OPT_DEOPT, deopt.kind)
        self.assertIs(True, deopt.fields["invalidated"])
        self.assertEqual("uncommon trap", deopt.fields["reason"])
        self.assertEqual(trace.OPT_DEQUEUED, unque.kind)
        self.assertEqual("Stale compilation task", unque.fields["reason"])

    def test_multi_line_failure_and_detail_are_single_records(self):
        text = fixtures.LogBuilder().failed(7, fixtures.A, 1).text()
        kinds = [r.kind for r in trace.split_records(text) if r.kind in trace.LIFECYCLE_KINDS]
        self.assertEqual([trace.OPT_FAILED, trace.OPT_FAIL_DETAIL], kinds)
        failed = next(r for r in trace.split_records(text) if r.kind == trace.OPT_FAILED)
        self.assertGreater(len(failed.lines), 3)
        self.assertEqual("PERMANENT", trace.classify_failure(failed.raw))

    def test_failure_classification(self):
        self.assertEqual("PERMANENT", trace.classify_failure(fixtures.PERMANENT_REASON))
        self.assertEqual("TEMPORARY", trace.classify_failure(fixtures.TEMPORARY_REASON))
        self.assertEqual("ERROR", trace.classify_failure("java.lang.AssertionError: boom"))

    def test_unknown_and_unparseable_opt_records_are_never_dropped(self):
        records = trace.split_records("[engine] opt reprofile engine=2  id=9   R@1 |Tier 1\n[engine] opt ???\n")
        self.assertEqual([trace.OPT_UNKNOWN, trace.OPT_UNPARSED], [r.kind for r in records])

    def test_markers_perf_warnings_and_dump_lines(self):
        builder = fixtures.LogBuilder().mark("warmup").perf_warn(fixtures.A, "Map.put(Object, Object)", ["a.B.c(B.java:1)", "d.E.f(E.java:2)"]).dump(2585, fixtures.A)
        by_kind = {r.kind: r for r in trace.split_records(builder.text())}
        self.assertEqual("warmup", by_kind[trace.MARK].fields["phase"])
        warn = by_kind[trace.PERF_WARN]
        self.assertEqual(("Map.put(Object, Object)", "1149|MethodCallTarget"), (warn.fields["target"], warn.fields["node"]))
        self.assertEqual(["a.B.c(B.java:1)", "d.E.f(E.java:2)"], warn.fields["frames"])
        self.assertEqual((2585, fixtures.A), (by_kind[trace.DUMP_FILE].fields["comp_id"], by_kind[trace.DUMP_FILE].fields["label"]))

    def test_option_rejection_and_deprecation_detection(self):
        rejected = "Exception in thread main java.lang.IllegalArgumentException: Could not find option with name engine.Nope."
        self.assertEqual(1, len(trace.find_option_rejections("ok\n" + rejected)))
        self.assertEqual(1, len(trace.find_option_rejections("Option 'engine.X' is experimental and must be enabled with allowExperimentalOptions(...)")))
        warning = "[engine] WARNING: Option 'engine.TraceInlining' is deprecated: use compiler.TraceInlining."
        self.assertEqual([], trace.find_option_rejections(warning))
        self.assertEqual(["engine.TraceInlining"], trace.deprecated_options(trace.split_records(warning + "\n")))

    def test_inlining_records_parse(self):
        line = "[engine] Cutoff         ProtosSemanticBytecodeRootNodeGen@4fad94a7                |Frequency     0.04|Recursion Depth      0|IR Nodes      0|Graph Size      0|Depth      1|Forced false"
        (record,) = trace.split_records(line + "\n")
        self.assertEqual(trace.INLINE_DECISION, record.kind)
        self.assertEqual("0.04", record.fields["values"]["Frequency"])
        self.assertEqual("1", record.fields["values"]["Depth"])


class LifecycleScenarioTest(unittest.TestCase):
    def test_every_scenario_has_the_expected_lifecycle(self):
        for name, (body, expected) in fixtures.LIFECYCLE_SCENARIOS.items():
            with self.subTest(name):
                _, result = normalize(fixtures.run(body))
                actual = root(result, fixtures.A)
                for key, value in expected.items():
                    if key == "classes":
                        for flag, wanted in value.items():
                            self.assertIs(wanted, actual["classes"][flag], flag)
                    else:
                        self.assertEqual(value, actual[key], key)

    def test_raw_events_are_retained_in_order(self):
        text = fixtures.run(fixtures.LIFECYCLE_SCENARIOS["permanent_failure"][0])
        records, result = normalize(text)
        self.assertEqual(text, "\n".join(r.raw for r in records) + "\n")
        seqs = [e["seq"] for e in root(result, fixtures.A)["events"]]
        self.assertEqual(sorted(seqs), seqs)
        self.assertEqual([r.seq for r in records if r.kind in trace.LIFECYCLE_KINDS], seqs)

    def test_permanent_failure_keeps_the_exact_reason(self):
        _, result = normalize(fixtures.run(fixtures.LIFECYCLE_SCENARIOS["permanent_failure"][0]))
        text = root(result, fixtures.A)["FAILURE_OR_BAILOUT"]
        self.assertIn("PermanentBailoutException: Too deep inlining", text)
        self.assertEqual("NONE", lifecycle_none_failure())

    def test_deopt_storm_is_one_episode(self):
        _, result = normalize(fixtures.run(fixtures.LIFECYCLE_SCENARIOS["invalidate"][0]))
        episodes = root(result, fixtures.A)["invalidation_episodes"]
        self.assertEqual(1, len(episodes))
        self.assertEqual(5000, episodes[0]["frame_deopts"])
        self.assertLessEqual(len(root(result, fixtures.A)["later_activity_after_final_done"]), lifecycle.LATER_ACTIVITY_SAMPLE)

    def test_silence_is_never_a_pass(self):
        body = fixtures.LIFECYCLE_SCENARIOS["final_tier_done"][0]
        _, no_end_marker = normalize(fixtures.run(body, phases=fixtures.PHASES[:4]))
        self.assertEqual("INCONCLUSIVE", root(no_end_marker, fixtures.A)["STABLE_FINAL_OPTIMIZED_STATE"])
        _, not_completed = normalize(fixtures.run(body), completed=False)
        self.assertEqual("INCONCLUSIVE", root(not_completed, fixtures.A)["STABLE_FINAL_OPTIMIZED_STATE"])
        self.assertFalse(not_completed["run"]["complete"])

    def test_events_carry_their_objective_phase(self):
        def body(b):
            b.queued(1, fixtures.A).start(1, fixtures.A).done(1, fixtures.A, 1, 2585)
            b.mark("steady")
            b.queued(1, fixtures.A, 2).start(1, fixtures.A, 2).done(1, fixtures.A, 2, 2600)

        builder = fixtures.LogBuilder().mark("startup").mark("warmup")
        body(builder)
        for phase in ("closing", "end"):
            builder.mark(phase)
        _, result = normalize(builder.text())
        phases = [e["phase"] for e in root(result, fixtures.A)["events"]]
        self.assertEqual(["warmup"] * 3 + ["steady"] * 3, phases)
        self.assertEqual(["startup", "warmup", "steady", "closing", "end"], result["run"]["phase_sequence"])

    def test_id_label_conflict_and_unknown_records_poison_the_root(self):
        text = fixtures.run(lambda b: (b.queued(1, fixtures.A), b.raw(f"[engine] opt start  engine=2  id=1   {fixtures.B}|Tier 1")))
        _, result = normalize(text)
        self.assertIn("ID_LABEL_CONFLICT", [a["kind"] for a in result["anomalies"]])
        self.assertEqual("INCONCLUSIVE", root(result, fixtures.A)["OPTIMIZATION_STATE"])

    def test_generic_replacement_reasons_are_configurable_and_default_to_other(self):
        self.assertEqual("GENERIC_REPLACEMENT", lifecycle.classify_invalidation_reason("Node replaced by generic", lifecycle.DEFAULT_REPLACEMENT_PATTERNS))
        self.assertEqual("UNCOMMON_TRAP", lifecycle.classify_invalidation_reason("uncommon trap", lifecycle.DEFAULT_REPLACEMENT_PATTERNS))
        self.assertEqual("OTHER", lifecycle.classify_invalidation_reason("assumption invalid", lifecycle.DEFAULT_REPLACEMENT_PATTERNS))


def lifecycle_none_failure():
    _, result = normalize(fixtures.run(fixtures.LIFECYCLE_SCENARIOS["final_tier_done"][0]))
    return root(result, fixtures.A)["FAILURE_OR_BAILOUT"]


@unittest.skipUnless(REAL_LOG.is_file(), "retained UPSTREAM003 25.4 log not present")
class Real25_4LogTest(unittest.TestCase):
    """The parser and the state machine against real retained GraalVM 25.4.4.1.1 compiler output."""

    @classmethod
    def setUpClass(cls):
        cls.text = REAL_LOG.read_text(encoding="utf-8", errors="replace")
        cls.records = trace.split_records(cls.text)

    def test_record_kind_counts_match_the_raw_log(self):
        counts = {}
        for record in self.records:
            counts[record.kind] = counts.get(record.kind, 0) + 1
        self.assertEqual(
            (19, 14, 11, 3, 3, 5, 9184),
            tuple(counts.get(k, 0) for k in (trace.OPT_QUEUED, trace.OPT_START, trace.OPT_DONE, trace.OPT_FAILED, trace.OPT_FAIL_DETAIL, trace.OPT_DEQUEUED, trace.OPT_DEOPT)),
        )
        self.assertEqual(0, counts.get(trace.OPT_UNKNOWN, 0) + counts.get(trace.OPT_UNPARSED, 0))
        self.assertEqual(self.text, "\n".join(r.raw for r in self.records) + "\n")

    def test_lifecycle_of_the_real_run(self):
        result = lifecycle.normalize_lifecycle(self.records, first_tier=1, final_tier=2, required_phases=(), process_completed=True)
        self.assertEqual([], result["anomalies"])
        self.assertEqual(8, len(result["roots"]))
        permanent = sorted(r["label"].split("@")[0] + "@" + r["label"].split("@")[1] for r in result["roots"].values() if r["classes"]["permanent_bailout"])
        self.assertEqual(3, len(permanent))
        self.assertTrue(all(r["classes"]["never_compiled"] and r["OPTIMIZATION_STATE"] == "OPT_FAILED" for r in result["roots"].values() if r["classes"]["permanent_bailout"]))
        semantic = root(result, "ProtosSemanticBytecodeRootNodeGen@4ae9cfc1")
        self.assertEqual("1,2", semantic["TIER_REACHED"])
        self.assertEqual("PRESENT", semantic["INVALIDATION_OR_RECOMPILATION"])
        self.assertTrue(semantic["classes"]["compiled_then_invalidated"] and semantic["classes"]["compiled_then_recompiled"])
        self.assertEqual(1, len(semantic["invalidation_episodes"]))
        self.assertEqual(9184, semantic["invalidation_episodes"][0]["frame_deopts"])
        self.assertEqual("YES", semantic["STABLE_FINAL_OPTIMIZED_STATE"])

    def test_without_termination_proof_the_real_run_is_not_stable(self):
        result = lifecycle.normalize_lifecycle(self.records, first_tier=1, final_tier=2, required_phases=fixtures.PHASES, process_completed=True)
        self.assertFalse(result["run"]["complete"])
        self.assertTrue(all(r["STABLE_FINAL_OPTIMIZED_STATE"] != "YES" for r in result["roots"].values()))


if __name__ == "__main__":
    unittest.main()
