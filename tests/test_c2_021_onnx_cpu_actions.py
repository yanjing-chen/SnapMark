"""C2-021: hosted CPU ONNX install; no GPU NuGet postinstall and no local install."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/ocr-onnx-engine.yml'

class HostedONNXCPUInstallTests(unittest.TestCase):
    def test_onnx_cpu_postinstall_skips_broken_cuda_download(self):
        text = WORKFLOW.read_text()
        step = text.split('      - name: Install ONNX dependencies on GitHub, never on Code01\n', 1)[1].split('      - name:', 1)[0]
        self.assertIn('ONNXRUNTIME_NODE_INSTALL: skip', step)
        self.assertIn('npm install --omit=dev --no-audit --no-fund', step)
        self.assertNotIn('sudo ', step)

    def test_build_still_runs_real_node_self_test_and_uploads_artifact(self):
        text = WORKFLOW.read_text()
        self.assertIn('node worker.cjs --self-test', text)
        self.assertIn('actions/upload-artifact@v4', text)
        self.assertIn('SnapMark-OCR-ONNX-linux-x86_64.tar.gz', text)
        self.assertIn('branches: [snapmark-c2-onnx]', text)

if __name__ == '__main__':
    unittest.main()
