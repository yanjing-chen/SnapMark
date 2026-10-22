"""C2-E English navigation and resilient settings source-contract tests."""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[1]
NAV=(ROOT/'snapmark/preferences_sidebar_c2e.py').read_text('utf-8')
EDITOR=(ROOT/'snapmark/editor.py').read_text('utf-8')

class EnglishUIContracts(unittest.TestCase):
    def test_english_core_navigation_and_order(self):
        for text in ('General', 'Screenshots & Annotation', 'Shortcuts',
                     'Plugin Management', 'Local AI Runtime', 'About'):
            self.assertIn("'"+text+"'", NAV)
        self.assertNotIn("('appearance', 'Appearance'", NAV)
        self.assertLess(NAV.index("'shortcuts'"),NAV.index("'ai-runtime'"))
        self.assertLess(NAV.index("'ai-runtime'"),NAV.index("'plugins'"))
    def test_no_chinese_hardcoded_core_navigation(self):
        for text in ('通用设置','截图与标注','外观设置','快捷键','插件管理','关于'):
            self.assertNotIn("'"+text+"'",NAV)
        self.assertIn('Example Settings Plugin',NAV)
    def test_native_font_and_legible_selected_item(self):
        self.assertIn('button = Gtk.ToggleButton()',NAV)
        self.assertIn('button.set_active(ident == name)',NAV)
        self.assertIn('self._go_to(name)',NAV)
        self.assertNotIn("button.add_css_class('suggested-action')",NAV)
        self.assertNotIn('font-family:',NAV)
        self.assertNotIn('font-size:',NAV)
    def test_missing_plugin_settings_produces_visible_error_page(self):
        self.assertIn('for ident in self.plugin_manager.enabled_ids():',EDITOR)
        self.assertIn('The enabled plugin did not register a settings page',EDITOR)
        self.assertIn('settings unavailable',EDITOR)
        self.assertIn('navigation.populate_plugins(registered)',EDITOR)
    def test_preserve_dynamic_loader_runtime_and_model_boundaries(self):
        self.assertIn('self._runtime_preferences = AIRuntimePreferences(window, stack)',EDITOR)
        self.assertIn('self._plugin_preferences = PluginPreferences(window, stack)',EDITOR)
        ast.parse(NAV);ast.parse(EDITOR)

if __name__=='__main__':unittest.main()
