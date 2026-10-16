"""C2-023 GitHub-only PP-OCRv6 tiny dictionary regression checks."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / '.github/workflows/ocr-onnx-engine.yml'

class OfficialTinyDictionaryTests(unittest.TestCase):
    def test_official_dictionary_is_downloaded_on_github_runner(self):
        s=FLOW.read_text()
        self.assertIn('https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/ppocrv6_tiny_dict.txt',s)
        self.assertIn('--output "$MODEL_STAGE/dict.txt"',s)
        self.assertIn('SNAPMARK_V6_TINY_DICT_ENTRIES=',s)
        self.assertIn('len(chars) != 6904',s)
        self.assertNotIn('Expected exactly one OCR dictionary:',s)

    def test_dictionary_available_before_real_inference_and_not_installed_locally(self):
        s=FLOW.read_text()
        self.assertLess(s.index('--output "$MODEL_STAGE/dict.txt"'),
                        s.index('node worker.cjs --smoke-test --model-dir "$MODEL_STAGE"'))
        self.assertIn('ONNXRUNTIME_NODE_INSTALL: skip',s)
        self.assertIn('runs-on: ubuntu-24.04',s)

if __name__ == '__main__':
    unittest.main()
