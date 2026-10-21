"""C2-G single-line swatch layout contracts; no display/GPU required."""
from __future__ import annotations
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / 'snapmark/editor.py'

def method(name):
    source=EDITOR.read_text('utf-8')
    tree=ast.parse(source)
    cls=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EditorWindow']
    assert len(cls)==1
    m=[n for n in cls[0].body if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(m)==1
    return ''.join(source.splitlines(keepends=True)[m[0].lineno-1:m[0].end_lineno])

class CompactOneLineColorTests(unittest.TestCase):
    def test_two_rows_are_not_scrolled_and_not_wrapped(self):
        s=method('_build_properties')
        self.assertNotIn('Gtk.FlowBox()',s)
        self.assertNotIn('stroke_scroll = Gtk.ScrolledWindow()',s)
        self.assertNotIn('fill_scroll = Gtk.ScrolledWindow()',s)
        self.assertEqual(s.count('Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)'),2)
        self.assertEqual(s.count('Gtk.ScrolledWindow()'),2) # styles and layers vertical only

    def test_fixed_row_fits_even_minimum_sidebar_width(self):
        # Properties has 246px minimum and 12px margins on both sides.
        min_available=246-12*2
        actual=8*26+7*1
        self.assertEqual(actual,215)
        self.assertLessEqual(actual,min_available)
        s=method('_build_properties')
        self.assertEqual(s.count('b.set_size_request(26, 26)'),2)
        self.assertEqual(s.count('        palette.set_halign(Gtk.Align.START)'),1)
        self.assertEqual(s.count('fill_palette.set_halign(Gtk.Align.START)'),1)

    def test_css_sizes_main_and_custom_picker_consistently(self):
        s=method('_build_ui')
        self.assertIn('.palette button { padding: 0; margin: 0; min-width: 26px; min-height: 26px;',s)
        self.assertIn('button.snapmark-custom-color { padding: 0; margin: 0; min-width: 26px;',s)
        self.assertIn('.palette button:checked',s)
        self.assertIn('background-color: alpha(@accent_bg_color, 0.15)',s)

    def test_all_eight_buttons_and_color_callbacks_unchanged(self):
        s=method('_build_properties')
        for expected in ('palette.append(b)','palette.append(self.custom_stroke)',
                         'fill_palette.append(b)','fill_palette.append(self.custom_fill)',
                         "b.connect('toggled', self._color_toggled, shade)",
                         "b.connect('toggled', self._fill_color_toggled, shade)"):
            self.assertIn(expected,s)
        self.assertEqual(s.count('marker.set_halign(Gtk.Align.CENTER)'),2)

    def test_text_layers_and_selected_center_untouched(self):
        source=EDITOR.read_text('utf-8')
        s=method('_build_properties')
        self.assertIn('stroke_scroll.get_prev_sibling()',s)
        self.assertIn('self._text_style_elements',s)
        self.assertIn('self.properties_split.set_end_child(layers_box)',s)
        self.assertIn('self.font_options',s)
        self.assertIn('cr.arc(_w / 2.0, _h / 2.0',method('_swatch_draw'))
        self.assertIn('# C2G_PALETTE_ALLOCATED_CENTER',source)

if __name__=='__main__': unittest.main()
