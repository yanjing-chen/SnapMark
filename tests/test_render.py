"""Render every annotation on a real Pixbuf (when GI is available).

Importing paint_document DIRECTLY must register Cairo's GI foreign Context
conversion, even when snapmark.app has not been imported.
"""
import io
import unittest

try:
    import cairo
    import gi
except ImportError:
    cairo = GdkPixbuf = paint_document = Mark = None
else:
    # If GI is installed but Cairo foreign types are missing, this must FAIL,
    # not silently mark the rendering regression as skipped.
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    from snapmark.paint import paint_document
    from snapmark.model import Mark


@unittest.skipIf(cairo is None, 'PyGObject / pycairo not installed')
class PaintTests(unittest.TestCase):
    def test_full_document_render_all_tools(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 128, 96)
        pixbuf.fill(0xffffffff)
        marks = [
            Mark('rectangle', 3, 3, 45, 45),
            Mark('triangle', 10, 10, 60, 70, fill=True),
            Mark('ellipse', 10, 20, 60, 55),
            Mark('line', 4, 90, 75, 45),
            Mark('arrow', 4, 4, 70, 40),
            Mark('pen', 0, 0, 22, 22, points=[(0, 0), (10, 20), (22, 22)]),
            Mark('highlighter', 0, 0, 35, 35, points=[(0, 0), (12, 30), (35, 35)]),
            Mark('mosaic', 40, 40, 85, 80),
            Mark('text', 5, 5, 5, 5, text='SnapMark', font='Sans 11'),
        ]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 128, 96)
        paint_document(cairo.Context(surface), pixbuf, marks)
        output = io.BytesIO()
        surface.write_to_png(output)
        self.assertTrue(output.getvalue().startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertGreater(len(output.getvalue()), 100)

    def test_render_modified_layer_with_original_pixels(self):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 64, 64)
        pixbuf.fill(0xffffffff)
        marks = [Mark('rectangle', 2, 2, 30, 30, color='#3584e4')]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
        paint_document(cairo.Context(surface), pixbuf, marks)
        self.assertNotEqual(surface.get_data(), b'')


if __name__ == '__main__':
    unittest.main()
