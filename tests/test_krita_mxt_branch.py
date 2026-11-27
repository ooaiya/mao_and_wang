"""Branch compatibility only; all GUI commands are mocked, no application starts."""
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
GUI=Path(__file__).resolve().parents[1]/'前台操作/前台操作自动化脚本采集'
sys.path.insert(0,str(GUI))
from oomlab_krita_collect import environment

class KritaBranchTests(unittest.TestCase):
    def check_branch(self,branch,dirty=False):
        config=json.loads((GUI/'configs/collection.rapid-9000-medium-tail-extended.json').read_text())
        with patch.object(environment,'source_identity',return_value={'git_branch':branch,'source_dirty':dirty}),patch.object(environment,'conflicts',return_value=[]),patch.object(environment,'command',return_value=types.SimpleNamespace(stdout='',returncode=0)),patch.object(environment.shutil,'which',return_value='/fake/tool'):
            return environment.check(config,Path('/tmp/krita-branch-test-output'))['errors']
    def test_mxt_allowed(self):self.assertFalse(any('requires main or mxt' in e for e in self.check_branch('mxt')))
    def test_main_allowed(self):self.assertFalse(any('requires main or mxt' in e for e in self.check_branch('main')))
    def test_report_branch_and_detached_rejected(self):
        for b in ['mxt_codex','HEAD','']:
            self.assertTrue(any('requires main or mxt' in e for e in self.check_branch(b)))
    def test_dirty_mxt_still_rejected(self):self.assertIn('formal collection requires committed clean source',self.check_branch('mxt',True))
