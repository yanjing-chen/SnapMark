"""Real filesystem + isolated HOME tests. Never access the user's Runtime service."""
import hashlib
import io
import json
from pathlib import Path
import os
import tarfile
import tempfile
import unittest
from unittest import mock

from snapmark import runtime_manager_b3 as m


def tar_fixture(extra=None):
    files = {f'src/{x}': b'# fake pinned source\n' for x in m.FILES
             if x != 'hunyuanocr_installer.py'}
    files.update({'config.example.json': b'{}\n', 'install-user.sh': b'''#!/bin/bash
set -eu
mkdir -p "$HOME/.local/lib/local-ai-runtime" "$HOME/.local/bin" "$HOME/.config/local-ai-runtime"
cp "$PWD/src/local_ai_runtime.py" "$HOME/.local/lib/local-ai-runtime/local_ai_runtime.py"
echo '#!/bin/bash' > "$HOME/.local/bin/local-ai-runtime"
if [ ! -f "$HOME/.config/local-ai-runtime/config.json" ]; then
  cp "$PWD/config.example.json" "$HOME/.config/local-ai-runtime/config.json"
fi
''', 'README.md': b'fixture'})
    if extra:
        files.update(extra)
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w:gz') as t:
        for name, content in files.items():
            info = tarfile.TarInfo(f'Local-AI-Runtime-1.0.0/{name}')
            info.size = len(content)
            t.addfile(info, io.BytesIO(content))
    return out.getvalue()


class Response:
    def __init__(self, raw):
        self.raw, self.status = raw, 200
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=-1): return self.raw[:n] if n >= 0 else self.raw


class RuntimeManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='snapmark-b3-isolated-')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.calls = []
        self.manager = m.RuntimeManager(self.home, service_runner=self.calls.append)
        self.payload = tar_fixture()
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.checksums = f'{self.digest}  {m.PACKAGE}\n'.encode()
        self.sums_digest = hashlib.sha256(self.checksums).hexdigest()
        patch1 = mock.patch.object(m, 'PACKAGE_SHA256', self.digest)
        patch2 = mock.patch.object(m, 'CHECKSUMS_SHA256', self.sums_digest)
        patch1.start(); patch2.start()
        self.addCleanup(patch1.stop); self.addCleanup(patch2.stop)

    def fake_opener(self, req, timeout=0):
        if req.full_url.endswith('SHA256SUMS'):
            return Response(self.checksums)
        if req.full_url.endswith(m.PACKAGE):
            return Response(self.payload)
        raise AssertionError(req.full_url)

    def prepare(self):
        self.manager.download_and_verify(opener=self.fake_opener)

    def test_download_verified_and_pinned(self):
        self.assertIn('Verified', self.manager.download_and_verify(opener=self.fake_opener))
        self.assertTrue(self.manager.archive_ready())
        self.assertFalse(self.manager.service.exists())

    def test_invalid_checksum_blocks_cache(self):
        self.checksums = b'0'*64 + b'  '+m.PACKAGE.encode()+b'\n'
        with self.assertRaises(m.ManagementError):
            self.manager.download_and_verify(opener=self.fake_opener)
        self.assertFalse(self.manager.archive_ready())

    def test_package_tamper_blocks_install(self):
        self.prepare()
        (self.manager.cache / m.PACKAGE).write_bytes(b'tampered')
        with self.assertRaises(m.ManagementError):
            self.manager.install_verified(confirmed=True)

    def test_install_consent_required(self):
        self.prepare()
        with self.assertRaises(m.ManagementError): self.manager.install_verified()
        self.assertFalse(self.manager.service.exists())

    def test_install_uses_isolated_home_and_no_restart(self):
        self.prepare()
        result = self.manager.install_verified(confirmed=True)
        self.assertIn('NOT restarted', result)
        self.assertEqual((self.manager.lib/'local_ai_runtime.py').read_bytes(),
                         b'# fake pinned source\n')
        self.assertTrue(self.manager.service.is_file())
        self.assertEqual(self.calls, [('daemon-reload',)])
        self.assertEqual(len(self.manager.list_backups()), 1)

    def test_upgrade_preserves_config_and_registry(self):
        self.prepare()
        self.manager.config.mkdir(parents=True)
        (self.manager.config / 'config.json').write_bytes(b'{"custom": true}')
        (self.manager.config / 'custom-models.json').write_bytes(b'important')
        self.manager.data.mkdir(parents=True)
        (self.manager.data / 'keep.gguf').write_bytes(b'weights')
        self.manager.install_verified(confirmed=True)
        self.assertEqual((self.manager.config/'config.json').read_bytes(), b'{"custom": true}')
        self.assertEqual((self.manager.config/'custom-models.json').read_bytes(), b'important')
        self.assertEqual((self.manager.data/'keep.gguf').read_bytes(), b'weights')

    def test_rollback_restore_0_8(self):
        self.prepare()
        self.manager.lib.mkdir(parents=True)
        (self.manager.lib / 'local_ai_runtime.py').write_bytes(b'old 0.8')
        self.manager.install_verified(confirmed=True)
        self.assertEqual((self.manager.lib/'local_ai_runtime.py').read_bytes(), b'# fake pinned source\n')
        self.manager.rollback(self.manager.list_backups()[0], confirmed=True)
        self.assertEqual((self.manager.lib/'local_ai_runtime.py').read_bytes(), b'old 0.8')
        self.assertFalse(self.manager.service.exists())

    def test_rollback_bad_sha_does_not_overwrite(self):
        self.prepare()
        self.manager.lib.mkdir(parents=True)
        (self.manager.lib / 'local_ai_runtime.py').write_bytes(b'0.8 original')
        self.manager.install_verified(confirmed=True)
        folder = self.manager.backups / self.manager.list_backups()[0]
        data = json.loads((folder/'manifest.json').read_text())
        name = next(row['blob'] for row in data['records'] if row['blob'])
        (folder/name).write_text('tamper')
        with self.assertRaises(m.ManagementError):
            self.manager.rollback(folder.name, confirmed=True)
        self.assertTrue(self.manager.service.is_file())

    def test_uninstall_preserves_data(self):
        self.prepare()
        self.manager.install_verified(confirmed=True)
        self.manager.data.mkdir(exist_ok=True,parents=True)
        (self.manager.data/'model.gguf').write_bytes(b'weights')
        (self.manager.config/'custom-models.json').write_text('{}')
        with self.assertRaises(m.ManagementError): self.manager.uninstall()
        self.manager.uninstall(confirmed=True)
        self.assertFalse((self.manager.lib/'local_ai_runtime.py').exists())
        self.assertFalse(self.manager.service.exists())
        self.assertTrue((self.manager.config/'custom-models.json').exists())
        self.assertEqual((self.manager.data/'model.gguf').read_bytes(), b'weights')
        self.assertIn(('stop',), self.calls)
        self.assertIn(('disable',), self.calls)

    def test_uninstall_delete_settings_opt_in(self):
        self.prepare(); self.manager.install_verified(confirmed=True)
        (self.manager.config / 'preferences.json').write_text('{}')
        self.manager.uninstall(confirmed=True, remove_config=True)
        self.assertFalse((self.manager.config / 'preferences.json').exists())
        self.assertFalse((self.manager.config / 'config.json').exists())
        self.assertEqual(len(self.manager.list_backups()), 2)

    def test_rollback_restores_enabled_service_state(self):
        self.prepare()
        self.manager.service.parent.mkdir(parents=True, exist_ok=True)
        self.manager.service.write_text('old service')
        self.manager.service_runner = lambda args: 'enabled' if args == ('is-enabled',) else self.calls.append(args)
        self.manager.install_verified(confirmed=True)
        self.manager.rollback(self.manager.list_backups()[0], confirmed=True)
        self.assertEqual(self.manager.service.read_text(), 'old service')
        self.assertIn(('enable',), self.calls)

    def test_service_explicit_actions_only(self):
        self.manager.service.parent.mkdir(parents=True,exist_ok=True)
        self.manager.service.write_text('unit')
        with self.assertRaises(m.ManagementError): self.manager.service_action('stop')
        self.assertEqual(self.calls, [])
        self.manager.service_action('start',confirmed=True)
        self.manager.service_action('stop',confirmed=True)
        self.manager.service_action('restart',confirmed=True)
        self.assertEqual(self.calls,[('start',),('stop',),('restart',)])

    def test_no_shell_execution_for_wrong_home(self):
        manager = m.RuntimeManager(self.home)
        manager.service.parent.mkdir(exist_ok=True, parents=True)
        manager.service.write_text('unit')
        with self.assertRaises(m.ManagementError):
            manager.service_action('stop', confirmed=True)

    def test_rejects_symlink_location(self):
        outside = self.home / 'outside'
        outside.mkdir()
        (self.home/'.local').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(m.ManagementError):
            m.RuntimeManager(self.home,service_runner=self.calls.append)

    def test_rejects_path_traversal_archive(self):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tf:
            ti = tarfile.TarInfo('../bad')
            ti.size = 1
            tf.addfile(ti,io.BytesIO(b'x'))
        with self.assertRaises(m.ManagementError):
            m._extract_validated_archive(out.getvalue(),self.home/'stage')

    def test_rejects_symlink_archive(self):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:gz') as tf:
            ti=tarfile.TarInfo('install-user.sh')
            ti.type=tarfile.SYMTYPE
            ti.linkname='/etc/passwd'
            tf.addfile(ti)
        with self.assertRaises(m.ManagementError):
            m._extract_validated_archive(out.getvalue(),self.home/'stage')

    def test_reject_invalid_archive_structure(self):
        with self.assertRaises(m.ManagementError):
            m._extract_validated_archive(b'garbage',self.home/'stage')


if __name__ == '__main__': unittest.main()
