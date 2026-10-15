"""C2 OCR source-image geometry and annotation separation contracts."""
import ast
import math
import unittest
from pathlib import Path

from snapmark.ocr_selection_c2 import normalize_region

ROOT = Path(__file__).resolve().parents[1]


class OCRGeometryTests(unittest.TestCase):
    def test_original_coordinate_rectangle(self):
        self.assertEqual(normalize_region((13.1, 20.6, 80.0, 50.1), 200, 100),
                         (13, 20, 80, 51))

    def test_reverse_drag(self):
        self.assertEqual(normalize_region((90, 80, 10, 20), 100, 90), (10, 20, 90, 80))

    def test_clamp_to_image(self):
        self.assertEqual(normalize_region((-10, -20, 110, 120), 100, 90), (0, 0, 100, 90))

    def test_too_small_rejected(self):
        for rect in [(3, 4, 3, 4), (0, 0, 1, 1), (30, 30, 35, 30)]:
            with self.subTest(rect=rect), self.assertRaises(ValueError):
                normalize_region(rect, 100, 90)

    def test_invalid_float_rejected(self):
        for val in [float('nan'), float('inf'), -float('inf')]:
            with self.subTest(val=val), self.assertRaises(ValueError):
                normalize_region((val, 0, 10, 10), 100, 90)

    def test_crop_never_scales_or_paints_annotation(self):
        text = (ROOT / 'snapmark/ocr_selection_c2.py').read_text()
        body = text.split('def original_pixbuf_png', 1)[1]
        self.assertNotIn('paint_document(', body)
        self.assertNotIn('history.marks', body)
        self.assertIn('Gdk.cairo_set_source_pixbuf', body)
        self.assertIn('normalize_region', body)

    def test_editor_draw_overlay_is_not_in_saved_png(self):
        text = (ROOT / 'snapmark/editor.py').read_text()
        export = text.split('    def _render_png(self)', 1)[1].split('    def copy_image', 1)[0]
        self.assertNotIn('_ocr_region_preview', export)
        self.assertIn('paint_document(', export)
        self.assertIn('def request_ocr_region', text)
        self.assertIn('def cancel_ocr_region', text)
        ast.parse(text)

    def test_escape_cancel_and_photo_change_cancel(self):
        text = (ROOT / 'snapmark/editor.py').read_text()
        self.assertIn('keyval == Gdk.KEY_Escape', text)
        block = text.split('    def load_image', 1)[1].split('    def _delayed_fit', 1)[0]
        self.assertIn('self.cancel_ocr_region()', block)


if __name__ == '__main__':
    unittest.main()
