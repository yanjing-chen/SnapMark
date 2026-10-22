"""StatusNotifierItem/dbusmenu serialization in the CI PyGObject runtime."""
import unittest

try:
    import gi
except ImportError:
    gi = None

if gi is not None:
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GLib, Gio
    from snapmark.tray import TrayIndicator, ITEM_XML, MENU_XML, icon_argb_pixmap


@unittest.skipIf(gi is None, 'PyGObject unavailable locally; CI must execute this')
class TrayApiTests(unittest.TestCase):
    def make_indicator(self):
        return TrayIndicator(lambda: None, lambda: None, lambda: None)

    def test_bundled_icon_has_correct_argb_dimensions(self):
        pixmaps = icon_argb_pixmap()
        self.assertEqual(len(pixmaps), 1, 'Tray PNG must be a decodable 32px icon')
        self.assertEqual(pixmaps[0][0:2], (32, 32))
        raw = pixmaps[0][2]
        self.assertEqual(len(raw), 32 * 32 * 4)
        self.assertTrue(any(raw[index] for index in range(0, len(raw), 4)))

    def test_dbus_xml_interfaces(self):
        self.assertEqual(Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0].name,
                         'org.kde.StatusNotifierItem')
        self.assertEqual(Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0].name,
                         'com.canonical.dbusmenu')

    def test_property_variants(self):
        tray = self.make_indicator()
        tray.pixmaps = [(1, 1, bytes([255, 0, 120, 60]))]
        for key, expected in (('IconPixmap', 'a(iiay)'), ('ToolTip', '(sa(iiay)ss)'),
                              ('Menu', 'o'), ('ItemIsMenu', 'b')):
            value = tray._item_prop(None, None, None, None, key)
            self.assertEqual(value.get_type_string(), expected)

    def test_menu_layout_variants(self):
        # This legacy structural contract checks the canonical English menu.
        # Explicitly select English so it does not depend on the language
        # left selected by C3's real zh_CN/nl gettext tests.
        from snapmark.i18n import configure
        configure('en')
        self.addCleanup(configure, 'system')
        class Invocation:
            value = None
            def return_value(self, v):
                self.value = v
        tray = self.make_indicator()
        invocation = Invocation()
        tray._menu_call(None, None, None, None, 'GetLayout',
                        GLib.Variant('(iias)', (0, -1, [])), invocation)
        self.assertEqual(invocation.value.get_type_string(), '(u(ia{sv}av))')
        layout = invocation.value.unpack()[1]
        self.assertEqual(layout[0], 0)
        # Eight nodes: six menu actions plus two visible separators.
        def unwrap(obj):
            while hasattr(obj, 'unpack'):
                obj = obj.unpack()
            return obj
        children = [unwrap(item) for item in layout[2]]
        self.assertEqual([entry[0] for entry in children],
                         [1, 7, 2, 3, 8, 4, 9, 6])
        props = {entry[0]: entry[1] for entry in children}
        def value(item_id, key):
            return unwrap(props[item_id][key])
        for item_id, label in ((1, 'Open SnapMark'),
                               (2, 'Open Clipboard Image'),
                               (3, 'Screenshot History'),
                               (4, 'Preferences'),
                               (9, 'Restart SnapMark'),
                               (6, 'Quit')):
            self.assertEqual(value(item_id, 'label'), label)
            self.assertTrue(value(item_id, 'visible'))
            self.assertIn('icon-name', props[item_id])
        for item_id in (7, 8):
            self.assertEqual(value(item_id, 'type'), 'separator')
            self.assertTrue(value(item_id, 'visible'))
        # Open is clickable; empty clipboards still disable import.
        self.assertTrue(value(1, 'enabled'))
        self.assertFalse(value(2, 'enabled'))
        self.assertTrue(value(3, 'enabled'))
        # Enabling clipboard image data must enable the action dynamically.
        tray.clipboard_ready = lambda: True
        self.assertTrue(tray._item_properties(2)['enabled'].unpack())


if __name__ == '__main__':
    unittest.main()
