"""Regression: a passive Settings check must not rescan GGUF models.

Uses only ephemeral loopback HTTP and a fake Runtime, never real :8111.
"""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from snapmark.ai_runtime import probe_runtime


class ModelServer(BaseHTTPRequestHandler):
    history = []

    def do_GET(self):
        self.history.append(('GET', self.path))
        if self.path == '/health':
            data = {'status': 'ok', 'runtime_version': '0.8.0'}
        elif self.path == '/v1/runtime/backends':
            data = {'effective_backend': 'vulkan'}
        elif self.path == '/v1/models':
            data = {'data': [{'id': 'cached-model', 'installed': True}]}
        elif self.path == '/v1/models?refresh=1':
            time.sleep(0.15)  # slower scan, independent of fast health checks
            data = {'data': [{'id': 'refreshed-model', 'installed': True}]}
        else:
            self.send_error(404)
            return
        body = json.dumps(data).encode('utf-8')
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # expected if client intentionally tests a short timeout

    def do_POST(self):
        self.history.append(('POST', self.path))
        self.send_error(405)

    def log_message(self, *_args):
        pass


class ModelQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), ModelServer)
        cls.endpoint = f'http://127.0.0.1:{cls.server.server_address[1]}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        ModelServer.history.clear()

    def test_default_is_cached_fast_and_never_scans(self):
        snapshot = probe_runtime(self.endpoint, timeout=0.5)
        self.assertEqual(snapshot.models, ('cached-model',))
        self.assertIn(('GET', '/v1/models'), ModelServer.history)
        self.assertNotIn(('GET', '/v1/models?refresh=1'), ModelServer.history)
        self.assertTrue(all(method == 'GET' for method, _ in ModelServer.history))

    def test_manual_refresh_uses_independent_timeout(self):
        snapshot = probe_runtime(self.endpoint, timeout=0.05,
                                 refresh_models=True, refresh_timeout=1.0)
        self.assertEqual(snapshot.models, ('refreshed-model',))
        self.assertIn(('GET', '/v1/models?refresh=1'), ModelServer.history)
        self.assertNotIn(('GET', '/v1/models'), ModelServer.history)
        self.assertTrue(all(method == 'GET' for method, _ in ModelServer.history))

    def test_refresh_timeout_does_not_break_health_check(self):
        snapshot = probe_runtime(self.endpoint, timeout=0.03,
                                 refresh_models=True, refresh_timeout=0.03)
        self.assertEqual(snapshot.health, 'ok')
        self.assertIn('timed out', snapshot.models_error.lower())
        self.assertEqual(snapshot.models, ())
        self.assertTrue(all(method == 'GET' for method, _ in ModelServer.history))

    def test_ui_exposes_explicit_refresh_without_regression_to_idle(self):
        ui = (Path(__file__).resolve().parents[1] / 'snapmark/ai_runtime_ui.py').read_text()
        for marker in ("label='Refresh Models'", 'def _refresh_models_clicked(',
                       'refresh_models=True', 'Custom idle timeout',
                       'change_idle_seconds(endpoint, seconds,'):
            self.assertIn(marker, ui)


if __name__ == '__main__':
    unittest.main()
