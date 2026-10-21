"""Regression for SSE metadata/role/null chunks observed in real Runtime usage."""
import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'official_plugins/ocr/advanced_runtime_c2.py'
spec = importlib.util.spec_from_file_location('_ocr_sse_compat', P)
ocr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocr)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_POST(self):
        data = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        assert json.loads(data).get('stream') is True
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream; charset=utf-8')
        self.end_headers()
        frames = self.server.frames
        for payload in frames:
            if payload == '[DONE]':
                raw = b'data: [DONE]\n\n'
            elif payload == 'HEARTBEAT':
                raw = b': ping\n\n'
            else:
                raw = ('data: ' + json.dumps(payload,ensure_ascii=False) + '\n\n').encode('utf8')
            self.wfile.write(raw)
            self.wfile.flush()

class StreamingCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.endpoint = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
    def run_frames(self, frames):
        self.server.frames = frames
        partials = []
        return ocr._stream_recognize({'model':'unit','stream':True},endpoint=self.endpoint,on_partial=partials.append), partials
    def test_null_role_and_finish_chunks_are_valid(self):
        frames = [
            {'choices':[{'delta':{'role':'assistant','content':None}}]},
            {'choices':[{'delta':{'content':'荷'}}]},
            {'choices':[{'delta':{'content':None},'finish_reason':'stop'}]},
            '[DONE]',
        ]
        self.assertEqual(self.run_frames(frames),('荷',['荷']))
    def test_heartbeat_usage_and_empty_choices(self):
        frames = ['HEARTBEAT', {'choices':[],'usage':{'total_tokens':7}},
                  {'choices':[{'delta':{'content':'Hello'}}]}, '[DONE]']
        self.assertEqual(self.run_frames(frames),('Hello',['Hello']))
    def test_typed_text_parts_and_metadata_only(self):
        frames = [{'choices':[{'delta':{'content':[
                    {'type':'text','text':'表'}, {'type':'metadata'}, {'type':'text','text':'格'}]}}]},
                  {'choices':[{'delta':{'content':{'type':'text','text':'A'}}}]},
                  '[DONE]']
        self.assertEqual(self.run_frames(frames),('表格A',['表格','表格A']))
    def test_invalid_nontext_chunk_not_silently_accepted(self):
        self.server.frames = [{'choices':[{'delta':{'content':123}}]},'[DONE]']
        with self.assertRaisesRegex(ocr.AdvancedOCRError,'content type'):
            ocr._stream_recognize({'stream':True},endpoint=self.endpoint)
    def test_partial_stream_cannot_succeed(self):
        self.server.frames = [{'choices':[{'delta':{'content':'partial'}}]}]
        with self.assertRaisesRegex(ocr.AdvancedOCRError,'Incomplete'):
            ocr._stream_recognize({'stream':True},endpoint=self.endpoint)
    def test_backend_error_not_treated_as_empty_chunk(self):
        self.server.frames = [{'error':{'message':'synthetic secret error'}},'[DONE]']
        with self.assertRaisesRegex(ocr.AdvancedOCRError,'Runtime reported'):
            ocr._stream_recognize({'stream':True},endpoint=self.endpoint)

if __name__ == '__main__': unittest.main()
