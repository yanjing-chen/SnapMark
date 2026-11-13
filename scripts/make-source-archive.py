#!/usr/bin/env python3
"""Create a deterministic complete source ZIP, excluding generated build outputs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snapmark import __version__

NAME = f'SnapMark-{__version__}'
DEST = ROOT / 'dist' / f'{NAME}-Full-Source.zip'
EXCLUDE_DIRS = {'.git', '.venv', '__pycache__', '.pytest_cache', 'build', 'dist', '.mypy_cache'}
EXCLUDE_EXT = {'.pyc', '.pyo', '.AppImage', '.zip'}


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return not any(part in EXCLUDE_DIRS for part in rel.parts) and path.suffix not in EXCLUDE_EXT


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in ROOT.rglob('*') if p.is_file() and included(p))
    if not files or not (ROOT / 'snapmark/app.py') in files:
        raise SystemExit('Source files are missing')
    with ZipFile(DEST, 'w', compression=ZIP_DEFLATED, compresslevel=8) as z:
        for path in files:
            z.write(path, f'{NAME}/{path.relative_to(ROOT).as_posix()}')
    with ZipFile(DEST) as z:
        if z.testzip() is not None or not any(s.endswith('/snapmark/app.py') for s in z.namelist()):
            raise SystemExit('Source archive integrity check failed')
    print(f'Complete source: {DEST} files={len(files)} bytes={DEST.stat().st_size}')


if __name__ == '__main__':
    main()
