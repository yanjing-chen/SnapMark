"""Quick action must be clickable and reconcile the clipboard on demand.

Static contracts guard the GTK4 integration; the behavior test executes the
real de-duplication/cache method from app.py under a mocked application.
"""
import ast
import hashlib
import unittest
from pathlib import Path

from snapmark.clipboard_images import PNG_MAGIC, image_to_png
from snapmark.screenshot_session import ScreenshotSession

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'snapmark' / 'app.py'
TRAY = ROOT / 'snapmark' / 'tray.py'


class QuickActionContracts(unittest.TestCase):
    def setUp(self):
        self.app = APP.read_text(encoding='utf-8')
        self.tray = TRAY.read_text(encoding='utf-8')
        ast.parse(self.app)
        ast.parse(self.tray)

    def test_no_background_clipboard_polling(self):
        self.assertNotIn('def _poll_clipboard(', self.app)
        self.assertNotIn('read_text_async(', self.app)
        self.assertNotIn('read_text_finish(', self.app)

    def test_explicit_reconciliation_points_exist(self):
        for fragment in ('def probe_clipboard_now(', 'def _probe_clipboard_stream(',
                         'def _clipboard_stream_ready(', 'def _drain_clipboard_stream(',
                         'def _accept_image(', 'def _ensure_focus_for_clipboard(',
                         'def _load_pending_into_editor(',
                         'def quick_action_available(',
                         'clipboard_probe=self.probe_clipboard_now',
                         'GLib.timeout_add(350, self._startup_clipboard_probe)',
                         'clipboard.read_async(list(mimes)',
                         'self.windows[-1].load_image(name)'):
            self.assertIn(fragment, self.app)

    def test_original_changed_signal_and_watcher_remain(self):
        self.assertIn("display.get_clipboard().connect('changed', self._clipboard_changed)",
                      self.app)
        self.assertIn('ScreenshotWatcher(self._record_screenshot_file)', self.app)

    def test_menu_open_triggers_a_probe(self):
        about = self.tray.split("elif name == 'AboutToShow':", 1)[1].split('else:', 1)[0]
        self.assertIn('self._probe_clipboard()', about)
        self.assertIn('self.refresh_clipboard_status()', about)
        self.assertIn("GLib.Variant('(b)', (True,))", about)
        self.assertIn('list(ids)', about)
        self.assertIn('clipboard_probe=None', self.tray)

    def test_enabled_contract_line_is_preserved(self):
        self.assertIn('self.clipboard_ready() if index == 2 else True', self.tray)


class DedupAndCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(APP.read_text(encoding='utf-8'))
        appclass = next(n for n in tree.body
                        if isinstance(n, ast.ClassDef) and n.name == 'SnapMarkApplication')
        names = {'quick_action_available', '_accept_image'}
        methods = [n for n in appclass.body
                   if isinstance(n, ast.FunctionDef) and n.name in names]
        assert len(methods) == len(names)
        module = ast.Module(body=methods, type_ignores=[])
        ast.fix_missing_locations(module)
        enabled = [True]

        class Settings:
            def monitor_clipboard_images(self):
                return enabled[0]

        ctx = {'Settings': Settings, 'hashlib': hashlib, 'image_to_png': image_to_png}
        exec(compile(module, str(APP), 'exec'), ctx)
        cls.Impl = type('Impl', (), {n: ctx[n] for n in names})
        cls.enabled = enabled

    def setUp(self):
        self.enabled[0] = True
        self.impl = self.Impl()
        self.impl._last_image_digest = None
        self.impl._clipboard_generation = 0
        self.impl._pending_open = False
        self.impl._screenshot_session = ScreenshotSession()
        self.impl.recent_screenshot_eligible = lambda: self.impl._screenshot_session.eligible(60)
        self.impl.refreshes = 0

        def refresh():
            self.impl.refreshes += 1

        self.impl.refresh_recent_screenshot_status = refresh

    def test_quick_action_is_clickable_for_on_demand_image_read(self):
        self.assertTrue(self.impl.quick_action_available())

    def test_monitoring_off_does_not_enable_empty_clipboard_action(self):
        self.enabled[0] = False
        self.assertFalse(self.impl.quick_action_available())

    def test_image_is_cached_once_and_duplicates_are_ignored(self):
        payload = PNG_MAGIC + b'the-same-image'
        self.impl._accept_image(payload, 'image/png')
        self.assertEqual(self.impl._screenshot_session.current_png(60), payload)
        self.assertEqual(self.impl.refreshes, 1)
        self.impl._accept_image(payload, 'image/png')
        self.assertEqual(self.impl.refreshes, 1)

    def test_probe_does_not_renew_expired_identical_image(self):
        self.impl._accept_image(PNG_MAGIC + b'identical', 'image/png')
        self.impl._screenshot_session._captured -= 65
        self.assertFalse(self.impl.recent_screenshot_eligible())
        self.impl._accept_image(PNG_MAGIC + b'identical', 'image/png')
        self.assertFalse(self.impl.recent_screenshot_eligible())
        self.impl._pending_open = True
        self.impl._accept_image(PNG_MAGIC + b'identical', 'image/png')
        self.assertTrue(self.impl.recent_screenshot_eligible())

    def test_new_image_replaces_previous_and_refreshes_menu(self):
        self.impl._accept_image(PNG_MAGIC + b'first', 'image/png')
        second = PNG_MAGIC + b'second'
        self.impl._accept_image(second, 'image/jpeg')
        self.assertEqual(self.impl._screenshot_session.current_png(60), second)
        self.assertEqual(self.impl.refreshes, 2)

    def test_monitor_disabled_blocks_caching(self):
        self.enabled[0] = False
        self.impl._accept_image(PNG_MAGIC + b'nope', 'image/png')
        self.assertIsNone(self.impl._screenshot_session.current_png(60))
        self.assertEqual(self.impl.refreshes, 0)

    def test_invalid_payload_never_cached(self):
        self.impl._accept_image(b'not-an-image', 'image/png')
        self.assertIsNone(self.impl._screenshot_session.current_png(60))
        self.assertEqual(self.impl.refreshes, 0)


if __name__ == '__main__':
    unittest.main()
