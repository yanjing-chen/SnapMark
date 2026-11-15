"""Clipboard Wayland focus and stream lifecycle regression contracts."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'snapmark/app.py').read_text(encoding='utf-8')
TRAY = (ROOT / 'snapmark/tray.py').read_text(encoding='utf-8')

class ClipboardProbeReliability(unittest.TestCase):
    def test_syntax(self):
        ast.parse(APP)
        ast.parse(TRAY)

    def test_present_before_clipboard_probe(self):
        open_now = APP.split('    def open_recent_screenshot(self):')[1].split('    def open_history(self):')[0]
        self.assertIn('self._ensure_focus_for_clipboard()', open_now)
        self.assertIn('GLib.timeout_add(220, self._pending_clipboard_retry, 4)', open_now)
        self.assertNotIn('self.probe_clipboard_now(force=True)', open_now)

    def test_explicit_probes_not_persistent_polling(self):
        self.assertIn('def _pending_clipboard_retry(', APP)
        self.assertIn('if not self._pending_open:', APP)
        self.assertNotIn('def _poll_clipboard(', APP)

    def test_only_one_image_read_path_selected(self):
        f = APP.split('    def probe_clipboard_now(')[1].split('    def _pending_clipboard_retry(')[0]
        self.assertIn('if mimes:', f)
        self.assertIn('self._probe_clipboard_stream(', f)
        self.assertIn('else:', f)
        self.assertIn('self._read_clipboard_screenshot(', f)

    def test_stream_is_closed_on_finish_failure_or_stale(self):
        self.assertIn('self._close_clipboard_stream(stream)', APP)
        self.assertIn('stream.close(None)', APP)
        self.assertIn('if len(chunks) + len(data) > 32 * 1024 * 1024', APP)

    def test_name_and_monitor_pref(self):
        self.assertIn('编辑/识别当前图片', TRAY)
        self.assertIn('Edit/Recognize Current Image', TRAY)
        self.assertIn('Settings().monitor_clipboard_images() or self.recent_screenshot_eligible()', APP)

if __name__ == '__main__':
    unittest.main()
