"""C2-G: fill palette Recent equals stroke UI behavior without changing stroke."""
import ast
import types
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'snapmark' / 'editor.py'
TEXT = SRC.read_text('utf-8')
TREE = ast.parse(TEXT)
CLS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'EditorWindow')


def source(name):
    node = next(n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return '\n'.join(TEXT.splitlines()[node.lineno-1:node.end_lineno])


def editor(*names, env=None):
    ns = {'COLORS': ['#eb3024','#26a269']}
    if env:
        ns.update(env)
    exec(compile('class Editor:\n' + '\n'.join(source(name) for name in names),
                 str(SRC), 'exec'), ns)
    return ns['Editor']()


class Widget:
    def __init__(self, *args, **kwargs):
        self.children = []
        self.active = False
        self.visible = True
        self.css = set()
        self.tooltip = kwargs.get('tooltip_text', '')
        self.draw_args = None
        self.handlers = {}
    def set_halign(self, *a): pass
    def add_css_class(self, css): self.css.add(css)
    def remove_css_class(self, css): self.css.discard(css)
    def append(self, obj): self.children.append(obj)
    def get_first_child(self): return self.children[0] if self.children else None
    def remove(self, obj): self.children.remove(obj)
    def set_size_request(self, *a): pass
    def set_group(self, other): self.grouped = other
    def set_content_width(self, *a): pass
    def set_content_height(self, *a): pass
    def set_draw_func(self, cb, value): self.draw_args = (cb, value)
    def set_child(self, child): self.child = child
    def connect(self, signal, cb, *extra): self.handlers[signal] = (cb, extra)
    def set_active(self, val): self.active = bool(val)
    def get_active(self): return self.active
    def click(self):
        self.active = True
        cb, extra = self.handlers['toggled']
        cb(self, *extra)
    def set_visible(self, val): self.visible = bool(val)


class FakeGtk:
    class Orientation: HORIZONTAL = 'horizontal'
    class Align: START = 'start'
    Box = Label = ToggleButton = DrawingArea = Widget


class FillRecentTests(unittest.TestCase):
    def make(self):
        w = editor('_add_recent_colors', '_refresh_recent', '_recent_toggled',
                   '_apply_recent', '_sync_palette_selection', env={'Gtk':FakeGtk})
        w.color_buttons = {'#eb3024':Widget(), '#26a269':Widget()}
        w.fill_buttons = {'#eb3024':Widget(), '#26a269':Widget()}
        w.custom_stroke, w.custom_fill = Widget(), Widget()
        w.color, w.fill_color = '#eb3024', '#eb3024'
        w.recent_panel = None
        w.fill_recent_panel = None
        w.recent_button = None
        w.fill_recent_button = None
        w._recent_color = None
        w._syncing_palette = False
        w.settings = types.SimpleNamespace(recent_colors=lambda:['#abc123','#ff1100'])
        w._swatch_draw = lambda *args:None
        self.edits = []
        w._change_selected = lambda **kw:self.edits.append(kw)
        w._sync_custom_picker = lambda *a:None
        return w

    def test_both_rows_created_with_exactly_one_recent_color(self):
        w = self.make()
        panel = Widget()
        w._add_recent_colors(panel, fill=False)
        w._add_recent_colors(panel, fill=True)
        self.assertEqual(len(panel.children),2)
        self.assertEqual(len(w.recent_panel.children),2)  # label + swatch
        self.assertEqual(len(w.fill_recent_panel.children),2)
        self.assertEqual(w._recent_color, '#abc123')
        self.assertEqual(w.recent_button.child.draw_args[1], '#abc123')
        self.assertEqual(w.fill_recent_button.child.draw_args[1], '#abc123')
        self.assertIsNot(w.recent_button,w.fill_recent_button)

    def test_fill_recent_only_changes_fill_and_selected_annotation_fill(self):
        w = self.make()
        root = Widget()
        w._add_recent_colors(root, fill=False)
        w._add_recent_colors(root, fill=True)
        before = w.color
        w.fill_recent_button.click()
        self.assertEqual(w.fill_color, '#abc123')
        self.assertEqual(w.color, before)
        self.assertEqual(self.edits, [{'fill_color':'#abc123'}])
        self.assertTrue(w.fill_recent_button.active)
        self.assertFalse(w.recent_button.active)
        self.assertNotIn('snapmark-custom-selected',w.custom_fill.css)

    def test_stroke_recent_does_not_change_fill(self):
        w = self.make()
        root = Widget()
        w._add_recent_colors(root, fill=False)
        w._add_recent_colors(root, fill=True)
        w.recent_button.click()
        self.assertEqual(w.color,'#abc123')
        self.assertEqual(w.fill_color,'#eb3024')
        self.assertEqual(self.edits,[{'color':'#abc123'}])

    def test_refresh_updates_both_rows_and_no_duplicates(self):
        w = self.make()
        root=Widget()
        w._add_recent_colors(root, fill=False)
        w._add_recent_colors(root, fill=True)
        w.settings=types.SimpleNamespace(recent_colors=lambda:['#112233'])
        w._refresh_recent()
        self.assertEqual(len(w.recent_panel.children),2)
        self.assertEqual(len(w.fill_recent_panel.children),2)
        self.assertEqual(w.recent_button.child.draw_args[1],'#112233')
        self.assertEqual(w.fill_recent_button.child.draw_args[1],'#112233')

    def test_fill_recent_only_visible_if_shapes_and_fill_enabled(self):
        panel_method=source('_update_active_tool_properties')
        self.assertIn("if getattr(self, 'fill_recent_panel', None) is not None:",panel_method)
        self.assertIn('allow.add(self.fill_recent_panel)',panel_method)
        # It is attached to the conditionally visible fill-controls group.
        self.assertIn('if self.fill:',panel_method)
        # Recent belongs to the same source-level style_children enumeration.
        self.assertIn('self._add_recent_colors(panel, fill=True)',TEXT)
        self.assertIn("self._style_elements.append(item)",TEXT)


if __name__ == '__main__':
    unittest.main()
