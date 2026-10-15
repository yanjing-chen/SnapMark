"""Local AI Runtime 1.0.0 backend lifecycle client.

API-only; never invokes shell commands, alters local files or chooses a backend
without explicit consent. Read statuses distinguish installed, usable, selected
and actually active. Operations run on the shared external Runtime service.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai_runtime import RuntimeIntegrationError, validate_endpoint, _read_json

FAMILIES = ('llama', 'cuda')
OPTIONS = ('auto', 'cpu', 'vulkan', 'cuda')
REQUIRED_VERSION = (1, 0, 0)
MAX_RESPONSE = 2 * 1024 * 1024


def _require_1_0(endpoint):
    health = _read_json(endpoint, '/health', 5)
    if not isinstance(health, dict) or health.get('service') != 'local-ai-runtime':
        raise RuntimeIntegrationError('Connected service is not Local AI Runtime.')
    version = str(health.get('runtime_version', ''))
    try:
        triple = tuple(int(n) for n in version.split('.')[:3])
    except ValueError as exc:
        raise RuntimeIntegrationError('Cannot verify Runtime version.') from exc
    if len(triple) != 3 or triple < REQUIRED_VERSION:
        raise RuntimeIntegrationError('Backend management requires Runtime 1.0.0+.')
    return health


def _post(endpoint, path, payload, expected_codes=(200,)):
    endpoint = validate_endpoint(endpoint)
    request = Request(endpoint + path, data=json.dumps(payload).encode('utf-8'), method='POST',
                      headers={'Content-Type':'application/json','Accept':'application/json',
                               'User-Agent':'SnapMark/0.6-runtime-backends'})
    try:
        with urlopen(request, timeout=20) as resp:
            code = resp.status
            body = resp.read(MAX_RESPONSE + 1)
    except HTTPError as exc:
        try:
            details = json.loads(exc.read(8192)).get('error', {})
            explanation = details.get('message', str(exc)) if isinstance(details, dict) else str(exc)
        except (ValueError, UnicodeError):
            explanation = str(exc)
        raise RuntimeIntegrationError(f'{path}: HTTP {exc.code}: {explanation}') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeIntegrationError(f'{path}: {exc}') from exc
    if code not in expected_codes or len(body) > MAX_RESPONSE:
        raise RuntimeIntegrationError(f'{path}: unexpected HTTP response {code}.')
    try:
        result = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeIntegrationError(f'{path}: invalid JSON response.') from exc
    if not isinstance(result, dict):
        raise RuntimeIntegrationError(f'{path}: response must be an object.')
    return result


@dataclass(frozen=True)
class BackendOverview:
    runtime_version: str
    active_backend: str
    model: str
    backend_running: bool
    healthy: bool
    fallback: str
    preference: str
    idle_seconds: int | None
    available: dict
    llama: dict
    cuda: dict


def read_overview(endpoint):
    """GET only. Status calls do not refresh/download manifests or load models."""
    endpoint = validate_endpoint(endpoint)
    health = _require_1_0(endpoint)
    paths = ('/v1/runtime/backends', '/v1/runtime/llama/status',
             '/v1/runtime/cuda/status', '/v1/runtime/preferences')
    values = [_read_json(endpoint, route, 25 if route.endswith('/backends') else 5)
              for route in paths]
    if not all(isinstance(obj, dict) for obj in values):
        raise RuntimeIntegrationError('Unexpected backend status response.')
    status, llama, cuda, prefs = values
    availability = status.get('availability')
    if not isinstance(availability, dict):
        availability = {}
    for family in FAMILIES:
        item = llama if family == 'llama' else cuda
        if not isinstance(item.get('operation'), dict):
            raise RuntimeIntegrationError(f'{family} operation status not reported.')
    timeout = prefs.get('idle_unload_seconds')
    if type(timeout) is not int:
        timeout = None
    return BackendOverview(
        str(health['runtime_version']), str(health.get('active_backend') or ''),
        str(health.get('current_model') or ''), health.get('backend_running') is True,
        health.get('backend_healthy') is True, str(health.get('backend_fallback') or ''),
        str(prefs.get('backend_preference') or ''), timeout, availability, llama, cuda)


def change_preference(endpoint, desired, *, confirmed=False, expected=None):
    """Explicitly update shared Runtime preference; switching can unload a model."""
    if not confirmed:
        raise RuntimeIntegrationError('Explicit user consent is required.')
    if desired not in OPTIONS:
        raise RuntimeIntegrationError('Unsupported backend preference.')
    endpoint = validate_endpoint(endpoint)
    _require_1_0(endpoint)
    current = _read_json(endpoint, '/v1/runtime/preferences', 5)
    if not isinstance(current, dict) or current.get('backend_preference') not in OPTIONS:
        raise RuntimeIntegrationError('Cannot verify current backend preference.')
    if expected is not None and current['backend_preference'] != expected:
        raise RuntimeIntegrationError('Runtime preference changed; refresh before saving.')
    if current['backend_preference'] == desired:
        return current
    answer = _post(endpoint, '/v1/runtime/preferences', {'backend_preference': desired})
    fresh = _read_json(endpoint, '/v1/runtime/preferences', 5)
    if not isinstance(fresh, dict) or fresh.get('backend_preference') != desired:
        raise RuntimeIntegrationError('Backend preference write not confirmed by Runtime.')
    return answer


def install_backend(endpoint, family, *, confirmed=False, version=None):
    if not confirmed:
        raise RuntimeIntegrationError('Explicit user consent is required.')
    if family not in FAMILIES:
        raise RuntimeIntegrationError('Unsupported backend family.')
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise RuntimeIntegrationError('Version must be nonempty or use latest.')
    endpoint = validate_endpoint(endpoint)
    _require_1_0(endpoint)
    payload = {'version': version.strip()} if version is not None else {}
    answer = _post(endpoint, f'/v1/runtime/{family}/install', payload, (202,))
    operation = answer.get('operation')
    if answer.get('accepted') is not True or not isinstance(operation, dict) or not operation.get('job_id'):
        raise RuntimeIntegrationError('Runtime did not confirm background install job.')
    return operation


def rollback_backend(endpoint, family, *, confirmed=False):
    if not confirmed:
        raise RuntimeIntegrationError('Explicit user consent is required.')
    if family not in FAMILIES:
        raise RuntimeIntegrationError('Unsupported backend family.')
    endpoint = validate_endpoint(endpoint)
    _require_1_0(endpoint)
    return _post(endpoint, f'/v1/runtime/{family}/rollback', {})


def wait_install(endpoint, family, job_id, *, interval=1.5, timeout=1800,
                 progress=None, sleeper=time.sleep, clock=time.monotonic):
    if family not in FAMILIES or not isinstance(job_id, str) or not job_id:
        raise RuntimeIntegrationError('Invalid install job.')
    endpoint = validate_endpoint(endpoint)
    deadline = clock() + timeout
    while clock() <= deadline:
        status = _read_json(endpoint, f'/v1/runtime/{family}/status', 10)
        operation = status.get('operation') if isinstance(status, dict) else None
        if not isinstance(operation, dict) or operation.get('job_id') != job_id:
            raise RuntimeIntegrationError('Backend install job identity changed.')
        state = operation.get('state')
        if progress:
            progress(operation)
        if state == 'success':
            return status
        if state == 'error':
            raise RuntimeIntegrationError('Backend installation failed: ' + str(operation.get('error')))
        if state != 'running':
            raise RuntimeIntegrationError('Unexpected backend install state: ' + str(state))
        sleeper(interval)
    raise RuntimeIntegrationError('Backend install still running; refresh status before retrying.')
