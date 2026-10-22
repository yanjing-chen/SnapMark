"""C3: dropdown labels are localized while stored profile keys stay stable."""
from __future__ import annotations
import ast
import inspect
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LocalizedPluginOptions(unittest.TestCase):
    def test_ocr_dropdown_display_only_and_stored_keys(self):
        code = (ROOT / 'official_plugins/ocr/main.py').read_text('utf-8')
        self.assertIn('Gtk.DropDown.new_from_strings([_(name) for name in preset_names])', code)
        self.assertIn('Gtk.DropDown.new_from_strings([_(name) for name in output_names])', code)
        self.assertIn("value = preset_names[widget.get_selected()]", code)
        self.assertIn("'preset': selected, 'prompt': prompt", code)
        self.assertIn("'output': output_names[output.get_selected()]", code)
        self.assertIn("Gtk.Label(label=_('Auto'))", code)
        for file in ('profiles_c2f.py', 'main.py'):
            ast.parse((ROOT / 'official_plugins/ocr' / file).read_text('utf-8'))

    def test_translation_dropdown_display_only_and_stored_keys(self):
        code = (ROOT / 'official_plugins/translation/main.py').read_text('utf-8')
        self.assertIn('Gtk.DropDown.new_from_strings([_(name) for name in presets])', code)
        self.assertIn("Gtk.DropDown.new_from_strings([_(name) if name == 'Model default' else name for name in options])", code)
        self.assertIn("'preset': presets[selection.get_selected()]", code)
        self.assertIn("'max_tokens': None if token_selector.get_selected() == 0 else int(options[token_selector.get_selected()])", code)
        ast.parse(code)

    def test_zh_and_english_real_compiled_catalogs(self):
        from snapmark.i18n import configure, plugin_gettext
        for locale in ('zh_CN', 'en'):
            try:
                configure(locale)
                for plugin, entries in (
                    ('ocr', ('Auto', 'Model default', 'Faithful text', 'Custom', 'Plain text', 'Preserve paragraphs')),
                    ('translation', ('General', 'Technical', 'Academic', 'Literary', 'Custom', 'Model default')),
                ):
                    for entry in entries:
                        result = plugin_gettext(plugin, entry)
                        if locale == 'zh_CN':
                            self.assertNotEqual(result, entry, (locale, plugin, entry))
                        else:
                            self.assertEqual(result, entry, (locale, plugin, entry))
            finally:
                configure('system')

    def test_original_profile_keys_remain_english(self):
        import importlib.util
        for plugin, filename, names in (
            ('ocr', 'profiles_c2f.py', ('Model default', 'Faithful text', 'Custom', 'Plain text')),
            ('translation', 'settings_c2e.py', ('General', 'Technical', 'Academic', 'Literary')),
        ):
            path = ROOT / 'official_plugins' / plugin / filename
            spec = importlib.util.spec_from_file_location('c3_settings_check_' + plugin, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for name in names:
                self.assertTrue(name in (module.PRESETS if name in module.PRESETS else getattr(module,'OUTPUTS',())))

if __name__ == '__main__':
    unittest.main()
