"""User-confirmed and isolated PaddleOCR 3.7 / PP-OCRv6 small setup.

No download, installation or registry write at import-time.
Only published official PaddlePaddle model artifacts are accepted.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ENGINE = ('paddlepaddle==3.3.1', 'paddleocr==3.7.0')
PAIR = 'PP-OCRv6 small'
COMPONENTS = {
    'PP-OCRv6_small_det': {
        'repo': 'PaddlePaddle/PP-OCRv6_small_det', 'rev': '680833b',
        'sha256': '5043d4ccc8d63402ccea8feefcee4db57077431a873e78d2191836a178a492da',
    },
    'PP-OCRv6_small_rec': {
        'repo': 'PaddlePaddle/PP-OCRv6_small_rec', 'rev': '728113c',
        'sha256': '406e1e689c9a7fbb04178007a3fe10cf852afe7bf8bb3bc6dbb9d532b13bd907',
    },
}
MODEL_FILES = ('inference.json', 'inference.pdiparams', 'inference.yml')


def _private_path(path: str, base: Path, purpose: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute() or p.is_symlink() or p.resolve() != base.resolve():
        raise ValueError(f'{purpose} must use the managed SnapMark location: {base}')
    return p


def _run(args, timeout=900):
    cp = subprocess.run(args, check=False, capture_output=True, text=True,
                        stdin=subprocess.DEVNULL, timeout=timeout)
    if cp.returncode:
        error = (cp.stderr or cp.stdout or 'Installation failed')[-3500:]
        raise RuntimeError(error)
    return (cp.stdout or '')[-3000:]


def engine_status(python: str) -> str:
    p = Path(python)
    if not p.is_file() or not os.access(p, os.X_OK):
        return 'Python environment missing'
    try:
        result = _run([str(p), '-c',
            'from importlib.metadata import version; '
            'print("PaddlePaddle " + version("paddlepaddle") + ", PaddleOCR " + version("paddleocr"))'], 10)
        return result.strip()
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return 'PaddleOCR engine not installed'


def install_engine(python: str, uv: str, *, confirmed=False) -> str:
    if not confirmed:
        raise PermissionError('Explicit user confirmation is required')
    home = Path.home()
    expected = home / '.local/share/snapmark/ocr-venv/bin/python'
    exe = _private_path(python, expected, 'OCR Python')
    uv_exe = _private_path(uv, home / '.local/bin/uv', 'uv installer')
    if not exe.is_file() or not os.access(exe, os.X_OK) or not uv_exe.is_file():
        raise FileNotFoundError('uv or independent OCR Python 3.12 is missing')
    result = _run([str(exe), '-c', 'import sys; assert sys.version_info[:2] == (3,12)'], 10)
    result = _run([str(uv_exe), 'pip', 'install', '--python', str(exe), *ENGINE], 1800)
    status = engine_status(str(exe))
    if 'PaddleOCR 3.7.0' not in status or 'PaddlePaddle 3.3.1' not in status:
        raise RuntimeError('Engine packages could not be verified after installation: ' + status)
    return status


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def model_installed(root: str) -> bool:
    base = Path(root)
    if not base.is_absolute() or not base.is_dir():
        return False
    try:
        for name, meta in COMPONENTS.items():
            folder = base / name
            if folder.is_symlink() or not folder.is_dir():
                return False
            for filename in MODEL_FILES:
                f = folder / filename
                if f.is_symlink() or not f.is_file() or f.stat().st_size < 100:
                    return False
            if _hash_file(folder / 'inference.pdiparams') != meta['sha256']:
                return False
        return True
    except OSError:
        return False


def _download(url: str, output: Path, *, expected=None, limit=48 * 1024 * 1024):
    # Only pinned official PaddlePaddle Hugging Face repositories; no caller URL.
    assert url.startswith('https://huggingface.co/PaddlePaddle/PP-OCRv6_small_')
    req = urllib.request.Request(url, headers={'User-Agent': 'SnapMark-C2B/1.0'})
    size = 0
    with urllib.request.urlopen(req, timeout=50) as response, output.open('xb') as sink:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError('Model file exceeds expected size')
            sink.write(chunk)
    if size < 100:
        raise ValueError('Model artifact unexpectedly small')
    if expected and _hash_file(output) != expected:
        raise ValueError('Official model SHA256 mismatch: ' + output.name)


def install_small(root: str, *, confirmed=False) -> str:
    if not confirmed:
        raise PermissionError('Explicit user confirmation is required')
    expected = Path.home() / '.local/share/snapmark/ocr-models'
    base = _private_path(root, expected, 'OCR models')
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if model_installed(str(base)):
        return 'PP-OCRv6 small already installed and verified'
    if any((base / name).exists() for name in COMPONENTS):
        raise FileExistsError('Existing model folders need manual inspection; no overwrite performed')
    # Downloads are quarantined until all weights, JSON and YAML pass checks.
    stage = Path(tempfile.mkdtemp(prefix='.snapmark-v6-small-', dir=base))
    try:
        for name, meta in COMPONENTS.items():
            folder = stage / name
            folder.mkdir(mode=0o700)
            for filename in MODEL_FILES:
                url = f"https://huggingface.co/{meta['repo']}/resolve/{meta['rev']}/{filename}"
                _download(url, folder / filename,
                          expected=meta['sha256'] if filename == 'inference.pdiparams' else None)
        if not model_installed(str(stage)):
            raise ValueError('Downloaded models failed validation')
        for name in COMPONENTS:
            os.replace(stage / name, base / name)
        return 'PP-OCRv6 small downloaded; detection and recognition weights verified'
    finally:
        shutil.rmtree(stage, ignore_errors=True)
