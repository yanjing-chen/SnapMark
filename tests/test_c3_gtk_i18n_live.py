"""Only when PyGObject and a GTK display exist: inspect real native widget captions.

No models, Runtime API calls, Flatpak installation or user settings mutations.
"""
import sys
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
try:
    import gi
    gi.require_version('Gtk','4.0')
    gi.require_version('Adw','1')
    from gi.repository import Gtk, Adw, Gdk
    if os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY'):
        Gtk.init()
        Adw.init()
    DISPLAY_READY=Gdk.Display.get_default() is not None
except (ImportError,ValueError,RuntimeError):
    DISPLAY_READY=False

@unittest.skipUnless(DISPLAY_READY,'GTK4/libadwaita display needed; execute on Code01 GNOME')
class NativeGtkLabels(unittest.TestCase):
    def tearDown(self):
        from snapmark.i18n import configure
        configure('system')
    def test_preferences_sidebar_real_labels(self):
        from snapmark.i18n import configure
        from snapmark.preferences_sidebar_c2e import PreferencesNavigation
        for lang,expected in (('zh_CN','插件管理'),):
            configure(lang)
            stack=Gtk.Stack()
            navigation=PreferencesNavigation(stack)
            label=navigation.buttons['plugins'].get_child().get_last_child().get_label()
            self.assertEqual(label,expected)
            self.assertNotEqual(navigation.buttons['general'].get_child().get_last_child().get_label(),'General')
    def test_runtime_page_real_gtk_labels_without_service_calls(self):
        from snapmark.i18n import configure
        import snapmark.ai_runtime_ui as rt
        class DummySettings:
            def load(self):
                return {'enabled':False,'endpoint':'http://127.0.0.1:8111','backend_preference':'auto'}
        for lang,title in (('zh_CN','连接状态'),):
            configure(lang)
            with patch.object(rt,'RuntimeSettings',DummySettings),patch.object(rt,'RuntimeManager',lambda:object()),patch.object(rt,'inspect_local_installation',lambda:SimpleNamespace(complete=False,installed=False)),patch.object(rt.AIRuntimePreferences,'_set_available',lambda self,x:None),patch.object(rt.AIRuntimePreferences,'_refresh_manager_buttons',lambda self:None):
                stack=Gtk.Stack()
                page=rt.AIRuntimePreferences(None,stack)
                self.assertEqual(page.widgets['status'].get_title(),title)
                self.assertNotEqual(page.widgets['endpoint'].get_title(),'Endpoint')
    def test_plugin_manager_real_gtk_labels_without_user_config(self):
        from snapmark.i18n import configure
        import snapmark.plugin_ui as plugin_ui
        class DummyManager:
            def known_ids(self):return ['ocr','translation']
            def selected(self,_id):return None
            def manifest(self,*args):return None
            def versions(self,_id):return []
            def is_available(self,_id):return False
            def is_enabled(self,_id):return False
        for lang,expected in (('zh_CN','已安装版本'),):
            configure(lang)
            with patch.object(plugin_ui,'PluginManager',DummyManager):
                stack=Gtk.Stack()
                page=plugin_ui.PluginPreferences(None,stack)
                self.assertEqual(page.widgets['ocr']['active'].get_title(),expected)
                self.assertNotEqual(page.widgets['ocr']['controls'].get_title(),'Activate selected version')

if __name__=='__main__':unittest.main()
