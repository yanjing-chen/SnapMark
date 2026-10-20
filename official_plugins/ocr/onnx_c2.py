"""C2-027 ONNX engine plus PaddlePaddle official-model integration (stdlib only).

Legacy C2-026 install stays for rollback; C2-027 OCR only uses model bytes
downloaded directly from official PaddlePaddle repositories.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

LABEL = 'PP-OCRv6 tiny (ONNX CPU)'
BASE = Path.home() / '下载' / 'SnapMark-C2-025-ONNX-portability-check'
ENGINE_SOURCE = BASE / 'engine' / 'ocr-onnx-linux-x86_64'
MODEL_SOURCE = BASE / 'model'
DET_SHA256 = '193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8'
REC_SHA256 = '9ef676d6ed3c88256a2d92c640c44f25b0c40947e111b14b8be8f594091563e6'

_official_spec = importlib.util.spec_from_file_location(
    __name__ + '_official_models', Path(__file__).with_name('official_models_c2.py'))
_official = importlib.util.module_from_spec(_official_spec)
_official_spec.loader.exec_module(_official)


def target_root():
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return data / 'snapmark' / 'ocr-onnx-v6-tiny'


def _digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _check_models(folder):
    folder = Path(folder)
    det, rec, dic = folder / 'det.onnx', folder / 'rec.onnx', folder / 'dict.txt'
    if not all(p.is_file() and not p.is_symlink() for p in (det, rec, dic)):
        raise ValueError('Missing or linked ONNX model/dictionary file')
    if _digest(det) != DET_SHA256 or _digest(rec) != REC_SHA256:
        raise ValueError('ONNX model SHA256 mismatch')
    raw = dic.read_bytes()
    chars = raw.decode('utf-8-sig').splitlines()
    if len(chars) != 6904 or not any(ch.strip() for ch in chars):
        raise ValueError('PP-OCRv6 tiny dictionary is invalid')
    return _digest(dic)


def _check_engine(folder, *, expected_worker=None):
    folder = Path(folder)
    node, worker = folder / 'node', folder / 'worker.cjs'
    if not (node.is_file() and worker.is_file() and
            os.access(node, os.X_OK) and (folder / 'node_modules').is_dir()):
        raise ValueError('Prebuilt ONNX engine is incomplete')
    if node.is_symlink() or worker.is_symlink():
        raise ValueError('ONNX engine files must not be symlinks')
    if expected_worker is not None and _digest(worker) != expected_worker:
        raise ValueError('Worker differs from the verified SnapMark source')
    return _digest(worker)


def verified_source_ready():
    """Safe for GTK thread; no execution and no writes."""
    try:
        return (ENGINE_SOURCE / 'node').is_file() and (ENGINE_SOURCE / 'worker.cjs').is_file() \
            and (MODEL_SOURCE / 'det.onnx').is_file() and (MODEL_SOURCE / 'rec.onnx').is_file() \
            and (MODEL_SOURCE / 'dict.txt').is_file() and \
            (BASE / 'artifact' / 'SHA256SUMS').is_file()
    except OSError:
        return False


def engine_ready():
    """Previously installed, GitHub-prebuilt CPU engine from C2-026."""
    target = target_root()
    manifest = target / 'install.json'
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('label') != LABEL or data.get('model_det_sha256') != DET_SHA256 or \
                data.get('model_rec_sha256') != REC_SHA256:
            return False
        e, m = target / 'engine', target / 'model'
        return ((e / 'node').is_file() and os.access(e / 'node', os.X_OK)
                and (e / 'worker.cjs').is_file()
                and (e / 'node_modules').is_dir()
                and all((m / n).is_file() for n in ('det.onnx', 'rec.onnx', 'dict.txt')))
    except (ValueError, OSError):
        return False


def official_models_ready():
    return _official.ready(target_root() / 'official-model')


def available_models():
    if not engine_ready(): return []
    return list(_official.installed(target_root()))


def installed_label(label):
    return engine_ready() and label in _official.installed(target_root())


def catalog_models():
    return _official.models()


def refresh_catalog():
    return _official.refresh_catalog()


def model_compatible(model):
    return _official.compatible(model)


def install_label(label, *, confirmed=False):
    if not confirmed: raise PermissionError('Explicit confirmation required')
    if not engine_ready():raise FileNotFoundError('Prebuilt ONNX engine not installed')
    entry=_official.by_label(label)
    if entry is None:raise ValueError('Model not present in official SnapMark catalog')
    if not _official.compatible(entry):raise ValueError('Model needs a newer OCR engine')
    destination=_official._candidate_paths(target_root(), entry['id'])
    return _official.install(destination,confirmed=True,model=entry)


def installed_ready():
    # Never run on models downloaded from the old third-party package.
    return engine_ready() and official_models_ready()


def download_official_models(*, confirmed=False):
    if not confirmed:
        raise PermissionError('Explicit confirmation is required')
    if not engine_ready():
        raise FileNotFoundError('Prebuilt ONNX CPU engine is missing; keep using OCR 0.1.8 until the engine is installed')
    return install_label(LABEL, confirmed=True)


def install_from_verified_stage(*, confirmed=False):
    if not confirmed:
        raise PermissionError('Explicit user confirmation required')
    if installed_ready():
        return 'Prebuilt PP-OCRv6 tiny ONNX engine is already installed'
    if not verified_source_ready():
        raise FileNotFoundError('C2-025 verified files not found. Run the portability check first.')

    # Validate the exact artifact previously tested, not an arbitrary host copy.
    bundle = BASE / 'artifact' / 'SnapMark-OCR-ONNX-linux-x86_64.tar.gz'
    sums = (BASE / 'artifact' / 'SHA256SUMS').read_text('ascii')
    lines = sums.splitlines()
    matches = [line for line in lines if line.endswith('  ' + bundle.name)]
    if len(matches) != 1 or not bundle.is_file() or _digest(bundle) != matches[0].split()[0]:
        raise ValueError('GitHub-built archive SHA256 verification failed')

    worker_sha = _check_engine(ENGINE_SOURCE)
    dict_sha = _check_models(MODEL_SOURCE)
    dest = target_root()
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if dest.exists():
        raise FileExistsError('OCR install destination already exists but is incomplete: ' + str(dest))

    # Leave existing configurations and all other SnapMark plugins untouched.
    temp = Path(tempfile.mkdtemp(prefix='.ocr-onnx-v6-tiny-', dir=dest.parent))
    try:
        needed = sum(f.stat().st_size for f in ENGINE_SOURCE.rglob('*') if f.is_file())
        if shutil.disk_usage(dest.parent).free < needed + 200 * 1024 * 1024:
            raise OSError('Insufficient disk space for verified ONNX engine')
        shutil.copytree(ENGINE_SOURCE, temp / 'engine', symlinks=False)
        shutil.copytree(MODEL_SOURCE, temp / 'model', symlinks=False)
        if _check_engine(temp / 'engine', expected_worker=worker_sha) != worker_sha:
            raise ValueError('Installed worker checksum mismatch')
        if _check_models(temp / 'model') != dict_sha:
            raise ValueError('Installed dictionary checksum mismatch')
        data = {
            'label': LABEL, 'model_det_sha256': DET_SHA256,
            'model_rec_sha256': REC_SHA256, 'dict_sha256': dict_sha,
            'worker_sha256': worker_sha, 'build_run': 38840611823,
            'source': 'Code01 C2-025 verified GitHub Actions bundle'
        }
        (temp / 'install.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        os.chmod(temp / 'install.json', 0o600)
        temp.rename(dest)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return 'PP-OCRv6 tiny ONNX CPU installed from the verified Code01 package'


def command(image, label=None):
    label=label or LABEL
    matches=_official.installed(target_root())
    if not engine_ready() or label not in matches:
        raise FileNotFoundError('ONNX engine or chosen model is not installed')
    root=target_root()
    return [str(root/'engine'/'node'),str(root/'engine'/'worker.cjs'),
            '--ocr','--model-dir',str(matches[label]),'--image',str(image)]
