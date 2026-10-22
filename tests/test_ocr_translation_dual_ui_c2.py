"""Source-level contracts for the user-approved dual-pane layout."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OCR = (ROOT / 'official_plugins/ocr/main.py').read_text()
TRANSLATION = (ROOT / 'official_plugins/translation/main.py').read_text()
EDITOR = (ROOT / 'snapmark/editor.py').read_text()
HOST = (ROOT / 'snapmark/plugin_host.py').read_text()


def method(source, cls, meth):
    tree = ast.parse(source)
    c = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    m = next(n for n in c.body if isinstance(n, ast.FunctionDef) and n.name == meth)
    return ast.get_source_segment(source, m)


class DualUIContractTests(unittest.TestCase):
    def test_ocr_has_four_buttons_at_bottom(self):
        part = method(OCR, 'OCRController', 'build_panel')
        self.assertEqual(part.count("Gtk.Button(label='Run OCR')"), 1)
        for name in ('Copy text', 'Clear text', 'Save as TXT'):
            self.assertIn(f"('{name}',", part)
        self.assertLess(part.index('root.append(result_stack)'), part.index('root.append(actions)'))

    def test_ocr_model_timer_on_top(self):
        part = method(OCR, 'OCRController', 'build_panel')
        for label in ('OCR model', 'Time: Not run'):
            self.assertIn(label, part)
        self.assertLess(part.index('root.append(header)'), part.index('root.append(result_stack)'))

    def test_ocr_no_double_selection(self):
        part = method(OCR, 'OCRController', 'build_panel')
        for forbidden in ('OCR area', 'Select region', 'scope_dropdown', 'Whole image'):
            self.assertNotIn(forbidden, part)
        self.assertNotIn('def select_region(', OCR)
        self.assertNotIn('request_ocr_region(', OCR)
        self.assertIn('original_png_for_ocr()', method(OCR, 'OCRController', 'run_whole'))

    def test_ocr_error_dialog_and_elapsed(self):
        self.assertIn('def _error_dialog(', OCR)
        self.assertIn('self._error_dialog(reason)', OCR)
        self.assertIn('time.perf_counter()', OCR)
        self.assertIn("_('Time: {seconds:.2f} s').format(seconds=elapsed)", OCR)

    def test_translation_top_target_only_and_translate(self):
        part = method(TRANSLATION, 'TranslationController', 'build_panel')
        self.assertIn('Target language', part)
        self.assertIn("Gtk.Button(label='Translate')", part)
        self.assertNotIn('Source language', part)
        self.assertNotIn('source_dropdown', part)
        self.assertLess(part.index('header.append(dropdown)'), part.index('header.append(run)'))
        self.assertLess(part.index('root.append(header)'), part.index('root.append(result_stack)'))

    def test_translation_three_bottom_buttons(self):
        part = method(TRANSLATION, 'TranslationController', 'build_panel')
        for name in ('Clear translation', 'Copy text', 'Save as TXT'):
            self.assertIn(f"('{name}',", part)
        self.assertLess(part.index('root.append(result_stack)'), part.index('root.append(actions)'))

    def test_translation_consumes_edited_ocr_text(self):
        self.assertIn("host.get_text_provider('ocr')", TRANSLATION)
        self.assertIn("host.register_text_provider('ocr', controller._get_text)", OCR)
        self.assertIn('source = self.source_getter()', TRANSLATION)
        self.assertIn('def get_text_provider(', HOST)

    def test_both_panels_side_by_side(self):
        part = method(EDITOR, 'EditorWindow', 'add_plugin_result')
        self.assertIn('Gtk.Orientation.HORIZONTAL', part)
        self.assertNotIn('self._result_split.set_end_child(holder)', part)
        render = method(EDITOR, 'EditorWindow', '_render_plugin_results')
        self.assertIn('split.set_start_child(ocr)', render)
        self.assertIn('split.set_end_child(trans)', render)

    def test_no_automatic_translation_or_installation(self):
        part = method(TRANSLATION, 'TranslationController', 'build_panel')
        self.assertIn("run.connect('clicked', self._run)", part)
        self.assertNotIn('urllib', part)
        runtime = (ROOT / 'official_plugins/translation/runtime_client.py').read_text()
        self.assertNotIn('install', method(runtime,'', '') if False else runtime.split('def translate(',1)[1].split('return content.strip()',1)[0].lower().replace('installed', ''))

    def test_target_language_persists(self):
        self.assertIn("_save_settings(self.target, self.selected_model)", TRANSLATION)
        self.assertIn("'target_language': 'Dutch'", TRANSLATION)
