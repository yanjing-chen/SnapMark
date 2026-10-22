"""C3 root-cause regressions: gettext must be used at widget creation."""
from pathlib import Path
import ast
import json
import sys
import unittest
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from snapmark import i18n

class SourceLocalization(unittest.TestCase):
    def tearDown(self):i18n.configure('system')
    def test_primary_navigation_languages(self):
        for lang,expected in (('zh_CN','插件管理'),):
            i18n.configure(lang)
            self.assertEqual(i18n._('Plugin Management'),expected)
            self.assertNotEqual(i18n._('Connection'),'Connection')
            self.assertNotEqual(i18n._('Hardware acceleration'),'Hardware acceleration')
    def test_navigation_translates_at_creation(self):
        source=(ROOT/'snapmark/preferences_sidebar_c2e.py').read_text()
        self.assertIn('Gtk.Label(label=_(label), xalign=0)',source)
        self.assertIn("self._add(root, 'about', 'About'",source)
        self.assertNotIn('localize_widget_tree(',source)
    def test_real_gtk_tree_is_not_scanned(self):
        class FakeNativeWidget:
            __gtype__=object()
            def get_first_child(self):raise AssertionError('Do not traverse GTK')
        self.assertEqual(i18n.localize_widget_tree(FakeNativeWidget()),0)
    def test_runtime_and_plugin_settings_have_direct_gettext(self):
        for file,needle in (
            ('snapmark/ai_runtime_ui.py',"Adw.PreferencesGroup(title=_('Connection')"),
            ('snapmark/ai_runtime_ui.py',"Adw.ActionRow(title=_('Backend preference')"),
            ('snapmark/plugin_ui.py',"Adw.ActionRow(title=_('Installed version')"),
            ('official_plugins/ocr/main.py',"run.set_label(_('Run OCR'))"),
            ('official_plugins/translation/main.py',"run.set_label(_('Translate'))")):
            src=(ROOT/file).read_text();ast.parse(src)
            self.assertIn(needle,src)
    def test_gettext_three_domains_zh_and_english_fallback(self):
        for lang in ('zh_CN',):
            i18n.configure(lang)
            self.assertNotEqual(i18n.plugin_gettext('ocr','Acceleration'),'Acceleration')
            self.assertNotEqual(i18n.plugin_gettext('translation','Registered translation model'),'Registered translation model')
            self.assertEqual(i18n._('MISSING_C3_I18N_SENTINEL'),'MISSING_C3_I18N_SENTINEL')
    def test_no_mutation_of_user_text_or_model_names(self):
        i18n.configure('zh_CN')
        self.assertEqual(i18n._('HY-MT2-7B-Q8_0.gguf'),'HY-MT2-7B-Q8_0.gguf')
        self.assertEqual(i18n._('user OCR result 2026'),'user OCR result 2026')
        source=(ROOT/'snapmark/i18n.py').read_text()
        self.assertNotIn("setter = getattr(widget, 'set_text'",source)
    def test_bilingual_catalogs_compiled_and_audited(self):
        report=json.loads((ROOT/'docs/C3_TRANSLATION_COVERAGE.json').read_text())['languages']
        self.assertEqual(set(report),{'zh_CN','en'})
        for lang in report:
            for domain in ('snapmark','snapmark-ocr','snapmark-translation'):
                self.assertTrue((ROOT/'snapmark/locale'/lang/'LC_MESSAGES'/f'{domain}.mo').is_file())
                info=report[lang][domain]
                self.assertGreater(info['total'],0)
                self.assertEqual(info['total'], info['populated'] + info['missing'])
        self.assertGreater(report['zh_CN']['snapmark']['localized_nonidentical'],300)
        self.assertGreater(report['en']['snapmark']['total'],300)
    def test_plugin_zip_builders_include_own_mo_not_models(self):
        for id in ('ocr','translation'):
            src=(ROOT/f'scripts/build-{id}-plugin-c2.py').read_text()
            self.assertIn("locale_root = ROOT / 'snapmark' / 'locale'",src)
            self.assertIn(f'snapmark-{id}.mo',src)
        for path in ROOT.glob('official_plugins/*/locale/*/LC_MESSAGES/*.mo'):
            self.fail('Original plugin source must stay code-only; ZIP carries compiled locale')

if __name__=='__main__':unittest.main()
