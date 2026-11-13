#!/usr/bin/env python3
"""Platform-independent packaging contract tests, no GI runtime required."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VERSION = '1.1.1'

class PackagingTests(unittest.TestCase):
    def test_version(self):
        from snapmark import __version__
        self.assertEqual(VERSION, __version__)

    def test_appimage_gtk_modes(self):
        text=(ROOT/'scripts/AppRun').read_text()
        self.assertIn('SNAPMARK_APPIMAGE_GTK_MODE',text)
        self.assertIn('host_gtk_available',text)
        self.assertIn('exec /usr/bin/python3 -m snapmark.app',text)
        self.assertIn('exec "$APPDIR/usr/bin/python3" -m snapmark.app',text)

    def test_no_change_screenshot_events(self):
        code=(ROOT/'snapmark/app.py').read_text()
        self.assertIn('def _clipboard_changed(',code)
        self.assertIn('def start_watching(',code)
        self.assertNotIn('def _poll_clipboard(',code)

    def test_deb_metadata_and_contents(self):
        pkg=ROOT/'dist'/f'snapmark_1.1.1-1_amd64.deb'
        if not pkg.exists():
            self.skipTest('DEB not built yet')
        lines=subprocess.check_output(['dpkg-deb','--contents',str(pkg)],text=True)
        for entry in ('./usr/bin/snapmark','./usr/share/snapmark/snapmark/app.py',
                      './usr/share/applications/io.github.yanjingchen.SnapMark.desktop'):
            self.assertIn(entry,lines)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.check_call(['dpkg-deb','-x',str(pkg),tmp])
            exec_text=(Path(tmp)/'usr/bin/snapmark').read_text()
            self.assertIn('PYTHONPATH="/usr/share/snapmark"', exec_text)
            desktop=(Path(tmp)/'usr/share/applications/io.github.yanjingchen.SnapMark.desktop').read_text()
            self.assertIn('Exec=/usr/bin/snapmark',desktop)
            self.assertTrue((Path(tmp)/'usr/share/snapmark/assets/io.github.yanjingchen.SnapMark-32.png').is_file())

    def test_stable_release_tag(self):
        launcher = (ROOT/'scripts/publish-v1.1.1.sh').read_text()
        self.assertIn("TAG='v1.1.1'", launcher)
        self.assertIn("isPrerelease --jq .isPrerelease", launcher)
        self.assertIn("== false ]]", launcher)
        self.assertNotIn('1.1.1-' + 'rc2', launcher)
        workflow=(ROOT/'.github/workflows/appimage.yml').read_text()
        self.assertIn("prerelease: ${{ contains(github.ref_name, '-') }}", workflow)

    def test_workflow_outputs(self):
        workflow=(ROOT/'.github/workflows/appimage.yml').read_text()
        for item in ('scripts/build-deb.sh', 'dist/*.AppImage', 'dist/*.deb',
                     'sha256sum -c SHA256SUMS.txt','softprops/action-gh-release@v2'):
            self.assertIn(item,workflow)
        self.assertIn("contains(github.ref_name, '-')",workflow)

if __name__=='__main__':
    unittest.main()
