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
from .screenshot_session import ScreenshotSession

APP_ID = 'io.github.yanjingchen.SnapMark'


class SnapMarkApplication(Adw.Application):
    def __init__(self):
        configure_interface_language(Settings().language())
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.watcher = None
        self.windows = []
        self.tray = TrayIndicator(self.show_or_present_editor, self.show_preferences, self.quit,
                                  self.open_recent_screenshot, self.open_history, self.request_restart,
                                  self.recent_screenshot_eligible)
        self._history_window = None
        self._temporary_images = tempfile.TemporaryDirectory(prefix='snapmark-clipboard-')
        self._tray_held = False
        self._clipboard_signal_connected = False
        self._screenshot_session = ScreenshotSession()
        self._clipboard_generation = 0
        self._screenshot_expiry_source = 0
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

    def recent_screenshot_eligible(self):
        return self._screenshot_session.eligible(Settings().screenshot_ocr_timeout())

    def refresh_recent_screenshot_status(self):
        """Update the menu also when the user changes the lifetime in Preferences."""
        self.tray.refresh_clipboard_status()
        if self.recent_screenshot_eligible() and not self._screenshot_expiry_source:
            self._screenshot_expiry_source = GLib.timeout_add_seconds(
                1, self._check_screenshot_expiry)

    def _check_screenshot_expiry(self):
        self.tray.refresh_clipboard_status()
        if not self.recent_screenshot_eligible():
            self._screenshot_expiry_source = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _record_screenshot_file(self, path):
        """An actual new GNOME screenshot enables the shortcut independently of clipboard.

        The watcher only observes new screenshot files; it does NOT open the
        editor or start OCR.  A pending clipboard read may have been started
        before the file was completed, so it must not replace this snapshot.
        """
        try:
            texture = Gdk.Texture.new_from_filename(str(path))
            png = bytes(texture.save_to_png_bytes().get_data())
            if not self._screenshot_session.record(png):
                print(f'SnapMark: screenshot is too large for shortcut: {path}', flush=True)
                return
            self._clipboard_generation += 1
            self.refresh_recent_screenshot_status()
            print(f'SnapMark: recent screenshot shortcut refreshed from {path}', flush=True)
        except (GLib.Error, ValueError, TypeError, OSError) as exc:
            print(f'SnapMark: cannot cache screenshot {path}: {exc}', flush=True)

    def _clipboard_changed(self, clipboard, *_unused):
        """Capture a NEW clipboard image, without erasing a recent saved screenshot.

        GNOME's screenshot image can become readable slightly after its clipboard
        changed signal.  Retry a few times rather than permanently leaving the
        shortcut disabled.  Text-only clipboard changes do not invalidate a
        previously captured screenshot within its configured lifetime.
        """
        self._clipboard_generation += 1
        generation = self._clipboard_generation
        self._read_clipboard_screenshot(clipboard, generation, attempts_remaining=3)

    def _read_clipboard_screenshot(self, clipboard, generation, attempts_remaining):
        if generation != self._clipboard_generation:
            return

        def retry():
            if generation == self._clipboard_generation and attempts_remaining > 1:
                self._read_clipboard_screenshot(clipboard, generation, attempts_remaining - 1)
            return GLib.SOURCE_REMOVE

        def finished(clip, result):
            if generation != self._clipboard_generation:
                return
            try:
                texture = clip.read_texture_finish(result)
                if texture is not None:
                    png = bytes(texture.save_to_png_bytes().get_data())
                    if self._screenshot_session.record(png):
                        self.refresh_recent_screenshot_status()
                        return
            except (GLib.Error, ValueError, TypeError, OSError):
                pass  # The clipboard may be transitioning between owners.
            if attempts_remaining > 1:
                GLib.timeout_add(180, retry)

        try:
            clipboard.read_texture_async(None, finished)
        except (GLib.Error, ValueError, TypeError, OSError):
            if attempts_remaining > 1:
                GLib.timeout_add(180, retry)

    def open_recent_screenshot(self):
        """Load captured PNG into the editor; OCR always requires a manual click."""
        png = self._screenshot_session.current_png(Settings().screenshot_ocr_timeout())
        if png is None:
            self.tray.refresh_clipboard_status()
            return False
        try:
            fd, name = tempfile.mkstemp(prefix='screenshot-', suffix='.png',
                                        dir=self._temporary_images.name)
            with os.fdopen(fd, 'wb') as output:
                output.write(png)
            self.show_editor(Path(name))
        except OSError as exc:
            print(f'SnapMark: cannot open recent screenshot: {exc}', flush=True)
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
        # close editor windows before relinquishing the D-Bus name.
        # A shared Ollama service is never stopped or restarted here.
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
            assert window._ocr_panel is not None
            assert window.ocr_toggle is not None
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
        if self._screenshot_expiry_source:
            GLib.source_remove(self._screenshot_expiry_source)
            self._screenshot_expiry_source = 0
        self._screenshot_session.clear()
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
        """Watch screenshot folders in the background without launching an editor.

        GdkClipboard.changed is insufficient on some GNOME 51 sessions while
        the application is minimized. File monitoring is a second, independent
        signal, particularly after a previous shortcut has expired.
        """
        if self.watcher is not None:
            return
        watcher = ScreenshotWatcher(self._record_screenshot_file)
        monitored = watcher.start()
        if not monitored:
            print('SnapMark: no screenshot folder to monitor; clipboard fallback remains active', flush=True)
            watcher.stop()
            return
        self.watcher = watcher
        self.hold()
        print(f'SnapMark: monitoring {len(monitored)} screenshot folders', flush=True)


def main():
    app = SnapMarkApplication()
    return app.run(sys.argv)


if __name__ == '__main__':
    raise SystemExit(main())
