#!/usr/bin/env python3
"""Bundle GTK4, libadwaita, PyGObject and CPython in a self-contained AppDir.

Built against Ubuntu 24.04 in Actions, with no dependency on Qt. This is an
explicit GTK4 bundler rather than the GTK2/GTK3 linuxdeploy-plugin-gtk.
"""
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'build' / 'SnapMark.AppDir'
PREFIX = Path('/usr')
ARCH = 'x86_64-linux-gnu'
LIB_DST = APP / 'usr/lib'
SKIP_PREFIX = ('libc.so.', 'libm.so.', 'libpthread.so.', 'libdl.so.',
               'librt.so.', 'libresolv.so.', 'libutil.so.', 'ld-linux-',
               'libnss_', 'libanl.so.')
# Use the host's graphics stack; bundling Mesa/EGL drivers risks hardware conflicts.
HOST_GFX = ('libEGL.so.', 'libGL.so.', 'libGLX.so.', 'libGLES',
            'libgbm.so.', 'libdrm.so.')
LIBRARY_SEEDS = (
    'libgtk-4.so.1', 'libadwaita-1.so.0', 'libgdk_pixbuf-2.0.so.0',
    'libpangocairo-1.0.so.0', 'libpango-1.0.so.0', 'libcairo.so.2',
    'libgirepository-1.0.so.1', 'libgio-2.0.so.0', 'libglib-2.0.so.0',
    'libgobject-2.0.so.0', 'libgraphene-1.0.so.0', 'librsvg-2.so.2',
)


def cpfile(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source.resolve(), dest)


def copy_lib_tree(paths: list[Path]) -> None:
    scanned: set[Path] = set()
    queue = list(paths)
    while queue:
        path = queue.pop(0).resolve()
        if path in scanned or not path.is_file():
            continue
        scanned.add(path)
        for line in subprocess.check_output(['ldd', str(path)], text=True,
                                            stderr=subprocess.STDOUT).splitlines():
            match = re.search(r'(?:(?:=>)\s*)?(/\S+\.so(?:[.\d]+)?)', line)
            if not match:
                continue
            lib = Path(match.group(1))
            name = lib.name
            if name.startswith(SKIP_PREFIX) or name.startswith(HOST_GFX):
                continue
            if not lib.is_file():
                continue
            # Soname matters, not the resolved file basename.
            dest = LIB_DST / name
            if not dest.exists():
                cpfile(lib, dest)
            queue.append(lib)


def main() -> None:
    if APP.exists():
        shutil.rmtree(APP)
    (APP / 'usr/bin').mkdir(parents=True)
    LIB_DST.mkdir(parents=True)
    (APP / 'usr/share/snapmark').mkdir(parents=True)
    shutil.copytree(ROOT / 'snapmark', APP / 'usr/share/snapmark/snapmark',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # The tray resource is loaded from the mounted AppDir, independently of
    # the runner checkout and any icons installed on the host machine.
    tray_assets = APP / 'usr/share/snapmark/assets'
    tray_assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'assets/io.github.yanjingchen.SnapMark-32.png', tray_assets)

    # Bundled libgio must have compiled schemas on runners that lack a GNOME
    # session; GTK/libadwaita query these even during the headless smoke test.
    system_schemas = Path('/usr/share/glib-2.0/schemas')
    if not (system_schemas / 'gschemas.compiled').is_file():
        raise RuntimeError('Missing compiled GLib schemas: /usr/share/glib-2.0/schemas/gschemas.compiled')
    shutil.copytree(system_schemas, APP / 'usr/share/glib-2.0/schemas')

    interpreter = Path(sys.executable).resolve()
    cpfile(interpreter, APP / 'usr/bin/python3')
    stdlib = Path(sysconfig.get_path('stdlib'))
    std_dest = APP / 'usr/lib' / stdlib.name
    shutil.copytree(stdlib, std_dest, ignore=shutil.ignore_patterns(
        '__pycache__', '*.pyc', 'test', 'tests', 'idlelib', 'tkinter',
        'ensurepip', 'venv', 'site-packages'))

    # Ubuntu system Python keeps GI and cairo in dist-packages.
    dist_candidates = [Path('/usr/lib/python3/dist-packages'),
                       Path('/usr/local/lib/python3/dist-packages')]
    dist_dest = APP / 'usr/lib/python3/dist-packages'
    native_modules = [interpreter]
    for dist in dist_candidates:
        for package in ('gi', 'cairo'):
            if (dist / package).exists() and not (dist_dest / package).exists():
                shutil.copytree(dist / package, dist_dest / package,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                native_modules.extend((dist_dest / package).rglob('*.so'))
    if not (dist_dest / 'gi').exists() or not (dist_dest / 'cairo').exists():
        raise RuntimeError('Requires Ubuntu packages python3-gi and python3-cairo')

    typelibs = Path(f'/usr/lib/{ARCH}/girepository-1.0')
    if not typelibs.exists():
        raise RuntimeError(f'GIRepository typelib directory missing: {typelibs}')
    shutil.copytree(typelibs, APP / 'usr/lib/girepository-1.0')

    seeds = []
    for soname in LIBRARY_SEEDS:
        paths = list(Path(f'/usr/lib/{ARCH}').glob(soname)) + list(Path(f'/lib/{ARCH}').glob(soname))
        if not paths:
            raise RuntimeError(f'Required shared library missing: {soname}')
        found = paths[0]
        cpfile(found, LIB_DST / soname)
        seeds.append(found)
    loaders = Path(f'/usr/lib/{ARCH}/gdk-pixbuf-2.0/2.10.0/loaders')
    if not loaders.exists():
        raise RuntimeError(f'GdkPixbuf loaders missing: {loaders}')
    dest_loaders = APP / 'usr/lib/gdk-pixbuf-2.0/2.10.0/loaders'
    shutil.copytree(loaders, dest_loaders)
    native_modules.extend(dest_loaders.glob('*.so'))

    query = Path('/usr/bin/gdk-pixbuf-query-loaders')
    if not query.is_file():
        query = Path(f'/usr/lib/{ARCH}/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders')
    if query.is_file():
        cpfile(query, APP / 'usr/bin/gdk-pixbuf-query-loaders')
        native_modules.append(query)

    copy_lib_tree(seeds + native_modules)

    desktop_name = 'io.github.yanjingchen.SnapMark'
    for location in (APP, APP / 'usr/share/applications'):
        location.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'assets' / f'{desktop_name}.desktop',
                     location / f'{desktop_name}.desktop')
    for location in (APP, APP / 'usr/share/icons/hicolor/256x256/apps'):
        location.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'assets' / f'{desktop_name}-256.png',
                     location / f'{desktop_name}.png')
    for size in (32, 64, 128):
        icons = APP / f'usr/share/icons/hicolor/{size}x{size}/apps'
        icons.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'assets' / f'{desktop_name}-{size}.png',
                     icons / f'{desktop_name}.png')
    (APP / '.DirIcon').symlink_to(f'{desktop_name}.png')
    shutil.copy2(ROOT / 'scripts/AppRun', APP / 'AppRun')
    (APP / 'AppRun').chmod(0o755)
    print(f'AppDir assembled: {APP}')


if __name__ == '__main__':
    main()
