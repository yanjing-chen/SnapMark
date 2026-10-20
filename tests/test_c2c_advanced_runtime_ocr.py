"""Offline HTTP simulator for high-performance OCR. Never talks to real Runtime."""
import base64
import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'official_plugins/ocr/advanced_runtime_c2.py'
spec = importlib.util.spec_from_file_location('advanced_c2c', MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
PNG = b'\x89PNG\r\n\x1a\n' + b'fake-idat-for-transport-test'

class Handler(BaseHTTPRequestHandler):
    inventory = {'data': [
        {'id': 'paddleocr-vl-1.6', 'type':'ocr', 'installed':True, 'capabilities':{'ocr':True}},
        {'id': 'hy-mt2-7b-q8', 'type':'translation','installed':True, 'capabilities':{'translation':True}},
        {'id':'smolvlm','type':'vision','installed':True,'capabilities':{'vision':True}},
    ]}
    last_payload = None
    def log_message(self, *_): pass
    def respond(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == '/v1/models':
            self.respond(self.inventory)
        else:
            self.send_error(404)
    def do_POST(self):
        if self.path != '/v1/chat/completions':
            self.send_error(404); return
        self.last_payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.last_payload = self.last_payload
        self.respond({'choices':[{'message':{'content':'古文\nOCR success'}}]})

class AdvancedOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.endpoint = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
    def test_ocr_role_only(self):
        self.assertEqual(mod.eligible_models(Handler.inventory),['paddleocr-vl-1.6'])
    def test_no_non_ocr_model(self):
        with self.assertRaisesRegex(mod.AdvancedOCRError,'not installed and registered for OCR'):
            mod.recognize(PNG,'hy-mt2-7b-q8',endpoint=self.endpoint)
    def test_actual_multimodal_payload(self):
        result=mod.recognize(PNG,'paddleocr-vl-1.6',endpoint=self.endpoint)
        self.assertEqual(result,'古文\nOCR success')
        req=self.server.last_payload
        self.assertEqual(req['model'],'paddleocr-vl-1.6')
        self.assertFalse(req['stream'])
        self.assertEqual(req['messages'][0]['content'][0]['text'],'OCR:')
        b64=req['messages'][0]['content'][1]['image_url']['url'].split(',',1)[1]
        self.assertEqual(base64.b64decode(b64),PNG)
    def test_reject_invalid_image(self):
        with self.assertRaisesRegex(mod.AdvancedOCRError,'not a PNG'):
            mod.recognize(b'abc','paddleocr-vl-1.6',endpoint=self.endpoint)
    def test_reject_oversize_image(self):
        with self.assertRaisesRegex(mod.AdvancedOCRError,'16 MiB'):
            mod.recognize(PNG+b'x'*mod.MAX_IMAGE_BYTES,'paddleocr-vl-1.6',endpoint=self.endpoint)
    def test_refuse_remote_endpoint(self):
        with self.assertRaises(mod.AdvancedOCRError):
            mod._request('/v1/models',endpoint='http://example.com:8111')
    def test_refuse_non_ocr_type_even_with_flag(self):
        sample={'data':[{'id':'mixed','type':'vision','installed':True,'capabilities':{'ocr':True}}]}
        self.assertEqual(mod.eligible_models(sample),[])
    def test_parse_text_parts(self):
        self.assertEqual(mod.parse_result({'choices':[{'message':{'content':[{'type':'text','text':'abc'}]}}]}),'abc')
    def test_parse_empty_result(self):
        with self.assertRaises(mod.AdvancedOCRError):
            mod.parse_result({'choices':[{'message':{'content':''}}]})
    def test_old_gui_untouched_in_subprocess(self):
        self.assertNotIn('gi.repository',MODULE.read_text())
    def test_gui_integration_prepared(self):
        main = (MODULE.parent/'main.py').read_text()
        self.assertIn("cfg['mode'] == 'high_performance'",main)
        self.assertIn("str(ROOT / 'advanced_runtime_c2.py')",main)
        self.assertIn("proc.communicate(timeout=360 if", main)
    def test_package_includes_subprocess(self):
        builder=(MODULE.parents[2]/'scripts/build-ocr-plugin-c2.py').read_text()
        self.assertIn("'advanced_runtime_c2.py'",builder)

if __name__ == '__main__':
    unittest.main()
