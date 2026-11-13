"""SnapMark's user-configurable OCR model client for local Ollama.

No Local AI Runtime, GPU toolkit installer, translation engine or extra Python
packages. All screenshot requests are restricted to an HTTP loopback address.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_MODEL = 'seriouswebby/paddleocr-vl-1.6:spotting'
BASE_URL = 'http://127.0.0.1:11434'
DEFAULT_PROMPT = 'OCR:'
DEFAULT_KEEP_ALIVE_SECONDS = 300
MAX_KEEP_ALIVE_SECONDS = 86400
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MODEL_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-/]*(?::[a-zA-Z0-9_.\-]+)?$')


class OllamaError(RuntimeError):
    """User-visible failure that should never silently fall back to cloud AI."""


def validate_model_name(model: str) -> str:
    if (not isinstance(model, str) or len(model) > 160 or not MODEL_RE.fullmatch(model)
            or '..' in model or '//' in model or model.endswith(('/', ':'))):
        raise OllamaError('Invalid Ollama model name')
    return model


def validate_hidden_models(models) -> list[str]:
    if not isinstance(models, list) or len(models) > 200:
        raise OllamaError('Invalid hidden OCR models')
    result = []
    for name in models:
        name = validate_model_name(name)
        if name not in result:
            result.append(name)
    return result


def detect_model_folder(directory: str | Path) -> dict:
    """Inspect a folder without guessing among ambiguous multimodal GGUF sets.

    A folder containing a single main GGUF and a uniquely named mmproj GGUF
    is supported. Otherwise a Modelfile may be used if present. We never
    import a random first GGUF from a directory with multiple candidates.
    """
    folder = Path(directory).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise OllamaError('Choose an OCR model directory')
    files = sorted((p for p in folder.iterdir() if p.is_file() and
                    p.suffix.casefold() == '.gguf'), key=lambda x: x.name.casefold())
    projector = [p for p in files if any(key in p.name.casefold() for key in
                 ('mmproj', 'projector', 'vision-proj', 'vision_proj'))]
    main = [p for p in files if p not in projector]
    if len(main) == 1 and len(projector) <= 1:
        return {'mode': 'gguf', 'main': main[0],
                'projector': projector[0] if projector else None,
                'folder': folder}
    if (folder / 'Modelfile').is_file():
        return {'mode': 'modelfile', 'folder': folder, 'main': None, 'projector': None}
    if not files:
        raise OllamaError('No GGUF files or Modelfile found in the selected directory')
    raise OllamaError('Ambiguous GGUF files: keep one main GGUF and at most one mmproj GGUF, '
                      'or provide a compatible Modelfile')


def validate_keep_alive(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_KEEP_ALIVE_SECONDS:
        raise OllamaError(f'Model retention must be 0–{MAX_KEEP_ALIVE_SECONDS} seconds')
    return value


def validate_base_url(value: str) -> str:
    """Protect private screenshots from accidental remote Ollama endpoints."""
    if not isinstance(value, str):
        raise OllamaError('Invalid Ollama address')
    parts = urlsplit(value.strip())
    if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise OllamaError('Ollama must use the local loopback HTTP service')
    if parts.username or parts.password or parts.path not in ('', '/') or parts.query or parts.fragment:
        raise OllamaError('Invalid Ollama service address')
    try:
        port = parts.port
    except ValueError as exc:
        raise OllamaError('Invalid Ollama TCP port') from exc
    if port is None or not (1 <= port <= 65535):
        raise OllamaError('Ollama URL must include a TCP port')
    return value.strip().rstrip('/')


def settings_file() -> Path:
    xdg = os.environ.get('XDG_CONFIG_HOME', '').strip()
    base = Path(xdg).expanduser() if xdg and Path(xdg).is_absolute() else Path.home() / '.config'
    return base / 'snapmark' / 'ocr.json'


def load_ocr_settings() -> dict:
    """Load SnapMark-only preferences, never edit Ollama's global configuration."""
    config = {'model': '', 'keep_alive_seconds': DEFAULT_KEEP_ALIVE_SECONDS,
              'prompt': DEFAULT_PROMPT, 'hidden_models': []}
    path = settings_file()
    try:
        if not path.exists():
            return config
        if path.stat().st_size > 32_768:
            return config
        saved = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(saved, dict):
            return config
        if isinstance(saved.get('model'), str):
            try:
                config['model'] = (validate_model_name(saved['model'])
                                   if saved['model'] else '')
            except OllamaError:
                pass
        if isinstance(saved.get('keep_alive_seconds'), int):
            try:
                config['keep_alive_seconds'] = validate_keep_alive(saved['keep_alive_seconds'])
            except OllamaError:
                pass
        if isinstance(saved.get('prompt'), str) and 0 < len(saved['prompt']) <= 2048:
            config['prompt'] = saved['prompt']
        if isinstance(saved.get('hidden_models'), list):
            try:
                config['hidden_models'] = validate_hidden_models(saved['hidden_models'])
            except OllamaError:
                pass
    except (OSError, UnicodeError, ValueError, TypeError):
        pass
    return config


def save_ocr_settings(**changes) -> dict:
    """Validate and atomically save only known keys; don't touch other applications."""
    current = load_ocr_settings()
    for key, value in changes.items():
        if key == 'model':
            current[key] = validate_model_name(value) if value else ''
        elif key == 'keep_alive_seconds':
            current[key] = validate_keep_alive(value)
        elif key == 'prompt':
            if not isinstance(value, str) or not 0 < len(value) <= 2048:
                raise OllamaError('OCR prompt must be 1–2048 characters')
            current[key] = value
        elif key == 'hidden_models':
            current[key] = validate_hidden_models(value)
        else:
            raise OllamaError(f'Unknown OCR setting: {key}')
    path = settings_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.ocr-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return current


class OllamaOCR:
    def __init__(self, base_url: str = BASE_URL, model: str | None = None,
                 keep_alive_seconds: int | None = None, prompt: str | None = None):
        config = load_ocr_settings()
        self.base_url = validate_base_url(base_url)
        chosen = model if model is not None else config['model']
        self.model = validate_model_name(chosen) if chosen else ''
        self.keep_alive_seconds = validate_keep_alive(
            keep_alive_seconds if keep_alive_seconds is not None else config['keep_alive_seconds'])
        self.prompt = prompt if prompt is not None else config['prompt']
        if not isinstance(self.prompt, str) or not 0 < len(self.prompt) <= 2048:
            raise OllamaError('Invalid OCR prompt')
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, route: str, payload=None, timeout: float = 20):
        headers = {'Accept': 'application/json'}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base_url + route, data=data, headers=headers,
                                     method='DELETE' if route == '/api/delete' else None)
        try:
            return self._opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.reason
            try:
                detail = exc.read(2048).decode('utf-8', 'replace')
            except Exception:
                pass
            raise OllamaError(f'Ollama HTTP {exc.code}: {detail}') from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise OllamaError(f'Cannot reach local Ollama at {self.base_url}: {exc}') from exc

    def status(self) -> str:
        with self._request('/api/version') as response:
            result = json.load(response)
        return str(result.get('version') or 'unknown')

    def models(self) -> list[str]:
        with self._request('/api/tags') as response:
            payload = json.load(response)
        found = payload.get('models', [])
        if not isinstance(found, list):
            raise OllamaError('Invalid /api/tags response')
        return [str(item['name']) for item in found if isinstance(item, dict) and item.get('name')]

    def model_capabilities(self, model: str) -> list[str]:
        with self._request('/api/show', {'model': validate_model_name(model)}) as response:
            data = json.load(response)
        caps = data.get('capabilities', [])
        return [str(c) for c in caps] if isinstance(caps, list) else []

    def vision_models(self) -> list[str]:
        """Prefer actual Ollama vision metadata; also list known PaddleOCR builds.

        /api/show on older Ollama releases may lack capabilities. Such models
        remain testable; a user who imports a Modelfile should validate OCR.
        """
        found = []
        for name in self.models():
            if 'paddleocr' in name.lower():
                found.append(name)
                continue
            try:
                if 'vision' in self.model_capabilities(name):
                    found.append(name)
            except OllamaError:
                continue
        return sorted(set(found), key=str.casefold)

    def is_installed(self) -> bool:
        return bool(self.model) and self.model in self.models()

    def recognize(self, image_png: bytes, *, cancelled: Callable[[], bool] | None = None) -> Iterator[str]:
        if not self.model:
            raise OllamaError('No OCR model enabled. Open Preferences → OCR to enable one.')
        if not isinstance(image_png, bytes) or not image_png.startswith(b'\x89PNG\r\n\x1a\n'):
            raise OllamaError('Expected a PNG screenshot')
        if len(image_png) > MAX_IMAGE_BYTES:
            raise OllamaError('Screenshot is too large (32 MiB maximum)')
        payload = {
            'model': self.model,
            'prompt': self.prompt,
            'images': [base64.b64encode(image_png).decode('ascii')],
            'stream': True,
            'options': {'temperature': 0},
            'keep_alive': self.keep_alive_seconds,
        }
        with self._request('/api/generate', payload, timeout=240) as response:
            total = 0
            for line in response:
                if cancelled is not None and cancelled():
                    return
                total += len(line)
                if total > MAX_RESPONSE_BYTES:
                    raise OllamaError('OCR response exceeds 2 MiB')
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise OllamaError('Invalid Ollama streaming response') from exc
                if event.get('error'):
                    raise OllamaError(str(event['error']))
                chunk = event.get('response', '')
                if not isinstance(chunk, str):
                    raise OllamaError('Invalid OCR text fragment')
                if chunk:
                    yield chunk
                if event.get('done') is True:
                    return
            raise OllamaError('Ollama ended the stream without a completion marker')

    def pull(self, model: str | None = None, *, on_status: Callable[[str], None] | None = None):
        """Explicit pull only; no delete or overwrite of other local models."""
        name = validate_model_name(model or DEFAULT_MODEL)
        with self._request('/api/pull', {'model': name, 'stream': True}, timeout=900) as response:
            for line in response:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get('error'):
                    raise OllamaError(str(event['error']))
                progress = str(event.get('status') or '')
                total, done = event.get('total'), event.get('completed')
                if isinstance(total, (int, float)) and total > 0 and isinstance(done, (int, float)):
                    progress += f' {min(100, max(0, 100*done/total)):.1f}%'
                if on_status and progress:
                    on_status(progress)
                if event.get('status') == 'success':
                    return
            raise OllamaError('Model download ended without success')

    def delete_model(self, model: str) -> None:
        """Ollama-owned model deletion; never remove original user GGUF files.

        Ollama blobs may be shared with other models. Let Ollama manage its
        references, and only call this after explicit destructive confirmation.
        """
        name = validate_model_name(model)
        if name not in self.models():
            raise OllamaError('Model not found in Ollama')
        with self._request('/api/delete', {'model': name}, timeout=120) as response:
            # Ollama returns HTTP 200 even when the body is empty.
            response.read(4096)

    def import_model_folder(self, folder: str | Path, name: str,
                            *, on_status: Callable[[str], None] | None = None) -> str:
        selection = detect_model_folder(folder)
        if selection['mode'] == 'modelfile':
            return self.import_model_directory(selection['folder'], name)
        return self.import_model_files(selection['main'], selection['projector'],
                                       name, on_status=on_status)

    def _ensure_new_model_name(self, name: str) -> str:
        name = validate_model_name(name)
        def canonical(model_name):
            # Ollama omits :latest in user input but /api/tags returns it.
            # Treat those aliases as identical to prevent accidental overwrite.
            item = model_name.casefold()
            return item if ':' in item.rsplit('/', 1)[-1] else item + ':latest'
        if canonical(name) in {canonical(item) for item in self.models()}:
            raise OllamaError('Model name already exists in Ollama; choose a new name to protect other applications')
        return name

    def _upload_gguf(self, path: Path, on_status: Callable[[str], None] | None = None) -> str:
        """Stream a GGUF file in small blocks into Ollama's content-addressed store.

        Never load a gigabyte model into Python RAM or delete any existing blob.
        Ollama may duplicate the model in its own store; original files remain intact.
        """
        if not path.is_file() or path.suffix.casefold() != '.gguf' or path.stat().st_size < 8:
            raise OllamaError(f'Expected a nonempty GGUF file: {path}')
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(block)
        key = 'sha256:' + digest.hexdigest()
        target = '/api/blobs/' + key
        from urllib.parse import urlsplit
        parts = urlsplit(self.base_url)
        if on_status:
            on_status(f'Checking {path.name}')
        conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=90)
        try:
            conn.request('HEAD', target)
            resp = conn.getresponse()
            resp.read()
            exists = resp.status == 200
            if not exists and resp.status != 404:
                raise OllamaError(f'Ollama blob check returned HTTP {resp.status}')
        except (OSError, http.client.HTTPException) as exc:
            raise OllamaError(f'Cannot access Ollama blob storage: {exc}') from exc
        finally:
            conn.close()
        if exists:
            return key
        conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=300)
        try:
            conn.putrequest('PUT', target)
            conn.putheader('Content-Type', 'application/octet-stream')
            conn.putheader('Content-Length', str(size))
            conn.endheaders()
            sent = 0
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    conn.send(block)
                    sent += len(block)
                    if on_status:
                        on_status(f'{path.name}: {sent * 100 // size}%')
            resp = conn.getresponse()
            detail = resp.read(8192)
            if resp.status not in (200, 201):
                raise OllamaError(f'Cannot upload GGUF: HTTP {resp.status}: {detail.decode("utf-8", "replace")}')
        except (OSError, http.client.HTTPException) as exc:
            raise OllamaError(f'GGUF upload failed: {exc}') from exc
        finally:
            conn.close()
        return key

    def _create_from_files(self, name: str, files: dict[str, str],
                           on_status: Callable[[str], None] | None = None) -> str:
        with self._request('/api/create', {'model': name, 'files': files, 'stream': True}, timeout=1800) as response:
            ok = False
            for line in response:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get('error'):
                    raise OllamaError(str(event['error']))
                if on_status and event.get('status'):
                    on_status(str(event['status']))
                if event.get('status') == 'success':
                    ok = True
            if not ok:
                raise OllamaError('Ollama model import did not finish successfully')
        self._verify_vision(name)
        return name

    def _verify_vision(self, name: str):
        """Validate that Ollama reports an actual multimodal model.

        This is not an OCR accuracy test. Some GGUF/mmproj pairs are still
        unsupported by Ollama even after successful blob upload.
        """
        try:
            caps = self.model_capabilities(name)
        except OllamaError as exc:
            raise OllamaError(f'Imported {name}, but could not check vision capability: {exc}') from exc
        if 'vision' not in caps:
            raise OllamaError(
                f'Imported {name}, but Ollama did not report vision capability. '
                'Not selected for OCR; please check the model format and projector compatibility.')

    def import_model_files(self, main_file: str | Path, projector_file: str | Path | None,
                           name: str, *, on_status: Callable[[str], None] | None = None) -> str:
        """Allow two distinct file selections, not a fixed OCR model path.

        For separate mmproj files the current Ollama GGUF import API accepts
        multiple files, but compatibility depends on their architecture. We
        verify capabilities and never switch to a text-only import.
        """
        name = self._ensure_new_model_name(name)
        main = Path(main_file).expanduser().resolve(strict=True)
        pairs = [main]
        if projector_file:
            projector = Path(projector_file).expanduser().resolve(strict=True)
            if projector == main or projector.name == main.name:
                raise OllamaError('Model GGUF and mmproj GGUF must be different files and names')
            pairs.append(projector)
        payload = {path.name: self._upload_gguf(path, on_status) for path in pairs}
        return self._create_from_files(name, payload, on_status)

    def import_model_directory(self, directory: str | Path, name: str) -> str:
        """Import an existing compatible Modelfile folder using the Ollama CLI."""
        name = self._ensure_new_model_name(name)
        folder = Path(directory).expanduser().resolve(strict=True)
        if not folder.is_dir():
            raise OllamaError('Choose a model folder, not a file')
        file = folder / 'Modelfile'
        if not file.is_file():
            raise OllamaError('Folder must contain an Ollama-compatible Modelfile. '
                              'Or choose main GGUF and mmproj separately in SnapMark.')
        cli = shutil.which('ollama')
        if not cli:
            raise OllamaError('The Ollama CLI is needed to import a local Modelfile')
        env = os.environ.copy()
        parts = urlsplit(self.base_url)
        host = f'[{parts.hostname}]' if ':' in parts.hostname else parts.hostname
        env['OLLAMA_HOST'] = f'{host}:{parts.port}'
        env['NO_PROXY'] = '127.0.0.1,localhost,::1'
        try:
            result = subprocess.run([cli, 'create', name, '-f', str(file)], cwd=folder,
                                    env=env, capture_output=True, text=True, timeout=1800,
                                    check=False)
        except subprocess.TimeoutExpired as exc:
            raise OllamaError('Local model import timed out after 30 minutes') from exc
        if result.returncode:
            raise OllamaError('Ollama import failed: ' + (result.stderr or result.stdout)[-1600:].strip())
        self._verify_vision(name)
        return name
