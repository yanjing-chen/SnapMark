import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from snapmark.plugin_host import PluginHost, load_plugin
from snapmark.plugins import PluginManager


class FakeEditor:
    def __init__(self):
        self.tools = []
        self.results = []

    def add_plugin_action(self, ident, label, callback):
        self.tools.append((ident, label, callback))

    def add_plugin_result(self, ident, label, factory):
        self.results.append((ident, label, factory))


class PluginHostTests(unittest.TestCase):
    def test_no_code_loaded_without_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = PluginManager(root / 'plugins', root / 'config')
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, 'w') as archive:
                archive.writestr('plugin.json', '{"id":"ocr","version":"0.1.0",'
                                 '"api_version":1,"entrypoint":"main:register"}')
                archive.writestr('main.py',
                    'def register(host):\n'
                    '    host.register_toolbar_action("ocr", "Run OCR", lambda: None)\n'
                    '    host.register_preferences_page("ocr", "OCR", lambda e: None)\n'
                    '    host.register_result_panel("ocr", "Result", lambda e: None)\n')
            raw = payload.getvalue()
            manager.install_zip(raw, 'ocr', '0.1.0', hashlib.sha256(raw).hexdigest())
            editor = FakeEditor()
            host = PluginHost(editor)
            self.assertFalse(load_plugin(manager, 'ocr', host))
            self.assertEqual(editor.tools, [])
            manager.select('ocr', '0.1.0')
            self.assertTrue(load_plugin(manager, 'ocr', host))
            self.assertEqual(editor.tools[0][:2], ('ocr', 'Run OCR'))
            self.assertIn('ocr', host.settings_factories)
            self.assertEqual(len(editor.results), 1)
            manager.set_enabled('ocr', False)
            self.assertFalse(load_plugin(manager, 'ocr', host))


if __name__ == '__main__':
    unittest.main()
