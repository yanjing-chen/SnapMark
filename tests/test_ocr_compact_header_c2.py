"""C2 0.1.3: compact OCR model selector and explanatory elapsed-time text."""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / 'official_plugins/ocr/main.py').read_text('utf-8')


def method(name):
    tree = ast.parse(CODE)
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'OCRController')
    fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(CODE, fn)


class CompactOCRHeaderTests(unittest.TestCase):
    def test_model_dropdown_not_stretched_and_spacer_fills(self):
        build = method('build_panel')
        self.assertIn('combo.set_hexpand(False)', build)
        self.assertIn('combo.set_size_request(152, -1)', build)
        self.assertIn('spacer.set_hexpand(True)', build)
        self.assertLess(build.index('header.append(combo)'), build.index('header.append(spacer)'))
        self.assertLess(build.index('header.append(spacer)'), build.index('header.append(run)'))

    def test_elapsed_label_is_clear_and_two_decimal_places(self):
        build = method('build_panel')
        self.assertIn("label='Time: Not run'", build)
        self.assertIn('Elapsed time for current or most recent OCR', build)
        self.assertIn('Time: {elapsed:.2f} s', method('_done'))
        self.assertIn('Time: {time.perf_counter() - self.started_at:.2f} s', method('_tick'))
        self.assertNotIn('OCR: —', CODE)

    def test_translation_minimum_remains_backwards_compatible(self):
        ocr = json.loads((ROOT / 'official_plugins/ocr/plugin.json').read_text('utf-8'))
        translation = json.loads((ROOT / 'official_plugins/translation/plugin.json').read_text('utf-8'))
        self.assertEqual(ocr['version'], '0.1.9')
        self.assertEqual(translation['dependencies'], {'ocr':'0.1.2'})
