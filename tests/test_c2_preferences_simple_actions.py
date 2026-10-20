"""GTK OCR preferences and hosted runtime contracts (C2-019)."""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OCR = (ROOT / 'official_plugins/ocr/main.py').read_text()

class CompactPreferencesTests(unittest.TestCase):
    def test_two_modes_with_separate_groups(self):
        self.assertIn("Gtk.ToggleButton(label='Lightweight · PP-OCR')", OCR)
        self.assertIn("Gtk.ToggleButton(label='Advanced · Local AI Runtime')", OCR)
        self.assertIn('advanced_button.set_group(light_button)', OCR)
        self.assertIn("lightweight.set_visible(selected == 'lightweight')", OCR)
        self.assertIn("advanced.set_visible(selected == 'high_performance')", OCR)
    def test_no_python_install_action_in_preferences(self):
        method = OCR.split('    def build_preferences(',1)[1].split('    def _model_selected(',1)[0]
        self.assertNotIn('install_engine(', method)
        self.assertNotIn('install_small(', method)
        self.assertNotIn('OCR Python environment (absolute path)', method)
        self.assertNotIn('Local OCR model root (absolute path)', method)
    def test_verified_onnx_install_after_real_inference_passed(self):
        method = OCR.split('    def build_preferences(',1)[1].split('    def _model_selected(',1)[0]
        self.assertIn('_onnx.install_label(label,confirmed=True)', method)
        self.assertIn('download.connect(', method)
        self.assertIn('ONNX', method)
        self.assertIn("Gtk.Button(label='Test OCR')", method)
    def test_remote_catalog_filters_ocr_role(self):
        method = OCR.split('    def build_preferences(',1)[1].split('    def _model_selected(',1)[0]
        self.assertIn("fetch_runtime_models('ocr')", method)
        self.assertNotIn("fetch_runtime_models('translation')", method)
    def test_actions_artifact_no_local_build(self):
        workflow = (ROOT / '.github/workflows/ocr-onnx-engine.yml').read_text()
        self.assertIn('runs-on: ubuntu-24.04', workflow)
        self.assertIn('upload-artifact@v4', workflow)
        self.assertIn('node worker.cjs --self-test', workflow)
        self.assertNotIn('softprops/action-gh-release', workflow)
    def test_package_revision(self):
        manifest = json.loads((ROOT / 'official_plugins/ocr/plugin.json').read_text())
        self.assertEqual(manifest['version'], '0.1.9')
        self.assertEqual(manifest['dependencies'], {})
        ast.parse(OCR)

if __name__ == '__main__':
    unittest.main()
