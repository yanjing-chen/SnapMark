"""Offline regression for plugin package and dependency security."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from snapmark.plugins import (PluginManager, PluginError, _safe_entries, _manifest,
                              available_releases, install_release, version_key)


def package(ident, version='0.1.0', **changes):
    manifest = {'id': ident, 'version': version, 'api_version': 1,
                'min_host_version': '0.6.0', 'dependencies': {'ocr': '0.1.0'} if ident == 'translation' else {}}
    manifest.update(changes)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('plugin.json', json.dumps(manifest))
        archive.writestr('plugin.py', '# standalone example\n')
    value = stream.getvalue()
    return value, hashlib.sha256(value).hexdigest()


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.manager = PluginManager(root / 'plugins', root / 'settings')

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, ident, version='0.1.0', **changes):
        payload, digest = package(ident, version, **changes)
        self.manager.install_zip(payload, ident, version, digest)

    def test_install_versions_activate_and_retire_without_other_state(self):
        self.install('ocr')
        self.install('ocr', '0.2.0')
        self.assertEqual(self.manager.versions('ocr'), ['0.2.0', '0.1.0'])
        self.assertFalse(self.manager.is_available('ocr'))
        self.manager.select('ocr', '0.1.0')
        self.assertTrue(self.manager.is_available('ocr'))
        self.manager.select('ocr', '0.2.0')
        self.assertEqual(self.manager.selected('ocr'), '0.2.0')
        self.manager.uninstall('ocr', '0.2.0')
        self.assertIsNone(self.manager.selected('ocr'))
        self.assertEqual(self.manager.versions('ocr'), ['0.1.0'])

    def test_translation_depends_on_enabled_ocr(self):
        self.install('translation')
        with self.assertRaises(PluginError):
            self.manager.select('translation', '0.1.0')
        self.install('ocr')
        self.manager.select('ocr', '0.1.0')
        self.manager.select('translation', '0.1.0')
        self.assertTrue(self.manager.is_available('translation'))
        self.manager.set_enabled('ocr', False)
        self.assertFalse(self.manager.is_available('translation'))
        self.assertEqual(self.manager.selected('translation'), '0.1.0')
        with self.assertRaises(PluginError):
            self.manager.uninstall('ocr', '0.1.0')
        self.manager.uninstall('translation', '0.1.0')
        self.manager.uninstall('ocr', '0.1.0')

    def test_incompatible_ocr_downgrade_blocked_while_translation_active(self):
        self.install('ocr', '0.1.0')
        self.install('ocr', '0.2.0')
        self.manager.select('ocr', '0.2.0')
        self.install('translation', dependencies={'ocr': '0.2.0'})
        self.manager.select('translation', '0.1.0')
        with self.assertRaisesRegex(PluginError, 'requires OCR'):
            self.manager.select('ocr', '0.1.0')
        self.assertEqual(self.manager.selected('ocr'), '0.2.0')
        self.manager.set_enabled('translation', False)
        self.manager.select('ocr', '0.1.0')
        self.assertEqual(self.manager.selected('ocr'), '0.1.0')

    def test_bad_identity_and_checksums_rejected(self):
        p, digest = package('ocr')
        with self.assertRaisesRegex(PluginError, 'SHA256'):
            self.manager.install_zip(p, 'ocr', '0.1.0', '0' * 64)
        with self.assertRaisesRegex(PluginError, 'identity'):
            self.manager.install_zip(p, 'translation', '0.1.0', digest)
        self.assertEqual(self.manager.versions('ocr'), [])

    def test_unsafe_zip_path_rejected(self):
        payload, _ = package('ocr')
        for evil in ('../traversal.txt', '/absolute.txt', 'bad\\slash.py'):
            z = io.BytesIO()
            with zipfile.ZipFile(z, 'w') as archive:
                archive.writestr('plugin.json', '{"id":"ocr","version":"0.1.0","api_version":1}')
                archive.writestr(evil, 'bad')
            data = z.getvalue()
            with self.assertRaises(PluginError):
                self.manager.install_zip(data, 'ocr', '0.1.0', hashlib.sha256(data).hexdigest())

    def test_old_host_and_invalid_dependencies_rejected(self):
        p, d = package('ocr', min_host_version='9.0.0')
        with self.assertRaisesRegex(PluginError, 'needs SnapMark'):
            self.manager.install_zip(p, 'ocr', '0.1.0', d)
        p, d = package('translation', dependencies={})
        with self.assertRaisesRegex(PluginError, 'must declare'):
            self.manager.install_zip(p, 'translation', '0.1.0', d)
        self.assertRaises(PluginError, version_key, 'v0.1')

    def test_only_official_tag_and_complete_assets(self):
        records = [
            {'tag_name': 'ocr-v0.2.0', 'assets': [
                {'name': 'SnapMark-ocr-0.2.0.zip', 'browser_download_url':
                 'https://github.com/yanjing-chen/SnapMark/releases/download/ocr-v0.2.0/SnapMark-ocr-0.2.0.zip'},
                {'name': 'SnapMark-ocr-0.2.0.zip.sha256', 'browser_download_url':
                 'https://github.com/yanjing-chen/SnapMark/releases/download/ocr-v0.2.0/SnapMark-ocr-0.2.0.zip.sha256'}]},
            {'tag_name': 'translation-v0.5.0', 'assets': []},
            {'tag_name': 'ocr-v0.3.0', 'draft': True, 'assets': []},
        ]
        with patch('snapmark.plugins._http_bytes', return_value=json.dumps(records).encode()):
            got = available_releases('ocr')
        self.assertEqual([x['version'] for x in got], ['0.2.0'])
        with self.assertRaises(PluginError):
            install_release(self.manager, {**got[0], 'url': 'https://evil.invalid/plugin.zip'})

    def test_install_never_runs_plugin_code(self):
        p, d = package('ocr')
        with patch('builtins.__import__', wraps=__import__) as mocked:
            self.manager.install_zip(p, 'ocr', '0.1.0', d)
        self.assertFalse(any(call.args and call.args[0] == 'plugin' for call in mocked.call_args_list))


if __name__ == '__main__':
    unittest.main()
