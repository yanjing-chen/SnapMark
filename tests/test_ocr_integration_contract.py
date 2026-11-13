"""Integration contracts for the current built-in OCR workflow."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source(file):
    text = (ROOT / 'snapmark' / file).read_text(encoding='utf-8')
    ast.parse(text)
    return text

class OCR4IntegrationContracts(unittest.TestCase):
    def test_tray_session_controls_click_not_auto_ocr(self):
        app = source('app.py')
        tray = source('tray.py')
        self.assertIn('self._screenshot_session = ScreenshotSession()', app)
        self.assertIn('def open_recent_screenshot(self):', app)
        method = app.split('    def open_recent_screenshot(self):',1)[1].split('    def open_history(self):',1)[0]
        self.assertIn('self.show_editor(Path(name))', method)
        self.assertNotIn('.run(', method)
        self.assertNotIn('ocr_toggle', method)
        self.assertIn('self.clipboard_ready() if index == 2 else True', tray)
        self.assertIn('ItemsPropertiesUpdated', tray)
        self.assertIn('LayoutUpdated', tray)

    def test_menu_and_refresh_model_workflow(self):
        gui = source('ocr_builtin.py')
        self.assertNotIn('恢复之前移出的模型', gui)
        self.assertNotIn('安装 / 更新', gui)
        self.assertIn('explicitly_requested=True', gui)
        self.assertIn('save_ocr_settings(hidden_models=[])', gui)
        self.assertIn('append_only_model(name)', gui)
        self.assertIn('set_propagate_natural_height(True)', gui)
        self.assertIn('Pango.EllipsizeMode.END', gui)

    def test_preferences_keep_timeout_independent(self):
        prefs = source('preferences.py')
        editor = source('editor.py')
        self.assertIn('screenshot_ocr_timeout', prefs)
        self.assertIn('set_screenshot_ocr_timeout', prefs)
        self.assertIn('ScreenshotSession', source('app.py'))
        self.assertIn('refresh_recent_screenshot_status()', editor)
        self.assertIn('screenshot_group.add(timeout_row)', editor)

    def test_obsolete_runtime_source_removed(self):
        self.assertFalse((ROOT / 'snapmark/ai_runtime.py').exists())
        self.assertFalse((ROOT / 'official_plugins').exists())
        self.assertFalse((ROOT / '.github/workflows/ocr-onnx-engine.yml').exists())

if __name__ == '__main__': unittest.main()
