"""B2-C2 HTTP contract tests against a throwaway loopback server only."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from snapmark.ai_runtime import RuntimeIntegrationError
from snapmark.runtime_idle import (
    supports_idle_write, read_idle_capability, change_idle_seconds,
    validate_idle_seconds,
)


class FakeHandler(BaseHTTPRequestHandler):
    version = '1.0.0'
    seconds = 600
    missing_field = False
    requests = []
    write_error = False

    def send_data(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.requests.append(('GET', self.path, None))
        if self.path == '/health':
            return self.send_data(200, {'status': 'ok', 'runtime_version': self.version})
        if self.path == '/v1/runtime/status':
            return self.send_data(200, {'idle_unload_seconds': self.seconds})
        if self.path == '/v1/runtime/preferences':
            prefs = {'backend_preference': 'auto', 'preload_model': ''}
            if not self.missing_field:
                prefs['idle_unload_seconds'] = self.seconds
            return self.send_data(200, prefs)
        self.send_data(404, {'error': {'message': 'unknown'}})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        payload = json.loads(body)
        self.requests.append(('POST', self.path, payload))
        if self.write_error:
            return self.send_data(400, {'error': {'message': 'bad preference'}})
        if self.path != '/v1/runtime/preferences':
            return self.send_data(404, {})
        type(self).seconds = payload['idle_unload_seconds']
        return self.send_data(200, {
            'idle_unload_seconds': self.seconds,
            'backend_preference': 'auto', 'preload_model': '',
            'backend_changed': False, 'applies_on_next_start': False,
        })

    def log_message(self, *_):
        pass


class IdlePreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeHandler)
        cls.endpoint = f'http://127.0.0.1:{cls.server.server_address[1]}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        FakeHandler.version = '1.0.0'
        FakeHandler.seconds = 600
        FakeHandler.requests = []
        FakeHandler.missing_field = False
        FakeHandler.write_error = False

    def test_versions_are_strict(self):
        for version in ('0.8.0', '1.0.0-rc1', '1.0.0-dev', '', 'garbage'):
            self.assertFalse(supports_idle_write(version))
        self.assertTrue(supports_idle_write('1.0.0'))
        self.assertTrue(supports_idle_write('1.1.2'))

    def test_rejects_bool_float_text_and_out_of_range(self):
        for value in (True, False, 0.5, '600', -1, 86401, None):
            with self.assertRaises(RuntimeIntegrationError):
                validate_idle_seconds(value)
        for value in (0, 1, 75, 600, 86400):
            self.assertEqual(validate_idle_seconds(value), value)

    def test_old_runtime_read_only_even_if_get_exists(self):
        state = read_idle_capability(self.endpoint, '0.8.0')
        self.assertFalse(state.writable)
        self.assertFalse(FakeHandler.requests)
        FakeHandler.version = '0.8.0'
        with self.assertRaises(RuntimeIntegrationError):
            change_idle_seconds(self.endpoint, 300, expected_seconds=600, confirmed=True)
        self.assertFalse(any(x[0] == 'POST' for x in FakeHandler.requests))

    def test_missing_capability_stays_read_only(self):
        FakeHandler.missing_field = True
        result = read_idle_capability(self.endpoint, '1.0.0')
        self.assertFalse(result.writable)
        self.assertFalse(any(x[0] == 'POST' for x in FakeHandler.requests))

    def test_read_never_posts(self):
        state = read_idle_capability(self.endpoint, '1.0.0')
        self.assertTrue(state.writable)
        self.assertEqual(state.seconds, 600)
        self.assertEqual([m for m, _, _ in FakeHandler.requests], ['GET'])

    def test_post_requires_confirmation(self):
        with self.assertRaises(RuntimeIntegrationError):
            change_idle_seconds(self.endpoint, 300, expected_seconds=600)
        self.assertEqual(FakeHandler.requests, [])

    def test_exact_payload_and_verified_result(self):
        self.assertEqual(change_idle_seconds(self.endpoint, 300,
                                              expected_seconds=600, confirmed=True), 300)
        posts = [r for r in FakeHandler.requests if r[0] == 'POST']
        self.assertEqual(posts, [('POST', '/v1/runtime/preferences', {'idle_unload_seconds': 300})])
        self.assertEqual(FakeHandler.seconds, 300)
        self.assertEqual(FakeHandler.requests[-1][0], 'GET')

    def test_zero_disables_unload(self):
        self.assertEqual(change_idle_seconds(self.endpoint, 0,
                                              expected_seconds=600, confirmed=True), 0)
        self.assertEqual(FakeHandler.seconds, 0)

    def test_rejects_stale_value_without_post(self):
        FakeHandler.seconds = 90
        with self.assertRaisesRegex(RuntimeIntegrationError, 'changed'):
            change_idle_seconds(self.endpoint, 300, expected_seconds=600, confirmed=True)
        self.assertFalse(any(x[0] == 'POST' for x in FakeHandler.requests))

    def test_noop_does_not_post(self):
        self.assertEqual(change_idle_seconds(self.endpoint, 600,
                                              expected_seconds=600, confirmed=True), 600)
        self.assertFalse(any(x[0] == 'POST' for x in FakeHandler.requests))

    def test_error_is_visible_and_does_not_claim_success(self):
        FakeHandler.write_error = True
        with self.assertRaisesRegex(RuntimeIntegrationError, '400'):
            change_idle_seconds(self.endpoint, 300, expected_seconds=600, confirmed=True)


if __name__ == '__main__':
    unittest.main()
