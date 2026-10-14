"""Blur is deterministic and does not require GTK/Xvfb."""
import unittest
from snapmark.filters import box_blur_bytes


class BlurTests(unittest.TestCase):
    def test_softens_sharp_edge(self):
        pixels = bytes([0, 0, 0] * 3 + [255, 255, 255] * 4)
        result = box_blur_bytes(pixels, 7, 1, 3, 2)
        self.assertEqual(len(result), len(pixels))
        self.assertTrue(0 < result[3 * 3] < 255)
        self.assertNotEqual(pixels, result)

    def test_preserves_alpha(self):
        rgba = bytes([0, 0, 0, 11, 255, 255, 255, 22, 0, 0, 0, 33])
        out = box_blur_bytes(rgba, 3, 1, 4, 1)
        self.assertEqual(out[3::4], bytes([11, 22, 33]))

    def test_small_images_and_bad_channels(self):
        self.assertEqual(box_blur_bytes(b'', 0, 0, 3, 4), b'')
        self.assertEqual(box_blur_bytes(b'abc', 1, 1, 3, 4), b'abc')
        self.assertEqual(box_blur_bytes(b'1234', 1, 1, 2, 4), b'1234')

    def test_uniform_color_unchanged(self):
        pixels = bytes([17, 25, 133] * (5 * 9))
        self.assertEqual(box_blur_bytes(pixels, 5, 9, 3, 20), pixels)


if __name__ == '__main__':
    unittest.main()
