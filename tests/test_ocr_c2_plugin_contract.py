"""C2 plugin packaging and safe editable text/worker separation contract."""
import ast
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from snapmark.plugins import PluginManager

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'official_plugins' / 'ocr'


class OCRPluginContractTests(unittest.TestCase):
    def test_package_schema(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text())
        self.assertEqual(manifest['id'], 'ocr')
        self.assertEqual(manifest['version'], '0.2.4')
        self.assertEqual(manifest['api_version'], 1)
        self.assertEqual(manifest['entrypoint'], 'main:register')

    def test_worker_no_gtk_runtime_or_download(self):
        text = (PLUGIN / 'worker.py').read_text()
        self.assertNotIn('gi.repository', text)
        self.assertNotIn('urllib', text)
        self.assertNotIn('local_ai_runtime', text)
        self.assertIn('text_recognition_model_dir=', text)
        self.assertIn('text_detection_model_dir=', text)

    def test_gui_in_main_process_inference_in_subprocess(self):
        source = (PLUGIN / 'main.py').read_text()
        self.assertIn('subprocess.Popen(', source)
        self.assertIn('threading.Thread(', source)
        self.assertNotIn('from paddleocr import PaddleOCR', source)
        self.assertIn('original_png_for_ocr()', source)
        self.assertNotIn('request_ocr_region(', source)
        self.assertNotIn('Select region', source)
        self.assertNotIn('OCR area', source)
        ast.parse(source)

    def test_result_edits_are_not_overwritten_automatically(self):
        source = (PLUGIN / 'main.py').read_text()
        done = source.split('    def _done(', 1)[1].split('    def cancel(', 1)[0]
        self.assertIn('buffer.insert(buffer.get_end_iter(), suffix + output)', done)
        self.assertNotIn("buffer.set_text(output)", done)
        self.assertIn('Save as TXT', source)
        self.assertIn('Copy text', source)

    def test_no_auto_plugin_activation_and_archive_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pack = folder / 'pack.zip'
            with zipfile.ZipFile(pack, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                for item in PLUGIN.iterdir():
                    if item.is_file():
                        z.write(item, item.name)
            payload = pack.read_bytes()
            manager = PluginManager(folder / 'installed', folder / 'settings')
            manifest = manager.install_zip(payload, 'ocr', '0.2.4', hashlib.sha256(payload).hexdigest())
            self.assertEqual(manifest['id'], 'ocr')
            self.assertFalse(manager.is_available('ocr'))
            manager.select('ocr', '0.2.4')
            self.assertTrue(manager.is_available('ocr'))


if __name__ == '__main__':
    unittest.main()
