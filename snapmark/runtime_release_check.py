"""B3-1: read-only installation and pinned official-release inspection.

Never execute installers or systemctl, never POST to Runtime, and never download
release assets.  Release metadata does not itself verify an archive checksum.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RELEASE_TAG = 'local-ai-runtime-v1.0.0'
RELEASE_VERSION = '1.0.0'
RELEASE_SHA = 'cb10db5f8bb1bf0590c245001e268d1f7cc60fa0'
RELEASE_URL = f'https://github.com/yanjing-chen/local-ai-runtime/releases/tag/{RELEASE_TAG}'
RELEASE_API = f'https://api.github.com/repos/yanjing-chen/local-ai-runtime/releases/tags/{RELEASE_TAG}'
MAX_RESPONSE_BYTES = 1024 * 1024
_VERSION_PATTERN = re.compile(r'^\s*(\d+)\.(\d+)\.(\d+)\s*$')


class ReleaseCheckError(Exception):
    """An optional read-only check failed; never block Runtime connection."""


@dataclass(frozen=True)
class LocalRuntimeInstallation:
    installed: bool
    complete: bool
    files: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeRelease:
    version: str
    tag: str
    web_url: str
    assets: tuple[str, ...]
    archive_assets: tuple[str, ...]
    checksum_assets: tuple[str, ...]


def inspect_local_installation(home: Path | None = None) -> LocalRuntimeInstallation:
    """Check known user-install markers; an unreachable API != not installed.

    This only checks presence and never reads users' config, models or secrets.
    """
    base = Path.home() if home is None else Path(home)
    paths = (
        base / '.local/bin/local-ai-runtime',
        base / '.local/lib/local-ai-runtime/local_ai_runtime.py',
        base / '.config/systemd/user/local-ai-runtime.service',
    )
    present = tuple(str(p) for p in paths if p.is_file())
    missing = tuple(str(p) for p in paths if not p.is_file())
    return LocalRuntimeInstallation(bool(present), not missing, present, missing)


def compare_versions(installed_version: str, target_version: str = RELEASE_VERSION) -> str:
    """Return older/equal/newer/unknown; never guess for development labels."""
    current = _VERSION_PATTERN.fullmatch(installed_version) if isinstance(installed_version, str) else None
    target = _VERSION_PATTERN.fullmatch(target_version) if isinstance(target_version, str) else None
    if not current or not target:
        return 'unknown'
    left = tuple(int(i) for i in current.groups())
    right = tuple(int(i) for i in target.groups())
    return 'older' if left < right else 'newer' if left > right else 'equal'


def inspect_release_payload(data: object) -> RuntimeRelease:
    """Reject unexpected or incomplete GitHub API responses (no guesswork)."""
    if not isinstance(data, dict) or data.get('tag_name') != RELEASE_TAG:
        raise ReleaseCheckError('Official release tag missing or unexpected.')
    page = data.get('html_url')
    if page != RELEASE_URL:
        raise ReleaseCheckError('Unexpected official release URL.')
    assets = data.get('assets')
    if not isinstance(assets, list):
        raise ReleaseCheckError('Missing official asset listing.')
    names = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get('name')
        if isinstance(name, str) and 0 < len(name) < 256:
            names.append(name)
    # These are only asset NAMES. Verification and installation belong to B3-2.
    archives = tuple(n for n in names if n.endswith(('.tar.gz', '.tgz', '.zip')))
    checksums = tuple(n for n in names if n.endswith(('.sha256', '.sha256sum', '.sha256sums')) or
                      n.lower() in ('sha256sums', 'sha256sums.txt', 'checksums.txt'))
    return RuntimeRelease(RELEASE_VERSION, RELEASE_TAG, page,
                          tuple(names), archives, checksums)


def fetch_official_release(*, timeout: float = 6.0) -> RuntimeRelease:
    """GET official pinned 1.0.0 metadata on a button click; no asset transfer."""
    if type(timeout) not in (int, float) or not 0 < timeout <= 30:
        raise ReleaseCheckError('Invalid release check timeout.')
    req = Request(RELEASE_API, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'SnapMark-B3-1-read-only',
        'X-GitHub-Api-Version': '2022-11-28',
    }, method='GET')
    try:
        with urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise ReleaseCheckError(f'GitHub returned HTTP {response.status}.')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ReleaseCheckError(f'Cannot query official release: {exc}') from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ReleaseCheckError('Official release metadata is too large.')
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ReleaseCheckError('Official release metadata is not valid JSON.') from exc
    return inspect_release_payload(data)
