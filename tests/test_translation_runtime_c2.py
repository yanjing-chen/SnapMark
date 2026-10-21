"""Offline Runtime translation client and plugin security checks."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile
from snapmark.plugins import PluginManager, PluginError

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'official_plugins/translation'
spec = importlib.util.spec_from_file_location('test_snapmark_translation_client', PLUGIN / 'runtime_client.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TranslationClientTests(unittest.TestCase):
    def test_requires_local_http(self):
        for endpoint in ('https://external.example:8111', 'http://evil.com:8111',
                         'http://127.0.0.1:8111/path', 'file:///tmp/x'):
            with self.assertRaises(module.TranslationError):
                module._endpoint(endpoint)
        self.assertEqual(module._endpoint('http://127.0.0.1:8111'), 'http://127.0.0.1:8111')

    def test_translation_installed_capability_only(self):
        records = {'data': [
            {'id':'ocr-only','installed':True,'capabilities':{'ocr':True}},
            {'id':'not-installed','installed':False,'capabilities':{'translation':True}},
            {'id':'custom-translation','installed':True,'capabilities':{'translation':True}},
            {'id':'HY-MT2-7B','installed':True,'capabilities':{'translation':True}},
        ]}
        self.assertEqual(module.choose_model(records), 'HY-MT2-7B')

    def test_no_translation_model_gives_error(self):
        with self.assertRaisesRegex(module.TranslationError, 'No installed translation'):
            module.choose_model({'data': [{'id':'missing','installed':False,
                                           'capabilities':{'translation':True}}]})

    def test_translate_source_detected_and_local_chat(self):
        requests=[]
        def fake(endpoint,path,**kwargs):
            requests.append((endpoint,path,kwargs))
            if path == '/v1/models':
                return {'data':[{'id':'HY-MT2-7B', 'installed':True,
                                 'capabilities':{'translation':True}}]}
            return {'choices':[{'message':{'content':'Goedemorgen'}}]}
        with patch.object(module, '_request', side_effect=fake):
            result, model = module.translate('早上好', 'Dutch')
        self.assertEqual((result,model), ('Goedemorgen','HY-MT2-7B'))
        self.assertEqual(requests[1][1], '/v1/chat/completions')
        payload=requests[1][2]['payload']
        self.assertEqual(payload['messages'][1]['content'], '早上好')
        self.assertIn('Automatically identify the source language', payload['messages'][0]['content'])
        self.assertEqual(payload['temperature'],0.0)
        self.assertFalse(payload['stream'])

    def test_translate_does_not_call_model_if_no_text(self):
        with patch.object(module,'_request') as req:
            with self.assertRaises(module.TranslationError):
                module.translate(' ', 'Dutch')
            req.assert_not_called()

    def test_response_missing_content_errors(self):
        with patch.object(module,'_request',side_effect=[
            {'data':[{'id':'t','installed':True,'capabilities':{'translation':True}}]},
            {'choices':[]}
        ]):
            with self.assertRaisesRegex(module.TranslationError, 'no translation'):
                module.translate('source','Dutch')

    def test_translation_package_dependency_and_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp)
            manager=PluginManager(temp/'plugins',temp/'config')
            ocr_root=ROOT/'official_plugins/ocr'
            def install(name,version,root):
                target=temp/(name+'.zip')
                with ZipFile(target,'w',compression=ZIP_DEFLATED) as z:
                    for f in root.iterdir():
                        if f.is_file(): z.write(f,f.name)
                data=target.read_bytes()
                return manager.install_zip(data,name,version,hashlib.sha256(data).hexdigest())
            install('ocr','0.2.4',ocr_root)
            manifest=install('translation','0.1.5',PLUGIN)
            self.assertEqual(manifest['dependencies'],{'ocr':'0.1.2'})
            with self.assertRaises(PluginError): manager.select('translation','0.1.5',True)
            manager.select('ocr','0.2.4',True)
            manager.select('translation','0.1.5',True)
            self.assertTrue(manager.is_available('translation'))
            manager.set_enabled('translation',False)
            self.assertFalse(manager.is_available('translation'))

    def test_invalid_api_result_refused(self):
        with patch.object(module, '_request',side_effect=[
            {'data':[{'id':'t','installed':True,'capabilities':{'translation':True}}]},
            {'choices':[{'message':{'content':None}}]}
        ]):
            with self.assertRaisesRegex(module.TranslationError, 'empty translation'):
                module.translate('input','Dutch')
