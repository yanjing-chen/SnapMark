"""OCR4 session screenshot quick-entry eligibility and expiration."""
import unittest
from snapmark.screenshot_session import ScreenshotSession, PNG_MAGIC

class ScreenshotSessionTests(unittest.TestCase):
    def setUp(self):
        self.t = [100.0]
        self.gate = ScreenshotSession(clock=lambda: self.t[0])
        self.png = PNG_MAGIC + b'12345678'

    def test_cannot_use_previous_session_clipboard(self):
        self.assertFalse(self.gate.eligible(60))
        self.assertIsNone(self.gate.current_png(60))

    def test_new_image_enabled_then_expires(self):
        self.assertTrue(self.gate.record(self.png))
        self.assertEqual(self.gate.current_png(60), self.png)
        self.t[0] += 59.9
        self.assertTrue(self.gate.eligible(60))
        self.t[0] += .1
        self.assertFalse(self.gate.eligible(60))
        self.assertIsNone(self.gate.current_png(60))

    def test_zero_disable_and_invalid_timeout(self):
        self.gate.record(self.png)
        for seconds in (0, -1, 3601, True, '60'):
            self.assertFalse(self.gate.eligible(seconds))
        self.assertTrue(self.gate.eligible(3600))

    def test_clipboard_changed_to_text_invalidates(self):
        self.gate.record(self.png)
        self.gate.clear()
        self.assertFalse(self.gate.eligible(60))
        self.assertFalse(self.gate.record(b'not-png'))
        self.assertFalse(self.gate.eligible(60))

    def test_clock_backwards_disallowed(self):
        self.gate.record(self.png)
        self.t[0] -= 1
        self.assertFalse(self.gate.eligible(60))

if __name__ == '__main__': unittest.main()
