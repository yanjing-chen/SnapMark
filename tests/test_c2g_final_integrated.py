"""C2-G final integrated: real source contracts and small executable rendering tests.

No network calls, no Runtime API changes, no changes to user preferences.
"""
import ast
import math
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / 'snapmark/editor.py'


def source_method(name):
    source = EDITOR.read_text(encoding='utf-8')
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EditorWindow']
    assert len(nodes) == 1
    methods = [n for n in nodes[0].body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(methods) == 1
    lines = source.splitlines(keepends=True)
    return ''.join(lines[methods[0].lineno-1:methods[0].end_lineno])


class CairoRecorder:
    def __init__(self):
        self.circles = []
        self.rectangles = []
        self.fills = 0
    def set_source_rgba(self,*args): pass
    def set_source_rgb(self,*args): pass
    def arc(self,x,y,r,a,b): self.circles.append((x,y,r))
    def rectangle(self,x,y,w,h): self.rectangles.append((x,y,w,h))
    def fill(self): self.fills += 1


def real_static(name):
    scope = {'math':math, 'hex_rgba': lambda c: (1,0,0,1)}
    exec(compile('class Widget:\n' + source_method(name),'<editor-swatch>','exec'),scope)
    return getattr(scope['Widget'],name)


class FinalIntegratedTests(unittest.TestCase):
    def test_swatch_drawn_at_actual_canvas_center(self):
        fn = real_static('_swatch_draw')
        for width,height in [(20,20),(24,20),(34,34),(40,28)]:
            cr = CairoRecorder()
            fn(None,cr,width,height,'#e82c20')
            self.assertEqual(len(cr.circles),1)
            x,y,r = cr.circles[0]
            self.assertAlmostEqual(x,width/2)
            self.assertAlmostEqual(y,height/2)
            self.assertGreater(r,0)
            self.assertLessEqual(r,min(width,height)/2)
            self.assertEqual(cr.fills,1)

    def test_custom_color_tile_is_centered(self):
        fn=real_static('_custom_color_icon')
        for width,height in [(22,22),(34,34),(30,24)]:
            cr=CairoRecorder(); fn(None,cr,width,height)
            self.assertEqual(len(cr.rectangles),4)
            x0=min(r[0] for r in cr.rectangles)
            y0=min(r[1] for r in cr.rectangles)
            right=max(r[0]+r[2] for r in cr.rectangles)
            bottom=max(r[1]+r[3] for r in cr.rectangles)
            self.assertAlmostEqual((x0+right)/2,width/2)
            self.assertAlmostEqual((y0+bottom)/2,height/2)

    def test_both_stroke_fill_toggles_center_content(self):
        s=source_method('_build_properties')
        self.assertEqual(s.count('b.set_size_request(26, 26)'),2)
        self.assertEqual(s.count('marker.set_halign(Gtk.Align.CENTER)'),2)
        self.assertEqual(s.count('marker.set_valign(Gtk.Align.CENTER)'),2)
        self.assertEqual(s.count('marker.set_hexpand(False)'),2)
        self.assertEqual(s.count('marker.set_vexpand(False)'),2)

    def test_selection_css_only_targets_palette(self):
        s=source_method('_build_ui')
        self.assertIn('.palette button:checked',s)
        self.assertIn('background-color: alpha(@accent_bg_color, 0.15)',s)
        self.assertIn('box-shadow: none;',s)
        self.assertIn('.snapmark-window windowcontrols',s)
        self.assertNotIn('font-family:',s)

    def test_font_is_prioritized_for_active_and_existing_text(self):
        source=EDITOR.read_text(encoding='utf-8')
        for term in ('def _update_active_tool_properties',
                     'self._style_panel.reorder_child_after(self.font_options',
                     'self._reset_text_properties_scroll',
                     'self._text_style_elements'):
            self.assertIn(term,source)
        self.assertIn('self.properties_split.set_end_child(layers_box)',source)

    def test_original_tool_controls_and_result_split_remain(self):
        src=EDITOR.read_text(encoding='utf-8')
        for term in ('_result_split','self._plugin_visibility',
                     'def _render_plugin_results','def original_png_for_ocr',
                     'self.width_scale','self.fill_switch','self.opacity_scale'):
            self.assertIn(term,src)

    def test_clipboard_history_and_output_format_sources_untouched(self):
        self.assertTrue((ROOT/'snapmark/history_c2g.py').is_file())
        self.assertTrue((ROOT/'snapmark/tray.py').is_file())
        pref=(ROOT/'snapmark/preferences.py').read_text('utf-8')
        self.assertIn('image_format',pref)
        history=(ROOT/'snapmark/history_c2g.py').read_text('utf-8')
        self.assertIn('load_more',history)
        self.assertIn('history_paths',history)

if __name__=='__main__': unittest.main()
