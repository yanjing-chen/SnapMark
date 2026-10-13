"""Watch GNOME screenshot output, without modifying Print Screen bindings."""
import os
import time
from pathlib import Path
from gi.repository import Gio, GLib


VALID_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}


def screenshot_directories() -> list[Path]:
    pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    pictures = Path(pictures) if pictures else Path.home() / 'Pictures'
    # GNOME uses a localized Pictures directory, but 'Screenshots' is
    # normally the unlocalized subdirectory. Also include translated names.
    candidates = [pictures / 'Screenshots', pictures / '屏幕截图', pictures / '截屏',
                  Path.home() / 'Pictures' / 'Screenshots']
    seen: set[Path] = set()
    return [p for p in candidates if not (p in seen or seen.add(p))]


class ScreenshotWatcher:
    def __init__(self, callback, directories=None):
        self.callback = callback
        self.directories = directories or screenshot_directories()
        self.monitors = []
        self.pending: dict[Path, tuple[int, int]] = {}
        self.seen: set[tuple[str, int, int]] = set()
        self.start_time = time.time()

    def start(self) -> list[Path]:
        watched = []
        for path in self.directories:
            if not path.is_dir():
                continue
            try:
                monitor = Gio.File.new_for_path(str(path)).monitor_directory(
                    Gio.FileMonitorFlags.WATCH_MOVES, None)
                monitor.connect('changed', self._on_changed)
                self.monitors.append(monitor)
                watched.append(path)
            except GLib.Error as exc:
                print(f'SnapMark: cannot monitor {path}: {exc}', flush=True)
        return watched

    def _on_changed(self, _monitor, file, _other, event):
        if event not in (Gio.FileMonitorEvent.CREATED,
                         Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                         Gio.FileMonitorEvent.MOVED_IN):
            return
        filename = file.get_path()
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() not in VALID_EXTENSIONS or path in self.pending:
            return
        self.pending[path] = (-1, 0)
        GLib.timeout_add(250, self._check_stable, path)

    def _check_stable(self, path: Path) -> bool:
        prior_size, attempts = self.pending.get(path, (-1, 0))
        try:
            stat = path.stat()
            if not path.is_file() or stat.st_mtime < self.start_time - 3:
                self.pending.pop(path, None)
                return False
            if stat.st_size < 16 or stat.st_size != prior_size:
                if attempts >= 24:
                    self.pending.pop(path, None)
                    return False
                self.pending[path] = (stat.st_size, attempts + 1)
                return True
            key = (str(path), stat.st_size, stat.st_mtime_ns)
            self.pending.pop(path, None)
            if key not in self.seen:
                self.seen.add(key)
                if len(self.seen) > 400:
                    self.seen.clear()
                self.callback(path)
        except (OSError, ValueError):
            self.pending.pop(path, None)
        return False
