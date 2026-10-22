"""C3 core and official-plugin gettext integration, with no GUI or Runtime needed."""
from pathlib import Path
import unittest
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snapmark import i18n

class FakeWidget:
    def __init__(self,label=None, children=(), title=None):
        self.label=label
        self.title=title
        self.children=list(children)
        self.user_text='Recognized source text: do NOT modify'
        for x,child in enumerate(self.children):
            child._next=self.children[x+1] if x+1<len(self.children) else None
    def get_label(self):return self.label
    def set_label(self,x):self.label=x
    def get_title(self):return self.title
    def set_title(self,x):self.title=x
    def get_first_child(self):return self.children[0] if self.children else None
    def get_next_sibling(self):return getattr(self,'_next',None)
    def get_text(self):return self.user_text
    def set_text(self,x):raise AssertionError('User OCR/translation data must never be translated')

class PluginI18nTests(unittest.TestCase):
    def tearDown(self):i18n.configure('system')
    def test_only_english_and_chinese_sorted(self):
        options=i18n.language_options()
        self.assertEqual(len(options),2)
        self.assertEqual([code for code,label in options],['zh_CN','en'])
        self.assertEqual([x[1].casefold() for x in i18n.LANGUAGES],sorted(x[1].casefold() for x in i18n.LANGUAGES))
    def test_chinese_main_and_both_plugins(self):
        i18n.configure('zh_CN')
        self.assertEqual(i18n._('Screenshot History'),'截图历史')
        self.assertEqual(i18n.plugin_gettext('ocr','Run OCR'),'开始 OCR')
        self.assertEqual(i18n.plugin_gettext('translation','Target language'),'目标语言')
    def test_english_main_and_both_plugins(self):
        i18n.configure('en')
        self.assertEqual(i18n._('Screenshot History'),'Screenshot History')
        self.assertEqual(i18n.plugin_gettext('ocr','Run OCR'),'Run OCR')
        self.assertEqual(i18n.plugin_gettext('translation','Target language'),'Target language')
    def test_plugin_falls_back_to_english_when_string_missing(self):
        i18n.configure('zh_CN')
        self.assertEqual(i18n.plugin_gettext('translation','SENTINEL_MISSING_UI'), 'SENTINEL_MISSING_UI')
    def test_only_widget_labels_titles_not_user_content_or_model_id(self):
        i18n.configure('zh_CN')
        child=FakeWidget(label='Run OCR')
        model=FakeWidget(label='hy-mt2-7b-q8')
        parent=FakeWidget(title='Translation', children=[child,model])
        self.assertEqual(i18n.localize_widget_tree(parent,'ocr'),3)
        self.assertEqual(child.label,'开始 OCR')
        self.assertEqual(parent.title,'翻译')
        self.assertEqual(model.label,'hy-mt2-7b-q8')
        self.assertEqual(child.user_text,'Recognized source text: do NOT modify')
    def test_unsupported_languages_are_rejected(self):
        for code in ('nl', 'ar', 'he', 'fa', 'zh_TW'):
            with self.assertRaises(ValueError): i18n.configure(code)
        self.assertEqual(len(i18n.language_options()), 2)
    def test_reject_malicious_language_and_untrusted_plugin_id(self):
        with self.assertRaises(ValueError):i18n.configure('../../etc')
        i18n.configure('zh_CN')
        self.assertEqual(i18n.plugin_gettext('../traversal','Save'),'保存')
    def test_editor_hooks_translate_loaded_plugin_settings_and_results(self):
        s=(ROOT/'snapmark/editor.py').read_text(encoding='utf8')
        self.assertIn('localize_widget_tree(widget, plugin_id=ident)',s)
        self.assertIn('localize_widget_tree(plugin_page, plugin_id=ident)',s)
        self.assertIn('localize_widget_tree(window)',s)
    def test_plugin_domain_catalogs_available_for_two_languages(self):
        for code,_,_ in i18n.LANGUAGES:
            d=ROOT/'snapmark/locale'/code/'LC_MESSAGES'
            for domain in ('snapmark','snapmark-ocr','snapmark-translation'):
                self.assertTrue((d/(domain+'.po')).is_file())
                self.assertTrue((d/(domain+'.mo')).is_file())
    def test_no_plugin_runtime_models_bundled_in_base_app(self):
        data=(ROOT/'scripts/check-base-package.py').read_text(encoding='utf8')
        self.assertTrue(data)
        self.assertFalse((ROOT/'snapmark/locale'/'models').exists())

if __name__=='__main__':unittest.main()
