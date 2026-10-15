"""B3-2 regression: the official Runtime bundle has install and uninstall scripts.

Offline; all tar archives are synthetic, all extraction goes to temporary dirs.
No Runtime API calls, no service control, no network and no model operations.
"""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from snapmark import runtime_manager_b3 as manager


PREFIX = 'Local-AI-Runtime-1.0.0-linux-x86_64'


def create_bundle(extra=None, *, include_installer=True):
    items = {
        'config.example.json': b'{}\n',
        'uninstall-user.sh': b'#!/bin/bash\nexit 0\n',
        'README.md': b'Official-layout test\n',
    }
    for name in manager.FILES:
        if name != 'hunyuanocr_installer.py':
            items[f'src/{name}'] = b'# synthetic module\n'
    if include_installer:
        items['install-user.sh'] = b'#!/bin/bash\nexit 0\n'
    items.update(extra or {})
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w:gz') as archive:
        for relative, content in items.items():
            member = tarfile.TarInfo(f'{PREFIX}/{relative}')
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return out.getvalue()


class OfficialArchiveLayoutTests(unittest.TestCase):
    def test_exact_installer_match_with_official_uninstaller(self):
        with tempfile.TemporaryDirectory(prefix='snapmark-b3-archive-') as tmp:
            destination = Path(tmp)
            result = manager._extract_validated_archive(create_bundle(), destination)
            self.assertEqual(result, destination)
            self.assertTrue((destination/'install-user.sh').is_file())
            self.assertTrue((destination/'uninstall-user.sh').is_file())
            self.assertTrue((destination/'src/local_ai_runtime.py').is_file())

    def test_reject_multiple_actual_installers(self):
        payload = create_bundle({'nested/install-user.sh': b'#!/bin/bash\n'})
        with tempfile.TemporaryDirectory(prefix='snapmark-b3-archive-') as tmp:
            with self.assertRaisesRegex(manager.ManagementError, 'Expected one official install-user.sh'):
                manager._extract_validated_archive(payload, Path(tmp))

    def test_uninstaller_is_not_accepted_as_installer(self):
        with tempfile.TemporaryDirectory(prefix='snapmark-b3-archive-') as tmp:
            with self.assertRaisesRegex(manager.ManagementError, 'Expected one official install-user.sh'):
                manager._extract_validated_archive(create_bundle(include_installer=False), Path(tmp))


if __name__ == '__main__':
    unittest.main()
