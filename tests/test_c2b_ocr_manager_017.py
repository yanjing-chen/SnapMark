"""OCR installation is opt-in, non-system, official model SHA256 pinned."""
import ast
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / 'official_plugins/ocr/manager_c2b.py'
MAIN = ROOT / 'official_plugins/ocr/main.py'


def load():
    spec = importlib.util.spec_from_file_location('manager_c2b_test', MANAGER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class OCRSetupTests(unittest.TestCase):
    def test_only_official_pinned_det_rec(self):
        m = load()
        self.assertEqual(set(m.COMPONENTS), {'PP-OCRv6_small_det', 'PP-OCRv6_small_rec'})
        for name, item in m.COMPONENTS.items():
            self.assertEqual(len(item['sha256']), 64)
            self.assertTrue(item['repo'].startswith('PaddlePaddle/PP-OCRv6_small_'))
            self.assertTrue(all(c in '0123456789abcdef' for c in item['sha256']))
        self.assertEqual(m.PAIR, 'PP-OCRv6 small')

    def test_no_implicit_engine_install(self):
        m = load()
        with patch.object(m, '_run') as command:
            with self.assertRaises(PermissionError):
                m.install_engine('/tmp/invalid', '/tmp/invalid')
            command.assert_not_called()

    def test_no_implicit_model_download(self):
        m = load()
        with patch.object(m, '_download') as command:
            with self.assertRaises(PermissionError):
                m.install_small('/tmp/invalid')
            command.assert_not_called()

    def test_installer_rejects_non_snapmark_model_root(self):
        m = load()
        with self.assertRaises(ValueError):
            m.install_small('/tmp/elsewhere', confirmed=True)

    def test_installer_does_not_modify_wrong_python(self):
        m = load()
        with patch.object(m, '_run') as command:
            with self.assertRaises(ValueError):
                m.install_engine('/usr/bin/python3.14', '/home/x/.local/bin/uv', confirmed=True)
            command.assert_not_called()

    def test_model_requires_complete_model_files_and_weight_hash(self):
        m = load()
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for name in m.COMPONENTS:
                folder = base/name
                folder.mkdir()
                for filename in m.MODEL_FILES:
                    (folder/filename).write_bytes(b'not-a-real-model'*10)
            self.assertFalse(m.model_installed(str(base)))
            with patch.dict(m.COMPONENTS, {k:{**v,'sha256':hashlib.sha256(b'not-a-real-model'*10).hexdigest()} for k,v in m.COMPONENTS.items()}, clear=True):
                self.assertTrue(m.model_installed(str(base)))

    def test_download_limit_rejected_and_no_registration(self):
        m = load()
        class Fake:
            def __init__(self): self.calls=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):
                self.calls+=1
                return b'x'*1000 if self.calls==1 else b''
        with tempfile.TemporaryDirectory() as temp, patch.object(m.urllib.request, 'urlopen', return_value=Fake()):
            out=Path(temp)/'test'
            with self.assertRaises(ValueError):
                m._download('https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det/resolve/680833b/inference.json',out,limit=500)

    def test_preferences_install_confirmation_and_threaded_work(self):
        source = MAIN.read_text()
        tree = ast.parse(source)
        self.assertIn('GitHub Actions',source)
        method = source.split('    def build_preferences(',1)[1].split('    def _model_selected(',1)[0]
        self.assertNotIn('install_engine(',method)
        self.assertNotIn('install_small(',method)
        self.assertIn('download.connect(',method)
        self.assertNotIn('from paddleocr import PaddleOCR',source)

    def test_archive_version_and_separate_model_manager(self):
        meta=json.loads((ROOT/'official_plugins/ocr/plugin.json').read_text())
        self.assertEqual(meta['version'],'0.2.4')
        build=(ROOT/'scripts/build-ocr-plugin-c2.py').read_text()
        self.assertIn("'manager_c2b.py'",build)
        self.assertEqual(meta['dependencies'],{})

    def test_manager_has_no_gtk_or_runtime(self):
        source=MANAGER.read_text()
        self.assertNotIn('gi.repository',source)
        self.assertNotIn('local_ai_runtime',source)
        self.assertNotIn('systemctl',source)
        self.assertNotIn('sudo',source)

if __name__=='__main__': unittest.main()
