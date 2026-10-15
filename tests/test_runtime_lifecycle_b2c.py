"""B2-C1 uses existing Runtime health without changing service behavior."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from snapmark.ai_runtime import (probe_runtime, describe_idle_unload, describe_preload)


class Handler(BaseHTTPRequestHandler):
    health = {}
    methods = []

    def do_GET(self):
        self.methods.append(('GET', self.path))
        if self.path == '/health':
            payload = self.health
        elif self.path == '/v1/runtime/backends':
            payload = {'selected': 'vulkan'}
        elif self.path == '/v1/models':
            payload = {'data': []}
        else:
            self.send_error(404)
            return
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.methods.append(('POST', self.path))
        self.send_error(405)

    def log_message(self, *args):
        return


class LifecycleTests(unittest.TestCase):
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
        Handler.methods = []
        Handler.health = {
            'status': 'ok', 'runtime_version': '0.8.0',
            'startup_preload': {'enabled': False, 'model': '', 'state': 'disabled'},
            'idle_unload_seconds': 600, 'backend_running': False,
            'current_model': None, 'active_backend': None,
            'backend_preference': 'auto'
        }

    def test_existing_runtime_idle_and_no_startup_preload(self):
        snap = probe_runtime(self.endpoint)
        self.assertEqual(describe_preload(snap), 'Disabled · load when requested')
        self.assertEqual(snap.preload_state, 'disabled')
        self.assertEqual(describe_idle_unload(snap), '10 minute(s) (600 seconds)')
        self.assertFalse(snap.backend_running)
        self.assertEqual(snap.active_backend, '')
        self.assertEqual(snap.current_model, '')
        self.assertTrue(Handler.methods)
        self.assertTrue(all(method == 'GET' for method, _ in Handler.methods))

    def test_startup_preload_enabled_is_distinct_from_running(self):
        Handler.health['startup_preload'] = {'enabled': True, 'model': 'sample-model', 'state': 'loading'}
        snap = probe_runtime(self.endpoint)
        self.assertEqual(describe_preload(snap), 'Enabled · sample-model')
        self.assertEqual(snap.preload_state, 'loading')
        self.assertFalse(snap.backend_running)

    def test_missing_fields_are_not_invented(self):
        del Handler.health['startup_preload']
        del Handler.health['idle_unload_seconds']
        snap = probe_runtime(self.endpoint)
        self.assertIsNone(snap.preload_enabled)
        self.assertIsNone(snap.idle_unload_seconds)
        self.assertEqual(describe_preload(snap), 'Not reported by Runtime')
        self.assertEqual(describe_idle_unload(snap), 'Not reported by Runtime')

    def test_reject_invalid_unload_intervals_and_bool_as_int(self):
        for invalid in [True, '600', -1, 10.5, {}, None]:
            Handler.health['idle_unload_seconds'] = invalid
            self.assertIsNone(probe_runtime(self.endpoint).idle_unload_seconds)

    def test_zero_is_not_treated_as_immediate_or_never(self):
        Handler.health['idle_unload_seconds'] = 0
        self.assertEqual(describe_idle_unload(probe_runtime(self.endpoint)),
                         '0 seconds (Runtime-defined behavior)')

    def test_different_idle_units(self):
        Handler.health['idle_unload_seconds'] = 3600
        self.assertIn('1 hour(s)', describe_idle_unload(probe_runtime(self.endpoint)))
        Handler.health['idle_unload_seconds'] = 75
        self.assertEqual(describe_idle_unload(probe_runtime(self.endpoint)), '75 seconds')


if __name__ == '__main__':
    unittest.main()
