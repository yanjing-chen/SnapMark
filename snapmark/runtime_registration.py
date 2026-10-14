"""Opt-in, loopback-only custom GGUF registration for Local AI Runtime 0.8.x.

Inspection is non-mutating, although Runtime exposes it via POST. Registry
writes happen *only* after explicit confirmation in the SnapMark GUI. Model
files are never copied, downloaded or modified by this module.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .ai_runtime import RuntimeIntegrationError, validate_endpoint, MAX_RESPONSE_BYTES
from .model_bundle import ModelBundle

ID_FORMAT = re.compile(r'^[a-z0-9][a-z0-9._-]{0,63}$')
SUPPORTED_TYPES = frozenset({'chat', 'vision', 'ocr', 'translation'})


@dataclass(frozen=True)
class RegistrationReview:
    endpoint: str
    payload: dict
    notes: tuple[str, ...]
    # Snapshot to reject file substitution between inspection and registration.
    files: tuple[tuple[str, int, int], ...]


# Do not send a filesystem path to a remote host. A remote Runtime cannot
# necessarily access that path and doing so could expose private information.
def _local_endpoint(endpoint: str) -> str:
    endpoint = validate_endpoint(endpoint)
    split = urlsplit(endpoint)
    if split.scheme != 'http' or split.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeIntegrationError('Local model registration requires a loopback HTTP Runtime.')
    return endpoint


def _json_request(endpoint: str, route: str, *, payload=None, method='GET', timeout=10.0) -> dict:
    endpoint = _local_endpoint(endpoint)
    headers = {'Accept': 'application/json', 'User-Agent': 'SnapMark/0.6-registration'}
    if method == 'POST':
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        data = None
    request = Request(endpoint + route, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status not in (200, 201):
                raise RuntimeIntegrationError(f'{route}: unexpected HTTP {response.status}')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        reason = exc.read(512).decode('utf-8', errors='replace')
        raise RuntimeIntegrationError(f'{route}: HTTP {exc.code} {reason}') from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise RuntimeIntegrationError(f'{route}: {exc}') from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeIntegrationError(f'{route}: response too large')
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeIntegrationError(f'{route}: invalid JSON') from exc
    if not isinstance(result, dict):
        raise RuntimeIntegrationError(f'{route}: expected JSON object')
    return result


def _files_snapshot(bundle: ModelBundle) -> tuple[tuple[str, int, int], ...]:
    paths = [bundle.main, *bundle.projectors]
    snapshot = []
    for value in paths:
        if value is None:
            continue
        path = Path(value).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != '.gguf':
            raise RuntimeIntegrationError('Only existing local GGUF files can be registered.')
        stats = path.stat()
        snapshot.append((str(path), stats.st_size, stats.st_mtime_ns))
    return tuple(snapshot)


def _validate_bundle(bundle: ModelBundle) -> None:
    if not bundle.ready_for_review or bundle.main is None:
        raise RuntimeIntegrationError('Model files are incomplete or ambiguous.')
    if bundle.shards:
        raise RuntimeIntegrationError('Split GGUF registration awaits Runtime compatibility verification.')
    if len(bundle.projectors) > 1:
        raise RuntimeIntegrationError('Choose exactly one matching mmproj.')
    if any('may require an mmproj' in warning.lower() for warning in bundle.warnings):
        raise RuntimeIntegrationError('A projector might be missing; review the model files first.')


def _ids(endpoint: str) -> set[str]:
    ids = set()
    for route in ('/v1/models/custom', '/v1/models?refresh=1'):
        listing = _json_request(endpoint, route)
        data = listing.get('data')
        if not isinstance(data, list):
            raise RuntimeIntegrationError(f'{route}: invalid model list; refusing to write')
        ids.update(str(item['id']) for item in data if isinstance(item, dict) and isinstance(item.get('id'), str))
    return ids


def inspect_registration(endpoint: str, bundle: ModelBundle) -> RegistrationReview:
    """Call Runtime's *non-mutating* inspector and prepare a human-readable proposal."""
    _validate_bundle(bundle)
    endpoint = _local_endpoint(endpoint)
    paths = _files_snapshot(bundle)
    main = paths[0][0]
    mmproj = paths[1][0] if len(paths) > 1 else ''
    response = _json_request(endpoint, '/v1/models/inspect', method='POST', payload={
        'model_path': main, 'mmproj_path': mmproj, 'auto_match_mmproj': False})
    if response.get('object') != 'gguf.inspection' or not isinstance(response.get('suggested'), dict):
        raise RuntimeIntegrationError('Runtime did not return a supported GGUF inspection result.')
    suggestion = response['suggested']
    model_id = suggestion.get('id')
    if not isinstance(model_id, str) or not ID_FORMAT.fullmatch(model_id):
        raise RuntimeIntegrationError('Runtime suggested an invalid model ID.')
    model_type = suggestion.get('type')
    if model_type not in SUPPORTED_TYPES:
        raise RuntimeIntegrationError('Runtime suggested an unsupported model purpose.')
    capabilities = suggestion.get('capabilities')
    if not isinstance(capabilities, dict) or any(not isinstance(k, str) or type(v) is not bool
                                                   for k, v in capabilities.items()):
        raise RuntimeIntegrationError('Runtime suggested invalid model capabilities.')
    if model_id in _ids(endpoint):
        raise RuntimeIntegrationError(f'Model ID {model_id} is already registered. This tool never overwrites it.')
    # Keep fields suggested by the model inspector; the Runtime validates the
    # complete payload again when a user explicitly requests registration.
    payload = {
        'id': model_id,
        'display_name': str(suggestion.get('display_name') or bundle.name),
        'type': model_type,
        'model_path': main,
        'mmproj_path': mmproj,
        'context_size': suggestion.get('context_size', 4096),
        'gpu_layers': suggestion.get('gpu_layers', 0),
        'default_prompt': str(suggestion.get('default_prompt', '')),
        'capabilities': capabilities,
    }
    if (type(payload['context_size']) is not int or payload['context_size'] < 1 or
            type(payload['gpu_layers']) is not int or payload['gpu_layers'] < 0):
        raise RuntimeIntegrationError('Runtime suggested invalid model resource settings.')
    details = tuple(str(w) for w in response.get('warnings', []) if isinstance(w, str))
    return RegistrationReview(endpoint, payload, details, paths)


def register_reviewed_model(review: RegistrationReview, *, confirmed: bool = False) -> dict:
    """Do not write unless user explicitly confirmed after inspecting this proposal."""
    if not confirmed:
        raise RuntimeIntegrationError('Registration requires explicit user confirmation.')
    for path, size, modified in review.files:
        try:
            s = Path(path).stat()
        except OSError as exc:
            raise RuntimeIntegrationError(f'Model file unavailable: {path}') from exc
        if (s.st_size, s.st_mtime_ns) != (size, modified):
            raise RuntimeIntegrationError('Model files changed after inspection; inspect again.')
    if review.payload['id'] in _ids(review.endpoint):
        raise RuntimeIntegrationError('Model ID was registered while this dialog was open; refusing to overwrite.')
    status = _json_request(review.endpoint, '/v1/models/custom', method='POST', payload=review.payload)
    if status.get('id') != review.payload['id'] or status.get('source') != 'custom':
        raise RuntimeIntegrationError('Runtime response did not confirm the expected custom model.')
    return status
