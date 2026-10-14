"""End-to-end tests with a fake local Runtime; never touch real user registry."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from snapmark.ai_runtime import RuntimeIntegrationError
from snapmark.model_bundle import inspect_gguf_files
from snapmark.runtime_registration import inspect_registration, register_reviewed_model


class FakeRuntime(BaseHTTPRequestHandler):
    registered = {}
    history = []
    unsafe = False

    def respond(self, status, data):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        self.history.append(('GET', self.path))
        if self.path == '/v1/models/custom':
            self.respond(200, {'data': list(self.registered.values())})
        elif self.path == '/v1/models?refresh=1':
            self.respond(200, {'data': [{'id': 'paddleocr-vl-1.6'}, *self.registered.values()]})
        else:
            self.respond(404, {})

    def do_POST(self):
        size = int(self.headers['Content-Length'])
        payload = json.loads(self.rfile.read(size))
        self.history.append(('POST', self.path))
        if self.path == '/v1/models/inspect':
            self.respond(200, {'object': 'gguf.inspection', 'suggested': {
                'id': 'smolvlm-500m-test', 'display_name': 'SmolVLM 500M test',
                'type': 'vision', 'context_size': 4096, 'gpu_layers': 99,
                'default_prompt': 'Describe:', 'capabilities': {'vision': True, 'ocr': False}}})
        elif self.path == '/v1/models/custom':
            if self.unsafe:
                self.respond(500, {'error': 'backend failed'})
            elif payload['id'] in self.registered:
                self.respond(409, {'error': 'collision'})
            else:
                self.registered[payload['id']] = {'id': payload['id'], 'source': 'custom',
                                                  'model_path': payload['model_path'],
                                                  'mmproj_path': payload['mmproj_path']}
                self.respond(201, self.registered[payload['id']])
        else:
            self.respond(404, {})

    def log_message(self, *_args):
        pass


class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeRuntime)
        cls.endpoint = 'http://127.0.0.1:' + str(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        FakeRuntime.registered = {}
        FakeRuntime.history = []
        self.main = Path(self.tmp.name) / 'SmolVLM-500M-Q8_0.gguf'
        self.proj = Path(self.tmp.name) / 'mmproj-SmolVLM-500M-Q8_0.gguf'
        self.main.write_bytes(b'GGUF' + b'0' * 64)
        self.proj.write_bytes(b'GGUF' + b'1' * 48)
        (self.bundle,) = inspect_gguf_files([self.main, self.proj])

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_readonly_then_explicit_confirm_registers_one_model(self):
        review = inspect_registration(self.endpoint, self.bundle)
        self.assertEqual(review.payload['mmproj_path'], str(self.proj.resolve()))
        self.assertEqual(review.payload['model_path'], str(self.main.resolve()))
        self.assertFalse(FakeRuntime.registered)
        self.assertEqual([route for method, route in FakeRuntime.history if method == 'POST'],
                         ['/v1/models/inspect'])
        with self.assertRaisesRegex(RuntimeIntegrationError, 'explicit user confirmation'):
            register_reviewed_model(review)
        self.assertFalse(FakeRuntime.registered)
        result = register_reviewed_model(review, confirmed=True)
        self.assertEqual(result['source'], 'custom')
        self.assertEqual(FakeRuntime.registered[result['id']]['mmproj_path'], str(self.proj))
        self.assertEqual([route for method, route in FakeRuntime.history if method == 'POST'],
                         ['/v1/models/inspect', '/v1/models/custom'])

    def test_no_overwrite_existing_or_catalog_entry(self):
        review = inspect_registration(self.endpoint, self.bundle)
        FakeRuntime.registered[review.payload['id']] = {'id': review.payload['id']}
        with self.assertRaisesRegex(RuntimeIntegrationError, 'already registered|already registered while|registered while'):
            register_reviewed_model(review, confirmed=True)
        self.assertFalse(any(method == 'POST' and route == '/v1/models/custom'
                             for method, route in FakeRuntime.history))

    def test_files_changed_after_inspection_cannot_be_registered(self):
        review = inspect_registration(self.endpoint, self.bundle)
        self.proj.write_bytes(b'GGUFmodified')
        with self.assertRaisesRegex(RuntimeIntegrationError, 'changed'):
            register_reviewed_model(review, confirmed=True)
        self.assertFalse(FakeRuntime.registered)

    def test_remote_registration_rejected_before_network(self):
        for endpoint in ('http://example.com:8111', 'https://127.0.0.1:8111'):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(RuntimeIntegrationError, 'loopback'):
                inspect_registration(endpoint, self.bundle)
        self.assertFalse(FakeRuntime.history)

    def test_split_bundle_blocked(self):
        first = Path(self.tmp.name) / 'model-00001-of-00002.gguf'
        second = Path(self.tmp.name) / 'model-00002-of-00002.gguf'
        first.write_bytes(b'GGUFhello')
        second.write_bytes(b'GGUFhello')
        (bundle,) = inspect_gguf_files([first, second])
        with self.assertRaisesRegex(RuntimeIntegrationError, 'Split GGUF'):
            inspect_registration(self.endpoint, bundle)
        self.assertFalse(FakeRuntime.history)


if __name__ == '__main__':
    unittest.main()
