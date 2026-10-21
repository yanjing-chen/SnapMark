"""Offline C2-F contracts. Test HTTP server uses loopback and temporary ports only."""
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUG = ROOT / 'official_plugins/ocr'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

cfg = load('c2f_profiles_test', PLUG/'profiles_c2f.py')
ocr = load('c2f_runtime_test', PLUG/'advanced_runtime_c2.py')
PNG = b'\x89PNG\r\n\x1a\n' + b'unit-test-image'

class FakeHandler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        if self.path == '/v1/models':
            data = {'data': [
                {'id':'paddleocr-vl-1.6','type':'ocr','installed':True,'capabilities':{'ocr':True}},
                {'id':'general-ocr','type':'ocr','installed':True,'capabilities':{'ocr':True}},
                {'id':'broken-ocr','type':'ocr','installed':True,'capabilities':{'ocr':True}},
            ]}
            raw = json.dumps(data).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
        else: self.send_error(404)
    def do_POST(self):
        obj = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.payload = obj
        if obj['stream']:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for chunk in ('表格', '文本'):
                data=json.dumps({'choices':[{'delta':{'content':chunk}}]}, ensure_ascii=False)
                self.wfile.write(('data: '+data+'\n\n').encode())
                self.wfile.flush()
            if obj['model'] != 'broken-ocr':
                self.wfile.write(b'data: [DONE]\n\n')
        else:
            raw = json.dumps({'choices':[{'message':{'content':'识别结果'}}]}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)

class Profiles(unittest.TestCase):
    def test_default_is_plain_without_stream(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME':tmp}):
            self.assertEqual(cfg.read_profile('not-configured')['temperature'],0.0)
        self.assertEqual(cfg.DEFAULT['output'],'Plain text')
        self.assertFalse(cfg.DEFAULT['streaming'])
    def test_paddle_native_ocr_task(self):
        self.assertEqual(cfg.prompt_for('paddleocr-vl-1.6',{}),'OCR:')
    def test_paddle_native_table_task(self):
        with self.assertRaises(ValueError):
            cfg.validate({'output':'Table recognition (experimental)'}, 'paddleocr-vl-1.6')
    def test_no_custom_paddle_prompt(self):
        with self.assertRaises(ValueError):
            cfg.validate({'preset':'Custom','prompt':'bad'},'paddleocr-vl-1.6')
    def test_table_rejected_for_non_paddle(self):
        with self.assertRaises(ValueError):
            cfg.validate({'output':'Table recognition (experimental)'},'general-ocr')
    def test_custom_prompt_supported_for_general(self):
        self.assertEqual(cfg.prompt_for('general-ocr',{'preset':'Custom','prompt':'  Copy exact text  '}),'Copy exact text')
    def test_preserve_paragraphs_in_generic_prompt(self):
        self.assertIn('paragraph boundaries', cfg.prompt_for('general-ocr',{'output':'Preserve paragraphs'}))
    def test_invalid_sampling_and_tokens_rejected(self):
        for entry in ({'temperature':float('nan')},{'max_tokens':99999},{'streaming':'yes'}, {'temperature':True}):
            with self.assertRaises(ValueError): cfg.validate(entry,'general-ocr')
    def test_profile_per_model_and_atomic(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'XDG_CONFIG_HOME':tmp}):
            cfg.save_profile('paddleocr-vl-1.6',{'temperature':0.2})
            cfg.save_profile('general-ocr',{'preset':'Custom','prompt':'Hello'})
            self.assertEqual(cfg.read_profile('paddleocr-vl-1.6')['temperature'],0.2)
            self.assertEqual(cfg.read_profile('general-ocr')['prompt'],'Hello')
            self.assertEqual(cfg.read_profile('third-model')['temperature'],0.0)
            self.assertEqual(cfg.profile_path().stat().st_mode & 0o777,0o600)
    def test_configuration_separate_from_runtime(self):
        text = (PLUG/'profiles_c2f.py').read_text()
        self.assertNotIn('systemctl',text)
        self.assertNotIn('urllib.',text)
        self.assertNotIn('subprocess.',text)
        self.assertNotIn('model_download',text)

class Network(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),FakeHandler)
        cls.endpoint=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
    def test_default_payload_unchanged(self):
        self.assertEqual(ocr.recognize(PNG,'paddleocr-vl-1.6',endpoint=self.endpoint),'识别结果')
        self.assertEqual(self.server.payload['messages'][0]['content'][0]['text'],'OCR:')
        self.assertFalse(self.server.payload['stream'])
    def test_table_payload_uses_native_task(self):
        ocr.recognize(PNG,'paddleocr-vl-1.6',endpoint=self.endpoint,
                      settings={'output':'Preserve paragraphs'})
        self.assertEqual(self.server.payload['messages'][0]['content'][0]['text'],'OCR:')
    def test_stream_success_and_partials(self):
        captured=[]
        text=ocr.recognize(PNG,'paddleocr-vl-1.6',endpoint=self.endpoint,
                           settings={'streaming':True}, on_partial=captured.append)
        self.assertEqual(text,'表格文本')
        self.assertEqual(captured,['表格','表格文本'])
    def test_incomplete_sse_rejected(self):
        with self.assertRaisesRegex(ocr.AdvancedOCRError,'Incomplete'):
            ocr.recognize(PNG,'broken-ocr',endpoint=self.endpoint,settings={'streaming':True})
    def test_stream_rejects_nonlocal_endpoint(self):
        with self.assertRaises(ocr.AdvancedOCRError):
            ocr._stream_recognize({'model':'fake'},endpoint='http://malicious.example:8111')

class Source(unittest.TestCase):
    def test_plugin_package_versions_and_contents(self):
        manifest=json.loads((PLUG/'plugin.json').read_text())
        self.assertEqual(manifest['version'],'0.2.4')
        self.assertEqual(manifest['dependencies'],{})
        builder=(ROOT/'scripts/build-ocr-plugin-c2.py').read_text()
        self.assertIn("'profiles_c2f.py'",builder)
        self.assertIn('SnapMark-ocr-0.2.4.zip',builder)
    def test_lightweight_unchanged_and_ocr_config_preserved(self):
        main=(PLUG/'main.py').read_text()
        self.assertIn('command = _onnx.command(',main)
        self.assertIn("cfg['mode'] == 'lightweight'",main)
        self.assertIn('Save as TXT',main)
        self.assertIn('_profiles_c2f.read_profile',main)
    def test_no_markdown_mode_or_unverified_sampling(self):
        profiles=(PLUG/'profiles_c2f.py').read_text()
        runtime=(PLUG/'advanced_runtime_c2.py').read_text()
        self.assertNotIn('Markdown',profiles)
        self.assertNotIn("'top_k':",runtime)
        self.assertNotIn("'thinking':",runtime)

if __name__=='__main__': unittest.main()
