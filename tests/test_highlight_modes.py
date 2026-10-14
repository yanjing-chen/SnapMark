"""Highlight Freehand vs Straight line: stable editable Mark models."""
import unittest
from snapmark.model import (History, Mark, mark_touches, mark_bounds,
                            update_highlighter_preview, translated, resized)


class HighlightModeTests(unittest.TestCase):
    def preview(self, mode):
        return Mark('highlighter', 2, 4, 2, 4, points=[(2, 4)],
                    highlighter_mode=mode, opacity=.35)

    def test_line_follows_only_first_and_last_position(self):
        mark = self.preview('line')
        for x, y in [(10, 40), (30, 2), (50, 40)]:
            update_highlighter_preview(mark, x, y)
        self.assertEqual(mark.points, [(2, 4), (50, 40)])
        self.assertEqual((mark.x2, mark.y2), (50, 40))
        self.assertTrue(mark.is_meaningful())
        self.assertTrue(mark_touches(mark, 26, 22))
        self.assertEqual(mark.highlighter_mode, 'line')

    def test_freehand_keeps_entire_path(self):
        mark = self.preview('freehand')
        for x, y in [(10, 40), (30, 2), (50, 40)]:
            update_highlighter_preview(mark, x, y)
        self.assertEqual(mark.points, [(2, 4), (10, 40), (30, 2), (50, 40)])
        self.assertTrue(mark.is_meaningful())

    def test_no_movement_does_not_create_layer(self):
        for mode in ('freehand', 'line'):
            mark = self.preview(mode)
            if mode == 'line':
                update_highlighter_preview(mark, 2, 4)
            self.assertFalse(mark.is_meaningful())

    def test_line_preserves_mode_in_layers_undo_resize_recolor(self):
        mark = self.preview('line')
        update_highlighter_preview(mark, 50, 40)
        history = History()
        self.assertTrue(history.push(mark))
        self.assertEqual(history.marks[0].highlighter_mode, 'line')
        recolored = translated(history.marks[0], 3, 2)
        recolored.color = '#26a269'
        self.assertTrue(history.replace(0, recolored))
        self.assertTrue(history.undo())
        self.assertEqual(history.marks[0].color, mark.color)
        self.assertTrue(history.redo())
        sized = resized(history.marks[0], (10, 20, 90, 75))
        self.assertEqual(len(sized.points), 2)
        self.assertEqual(sized.highlighter_mode, 'line')
        self.assertNotEqual(mark_bounds(sized), mark_bounds(mark))

    def test_invalid_mode_rejected_on_preview_update(self):
        mark = self.preview('invalid')
        with self.assertRaises(ValueError):
            update_highlighter_preview(mark, 20, 30)

    def test_non_highlighter_cannot_use_mode_helper(self):
        with self.assertRaises(ValueError):
            update_highlighter_preview(Mark('pen', 0, 0, 0, 0), 3, 5)


if __name__ == '__main__':
    unittest.main()
