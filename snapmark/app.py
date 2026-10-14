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
from .preferences import Settings
from .tray import TrayIndicator

APP_ID = 'io.github.yanjingchen.SnapMark'


class SnapMarkApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.watcher = None
        self.windows = []
        self.tray = TrayIndicator(self.show_or_present_editor, self.show_preferences, self.quit)
        self.tray_started = False
        # Let GTK/libadwaita own the shutdown virtual method; register cleanup
        # as a signal handler instead of chaining an incompatible GI wrapper.
        self.connect('shutdown', self._on_shutdown)
        self.add_main_option('watch', 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             'Watch GNOME screenshots in the background', None)
        self.add_main_option('login-start', 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             'Start from the GNOME login session', None)
        self.add_main_option('open', 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             'Open an existing screenshot', 'FILE')
        self.add_main_option('smoke-test', 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             'Test the installed GUI and exit', None)

    def do_activate(self):
        self._start_tray()
        self.start_watching()
        if Settings().start_minimized() and self.tray.available:
            print('SnapMark: started minimized with a status indicator', flush=True)
            return
        if Settings().start_minimized() and not self.tray.available:
            print('SnapMark: no status icon host; showing editor so it remains accessible', flush=True)
        self.show_editor()

    def _start_tray(self):
        if not self.tray_started:
            self.tray_started = True
            self.tray.start()

    def show_preferences(self):
        if not self.windows:
            self.show_editor()
        self.windows[-1].show_preferences()
        return False


    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        if options.contains('watch'):
            self._start_tray()
            self.start_watching()
            return 0
        if options.contains('login-start'):
            self.activate()
            return 0
        if options.contains('open'):
            value = options.lookup_value('open', GLib.VariantType.new('s'))
            if value:
                self._start_tray()
                self.start_watching()
                self.show_editor(Path(value.get_string()))
                return 0
        if options.contains('smoke-test'):
            # GUI smoke tests must build a window even when minimized is enabled.
            self._start_tray()
            self.show_editor()
        else:
            self.activate()
        if options.contains('smoke-test'):
            GLib.timeout_add(200, self._smoke_editor)
            GLib.timeout_add(1700, self._end_smoke)
        return 0

    def _smoke_editor(self):
        # Xvfb CI verifies construction of BOTH the layers UI and Preferences.
        # Fail loudly if the new GTK4 API is unavailable in the AppImage.
        try:
            from .model import Mark
            window = self.windows[-1]
            assert window.paned is not None and window.layers is not None
            # Actually exercise the packaged executable, not Python modules
            # shadowing it from the GitHub runner's checkout directory.
            import os
            if os.environ.get('APPDIR'):
                module = Path(__file__).resolve()
                assert module.is_relative_to(Path(os.environ['APPDIR']).resolve()), (
                    f'AppImage imported external source: {module}')
                print(f'SnapMark: bundled module verified: {module}', flush=True)
                schema = Gio.SettingsSchemaSource.get_default()
                assert schema is not None, 'Bundled GLib GSettings schema source missing'
                assert any(schema.list_schemas(True)), (
                    'Bundled GSettings schemas appear to be empty')
                # If PNGs cannot be decoded from the AppDir, opening GNOME
                # screenshots will fail even though the tray icon uses Cairo.
                from gi.repository import GdkPixbuf
                icon_path = Path(os.environ['APPDIR']) / (
                    'usr/share/icons/hicolor/32x32/apps/io.github.yanjingchen.SnapMark.png')
                check_png = GdkPixbuf.Pixbuf.new_from_file(str(icon_path))
                assert check_png.get_width() == 32
            for field in ('font_options', 'custom_stroke', 'custom_fill'):
                assert getattr(window, field, None) is not None, (
                    f'Editor failed to initialize {field}')
            assert window.save_button.has_css_class('suggested-action')
            assert not window.save_button.has_css_class('snapmark-quiet')
            assert len([t for t in window.tool_buttons if t == 'highlighter']) == 1
            window.tool_buttons['highlighter'].set_active(True)
            assert window.highlight_mode_row.get_visible()
            assert window.highlight_free_button.get_active()
            window.highlight_line_button.set_active(True)
            assert window.highlight_mode == 'line'
            window.tool_buttons['select'].set_active(True)
            assert not window.highlight_mode_row.get_visible()
            window.tool_buttons['text'].set_active(True)
            assert window.font_options.get_visible()
            window.tool_buttons['select'].set_active(True)
            # Status notifier protocol and packaged icon must serialize with
            # real GLib variants, even when the runner has no tray host.
            for prop, signature in (('IconPixmap', 'a(iiay)'), ('ToolTip', '(sa(iiay)ss)'),
                                    ('Menu', 'o')):
                variant = self.tray._item_prop(None, None, None, None, prop)
                assert variant.get_type_string() == signature
            assert self.tray.pixmaps, 'AppImage status icon missing'
            assert window.custom_stroke.has_css_class('snapmark-custom-color')
            assert window.custom_fill.has_css_class('snapmark-custom-color')
            assert self.tray._item_prop(None, None, None, None, 'IconName').unpack() == ''
            window.history.push(Mark('rectangle', 5, 5, 50, 40))
            window._refresh_layers()
            assert window.layers.get_row_at_index(0) is not None
            window.select_layer(0)
            assert window.selected_index == 0
            window.show_preferences()
            assert window._preferences_window is not None
            assert window._plugin_preferences is not None
            assert window._plugin_preferences.widgets['ocr'] is not None
            assert window._plugin_preferences.widgets['translation'] is not None
            assert window._runtime_preferences.widgets['enabled'] is not None
            assert window._runtime_preferences.widgets['status'] is not None
            assert window._runtime_preferences.widgets['actual'] is not None
            assert window._runtime_preferences.widgets['preview_group'] is not None
            assert not window._preferences_window.get_modal()
            print('SnapMark: GTK4 layers + Preferences smoke PASS', flush=True)
        except Exception:
            import traceback
            import os
            traceback.print_exc()
            os._exit(1)  # Test-only failure; do not misreport a passing CI run.
        return False

    def _end_smoke(self):
        self.quit()
        return False

    def show_or_present_editor(self):
        if self.windows:
            self.windows[-1].present()
        else:
            self.show_editor()
        return False

    def show_editor(self, path=None):
        window = EditorWindow(self, filename=path)
        self.windows.append(window)
        window.connect('close-request', lambda w: self._remove_window(w))

    def _remove_window(self, window):
        if window in self.windows:
            self.windows.remove(window)
        return False

    def _on_shutdown(self, _application):
        # Cleanup only. Gtk/Adw handles parent shutdown automatically.
        self.tray.stop()

    def stop_watching(self):
        if self.watcher is None:
            return
        self.watcher.stop()
        self.watcher = None
        self.release()
        print('SnapMark: screenshot watcher stopped', flush=True)

    def refresh_watching(self):
        if self.watcher is None:
            return
        self.stop_watching()
        self.start_watching()

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
