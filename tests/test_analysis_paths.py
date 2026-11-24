"""Check containment without loading numpy or running a workload."""
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import unittest

SPEC = importlib.util.spec_from_file_location('analysis_paths', Path(__file__).resolve().parents[1] / '基线并发/tools/analysis_paths.py')
paths = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(paths)


class PathTests(unittest.TestCase):
    def test_repo_output_is_rejected(self):
        with self.assertRaises(ValueError):
            paths.external_output(Path(__file__).resolve().parents[1] / 'results')

    def test_external_output_and_source_containment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(paths.external_output(root / 'out'), root / 'out')
            (root / 'sample.csv').write_text('synthetic')
            self.assertEqual(paths.source_file(root, 'sample.csv'), root / 'sample.csv')
            with self.assertRaises(ValueError):
                paths.source_file(root / 'out', root / 'sample.csv')
            # Reproduce /tmp/.git's empty placeholder without changing /tmp/.git.
            (root / '.git').mkdir(mode=0o555)
            self.assertEqual(paths.external_output(root / 'placeholder-ok'), root / 'placeholder-ok')
            (root / '.git').chmod(0o755)
            subprocess.run(['git', 'init', '-q', '-b', 'main', str(root)], check=True)
            with self.assertRaises(ValueError):
                paths.external_output(root / 'blocked')
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test',
                            '-c', 'user.email=test@example.invalid', '-c', 'core.hooksPath=/dev/null',
                            'commit', '--allow-empty', '-qm', 'fixture'], check=True)
            worktree = root.parent / (root.name + '-worktree')
            subprocess.run(['git', '-C', str(root), 'worktree', 'add', '-q', '--detach', str(worktree)], check=True)
            try:
                self.assertTrue((worktree / '.git').is_file())
                with self.assertRaises(ValueError):
                    paths.external_output(worktree / 'blocked')
            finally:
                subprocess.run(['git', '-C', str(root), 'worktree', 'remove', str(worktree)], check=True)


if __name__ == '__main__':
    unittest.main()
