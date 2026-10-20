"""C2-026: prebuilt ONNX CPU OCR contract; no native install during tests."""
import ast
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'official_plugins/ocr/main.py'
HELPER = ROOT / 'official_plugins/ocr/onnx_c2.py'


def load_helper():
    spec = importlib.util.spec_from_file_location('snapmark_onnx_c2_testing', HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StandaloneONNXIntegrationTests(unittest.TestCase):
    def test_version_and_bundle_content(self):
        manifest = json.loads((ROOT / 'official_plugins/ocr/plugin.json').read_text())
        self.assertEqual(manifest['version'], '0.2.0')
        builder = (ROOT / 'scripts/build-ocr-plugin-c2.py').read_text()
        self.assertIn("'onnx_c2.py'", builder)
        self.assertIn("'official_models_c2.py'", builder)
        self.assertIn('SnapMark-ocr-0.2.0.zip', builder)

    def test_controller_uses_onnx_only_for_lightweight(self):
        source = MAIN.read_text()
        ast.parse(source)
        self.assertIn('items = list(_onnx.available_models())', source)
        self.assertIn("if cfg['model'] in _onnx.available_models():", source)
        self.assertIn("command = _onnx.command(root / 'input.png', cfg['model'])", source)
        self.assertIn('stdout=(subprocess.PIPE if is_onnx else subprocess.DEVNULL)', source)
        self.assertIn('json.loads(_out.decode(', source)
        self.assertIn('buffer.insert(buffer.get_end_iter(), suffix + output)', source)

    def test_preferences_requires_confirmation_and_uses_background_thread(self):
        method = MAIN.read_text().split('    def build_preferences(', 1)[1].split('    def _model_selected(', 1)[0]
        self.assertIn("Gtk.ToggleButton(label='Lightweight · PP-OCR')", method)
        self.assertIn("Gtk.ToggleButton(label='Advanced · Local AI Runtime')", method)
        self.assertIn("download = Gtk.Button(label='Download official models…')", method)
        self.assertIn("confirm.add_response('confirm','Download')", method)
        self.assertIn("if response!='confirm' or busy:return", method)
        self.assertIn('threading.Thread(target=job,daemon=True).start()', method)
        self.assertIn('_onnx.install_label(label,confirmed=True)', method)
        self.assertNotIn('_setup.install_engine(', method)
        self.assertNotIn('_setup.install_small(', method)

    def test_helper_cannot_modify_runtime_or_launch_install(self):
        source = HELPER.read_text()
        ast.parse(source)
        for forbidden in ('sudo', 'systemctl', 'pip install', 'npm install', 'local_ai_runtime',
                          'http://127.0.0.1:8111'):
            self.assertNotIn(forbidden, source)
        mod = load_helper()
        with self.assertRaises(PermissionError):
            mod.install_from_verified_stage()

    def test_installed_state_empty_directory_is_false(self):
        mod = load_helper()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(mod, 'target_root', return_value=Path(temp) / 'target'):
                self.assertFalse(mod.installed_ready())

    def test_install_never_destroys_existing_data(self):
        mod = load_helper()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'target'
            target.mkdir()
            marker = target / 'do-not-overwrite'
            marker.write_text('keep')
            with patch.object(mod, 'target_root', return_value=target), \
                    patch.object(mod, 'verified_source_ready', return_value=True), \
                    patch.object(mod, 'installed_ready', return_value=False), \
                    patch.object(mod, '_digest', return_value='invalid'):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    mod.install_from_verified_stage(confirmed=True)
            self.assertEqual(marker.read_text(), 'keep')

    def test_onnx_runner_command_is_argument_vector(self):
        mod = load_helper()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(mod, 'target_root', return_value=Path(temp)), \
                 patch.object(mod, 'engine_ready', return_value=True), \
                 patch.object(mod._official, 'installed', return_value={mod.LABEL:Path(temp)/'official-model'}):
                image = '/tmp/screenshot with spaces.png'
                cmd = mod.command(image)
                self.assertEqual(cmd[-1], image)
                self.assertIn('--ocr', cmd)
                self.assertEqual(cmd[-3], str(Path(temp) / 'official-model'))
                self.assertTrue(cmd[0].endswith('/engine/node'))
                self.assertNotIn('shell', cmd)

    def test_models_have_pinned_hashes_and_dictionary_length(self):
        mod = load_helper()
        self.assertEqual(len(mod.DET_SHA256), 64)
        self.assertEqual(len(mod.REC_SHA256), 64)
        self.assertIn('6904', (ROOT/'official_plugins/ocr/catalog_builtin.json').read_text())
        self.assertIn('PP-OCRv6 tiny (ONNX CPU)', mod.LABEL)


if __name__ == '__main__':
    unittest.main()
