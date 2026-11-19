"""TEST_ONLY path relocation checks; no real assets or collection are used."""
import importlib.util
from pathlib import Path
import unittest

from oomlab_krita_collect.common import GUI

spec = importlib.util.spec_from_file_location('handoff_path_test', GUI / 'scripts/prepare_handoff_config.py')
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class HandoffPathTests(unittest.TestCase):
    target = Path('/TEST_ONLY/isolated/assets')

    def test_legacy_template_relocates(self):
        result = handoff.relocated('/home/legacy/OOM_assets/krita/light.ora', self.target)
        self.assertEqual(result, str(self.target / 'krita/light.ora'))

    def test_team_template_relocates_to_an_explicit_root(self):
        source = GUI.parents[2] / 'assets/foreground/krita/light.ora'
        self.assertEqual(handoff.relocated(source, self.target), str(self.target / 'krita/light.ora'))

    def test_current_team_root_is_idempotent(self):
        root = GUI.parents[2] / 'assets/foreground'
        source = root / 'krita/light.ora'
        self.assertEqual(handoff.relocated(source, root), str(source))

    def test_unrelated_source_is_rejected(self):
        with self.assertRaises(ValueError):
            handoff.relocated('/TEST_ONLY/unrelated/light.ora', self.target)

    def test_legacy_parent_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            handoff.relocated('/home/legacy/OOM_assets/../escape.ora', self.target)

    def test_team_parent_traversal_is_rejected(self):
        source = GUI.parents[2] / 'assets/foreground/../escape.ora'
        with self.assertRaises(ValueError):
            handoff.relocated(source, self.target)
