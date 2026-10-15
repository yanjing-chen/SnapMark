"""Static UI guardrails work even without GTK installed in CI."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiB2C2Contracts(unittest.TestCase):
    def test_explicit_ui_consent_async_and_capability_gate(self):
        ui = (ROOT / 'snapmark/ai_runtime_ui.py').read_text()
        for fragment in ('Custom idle timeout', 'Save timeout…',
                         'Change shared Runtime idle timeout?',
                         "dialog.set_default_response('cancel')",
                         "response != 'save'",
                         'change_idle_seconds(endpoint, seconds,',
                         'read_idle_capability(endpoint, version)',
                         'threading.Thread(target=worker, daemon=True).start()',
                         'Shared Runtime setting · view only'):
            self.assertIn(fragment, ui)
        self.assertNotIn('subprocess.', ui)
        self.assertNotIn('systemctl', ui)

    def test_no_existing_registration_or_ocr_removed(self):
        ui = (ROOT / 'snapmark/ai_runtime_ui.py').read_text()
        for fragment in ('register_reviewed_model', '_inspect_bundle', '_choose_folder',
                         "self.widgets['idle_unload'].set_subtitle(describe_idle_unload(result))"):
            self.assertIn(fragment, ui)


if __name__ == '__main__':
    unittest.main()
