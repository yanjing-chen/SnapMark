"""GTK4-independent StatusNotifierItem + dbusmenu indicator.

GNOME Shell needs an SNI/AppIndicator host; no GTK3 or Qt process is loaded.
The indicator gracefully does nothing without a host.
"""
import os
from pathlib import Path

from gi.repository import GdkPixbuf, Gio, GLib

ITEM_PATH = '/StatusNotifierItem'
MENU_PATH = '/MenuBar'
WATCHER = 'org.kde.StatusNotifierWatcher'
ITEM_XML = '''<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
<method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
<method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/>
<property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/>
<property name="Status" type="s" access="read"/>
<property name="WindowId" type="i" access="read"/>
<property name="IconName" type="s" access="read"/>
<property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="OverlayIconName" type="s" access="read"/>
<property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionIconName" type="s" access="read"/>
<property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionMovieName" type="s" access="read"/>
<property name="IconThemePath" type="s" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<property name="Menu" type="o" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/>
<signal name="NewIcon"/><signal name="NewStatus"><arg type="s"/></signal>
</interface></node>'''
MENU_XML = '''<node><interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg name="parentId" type="i" direction="in"/>
<arg name="recursionDepth" type="i" direction="in"/>
<arg name="propertyNames" type="as" direction="in"/>
<arg name="revision" type="u" direction="out"/>
<arg name="layout" type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg name="ids" type="ai" direction="in"/><arg name="propertyNames" type="as" direction="in"/><arg name="properties" type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg name="id" type="i" direction="in"/><arg name="name" type="s" direction="in"/><arg name="value" type="v" direction="out"/></method>
<method name="Event"><arg name="id" type="i" direction="in"/><arg name="eventId" type="s" direction="in"/><arg name="data" type="v" direction="in"/><arg name="timestamp" type="u" direction="in"/></method>
<method name="EventGroup"><arg name="events" type="a(isvu)" direction="in"/><arg name="unhandled" type="ai" direction="out"/></method>
<method name="AboutToShow"><arg name="id" type="i" direction="in"/><arg name="needsUpdate" type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg name="ids" type="ai" direction="in"/><arg name="updates" type="ai" direction="out"/><arg name="idErrors" type="ai" direction="out"/></method>
<property name="Version" type="u" access="read"/>
<property name="TextDirection" type="s" access="read"/>
<property name="Status" type="s" access="read"/>
<property name="IconThemePath" type="as" access="read"/>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
</interface></node>'''

MENU_ITEMS = {1: 'Open SnapMark', 2: 'Preferences', 3: 'Quit SnapMark'}


def icon_file():
    candidates = [Path(__file__).resolve().parent.parent / 'assets' / 'io.github.yanjingchen.SnapMark-32.png']
    candidates.append(Path.home() / '.local/share/icons/hicolor/32x32/apps/io.github.yanjingchen.SnapMark.png')
    appdir = os.environ.get('APPDIR')
    if appdir:
        candidates.append(Path(appdir) / 'usr/share/icons/hicolor/32x32/apps/io.github.yanjingchen.SnapMark.png')
    return next((f for f in candidates if f.is_file()), None)


def icon_argb_pixmap():
    path = icon_file()
    if path is None:
        return []
    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 32, 32, True)
    if pb.get_width() != 32 or pb.get_height() != 32:
        return []
    raw, stride = pb.get_pixels(), pb.get_rowstride()
    channels = pb.get_n_channels()
    argb = bytearray()
    for y in range(32):
        for x in range(32):
            i = y * stride + x * channels
            r, g, b = raw[i:i + 3]
            a = raw[i + 3] if channels == 4 else 255
            argb.extend((a, r, g, b))
    return [(32, 32, bytes(argb))]


class TrayIndicator:
    def __init__(self, open_editor, open_preferences, quit_app):
        self.open_editor, self.open_preferences, self.quit_app = open_editor, open_preferences, quit_app
        self.bus = None
        self.registration_ids = []
        self.name = f'org.freedesktop.StatusNotifierItem-{os.getpid()}-1'
        self.available = False
        self.watch_id = 0
        self.pixmaps = []

    def start(self):
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self.pixmaps = icon_argb_pixmap()
            for path, xml, method, getprop in ((ITEM_PATH, ITEM_XML, self._item_call, self._item_prop),
                                                (MENU_PATH, MENU_XML, self._menu_call, self._menu_prop)):
                info = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]
                ident = self.bus.register_object(path, info, method, getprop, None)
                self.registration_ids.append(ident)
            self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                               'org.freedesktop.DBus', 'RequestName',
                               GLib.Variant('(su)', (self.name, 0)), GLib.VariantType.new('(u)'),
                               Gio.DBusCallFlags.NONE, 1500, None)
            # Resolve an already running host synchronously before a possible
            # start-minimized decision. The watcher also handles later hosts.
            has_host = self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                          'org.freedesktop.DBus', 'NameHasOwner',
                                          GLib.Variant('(s)', (WATCHER,)),
                                          GLib.VariantType.new('(b)'),
                                          Gio.DBusCallFlags.NONE, 1500, None).unpack()[0]
            if has_host:
                self._register()
            self.watch_id = Gio.bus_watch_name_on_connection(
                self.bus, WATCHER, Gio.BusNameWatcherFlags.NONE,
                lambda *_: self._register(), lambda *_: setattr(self, 'available', False))
        except (GLib.Error, ValueError, TypeError, OSError) as exc:
            print(f'SnapMark: status indicator unavailable: {exc}', flush=True)
        return self.available

    def _register(self):
        if self.available:
            return
        try:
            self.bus.call_sync(WATCHER, '/StatusNotifierWatcher', WATCHER,
                               'RegisterStatusNotifierItem', GLib.Variant('(s)', (self.name,)),
                               None, Gio.DBusCallFlags.NONE, 1500, None)
            self.available = True
            print('SnapMark: status indicator registered', flush=True)
        except GLib.Error as exc:
            self.available = False
            print(f'SnapMark: status host rejected indicator: {exc}', flush=True)

    def stop(self):
        if self.watch_id:
            Gio.bus_unwatch_name(self.watch_id)
            self.watch_id = 0
        if self.bus:
            for ident in self.registration_ids:
                self.bus.unregister_object(ident)
        self.registration_ids.clear()
        self.available = False

    def _item_prop(self, _bus, _sender, _path, _iface, name):
        props = {'Category': GLib.Variant('s', 'ApplicationStatus'),
                 'Id': GLib.Variant('s', 'snapmark'), 'Title': GLib.Variant('s', 'SnapMark'),
                 'Status': GLib.Variant('s', 'Active'), 'WindowId': GLib.Variant('i', 0),
                 'IconName': GLib.Variant('s', 'io.github.yanjingchen.SnapMark'),
                 'IconPixmap': GLib.Variant('a(iiay)', self.pixmaps),
                 'Menu': GLib.Variant('o', MENU_PATH), 'ItemIsMenu': GLib.Variant('b', False),
                 'OverlayIconName': GLib.Variant('s', ''),
                 'OverlayIconPixmap': GLib.Variant('a(iiay)', []),
                 'AttentionIconName': GLib.Variant('s', ''),
                 'AttentionIconPixmap': GLib.Variant('a(iiay)', []),
                 'AttentionMovieName': GLib.Variant('s', ''),
                 'IconThemePath': GLib.Variant('s', ''),
                 'ToolTip': GLib.Variant('(sa(iiay)ss)', ('SnapMark', self.pixmaps,
                                                        'SnapMark', 'Screenshot annotation'))}
        return props.get(name)

    def _item_call(self, _bus, _sender, _path, _iface, name, _args, invocation):
        if name == 'Activate':
            GLib.idle_add(self.open_editor)
        elif name in ('SecondaryActivate', 'ContextMenu'):
            GLib.idle_add(self.open_preferences)
        invocation.return_value(None)

    @staticmethod
    def _item_properties(index):
        return {'label': GLib.Variant('s', MENU_ITEMS[index]),
                'enabled': GLib.Variant('b', True),
                'visible': GLib.Variant('b', True)}

    def _menu_prop(self, _bus, _sender, _path, _iface, name):
        return {'Version': GLib.Variant('u', 2), 'TextDirection': GLib.Variant('s', 'ltr'),
                'Status': GLib.Variant('s', 'normal'),
                'IconThemePath': GLib.Variant('as', [])}.get(name)

    def _menu_call(self, _bus, _sender, _path, _iface, name, args, invocation):
        if name == 'GetLayout':
            parent, depth, _ = args.unpack()
            if parent == 0:
                children = [GLib.Variant('(ia{sv}av)', (i, self._item_properties(i), []))
                            for i in MENU_ITEMS] if depth != 0 else []
                layout = (0, {}, children)
            else:
                layout = (parent, self._item_properties(parent) if parent in MENU_ITEMS else {}, [])
            invocation.return_value(GLib.Variant('(u(ia{sv}av))', (1, layout)))
        elif name == 'GetGroupProperties':
            ids, _ = args.unpack()
            ids = MENU_ITEMS.keys() if not ids else ids
            invocation.return_value(GLib.Variant('(a(ia{sv}))',
                                                 ([(i, self._item_properties(i)) for i in ids if i in MENU_ITEMS],)))
        elif name == 'GetProperty':
            index, prop = args.unpack()
            value = self._item_properties(index).get(prop, GLib.Variant('s', '')) if index in MENU_ITEMS else GLib.Variant('s', '')
            invocation.return_value(GLib.Variant('(v)', (value,)))
        elif name in ('Event', 'EventGroup'):
            events = [args.unpack()] if name == 'Event' else args.unpack()[0]
            for index, event_id, *_ in events:
                if event_id == 'clicked':
                    callbacks = {1: self.open_editor, 2: self.open_preferences, 3: self.quit_app}
                    if index in callbacks:
                        GLib.idle_add(callbacks[index])
            invocation.return_value(None if name == 'Event' else GLib.Variant('(ai)', ([],)))
        elif name == 'AboutToShow':
            invocation.return_value(GLib.Variant('(b)', (False,)))
        elif name == 'AboutToShowGroup':
            invocation.return_value(GLib.Variant('(aiai)', ([], [])))
        else:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod', name)
