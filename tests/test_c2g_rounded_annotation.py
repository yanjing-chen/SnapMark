"""C2-G rounded corners and annotation-only erasing; no system model calls."""
import ast
import math
import unittest
from pathlib import Path
from snapmark.model import Mark, History, resized

try:
    import cairo
except ImportError:
    cairo = None

ROOT = Path(__file__).resolve().parents[1]
PAINT = ROOT / 'snapmark' / 'paint.py'
EDITOR = ROOT / 'snapmark' / 'editor.py'


def cairo_render_functions():
    """Load real Cairo drawing functions with a fake Gdk source surface.

    Allows pure graphics unit tests without a GNOME display or installed GI.
    The production tests additionally import the actual GdkPixbuf on Code01.
    """
    source = PAINT.read_text('utf-8')
    tree = ast.parse(source)
    keep = {'hex_rgba', 'fill_or_stroke', 'rounded_rectangle_path',
            'rounded_triangle_path', 'paint_mark', 'paint_document'}
    pieces = [ast.get_source_segment(source, node) for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name in keep]

    class GdkFake:
        @staticmethod
        def cairo_set_source_pixbuf(cr, surf, x, y):
            cr.set_source_surface(surf, x, y)

    scope = {'cairo': cairo, 'math': math, 'Gdk': GdkFake,
             'PangoCairo': None, 'Pango': None}
    exec(compile('\n\n'.join(pieces), str(PAINT), 'exec'), scope)
    return scope


def sample_surface():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 96, 80)
    cr = cairo.Context(surface)
    cr.set_source_rgb(.16, .55, .78)
    cr.paint()
    return surface


def pixel(data, x, y, stride):
    off = y * stride + x * 4
    return bytes(data[off:off+4])


class GeometryHistoryTests(unittest.TestCase):
    def test_default_zero_compatibility_and_roundtrip(self):
        mark = Mark('rectangle', 5, 7, 75, 55)
        self.assertEqual(mark.corner_radius, 0)
        rounded = Mark('triangle', 10, 10, 70, 70, corner_radius=15)
        history = History()
        self.assertTrue(history.push(rounded))
        self.assertTrue(history.undo())
        self.assertTrue(history.redo())
        self.assertEqual(history.marks[0].corner_radius, 15)
        self.assertNotEqual(resized(rounded, (10, 10, 40, 40)).corner_radius, 15)

    def test_sidebar_and_new_mark_store_corner_radius(self):
        src = EDITOR.read_text('utf-8')
        for item in ("label='Corner radius · 0 px'", 'def _radius_changed(',
                     "selected.tool in ('rectangle', 'triangle')",
                     "corner_radius=(self.corner_radius if self.tool in ('rectangle', 'triangle')",
                     'self.radius_scale.set_value('):
            self.assertIn(item, src)
        for item in ('self.eraser_label', 'self.eraser_scale',
                     "m.tool not in ('eraser', 'mosaic', 'blur')"):
            self.assertIn(item, src)

    def test_erasure_is_composited_only_in_annotation_group(self):
        src = PAINT.read_text('utf-8')
        body = src[src.index('def paint_document('):]
        self.assertIn('cr.push_group()', body)
        self.assertIn('cr.pop_group_to_source()', body)
        self.assertIn("if mark.tool not in ('mosaic', 'blur')", body)
        self.assertNotIn('cairo.OPERATOR_CLEAR', body)


@unittest.skipIf(cairo is None, 'Requires PyCairo')
class CairoImageTests(unittest.TestCase):
    def setUp(self):
        self.fn = cairo_render_functions()['paint_document']
        self.source = sample_surface()

    def render(self, marks, preview=None):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 96, 80)
        self.fn(cairo.Context(surf), self.source, marks, preview)
        surf.flush()
        return surf

    def color(self, surf, x, y):
        return pixel(surf.get_data(), x, y, surf.get_stride())

    def test_eraser_with_no_marks_changes_nothing(self):
        original = self.render([])
        eraser = Mark('eraser', 10, 40, 80, 40, width=19, points=[(10,40),(80,40)])
        self.assertEqual(bytes(original.get_data()), bytes(self.render([eraser]).get_data()))

    def test_eraser_removes_only_local_stroke_not_base(self):
        original = self.render([])
        pen = Mark('pen', 10, 40, 80, 40, '#e82c20', width=10,
                   points=[(10,40), (80,40)])
        eraser = Mark('eraser', 46, 40, 46, 40, width=17, points=[(46,40)])
        with_stroke = self.render([pen])
        erased = self.render([pen, eraser])
        self.assertNotEqual(self.color(original, 46, 40), self.color(with_stroke, 46, 40))
        self.assertEqual(self.color(original, 46, 40), self.color(erased, 46, 40))
        self.assertEqual(self.color(erased, 20, 40), self.color(with_stroke, 20, 40))
        self.assertEqual(self.color(original, 46, 15), self.color(erased, 46, 15))
        preview = self.render([pen], eraser)
        self.assertEqual(self.color(erased, 46, 40), self.color(preview, 46, 40))

    def test_new_mark_after_eraser_not_erased(self):
        pen = Mark('pen', 10, 40, 80, 40, '#e82c20', width=9,
                   points=[(10,40),(80,40)])
        eraser = Mark('eraser', 46, 40, 46, 40, width=20, points=[(46,40)])
        blue = Mark('pen', 30, 40, 70, 40, '#3584e4', width=4,
                    points=[(30,40),(70,40)])
        base=self.render([])
        cleared=self.render([pen,eraser])
        result=self.render([pen,eraser,blue])
        self.assertEqual(self.color(cleared,46,40),self.color(base,46,40))
        self.assertNotEqual(self.color(result,46,40),self.color(base,46,40))

    def test_rectangle_rounding_changes_corner_but_not_interior(self):
        plain = Mark('rectangle', 10, 10, 75, 60, '#e82c20', width=2,
                     fill=True, opacity=1)
        round_ = Mark('rectangle', 10, 10, 75, 60, '#e82c20', width=2,
                      fill=True, opacity=1, corner_radius=20)
        sharp = self.render([plain]); rounded=self.render([round_]); base=self.render([])
        self.assertNotEqual(self.color(sharp,13,13),self.color(rounded,13,13))
        self.assertEqual(self.color(rounded,13,13),self.color(base,13,13))
        self.assertEqual(self.color(sharp,40,35),self.color(rounded,40,35))

    def test_triangle_rounded_and_radius_clamped_when_tiny(self):
        plain=Mark('triangle', 12, 10, 80, 70, '#e82c20', fill=True, opacity=1)
        round_=Mark('triangle', 12, 10, 80, 70, '#e82c20', fill=True,
                    opacity=1, corner_radius=15)
        a=self.render([plain]); b=self.render([round_])
        self.assertNotEqual(bytes(a.get_data()),bytes(b.get_data()))
        small=Mark('triangle', 30, 30, 33, 32, '#e82c20',fill=True,
                   corner_radius=1000)
        self.render([small]) # Degenerate sizes must not trigger cairo errors.


if __name__=='__main__':
    unittest.main()
