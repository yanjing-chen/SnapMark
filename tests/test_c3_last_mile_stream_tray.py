"""C3 final tray and stream behavior (retaining every legacy regression)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TRAY = (ROOT/'snapmark/tray.py').read_text()
APP = (ROOT/'snapmark/app.py').read_text()
OCR = (ROOT/'official_plugins/ocr/main.py').read_text()
TRANSLATION = (ROOT/'official_plugins/translation/main.py').read_text()
STREAM = (ROOT/'snapmark/stream_preview_c3.py').read_text()

class LastMileContracts(unittest.TestCase):
    def test_about_removed_from_tray_but_preferences_about_kept(self):
        import ast
        tray = ast.parse(TRAY)
        table = next(node.value for node in tray.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'MENU_ITEMS' for t in node.targets))
        items = ast.literal_eval(table)
        self.assertNotIn('About', items.values())
        self.assertEqual(items[1], 'Open SnapMark')
        self.assertEqual(items[9], 'Restart SnapMark')
        self.assertIn("stack.add_titled(about_page, 'about', 'About')", (ROOT/'snapmark/editor.py').read_text())
    def test_menu_actions_keep_independent_runtime(self):
        self.assertIn('self.show_or_present_editor', APP)
        self.assertIn('self.request_restart', APP)
        self.assertIn('subprocess.Popen(',APP)
        self.assertIn('self.quit()',APP)
        self.assertNotIn('os.execv(',APP)
        self.assertNotIn('stop_runtime',APP)
        self.assertNotIn("heading=_('Restart SnapMark?')",APP)
    def test_protected_final_result_buffers_unchanged(self):
        self.assertIn('buffer.insert(buffer.get_end_iter(), suffix + output)', OCR)
        self.assertIn('self.textview.get_buffer().set_text(result)', TRANSLATION)
        self.assertIn('if self._text() != previous',TRANSLATION)
        self.assertIn("re.sub(r'\\[\\[SMTECH_", TRANSLATION)
        self.assertIn("self.view.set_editable(False)", STREAM)
        self.assertIn('self.follow = self._at_bottom()',STREAM)
        self.assertIn('self.buffer.insert(self.buffer.get_end_iter(), suffix)',STREAM)
    def test_bilingual_gettext_entries(self):
        import gettext
        for lang, expected in [('zh_CN','重新启动'), ('en','Restart SnapMark')]:
            t = gettext.translation('snapmark', localedir=str(ROOT/'snapmark/locale'),languages=[lang])
            self.assertEqual(t.gettext('Restart SnapMark'), expected)
    def test_parses(self):
        for data in (TRAY,APP,OCR,TRANSLATION,STREAM): ast.parse(data)

try:
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk, Gdk, GLib
    READY = Gdk.Display.get_default() is not None
except (ImportError, RuntimeError, ValueError):
    READY=False

@unittest.skipUnless(READY,'Run on Code01 GNOME/GTK4 Wayland')
class NativeStreamAndTray(unittest.TestCase):
    def test_real_streaming_view_follow_and_manual_browse(self):
        from snapmark.stream_preview_c3 import StreamingPreview
        stack=Gtk.Stack()
        stack.add_named(Gtk.Label(label='Saved result'), 'result')
        preview=StreamingPreview(stack)
        preview.start()
        self.assertEqual(stack.get_visible_child_name(),'stream')
        self.assertFalse(preview.view.get_editable())
        preview.set_text('abc')
        preview.set_text('abcdef')
        self.assertEqual(preview.get_text(),'abcdef')
        self.assertEqual(preview.buffer.get_text(preview.buffer.get_start_iter(),preview.buffer.get_end_iter(),False),'abcdef')
        # Changing adjustment during a user scroll disables following.
        preview.follow=True
        preview._updating=False
        # GTK layout may not allocate until mapped: emulate a user scrolling up.
        preview._at_bottom=lambda:False
        preview._on_scroll()
        self.assertFalse(preview.follow)
        preview.set_text('abcdefgh')
        self.assertFalse(preview.follow)
        preview._at_bottom=lambda:True
        preview._updating=False
        preview._on_scroll()
        self.assertTrue(preview.follow)
        preview.set_visible(False)
        self.assertEqual(stack.get_visible_child_name(),'result')
    def test_live_tray_menu_has_open_restart_no_about(self):
        from snapmark.tray import TrayIndicator,MENU_ITEMS,MENU_ORDER
        from snapmark.i18n import configure
        tray=TrayIndicator(lambda:None,lambda:None,lambda:None)
        self.assertNotIn(5,MENU_ORDER)
        self.assertIn(9,MENU_ORDER)
        configure('zh_CN')
        try:
            self.assertEqual(tray._item_properties(9)['label'].unpack(),'重新启动')
            self.assertTrue(tray._item_properties(1)['enabled'].unpack())
        finally:
            configure('system')
