"""Image-source erasing and pixel-opacity regression tests.

The Cairo/GI checks are run by the GTK4 GitHub Actions job. They are skipped
when only the pure Python model is installed locally.
"""
import unittest
from snapmark.model import History, Mark, mark_bounds, mark_touches, resized, translated

try:
    import cairo
    import gi
except ImportError:
    cairo = None
else:
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GLib, GdkPixbuf
    from snapmark.paint import paint_document


class EraserLayerTests(unittest.TestCase):
    def test_eraser_is_real_undoable_layer_and_does_not_delete_marks(self):
        history = History()
        self.assertTrue(history.push(Mark('rectangle', 5, 5, 15, 15)))
        self.assertTrue(history.push(Mark('eraser', 20, 20, 20, 20,
                                          points=[(20, 20)], width=7)))
        self.assertEqual([m.tool for m in history.marks], ['rectangle', 'eraser'])
        self.assertTrue(history.undo())
        self.assertEqual([m.tool for m in history.marks], ['rectangle'])
        self.assertTrue(history.redo())
        self.assertEqual([m.tool for m in history.marks], ['rectangle', 'eraser'])

    def test_eraser_move_resize_and_hit_testing(self):
        mark = Mark('eraser', 2, 3, 22, 23, width=5,
                    points=[(2, 3), (12, 13), (22, 23)])
        self.assertTrue(mark_touches(mark, 12, 13))
        self.assertEqual(translated(mark, 10, 5).points[0], (12, 8))
        self.assertNotEqual(resized(mark, (0, 0, 60, 60)).points, mark.points)
        self.assertGreater(mark_bounds(mark)[2], 22)


@unittest.skipIf(cairo is None, 'Requires Cairo + PyGObject runtime')
class RenderEraserAndOpacityTests(unittest.TestCase):
    @staticmethod
    def sample_pixbuf():
        w, h = 64, 48
        pixels = bytearray()
        for y in range(h):
            for x in range(w):
                pixels.extend(((x * 17 + y * 3) % 256,
                               (x * 7 + y * 11) % 256,
                               (x * 2 + y * 19) % 256, 255))
        return GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(bytes(pixels)), GdkPixbuf.Colorspace.RGB,
            True, 8, w, h, w * 4)

    def render(self, marks):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 48)
        cr = cairo.Context(surface)
        paint_document(cr, self.sample_pixbuf(), marks)
        surface.flush()
        return bytes(surface.get_data())

    @staticmethod
    def alpha_at(data, x, y):
        offset = (y * 64 + x) * 4
        # The alpha byte is last on little-endian; first on big-endian.
        import sys
        return data[offset + (3 if sys.byteorder == 'little' else 0)]

    def test_eraser_removes_original_pixels_to_alpha(self):
        before = self.render([])
        eraser = Mark('eraser', 5, 20, 45, 20, width=7,
                      points=[(5, 20), (45, 20)])
        after = self.render([eraser])
        self.assertEqual(self.alpha_at(before, 20, 20), 255)
        self.assertEqual(self.alpha_at(after, 20, 20), 0)
        self.assertEqual(self.alpha_at(after, 20, 2), 255)

    def test_one_click_erase_clears_pixels(self):
        after = self.render([Mark('eraser', 10, 12, 10, 12, width=5,
                                  points=[(10, 12)])])
        self.assertEqual(self.alpha_at(after, 10, 12), 0)

    def test_mosaic_and_blur_opacity_affects_output(self):
        before = self.render([])
        for tool in ('mosaic', 'blur'):
            def mark(opacity):
                return Mark(tool, 7, 8, 48, 39, width=7, opacity=opacity)
            zero = self.render([mark(0)])
            half = self.render([mark(.5)])
            full = self.render([mark(1)])
            self.assertEqual(zero, before, f'{tool}: zero opacity must be unchanged')
            self.assertNotEqual(full, before, f'{tool}: 100% must alter image')
            self.assertNotEqual(half, before, f'{tool}: 50% must alter image')
            self.assertNotEqual(half, full, f'{tool}: 50% and 100% must differ')


if __name__ == '__main__':
    unittest.main()
