"""C3 About page and standalone About window share the same app version."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'snapmark/editor.py').read_text(encoding='utf-8')
APP = (ROOT / 'snapmark/app.py').read_text(encoding='utf-8')
INIT = (ROOT / 'snapmark/__init__.py').read_text(encoding='utf-8')


class AboutVersionContract(unittest.TestCase):
    def test_main_version_defined_only_by_package(self):
        tree = ast.parse(INIT)
        versions = [node.value.value for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == '__version__'
                            for t in node.targets)
                    and isinstance(node.value, ast.Constant)]
        self.assertEqual(versions, ['1.0.0'])

    def test_preferences_about_page_exposes_version_row(self):
        tree = ast.parse(EDITOR)
        imports = [node for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom)
                   and node.level == 1 and node.module is None]
        self.assertTrue(any(alias.name == '__version__'
                            for node in imports for alias in node.names))
        self.assertIn("about_group.add(Adw.ActionRow(title=_('Version'), subtitle=__version__))", EDITOR)
        before_row = EDITOR.index("about_page.add(about_group)")
        after_row = EDITOR.index("stack.add_titled(about_page, 'about', 'About')")
        self.assertLess(before_row, EDITOR.index("about_group.add(Adw.ActionRow", before_row))
        self.assertLess(EDITOR.index("about_group.add(Adw.ActionRow", before_row), after_row)

    def test_tray_and_preferences_use_same_version(self):
        ast.parse(APP)
        self.assertIn("application_name='SnapMark', version=__version__", APP)
        self.assertNotIn("subtitle='1.0.0'", EDITOR)


if __name__ == '__main__':
    unittest.main()
