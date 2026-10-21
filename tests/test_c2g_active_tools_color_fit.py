"""GUI-independent regressions: real EditorWindow methods, lightweight GTK substitutes."""
import ast
import math
import types
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'snapmark/editor.py'
TEXT = SRC.read_text('utf-8')
TREE = ast.parse(TEXT)
CLS = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'EditorWindow')


def extract(name):
    node = next(n for n in CLS.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return '\n'.join(TEXT.splitlines()[node.lineno - 1:node.end_lineno])


def real_window(*names, **values):
    body = '\n'.join(extract(n) for n in names)
    env = dict(values)
    exec(compile('class Window:\n' + body, str(SRC), 'exec'), env)
    return env['Window']()


class W:
    def __init__(self, label=''):
        self.label, self.visible, self.active = label, True, False
        self.css = set()
        self.value = None
    def set_text(self, text): self.label = text
    def set_visible(self, visible): self.visible = bool(visible)
    def set_active(self, active): self.active = bool(active)
    def get_active(self): return self.active
    def set_value(self, value): self.value = value
    def add_css_class(self, css): self.css.add(css)
    def remove_css_class(self, css): self.css.discard(css)


class Panel:
    def __init__(self, widgets): self.children = list(widgets)
    def reorder_child_after(self, child, after):
        self.children.remove(child)
        self.children.insert(self.children.index(after) + 1, child)


class Adjust:
    def __init__(self): self.value = 42
    def get_lower(self): return 0
    def set_value(self, v): self.value = v


class Tests(unittest.TestCase):
    def tool_window(self):
        glib = types.SimpleNamespace(idle_add=lambda f: f(), SOURCE_REMOVE=False)
        win = real_window('_update_active_tool_properties', '_reset_text_properties_scroll', GLib=glib)
        attrs = ['_style_header', 'font_options', 'highlight_mode_row',
                 '_stroke_color_label', '_stroke_color_box', 'recent_panel',
                 'width_label', 'width_scale', 'eraser_label', 'eraser_scale',
                 'radius_label', 'radius_scale', '_shape_separator', '_fill_row',
                 '_fill_color_label', '_fill_color_box', 'opacity_label', 'opacity_scale']
        for name in attrs: setattr(win, name, W(name))
        win._style_elements = [getattr(win, n) for n in attrs]
        win._text_style_elements = (win._style_header, win.font_options,
                                    win._stroke_color_label, win._stroke_color_box,
                                    win.recent_panel)
        win._style_panel = Panel(win._style_elements)
        win._style_scroll = types.SimpleNamespace(get_vadjustment=lambda: Adjust())
        win._selected_mark = lambda: None
        win.tool, win.fill, win.stroke = 'mosaic', False, 4.0
        win.opacity, win.effect_strength = .25, 1.0
        return win

    def test_mosaic_blur_have_only_working_block_radius_strength(self):
        win = self.tool_window()
        for tool, label in [('mosaic', 'Mosaic'), ('blur', 'Blur')]:
            win.tool = tool
            win._update_active_tool_properties()
            self.assertEqual(win._style_header.label, label)
            for name in ('_stroke_color_label', '_stroke_color_box', 'recent_panel',
                         '_fill_color_label', '_fill_color_box', '_fill_row',
                         'radius_label', 'radius_scale'):
                self.assertFalse(getattr(win, name).visible, (tool, name))
            for name in ('width_label', 'width_scale', 'opacity_label', 'opacity_scale'):
                self.assertTrue(getattr(win, name).visible, (tool, name))
            self.assertIn('Strength', win.opacity_label.label)
            self.assertEqual(win.opacity_scale.value, 100)

    def test_shapes_text_eraser_have_distinct_controls(self):
        win = self.tool_window()
        win.tool = 'rectangle'
        win._update_active_tool_properties()
        self.assertTrue(win.radius_label.visible)
        self.assertTrue(win._fill_row.visible)
        self.assertFalse(win._fill_color_label.visible)
        win.fill = True
        win._update_active_tool_properties()
        self.assertTrue(win._fill_color_label.visible)
        win.tool = 'ellipse'
        win._update_active_tool_properties()
        self.assertFalse(win.radius_label.visible)
        win.tool = 'eraser'
        win._update_active_tool_properties()
        self.assertTrue(win.eraser_scale.visible)
        self.assertFalse(win.width_scale.visible)
        self.assertFalse(win._stroke_color_box.visible)

    def test_colour_selects_exact_preset_or_single_recent(self):
        win = real_window('_sync_palette_selection')
        win.color_buttons = {'#e82c20': W('red'), '#26a269': W('green')}
        win.fill_buttons = {'#e82c20': W('red-fill')}
        win.custom_stroke, win.custom_fill, win.recent_button = W(), W(), W()
        win._recent_color = '#aeacac'
        win._syncing_palette = False
        win.color, win.fill_color = '#e82c20', '#e82c20'
        win._sync_palette_selection()
        self.assertTrue(win.color_buttons['#e82c20'].active)
        self.assertFalse(win.recent_button.active)
        win.color = '#aeacac'
        win._sync_palette_selection()
        self.assertFalse(win.color_buttons['#e82c20'].active)
        self.assertTrue(win.recent_button.active)
        win.color = '#123456'
        win._sync_palette_selection()
        self.assertFalse(win.recent_button.active)
        self.assertIn('snapmark-custom-selected', win.custom_stroke.css)
        win.fill_color = '#e82c20'
        win._sync_palette_selection(fill=True)
        self.assertTrue(win.fill_buttons['#e82c20'].active)
        self.assertNotIn('snapmark-custom-selected', win.custom_fill.css)

    def test_recent_one_last_used_and_custom_callback_resync(self):
        self.assertIn('recent[0].lower()', extract('_refresh_recent'))
        self.assertNotIn('recent[:5]', extract('_refresh_recent'))
        self.assertIn('self._sync_palette_selection(fill=fill)', extract('_color_chosen'))
        self.assertIn('self._sync_palette_selection(fill=False)', extract('_color_toggled'))
        self.assertIn('self._sync_palette_selection(fill=True)', extract('_fill_color_toggled'))

    def test_fit_follows_layout_but_respects_manual_zoom(self):
        pending = []
        glib = types.SimpleNamespace(SOURCE_REMOVE=False, SOURCE_CONTINUE=True,
                                     timeout_add=lambda _delay, cb: pending.append(cb))
        def fit(a,b,w,h): return min(1.0,w/a,h/b)
        def clamp(x,a,b): return max(a,min(b,x))
        win = real_window('_schedule_auto_fit', '_apply_fit_to_viewport', 'set_zoom',
                          GLib=glib, fit_zoom=fit, clamp=clamp, math=math)
        win.pixbuf = types.SimpleNamespace(get_width=lambda:1600, get_height=lambda:1000)
        size = {'w':800, 'h':330}
        win.scroller = types.SimpleNamespace(get_allocated_width=lambda:size['w'],
                                            get_allocated_height=lambda:size['h'])
        win.canvas = types.SimpleNamespace(set_content_width=lambda x:None,
                                           set_content_height=lambda x:None,
                                           queue_draw=lambda:None)
        win.zoom_label = W()
        win._auto_fit_image, win._fit_generation = True, 0
        win._schedule_auto_fit()
        pending.pop()()
        self.assertAlmostEqual(win.zoom, .3)
        size['h'] = 800
        win._schedule_auto_fit()
        pending.pop()()
        self.assertGreater(win.zoom, .45)
        win.set_zoom(1.25)
        win._schedule_auto_fit()
        self.assertAlmostEqual(win.zoom, 1.25)
        self.assertFalse(win._auto_fit_image)
        self.assertIn('self._schedule_auto_fit()', extract('_render_plugin_results'))


if __name__ == '__main__': unittest.main()
