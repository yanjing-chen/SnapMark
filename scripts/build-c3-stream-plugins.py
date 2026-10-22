#!/usr/bin/env python3
"""Build side-by-side bilingual streaming fixes without overwriting v1.0.0.

Only gettext catalogs for en and zh_CN are packaged. Original code-only
plugin sources stay at their historical versions for C2 compatibility.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LANGUAGES = ('en', 'zh_CN')
RELEASES = {
    'ocr': ('1.0.2', ('plugin.json', 'models.json', 'catalog.py', 'main.py',
                       'worker.py', 'manager_c2b.py', 'onnx_c2.py',
                       'official_models_c2.py', 'catalog_builtin.json',
                       'advanced_runtime_c2.py', 'profiles_c2f.py')),
    'translation': ('1.0.2', ('plugin.json', 'main.py', 'runtime_client.py',
                             'format_guard_c2d.py', 'settings_c2e.py')),
}

def build(output: Path):
    from snapmark.i18n import CODES
    assert set(CODES) == set(LANGUAGES), 'Source language policy mismatch'
    output.mkdir(parents=True, exist_ok=True)
    result = []
    for ident, (version, source_files) in RELEASES.items():
        source = ROOT / 'official_plugins' / ident
        output_zip = output / f'SnapMark-{ident}-{version}.zip'
        assert not output_zip.exists(), f'Refusing to overwrite: {output_zip}'
        manifest = json.loads((source/'plugin.json').read_text('utf-8'))
        assert manifest['id'] == ident
        manifest['version'] = version
        # Translation v1 requires the jointly released OCR v1, not an arbitrary old OCR.
        if ident == 'translation':
            manifest['dependencies'] = {'ocr': '1.0.2'}
        with ZipFile(output_zip, 'w', compression=ZIP_DEFLATED, compresslevel=9) as z:
            for name in source_files:
                payload = ((json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode()
                           if name == 'plugin.json' else (source/name).read_bytes())
                entry = ZipInfo(name, date_time=(2026, 10, 22, 0, 0, 0))
                entry.external_attr = 0o100644 << 16
                entry.compress_type = ZIP_DEFLATED
                z.writestr(entry, payload, compress_type=ZIP_DEFLATED, compresslevel=9)
            for lang in LANGUAGES:
                path = ROOT/'snapmark'/'locale'/lang/'LC_MESSAGES'/f'snapmark-{ident}.mo'
                assert path.is_file(), f'Missing compiled gettext catalog: {path}'
                entry = ZipInfo(f'locale/{lang}/LC_MESSAGES/snapmark-{ident}.mo',
                                date_time=(2026, 10, 22, 0, 0, 0))
                entry.external_attr = 0o100644 << 16
                entry.compress_type = ZIP_DEFLATED
                z.writestr(entry, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
        digest = hashlib.sha256(output_zip.read_bytes()).hexdigest()
        sidecar = output_zip.with_name(output_zip.name+'.sha256')
        sidecar.write_text(f'{digest}  {output_zip.name}\n', encoding='ascii')
        result.append(output_zip)
        print(f'BILINGUAL_PLUGIN={output_zip} SHA256={digest}')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    a=parser.parse_args()
    build(a.output.expanduser().resolve())
