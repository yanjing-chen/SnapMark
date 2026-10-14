"""B2 GUI structure and no-writes preflight independent of GTK availability."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class B2Contracts(unittest.TestCase):
    def test_file_and_folder_selector_and_distinct_backend_states(self):
        ui = (ROOT / 'snapmark/ai_runtime_ui.py').read_text(encoding='utf-8')
        self.assertIn('Select files…', ui)
        self.assertIn('Select folder…', ui)
        self.assertIn('Active inference backend', ui)
        self.assertIn('Model loaded in memory', ui)
        self.assertIn('inspect_gguf_files(paths)', ui)
        self.assertIn('inspect_gguf_folder(folder)', ui)
        self.assertIn('result.backend_running', ui)
        self.assertIn('result.current_model', ui)

    def test_b2_import_remains_non_mutating(self):
        code = (ROOT / 'snapmark/model_bundle.py').read_text(encoding='utf-8')
        tree = ast.parse(code)
        bad = {'subprocess', 'shutil', 'requests'}
        imported = {a.name.split('.')[0] for n in ast.walk(tree)
                    if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse(bad & imported)
        self.assertNotIn('method=\'POST\'', code)
        self.assertNotIn('.write_bytes(', code)
        self.assertNotIn('.write_text(', code)
        runtime = (ROOT / 'snapmark/ai_runtime.py').read_text(encoding='utf-8')
        self.assertNotIn("method='POST'", runtime)


if __name__ == '__main__':
    unittest.main()
