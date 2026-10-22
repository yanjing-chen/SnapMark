"""Release-only v1 ZIP metadata, minimal OCR dependency, and safe install contract."""
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


class PluginV1Release(unittest.TestCase):
    def test_bilingual_v1_archives_install_and_activate_without_models(self):
        source = ROOT / 'scripts/build-c3-bilingual-plugins.py'
        spec = importlib.util.spec_from_file_location('bilingual_release_v1', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from snapmark.plugins import PluginManager, PluginError
        with TemporaryDirectory() as home:
            root = Path(home)
            archives = module.build(root / 'archives')
            manager = PluginManager(root / 'plugins', root / 'settings')
            for archive in archives:
                with ZipFile(archive) as zipped:
                    entry = json.loads(zipped.read('plugin.json'))
                    self.assertEqual(entry['version'], '1.0.0')
                    self.assertEqual(entry['dependencies'],
                                     {'ocr': '1.0.0'} if entry['id'] == 'translation' else {})
                    self.assertEqual({f.split('/')[1] for f in zipped.namelist()
                                      if f.startswith('locale/')}, {'en', 'zh_CN'})
                    self.assertFalse(any(f.endswith(('.gguf', '.onnx', '.safetensors'))
                                         for f in zipped.namelist()))
                    payload = archive.read_bytes()
                    manager.install_zip(payload, entry['id'], '1.0.0',
                                        hashlib.sha256(payload).hexdigest())
            with self.assertRaises(PluginError):
                manager.select('translation', '1.0.0')
            manager.select('ocr', '1.0.0')
            manager.select('translation', '1.0.0')
            self.assertTrue(manager.is_available('ocr'))
            self.assertTrue(manager.is_available('translation'))
            self.assertEqual(manager.selected('ocr'), '1.0.0')
            self.assertEqual(manager.selected('translation'), '1.0.0')
            self.assertFalse(list((root/'plugins').rglob('*.gguf')))


if __name__ == '__main__':
    unittest.main()
