"""No-GI tests of the *actual* SNI start/registration/stop methods.

The project is also tested on systems without a GUI stack, so this test
extracts TrayIndicator from the AST and supplies a synthetic D-Bus host.
The resulting code executes the same class/method bodies as the application.
"""
import ast
from pathlib import Path
import re
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
TRAY = ROOT / 'snapmark' / 'tray.py'
ITEM_PATH = '/StatusNotifierItem'
WATCHER = 'org.kde.StatusNotifierWatcher'


class FakeVariant:
    def __init__(self, signature, value):
        self.signature = signature
        self.value = value

    def unpack(self):
        return self.value


class FakeBus:
    def __init__(self, host=True):
        self.host = host
        self.calls = []
        self.unregistered = []
        self.exported = []

    def register_object(self, path, info, callback, property_callback, *_):
        self.exported.append((path, info, callback, property_callback))
        return len(self.exported)

    def unregister_object(self, number):
        self.unregistered.append(number)

    def call_sync(self, destination, obj, interface, method, arguments, *others):
        self.calls.append((destination, obj, interface, method, arguments))
        if method == 'NameHasOwner':
            return FakeVariant('(b)', (self.host,))
        return FakeVariant('()', ())

    def registration_values(self):
        return [c[4].unpack()[0] for c in self.calls
                if c[3] == 'RegisterStatusNotifierItem']


class FakeInfo:
    @staticmethod
    def new_for_xml(xml):
        return types.SimpleNamespace(interfaces=[object()])


def make_tray(flatpak=False, host=True):
    bus = FakeBus(host)
    gio = types.SimpleNamespace(
        BusType=types.SimpleNamespace(SESSION=0),
        BusNameWatcherFlags=types.SimpleNamespace(NONE=0),
        DBusCallFlags=types.SimpleNamespace(NONE=0),
        DBusNodeInfo=FakeInfo,
        bus_get_sync=lambda *args: bus,
        bus_watch_name_on_connection=lambda *args: 7,
        bus_unwatch_name=lambda number: None,
    )
    glib = types.SimpleNamespace(
        Variant=FakeVariant,
        VariantType=types.SimpleNamespace(new=lambda *args: object()),
        Error=Exception,
    )
    # Compile the real class, not a reimplementation of its methods.
    source = ast.parse(TRAY.read_text(encoding='utf-8'))
    original_class = next(n for n in source.body
                          if isinstance(n, ast.ClassDef) and n.name == 'TrayIndicator')
    module = ast.Module(body=[original_class], type_ignores=[])
    obj = types.SimpleNamespace(is_file=lambda: flatpak)
    globals_ = {
        'Gio': gio, 'GLib': glib, 'ITEM_PATH': ITEM_PATH,
        'MENU_PATH': '/MenuBar', 'ITEM_XML': '<node/>',
        'MENU_XML': '<node/>', 'WATCHER': WATCHER,
        'Path': lambda path: obj,
        'icon_argb_pixmap': lambda: [(32, 32, b'pixel-data')],
        'os': types.SimpleNamespace(getpid=lambda: 5203),
    }
    exec(compile(module, str(TRAY), 'exec'), globals_)
    tray = globals_['TrayIndicator'](lambda: None, lambda: None, lambda: None)
    return tray, bus


def extension_indicator_id(service, bus_name, obj_path):
    """Source: ubuntu/gnome-shell-extension-appindicator util.js indicatorId."""
    bus_address = r'([a-zA-Z0-9._-]+\.[a-zA-Z0-9.-]+)|(:[0-9]+\.[0-9]+)$'
    if service != bus_name and service and re.search(bus_address, service):
        return service
    return f'{bus_name}@{obj_path}'


class SingleTrayContracts(unittest.TestCase):
    def test_native_registration_is_path_and_does_not_request_an_extra_name(self):
        tray, bus = make_tray()
        self.assertTrue(tray.start())
        self.assertEqual(bus.registration_values(), [ITEM_PATH])
        self.assertFalse(any(c[3] == 'RequestName' for c in bus.calls))
        self.assertEqual([item[0] for item in bus.exported],
                         [ITEM_PATH, '/MenuBar'])
        self.assertIsNone(tray.name)
        tray.stop()
        self.assertEqual(bus.unregistered, [1, 2])
        self.assertFalse(tray.available)

    def test_ubuntu_gnome_scan_has_same_id_as_explicit_register(self):
        tray, bus = make_tray()
        self.assertTrue(tray.start())
        service = bus.registration_values()[0]    # path registered by SnapMark
        unique = ':1.69'                          # DBus invocation sender
        register_id = extension_indicator_id(service, unique, ITEM_PATH)
        discovered = [None, 'io.github.yanjingchen.SnapMark']
        scan_ids = [extension_indicator_id(s, unique, ITEM_PATH)
                    for s in discovered]
        self.assertEqual(register_id, ':1.69@/StatusNotifierItem')
        self.assertIn(register_id, scan_ids)

    def test_repeated_registration_does_not_reexport_or_claim_name(self):
        tray, bus = make_tray()
        self.assertTrue(tray.start())
        tray._register()
        self.assertEqual(bus.registration_values(), [ITEM_PATH])
        self.assertEqual(len(bus.exported), 2)
        tray.available = False  # watcher restarted
        tray._register()
        self.assertEqual(bus.registration_values(), [ITEM_PATH, ITEM_PATH])
        self.assertFalse(any(c[3] == 'RequestName' for c in bus.calls))

    def test_flatpak_keeps_original_bus_name_policy(self):
        tray, bus = make_tray(flatpak=True)
        self.assertTrue(tray.start())
        expected = 'io.github.yanjingchen.SnapMark.StatusNotifierItem'
        self.assertEqual(bus.registration_values(), [expected])
        names = [c[4].unpack()[0] for c in bus.calls if c[3] == 'RequestName']
        self.assertEqual(names, [expected])
        tray.stop()
        self.assertEqual(bus.unregistered, [1, 2])

    def test_no_watcher_does_not_claim_native_bus_name(self):
        tray, bus = make_tray(host=False)
        self.assertFalse(tray.start())
        self.assertEqual(bus.registration_values(), [])
        self.assertFalse(any(c[3] == 'RequestName' for c in bus.calls))
        self.assertEqual(len(bus.exported), 2)
        tray.stop()
        self.assertEqual(bus.unregistered, [1, 2])


if __name__ == '__main__':
    unittest.main()
