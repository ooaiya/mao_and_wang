"""Non-destructive policy tests; commits exist only in temporary repositories."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('guard', Path(__file__).resolve().parents[1] / 'tools/git_guard.py')
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.temp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Policy Test')
        self.git('config', 'user.email', 'policy@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.write('code.py', 'value = 1\n')
        self.commit('initial')
        self.base = self.sha()
        self.git('switch', '-q', '-c', 'mxt')

    def tearDown(self):
        os.chdir(self.previous)
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', *args], stderr=subprocess.DEVNULL)

    def write(self, path, text):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.git('add', '--', path)

    def commit(self, message):
        self.git('commit', '-qm', message)

    def sha(self):
        return self.git('rev-parse', 'HEAD').decode().strip()

    def push(self, branch='mxt', old=None, target=None, new=None):
        ref = 'refs/heads/' + branch
        guard.check_push(next(iter(guard.REMOTES)),
                         f'{ref} {new or self.sha()} {target or ref} {old or self.base}')

    def test_code_and_report_commits(self):
        self.write('code.py', 'value = 2\n')
        guard.pre_commit()
        self.commit('code')
        self.push()
        self.git('switch', '-q', '-c', 'mxt_codex')
        self.write('codex_reports/report.md', '# Reviewed report\n')
        guard.pre_commit()
        self.commit('report')
        self.push('mxt_codex')

    def test_data_and_credentials(self):
        for path in ['results/run.json', 'capture.csv', 'trace.jsonl', 'curves.npz',
                     'run.log', 'image.png', 'taxi.parquet', 'model.joblib', 'trip_duration_model.txt', 'run.ipynb', '.aws/config', '.env', 'id_ed25519']:
            with self.subTest(path=path):
                self.assertIsNotNone(guard.violation(path, b'test'))
        secret = ('gh' + 'p_' + 'A' * 36).encode()
        self.assertIsNotNone(guard.violation('config.py', secret))
        key = ('-----BEGIN ' + 'OPENSSH PRIVATE KEY-----').encode()
        self.assertIsNotNone(guard.violation('notes.md', key))
        self.write('bad.csv', 'raw,data\n')
        with self.assertRaises(ValueError):
            guard.pre_commit()
        self.commit('bad data')
        with self.assertRaises(ValueError):
            self.push()

    def test_intermediate_bad_commit_is_rejected(self):
        self.write('raw.npy', 'not a real array')
        self.commit('data')
        self.git('rm', '-q', 'raw.npy')
        self.commit('remove data')
        with self.assertRaises(ValueError):
            self.push()

    def test_configs_manifests_and_synthetic_fixtures(self):
        for path in ['config/settings.json', '素材/SHA256SUMS', '素材/manifest.json',
                     '素材/README.md', 'tests/fixtures/synthetic.csv']:
            self.assertIsNone(guard.violation(path, b'{}'))
        self.assertIsNotNone(guard.violation('tests/fixtures/key.json',
                             ('gh' + 'p_' + 'A' * 36).encode()))

    def test_wrong_refs_deletion_and_nonfastforward(self):
        for branch in ['main', 'unknown']:
            with self.assertRaises(ValueError):
                self.push(branch)
        with self.assertRaises(ValueError):
            self.push(target='refs/heads/main')
        with self.assertRaises(ValueError):
            self.push(new='0' * 40)
        self.write('code.py', 'value = 3\n')
        self.commit('forward')
        descendant = self.sha()
        self.git('update-ref', 'refs/heads/mxt', self.base)
        with self.assertRaises(ValueError):
            self.push(old=descendant, new=self.base)
        with self.assertRaises(ValueError):
            guard.check_push('https://example.invalid/repo', '')

    def test_codex_code_change_rejected(self):
        self.git('switch', '-q', '-c', 'mxt_codex')
        self.write('code.py', 'value = 4\n')
        with self.assertRaises(ValueError):
            guard.pre_commit()
        self.commit('illegal code')
        with self.assertRaises(ValueError):
            self.push('mxt_codex')

    def test_explicit_mxt_sync_merge(self):
        self.git('switch', '-q', '-c', 'mxt_codex')
        self.write('codex_reports/README.md', '# Reports\n')
        self.commit('report')
        old = self.sha()
        self.git('switch', '-q', 'mxt')
        self.write('code.py', 'value = 5\n')
        self.commit('code cleanup')
        self.git('switch', '-q', 'mxt_codex')
        self.git('merge', '--no-ff', '--no-commit', 'mxt')
        guard.pre_commit()
        self.commit('Sync mxt code')
        self.push('mxt_codex', old=old)
        self.assertEqual(Path('codex_reports/README.md').read_text(), '# Reports\n')


if __name__ == '__main__':
    unittest.main()
