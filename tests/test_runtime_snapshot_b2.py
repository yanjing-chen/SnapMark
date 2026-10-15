"""B2: independently report installed, loaded and actually active backend."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from snapmark.ai_runtime import probe_runtime


class Handler(BaseHTTPRequestHandler):
    health = {}
    models = {}
    def do_GET(self):
        data = (self.health if self.path == '/health' else
                self.models if self.path == '/v1/models' else
                {'effective_backend': 'vulkan'} if self.path == '/v1/runtime/backends' else None)
        self.send_response(200 if data is not None else 404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data or {}).encode())
    def log_message(self, *args):
        pass


class RuntimeSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.endpoint = 'http://127.0.0.1:' + str(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        Handler.health = {'status': 'ok', 'runtime_version': '0.8.0',
                          'current_model': None, 'backend_running': False,
                          'backend_preference': 'auto', 'active_backend': None}
        Handler.models = {'data': [
            {'id': 'paddleocr-vl-1.6', 'installed': True,
             'capabilities': {'ocr': True, 'vision': True, 'translation': False},
             'operation': {'state': 'idle'}},
            {'id': 'example-translation', 'installed': False,
             'capabilities': {'translation': True}}]}

    def test_installed_does_not_mean_loaded_and_vulkan_is_not_active(self):
        snap = probe_runtime(self.endpoint)
        self.assertEqual(snap.version, '0.8.0')
        self.assertEqual(snap.backend, 'vulkan')
        self.assertFalse(snap.backend_running)
        self.assertEqual(snap.active_backend, '')
        self.assertEqual(snap.current_model, '')
        self.assertEqual(snap.configured_backend, 'auto')
        self.assertTrue(snap.detailed_models[0].installed)
        self.assertEqual(snap.detailed_models[0].capabilities, ('ocr', 'vision'))
        self.assertFalse(snap.detailed_models[1].installed)

    def test_only_running_model_can_be_marked_loaded(self):
        Handler.health.update(backend_running=True, active_backend='cuda',
                              current_model='paddleocr-vl-1.6')
        snap = probe_runtime(self.endpoint)
        self.assertTrue(snap.backend_running)
        self.assertEqual(snap.active_backend, 'cuda')
        self.assertEqual(snap.current_model, 'paddleocr-vl-1.6')

    def test_do_not_trust_active_backend_if_backend_is_not_running(self):
        Handler.health.update(backend_running=False, active_backend='cuda',
                              current_model='paddleocr-vl-1.6')
        snap = probe_runtime(self.endpoint)
        self.assertEqual(snap.active_backend, '')
        self.assertEqual(snap.current_model, '')


if __name__ == '__main__':
    unittest.main()

class RegistrationDiscoveryContractTests(unittest.TestCase):
    def test_diagnostic_script_is_get_only(self):
        from pathlib import Path
        script = (Path(__file__).resolve().parents[1] /
                  'scripts/diagnose-runtime-registration-api.sh').read_text()
        self.assertIn('openapi.json', script)
        self.assertIn("method='GET'", script)
        self.assertNotIn('curl -X POST', script)
        self.assertNotIn('systemctl', script)
