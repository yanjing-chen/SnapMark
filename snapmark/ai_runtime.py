"""Read-only client for a *separate*, user-managed Local AI Runtime service.

No model downloads, subprocess execution, service control or backend overrides.
The integration toggle is SnapMark-only; disabling never stops Runtime.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT = 'http://127.0.0.1:8111'
RUNTIME_PROJECT = 'https://github.com/yanjing-chen/local-ai-runtime'
RUNTIME_RELEASES = RUNTIME_PROJECT + '/releases'
BACKEND_PREFERENCES = ('auto', 'cpu', 'vulkan', 'cuda')
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class RuntimeIntegrationError(Exception):
    pass


def validate_endpoint(value: str) -> str:
    """Accept base URLs only; never silently add paths or credentials."""
    if not isinstance(value, str):
        raise RuntimeIntegrationError('Endpoint must be a URL.')
    value = value.strip().rstrip('/')
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname
    except ValueError as exc:
        raise RuntimeIntegrationError('Invalid endpoint URL or port.') from exc
    if (parsed.scheme not in ('http', 'https') or not host or
            parsed.username is not None or parsed.password is not None or
            parsed.path or parsed.query or parsed.fragment or
            port is None or not (1 <= port <= 65535)):
        raise RuntimeIntegrationError('Enter a base URL such as http://127.0.0.1:8111 (no path).')
    return value


class RuntimeSettings:
    """Only SnapMark integration preferences; NOT Runtime configuration."""
    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
        self.path = Path(path) if path is not None else base / 'snapmark' / 'ai-runtime.json'

    def load(self) -> dict:
        defaults = {'enabled': False, 'endpoint': DEFAULT_ENDPOINT, 'backend_preference': 'auto'}
        if not self.path.is_file():
            return defaults
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(raw, dict):
                raise ValueError('Settings must be an object')
            settings = dict(defaults)
            if type(raw.get('enabled')) is bool:
                settings['enabled'] = raw['enabled']
            if isinstance(raw.get('endpoint'), str):
                settings['endpoint'] = validate_endpoint(raw['endpoint'])
            if raw.get('backend_preference') in BACKEND_PREFERENCES:
                settings['backend_preference'] = raw['backend_preference']
            return settings
        except (OSError, ValueError, RuntimeIntegrationError, json.JSONDecodeError):
            # Fail closed: corrupt settings must not automatically connect.
            return defaults

    def update(self, **changes) -> dict:
        allowed = {'enabled', 'endpoint', 'backend_preference'}
        if not changes.keys() <= allowed:
            raise RuntimeIntegrationError('Unknown AI Runtime setting.')
        old = self.load()
        new = dict(old, **changes)
        if type(new['enabled']) is not bool:
            raise RuntimeIntegrationError('Enabled must be true or false.')
        new['endpoint'] = validate_endpoint(new['endpoint'])
        if new['backend_preference'] not in BACKEND_PREFERENCES:
            raise RuntimeIntegrationError('Unsupported backend preference.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.ai-runtime-', suffix='.tmp', dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump({'schema_version': 1, **new}, output, indent=2)
                output.write('\n')
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return new


def _read_json(endpoint: str, route: str, timeout: float) -> object:
    address = validate_endpoint(endpoint) + route
    request = Request(address, headers={'Accept': 'application/json',
                                        'User-Agent': 'SnapMark/0.6-runtime-integration'}, method='GET')
    try:
        with urlopen(request, timeout=timeout) as reply:
            if reply.status != 200:
                raise RuntimeIntegrationError(f'HTTP {reply.status} at {route}.')
            data = reply.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeIntegrationError(f'{route}: {exc}') from exc
    if len(data) > MAX_RESPONSE_BYTES:
        raise RuntimeIntegrationError(f'{route}: response too large.')
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeIntegrationError(f'{route}: invalid JSON response.') from exc


def _stringify_backend(value):
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        # The Runtime API can evolve; never guess a GPU solely from host hardware.
        for name in ('effective_backend', 'effective', 'active', 'selected', 'backend', 'name'):
            if isinstance(value.get(name), str) and value[name]:
                return value[name]
    return 'Not reported by Runtime'


@dataclass(frozen=True)
class RuntimeModel:
    identifier: str
    installed: bool | None
    capabilities: tuple[str, ...] = ()
    operation: str = ''


@dataclass(frozen=True)
class RuntimeSnapshot:
    endpoint: str
    health: str
    backend: str
    models: tuple[str, ...]
    backend_error: str = ''
    models_error: str = ''
    version: str = ''
    configured_backend: str = ''
    active_backend: str = ''
    backend_running: bool = False
    current_model: str = ''
    detailed_models: tuple[RuntimeModel, ...] = ()
    preload_enabled: bool | None = None
    preload_model: str = ''
    preload_state: str = ''
    idle_unload_seconds: int | None = None


def probe_runtime(endpoint: str = DEFAULT_ENDPOINT, *, timeout: float = 3.0) -> RuntimeSnapshot:
    """Probe only GET endpoints. Backends/models are best effort after /health."""
    endpoint = validate_endpoint(endpoint)
    health = _read_json(endpoint, '/health', timeout)
    if not isinstance(health, dict):
        raise RuntimeIntegrationError('Unexpected /health response.')
    status = str(health.get('status', 'connected'))
    if status.lower() in ('error', 'failed', 'unhealthy'):
        raise RuntimeIntegrationError(f'Runtime health: {status}')
    backend = 'Not reported by Runtime'
    backend_error = ''
    try:
        backends = _read_json(endpoint, '/v1/runtime/backends', timeout)
        if isinstance(backends, dict):
            backend = _stringify_backend(backends)
            if backend == 'Not reported by Runtime':
                for key in ('runtime', 'backend_status', 'current_backend'):
                    if key in backends:
                        backend = _stringify_backend(backends[key])
                        if backend != 'Not reported by Runtime':
                            break
    except RuntimeIntegrationError as exc:
        backend_error = str(exc)
    models = []
    detailed_models = []
    models_error = ''
    try:
        listing = _read_json(endpoint, '/v1/models?refresh=1', timeout)
        if not isinstance(listing, dict):
            raise RuntimeIntegrationError('Unexpected models response.')
        entries = listing.get('data', listing.get('models', []))
        if not isinstance(entries, list):
            raise RuntimeIntegrationError('Model list is not an array.')
        for item in entries:
            if isinstance(item, dict):
                identifier = item.get('id') or item.get('name')
                if isinstance(identifier, str) and identifier.strip():
                    identifier = identifier.strip()
                    if identifier not in models:
                        models.append(identifier)
                        installed = item.get('installed')
                        if type(installed) is not bool:
                            installed = None
                        caps = item.get('capabilities')
                        supported = tuple(k for k, enabled in caps.items()
                                          if enabled is True) if isinstance(caps, dict) else ()
                        operation = item.get('operation')
                        operation = str(operation.get('state', '')) if isinstance(operation, dict) else ''
                        detailed_models.append(RuntimeModel(identifier, installed, supported, operation))
    except RuntimeIntegrationError as exc:
        models_error = str(exc)
    # /health is authoritative for the *active* backend. A backend choice
    # returned from /v1/runtime/backends is not proof inference is running.
    running = health.get('backend_running') is True
    active = health.get('active_backend') if running else None
    active = active.strip() if isinstance(active, str) and active.strip() else ''
    loaded = health.get('current_model') if running else None
    loaded = loaded.strip() if isinstance(loaded, str) and loaded.strip() else ''
    preference = health.get('backend_preference')
    preference = preference if preference in BACKEND_PREFERENCES else ''
    version = health.get('runtime_version')
    version = version if isinstance(version, str) else ''
    # Only /health is authoritative for these life-cycle settings.  Booleans
    # must not be treated as integer seconds, and missing data is UNKNOWN,
    # rather than silently claiming that startup preload is disabled.
    preload = health.get('startup_preload')
    preload_enabled = None
    preload_model = ''
    preload_state = ''
    if isinstance(preload, dict):
        flag = preload.get('enabled')
        if type(flag) is bool:
            preload_enabled = flag
        name = preload.get('model')
        if isinstance(name, str):
            preload_model = name.strip()
        state = preload.get('state')
        if isinstance(state, str):
            preload_state = state.strip()
    idle = health.get('idle_unload_seconds')
    # Preserve '0' exactly as a Runtime value: its semantics are determined
    # by the Runtime, and should not be assumed to mean "immediately".
    if type(idle) is not int or idle < 0:
        idle = None
    return RuntimeSnapshot(endpoint, status, backend, tuple(models),
                           backend_error, models_error, version, preference,
                           active, running, loaded, tuple(detailed_models),
                           preload_enabled, preload_model, preload_state, idle)


def describe_preload(snapshot: RuntimeSnapshot) -> str:
    """Human-visible state without triggering a preload or changing the service."""
    if snapshot.preload_enabled is False:
        return 'Disabled · load when requested'
    if snapshot.preload_enabled is True:
        model = snapshot.preload_model or 'model not specified'
        return 'Enabled · ' + model
    return 'Not reported by Runtime'


def describe_idle_unload(snapshot: RuntimeSnapshot) -> str:
    """Summarize exactly the idle value from /health; no guessed semantics."""
    seconds = snapshot.idle_unload_seconds
    if seconds is None:
        return 'Not reported by Runtime'
    if seconds == 0:
        return '0 seconds (Runtime-defined behavior)'
    if seconds % 3600 == 0:
        return f'{seconds // 3600} hour(s) ({seconds} seconds)'
    if seconds % 60 == 0:
        return f'{seconds // 60} minute(s) ({seconds} seconds)'
    return f'{seconds} seconds'
