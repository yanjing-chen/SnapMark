"""C3 bilingual-only release contract; no Runtime nor user settings changes."""
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]

class BilingualOnly(unittest.TestCase):
    def tearDown(self):
        from snapmark.i18n import configure
        configure('en')

    def test_only_two_language_choices_no_system_default(self):
        from snapmark.i18n import CODES, LANGUAGES, language_options, configure
        self.assertEqual(set(CODES), {'en','zh_CN'})
        self.assertEqual([code for code,_ in language_options()], ['zh_CN','en'])
        self.assertEqual(len(LANGUAGES),2)
        for removed in ('nl', 'zh_TW','ar','fr','de','ja'):
            with self.assertRaises(ValueError):configure(removed)

    def test_other_28_catalogs_physically_absent(self):
        locale = ROOT/'snapmark/locale'
        self.assertEqual({p.name for p in locale.iterdir() if p.is_dir()}, {'en','zh_CN'})
        for lang in ('en','zh_CN'):
            self.assertEqual({p.name for p in (locale/lang/'LC_MESSAGES').iterdir()}, {
                'snapmark.po','snapmark.mo','snapmark-ocr.po','snapmark-ocr.mo',
                'snapmark-translation.po','snapmark-translation.mo'})

    def test_legacy_dutch_saved_setting_falls_back_without_writing(self):
        from snapmark.preferences import Settings
        with TemporaryDirectory() as temp:
            s=Settings(temp)
            original={'language':'nl','recent_colors':['#aabbcc'],
                      'image_format':'png','image_quality':90}
            s.file.parent.mkdir(parents=True,exist_ok=True)
            before=json.dumps(original,ensure_ascii=False).encode()
            s.file.write_bytes(before)
            self.assertEqual(s.language(),'en')
            self.assertEqual(s.recent_colors(),['#aabbcc'])
            self.assertEqual(s.file.read_bytes(),before)
            s.set_language('zh_CN')
            self.assertEqual(Settings(temp).language(),'zh_CN')

    def test_legacy_system_resolves_to_two_languages_without_write(self):
        from snapmark.preferences import Settings
        from unittest.mock import patch
        with TemporaryDirectory() as temp:
            s=Settings(temp)
            s.file.parent.mkdir(parents=True,exist_ok=True)
            s.file.write_text('{"language":"system"}',encoding='utf-8')
            with patch.dict(os.environ, {'LC_ALL':'zh_CN.UTF-8'}):
                self.assertEqual(s.language(),'zh_CN')
            with patch.dict(os.environ, {'LC_ALL':'nl_NL.UTF-8'}):
                self.assertEqual(s.language(),'en')
            self.assertEqual(s.file.read_text(),'{"language":"system"}')

    def test_all_zip_locale_and_version_and_model_safety(self):
        module_path=ROOT/'scripts/build-c3-bilingual-plugins.py'
        spec=importlib.util.spec_from_file_location('snapmark_bilingual_builder',module_path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with TemporaryDirectory() as tmp:
            files=module.build(Path(tmp))
            self.assertEqual(len(files),2)
            for zippath in files:
                with ZipFile(zippath) as z:
                    names=z.namelist()
                    config=json.loads(z.read('plugin.json'))
                    ident=config['id']
                    self.assertEqual(config['version'], {'ocr':'1.0.0','translation':'1.0.0'}[ident])
                    self.assertEqual(config.get('dependencies', {}),
                                     {} if ident == 'ocr' else {'ocr': '1.0.0'})
                    locale_paths=[n for n in names if n.startswith('locale/')]
                    self.assertEqual(set(locale_paths),{
                        f'locale/en/LC_MESSAGES/snapmark-{ident}.mo',
                        f'locale/zh_CN/LC_MESSAGES/snapmark-{ident}.mo'})
                    self.assertFalse(any(n.endswith(('.gguf','.onnx','.safetensors')) for n in names))

    def test_reports_are_bilingual(self):
        for file in ('C3_TRANSLATION_COVERAGE.json','C3_SOURCE_UI_TRANSLATION_AUDIT.json'):
            obj=json.loads((ROOT/'docs'/file).read_text(encoding='utf-8'))
            langs=obj['languages'] if 'languages' in obj else obj
            self.assertEqual(set(langs), {'zh_CN','en'})

if __name__=='__main__':unittest.main()
