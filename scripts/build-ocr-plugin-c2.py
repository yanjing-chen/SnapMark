#!/usr/bin/env python3
"""Build deterministic official code-only OCR ZIP and adjacent SHA256 sidecar."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = ('plugin.json', 'models.json', 'catalog.py', 'main.py', 'worker.py', 'manager_c2b.py', 'onnx_c2.py', 'official_models_c2.py', 'catalog_builtin.json', 'advanced_runtime_c2.py', 'profiles_c2f.py')


def build(output):
    src = ROOT / 'official_plugins/ocr'
    manifest = json.loads((src / 'plugin.json').read_text('utf-8'))
    assert manifest['id'] == 'ocr' and manifest['version'] == '0.2.4'
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'SnapMark-ocr-0.2.4.zip'
    with ZipFile(path, 'w', compression=ZIP_DEFLATED, compresslevel=9) as z:
        for name in FILES:
            data = (src / name).read_bytes()
            info = ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            z.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar = path.with_name(path.name + '.sha256')
    sidecar.write_text(f'{digest}  {path.name}\n', encoding='ascii')
    print(f'OCR_PLUGIN_ZIP={path}')
    print(f'OCR_PLUGIN_SHA256={digest}')
    return path, sidecar


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output.expanduser().resolve())
