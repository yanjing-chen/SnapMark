"""C3 Runtime three-level UI: old service/runtime functionality is preserved."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=(ROOT/'snapmark/ai_runtime_ui.py').read_text(encoding='utf-8')
NAV=(ROOT/'snapmark/preferences_sidebar_c2e.py').read_text(encoding='utf-8')
EDITOR=(ROOT/'snapmark/editor.py').read_text(encoding='utf-8')
APP=(ROOT/'snapmark/app.py').read_text(encoding='utf-8')

class RuntimeThreeLevelsContract(unittest.TestCase):
    def test_main_advanced_and_separate_maintenance(self):
        ast.parse(RUNTIME)
        self.assertIn('self.advanced_revealer = Gtk.Revealer()', RUNTIME)
        self.assertIn('self.advanced_box.append(group)', RUNTIME)
        self.assertIn('self.advanced_box.append(memory)', RUNTIME)
        self.assertIn('self.maintenance_window = Adw.PreferencesWindow',RUNTIME)
        for name in ('packages','models','install','management','select'):
            self.assertIn('self.maintenance_page.add('+name+')',RUNTIME)
    def test_all_service_actions_still_guarded(self):
        for name in ('download','backup','install','rollback','start','stop','restart',
                     'uninstall','purge_config','llama_install','cuda_install'):
            self.assertIn("'"+name+"'",RUNTIME)
        self.assertIn("dialog.set_default_response('cancel')",RUNTIME)
        self.assertIn("dialog.set_close_response('cancel')",RUNTIME)
    def test_original_model_registration_and_timeout_kept(self):
        for identifier in ('_registration_response','_b4_confirm','_idle_save_confirmed',
                           '_preview_async','_management_clicked','_start_probe'):
            self.assertIn('def '+identifier+'(',RUNTIME)
    def test_appearance_removed_but_editor_functions_remain(self):
        ast.parse(NAV);ast.parse(EDITOR)
        self.assertNotIn("('appearance', 'Appearance'",NAV)
        self.assertNotIn("stack.add_titled(appearance_page",EDITOR)
        self.assertIn('custom_stroke',EDITOR)
        self.assertIn('custom_fill',EDITOR)
    def test_plugin_version_and_enablement_share_one_dropdown(self):
        plugin=(ROOT/'snapmark/plugin_ui.py').read_text()
        self.assertIn('def _selected_version_or_disabled(', plugin)
        self.assertIn("versions + [_('Disabled')]",plugin)
        self.assertNotIn('group.add(controls)',plugin)
        self.assertIn('self.manager.select(ident, versions[index], True)',plugin)
        self.assertIn('self.manager.set_enabled(ident, False)',plugin)
    def test_about_has_real_release_version(self):
        ast.parse(APP)
        self.assertIn("application_name='SnapMark', version=__version__",APP)
        self.assertIn("__version__ = '1.0.0'", (ROOT/'snapmark/__init__.py').read_text())

try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, Gdk
    from unittest.mock import patch
    from types import SimpleNamespace
    READY=Gdk.Display.get_default() is not None
except (ImportError, ValueError, RuntimeError):
    READY=False

@unittest.skipUnless(READY,'Native GTK4/GNOME display required')
class RuntimeThreeLevelsLive(unittest.TestCase):
    def test_advanced_starts_collapsed_and_maintenance_is_separate(self):
        import snapmark.ai_runtime_ui as ui
        class DummySettings:
            def load(self): return {'enabled':False,'endpoint':'http://127.0.0.1:8111','backend_preference':'auto'}
        with patch.object(ui, 'RuntimeSettings', DummySettings), \
             patch.object(ui, 'RuntimeManager', lambda:object()), \
             patch.object(ui,'inspect_local_installation',lambda:SimpleNamespace(complete=False,installed=False)), \
             patch.object(ui.AIRuntimePreferences,'_set_available',lambda self,value:None), \
             patch.object(ui.AIRuntimePreferences,'_refresh_manager_buttons',lambda self:None):
            screen=Gtk.Stack()
            control=ui.AIRuntimePreferences(None,screen)
            self.assertFalse(control.advanced_revealer.get_reveal_child())
            self.assertFalse(control.maintenance_window.get_visible())
            self.assertIsNotNone(control.widgets['manager_status'].get_parent())
            control.widgets['advanced_toggle'].set_active(True)
            self.assertTrue(control.advanced_revealer.get_reveal_child())
            control.maintenance_window.destroy()

if __name__=='__main__':unittest.main()
