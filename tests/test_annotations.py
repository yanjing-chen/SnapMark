"""Regression coverage for new tools and eraser command grouping."""
import unittest
from snapmark.model import Mark, History, mark_touches


class AnnotationTests(unittest.TestCase):
    def test_new_shapes_are_meaningful(self):
        for tool in ('triangle', 'mosaic'):
            self.assertTrue(Mark(tool, 0, 0, 50, 40).is_meaningful())
            self.assertFalse(Mark(tool, 0, 0, 0, 0).is_meaningful())

    def test_highlight_stroke(self):
        mark = Mark('highlighter', 0, 0, 20, 20, points=[(0, 0), (20, 20)])
        self.assertTrue(mark.is_meaningful())
        self.assertTrue(mark_touches(mark, 10, 10))

    def test_eraser_preserves_image_annotation_history(self):
        h = History()
        h.push(Mark('rectangle', 0, 0, 90, 90))
        h.push(Mark('text', 100, 100, 100, 100, text='NOTE', font='Serif 24'))
        h.begin_erase()
        self.assertTrue(h.erase_at(0, 40))
        self.assertTrue(h.erase_at(110, 115))
        h.end_erase()
        self.assertEqual(len(h.marks), 0)
        self.assertTrue(h.undo())
        self.assertEqual(len(h.marks), 2)
        self.assertTrue(h.redo())
        self.assertEqual(len(h.marks), 0)

    def test_do_nothing_eraser_does_not_create_undo_step(self):
        h = History()
        h.begin_erase()
        self.assertFalse(h.erase_at(12, 12))
        h.end_erase()
        self.assertFalse(h.undo())

    def test_mosaic_is_inside_rectangle(self):
        mark = Mark('mosaic', 30, 30, 70, 80)
        self.assertTrue(mark_touches(mark, 50, 50))
        self.assertFalse(mark_touches(mark, 110, 110))

    def test_text_font_preserved(self):
        m = Mark('text', 1, 1, 1, 1, text='你好', font='Noto Sans CJK SC 23')
        h = History()
        h.push(m)
        h.undo()
        h.redo()
        self.assertEqual(h.marks[0].font, 'Noto Sans CJK SC 23')


if __name__ == '__main__':
    unittest.main()
