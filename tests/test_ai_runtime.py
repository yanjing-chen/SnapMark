"""Network and configuration contracts for read-only AI Runtime integration."""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from snapmark.ai_runtime import (DEFAULT_ENDPOINT, RuntimeIntegrationError,
                                 RuntimeSettings, probe_runtime, validate_endpoint)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'settings' / 'ai-runtime.json'
        self.settings = RuntimeSettings(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_is_disabled_auto_and_existing_port(self):
        self.assertEqual(self.settings.load(), {
            'enabled': False, 'backend_preference': 'auto', 'endpoint': DEFAULT_ENDPOINT})
        self.assertFalse(self.path.exists(), 'Reading defaults must not write settings')

    def test_atomic_setting_preserves_independent_preferences(self):
        self.settings.update(enabled=True)
        self.settings.update(endpoint='http://localhost:8111/', backend_preference='vulkan')
        self.assertEqual(self.settings.load(), {
            'enabled': True, 'backend_preference': 'vulkan', 'endpoint': 'http://localhost:8111'})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.settings.update(enabled=False)
        self.assertEqual(self.settings.load()['backend_preference'], 'vulkan')

    def test_corrupt_settings_fail_closed(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{wrong', encoding='utf-8')
        self.assertFalse(self.settings.load()['enabled'])

    def test_bad_input_makes_no_change(self):
        before = self.settings.update(enabled=True)
        content = self.path.read_bytes()
        for changes in ({'enabled': 'yes'}, {'endpoint': 'https://example.com/api'},
                        {'backend_preference': 'nvidia'}, {'invalid': True}):
            with self.assertRaises(RuntimeIntegrationError):
                self.settings.update(**changes)
            self.assertEqual(self.path.read_bytes(), content)
        self.assertEqual(self.settings.load(), before)

    def test_endpoint_rules(self):
        for val in ('file:///etc/passwd', 'http://localhost:8111/v1/models',
                    'http://user:secret@localhost:8111', 'http://localhost',
                    'http://localhost:8111?token=123', 'http://localhost:bad', 'junk'):
            with self.subTest(value=val), self.assertRaises(RuntimeIntegrationError):
                validate_endpoint(val)
        self.assertEqual(validate_endpoint(DEFAULT_ENDPOINT), DEFAULT_ENDPOINT)


class Handler(BaseHTTPRequestHandler):
    routes = {}
    seen = []

    def do_GET(self):
        self.seen.append(('GET', self.path))
        status, payload = self.routes.get(self.path, (404, {'error': 'missing'}))
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_POST(self):
        self.seen.append(('POST', self.path))
        self.send_error(405)

    def log_message(self, *_args):
        pass


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.endpoint = f'http://127.0.0.1:{cls.server.server_address[1]}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        Handler.seen.clear()
        Handler.routes = {
            '/health': (200, {'status': 'ok'}),
            '/v1/runtime/backends': (200, {'effective_backend': 'vulkan'}),
            '/v1/models?refresh=1': (200, {'data': [
                {'id': 'paddleocr-vl-1.6'}, {'id': 'hy-mt2-7b'}, {'id': 'paddleocr-vl-1.6'}]})}

    def test_can_read_health_models_and_backend_without_writing_to_runtime(self):
        snapshot = probe_runtime(self.endpoint)
        self.assertEqual(snapshot.health, 'ok')
        self.assertEqual(snapshot.backend, 'vulkan')
        self.assertEqual(snapshot.models, ('paddleocr-vl-1.6', 'hy-mt2-7b'))
        self.assertEqual(Handler.seen, [
            ('GET', '/health'), ('GET', '/v1/runtime/backends'),
            ('GET', '/v1/models?refresh=1')])

    def test_optional_endpoint_failure_does_not_hide_successful_connection(self):
        Handler.routes['/v1/runtime/backends'] = (404, {})
        Handler.routes['/v1/models?refresh=1'] = (404, {})
        s = probe_runtime(self.endpoint)
        self.assertEqual(s.health, 'ok')
        self.assertEqual(s.models, ())
        self.assertIn('404', s.models_error)
        self.assertIn('404', s.backend_error)

    def test_health_failure_is_not_connected(self):
        Handler.routes['/health'] = (500, {})
        with self.assertRaises(RuntimeIntegrationError):
            probe_runtime(self.endpoint)

    def test_no_external_connections_on_settings_load(self):
        with tempfile.TemporaryDirectory() as tmp, patch('snapmark.ai_runtime.urlopen') as opener:
            state = RuntimeSettings(Path(tmp) / 'prefs.json')
            self.assertFalse(state.load()['enabled'])
            opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
