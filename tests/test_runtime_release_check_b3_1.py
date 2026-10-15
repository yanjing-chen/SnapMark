"""B3-1 pure/isolated read-only tests: no access to real 8111 or GitHub."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from snapmark.runtime_release_check import (
    RELEASE_TAG, RELEASE_URL, RELEASE_API, ReleaseCheckError,
    compare_versions, fetch_official_release, inspect_local_installation,
    inspect_release_payload,
)


class DummyReply:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, count):
        return self.payload[:count]


class RuntimeB31Tests(unittest.TestCase):
    def test_local_installation_not_inferred_from_api(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            empty = inspect_local_installation(home)
            self.assertFalse(empty.installed)
            self.assertFalse(empty.complete)
            for path in ('.local/bin/local-ai-runtime',
                         '.local/lib/local-ai-runtime/local_ai_runtime.py'):
                p = home / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('dummy')
            partial = inspect_local_installation(home)
            self.assertTrue(partial.installed)
            self.assertFalse(partial.complete)
            p = home / '.config/systemd/user/local-ai-runtime.service'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('dummy')
            self.assertTrue(inspect_local_installation(home).complete)

    def test_version_compare_pinned(self):
        for v, expected in [('0.8.0', 'older'), ('1.0.0', 'equal'),
                            ('1.1.0', 'newer'), ('1.0.0-rc1', 'unknown'),
                            ('', 'unknown'), ('1.0.0.dev', 'unknown')]:
            self.assertEqual(compare_versions(v), expected)

    def test_release_schema(self):
        release = inspect_release_payload({
            'tag_name': RELEASE_TAG, 'html_url': RELEASE_URL,
            'assets': [{'name': 'application.tar.gz'}, {'name': 'application.tar.gz.sha256'},
                       {'name': 'release-notes.md'}]})
        self.assertEqual(release.version, '1.0.0')
        self.assertEqual(release.archive_assets, ('application.tar.gz',))
        self.assertEqual(release.checksum_assets, ('application.tar.gz.sha256',))

    def test_reject_wrong_repository_url_or_tag(self):
        for payload in ({'tag_name': RELEASE_TAG, 'html_url': 'https://example.com', 'assets': []},
                        {'tag_name': 'local-ai-runtime-v0.8.0', 'html_url': RELEASE_URL, 'assets': []},
                        {'tag_name': RELEASE_TAG, 'html_url': RELEASE_URL, 'assets': None}):
            with self.assertRaises(ReleaseCheckError):
                inspect_release_payload(payload)

    def test_fetch_pinned_metadata_get_only_no_download(self):
        response = json.dumps({'tag_name': RELEASE_TAG, 'html_url': RELEASE_URL,
                               'assets': [{'name': 'application.tar.gz'}]}).encode()
        observed = []

        def fake_open(request, timeout):
            self.assertEqual(request.full_url, RELEASE_API)
            self.assertEqual(request.get_method(), 'GET')
            observed.append((request.full_url, timeout))
            return DummyReply(response)

        with patch('snapmark.runtime_release_check.urlopen', side_effect=fake_open):
            result = fetch_official_release()
        self.assertEqual(result.version, '1.0.0')
        self.assertEqual(len(observed), 1)

    def test_reject_bad_json(self):
        with patch('snapmark.runtime_release_check.urlopen', return_value=DummyReply(b'{bad')):
            with self.assertRaises(ReleaseCheckError):
                fetch_official_release()

    def test_does_not_offer_installer_actions(self):
        source = (Path(__file__).resolve().parents[1] / 'snapmark/runtime_release_check.py').read_text()
        self.assertNotIn('subprocess', source)
        self.assertNotIn('subprocess.run(', source)
        self.assertNotIn('method=\'POST\'', source)
        self.assertNotIn('urlretrieve', source)

    def test_ui_button_not_automatic_on_startup(self):
        ui = (Path(__file__).resolve().parents[1] / 'snapmark/ai_runtime_ui.py').read_text()
        self.assertIn('def _check_release_clicked(', ui)
        self.assertIn('fetch_official_release()', ui)
        self.assertNotIn('fetch_official_release()\n        self._set_available', ui)


if __name__ == '__main__':
    unittest.main()
