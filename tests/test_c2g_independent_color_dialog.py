"""C2-G: ColorDialog is unparented, nonmodal, and preserves RGB callbacks."""
import ast
import types
import unittest
import textwrap
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / 'snapmark/editor.py'
SRC = FILE.read_text('utf-8')
TREE = ast.parse(SRC)
ED = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'EditorWindow')

def method(name):
    node = next(n for n in ED.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SRC, node)

def standalone(name, **ctx):
    env = dict(ctx)
    exec('class Dummy:\n' + textwrap.indent(method(name), '    '), env)
    return env['Dummy']

class ColourDialogTests(unittest.TestCase):
    def test_nonmodal_unparented_and_dialog_can_move_independently(self):
        seen=[]
        class FakeRGBA:
            def parse(self, value):
                seen.append(('initial', value))
        class FakeDialog:
            def __init__(self, **kwargs):
                seen.append(('constructor', kwargs))
                self.modal = True
            def set_modal(self, enabled):
                self.modal = enabled
                seen.append(('modal', enabled))
            def choose_rgba(self, parent, initial, cancellable, callback):
                seen.append(('choose', parent, self.modal, callable(callback)))
        klass=standalone('_choose_color', Gtk=types.SimpleNamespace(ColorDialog=FakeDialog),
                          Gdk=types.SimpleNamespace(RGBA=FakeRGBA))
        dummy=klass(); dummy.color='#3584e4'; dummy.fill_color='#26a269'; dummy._color_chosen=lambda *args: None
        dummy._choose_color(False)
        self.assertEqual(seen[1], ('modal', False))
        self.assertEqual(seen[2], ('initial','#3584e4'))
        self.assertEqual(seen[3], ('choose', None, False, True))
        seen.clear()
        dummy._choose_color(True)
        self.assertIn(('initial','#26a269'), seen)
        self.assertIn(('choose',None,False,True), seen)

    def test_old_modal_parent_binding_was_removed(self):
        source=method('_choose_color')
        self.assertNotIn('choose_rgba(self,', source)
        self.assertIn('dialog.choose_rgba(None,',source)
        self.assertIn('dialog.set_modal(False)',source)
        self.assertIn('with_alpha=False',source)
        self.assertIn('self._color_chosen(dlg, result, fill)',source)

    def test_colour_selection_still_updates_both_palette_and_recent(self):
        source=method('_color_chosen')
        for expected in ('dialog.choose_rgba_finish(result)',
                         'self.fill_color = color', 'self.color = color',
                         'self.settings.remember_color(color)',
                         'self._refresh_recent()',
                         'self._sync_palette_selection(fill=fill)'):
            self.assertIn(expected,source)

if __name__ == '__main__': unittest.main()
