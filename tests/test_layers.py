"""Layer edit regression tests; no graphical environment required."""
import unittest
from copy import deepcopy
from snapmark.model import History, Mark, mark_bounds, resized, translated


class LayerTests(unittest.TestCase):
    def make_layers(self):
        history = History()
        history.push(Mark('rectangle', 10, 10, 70, 50, color='#e82c20'))
        history.push(Mark('text', 25, 40, 25, 40, text='Hello', font='Sans 20'))
        history.push(Mark('pen', 5, 5, 50, 50,
                          points=[(5, 5), (9, 16), (50, 50)]))
        return history

    def test_blur_layer_is_editable(self):
        from snapmark.model import Mark, History, translated, mark_touches
        h = History()
        self.assertTrue(h.push(Mark('blur', 5, 5, 42, 48)))
        self.assertTrue(mark_touches(h.marks[0], 20, 20))
        self.assertTrue(h.replace(0, translated(h.marks[0], 10, 20)))
        self.assertTrue(h.undo())
        self.assertEqual(h.marks[0].x1, 5)
        self.assertTrue(h.redo())
        self.assertEqual(h.marks[0].x1, 15)

    def test_layer_order_and_topmost_hit(self):
        history = History()
        history.push(Mark('rectangle', 0, 0, 50, 50, fill=True))
        history.push(Mark('rectangle', 10, 10, 60, 60, fill=True))
        self.assertEqual(history.index_at_point(25, 25), 1)
        self.assertEqual(history.index_at_point(3, 3, radius=0), 0)
        self.assertIsNone(history.index_at_point(120, 120))

    def test_move_preserves_original_and_point_array(self):
        h = self.make_layers()
        old = deepcopy(h.marks[2])
        moved = translated(h.marks[2], 10, -7)
        self.assertEqual(h.marks[2], old)
        self.assertEqual(moved.points[1], (19, 9))
        self.assertTrue(h.replace(2, moved))
        self.assertTrue(h.undo())
        self.assertEqual(h.marks[2], old)
        self.assertTrue(h.redo())
        self.assertEqual(h.marks[2], moved)

    def test_resize_line_and_freehand(self):
        h = self.make_layers()
        pen = h.marks[2]
        resized_pen = resized(pen, (10, 20, 110, 140))
        bounds = mark_bounds(resized_pen)
        self.assertAlmostEqual(bounds[0], 10, delta=4)
        self.assertAlmostEqual(bounds[2], 110, delta=4)
        self.assertEqual(len(resized_pen.points), 3)
        self.assertTrue(h.replace(2, resized_pen))
        self.assertTrue(h.undo())
        self.assertEqual(h.marks[2], pen)

    def test_text_font_scales_with_box(self):
        text = Mark('text', 5, 5, 5, 5, text='Hello', font='Noto Sans 20')
        x0, y0, x1, y1 = mark_bounds(text)
        changed = resized(text, (x0, y0, x1 * 2, y1 * 2))
        self.assertNotEqual(text.font, changed.font)
        self.assertTrue(changed.font.startswith('Noto Sans'))

    def test_recolor_and_width_are_one_undo_each(self):
        h = self.make_layers()
        new = deepcopy(h.marks[0])
        new.color = '#3584e4'
        self.assertTrue(h.replace(0, new))
        new2 = deepcopy(new)
        new2.width = 10
        self.assertTrue(h.replace(0, new2))
        self.assertFalse(h.replace(0, new2))
        self.assertTrue(h.undo())
        self.assertEqual(h.marks[0].color, '#3584e4')
        self.assertEqual(h.marks[0].width, 4)
        self.assertTrue(h.undo())
        self.assertEqual(h.marks[0].color, '#e82c20')
        self.assertTrue(h.redo())
        self.assertEqual(h.marks[0].color, '#3584e4')

    def test_delete_undo_redo(self):
        h = self.make_layers()
        self.assertFalse(h.delete(99))
        self.assertTrue(h.delete(1))
        self.assertEqual([m.tool for m in h.marks], ['rectangle', 'pen'])
        self.assertTrue(h.undo())
        self.assertEqual([m.tool for m in h.marks], ['rectangle', 'text', 'pen'])
        self.assertTrue(h.redo())
        self.assertEqual(len(h.marks), 2)

    def test_external_mutation_does_not_modify_history(self):
        h = self.make_layers()
        original = h.marks[2]
        moved = translated(original, 5, 5)
        h.replace(2, moved)
        moved.points[0] = (999, 999)
        h.undo()
        self.assertEqual(h.marks[2].points[0], (5, 5))
        h.redo()
        self.assertEqual(h.marks[2].points[0], (10, 10))

    def test_empty_changes_do_not_create_history(self):
        h = History()
        h.push(Mark('text', 0, 0, 0, 0, text='X'))
        self.assertFalse(h.replace(0, h.marks[0]))
        self.assertTrue(h.undo())
        self.assertEqual(h.marks, [])
        self.assertFalse(h.undo())


if __name__ == '__main__':
    unittest.main()
