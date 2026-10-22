#!/usr/bin/env python3
"""Compile vetted gettext .po with msgfmt; no network or model translation."""
from pathlib import Path
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from snapmark.i18n import LANGUAGES

def main():
    msgfmt = shutil.which('msgfmt')
    if not msgfmt:
        raise SystemExit('gettext msgfmt missing; install package gettext (development only)')
    for code, _, _ in LANGUAGES:
        for domain in ('snapmark', 'snapmark-ocr', 'snapmark-translation'):
            src = ROOT / 'snapmark' / 'locale' / code / 'LC_MESSAGES' / (domain + '.po')
            dst = src.with_suffix('.mo')
            if not src.is_file():
                raise SystemExit(f'Missing gettext catalog: {src}')
            subprocess.run([msgfmt, '--check', '-o', str(dst), str(src)], check=True)
    print('C3_GETTEXT_COMPILED=2_LOCALES_3_DOMAINS')
if __name__ == '__main__': main()
