"""Watcher event tests (executed by CI when PyGObject is available)."""
import tempfile
import time
import unittest
from pathlib import Path

try:
    from gi.repository import Gio, GLib
    from snapmark.watch import ScreenshotWatcher
except (ImportError, ValueError):
    Gio = GLib = ScreenshotWatcher = None


@unittest.skipIf(Gio is None, 'PyGObject not installed')
class ScreenshotWatcherTests(unittest.TestCase):
    @staticmethod
    def process_events(seconds=1.2):
        until = time.monotonic() + seconds
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            while context.pending():
                context.iteration(False)
            time.sleep(0.015)

    def test_created_changed_only_opens_once(self):
        with tempfile.TemporaryDirectory() as temp:
            screenshots = Path(temp) / '图片' / '截图'
            screenshots.mkdir(parents=True)
            path = screenshots / '截图 2026-10-13 23-34-45.png'
            events = []
            watcher = ScreenshotWatcher(events.append, directories=[screenshots])
            self.assertEqual(len(watcher.start()), 1)
            path.write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(100))
            f = Gio.File.new_for_path(str(path))
            watcher._on_changed(None, f, None, Gio.FileMonitorEvent.CREATED)
            watcher._on_changed(None, f, None, Gio.FileMonitorEvent.CHANGES_DONE_HINT)
            self.process_events()
            self.assertEqual(events, [path])
            watcher._on_changed(None, f, None, Gio.FileMonitorEvent.CHANGES_DONE_HINT)
            self.process_events()
            self.assertEqual(events, [path])

    def test_ignore_unrelated_image(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / 'holiday.png'
            path.write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(100))
            events = []
            watcher = ScreenshotWatcher(events.append, directories=[folder])
            watcher._on_changed(None, Gio.File.new_for_path(str(path)), None,
                                Gio.FileMonitorEvent.CREATED)
            self.process_events(.4)
            self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
