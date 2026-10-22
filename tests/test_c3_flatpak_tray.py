"""Tray sandbox regression without accessing a user's D-Bus or GTK windows."""
import ast
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'snapmark/tray.py').read_text(encoding='utf-8')
MANIFEST = (ROOT/'flatpak/io.github.yanjingchen.SnapMark.yml').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)

class _FakePath:
    flatpak = False
    target = '/app/share/icons/hicolor/32x32/apps/io.github.yanjingchen.SnapMark.png'
    def __init__(self, path): self.path = str(path)
    def __truediv__(self, other): return _FakePath(self.path.rstrip('/')+'/'+str(other))
    def is_file(self):
        return ((self.path == '/.flatpak-info' and self.flatpak) or
                (self.path == self.target and self.flatpak))
    def resolve(self): return self
    @property
    def parent(self): return _FakePath(str(Path(self.path).parent))
    @classmethod
    def home(cls): return cls('/testhome')

class C3TrayFlatpakTests(unittest.TestCase):
    def test_flatpak_icon_is_read_from_installed_app_tree(self):
        f = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'icon_file')
        mod = ast.Module(body=[f], type_ignores=[])
        ns = {'Path':_FakePath,'os':os,'__file__':'/app/share/snapmark/snapmark/tray.py'}
        old = _FakePath.flatpak
        try:
            _FakePath.flatpak = True
            exec(compile(mod,'tray-test','exec'), ns)
            result = ns['icon_file']()
            self.assertEqual(result.path, _FakePath.target)
        finally: _FakePath.flatpak = old

    def test_host_source_icons_stay_unchanged(self):
        self.assertIn("Path(__file__).resolve().parent.parent / 'assets' / 'io.github.yanjingchen.SnapMark-32.png'", SOURCE)
        self.assertIn("os.environ.get('APPDIR')", SOURCE)

    def test_sandbox_uses_own_app_id_dbus_subname(self):
        cls = next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='TrayIndicator')
        init = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
        cls2 = ast.ClassDef(name='TrayIndicator', bases=[], keywords=[], body=[init], decorator_list=[])
        ast.fix_missing_locations(cls2)
        ns = {'Path':_FakePath,'os':os}
        old = _FakePath.flatpak
        try:
            exec(compile(ast.Module(body=[cls2],type_ignores=[]),'tray-test','exec'), ns)
            _FakePath.flatpak=True
            indicator=ns['TrayIndicator'](lambda:None,lambda:None,lambda:None)
            self.assertEqual(indicator.name,'io.github.yanjingchen.SnapMark.StatusNotifierItem')
            _FakePath.flatpak=False
            indicator2=ns['TrayIndicator'](lambda:None,lambda:None,lambda:None)
            self.assertEqual(indicator2.name,f'org.freedesktop.StatusNotifierItem-{os.getpid()}-1')
        finally: _FakePath.flatpak=old

    def test_minimal_dbus_permissions_and_no_plugins_in_manifest(self):
        self.assertIn('  - --talk-name=org.kde.StatusNotifierWatcher',MANIFEST)
        self.assertNotIn('--socket=session-bus',MANIFEST)
        self.assertNotIn('--filesystem=home',MANIFEST)
        self.assertNotIn('--own-name=org.freedesktop.',MANIFEST)
        self.assertNotIn('official_plugins/', MANIFEST)

    def test_status_protocol_kept(self):
        self.assertIn('RegisterStatusNotifierItem',SOURCE)
        self.assertIn('IconPixmap',SOURCE)
        self.assertIn('Gio.bus_get_sync(Gio.BusType.SESSION',SOURCE)

if __name__ == '__main__': unittest.main()
