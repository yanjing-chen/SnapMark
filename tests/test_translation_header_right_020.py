"""C2-020 translation Translate button alignment contract."""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'official_plugins/translation/main.py').read_text()

def build_panel():
    tree = ast.parse(SRC)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TranslationController')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'build_panel')
    return ast.get_source_segment(SRC,method)

class TranslateRightAlignmentTests(unittest.TestCase):
    def test_translate_button_right_of_stretch_spacer(self):
        panel = build_panel()
        self.assertLess(panel.index('header.append(dropdown)'), panel.index('header.append(translate_spacer)'))
        self.assertLess(panel.index('header.append(translate_spacer)'), panel.index('header.append(run)'))
        self.assertIn('translate_spacer.set_hexpand(True)',panel)

    def test_header_expands_button_right_aligned(self):
        panel = build_panel()
        self.assertIn('header.set_hexpand(True)',panel)
        self.assertIn('run.set_halign(Gtk.Align.END)',panel)
        self.assertIn('run.set_hexpand(False)',panel)

    def test_same_header_contains_both_models_language_and_translate(self):
        panel = build_panel()
        for piece in ('header.append(selector)','header.append(dropdown)',"Gtk.Button(label='Translate')", "run.connect('clicked', self._run)"):
            self.assertIn(piece,panel)
        self.assertNotIn('root.append(translate_spacer)',panel)

    def test_only_translation_ui_version_changes(self):
        manifest = json.loads((ROOT/'official_plugins/translation/plugin.json').read_text())
        self.assertEqual(manifest['version'],'0.1.4')
        self.assertEqual(manifest['dependencies'],{'ocr':'0.1.2'})
        self.assertIn('SnapMark-translation-0.1.4.zip',(ROOT/'scripts/build-translation-plugin-c2.py').read_text())
