"""Verify OCR worker input validation and output without installing PaddleOCR."""
import importlib.util
import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'official_plugins' / 'ocr'

spec = importlib.util.spec_from_file_location('c2_worker', DIRECTORY / 'worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
MODELS = json.loads((DIRECTORY / 'models.json').read_text('utf-8'))


class OCRWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / 'input.png'
        self.image.write_bytes(b'PNG example data')
        self.models_root = self.root / 'models'
        self.models_root.mkdir()
        self.model = 'PP-OCRv6 small'
        self.det, self.rec = MODELS[self.model]
        self.request = {'model': self.model, 'models_root': str(self.models_root),
                        'image_path': str(self.image)}

    def create_models(self):
        for name in (self.det, self.rec):
            d = self.models_root / name
            d.mkdir()
            (d / 'inference.yml').write_text('dummy for validation')

    def test_missing_models_refuses_before_import(self):
        with self.assertRaisesRegex(ValueError, 'Offline model missing'):
            worker.inspect_request(self.request, MODELS)

    def test_existing_empty_folders_refused(self):
        for name in (self.det, self.rec):
            (self.models_root / name).mkdir()
        with self.assertRaisesRegex(ValueError, 'Offline model missing'):
            worker.inspect_request(self.request, MODELS)

    def test_non_absolute_folder_rejected(self):
        self.create_models()
        self.request['models_root'] = 'relative-models'
        with self.assertRaisesRegex(ValueError, 'absolute'):
            worker.inspect_request(self.request, MODELS)

    def test_unrecognized_model_rejected(self):
        self.create_models()
        self.request['model'] = 'PP-OCRv7 fake'
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            worker.inspect_request(self.request, MODELS)

    def test_known_models_list_both_generations(self):
        self.assertEqual(len(MODELS), 5)
        self.assertTrue(any(k.startswith('PP-OCRv5') for k in MODELS))
        self.assertTrue(any(k.startswith('PP-OCRv6') for k in MODELS))

    def test_output_parses_realistic_paddlex_format(self):
        output = {'res': {'rec_texts': ['荷兰语', 'Nederlandse taal']}}
        self.assertEqual(worker._extract_text(output), '荷兰语\nNederlandse taal')

    def test_validated_local_paths_passed_to_paddleocr(self):
        self.create_models()
        seen = {}

        class FakePaddle:
            def __init__(self, **kw):
                seen.update(kw)
            def predict(self, path):
                self_path = path
                self.assertion = str(self_path)
                return [types.SimpleNamespace(json={'res': {'rec_texts': ['ABC', '荷兰']}})]

        with patch.dict('sys.modules', {'paddleocr': types.SimpleNamespace(PaddleOCR=FakePaddle)}):
            value = worker.recognize(self.request, MODELS)
        self.assertEqual(value, 'ABC\n荷兰')
        self.assertEqual(seen['device'], 'cpu')
        self.assertEqual(seen['text_detection_model_dir'], str(self.models_root / self.det))
        self.assertEqual(seen['text_recognition_model_dir'], str(self.models_root / self.rec))
        self.assertFalse(seen['use_doc_orientation_classify'])
        self.assertFalse(seen['use_doc_unwarping'])
        self.assertFalse(seen['use_textline_orientation'])

    def test_error_does_not_create_result_file(self):
        request_path = self.root / 'request.json'
        result_path = self.root / 'result.json'
        request_path.write_text(json.dumps(self.request))
        self.assertEqual(worker.main(['--request', str(request_path), '--result', str(result_path)]), 1)
        self.assertFalse(result_path.exists())


if __name__ == '__main__':
    unittest.main()
