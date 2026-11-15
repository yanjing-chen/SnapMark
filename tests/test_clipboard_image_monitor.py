"""Image-only, event-driven clipboard behavior; runs without PyGObject."""
import ast
import tempfile
import unittest
from pathlib import Path

from snapmark.clipboard_images import clipboard_image_state
from snapmark.preferences import Settings

ROOT = Path(__file__).resolve().parents[1]


class FakeFormats:
    def __init__(self, mime=(), gtypes=()):
        self._mime = tuple(mime)
        self._gtypes = tuple(gtypes)

    def get_mime_types(self):
        return self._mime

    def get_gtypes(self):
        return self._gtypes

    def contain_gtype(self, gtype):
        return gtype in self._gtypes


class ImageOnlyFormats(unittest.TestCase):
    def test_all_supported_web_image_types(self):
        for mime in ('image/png', 'image/jpeg', 'image/webp', 'image/tiff',
                     'image/bmp', 'image/gif', 'image/avif'):
            with self.subTest(mime=mime):
                self.assertEqual('image', clipboard_image_state(FakeFormats([mime])))

    def test_image_and_html_is_still_real_image(self):
        self.assertEqual('image', clipboard_image_state(
            FakeFormats(['text/html', 'image/png', 'text/plain'])))

    def test_text_links_html_and_file_uri_are_not_images(self):
        for mimes in (["text/plain"], ["text/html", "text/plain"],
                      ["text/uri-list"], ["application/x-gnome-copied-files"]):
            self.assertEqual('other', clipboard_image_state(FakeFormats(mimes)))

    def test_support_in_process_texture_without_mime(self):
        texture_type = object()
        self.assertEqual('image', clipboard_image_state(
            FakeFormats(gtypes=[texture_type]), texture_type))

    def test_await_transitional_empty_formats_only(self):
        self.assertEqual('empty', clipboard_image_state(None))
        self.assertEqual('empty', clipboard_image_state(FakeFormats()))
        self.assertEqual('other', clipboard_image_state(FakeFormats(['text/plain'])))


class ImageClipboardPreference(unittest.TestCase):
    def test_switch_defaults_on_and_persists_off_and_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Settings(root=tmp)
            self.assertTrue(cfg.monitor_clipboard_images())
            cfg.set_monitor_clipboard_images(False)
            self.assertFalse(Settings(root=tmp).monitor_clipboard_images())
            cfg.set_monitor_clipboard_images(True)
            self.assertTrue(Settings(root=tmp).monitor_clipboard_images())

    def test_ignore_non_boolean_config_and_reject_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Settings(root=tmp)
            (Path(tmp)/'preferences.json').write_text('{"monitor_clipboard_images": "no"}')
            self.assertFalse(cfg.monitor_clipboard_images())
            with self.assertRaises(ValueError):
                cfg.set_monitor_clipboard_images(1)


class NoPollingIntegrationContracts(unittest.TestCase):
    def test_clipboard_filters_before_texture_read(self):
        app = (ROOT / 'snapmark' / 'app.py').read_text(encoding='utf-8')
        ast.parse(app)
        method = app.split('    def _read_clipboard_screenshot(', 1)[1].split(
            '    def open_recent_screenshot(', 1)[0]
        self.assertLess(method.index('clipboard_image_state(clipboard.get_formats()'),
                        method.index('clipboard.read_texture_async('))
        self.assertIn("if state != 'image':", method)
        self.assertIn('Settings().monitor_clipboard_images()', app)
        self.assertNotIn('read_text_async(', app)
        self.assertNotIn('read_text_finish(', app)
        self.assertNotIn('def _poll_clipboard(', app)

    def test_original_file_watcher_tray_and_manual_ocr_remain(self):
        app = (ROOT / 'snapmark' / 'app.py').read_text()
        self.assertIn('ScreenshotWatcher(self._record_screenshot_file)', app)
        self.assertIn("display.get_clipboard().connect('changed', self._clipboard_changed)", app)
        self.assertIn('self.show_editor(Path(name))', app)
        self.assertNotIn('self.ocr_toggle.set_active(True)',
                         app.split('    def open_recent_screenshot(self):', 1)[1].split('    def open_history(', 1)[0])
        tray = (ROOT / 'snapmark' / 'tray.py').read_text()
        self.assertIn('self.registration_target = self.name or ITEM_PATH', tray)
        self.assertIn('self.clipboard_ready()', tray)

    def test_preference_switch_visible_in_screenshot_settings(self):
        editor = (ROOT / 'snapmark' / 'editor.py').read_text()
        self.assertIn("image_monitor = Adw.SwitchRow(", editor)
        self.assertIn('self.settings.set_monitor_clipboard_images(row.get_active())', editor)
        self.assertIn('screenshot_group.add(image_monitor)', editor)


if __name__ == '__main__':
    unittest.main()
