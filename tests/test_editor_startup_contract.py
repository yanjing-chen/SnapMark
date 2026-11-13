"""The editor toolbar must use the integrated OCR panel, not plugin controls."""
import ast
import unittest
from pathlib import Path

class EditorStartupContractTests(unittest.TestCase):
    def test_editor_uses_builtin_ocr(self):
        source = (Path(__file__).resolve().parents[1] / 'snapmark/editor.py').read_text()
        ast.parse(source)
        self.assertIn('from .ocr_builtin import OCRPanel, create_ocr_preferences', source)
        self.assertIn('self._ocr_panel', source)
        self.assertIn('self.ocr_toggle', source)
        self.assertNotIn('self._plugin_tools', source)

if __name__ == '__main__': unittest.main()
