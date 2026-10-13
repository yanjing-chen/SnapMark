import unittest
from snapmark.model import Mark, History, clamp, fit_zoom


class ModelTests(unittest.TestCase):
    def test_round_trip(self):
        h = History()
        m = Mark('rectangle', 1, 2, 40, 60)
        self.assertTrue(h.push(m))
        self.assertTrue(h.undo())
        self.assertEqual(h.marks, [])
        self.assertTrue(h.redo())
        self.assertEqual(h.marks, [m])

    def test_new_edit_clears_redo(self):
        h = History()
        h.push(Mark('line', 0, 0, 10, 10))
        h.undo()
        h.push(Mark('arrow', 0, 0, 20, 10))
        self.assertFalse(h.redo())

    def test_reject_empty(self):
        self.assertFalse(History().push(Mark('line', 0, 0, 0, 0)))
        self.assertTrue(History().push(Mark('text', 0, 0, 0, 0, text='你好')))

    def test_fit(self):
        self.assertEqual(fit_zoom(2000, 1000, 1000, 1000), .5)
        self.assertEqual(fit_zoom(500, 300, 1000, 1000), 1)
        self.assertEqual(clamp(15, 0, 10), 10)
