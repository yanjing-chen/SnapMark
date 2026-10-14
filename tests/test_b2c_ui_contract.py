"""Static contracts; executed even when GI/GTK is unavailable in CI."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class B2CUiContracts(unittest.TestCase):
    def test_memory_rows_and_consent_scope(self):
        text = (ROOT / 'snapmark/ai_runtime_ui.py').read_text()
        for item in ('Model memory management', 'Startup model preload',
                     'Runtime preload status', 'Unload after inactivity',
                     'Connected service detected', 'Service not reachable',
                     'Shared Runtime setting · view only',
                     "self.widgets['preload'].set_subtitle(describe_preload(result))",
                     "self.widgets['idle_unload'].set_subtitle(describe_idle_unload(result))"):
            self.assertIn(item, text)

    def test_installer_is_never_claimed_completed(self):
        text = (ROOT / 'snapmark/ai_runtime_ui.py').read_text()
        self.assertIn('View releases…', text)
        self.assertIn('no automatic install yet', text)
        self.assertNotIn('subprocess.', text)
        self.assertNotIn('pip install', text)

    def test_lifecycle_diagnostics_do_not_post(self):
        script = (ROOT / 'scripts/diagnose-runtime-lifecycle-api.sh').read_text()
        self.assertIn('===== EXECUTION MACHINE: Ryzen 7 6800H =====', script)
        self.assertNotIn('curl -X POST', script)
        self.assertNotIn('systemctl stop', script)
        self.assertNotIn('git reset', script)


if __name__ == '__main__':
    unittest.main()
