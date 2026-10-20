"""Contract checks for hosted real-image inference. No npm install is run locally."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'scripts/ocr-onnx/worker.cjs'
FLOW = ROOT / '.github/workflows/ocr-onnx-engine.yml'

class HostedRealOCRWorkerTests(unittest.TestCase):
    def test_worker_exposes_real_image_and_model_inference(self):
        s = WORKER.read_text()
        for part in ('setOCREnv', 'await ocr.init(', 'engine.ocr(',
                     '--model-dir', '--image', 'JSON.stringify(await recognize(',
                     'SNAPMARK_ONNX_REAL_INFERENCE=PASS'):
            self.assertIn(part, s)
        self.assertNotIn('ONNX OCR inference will be enabled after model integration tests.', s)

    def test_smoke_runs_real_tiny_model_only_on_github(self):
        s = FLOW.read_text()
        for part in ('ONNXRUNTIME_NODE_INSTALL: skip',
                     'PaddlePaddle/PP-OCRv6_tiny_det_onnx', 'node worker.cjs --smoke-test',
                     'actions/upload-artifact@v4', 'node worker.cjs --self-test'):
            self.assertIn(part, s)
        self.assertIn('runs-on: ubuntu-24.04', s)

    def test_worker_requires_existing_model_and_image(self):
        s = WORKER.read_text()
        for part in ("assertFile(det, 'Detection model')", "assertFile(rec, 'Recognition model')",
                     "assertFile(dic, 'Character dictionary')", "assertFile(imagePath, 'Image')"):
            self.assertIn(part, s)
        self.assertNotIn('npm install', s)
        self.assertNotIn('paddleocr', s.lower())

if __name__ == '__main__':
    unittest.main()
