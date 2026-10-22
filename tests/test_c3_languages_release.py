"""No GTK required: C3 language and release safety contracts."""
import ast
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from snapmark.i18n import LANGUAGES,CODES,language_options,configure,_

class C3ReleaseContracts(unittest.TestCase):
    def test_only_two_langs_a_to_z(self):
        self.assertEqual(len(LANGUAGES),2)
        self.assertEqual(len(CODES),2)
        self.assertEqual([x[0] for x in language_options()], ['zh_CN','en'])
        self.assertEqual([x[1].casefold() for x in LANGUAGES],
                         sorted(x[1].casefold() for x in LANGUAGES))
        self.assertEqual(len(language_options()),2)
    def test_unknown_language_rejected(self):
        with self.assertRaises(ValueError): configure('../escape')
    def test_system_and_missing_strings_fall_back(self):
        configure('system')
        self.assertIsInstance(_('Save'),str)
        configure('en')
        self.assertEqual(_('C3_MISSING_STRING_SENTINEL'), 'C3_MISSING_STRING_SENTINEL')
    def test_optional_plugins_not_embedded_in_flatpak(self):
        text=(ROOT/'flatpak/io.github.yanjingchen.SnapMark.yml').read_text()
        self.assertIn('xdg-pictures:ro',text)
        self.assertIn('share=network',text)
        self.assertNotIn('--filesystem=home',text)
        self.assertNotIn('install official_plugins',text)
        self.assertNotIn('install local-ai-runtime',text)
    def test_all_po_present(self):
        for code,_,_ in LANGUAGES:
            f=ROOT/'snapmark/locale'/code/'LC_MESSAGES/snapmark.po'
            self.assertTrue(f.is_file(),f)
    def test_language_setting_is_persistent(self):
        from snapmark.preferences import Settings
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as root:
            s=Settings(root)
            self.assertIn(s.language(),('en','zh_CN'))
            s.set_language('zh_CN')
            self.assertEqual(Settings(root).language(),'zh_CN')
            with self.assertRaises(ValueError): s.set_language('../../../tmp')

if __name__=='__main__': unittest.main()
