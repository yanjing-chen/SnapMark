"""Explicit, consent-gated Runtime 1.0+ idle-unload preference client.

No installation, model operation, backend selection, or service control.
GET checks may be made in a worker thread; POST requires explicit confirmation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai_runtime import RuntimeIntegrationError, validate_endpoint

PREFERENCES_ROUTE = '/v1/runtime/preferences'
MAX_IDLE_SECONDS = 86400
MAX_BODY = 65536


@dataclass(frozen=True)
class IdleCapability:
    writable: bool
    seconds: int | None = None
    reason: str = ''


def supports_idle_write(version: str) -> bool:
    """Only official stable 1.0+ versions; never infer from an old GET 200."""
    if not isinstance(version, str):
        return False
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:\+[A-Za-z0-9.-]+)?', version.strip())
    return bool(match and tuple(map(int, match.groups()[:3])) >= (1, 0, 0))


def validate_idle_seconds(seconds: int) -> int:
    if type(seconds) is not int or not (0 <= seconds <= MAX_IDLE_SECONDS):
        raise RuntimeIntegrationError('Idle time must be an integer from 0 to 86400 seconds (0 disables).')
    return seconds


def _json_request(endpoint: str, method: str, *, payload: dict | None = None,
                  timeout: float = 4.0) -> dict:
    address = validate_endpoint(endpoint) + PREFERENCES_ROUTE
    raw = None if payload is None else json.dumps(payload, separators=(',', ':')).encode('utf-8')
    request = Request(address, method=method, data=raw, headers={
        'Accept': 'application/json', 'User-Agent': 'SnapMark/0.6-B2-C2',
        **({'Content-Type': 'application/json'} if raw is not None else {}),
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeIntegrationError(f'Runtime returned HTTP {response.status}.')
            data = response.read(MAX_BODY + 1)
    except HTTPError as exc:
        message = ''
        try:
            error = json.loads(exc.read(MAX_BODY))
            item = error.get('error', {}) if isinstance(error, dict) else {}
            if isinstance(item, dict) and isinstance(item.get('message'), str):
                message = ': ' + item['message'][:200]
        except (OSError, ValueError, UnicodeDecodeError):
            pass
        raise RuntimeIntegrationError(f'Runtime HTTP {exc.code}{message}') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeIntegrationError(f'Runtime connection failed: {exc}') from exc
    if len(data) > MAX_BODY:
        raise RuntimeIntegrationError('Runtime preferences response is too large.')
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeIntegrationError('Runtime returned invalid preferences JSON.') from exc
    if not isinstance(parsed, dict):
        raise RuntimeIntegrationError('Runtime preferences response must be an object.')
    return parsed


def read_idle_capability(endpoint: str, version: str) -> IdleCapability:
    """Read-only; a successful 0.8.0 preferences GET does not allow edits."""
    if not supports_idle_write(version):
        return IdleCapability(False, reason='Requires verified Runtime 1.0.0+ (older service: read-only).')
    try:
        data = _json_request(endpoint, 'GET')
        seconds = validate_idle_seconds(data.get('idle_unload_seconds'))
        return IdleCapability(True, seconds)
    except RuntimeIntegrationError as exc:
        return IdleCapability(False, reason=f'Cannot verify Runtime 1.0 preferences API: {exc}')


def change_idle_seconds(endpoint: str, seconds: int, *, expected_seconds: int,
                        confirmed: bool = False) -> int:
    """Write precisely one preference after opt-in and stale-setting detection.

    Uses a fresh health/version read and the existing effective preference before
    POST; verifies the persisted value with GET afterwards. This is a best-effort
    client-side race check, not a server-side compare-and-swap transaction.
    """
    if confirmed is not True:
        raise RuntimeIntegrationError('An explicit user confirmation is required.')
    seconds = validate_idle_seconds(seconds)
    expected_seconds = validate_idle_seconds(expected_seconds)
    from .ai_runtime import _read_json  # keep read-only probe module intact
    health = _read_json(endpoint, '/health', 4.0)
    if not isinstance(health, dict) or health.get('status') != 'ok' or not supports_idle_write(health.get('runtime_version')):
        raise RuntimeIntegrationError('Runtime 1.0.0+ could not be verified; no change sent.')
    before = _json_request(endpoint, 'GET')
    previous = validate_idle_seconds(before.get('idle_unload_seconds'))
    if previous != expected_seconds:
        raise RuntimeIntegrationError('The shared Runtime timeout changed since your last check. Refresh before saving.')
    if previous == seconds:
        return seconds  # no-op: do not POST
    response = _json_request(endpoint, 'POST', payload={'idle_unload_seconds': seconds})
    # Response shape is documented in pinned Runtime 1.0.0 source.
    try:
        accepted = validate_idle_seconds(response.get('idle_unload_seconds'))
    except RuntimeIntegrationError as exc:
        raise RuntimeIntegrationError('Write response unrecognized; refresh Runtime status to confirm the outcome.') from exc
    if accepted != seconds:
        raise RuntimeIntegrationError('Runtime returned a different timeout; refresh to inspect the current value.')
    final = _json_request(endpoint, 'GET')
    try:
        effective = validate_idle_seconds(final.get('idle_unload_seconds'))
    except RuntimeIntegrationError as exc:
        raise RuntimeIntegrationError('Cannot confirm saved value; refresh Runtime status.') from exc
    if effective != seconds:
        raise RuntimeIntegrationError('Runtime did not retain the requested timeout; refresh before retrying.')
    # Verify the live manager (not only the persisted preference) was updated.
    status = _read_json(endpoint, '/v1/runtime/status', 4.0)
    if not isinstance(status, dict) or status.get('idle_unload_seconds') != seconds:
        raise RuntimeIntegrationError('Preference saved, but live Runtime status disagrees; refresh before retrying.')
    return effective
