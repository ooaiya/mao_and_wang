"""Isolated version-admission fixtures; no VM/Freezer success is inferred."""
from contextlib import ExitStack
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

GUI = Path(__file__).resolve().parents[1]


class TargetEnvironmentTests(unittest.TestCase):
    def test_frontend_formal_check_uses_same_exact_base_version(self):
        # Call the existing checker; mock external probes, never launch GUI input.
        sys.path.insert(0, str(GUI))
        frontend = importlib.import_module('oomlab_krita_collect.environment')
        config = {'display_size': [1, 1], 'asset': {}, 'safety': {
            'min_available_bytes': 0, 'min_swap_free_bytes': 0,
            'min_disk_free_bytes': 0, 'max_global_full_avg10': 100}}
        for release, accepted in [('6.17.13-oomlab', True), ('6.17.13-generic', True),
                                  ('6.17.12-generic', False), ('6.17.14-generic', False),
                                  ('6.17.130-generic', False)]:
            with self.subTest(release=release), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                stack.enter_context(patch.object(frontend.os, 'geteuid', return_value=1000, create=True))
                stack.enter_context(patch.object(frontend.platform, 'release', return_value=release))
                stack.enter_context(patch.object(frontend.platform, 'freedesktop_os_release', return_value={'ID': 'ubuntu', 'VERSION_ID': '22.04'}))
                stack.enter_context(patch.object(frontend, 'source_identity', return_value={'git_branch': 'main', 'source_dirty': False}))
                stack.enter_context(patch.object(frontend, 'conflicts', return_value=[]))
                stack.enter_context(patch.object(frontend, 'command', return_value=SimpleNamespace(stdout='1 1')))
                stack.enter_context(patch.object(frontend, 'pinned', return_value={}))
                result = frontend.check(config, directory, require_gui=True)
                mismatch = any('formal target requires' in e for e in result['errors'])
                self.assertEqual(mismatch, not accepted, result['errors'])
                self.assertEqual(result['kernel'], release)


if __name__ == '__main__':
    unittest.main()
