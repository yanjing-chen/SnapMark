"""OCR4 Fix3 checks that screenshot detection does not depend on opening a window.

GUI behaviour is additionally checked on the user's GNOME machine; these pure
source contracts run in container CI where PyGObject is not installed.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'snapmark'


def read(name):
    s = (ROOT / name).read_text(encoding='utf-8')
    ast.parse(s)
    return s


class ScreenshotActivationContracts(unittest.TestCase):
    def test_background_folder_watcher_enabled(self):
        app = read('app.py')
        start = app.split('    def start_watching(self):', 1)[1]
        self.assertIn('ScreenshotWatcher(self._record_screenshot_file)', start)
        self.assertIn('watcher.start()', start)
        self.assertIn('self.hold()', start)

    def test_saved_screenshot_is_recorded_without_opening_editor(self):
        app = read('app.py')
        method = app.split('    def _record_screenshot_file(self, path):', 1)[1].split('    def _clipboard_changed(', 1)[0]
        self.assertIn('Gdk.Texture.new_from_filename', method)
        self.assertIn('self._screenshot_session.record(png)', method)
        self.assertIn('self.refresh_recent_screenshot_status()', method)
        self.assertNotIn('self.show_editor', method)
        self.assertNotIn('ocr_toggle', method)

    def test_clipboard_retry_and_nonimage_does_not_erase_snapshot(self):
        app = read('app.py')
        method = app.split('    def _clipboard_changed(', 1)[1].split('    def open_recent_screenshot', 1)[0]
        self.assertIn('attempts_remaining=3', method)
        self.assertIn('GLib.timeout_add(180, retry)', method)
        self.assertNotIn('self._screenshot_session.clear()', method)

    def test_tray_requests_fresh_layout_on_open(self):
        tray = read('tray.py')
        about = tray.split("elif name == 'AboutToShow':", 1)[1].split('else:', 1)[0]
        self.assertIn("GLib.Variant('(b)', (True,))", about)
        self.assertIn('self.refresh_clipboard_status()', about)
        self.assertIn('list(ids)', about)

    def test_autostart_does_not_disable_running_watcher(self):
        editor = read('editor.py')
        toggle = editor.split('        def toggle_switch(', 1)[1].split('        toggle_handler =', 1)[0]
        self.assertIn('autostart.set_enabled', toggle)
        self.assertNotIn('stop_watching()', toggle)

    def test_click_only_opens_editor_and_no_automatic_ocr(self):
        app = read('app.py')
        click = app.split('    def open_recent_screenshot(self):', 1)[1].split('    def open_history(self):', 1)[0]
        self.assertIn('self.show_editor(Path(name))', click)
        self.assertNotIn('ocr_toggle', click)
        self.assertNotIn('.run(', click)


if __name__ == '__main__':
    unittest.main()
