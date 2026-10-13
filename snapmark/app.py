"""GTK4 application, CLI entry point, and screenshot watcher lifecycle."""
import sys
from pathlib import Path
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_foreign('cairo')

from gi.repository import Adw, Gio, GLib
from .editor import EditorWindow
from .watch import ScreenshotWatcher

APP_ID = 'io.github.yanjingchen.SnapMark'


class SnapMarkApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.watcher = None
        self.windows = []
        self.add_main_option('watch', 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             'Watch GNOME screenshots in the background', None)
        self.add_main_option('open', 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             'Open an existing screenshot', 'FILE')
        self.add_main_option('smoke-test', 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             'Test the installed GUI and exit', None)

    def do_activate(self):
        self.show_editor()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        if options.contains('watch'):
            self.start_watching()
            return 0
        if options.contains('open'):
            value = options.lookup_value('open', GLib.VariantType.new('s'))
            if value:
                self.show_editor(Path(value.get_string()))
                return 0
        self.activate()
        if options.contains('smoke-test'):
            GLib.timeout_add(1000, self._end_smoke)
        return 0

    def _end_smoke(self):
        self.quit()
        return False

    def show_editor(self, path=None):
        window = EditorWindow(self, filename=path)
        self.windows.append(window)
        window.connect('close-request', lambda w: self._remove_window(w))

    def _remove_window(self, window):
        if window in self.windows:
            self.windows.remove(window)
        return False

    def start_watching(self):
        if self.watcher is not None:
            return
        self.watcher = ScreenshotWatcher(self.show_editor)
        watched = self.watcher.start()
        if not watched:
            print('SnapMark: no screenshot folders available for monitoring', flush=True)
            self.watcher = None
            return
        for directory in watched:
            print(f'SnapMark: watching {directory}', flush=True)
        self.hold()


def main():
    app = SnapMarkApplication()
    return app.run(sys.argv)


if __name__ == '__main__':
    raise SystemExit(main())
