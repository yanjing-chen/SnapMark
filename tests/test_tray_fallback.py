import unittest

try:
    import gi
except ImportError:
    gi = None

if gi is not None:
    from snapmark.tray import TrayIndicator


@unittest.skipIf(gi is None, 'Requires PyGObject')
class TrayFallbackTests(unittest.TestCase):
    def test_pixmap_takes_precedence_over_uninstalled_icon_name(self):
        tray = TrayIndicator(lambda: None, lambda: None, lambda: None)
        tray.pixmaps = [(1, 1, bytes([255, 10, 50, 60]))]
        self.assertEqual(tray._item_prop(None, None, None, None, 'IconName').unpack(), '')
        self.assertEqual(tray._item_prop(None, None, None, None, 'IconPixmap').get_type_string(), 'a(iiay)')
