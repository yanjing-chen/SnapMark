"""Watch GNOME screenshot output without modifying Print Screen bindings."""
import os
import time
from pathlib import Path
from gi.repository import Gio, GLib

from .screenshot_paths import (is_screenshot_folder, is_screenshot_name,
                               monitored_directories, IMAGE_SUFFIXES)


def _pictures_directory() -> Path:
    location = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    return Path(location) if location else Path.home() / 'Pictures'


def screenshot_directories() -> list[Path]:
    return monitored_directories(_pictures_directory())


class ScreenshotWatcher:
    """Watch existing screenshot folders and discover newly created ones."""

    def __init__(self, callback, directories=None):
        self.callback = callback
        self.pictures = _pictures_directory().resolve(strict=False)
        self.directories = directories if directories is not None else screenshot_directories()
        self.monitors = []
        self.watched: set[Path] = set()
        self.pending: dict[Path, tuple[int, int]] = {}
        self.seen: set[tuple[str, int, int]] = set()
        self.start_time = time.time()
        custom = os.getenv('SNAPMARK_SCREENSHOT_DIR')
        self.custom_dir = Path(custom).expanduser().resolve(strict=False) if custom else None

    def _add_directory(self, path: Path) -> bool:
        path = path.resolve(strict=False)
        if path in self.watched or not path.is_dir():
            return False
        try:
            monitor = Gio.File.new_for_path(str(path)).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None)
            monitor.connect('changed', self._on_changed)
            self.monitors.append(monitor)
            self.watched.add(path)
            return True
        except GLib.Error as exc:
            print(f'SnapMark: cannot monitor {path}: {exc}', flush=True)
            return False

    def start(self) -> list[Path]:
        for directory in self.directories:
            self._add_directory(Path(directory))
        return sorted(self.watched, key=str)

    def _queue(self, path: Path):
        if path.suffix.casefold() not in IMAGE_SUFFIXES or path in self.pending:
            return
        # Avoid opening unrelated images placed under Pictures. A deliberate
        # custom directory override may contain arbitrarily named images.
        if not (is_screenshot_name(path.name)
                or (self.custom_dir is not None and path.parent == self.custom_dir)):
            return
        self.pending[path] = (-1, 0)
        GLib.timeout_add(250, self._check_stable, path)

    def _on_changed(self, _monitor, file, other, event):
        allowed = (Gio.FileMonitorEvent.CREATED,
                   Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                   Gio.FileMonitorEvent.MOVED_IN,
                   Gio.FileMonitorEvent.RENAMED)
        if event not in allowed:
            return
        target = other if event == Gio.FileMonitorEvent.RENAMED and other else file
        name = target.get_path() if target is not None else None
        if not name:
            return
        path = Path(name).resolve(strict=False)
        # React if GNOME creates a localized screenshot folder after startup.
        if path.parent == self.pictures and path.is_dir() and is_screenshot_folder(path.name):
            if self._add_directory(path):
                print(f'SnapMark: discovered screenshot folder {path}', flush=True)
                try:
                    for child in path.iterdir():
                        if child.is_file() and child.stat().st_mtime >= self.start_time - 3:
                            self._queue(child)
                except OSError:
                    pass
            return
        if path.parent in self.watched:
            self._queue(path)

    def _check_stable(self, path: Path) -> bool:
        previous, attempts = self.pending.get(path, (-1, 0))
        try:
            stat = path.stat()
            if not path.is_file() or stat.st_mtime < self.start_time - 3:
                self.pending.pop(path, None)
                return False
            if stat.st_size < 16 or stat.st_size != previous:
                if attempts >= 24:
                    self.pending.pop(path, None)
                    print(f'SnapMark: screenshot not ready: {path}', flush=True)
                    return False
                self.pending[path] = (stat.st_size, attempts + 1)
                return True
            key = (str(path), stat.st_size, stat.st_mtime_ns)
            self.pending.pop(path, None)
            if key not in self.seen:
                self.seen.add(key)
                if len(self.seen) > 400:
                    self.seen.clear()
                print(f'SnapMark: opening screenshot {path}', flush=True)
                self.callback(path)
        except (OSError, ValueError) as exc:
            self.pending.pop(path, None)
            print(f'SnapMark: screenshot read failed: {path}: {exc}', flush=True)
        return False
