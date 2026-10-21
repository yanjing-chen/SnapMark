"""C2-G color palette structural regressions; no GTK display required."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT/'snapmark/editor.py').read_text('utf-8')

def method(name):
    tree = ast.parse(source)
    cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EditorWindow']
    assert len(cls) == 1
    fn = [n for n in cls[0].body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(fn) == 1
    lines = source.splitlines(keepends=True)
    return ''.join(lines[fn[0].lineno - 1:fn[0].end_lineno])

class ColorPaletteTests(unittest.TestCase):
    def test_both_palettes_are_compact_single_rows(self):
        s=method('_build_properties')
        self.assertEqual(s.count('Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)'),2)
        self.assertNotIn('Gtk.FlowBox()',s)
        self.assertNotIn('set_max_children_per_line(4)',s)
        self.assertEqual(s.count('b.set_size_request(26, 26)'),2)

    def test_no_horizontal_scroll_container_over_color_swatch(self):
        s=method('_build_properties')
        self.assertNotIn('stroke_scroll = Gtk.ScrolledWindow()',s)
        self.assertNotIn('fill_scroll = Gtk.ScrolledWindow()',s)
        self.assertNotIn('Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER',s)
        self.assertIn('side_scroll = Gtk.ScrolledWindow()',s)
        self.assertIn('layer_scroll = Gtk.ScrolledWindow()',s)

    def test_all_buttons_and_custom_colors_migrate(self):
        s=method('_build_properties')
        for token in ('            palette.append(b)', '        palette.append(self.custom_stroke)',
                      '            fill_palette.append(b)', '        fill_palette.append(self.custom_fill)'):
            self.assertEqual(s.count(token),1)
        for token in ('self.color_buttons[shade] = b', 'self.fill_buttons[shade] = b',
                      'b.connect(\'toggled\', self._color_toggled',
                      'b.connect(\'toggled\', self._fill_color_toggled'):
            self.assertIn(token,s)

    def test_text_properties_and_layout_not_regressed(self):
        s=method('_build_properties')
        self.assertIn('stroke_scroll.get_prev_sibling()',s)
        self.assertIn('stroke_scroll, self.recent_panel',s)
        self.assertIn('self.properties_split.set_end_child(layers_box)',s)
        self.assertIn('self.width_scale',s)
        self.assertIn('self.opacity_scale',s)
        self.assertIn('self.font_options',s)
        self.assertIn('self.properties_split',s)

    def test_selected_swatch_styles_and_cairo_center_remain(self):
        ui=method('_build_ui')
        self.assertIn('.palette button:checked',ui)
        swatch=method('_swatch_draw')
        self.assertIn('cr.arc(_w / 2.0, _h / 2.0',swatch)

if __name__=='__main__': unittest.main()
