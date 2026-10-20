"""C2-027: official model catalog, compatibility and safe installer contracts."""
import ast
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'official_plugins/ocr'
OFFICIAL = HERE / 'official_models_c2.py'
ONNX = HERE / 'onnx_c2.py'
MAIN = HERE / 'main.py'
BUILTIN = HERE / 'catalog_builtin.json'
FLOW = ROOT / '.github/workflows/ocr-onnx-engine.yml'
CATALOG = ROOT / 'ocr-models/catalog-v1.json'


def helper():
    spec=importlib.util.spec_from_file_location('snapmark_official_model_catalog_testing', OFFICIAL)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class OfficialModelCatalogTests(unittest.TestCase):
    def setUp(self):
        self.mod=helper()
        self.data=json.loads(BUILTIN.read_text())

    def test_builtin_manifest_matches_repository(self):
        self.assertEqual(self.data,json.loads(CATALOG.read_text()))
        self.assertEqual(self.mod.validate_catalog(self.data),self.data)

    def test_official_sources_and_pinned_onnx_sha(self):
        model=self.data['models'][0]
        self.assertTrue(self.mod._official_url(model['files']['det']['url'],'det'))
        self.assertTrue(self.mod._official_url(model['files']['rec']['url'],'rec'))
        self.assertTrue(self.mod._official_url(model['files']['dict']['url'],'dict'))
        self.assertEqual(model['files']['det']['sha256'],self.mod.DET_SHA256)
        self.assertEqual(model['files']['rec']['sha256'],self.mod.REC_SHA256)

    def test_nonofficial_or_floating_onnx_urls_rejected(self):
        for bad in ('https://huggingface.co/someone/model/resolve/main/inference.onnx',
                    'http://huggingface.co/PaddlePaddle/model/resolve/abcd/inference.onnx',
                    'https://huggingface.co.evil.test/PaddlePaddle/foo'):
            self.assertFalse(self.mod._official_url(bad,'det'))

    def test_manifest_rejects_third_party_models(self):
        bad=copy.deepcopy(self.data)
        bad['models'][0]['files']['det']['url']='https://github.com/someone/weights.onnx'
        with self.assertRaises(ValueError):self.mod.validate_catalog(bad)

    def test_manifest_requires_compatibility_declaration(self):
        bad=copy.deepcopy(self.data)
        bad['models'][0]['min_engine_api']='1'
        with self.assertRaises(ValueError):self.mod.validate_catalog(bad)

    def test_unverified_future_version_is_not_runnable(self):
        model=copy.deepcopy(self.data['models'][0]);model['id']='ppocr-v7-tiny'
        model['profile']='ppocr-v7-unverified'
        self.assertFalse(self.mod.compatible(model))
        model['profile']=self.mod.PROFILE;model['min_engine_api']=2
        self.assertFalse(self.mod.compatible(model))
        model['min_engine_api']=1;model['verification']='unverified'
        self.assertFalse(self.mod.compatible(model))

    def test_refresh_does_not_destroy_previous_cache_on_invalid_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.json'
            path.write_text(json.dumps(self.data))
            with patch.object(self.mod,'CACHE_PATH',path), \
                 patch.object(self.mod,'urlopen',side_effect=OSError('offline')):
                with self.assertRaises(OSError):self.mod.refresh_catalog()
                self.assertEqual(json.loads(path.read_text()),self.data)

    def test_explicit_user_approval_required(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(PermissionError):
                self.mod.install(Path(folder)/'new')

    def test_existing_files_cannot_be_overwritten(self):
        model=self.data['models'][0]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model';path.mkdir();(path/'keep').write_text('yes')
            with self.assertRaises(FileExistsError):self.mod.install(path,confirmed=True,model=model)
            self.assertEqual((path/'keep').read_text(),'yes')

    def test_invalid_hash_rolls_back_model_directory(self):
        model=self.data['models'][0]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model'
            def bad_download(url,output,max_bytes,kind):Path(output).write_bytes(b'corrupt')
            with patch.object(self.mod,'_download',side_effect=bad_download):
                with self.assertRaises(ValueError):self.mod.install(path,confirmed=True,model=model)
            self.assertFalse(path.exists())

    def test_refresh_and_install_buttons_only_in_preferences(self):
        method=MAIN.read_text().split('    def build_preferences(',1)[1].split('    def _model_selected(',1)[0]
        self.assertIn('Refresh models',method)
        self.assertIn('_onnx.refresh_catalog()',method)
        self.assertIn("Adw.ComboRow(title='Available OCR models')",method)
        self.assertIn('_onnx.install_label(label,confirmed=True)',method)
        self.assertIn('threading.Thread(target=job,daemon=True).start()',method)
        self.assertNotIn('_setup.install_engine(',method)

    def test_onnx_worker_uses_current_selected_model(self):
        self.assertIn("str(matches[label])",ONNX.read_text())
        self.assertIn("_official.installed(target_root())",ONNX.read_text())
        self.assertIn("command = _onnx.command(root / 'input.png', cfg['model'])",MAIN.read_text())

    def test_builder_includes_bundled_fallback_manifest(self):
        s=(ROOT/'scripts/build-ocr-plugin-c2.py').read_text()
        self.assertIn("'catalog_builtin.json'",s)
        self.assertIn("'official_models_c2.py'",s)
        ast.parse(MAIN.read_text());ast.parse(ONNX.read_text())

    def test_actions_use_only_official_paddlepaddle_weights(self):
        s=FLOW.read_text()
        self.assertIn('PaddlePaddle/PP-OCRv6_tiny_det_onnx',s)
        self.assertIn('PaddlePaddle/PP-OCRv6_tiny_rec_onnx',s)
        self.assertNotIn('ppocr_v6_tiny.zip',s)

if __name__=='__main__':unittest.main()
