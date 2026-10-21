"""Regression contracts for C2-E GTK4 controls and live plugin state changes."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT/'official_plugins/translation/main.py').read_text('utf-8')
EDITOR = (ROOT/'snapmark/editor.py').read_text('utf-8')
UI = (ROOT/'snapmark/plugin_ui.py').read_text('utf-8')

class LiveSettingsTests(unittest.TestCase):
    def test_gtk4_text_wrap_enum(self):
        self.assertNotIn('Gtk.WrapMode.WORD_WORD', MAIN)
        self.assertIn('prompt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)', MAIN)

    def test_live_plugin_callback_is_connected(self):
        self.assertIn('self._plugin_preferences.on_changed = self._c2e_plugins_changed', EDITOR)
        self.assertIn('self.on_changed()', UI)

    def test_disable_hides_and_closes_plugin_toggle(self):
        self.assertIn('button.set_active(False)', EDITOR)
        self.assertIn('button.set_visible(False)', EDITOR)
        self.assertIn('button.set_visible(True)', EDITOR)
        self.assertIn('self._plugin_action_buttons.items()', EDITOR)

    def test_new_enable_loads_plugin_on_gtk_main_loop(self):
        self.assertIn('load_plugin(self.plugin_manager, ident, self.plugin_host)', EDITOR)
        self.assertIn('self._c2e_loaded_plugins[ident] = version', EDITOR)
        self.assertIn('self._c2e_refresh_preferences_pages()', EDITOR)

    def test_version_switch_requires_restart_and_code_parses(self):
        self.assertIn('Restart SnapMark to load the selected new plugin version', EDITOR)
        self.assertIn('navigation.populate_plugins(registered)', EDITOR)
        ast.parse(MAIN); ast.parse(EDITOR)

if __name__ == '__main__': unittest.main()
