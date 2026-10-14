"""Contracts that don't require a working GTK graphical session."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class B2BContracts(unittest.TestCase):
    def test_registration_dialog_requires_second_user_action(self):
        ui = (ROOT / 'snapmark/ai_runtime_ui.py').read_text()
        self.assertIn('Inspect with Runtime…', ui)
        self.assertIn('Register this local model?', ui)
        self.assertIn("dialog.add_response('register', 'Register model')", ui)
        self.assertIn("if response != 'register'", ui)
        self.assertIn('register_reviewed_model(review, confirmed=True)', ui)
        self.assertIn('GLib.idle_add', ui)

    def test_no_auto_write_on_import_or_page_initialization(self):
        s = (ROOT / 'snapmark/runtime_registration.py').read_text()
        tree = ast.parse(s)
        writes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and
                  node.name == 'register_reviewed_model']
        self.assertEqual(len(writes), 1)
        self.assertIn('confirmed: bool = False', s)
        self.assertNotIn('subprocess', s)
        self.assertNotIn('shutil', s)

if __name__ == '__main__':
    unittest.main()
