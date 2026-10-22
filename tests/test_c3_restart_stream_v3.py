"""C3 no-prompt restart and live, scrollable plugin preview contracts."""
import ast
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'snapmark/app.py').read_text()
STREAM = (ROOT / 'snapmark/stream_preview_c3.py').read_text()
BUILDER = (ROOT / 'scripts/build-c3-stream-plugins.py').read_text()


class SourceContracts(unittest.TestCase):
    def test_restart_is_immediate_but_new_pid_and_waits_for_shutdown(self):
        tree = ast.parse(APP)
        cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'SnapMarkApplication')
        request = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == 'request_restart')
        text = ast.get_source_segment(APP, request)
        self.assertNotIn('AlertDialog', text)
        self.assertIn('GLib.idle_add(self._restart_with_fresh_process)', text)
        self.assertIn('subprocess.Popen(', APP)
        self.assertIn('start_new_session=True', APP)
        self.assertIn('kill -0 "$old_pid"', APP)
        self.assertIn('self.quit()', APP)
        self.assertNotIn('os.execv(', APP)

    def test_plugin_versions_and_translation_dependencies(self):
        self.assertIn("'ocr': ('1.0.2'", BUILDER)
        self.assertIn("'translation': ('1.0.2'", BUILDER)
        self.assertIn("{'ocr': '1.0.2'}", BUILDER)

    def test_stream_result_protection_and_user_scroll(self):
        self.assertIn('self.view.set_editable(False)', STREAM)
        self.assertIn('self.follow = False', STREAM)
        self.assertIn('self.view.scroll_mark_onscreen(self.end_mark)', STREAM)
        self.assertIn('self.buffer.insert(self.buffer.get_end_iter(), suffix)', STREAM)
        self.assertNotIn('set_sensitive(False)', STREAM)

    def test_geometry_changes_are_not_user_scrolls(self):
        # GTK may asynchronously reflow text and update Adjustment values.
        # The native GTK test below verifies the actual final scroll offset.
        self.assertIn("self.adjustment.connect('changed', self._on_adjustment_changed)", STREAM)
        self.assertIn("self.adjustment.connect('value-changed', self._on_adjustment_value)", STREAM)
        self.assertNotIn("bar.connect('change-value'", STREAM)
        self.assertIn("Gtk.GestureClick.new()", STREAM)
        self.assertIn("bar.add_controller(self.bar_gesture)", STREAM)
        self.assertIn("self.bar_gesture.connect('pressed', self._on_bar_pressed)", STREAM)
        self.assertIn("self.bar_gesture.connect('released', self._on_bar_released)", STREAM)
        self.assertIn('self.view.scroll_to_mark(self.end_mark, 0.0, True, 0.0, 1.0)', STREAM)
        self.assertIn('self._follow_attempts < 30', STREAM)
        self.assertIn('self.follow = False', STREAM)

    def test_state_is_initialized_before_adjustment_callbacks(self):
        constructor=STREAM[STREAM.index('    def __init__(self, stack):'):STREAM.index('    def _at_bottom(self):')]
        self.assertLess(constructor.index('self.follow = True'), constructor.index("self.adjustment.connect('changed'"))
        self.assertLess(constructor.index('self._follow_source = 0'), constructor.index("self.adjustment.connect('changed'"))
        self.assertLess(constructor.index('self._bar_down = False'), constructor.index("self.adjustment.connect('changed'"))

    def test_stream_plugins_can_be_installed_together(self):
        import importlib.util
        from snapmark.plugins import PluginManager
        spec = importlib.util.spec_from_file_location('stream_v3_builder',ROOT/'scripts/build-c3-stream-plugins.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            packages=builder.build(root/'zips')
            manager=PluginManager(root=root/'plugins',settings_root=root/'config')
            for path in packages:
                ident=path.name.split('-')[1]
                data=path.read_bytes()
                manager.install_zip(data,ident,'1.0.2',hashlib.sha256(data).hexdigest())
                if ident=='ocr':
                    manager.select(ident,'1.0.2',True)
            manager.select('translation','1.0.2',True)
            self.assertTrue(manager.is_available('ocr'))
            self.assertTrue(manager.is_available('translation'))


try:
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk, GLib, Gdk
    HAS_GI=True
except (ImportError,ValueError,RuntimeError):
    HAS_GI=False


@unittest.skipUnless(HAS_GI,'Requires real Code01 GTK4 Wayland display')
class NativeGtkStream(unittest.TestCase):
    def test_real_scrollbar_and_follow_state_and_saved_result_isolated(self):
        from snapmark.stream_preview_c3 import StreamingPreview
        self.assertTrue(Gtk.init_check(), 'GTK display required for native scroll test')
        window=Gtk.Window()
        window.set_default_size(520,220)
        stack=Gtk.Stack()
        result=Gtk.TextView()
        result.get_buffer().set_text('existing user-edited text')
        stack.add_named(result,'result')
        preview=StreamingPreview(stack)
        window.set_child(stack)
        def pump(n=20):
            for _ in range(n):
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                time.sleep(0.008)
        try:
            window.present()
            preview.start()
            preview.set_text(''.join(f'line {i}: testing live token scrolling and selection\n' for i in range(150)))
            pump(25)
            adj=preview.adjustment
            self.assertGreater(adj.get_upper()-adj.get_page_size(),50, 'preview must actually be scrollable')
            pump(15)
            self.assertTrue(preview._at_bottom(), 'generated text must follow last line')
            preview._wheel_scroll(None,0,-1)
            adj.set_value(0)
            self.assertFalse(preview.follow)
            # Dragging the scrollbar must also suspend auto-follow, rather
            # than treating this as a harmless programmatic reflow.
            preview.follow = True
            preview._on_bar_pressed(None, 1, 0, 0)
            self.assertFalse(preview.follow)
            self.assertTrue(preview._bar_down)
            preview.set_text(preview.get_text()+'new live tokens\n'*25)
            pump(10)
            self.assertFalse(preview.follow, 'user scroll-up must suspend following')
            self.assertLess(adj.get_value(),adj.get_upper()-adj.get_page_size()-25)
            preview._on_bar_released(None, 1, 0, 0)
            adj.set_value(max(0,adj.get_upper()-adj.get_page_size()))
            pump(9)
            self.assertTrue(preview.follow, 'return to bottom must restore following')
            preview.set_text(preview.get_text()+'latest output tail\n'*10)
            pump(20)
            self.assertTrue(preview._at_bottom())
            preview.set_visible(False)
            buf=result.get_buffer()
            self.assertEqual(buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False),
                             'existing user-edited text')
            self.assertTrue(result.get_editable())
        finally:
            window.close()
            pump(2)


if __name__=='__main__':
    unittest.main()
