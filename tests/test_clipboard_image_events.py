"""Execute actual app.py clipboard callbacks in pure-Python mocked GDK.

This tests the exact application callback logic, without a GTK display.
"""
import ast
import types
import unittest
from pathlib import Path

from snapmark.clipboard_images import clipboard_image_state
from snapmark.screenshot_session import ScreenshotSession, PNG_MAGIC

APP = Path(__file__).resolve().parents[1] / 'snapmark/app.py'


class FakeFormats:
    def __init__(self, mimes=()):
        self.mimes = mimes
    def get_mime_types(self):
        return self.mimes
    def get_gtypes(self):
        return ()
    def contain_gtype(self, _):
        return False


class FakeGLib:
    Error = Exception
    SOURCE_REMOVE = False
    queued = []
    @classmethod
    def timeout_add(cls, milliseconds, callback):
        assert milliseconds == 180
        cls.queued.append(callback)
        return 1


class FakeGdk:
    class Texture:
        __gtype__ = 'GdkTexture'


class FakeBytes:
    def get_data(self):
        return PNG_MAGIC + b'fake-png-from-image-copy'


class FakeTexture:
    def save_to_png_bytes(self):
        return FakeBytes()


class FakeClipboard:
    def __init__(self, mimes=('image/png',), deferred=False):
        self.mimes = mimes
        self.reads = 0
        self.deferred = deferred
        self.callbacks = []
    def get_formats(self):
        return FakeFormats(self.mimes)
    def read_texture_async(self, cancellable, callback):
        self.reads += 1
        if self.deferred:
            self.callbacks.append(callback)
        else:
            callback(self, object())
    def read_texture_finish(self, result):
        return FakeTexture()
    def deliver(self):
        for callback in self.callbacks:
            callback(self, object())
        self.callbacks.clear()


class MockApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enabled = True
        class Settings:
            def monitor_clipboard_images(_self):
                return cls.enabled
        code = ast.parse(APP.read_text(encoding='utf-8'))
        appclass = next(node for node in code.body if isinstance(node, ast.ClassDef)
                        and node.name == 'SnapMarkApplication')
        names = {'_clipboard_changed', '_retry_clipboard_image', '_read_clipboard_screenshot'}
        methods = [node for node in appclass.body if isinstance(node, ast.FunctionDef)
                   and node.name in names]
        assert len(methods) == len(names)
        mod = ast.Module(body=methods, type_ignores=[])
        ast.fix_missing_locations(mod)
        ctx = {'Settings': Settings, 'Gdk': FakeGdk, 'GLib': FakeGLib,
               'clipboard_image_state': clipboard_image_state}
        exec(compile(mod, str(APP), 'exec'), ctx)
        cls.Callbacks = type('Callbacks', (), {name: ctx[name] for name in names})

    def setUp(self):
        MockApp.enabled = True
        FakeGLib.queued = []
        self.app = self.Callbacks()
        self.app._clipboard_generation = 0
        self.clock = [100.]
        self.app._screenshot_session = ScreenshotSession(clock=lambda: self.clock[0])
        self.app.refreshes = 0
        self.app.refresh_recent_screenshot_status = lambda: setattr(
            self.app, 'refreshes', self.app.refreshes + 1)

    def test_copy_web_image_records_and_reenables_after_expiry(self):
        self.assertFalse(self.app._screenshot_session.eligible(60))
        image = FakeClipboard(['text/html', 'image/png'])
        self.app._clipboard_changed(image)
        self.assertEqual(image.reads, 1)
        self.assertEqual(self.app.refreshes, 1)
        self.assertTrue(self.app._screenshot_session.eligible(60))
        self.clock[0] += 61
        self.assertFalse(self.app._screenshot_session.eligible(60))
        self.app._clipboard_changed(image)
        self.assertTrue(self.app._screenshot_session.eligible(60))
        self.assertEqual(image.reads, 2)

    def test_text_html_and_link_copy_never_read_a_payload(self):
        for mimes in (['text/plain'], ['text/html', 'text/plain'],
                      ['text/uri-list'], ['application/x-gnome-copied-files']):
            clip = FakeClipboard(mimes)
            self.app._clipboard_changed(clip)
            self.assertEqual(clip.reads, 0)
            self.assertEqual(FakeGLib.queued, [])
            self.assertIsNone(self.app._screenshot_session.current_png(60))

    def test_disable_prevents_new_image_read(self):
        MockApp.enabled = False
        image = FakeClipboard()
        self.app._clipboard_changed(image)
        self.assertEqual(image.reads, 0)
        self.assertEqual(self.app.refreshes, 0)

    def test_disable_during_inflight_read_disallows_record(self):
        image = FakeClipboard(deferred=True)
        self.app._clipboard_changed(image)
        MockApp.enabled = False
        image.deliver()
        self.assertFalse(self.app._screenshot_session.eligible(60))

    def test_text_after_image_keeps_existing_quick_action(self):
        image = FakeClipboard()
        self.app._clipboard_changed(image)
        self.app._clipboard_changed(FakeClipboard(['text/plain']))
        self.assertTrue(self.app._screenshot_session.eligible(60))
        self.assertEqual(self.app.refreshes, 1)

    def test_empty_formats_rechecks_only_after_signal(self):
        clip = FakeClipboard(())
        self.app._clipboard_changed(clip)
        self.assertEqual(clip.reads, 0)
        self.assertEqual(len(FakeGLib.queued), 1)
        clip.mimes = ('image/jpeg',)
        FakeGLib.queued.pop()()
        self.assertEqual(clip.reads, 1)
        self.assertEqual(self.app.refreshes, 1)


if __name__ == '__main__':
    unittest.main()
