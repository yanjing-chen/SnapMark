"""C2-G Text sidebar: source contracts and executable tool-switch tests."""
import ast
import os
import types
import unittest
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / 'snapmark/editor.py'
SOURCE_FILE = Path(os.environ.get('SNAPMARK_C2G_EDITOR_SOURCE', str(DEFAULT)))


def source_and_class():
    text = SOURCE_FILE.read_text('utf-8')
    tree = ast.parse(text)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EditorWindow']
    assert len(classes) == 1, 'EditorWindow missing or duplicated'
    return text, classes[0]


def method(name):
    text, cls = source_and_class()
    hits = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(hits) == 1, 'Method missing or duplicated: ' + name
    lines = text.splitlines(keepends=True)
    return ''.join(lines[hits[0].lineno - 1:hits[0].end_lineno])


class Widget:
    def __init__(self, label=''):
        self.label = label
        self.visible = True
    def set_visible(self, value): self.visible = bool(value)
    def set_text(self, value): self.label = value

class Panel:
    def __init__(self, children): self.children = list(children)
    def reorder_child_after(self, widget, after):
        self.children.remove(widget)
        self.children.insert(self.children.index(after) + 1, widget)

class Adjustment:
    def __init__(self): self.value = 99
    def get_lower(self): return 0
    def set_value(self, value): self.value = value

class TextPropertiesTests(unittest.TestCase):
    def test_tool_selection_reconciles_font_and_color(self):
        for name in ('_tool_toggled', '_sync_selected_properties', 'select_layer'):
            self.assertIn('self._update_active_tool_properties()', method(name))

    def test_builder_preserves_scrolling_and_layers(self):
        builder = method('_build_properties')
        self.assertIn('self._style_scroll = side_scroll', builder)
        self.assertIn('self._style_panel = panel', builder)
        self.assertIn('self._text_style_elements', builder)
        self.assertIn('self.properties_split.set_end_child(layers_box)', builder)

    def fake_window(self):
        code = ('class Window:\n' + method('_update_active_tool_properties') +
                method('_reset_text_properties_scroll'))
        scope = {'GLib': types.SimpleNamespace(SOURCE_REMOVE=False,
                                               idle_add=lambda fn: fn())}
        exec(compile(code, '<snapmark_real_sidebar_methods>', 'exec'), scope)
        window = scope['Window']()
        window._style_header = Widget('Stroke')
        window.font_options = Widget('Text font and size')
        window.highlight_mode_row = Widget('Highlight mode')
        color_label = Widget('Color')
        palette = Widget('Palette')
        recent = Widget('Recent')
        width = Widget('Width')
        fill = Widget('Fill')
        window.opacity_scale = Widget('Opacity')
        window._style_elements = [window._style_header, window.highlight_mode_row,
                                   color_label, palette, recent, width, fill,
                                   window.opacity_scale, window.font_options]
        window._style_text_visible_unused = None
        window._text_style_elements = (window._style_header, window.font_options,
                                        color_label, palette, recent)
        window._style_panel = Panel(window._style_elements)
        adjustment = Adjustment()
        window._style_scroll = types.SimpleNamespace(get_vadjustment=lambda: adjustment)
        window.tool = 'select'
        window.selected = None
        window._selected_mark = lambda: window.selected
        return window, adjustment, color_label, palette, width, fill

    def test_text_tool_font_and_color_are_first_and_visible(self):
        win, adj, color, palette, width, fill = self.fake_window()
        win.tool = 'text'
        win._update_active_tool_properties()
        self.assertEqual(win._style_header.label, 'Text')
        self.assertIs(win._style_panel.children[1], win.font_options)
        self.assertTrue(win.font_options.visible)
        self.assertTrue(color.visible)
        self.assertTrue(palette.visible)
        self.assertFalse(width.visible)
        self.assertFalse(fill.visible)
        self.assertEqual(adj.value, 0)

    def test_switching_tools_restores_settings_and_highlighter(self):
        win, _, _, _, width, fill = self.fake_window()
        win.tool = 'text'
        win._update_active_tool_properties()
        win.tool = 'rectangle'
        win._update_active_tool_properties()
        self.assertFalse(win.font_options.visible)
        self.assertTrue(width.visible)
        self.assertTrue(fill.visible)
        self.assertIs(win._style_panel.children[-1], win.font_options)
        self.assertEqual(win._style_header.label, 'Stroke')
        win.tool = 'highlighter'
        win._update_active_tool_properties()
        self.assertTrue(win.highlight_mode_row.visible)

    def test_select_existing_text_layer_shows_font_and_deselect_restores(self):
        win, _, _, _, width, _ = self.fake_window()
        win.selected = types.SimpleNamespace(tool='text')
        win._update_active_tool_properties()
        self.assertTrue(win.font_options.visible)
        self.assertFalse(width.visible)
        win.selected = None
        win._update_active_tool_properties()
        self.assertFalse(win.font_options.visible)
        self.assertTrue(width.visible)

if __name__ == '__main__': unittest.main()
