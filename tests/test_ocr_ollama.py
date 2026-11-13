"""Pure unit tests for model selection, retention and Ollama transport."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from snapmark.ocr_ollama import (DEFAULT_MODEL, OllamaError, OllamaOCR,
                                  validate_base_url, validate_keep_alive,
                                  load_ocr_settings, save_ocr_settings)

PNG = b'\x89PNG\r\n\x1a\n' + b'fake-png-bytes'

class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

class OCRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_only_loopback(self):
        for url in ('https://127.0.0.1:11434', 'http://example.org:11434',
                    'http://127.0.0.1:11434/secret', 'http://127.0.0.1'):
            with self.assertRaises(OllamaError): validate_base_url(url)
        self.assertEqual(validate_base_url('http://127.0.0.1:11434'), 'http://127.0.0.1:11434')

    def test_retention_values_and_persistence(self):
        for number in (0, 1, 300, 86400):
            self.assertEqual(validate_keep_alive(number), number)
            save_ocr_settings(keep_alive_seconds=number)
            self.assertEqual(load_ocr_settings()['keep_alive_seconds'], number)
        for number in (-1, 86401, 1.2, '5m', True):
            with self.assertRaises(OllamaError): validate_keep_alive(number)
        self.assertEqual(load_ocr_settings()['model'], '')

    def test_selected_model_is_user_configurable(self):
        save_ocr_settings(model='snapmark-ocr-local:latest', prompt='Spotting:')
        model = OllamaOCR()
        self.assertEqual(model.model, 'snapmark-ocr-local:latest')
        self.assertEqual(model.prompt, 'Spotting:')
        with self.assertRaises(OllamaError): save_ocr_settings(model='../../evil')

    def test_stream_sends_selected_model_and_seconds(self):
        save_ocr_settings(model='paddleocr-vl:future', keep_alive_seconds=0,
                          prompt='Spotting:')
        instance = OllamaOCR()
        instance._opener.open = Mock(return_value=FakeResponse(
            b'{"response":"hello","done":false}\n{"response":"","done":true}\n'))
        self.assertEqual(''.join(instance.recognize(PNG)), 'hello')
        request = instance._opener.open.call_args.args[0]
        data = json.loads(request.data)
        self.assertEqual(data['model'], 'paddleocr-vl:future')
        self.assertEqual(data['keep_alive'], 0)
        self.assertEqual(data['prompt'], 'Spotting:')
        self.assertTrue(data['images'])

    def test_truncated_stream_rejected(self):
        instance = OllamaOCR()
        instance._opener.open = Mock(return_value=FakeResponse(b'{"response":"hi"}\n'))
        with self.assertRaises(OllamaError): list(instance.recognize(PNG))

    def test_import_two_file_buttons_backend(self):
        with tempfile.TemporaryDirectory() as temp:
            main = Path(temp) / 'main.gguf'; main.write_bytes(b'GGUFtest-main')
            projector = Path(temp) / 'mmproj.gguf'; projector.write_bytes(b'GGUFtest-projector')
            client = OllamaOCR()
            with patch.object(client, 'models', return_value=[]), \
                 patch.object(client, '_upload_gguf', side_effect=['sha256:main', 'sha256:proj']) as upload, \
                 patch.object(client, '_create_from_files', return_value='snapmark-ocr-local:latest') as create:
                value = client.import_model_files(main, projector, 'snapmark-ocr-local:latest')
            self.assertEqual(value, 'snapmark-ocr-local:latest')
            self.assertEqual(upload.call_count, 2)
            self.assertEqual(create.call_args.args[1], {'main.gguf': 'sha256:main', 'mmproj.gguf': 'sha256:proj'})

    def test_import_never_overwrites_an_existing_ollama_model(self):
        with tempfile.TemporaryDirectory() as temp:
            main = Path(temp) / 'main.gguf'; main.write_bytes(b'GGUFtest-main')
            client = OllamaOCR()
            with patch.object(client, 'models', return_value=['popup-model:latest']):
                with self.assertRaises(OllamaError):
                    client.import_model_files(main, None, 'popup-model:latest')

    def test_nonvisual_import_not_selected(self):
        client = OllamaOCR()
        with patch.object(client, 'model_capabilities', return_value=['completion']):
            with self.assertRaisesRegex(OllamaError, 'did not report vision'):
                client._verify_vision('snapmark-local:latest')

    def test_model_listing(self):
        client = OllamaOCR()
        with patch.object(client, 'models', return_value=['paddleocr-vl:latest', 'popup-7b:latest', 'custom-ocr:latest']), \
             patch.object(client, 'model_capabilities', side_effect=lambda model: ['vision'] if 'ocr' in model else ['completion']):
            self.assertEqual(client.vision_models(), ['custom-ocr:latest','paddleocr-vl:latest'])


class OCR3ModelManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_auto_detects_main_and_mmproj_in_one_folder(self):
        from snapmark.ocr_ollama import detect_model_folder
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'PaddleOCR-VL-1.6-GGUF.gguf').write_bytes(b'GGUFmain')
            (root/'PaddleOCR-VL-1.6-GGUF-mmproj.gguf').write_bytes(b'GGUFproj')
            result = detect_model_folder(root)
            self.assertEqual(result['mode'], 'gguf')
            self.assertIn('mmproj', result['projector'].name)
            self.assertNotIn('mmproj', result['main'].name)

    def test_refuses_ambiguous_or_missing_folder_contents(self):
        from snapmark.ocr_ollama import detect_model_folder
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaisesRegex(OllamaError, 'No GGUF'):
                detect_model_folder(root)
            (root/'model1.gguf').write_bytes(b'GGUFmain1')
            (root/'model2.gguf').write_bytes(b'GGUFmain2')
            with self.assertRaisesRegex(OllamaError, 'Ambiguous'):
                detect_model_folder(root)

    def test_single_gguf_and_modelfile(self):
        from snapmark.ocr_ollama import detect_model_folder
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'model.gguf').write_bytes(b'GGUFmain')
            self.assertEqual(detect_model_folder(root)['mode'], 'gguf')
            (root/'model.gguf').unlink()
            (root/'Modelfile').write_text('FROM ./model.gguf\n')
            self.assertEqual(detect_model_folder(root)['mode'], 'modelfile')

    def test_folder_import_routes_both_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'main.gguf').write_bytes(b'GGUFmain')
            (root/'mmproj.gguf').write_bytes(b'GGUFproj')
            cli=OllamaOCR()
            with patch.object(cli, 'import_model_files', return_value='local-ocr:latest') as importer:
                result=cli.import_model_folder(root, 'local-ocr:latest')
                self.assertEqual(result, 'local-ocr:latest')
                args=importer.call_args.args
                self.assertEqual(args[0].name, 'main.gguf')
                self.assertEqual(args[1].name, 'mmproj.gguf')

    def test_hidden_list_is_snapmark_only_and_can_be_restored(self):
        from snapmark.ocr_ollama import validate_hidden_models
        save_ocr_settings(hidden_models=['local:latest','local:latest'])
        self.assertEqual(load_ocr_settings()['hidden_models'], ['local:latest'])
        save_ocr_settings(hidden_models=[])
        self.assertEqual(load_ocr_settings()['hidden_models'], [])
        for invalid in ([123], ['../../bad'], 'bad'):
            with self.assertRaises(OllamaError):
                validate_hidden_models(invalid)

    def test_active_model_can_be_cleared_after_removal(self):
        save_ocr_settings(model='local:latest')
        save_ocr_settings(model='', hidden_models=['local:latest'])
        self.assertEqual(load_ocr_settings()['model'], '')
        client = OllamaOCR()
        self.assertEqual(client.model, '')
        with self.assertRaisesRegex(OllamaError, 'No OCR model'):
            list(client.recognize(PNG))

    def test_duplicate_latest_alias_is_rejected_before_upload(self):
        cli=OllamaOCR()
        with patch.object(cli, 'models', return_value=['same-model:latest']):
            with self.assertRaisesRegex(OllamaError, 'already exists'):
                cli._ensure_new_model_name('same-model')

    def test_http_delete_uses_delete_verb(self):
        cli=OllamaOCR()
        cli._opener.open = Mock(return_value=FakeResponse(b''))
        with cli._request('/api/delete', {'model':'local-ocr:latest'}):
            pass
        req=cli._opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), 'DELETE')

    def test_delete_uses_ollama_endpoint_not_original_files(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder)/'original.gguf'
            original.write_bytes(b'GGUF untouchable')
            client=OllamaOCR()
            with patch.object(client, 'models', return_value=['local-ocr:latest']), \
                 patch.object(client, '_request', return_value=FakeResponse(b'')) as call:
                client.delete_model('local-ocr:latest')
                self.assertEqual(call.call_args.args[:2],
                                 ('/api/delete', {'model': 'local-ocr:latest'}))
                self.assertTrue(original.is_file())

if __name__ == '__main__': unittest.main()
