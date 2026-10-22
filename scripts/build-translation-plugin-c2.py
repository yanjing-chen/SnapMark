#!/usr/bin/env python3
"""Build deterministic code-only Translation plugin archive; no network."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = ('plugin.json', 'main.py', 'runtime_client.py', 'format_guard_c2d.py', 'settings_c2e.py')


def build(output):
    src = ROOT / 'official_plugins/translation'
    manifest = json.loads((src / 'plugin.json').read_text('utf-8'))
    assert manifest['id'] == 'translation' and manifest['version'] == '0.1.5'
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'SnapMark-translation-0.1.5.zip'
    with ZipFile(path, 'w', compression=ZIP_DEFLATED, compresslevel=9) as z:
        for name in FILES:
            data = (src / name).read_bytes()
            entry = ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            z.writestr(entry, data, compress_type=ZIP_DEFLATED, compresslevel=9)
        locale_root = ROOT / 'snapmark' / 'locale'
        for catalog in sorted(locale_root.glob('*/LC_MESSAGES/snapmark-translation.mo')):
            arcname = 'locale/' + catalog.parent.parent.name + '/LC_MESSAGES/' + catalog.name
            info = ZipInfo(arcname, date_time=(2026, 10, 15, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            z.writestr(info, catalog.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + '.sha256').write_text(f'{digest}  {path.name}\n', 'ascii')
    print('TRANSLATION_PLUGIN_ZIP=', path)
    print('TRANSLATION_PLUGIN_SHA256=', digest)
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output.expanduser().resolve())
