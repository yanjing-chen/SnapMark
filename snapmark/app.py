"""GTK4 application, CLI entry point, and screenshot watcher lifecycle."""
import sys
import os
import tempfile
import subprocess
from pathlib import Path
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_foreign('cairo')

from gi.repository import Adw, Gdk, Gio, GLib
from . import __version__
from .editor import EditorWindow
from .watch import ScreenshotWatcher
from .preferences import Settings
from .i18n import configure as configure_interface_language, _
from .tray import TrayIndicator
from .history_c2g import show_history

APP_ID = 'io.github.yanjingchen.SnapMark'


class SnapMarkApplication(Adw.Application):
    def __init__(self):
        configure_interface_language(Settings().language())
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.watcher = None
        self.windows = []
        self.tray = TrayIndicator(self.show_or_present_editor, self.show_preferences, self.quit,
                                  self.open_clipboard_image, self.open_history, self.request_restart,
                                  self.clipboard_has_image)
        self._history_window = None
        self._temporary_images = tempfile.TemporaryDirectory(prefix='snapmark-clipboard-')
        self._tray_held = False
        self._clipboard_signal_connected = False
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
            if self.tray.available and not self._tray_held:
                self.hold()
                self._tray_held = True
            display = Gdk.Display.get_default()
            if display is not None and not self._clipboard_signal_connected:
                display.get_clipboard().connect('changed', self._clipboard_changed)
                self._clipboard_signal_connected = True
            self.tray.refresh_clipboard_status()

    def clipboard_has_image(self):
        display = Gdk.Display.get_default()
        if display is None:
            return False
        formats = display.get_clipboard().get_formats()
        return (formats.contain_gtype(Gdk.Texture.__gtype__)
                or any(formats.contain_mime_type(mime) for mime in
                       ('image/png', 'image/jpeg', 'image/webp', 'image/bmp')))

    def _clipboard_changed(self, *_unused):
        self.tray.refresh_clipboard_status()

    def open_clipboard_image(self):
        display = Gdk.Display.get_default()
        if display is None or not self.clipboard_has_image():
            print('SnapMark: clipboard does not contain an image', flush=True)
            return False
        clipboard = display.get_clipboard()
        def finished(clip, result):
            try:
                texture = clip.read_texture_finish(result)
                if texture is None:
                    raise ValueError('Clipboard image unavailable')
                data = texture.save_to_png_bytes().get_data()
                fd, name = tempfile.mkstemp(prefix='clipboard-', suffix='.png',
                                              dir=self._temporary_images.name)
                with os.fdopen(fd, 'wb') as output:
                    output.write(data)
                self.show_editor(Path(name))
            except Exception as exc:
                print(f'SnapMark: cannot open clipboard image: {exc}', flush=True)
        clipboard.read_texture_async(None, finished)
        return False

    def open_history(self):
        # A GTK idle callback must not disappear silently if the gallery fails.
        previous = self._history_window
        try:
            window = show_history(self, previous)
        except Exception:
            import traceback
            traceback.print_exc()
            return False
        self._history_window = window
        if previous is None:
            window.connect('close-request', self._history_closed)
        return False

    def _history_closed(self, *_unused):
        self._history_window = None
        return False

    def request_restart(self):
        """Restart SnapMark without a confirmation dialog or Runtime mutation.

        A fresh process ID gives the SNI host a new unique item name.  The
        detached helper waits until the previous process and its D-Bus owner
        have exited, so the new indicator is registered after cleanup.
        """
        GLib.idle_add(self._restart_with_fresh_process)
        return False

    def _restart_launch_command(self):
        appimage = os.environ.get('APPIMAGE')
        if appimage and Path(appimage).is_file():
            return [appimage]
        # In a Flatpak sandbox this interpreter already points at the
        # installed runtime, and the helper inherits the same sandbox.
        return [sys.executable, '-m', 'snapmark.app']

    def _restart_with_fresh_process(self):
        argv = self._restart_launch_command()
        # Do not use os.execv: reusing the PID lets SNI hosts retain the
        # previous tray item.  A separate shell survives application shutdown
        # and starts a new process only AFTER the old PID is gone.
        helper = (
            'old_pid="$1"; shift; '
            'i=0; '
            'while kill -0 "$old_pid" 2>/dev/null; do '
            '  i=$((i+1)); '
            '  if [ "$i" -ge 200 ]; then echo "Timed out waiting for old SnapMark PID" >&2; exit 21; fi; '
            '  sleep 0.1; '
            'done; '
            'sleep 0.7; '
            'exec "$@"'
        )
        try:
            log_path = (Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
                        / 'snapmark' / 'restart.log')
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open('ab') as logfile:
                subprocess.Popen(
                    ['/bin/sh', '-c', helper, 'snapmark-restart-helper',
                     str(os.getpid()), *argv],
                    stdin=subprocess.DEVNULL,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError as exc:
            print(f'SnapMark: unable to start restart helper: {exc}', flush=True)
            return False
        # No confirmation by explicit user request. Close pending dialogs and
        # cancel plugin work through normal GTK teardown before relinquishing
        # the application D-Bus name. Shared Local AI Runtime stays untouched.
        for window in list(self.windows):
            window.close()
        if self._history_window is not None:
            self._history_window.close()
        self.quit()
        return False

    def show_about(self):
        window = Adw.AboutWindow(application_name='SnapMark', version=__version__,
                                 developer_name='SnapMark contributors')
        window.set_application(self)
        if self.windows:
            window.set_transient_for(self.windows[-1])
        window.present()
        return False

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
        self._temporary_images.cleanup()

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
        """No-op by design. GNOME Print Screen never launches SnapMark."""
        return


def main():
    app = SnapMarkApplication()
    return app.run(sys.argv)


if __name__ == '__main__':
    raise SystemExit(main())
