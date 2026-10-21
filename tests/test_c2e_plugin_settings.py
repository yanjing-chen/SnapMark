"""C2-E isolated, offline config/stream/navigation safety contracts."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TRANS = ROOT / 'official_plugins/translation'

def load(module):
    spec = importlib.util.spec_from_file_location('c2e_test_' + module, TRANS / (module + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
S = load('settings_c2e')
C = load('runtime_client')
MODEL = {'data':[{'id':'test-model','installed':True,'type':'translation','capabilities':{'translation':True}}]}

class ProfilesTests(unittest.TestCase):
    def test_defaults_preserve_c2d(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'XDG_CONFIG_HOME':temp}):
            p = S.read_profile('test-model')
            self.assertEqual(p['temperature'], 0.0)
            self.assertFalse(p['streaming'])
            self.assertIsNone(p['max_tokens'])
    def test_per_model_and_legacy_values(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'XDG_CONFIG_HOME':temp}):
            path = S.settings_file()
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'model':'test-model','target_language':'Dutch'}))
            first = dict(S.DEFAULT, preset='Custom', prompt='Protect Chinese literals', temperature=0.3, streaming=True)
            S.save_profile('test-model', first)
            self.assertEqual(S.read_profile('test-model')['temperature'],0.3)
            self.assertEqual(S.read_profile('another')['temperature'],0.0)
            self.assertEqual(json.loads(path.read_text())['target_language'],'Dutch')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
    def test_reject_invalid_inference_params(self):
        for change in ({'temperature': 2}, {'streaming':'yes'}, {'thinking':'on'},
                       {'max_tokens': 123}, {'prompt':''}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                S.validate(dict(S.DEFAULT, **change))
    def test_defaults_profiles_are_distinct(self):
        self.assertEqual(len(S.PRESETS),4)
        self.assertNotEqual(S.PRESETS['Technical'],S.PRESETS['Literary'])
    def test_no_remote_models_installed(self):
        import inspect
        self.assertNotIn('pip install',inspect.getsource(S))

class RuntimeTests(unittest.TestCase):
    def test_prompt_and_temperature_settings(self):
        recorded=[]
        def fake(endpoint,path,**kw):
            if path == '/v1/models': return MODEL
            recorded.append(kw['payload'])
            return {'choices':[{'message':{'content':'Klaar'}}]}
        with patch.object(C,'_request', side_effect=fake):
            self.assertEqual(C.translate('完成','Dutch',model_id='test-model',
                settings=dict(S.DEFAULT, preset='Technical', prompt=S.PRESETS['Technical'],
                              temperature=0.4,max_tokens=1024))[0],'Klaar')
        payload=recorded[0]
        self.assertEqual(payload['temperature'],0.4)
        self.assertEqual(payload['max_tokens'],1024)
        self.assertIn('Technical',payload['messages'][0]['content'].replace('technical','Technical'))
    def test_streaming_uses_guard_and_restores(self):
        previews=[]
        requests=[]
        def fake(endpoint,path,**kw):
            if path == '/v1/models': return MODEL
            raise AssertionError('unexpected JSON completion request')
        def stream(endpoint,path,**kw):
            requests.append(kw['payload'])
            value = kw['payload']['messages'][1]['content']
            kw['on_partial']('Open ' + value)
            return 'Open ' + value.replace('打开 ', '')
        with patch.object(C,'_request', side_effect=fake), patch.object(C,'_stream_request', side_effect=stream):
            result,_=C.translate('打开 ~/下载/model.gguf','Dutch',model_id='test-model',
                settings=dict(S.DEFAULT,streaming=True),on_partial=previews.append)
        self.assertIn('~/下载/model.gguf',result)
        self.assertTrue(requests[0]['stream'])
        self.assertNotIn('~/下载/model.gguf',requests[0]['messages'][1]['content'])
    def test_stream_missing_placeholder_fails_closed(self):
        with patch.object(C,'_request', return_value=MODEL),patch.object(C,'_stream_request',return_value='Bad ~/Downloads'):
            with self.assertRaises(C.TranslationError):
                C.translate('Open ~/下载/file', 'Dutch',model_id='test-model',
                    settings=dict(S.DEFAULT,streaming=True))
    def test_sse_parsing_and_done(self):
        class FakeResponse:
            headers={'Content-Type':'text/event-stream'}
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def __iter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Hallo "}}]}\n'
                yield b'data: {"choices":[{"delta":{"content":"wereld"}}]}\n'
                yield b'data: [DONE]\n'
        class Opener:
            def open(self,*a,**kw): return FakeResponse()
        previews=[]
        with patch.object(C.urllib.request,'build_opener',return_value=Opener()):
            result=C._stream_request(C.ENDPOINT,'/v1/chat/completions',
                payload={'stream':True},on_partial=previews.append)
        self.assertEqual(result,'Hallo wereld')
        self.assertEqual(previews[-1],result)

class NavigationTests(unittest.TestCase):
    def test_nested_navigation_declared(self):
        source=(ROOT/'snapmark/preferences_sidebar_c2e.py').read_text()
        self.assertIn('Gtk.Revealer()',source)
        # Dynamic submenus are derived from enabled plugin registrations,
        # not two fixed OCR / Translation entries in the host application.
        self.assertIn('def populate_plugins(self, registrations):',source)
        self.assertIn("self._add(self.plugin_box, page_name, title, icon)",source)
        self.assertNotIn("self._add(inner, 'plugin-ocr'",source)
        self.assertNotIn("self._add(inner, 'plugin-translation'",source)
    def test_runtime_after_shortcuts_and_before_plugins(self):
        source=(ROOT/'snapmark/preferences_sidebar_c2e.py').read_text()
        self.assertLess(source.index("('shortcuts',"), source.index("self._add(root, 'ai-runtime'"))
        self.assertLess(source.index("self._add(root, 'ai-runtime'"), source.index("self._add(plugin_line, 'plugins'"))
    def test_editor_preserves_existing_runtime_ui(self):
        source=(ROOT/'snapmark/editor.py').read_text()
        self.assertIn('self._runtime_preferences = AIRuntimePreferences(window, stack)',source)
    def test_translation_dependency_unchanged(self):
        meta=json.loads((TRANS/'plugin.json').read_text())
        self.assertEqual(meta['version'],'0.1.5')
        self.assertEqual(meta['dependencies'],{'ocr':'0.1.2'})

if __name__=='__main__': unittest.main()
