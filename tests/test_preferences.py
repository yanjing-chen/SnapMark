import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from snapmark.preferences import Settings, Autostart


class PreferencesTests(unittest.TestCase):
    def test_custom_folder_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root)
            folder = parent / '图片' / '截图'
            folder.mkdir(parents=True)
            settings = Settings(parent / 'config')
            self.assertEqual(settings.screenshot_directory(), '')
            settings.set_screenshot_directory(str(folder))
            self.assertEqual(settings.screenshot_directory(), str(folder))
            settings.set_screenshot_directory('')
            self.assertEqual(settings.screenshot_directory(), '')

    def test_invalid_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            settings = Settings(Path(root) / 'config')
            with self.assertRaises(ValueError):
                settings.set_screenshot_directory(str(Path(root) / 'does-not-exist'))

    def test_autostart_uses_persistent_appimage_path(self):
        with tempfile.TemporaryDirectory() as root:
            parent = Path(root)
            executable = parent / 'SnapMark demo.AppImage'
            executable.write_text('#!/bin/sh\n')
            executable.chmod(0o755)
            entry = Autostart(parent / 'config')
            with patch.object(Autostart, 'launcher', return_value=str(executable)):
                entry.set_enabled(True)
            self.assertTrue(entry.enabled())
            self.assertIn(f'Exec="{executable}" --watch', entry.file.read_text())
            entry.set_enabled(False)
            self.assertFalse(entry.enabled())

    def test_does_not_delete_foreign_autostart_entry(self):
        with tempfile.TemporaryDirectory() as root:
            entry = Autostart(Path(root))
            entry.file.parent.mkdir(parents=True)
            entry.file.write_text('[Desktop Entry]\nName=Unrelated\n')
            entry.set_enabled(False)
            self.assertTrue(entry.file.exists())


if __name__ == '__main__':
    unittest.main()
