"""C3 GNOME follow-up: dynamic property labels, tray menu, history opening.

Do not connect to Runtime or change user's preferences/plugins.
"""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock, skipUnless

ROOT=Path(__file__).resolve().parents[1]

class StaticFollowup(TestCase):
    def test_gallery_imports_gettext_not_missing_global(self):
        source=(ROOT/'snapmark/history_c2g.py').read_text('utf8')
        self.assertIn('from .i18n import _',source)
        ast.parse(source)
    def test_tray_dbus_label_is_localized_at_serialization(self):
        source=(ROOT/'snapmark/tray.py').read_text('utf8')
        self.assertIn("GLib.Variant('s', _(MENU_ITEMS[index]))",source)
        self.assertIn('from .i18n import _',source)
    def test_property_dynamic_paths_translate_labels(self):
        source=(ROOT/'snapmark/editor.py').read_text('utf8')
        for s in ('self._style_header.set_text(_(',"_('Strength')","_('Opacity')", "_('Width')", "_('Block size')", "_('Blur radius')", "_('Corner radius')", "_('Brush size')", "menu.append(_('Preferences')"):
            self.assertIn(s,source)
        self.assertNotIn("self._style_header.set_text('Stroke')",source)
        self.assertNotIn("self.opacity_label.set_text(f'Strength",source)
    def test_plugin_runtime_captions_localize_without_touching_results(self):
        from snapmark.i18n import configure, plugin_gettext
        for plugin in ('ocr','translation'):
            source=(ROOT/'official_plugins'/plugin/'main.py').read_text('utf8')
            self.assertIn("_('Time: {seconds:.2f} s').format(seconds=elapsed)",source)
            self.assertIn("_('Time: {seconds:.2f} s').format(seconds=time.perf_counter() - self.started_at)",source)
            for lang in ('zh_CN',):
                configure(lang)
                caption=plugin_gettext(plugin,'Time: {seconds:.2f} s').format(seconds=2.5)
                self.assertNotIn('Time:',caption)
                self.assertIn('2.50',caption)
            self.assertIn('get_buffer().set_text',source)
        configure('system')
    def test_translations_in_catalogs(self):
        from snapmark.i18n import _, configure
        try:
            for code,expected in [('zh_CN','属性')]:
                configure(code)
                self.assertEqual(_('Properties'),expected)
                for key in ('Strength','Opacity','Width','Block size','Blur radius','Corner radius','Brush size','Preferences','Screenshot History'):
                    self.assertNotEqual(_(key),key)
        finally:configure('system')

try:
    import gi
    gi.require_version('Gtk','4.0')
    gi.require_version('Adw','1')
    from gi.repository import Gtk, Adw, Gio, Gdk, GLib
    Gtk.init()
    Adw.init()
    HAS_GTK=Gdk.Display.get_default() is not None
except (ImportError,ValueError,RuntimeError):
    HAS_GTK=False

@skipUnless(HAS_GTK,'Requires Code01 GTK4 display')
class GtkFollowup(TestCase):
    def tearDown(self):
        from snapmark.i18n import configure
        configure('system')
    def test_live_property_callbacks_zh(self):
        from snapmark.i18n import configure, _
        from snapmark.editor import EditorWindow
        for code in ('zh_CN',):
            configure(code)
            fake=SimpleNamespace(
                stroke=4.0, eraser_size=12.0, corner_radius=5.0,
                opacity=0.5, effect_strength=0.5,tool='pen',
                width_label=Gtk.Label(),opacity_label=Gtk.Label(),
                eraser_label=Gtk.Label(),radius_label=Gtk.Label(),
                _selected_mark=lambda:None, _change_selected=lambda **kw:None)
            scale=SimpleNamespace(get_value=lambda:7.0)
            EditorWindow._width_changed(fake,scale)
            self.assertEqual(fake.width_label.get_label(),f'{_("Width")} · 7 px')
            EditorWindow._opacity_changed(fake,scale)
            self.assertEqual(fake.opacity_label.get_label(),f'{_("Opacity")} · 7%')
            fake.tool='mosaic'
            EditorWindow._width_changed(fake,scale)
            self.assertEqual(fake.width_label.get_label(),f'{_("Block size")} · 21 px')
            EditorWindow._opacity_changed(fake,scale)
            self.assertEqual(fake.opacity_label.get_label(),f'{_("Strength")} · 7%')
            fake.tool='blur'
            EditorWindow._width_changed(fake,scale)
            self.assertEqual(fake.width_label.get_label(),f'{_("Blur radius")} · 14 px')
    def test_dbus_tray_menu_returns_zh(self):
        from snapmark.i18n import configure, _
        from snapmark.tray import TrayIndicator
        for code in ('zh_CN',):
            configure(code)
            indicator=TrayIndicator(lambda:False,lambda:False,lambda:False)
            for ident,key in ((2,'Open Clipboard Image'),(3,'Screenshot History'),(4,'Preferences'),(6,'Quit')):
                self.assertEqual(indicator._item_properties(ident)['label'].unpack(),_(key))
    def test_history_constructs_window_without_runtime(self):
        from snapmark.i18n import configure, _
        from snapmark import history_c2g
        # Keep one registered Gio.Application for both languages. Registering
        # separate applications with the same ID on the same session-bus
        # connection attempts to export org.gtk.Application twice at one
        # object path and raises GLib.GError; this is a test-fixture bug,
        # not a Screenshot History failure.
        app=Adw.Application(application_id='io.github.yanjingchen.SnapMark.I18nValidation',
                            flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.assertTrue(app.register(None))
        for code in ('zh_CN',):
            configure(code)
            with mock.patch.object(history_c2g,'history_paths',return_value=[]):
                with mock.patch.object(history_c2g.Settings,'screenshot_directory',return_value=''):
                    window=history_c2g.show_history(app)
            try:
                self.assertEqual(window.get_title(),_('Screenshot History'))
            finally:
                window.close()
