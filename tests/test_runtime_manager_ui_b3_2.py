from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT/'snapmark/ai_runtime_ui.py').read_text()

class UIContract(unittest.TestCase):
    def test_all_management_actions_exist(self):
        for key in ('download', 'backup', 'install', 'rollback', 'start', 'stop',
                    'restart', 'uninstall', 'purge_config'):
            self.assertIn(f"'{key}'", UI)
    def test_mutations_all_use_confirmation(self):
        self.assertIn("dialog.set_default_response('cancel')", UI)
        self.assertIn("dialog.set_close_response('cancel')", UI)
        self.assertIn('confirmed=True',UI)
    def test_user_action_uses_worker(self):
        self.assertIn('threading.Thread(target=worker, daemon=True).start()',UI)
    def test_no_automatic_start_in_constructor(self):
        block = UI.split('    def __init__(self, window, stack):',1)[1].split('    def _management_row(',1)[0]
        self.assertNotIn('.install_verified(',block)
        self.assertNotIn('.uninstall(',block)
        self.assertNotIn('.service_action(',block)
