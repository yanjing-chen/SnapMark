"""Safe, offline tests for technical translation; no GGUF loading."""
from __future__ import annotations
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TRANS = ROOT / 'official_plugins/translation'

def load(name):
    spec = importlib.util.spec_from_file_location(name, TRANS / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

GUARD = load('format_guard_c2d')
CLIENT = load('runtime_client')
MODEL = {'data': [{'id': 'hy-mt2-7b-q8', 'installed': True, 'type': 'translation',
                   'capabilities': {'translation': True}}]}

class C2DFormatGuardTests(unittest.TestCase):
    def test_plain_text_not_changed(self):
        self.assertEqual(GUARD.protect('你好，杭州西湖很美。'), ('你好，杭州西湖很美。', {}))

    def test_terminal_command_preserved(self):
        source = '请在终端执行：\ncd ~/下载/SnapMark-C2C-advanced-ocr\nbash scripts/run-local.sh\n结束。'
        safe, slots = GUARD.protect(source)
        self.assertNotIn('~/下载', safe)
        self.assertNotIn('bash scripts', safe)
        self.assertEqual(GUARD.restore(safe, slots), source)

    def test_inline_path_unmodified(self):
        source = '路径 ~/下载/SnapMark-C2C-advanced-ocr 不要翻译。'
        safe, slots = GUARD.protect(source)
        self.assertEqual(GUARD.restore(safe, slots), source)
        self.assertNotIn('~/下载', safe)

    def test_fenced_code_block(self):
        source = '执行以下命令：\n```bash\ncd ~/下载\npython3 -V\n```\n然后继续。'
        safe, slots = GUARD.protect(source)
        self.assertNotIn('python3 -V', safe)
        self.assertEqual(len(slots), 1)
        self.assertEqual(GUARD.restore(safe, slots), source)

    def test_inline_code(self):
        text = 'Use `sudo apt install hello` as an example.'
        safe, slots = GUARD.protect(text)
        self.assertEqual(GUARD.restore(safe, slots), text)

    def test_url_and_names(self):
        text = 'Check https://example.org/file.json and hy-mt2-7b-q8, not Pinyin.'
        safe, slots = GUARD.protect(text)
        self.assertEqual(GUARD.restore(safe, slots), text)
        self.assertGreaterEqual(len(slots), 2)

    def test_placeholders_not_duplicated(self):
        safe, slots = GUARD.protect('cd ~/下载\n请看路径 ~/下载/foo.json')
        self.assertEqual(len(GUARD.MARKER_PATTERN.findall(safe)), len(slots))

    def test_missing_marker_fails_closed(self):
        _, slots = GUARD.protect('路径 ~/下载/abc')
        with self.assertRaisesRegex(ValueError, 'altered or omitted'):
            GUARD.restore('I translated the path', slots)

    def test_duplicate_marker_fails_closed(self):
        safe, slots = GUARD.protect('path ~/下载/abc')
        with self.assertRaises(ValueError):
            GUARD.restore(safe + '\n' + next(iter(slots)), slots)

    def test_undisclosed_marker_fails(self):
        with self.assertRaises(ValueError):
            GUARD.restore('[[SMTECH_00009]]', {})

    def test_reserved_marker_input_is_rejected(self):
        with self.assertRaises(ValueError):
            GUARD.protect('[[SMTECH_00000]]')

    def test_real_client_restores_path(self):
        requests = []
        original = '打开 ~/下载/SnapMark-C2C-advanced-ocr，然后继续。'
        def fake(endpoint, path, **kwargs):
            if path == '/v1/models':
                return MODEL
            payload = kwargs['payload']
            requests.append(payload)
            safe = payload['messages'][1]['content']
            return {'choices':[{'message':{'content': 'Open ' + safe.split('打开 ',1)[-1].replace('，然后继续。',' and continue.')}}]}
        with patch.object(CLIENT, '_request', side_effect=fake):
            result, model = CLIENT.translate(original, 'English', model_id='hy-mt2-7b-q8')
        self.assertIn('~/下载/SnapMark-C2C-advanced-ocr', result)
        self.assertNotIn('~/下载/SnapMark-C2C-advanced-ocr', requests[0]['messages'][1]['content'])
        self.assertEqual(model, 'hy-mt2-7b-q8')

    def test_real_client_rejects_lost_path(self):
        def fake(endpoint, path, **kwargs):
            if path == '/v1/models': return MODEL
            return {'choices':[{'message':{'content': 'Use ~/Downloads/incorrect.'}}]}
        with patch.object(CLIENT, '_request', side_effect=fake):
            with self.assertRaisesRegex(CLIENT.TranslationError, 'protected technical'):
                CLIENT.translate('Use ~/下载/correct', 'Dutch', model_id='hy-mt2-7b-q8')

    def test_plain_client_regression(self):
        payload = []
        def fake(endpoint, path, **kwargs):
            if path == '/v1/models': return MODEL
            payload.append(kwargs['payload'])
            return {'choices':[{'message':{'content': 'Goedemorgen'}}]}
        with patch.object(CLIENT, '_request', side_effect=fake):
            self.assertEqual(CLIENT.translate('早上好', 'Dutch', model_id='hy-mt2-7b-q8')[0], 'Goedemorgen')
        self.assertEqual(payload[0]['messages'][1]['content'], '早上好')

if __name__ == '__main__': unittest.main()
