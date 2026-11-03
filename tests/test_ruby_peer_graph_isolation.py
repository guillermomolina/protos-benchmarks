# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.
"""Peer graph-capture does not mount/inspect Protos. Host-only mock tests."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'harness'))
import benchmark
import measure_graphs

class RubyPeerGraphIsolationTest(unittest.TestCase):
    def test_ruby_cold_host_does_not_require_protos_checkout(self):
        args=benchmark.parse_args([
            'cold-capture', '--language', 'ruby',
            '--case','primitive-closure-call', '--root','all', '--tier','1',
        ])
        with (mock.patch.object(benchmark,'podman_binary',return_value='podman'),
              mock.patch.object(benchmark,'require_image'),
              mock.patch.object(benchmark,'product_directory') as product,
              mock.patch.object(benchmark,'run_container',return_value=0) as run):
            self.assertEqual(0,benchmark.run_cold(args))
        product.assert_not_called()
        self.assertIsNone(run.call_args.args[2])
        self.assertNotIn('--dir',run.call_args.args[3])
        self.assertEqual(args.ruby_image,run.call_args.args[1])

    def test_protos_cold_retains_product_mount_and_argument(self):
        args=benchmark.parse_args([
            'cold-capture','--language','protos',
            '--case','primitive-closure-call','--tier','1',
        ])
        with (mock.patch.object(benchmark,'podman_binary',return_value='podman'),
              mock.patch.object(benchmark,'require_image'),
              mock.patch.object(benchmark,'product_directory',return_value=ROOT) as product,
              mock.patch.object(benchmark,'run_container',return_value=0) as run):
            self.assertEqual(0,benchmark.run_cold(args))
        product.assert_called_once()
        self.assertEqual(ROOT,run.call_args.args[2])
        self.assertIn('--dir',run.call_args.args[3])
        self.assertEqual(args.image,run.call_args.args[1])

    def test_ruby_graph_capture_host_is_independent(self):
        args=benchmark.parse_args([
            'graphs-capture','--language','ruby',
            '--case','primitive-closure-call',
        ])
        with (mock.patch.object(benchmark,'podman_binary',return_value='podman'),
              mock.patch.object(benchmark,'require_image'),
              mock.patch.object(benchmark,'product_directory') as product,
              mock.patch.object(benchmark,'run_container',return_value=0) as run):
            self.assertEqual(0,benchmark.run_graphs(args))
        product.assert_not_called()
        self.assertIsNone(run.call_args.args[2])
        self.assertNotIn('--dir',run.call_args.args[3])
        self.assertEqual(args.ruby_image,run.call_args.args[1])

    def test_cold_cli_dir_is_optional_but_language_is_explicit(self):
        args=measure_graphs.parse_args([
            'cold','--language','ruby','--workload','primitive-closure-call',
            '--output','/tmp/any','--tier','1','--last-threshold','1000000',
        ])
        self.assertIsNone(args.dir)
        self.assertEqual('ruby',args.language)

if __name__=='__main__':
    unittest.main()
