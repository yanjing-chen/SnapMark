"""Screenshot folder regression tests (no GTK/GI dependencies)."""
import tempfile
import unittest
from pathlib import Path
from snapmark.screenshot_paths import (is_screenshot_folder, is_screenshot_name,
                                       monitored_directories)


class ScreenshotPathsTests(unittest.TestCase):
    def test_chinese_gnome_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pictures = home / '图片'
            screenshots = pictures / '截图'
            screenshots.mkdir(parents=True)
            selected = monitored_directories(pictures, home, custom_dir='')
            self.assertIn(screenshots.resolve(), selected)
            self.assertIn(pictures.resolve(), selected)

    def test_english_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pictures = home / 'Pictures'
            screenshots = pictures / 'Screenshots'
            screenshots.mkdir(parents=True)
            self.assertIn(screenshots.resolve(),
                          monitored_directories(pictures, home, custom_dir=''))

    def test_custom_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pictures = home / '图片'
            custom = home / 'Custom Screens'
            pictures.mkdir()
            custom.mkdir()
            self.assertIn(custom.resolve(),
                          monitored_directories(pictures, home, str(custom)))

    def test_screenshot_filename_filter(self):
        self.assertTrue(is_screenshot_name('截图 2026-10-13 23-34-45.png'))
        self.assertTrue(is_screenshot_name('Screenshot from 2026-10-13.png'))
        self.assertFalse(is_screenshot_name('holiday.png'))
        self.assertFalse(is_screenshot_name('截图 note.txt'))
        self.assertTrue(is_screenshot_folder('截图'))
        self.assertTrue(is_screenshot_folder('Screenshots'))
        self.assertFalse(is_screenshot_folder('Documents'))

    def test_no_creation_of_unused_english_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pictures = home / '图片'
            pictures.mkdir()
            selected = monitored_directories(pictures, home, custom_dir='')
            self.assertIn(pictures.resolve(), selected)
            self.assertFalse((pictures / 'Screenshots').exists())


if __name__ == '__main__':
    unittest.main()
