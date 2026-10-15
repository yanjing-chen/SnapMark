"""Regression contract: separate the shared backend selector and action.

Pure static checks: never contact a running Runtime or change user settings.
"""
import ast
from pathlib import Path
import unittest


UI = Path(__file__).resolve().parents[1] / 'snapmark' / 'ai_runtime_ui.py'


class B4C1BackendLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = UI.read_text(encoding='utf-8')
        ast.parse(cls.source, filename=str(UI))
        cls.section = cls.source.split('        # Keep dropdown and confirmation action on separate ActionRows.', 1)[1].split('        action_rows = (',1)[0]

    def test_selector_and_apply_are_in_distinct_rows(self):
        s = self.section
        self.assertEqual(s.count('shared_choice.add_suffix('), 1)
        self.assertEqual(s.count('apply_choice.add_suffix('), 1)
        self.assertIn('shared_choice.add_suffix(shared_dropdown)', s)
        self.assertIn('apply_choice.add_suffix(save_shared)', s)
        self.assertNotIn('shared_choice.add_suffix(save_shared)', s)
        self.assertLess(s.index('packages.add(shared_choice)'), s.index('packages.add(apply_choice)'))
        self.assertIn("title='Apply selected backend preference'", s)

    def test_existing_signal_and_widget_identifiers_are_preserved(self):
        s = self.section
        self.assertIn("save_shared.connect('clicked', self._b4_action, 'preference')", s)
        self.assertIn("self.widgets['b4_choice'] = shared_dropdown", s)
        self.assertIn("self.widgets['b4_save'] = save_shared", s)
        self.assertIn("['Auto (recommended)', 'CPU', 'Vulkan', 'CUDA']", s)
        self.assertIn('save_shared.set_sensitive(False)', s)


if __name__ == '__main__':
    unittest.main()
