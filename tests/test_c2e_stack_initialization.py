"""C2-E regression: Gtk.Stack page exists before selection."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent.parent
class GtkStackInitializationTests(unittest.TestCase):
    def test_sidebar_constructor_does_not_select_unregistered_general(self):
        source=(ROOT/'snapmark/preferences_sidebar_c2e.py').read_text('utf-8')
        ast.parse(source)
        self.assertNotIn("stack.set_visible_child_name('general')", source)
        self.assertIn("stack.connect('notify::visible-child-name'",source)
        self.assertIn('populate_plugins',source)

    def test_editor_selects_after_general_and_about_registered(self):
        source=(ROOT/'snapmark/editor.py').read_text('utf-8')
        ast.parse(source)
        start=source.index('    def show_preferences(self):')
        body=source[start:]
        creation=body.index('navigation = PreferencesNavigation(stack)')
        general=body.index("stack.add_titled(page, 'general', 'General')")
        about=body.index("stack.add_titled(about_page, 'about', 'About')")
        select=body.index("stack.set_visible_child_name('general')")
        self.assertLess(creation,general)
        self.assertLess(general,about)
        self.assertLess(about,select)
        self.assertIn('navigation._highlight()',body[select:select+160])

if __name__=='__main__':
    unittest.main()
