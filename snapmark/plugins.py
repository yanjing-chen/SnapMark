"""SnapMark official-plugin lifecycle (API v1, no GTK dependency).

Only official GitHub releases are discovered. Plugins are user-level code and
MUST be considered executable: release checksum verifies transport integrity,
not the trustworthiness of the release publisher. Never import plugin code from
an unknown archive as part of discovery/installation.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

PLUGIN_API = 1
HOST_VERSION = '0.6.0'
OFFICIAL_REPO = 'yanjing-chen/SnapMark'
PLUGIN_IDS = ('ocr', 'translation')
MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 40 * 1024 * 1024
MAX_ENTRIES = 350
VERSION_RE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')


class PluginError(ValueError):
    """User-visible validation, dependency or network failure."""


def version_key(v):
    if not isinstance(v, str) or not VERSION_RE.fullmatch(v):
        raise PluginError('Expected a stable X.Y.Z plugin version')
    return tuple(int(part) for part in v.split('.'))


def data_root():
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'snapmark/plugins'


def config_root():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'snapmark'


def _manifest(data):
    if not isinstance(data, dict):
        raise PluginError('Invalid plugin manifest')
    ident, ver = data.get('id'), data.get('version')
    if ident not in PLUGIN_IDS:
        raise PluginError('Only SnapMark official OCR and Translation plugins are allowed')
    version_key(ver)
    if type(data.get('api_version')) is not int or data['api_version'] != PLUGIN_API:
        raise PluginError('Plugin API version is not supported')
    minimum = data.get('min_host_version', HOST_VERSION)
    if version_key(minimum) > version_key(HOST_VERSION):
        raise PluginError(f'Plugin needs SnapMark {minimum} or later')
    dependencies = data.get('dependencies', {})
    if not isinstance(dependencies, dict) or set(dependencies) - set(PLUGIN_IDS):
        raise PluginError('Invalid plugin dependencies')
    if ident == 'translation' and 'ocr' not in dependencies:
        raise PluginError('Translation must declare its OCR dependency')
    if ident == 'ocr' and dependencies:
        raise PluginError('OCR cannot depend on another plugin')
    if ident in dependencies:
        raise PluginError('A plugin cannot depend on itself')
    for depver in dependencies.values():
        version_key(depver)
    entry = data.get('entrypoint')
    if entry is not None and (not isinstance(entry, str) or not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*:[A-Za-z_]\w*', entry)):
        raise PluginError('Invalid plugin entrypoint')
    return dict(data)


def _safe_entries(archive):
    items = archive.infolist()
    if len(items) > MAX_ENTRIES:
        raise PluginError('Too many files in plugin ZIP')
    if sum(info.file_size for info in items) > MAX_UNPACKED_BYTES:
        raise PluginError('Plugin ZIP exceeds unpacked size limit')
    names = set()
    for info in items:
        name = info.filename
        path = PurePosixPath(name)
        if (not name or '\\' in name or path.is_absolute() or '..' in path.parts
                or not path.parts or ':' in path.parts[0]):
            raise PluginError('Unsafe plugin archive path')
        if name in names:
            raise PluginError('Duplicate plugin archive entry')
        names.add(name)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise PluginError('Symbolic links are forbidden inside plugin ZIP')
        if mode and stat.S_IFMT(mode) not in (0, stat.S_IFDIR, stat.S_IFREG):
            raise PluginError('Unsupported plugin ZIP file type')
    if 'plugin.json' not in names:
        raise PluginError('Plugin ZIP must contain a top-level plugin.json')
    return items


class PluginManager:
    def __init__(self, root=None, settings_root=None):
        self.root = Path(root) if root is not None else data_root()
        self.settings_root = Path(settings_root) if settings_root is not None else config_root()
        self.state_path = self.settings_root / 'plugins.json'

    def _state(self):
        try:
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
            return state if isinstance(state, dict) else {}
        except (ValueError, OSError):
            return {}

    def _save(self, state):
        self.settings_root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.settings_root, prefix='.plugins-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            os.replace(name, self.state_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def manifest(self, ident, version):
        if ident not in PLUGIN_IDS:
            raise PluginError('Unknown plugin')
        version_key(version)
        path = self.root / ident / version / 'plugin.json'
        try:
            m = _manifest(json.loads(path.read_text(encoding='utf-8')))
            return m if m['id'] == ident and m['version'] == version else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def versions(self, ident):
        if ident not in PLUGIN_IDS:
            raise PluginError('Unknown plugin')
        folder = self.root / ident
        if not folder.is_dir():
            return []
        return sorted([p.name for p in folder.iterdir() if p.is_dir()
                       and VERSION_RE.fullmatch(p.name) and self.manifest(ident, p.name)],
                      key=version_key, reverse=True)

    def selected(self, ident):
        obj = self._state().get(ident)
        v = obj.get('version') if isinstance(obj, dict) else None
        return v if v in self.versions(ident) else None

    def is_enabled(self, ident):
        obj = self._state().get(ident)
        return bool(self.selected(ident) and isinstance(obj, dict) and obj.get('enabled') is True)

    def is_available(self, ident):
        if not self.is_enabled(ident):
            return False
        manifest = self.manifest(ident, self.selected(ident))
        return bool(manifest and all(self.is_available(dep) and
                    version_key(self.selected(dep)) >= version_key(minimum)
                    for dep, minimum in manifest.get('dependencies', {}).items()))

    def select(self, ident, version, enabled=True):
        manifest = self.manifest(ident, version)
        if not manifest:
            raise PluginError('Selected plugin version is not installed or is invalid')
        if enabled:
            for dep, minimum in manifest.get('dependencies', {}).items():
                active = self.selected(dep)
                if not active or not self.is_available(dep) or version_key(active) < version_key(minimum):
                    raise PluginError(f'{ident} needs enabled {dep} {minimum} or later')
        # Do not silently break an enabled Translation installation when
        # switching OCR to an older, incompatible version.
        if ident == 'ocr' and self.is_enabled('translation'):
            active_translation = self.manifest('translation', self.selected('translation'))
            minimum = active_translation['dependencies']['ocr']
            if version_key(version) < version_key(minimum):
                raise PluginError(f'Translation requires OCR {minimum} or later')
        state = self._state()
        state[ident] = {'version': version, 'enabled': bool(enabled)}
        self._save(state)

    def set_enabled(self, ident, enabled):
        v = self.selected(ident)
        if not v:
            raise PluginError('Install a plugin version first')
        self.select(ident, v, bool(enabled))

    def uninstall(self, ident, version):
        if not self.manifest(ident, version):
            raise PluginError('Plugin version not installed')
        if ident == 'ocr' and self.versions('translation') and len(self.versions('ocr')) == 1:
            raise PluginError('Uninstall Translation before removing the last OCR version')
        was_selected = self.selected(ident) == version
        folder = self.root / ident / version
        shutil.rmtree(folder)
        if was_selected:
            # selection now points to a missing version; clear it safely.
            state = self._state()
            state.pop(ident, None)
            self._save(state)

    def install_zip(self, payload: bytes, ident: str, version: str, expected_sha256: str):
        """Install *verified* official release bytes, never execute during install."""
        if ident not in PLUGIN_IDS:
            raise PluginError('Unknown plugin')
        version_key(version)
        if len(payload) > MAX_PACKAGE_BYTES:
            raise PluginError('Plugin package is too large')
        if not re.fullmatch(r'[a-fA-F0-9]{64}', expected_sha256 or ''):
            raise PluginError('A published SHA256 checksum is required')
        if hashlib.sha256(payload).hexdigest().lower() != expected_sha256.lower():
            raise PluginError('Plugin SHA256 checksum mismatch')
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                _safe_entries(archive)
                manifest = _manifest(json.loads(archive.read('plugin.json')))
                if manifest['id'] != ident or manifest['version'] != version:
                    raise PluginError('Plugin release identity mismatch')
                dest = self.root / ident / version
                if dest.exists():
                    raise PluginError('This plugin version is already installed')
                self.root.mkdir(parents=True, exist_ok=True)
                stage = Path(tempfile.mkdtemp(prefix='.snapmark-plugin-', dir=self.root))
                try:
                    for info in archive.infolist():
                        target = stage.joinpath(*PurePosixPath(info.filename).parts)
                        if info.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(info) as src, target.open('wb') as dst:
                                shutil.copyfileobj(src, dst)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    stage.rename(dest)
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
        except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginError(f'Invalid plugin ZIP: {exc}') from exc
        return manifest


def _http_bytes(url, *, max_bytes=MAX_PACKAGE_BYTES):
    request = urllib.request.Request(url, headers={'User-Agent': 'SnapMark-plugin-manager/0.6',
                                                   'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=15) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PluginError('Remote response exceeds download limit')
    return data


def available_releases(ident):
    """Read OFFICIAL repository only; empty list is valid before first release."""
    if ident not in PLUGIN_IDS:
        raise PluginError('Unknown plugin')
    url = f'https://api.github.com/repos/{OFFICIAL_REPO}/releases?per_page=100'
    try:
        records = json.loads(_http_bytes(url, max_bytes=1024 * 1024))
    except Exception as exc:
        raise PluginError(f'Could not check GitHub Releases: {exc}') from exc
    if not isinstance(records, list):
        raise PluginError('Unexpected GitHub response')
    result = []
    for record in records:
        if not isinstance(record, dict) or record.get('draft') or record.get('prerelease'):
            continue
        tag = record.get('tag_name', '')
        prefix = ident + '-v'
        if not isinstance(tag, str) or not tag.startswith(prefix):
            continue
        version = tag[len(prefix):]
        try:
            version_key(version)
        except PluginError:
            continue
        assets = {a.get('name'): a.get('browser_download_url') for a in (record.get('assets') or []) if isinstance(a, dict)}
        filename = f'SnapMark-{ident}-{version}.zip'
        checksum = filename + '.sha256'
        if all(isinstance(assets.get(name), str) and assets[name].startswith(
                f'https://github.com/{OFFICIAL_REPO}/releases/download/')
               for name in (filename, checksum)):
            result.append({'id': ident, 'version': version,
                           'url': assets[filename], 'checksum_url': assets[checksum]})
    return sorted(result, key=lambda x: version_key(x['version']), reverse=True)


def install_release(manager, release):
    """Download ZIP and checksum from matched official release metadata."""
    ident, version = release['id'], release['version']
    if ident not in PLUGIN_IDS:
        raise PluginError('Unknown release plugin')
    version_key(version)
    prefix = f'https://github.com/{OFFICIAL_REPO}/releases/download/{ident}-v{version}/'
    expected_zip = f'SnapMark-{ident}-{version}.zip'
    if release.get('url') != prefix + expected_zip or release.get('checksum_url') != prefix + expected_zip + '.sha256':
        raise PluginError('Unexpected release download URL')
    try:
        sums = _http_bytes(release['checksum_url'], max_bytes=4096).decode('ascii').strip().split()
        if not sums or (len(sums) > 1 and sums[1].lstrip('*') != expected_zip):
            raise PluginError('Invalid checksum file')
        payload = _http_bytes(release['url'])
    except (OSError, UnicodeError, ValueError) as exc:
        raise PluginError(f'Plugin download failed: {exc}') from exc
    return manager.install_zip(payload, ident, version, sums[0])
