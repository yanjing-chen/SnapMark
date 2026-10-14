"""UI contract tests that also run on machines without Gtk available."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeUiContractTests(unittest.TestCase):
    def test_runtime_is_own_preferences_tab(self):
        text = (ROOT / 'snapmark/ai_runtime_ui.py').read_text()
        self.assertIn("stack.add_titled(page, 'ai-runtime', 'AI Runtime')", text)
        self.assertIn('Enable AI Runtime integration', text)
        self.assertIn('Use existing Runtime', text)
        self.assertIn('Not reported by Runtime', (ROOT / 'snapmark/ai_runtime.py').read_text())
        editor = (ROOT / 'snapmark/editor.py').read_text()
        self.assertIn('AIRuntimePreferences(window, stack)', editor)
        app = (ROOT / 'snapmark/app.py').read_text()
        self.assertIn("window._runtime_preferences.widgets['status']", app)

    def test_no_service_mutation_or_automatic_model_download(self):
        src = (ROOT / 'snapmark/ai_runtime.py').read_text()
        tree = ast.parse(src)
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
        self.assertFalse(any(alias.name == 'subprocess' for item in imports for alias in item.names))
        self.assertNotIn("method='POST'", src)
        self.assertNotIn('systemctl', src)
        self.assertNotIn('wget ', src)
        self.assertNotIn('paddleocr-vl', src.lower())


if __name__ == '__main__':
    unittest.main()
