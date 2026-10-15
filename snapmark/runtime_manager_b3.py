"""B3-2: consent-gated management of the *application* Local AI Runtime.

The pinned package never includes or updates GPU backend packages or models.
No operation is automatic, including service restarts. Testable with a private HOME
and a fake service runner; never use sudo.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from urllib.request import Request, urlopen

VERSION = '1.0.0'
TAG = 'local-ai-runtime-v1.0.0'
PACKAGE = 'Local-AI-Runtime-1.0.0-linux-x86_64.tar.gz'
PACKAGE_SHA256 = 'a87749de1c16fc43055292def788fc04f90389b11b07d7b17ddf05c0dca09953'
CHECKSUMS_SHA256 = '2811525dd2669cef32656d1fed5e97a73a56bcf1f272fe8bf0e87b21cdb207df'
RELEASE_ROOT = f'https://github.com/yanjing-chen/local-ai-runtime/releases/download/{TAG}'
FILES = ('local_ai_runtime.py', 'runtime_manager.py', 'runtime_api.py',
         'model_api.py', 'custom_model_api.py', 'gguf_inspector.py',
         'preferences_api.py', 'runtimectl.py', 'hunyuanocr_installer.py')
BINARIES = ('local-ai-runtime', 'local-ai-runtime-runtime')
SERVICE_NAME = 'local-ai-runtime.service'
MAX_PACKAGE = 2 * 1024 * 1024
MAX_CHECKSUMS = 16384
MAX_MEMBER = 1024 * 1024


class ManagementError(Exception):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes, mode: int = 0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.snapmark-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _safe_home_path(home: Path, target: Path):
    """Reject symlinks in path segments so management cannot escape HOME."""
    home = home.absolute()
    path = target.absolute()
    if not path.is_relative_to(home) or path == home:
        raise ManagementError('Unsafe path outside private HOME')
    current = home
    for part in path.relative_to(home).parts:
        current = current / part
        if current.is_symlink():
            raise ManagementError(f'Symlink at managed location: {current}')
    return path


def _fetch_pinned(url: str, *, limit: int, opener=urlopen) -> bytes:
    if url not in (f'{RELEASE_ROOT}/{PACKAGE}', f'{RELEASE_ROOT}/SHA256SUMS'):
        raise ManagementError('Unapproved download URL')
    try:
        request = Request(url, headers={'User-Agent': 'SnapMark-B3-2/1.0',
                                         'Accept': 'application/octet-stream'})
        with opener(request, timeout=35) as res:
            if res.status != 200:
                raise ManagementError(f'HTTP {res.status}')
            payload = res.read(limit + 1)
    except (OSError, TimeoutError) as e:
        raise ManagementError(f'Download failed: {e}') from e
    if not payload or len(payload) > limit:
        raise ManagementError('Download empty or too large')
    return payload


def verify_checksum_file(raw: bytes):
    if _sha(raw) != CHECKSUMS_SHA256:
        raise ManagementError('Checksum manifest SHA256 does not match pinned release')
    values = []
    for line in raw.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?(.+)', line.strip())
        if match and match.group(2) == PACKAGE:
            values.append(match.group(1).lower())
    if values != [PACKAGE_SHA256]:
        raise ManagementError('Application archive missing or mismatched in SHA256SUMS')


def _extract_validated_archive(payload: bytes, destination: Path):
    """Validate every tar member *before* extracting any. Disallow links/devices.

    Archive may have one folder prefix; install-user.sh and src files must be
    from the same archive root. Reject duplicate paths and excessive members.
    """
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz')
    except (tarfile.TarError, OSError) as e:
        raise ManagementError(f'Invalid Runtime archive: {e}') from e
    with archive:
        members = archive.getmembers()
        if len(members) > 100:
            raise ManagementError('Too many Runtime archive files')
        seen = set()
        for member in members:
            name = member.name.rstrip('/')
            path = PurePosixPath(name)
            if (not name or name.startswith('/') or '\\' in name or
                    '..' in path.parts or '.' in path.parts or path.is_absolute()):
                raise ManagementError('Unsafe path in archive')
            if name in seen:
                raise ManagementError('Duplicate path in Runtime archive')
            seen.add(name)
            if not (member.isfile() or member.isdir()) or member.size > MAX_MEMBER:
                raise ManagementError('Unsupported member/size in archive')
        # Match the installer by its exact basename. A real official bundle
        # also contains uninstall-user.sh, which ends with 'install-user.sh'.
        roots = []
        for member in members:
            path = PurePosixPath(member.name)
            if member.isfile() and path.name == 'install-user.sh':
                roots.append(path.parent)
        if len(roots) != 1:
            raise ManagementError('Expected one official install-user.sh')
        root = roots[0]
        required = {'install-user.sh', 'config.example.json'} | {
            f'src/{item}' for item in FILES if item != 'hunyuanocr_installer.py'}
        normalized = {str(PurePosixPath(name).relative_to(root))
                      for name in seen if PurePosixPath(name).is_relative_to(root)}
        if not required.issubset(normalized):
            raise ManagementError('Incomplete Runtime 1.0.0 archive')
        # Only accept the official expected application/source layout.
        for member in members:
            name = PurePosixPath(member.name)
            if not name.is_relative_to(root):
                # Tar archives may include a single parent directory.
                if not member.isdir() or not root.is_relative_to(name):
                    raise ManagementError('Unexpected outside archive content')
                continue
            relative = name.relative_to(root)
            if not relative.parts:
                continue
            dest = destination.joinpath(*relative.parts)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream is None:
                    raise ManagementError('Unreadable Runtime archive member')
                _atomic_write(dest, stream.read(), 0o755 if relative.name == 'install-user.sh' else 0o644)
    return destination


class RuntimeManager:
    def __init__(self, home: Path | None = None, *, service_runner=None):
        self.home = (Path.home() if home is None else Path(home)).absolute()
        if self.home.is_symlink() or not self.home.is_dir():
            raise ManagementError('HOME must exist and not be a symlink')
        self.lib = self.home / '.local/lib/local-ai-runtime'
        self.bin = self.home / '.local/bin'
        self.config = self.home / '.config/local-ai-runtime'
        self.data = self.home / '.local/share/local-ai-runtime'
        self.service = self.home / '.config/systemd/user' / SERVICE_NAME
        self.cache = self.home / '.cache/snapmark/runtime-1.0.0'
        self.backups = self.home / '.local/share/snapmark/runtime-backups'
        self.service_runner = service_runner
        for path in (self.lib, self.bin, self.config, self.data, self.service,
                     self.cache, self.backups):
            _safe_home_path(self.home, path)

    def _run(self, *args):
        if self.service_runner is None:
            if self.home != Path.home().absolute():
                raise ManagementError('Never run real systemctl against an isolated HOME')
            command = ['systemctl', '--user', *args, SERVICE_NAME]
            try:
                result = subprocess.run(command, capture_output=True,
                                        text=True, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired) as e:
                raise ManagementError(f'Service command failed: {e}') from e
            if result.returncode:
                raise ManagementError(result.stderr.strip()[:240] or 'systemctl failed')
        else:
            self.service_runner(tuple(args))

    def _is_service_enabled(self):
        """Read-only service enablement check; None means unknown."""
        if not self.service.is_file():
            return False
        if self.service_runner is not None:
            value = self.service_runner(('is-enabled',))
            return value == 'enabled' if isinstance(value, str) else None
        if self.home != Path.home().absolute():
            return None
        try:
            p = subprocess.run(['systemctl', '--user', 'is-enabled', SERVICE_NAME],
                               capture_output=True, text=True, timeout=8)
            state = p.stdout.strip()
            if state == 'enabled':
                return True
            if state in ('disabled', 'static', 'masked'):
                return False
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    def service_action(self, action: str, *, confirmed: bool = False):
        if not confirmed:
            raise ManagementError('Explicit confirmation required')
        if action not in ('start', 'stop', 'restart'):
            raise ManagementError('Unsupported service action')
        if not self.service.is_file():
            raise ManagementError('Local user service not installed')
        self._run(action)
        return f'{action} requested'

    def _daemon_reload(self):
        if self.service_runner is not None:
            self.service_runner(('daemon-reload',))
            return
        if self.home != Path.home().absolute():
            raise ManagementError('Isolated HOME may not run real systemctl')
        p = subprocess.run(['systemctl', '--user', 'daemon-reload'],
                           capture_output=True, text=True, timeout=15)
        if p.returncode:
            raise ManagementError(p.stderr.strip()[:240] or 'daemon-reload failed')

    def download_and_verify(self, *, opener=urlopen):
        """Only on user click. The fixed pinned hash protects even a fake release link."""
        raw_sum = _fetch_pinned(f'{RELEASE_ROOT}/SHA256SUMS', limit=MAX_CHECKSUMS, opener=opener)
        verify_checksum_file(raw_sum)
        payload = _fetch_pinned(f'{RELEASE_ROOT}/{PACKAGE}', limit=MAX_PACKAGE, opener=opener)
        if _sha(payload) != PACKAGE_SHA256:
            raise ManagementError('Archive digest mismatch')
        with tempfile.TemporaryDirectory(prefix='snapmark-verify-') as temp:
            _extract_validated_archive(payload, Path(temp))
        _atomic_write(_safe_home_path(self.home, self.cache / PACKAGE), payload)
        _atomic_write(_safe_home_path(self.home, self.cache / 'SHA256SUMS'), raw_sum)
        return f'Verified {PACKAGE} ({len(payload)} bytes)'

    def archive_ready(self):
        path = self.cache / PACKAGE
        return (path.is_file() and 0 < path.stat().st_size <= MAX_PACKAGE
                and _sha(path.read_bytes()) == PACKAGE_SHA256)

    def _tracked_paths(self):
        return ([self.lib / name for name in FILES] +
                [self.bin / name for name in BINARIES] +
                [self.service] +
                [self.config / name for name in ('config.json', 'preferences.json', 'custom-models.json')])

    def backup(self):
        """Snapshot application and config files only; NEVER copy GGUF or GPU backend data."""
        stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + os.urandom(3).hex()
        dst = _safe_home_path(self.home, self.backups / stamp)
        if dst.exists():
            raise ManagementError('Backup destination exists')
        dst.mkdir(parents=True, mode=0o700)
        dst.chmod(0o700)
        records = []
        for idx, original in enumerate(self._tracked_paths()):
            _safe_home_path(self.home, original)
            if original.exists():
                if not original.is_file() or original.stat().st_size > MAX_MEMBER:
                    raise ManagementError('Unexpected managed file')
                raw = original.read_bytes()
                filename = f'file-{idx:02d}'
                _atomic_write(dst / filename, raw, 0o600)
                records.append({'path': str(original.relative_to(self.home)),
                                'blob': filename, 'sha256': _sha(raw),
                                'mode': original.stat().st_mode & 0o777})
            else:
                records.append({'path': str(original.relative_to(self.home)), 'blob': None})
        manifest = {'schema': 1, 'timestamp': stamp, 'records': records,
                    'service_enabled': self._is_service_enabled()}
        _atomic_write(dst / 'manifest.json', json.dumps(manifest).encode())
        return dst

    def list_backups(self):
        if not self.backups.is_dir():
            return []
        return sorted((p.name for p in self.backups.iterdir()
                       if p.is_dir() and re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{6}', p.name)), reverse=True)

    def _restore(self, backup: Path):
        _safe_home_path(self.home, backup)
        try:
            manifest = json.loads((backup / 'manifest.json').read_text())
        except (OSError, ValueError) as e:
            raise ManagementError(f'Invalid backup manifest: {e}') from e
        if manifest.get('schema') != 1 or not isinstance(manifest.get('records'), list):
            raise ManagementError('Unsupported backup manifest')
        expected = {str(p.relative_to(self.home)) for p in self._tracked_paths()}
        records = manifest['records']
        if len(records) != len(expected) or {r.get('path') for r in records} != expected:
            raise ManagementError('Backup file list mismatch')
        verified = []
        for rec in records:
            dest = _safe_home_path(self.home, self.home / rec['path'])
            blob = rec.get('blob')
            if blob is not None:
                if not re.fullmatch(r'file-\d{2}', str(blob)):
                    raise ManagementError('Unsafe backup blob')
                source = _safe_home_path(self.home, backup / blob)
                raw = source.read_bytes()
                if _sha(raw) != rec.get('sha256') or len(raw) > MAX_MEMBER:
                    raise ManagementError('Backup checksum mismatch')
                mode = rec.get('mode')
                if type(mode) is not int or mode & ~0o777:
                    raise ManagementError('Backup permission invalid')
                verified.append((dest, raw, mode))
            else:
                verified.append((dest, None, None))
        for dest, raw, mode in verified:
            if raw is None:
                if dest.is_file():
                    dest.unlink()
            else:
                _atomic_write(dest, raw, mode)
        self._daemon_reload()
        enabled = manifest.get('service_enabled')
        if enabled is True and self.service.is_file():
            self._run('enable')
        elif enabled is False and self.service.is_file():
            self._run('disable')
        return 'Files restored; start service only after explicit confirmation'

    def rollback(self, backup_id: str, *, confirmed: bool = False):
        if not confirmed:
            raise ManagementError('Explicit confirmation required')
        if backup_id not in self.list_backups():
            raise ManagementError('Unknown backup')
        return self._restore(self.backups / backup_id)

    def install_verified(self, *, confirmed: bool = False):
        if not confirmed:
            raise ManagementError('Explicit confirmation required')
        if not self.archive_ready():
            raise ManagementError('No pinned verified package cached')
        # Mandatory backup, even for a new installation.
        snap = self.backup()
        payload = (self.cache / PACKAGE).read_bytes()
        try:
            with tempfile.TemporaryDirectory(prefix='snapmark-runtime-src-') as temp:
                stage = _extract_validated_archive(payload, Path(temp))
                # Reuse OFFICIAL installer, not a reimplementation.
                env = dict(os.environ)
                env['HOME'] = str(self.home)
                p = subprocess.run(['bash', str(stage / 'install-user.sh'), '--no-systemd'],
                                   cwd=stage, env=env, capture_output=True,
                                   text=True, timeout=30)
                if p.returncode:
                    raise ManagementError('Official installer failed: ' + p.stderr[-300:])
            # Use exact pinned unit format, matching official installer, and
            # do not auto-start/restart active 0.8.0 service.
            unit = ('[Unit]\nDescription=Local AI Runtime\nAfter=graphical-session.target\n\n'
                    '[Service]\nType=simple\nExecStart=%h/.local/bin/local-ai-runtime '
                    '--config %h/.config/local-ai-runtime/config.json\n'
                    'Restart=on-failure\nRestartSec=2\n\n[Install]\nWantedBy=default.target\n')
            _atomic_write(self.service, unit.encode(), 0o644)
            self._daemon_reload()
            return f'Installed program files for {VERSION}; backup {snap.name}. Service NOT restarted.'
        except Exception:
            self._restore(snap)
            raise

    def uninstall(self, *, confirmed: bool = False, remove_config: bool = False):
        """Uninstall app/service only by default; NEVER remove data or external GGUF.

        A separate explicit option may remove only three small configuration files.
        GPU runtimes and model files, including external GGUF, are preserved.
        """
        if not confirmed:
            raise ManagementError('Explicit confirmation required')
        snap = self.backup()
        try:
            # Stop and disable service before touching the executable. Never
            # act on global/root system services.
            if self.service.is_file():
                self._run('stop')
                self._run('disable')
            for path in [self.lib / x for x in FILES] + [self.bin / x for x in BINARIES] + [self.service]:
                _safe_home_path(self.home, path)
                if path.is_file():
                    path.unlink()
            if remove_config:
                for name in ('config.json', 'preferences.json', 'custom-models.json'):
                    path = _safe_home_path(self.home, self.config / name)
                    if path.is_file():
                        path.unlink()
            self._daemon_reload()
            return f'Runtime program removed. Backup {snap.name}. Models and GPU backends preserved.'
        except Exception:
            self._restore(snap)
            raise
