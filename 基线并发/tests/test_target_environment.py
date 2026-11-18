"""Isolated version-admission fixtures; no VM/Freezer success is inferred."""
from contextlib import ExitStack
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '后台操作'))
from oomlab import environment


class TargetEnvironmentTests(unittest.TestCase):
    def check_backend(self, release, distribution=None):
        files = {
            '/proc/1/comm': 'systemd\n',
            '/sys/fs/cgroup/cgroup.controllers': 'memory cpu io\n',
            '/sys/fs/cgroup/memory.stat': 'anon 1024\nfile 1024\n',
            '/proc/swaps': 'Filename Type Size Used Priority\n',
        }
        with ExitStack() as stack:
            stack.enter_context(patch.object(environment.platform, 'release', return_value=release))
            stack.enter_context(patch.object(environment.platform, 'freedesktop_os_release', return_value=distribution or {'ID': 'ubuntu', 'VERSION_ID': '22.04', 'PRETTY_NAME': 'Ubuntu 22.04.5 LTS'}))
            stack.enter_context(patch.object(Path, 'read_text', autospec=True, side_effect=lambda p, *a, **k: files[str(p)]))
            stack.enter_context(patch.object(Path, 'is_file', return_value=True))
            stack.enter_context(patch.object(Path, 'exists', return_value=True))
            stack.enter_context(patch.object(environment.shutil, 'which', return_value='/fixture/tool'))
            stack.enter_context(patch.object(environment.shutil, 'disk_usage', return_value=SimpleNamespace(free=100 * 1024**3)))
            stack.enter_context(patch.object(environment, 'privileged', return_value=SimpleNamespace(stdout='Version=249\n')))
            stack.enter_context(patch.object(environment, 'meminfo', return_value={'MemTotal': 16 * 1024**3}))
            stack.enter_context(patch.object(environment, 'resource_check', return_value={}))
            return environment.check_environment('.')

    def assert_kernel_admission(self, release, accepted):
        result = self.check_backend(release)
        self.assertEqual(result['target']['kernel'], '6.17.13')
        self.assertEqual(result['kernel'], release, 'retain full platform.release()')
        self.assertEqual(result['target_matches'], accepted)
        self.assertEqual(result['ok'], accepted, result['errors'])
        self.assertEqual(any('目标版本不匹配' in e for e in result['errors']), not accepted)

    def test_61713_oomlab_passes(self):
        self.assert_kernel_admission('6.17.13-oomlab', True)

    def test_61713_generic_passes(self):
        self.assert_kernel_admission('6.17.13-generic', True)

    def test_61712_generic_fails(self):
        self.assert_kernel_admission('6.17.12-generic', False)

    def test_61714_generic_fails(self):
        self.assert_kernel_admission('6.17.14-generic', False)

    def test_exact_base_version(self):
        self.assert_kernel_admission('6.17.13', True)
        self.assert_kernel_admission('6.17.130-generic', False)

    def test_ubuntu_version_id_guard_is_unchanged(self):
        result = self.check_backend('6.17.13-oomlab', {'ID': 'ubuntu', 'VERSION_ID': '24.04'})
        self.assertFalse(result['target_matches'])
        self.assertFalse(result['ok'])

    def test_frontend_formal_check_uses_same_exact_base_version(self):
        # Call the existing checker; mock external probes, never launch GUI input.
        sys.path.insert(0, str(ROOT / '前台操作/前台操作自动化脚本采集'))
        frontend = importlib.import_module('oomlab_krita_collect.environment')
        config = {'display_size': [1, 1], 'asset': {}, 'safety': {
            'min_available_bytes': 0, 'min_swap_free_bytes': 0,
            'min_disk_free_bytes': 0, 'max_global_full_avg10': 100}}
        for release, accepted in [('6.17.13-oomlab', True), ('6.17.13-generic', True),
                                  ('6.17.12-generic', False), ('6.17.14-generic', False),
                                  ('6.17.130-generic', False)]:
            with self.subTest(release=release), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
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
