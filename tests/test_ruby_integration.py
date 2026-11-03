# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Ruby integration contracts without a Ruby runtime or JVM."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))

import graph_evidence as ge
import measure_graphs as mg
import measure_protos as mp
import workload_catalog


class RubyIntegrationContractTest(unittest.TestCase):

    def test_all_seventeen_workloads_are_catalogued(self):
        self.assertEqual(17, len(workload_catalog.workload_ids()))
        self.assertEqual(
            ("protos", "js", "python", "ruby"),
            workload_catalog.LANGUAGES,
        )
        self.assertEqual(
            workload_catalog.LANGUAGES, mg.LANGUAGES
        )

        for workload in workload_catalog.workload_ids():
            path = workload_catalog.source_for(
                workload, "ruby"
            )
            self.assertTrue(path.is_file())
            self.assertEqual(".rb", path.suffix)
            self.assertIn(
                "method(:run)",
                path.read_text(encoding="utf-8"),
            )

    def test_ruby_version_matches_pinned_truffle(self):
        spec = mp.jvm_runtime.ruby_runtime_spec()
        self.assertEqual("40.0.0", spec["version"])
        self.assertEqual(
            "25.3.4.1",
            spec["truffle_version"],
        )
        self.assertEqual(
            "dev.truffleruby:truffleruby",
            spec["maven_coordinate"],
        )

    def test_incompatible_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                mp, "EMBEDDED_CACHE", Path(directory)
            ):
                with self.assertRaises(mp.UsageError) as raised:
                    mp.peer_classpath(
                        "40.1.0", language="ruby",
                        offline=True,
                    )
                self.assertIn(
                    "RUBY_TRUFFLE_VERSION_INCOMPATIBLE",
                    str(raised.exception),
                )

    def test_missing_ruby_preparation_fails_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.object(
                    mp, "EMBEDDED_CACHE", Path(directory)
                ),
                mock.patch.dict(os.environ, {"PROTOS_RUBY_IMAGE_CLASSPATH": ""}),
                mock.patch.object(
                    mp.subprocess, "run",
                    side_effect=AssertionError(
                        "Maven must not run in this test"
                    ),
                ),
            ):
                with self.assertRaises(mp.UsageError) as raised:
                    mp.peer_classpath(
                        language="ruby", offline=True
                    )
                self.assertIn(
                    "RUBY_NOT_PREPARED",
                    str(raised.exception),
                )

    def test_root_identity_is_not_invented(self):
        policy = mg.load_policy()
        ruby = policy["languages"]["ruby"]

        self.assertIsNone(
            ruby["primary_label_pattern"]
        )
        self.assertEqual(
            "PENDING_RUNTIME_EVIDENCE",
            ruby["root_identity_status"],
        )

        with self.assertRaises(ge.EvidenceError) as raised:
            ge.validate_primary_label(
                ruby, "unverified Ruby root"
            )
        self.assertEqual(
            "PRIMARY_IDENTITY_UNVERIFIED",
            raised.exception.reason,
        )

    def test_graph_capture_requires_prepared_ruby(self):
        product = {
            "revision": "a" * 40,
            "source_state_sha256": "b" * 64,
        }
        java = {"java.runtime.version": "25"}

        with mock.patch.object(
            mp, "peer_classpath",
            side_effect=mp.UsageError("RUBY_NOT_PREPARED"),
        ):
            with self.assertRaises(mp.UsageError):
                mg.graph_capture_key(
                    mg.load_policy(),
                    product,
                    "ruby",
                    "executable-value",
                    "primitive-closure-call",
                    "smoke",
                    java,
                )


class RubyStructuralComparisonTest(unittest.TestCase):

    @staticmethod
    def sample(nodes: int, graphs: int = 1) -> dict:
        return {
            "relevant_graph_nodes_total_after_truffle_tier": nodes,
            "graph_count": graphs,
            "families": {
                family: 0 for family in ge.FAMILIES
            },
            "additional_language_owned_compiled_units": [],
        }

    def test_three_peer_reference_uses_ruby(self):
        result = ge.compare_rung(
            "primitive-closure-call",
            "closure invocation",
            {
                "js": self.sample(10),
                "python": self.sample(14),
                "ruby": self.sample(18),
                "protos": self.sample(23),
            },
        )
        self.assertEqual("js-python-ruby", result["peer_reference_scope"])
        self.assertTrue(result["peer_cohort_complete"])
        self.assertEqual(18, result["ruby_total"])
        self.assertEqual([10, 18], result["peer_band"])
        self.assertEqual(8, result["peer_spread"])
        self.assertEqual(ge.PEER_CONVERGED, result["peer_reference"])

    def test_legacy_reference_does_not_claim_ruby(self):
        result = ge.compare_rung(
            "primitive-closure-call",
            "closure invocation",
            {
                "js": self.sample(10),
                "python": self.sample(14),
                "protos": self.sample(23),
            },
        )
        self.assertEqual(
            "legacy-js-python", result["peer_reference_scope"]
        )
        self.assertFalse(result["peer_cohort_complete"])
        self.assertIsNone(result["ruby_total"])
        self.assertEqual([10, 14], result["peer_band"])

    def test_ruby_topology_disagreement_is_unresolved(self):
        result = ge.compare_rung(
            "primitive-closure-call",
            "closure invocation",
            {
                "js": self.sample(10),
                "python": self.sample(14),
                "ruby": self.sample(18, graphs=2),
                "protos": self.sample(100),
            },
        )
        self.assertEqual(ge.PEER_UNRESOLVED, result["peer_reference"])
        self.assertIn(
            "PEER_TOPOLOGY_DISAGREES",
            result["peer_reasons"],
        )
        self.assertEqual(ge.NOT_EVALUATED, result["protos_status"])

    def test_cold_accepts_ruby_implementation_version(self):
        args = mg.parse_args([
            "cold",
            "--dir", "/tmp/protos",
            "--output", "/tmp/cold-ruby",
            "--language", "ruby",
            "--workload", "primitive-closure-call",
            "--tier", "1",
            "--last-threshold", "1000000",
            "--root", "all",
            "--version", "40.0.0",
        ])
        self.assertEqual("ruby", args.language)
        self.assertEqual("40.0.0", args.version)
        self.assertEqual("all", args.root)

    def test_graph_capture_accepts_ruby_version(self):
        args = mg.parse_args([
            "capture",
            "--output", "/tmp/graph-ruby",
            "--language", "ruby",
            "--ruby-version", "40.0.0",
            "--workload", "primitive-closure-call",
        ])
        self.assertEqual("40.0.0", args.ruby_version)

if __name__ == "__main__":
    unittest.main()
