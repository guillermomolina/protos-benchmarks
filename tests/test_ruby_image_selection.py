# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina.
# See LICENSE.TXT at the repository root.

"""Host Podman selection and independent GraalVM versions, without a JVM."""

from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'harness'))
import benchmark
import measurement_support as runtime


class RubyImageSelectionTest(unittest.TestCase):
    def test_each_language_uses_one_pinned_image(self):
        args = benchmark.parse_args(['correctness', '--language', 'all'])
        self.assertEqual('localhost/protos-bench-runner:ruby-40.0.0-graal25.3.4.1',
                         benchmark.runtime_image(args, 'ruby'))
        for language in ('protos', 'js', 'python'):
            self.assertEqual(args.image, benchmark.runtime_image(args, language))
        self.assertNotEqual(args.image, args.ruby_image)

    def test_ruby_is_first_class_in_all_selection(self):
        self.assertEqual(('protos', 'js', 'python', 'ruby'),
                         benchmark.selected_languages('all'))

    def test_ruby_image_is_frozen_to_compatible_toolchain(self):
        spec = runtime.ruby_runtime_spec()
        self.assertEqual('40.0.0', spec['version'])
        self.assertEqual('25.3.4.1', spec['graalvm_version'])
        self.assertEqual('25.3.4.1', spec['truffle_version'])
        self.assertNotEqual(runtime.harness_graalvm_version(),
                            spec['graalvm_version'])
        self.assertEqual('image-baked', spec['classpath_source'])

    def test_maven_pom_matches_baked_image(self):
        spec=runtime.ruby_runtime_spec()
        built=runtime.ruby_peer_pom(spec['version'], spec['graalvm_version'])
        pinned=(ROOT/'harness/policy/ruby-peer.pom.xml').read_text(encoding='utf-8')
        self.assertEqual(pinned, built)

    def test_correctness_dispatches_ruby_to_its_own_image(self):
        args=benchmark.parse_args([
            'correctness', '--language', 'ruby',
            '--case', 'primitive-closure-call',
        ])
        with (mock.patch.object(benchmark,'podman_binary',return_value='podman'),
              mock.patch.object(benchmark,'require_image'),
              mock.patch.object(benchmark,'image_identity',return_value='sha256:'+'1'*64),
              mock.patch.object(benchmark,'run_container',return_value=0) as run):
            result=benchmark.run_measurement(args,'correctness')
        self.assertEqual(0,result)
        self.assertEqual(args.ruby_image,run.call_args.args[1])
        self.assertIsNone(run.call_args.args[2])
        self.assertIn('--correctness-only',run.call_args.args[3])

    def test_graph_capture_all_dispatches_each_image(self):
        args=benchmark.parse_args([
            'graphs-capture','--language','all',
            '--case','primitive-closure-call',
        ])
        with (mock.patch.object(benchmark,'podman_binary',return_value='podman'),
              mock.patch.object(benchmark,'require_image'),
              mock.patch.object(benchmark,'product_directory',return_value=ROOT),
              mock.patch.object(benchmark,'run_container',return_value=0) as run):
            result=benchmark.run_graphs(args)
        self.assertEqual(0,result)
        self.assertEqual(4,run.call_count)
        images=[call.args[1] for call in run.call_args_list]
        self.assertEqual([args.image,args.image,args.image,args.ruby_image],images)
        language_args=[call.args[3] for call in run.call_args_list]
        for language, invocation in zip(('protos','js','python','ruby'),language_args):
            self.assertEqual(language,invocation[invocation.index('--language')+1])

    def test_old_unpublished_version_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'RUBY_RUNTIME_POLICY_INCOMPATIBLE'):
            runtime.ruby_peer_pom('40.1.0','25.4.4.1.1')


if __name__ == '__main__':
    unittest.main()
