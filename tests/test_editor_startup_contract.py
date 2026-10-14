"""Offline regression for the A1 tray-only / invisible-editor startup failure.

The full GTK window-construction test is performed by --smoke-test in Actions
and on GNOME Wayland. This check runs even where PyGObject is unavailable.
"""
import ast
import unittest
from pathlib import Path


class EditorStartupContractTests(unittest.TestCase):
    def test_plugin_toolbar_is_constructed_before_reference_is_stored(self):
        source = Path(__file__).resolve().parents[1] / 'snapmark' / 'editor.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        editor = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                      and node.name == 'EditorWindow')
        build = next(node for node in editor.body if isinstance(node, ast.FunctionDef)
                     and node.name == '_build_ui')

        create_at = []
        assign_at = []
        for index, statement in enumerate(build.body):
            if not isinstance(statement, ast.Assign):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id == 'tools':
                    create_at.append(index)
                if (isinstance(target, ast.Attribute) and target.attr == '_plugin_tools'
                        and isinstance(target.value, ast.Name) and target.value.id == 'self'):
                    assign_at.append(index)
                    self.assertIsInstance(statement.value, ast.Name)
                    self.assertEqual(statement.value.id, 'tools')
        self.assertEqual(len(create_at), 1, 'Expected exactly one tools container construction')
        self.assertEqual(len(assign_at), 1, 'Expected exactly one plugin tools assignment')
        self.assertLess(create_at[0], assign_at[0], 'Gtk.Box must exist before use')


if __name__ == '__main__':
    unittest.main()
