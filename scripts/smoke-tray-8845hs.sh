#!/usr/bin/env bash
# Non-destructive diagnostic for native SnapMark SNI under GNOME 51/Wayland.
# Run after installing candidate DEB and signing back into the desktop.
set -euo pipefail

echo '===== SnapMark process(es) ====='
pgrep -af '[/]usr/bin/python3 -m snapmark.app' || true

echo '===== D-Bus names owned by SnapMark ====='
busctl --user --no-pager list | grep -iE 'SnapMark|org.freedesktop.StatusNotifierItem-' || true

echo '===== StatusNotifierWatcher registration ====='
gdbus call --session --dest org.kde.StatusNotifierWatcher \
  --object-path /StatusNotifierWatcher \
  --method org.freedesktop.DBus.Properties.Get \
  org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems || true

echo '===== Check registrations refer to exactly ONE SnapMark indicator ====='
/usr/bin/python3 - <<'PY'
import gi
from gi.repository import Gio, GLib
bus=Gio.bus_get_sync(Gio.BusType.SESSION, None)
watcher='org.kde.StatusNotifierWatcher'
item_path='/StatusNotifierItem'
arg=GLib.Variant('(ss)', (watcher, 'RegisteredStatusNotifierItems'))
try:
    res=bus.call_sync(watcher, '/StatusNotifierWatcher',
        'org.freedesktop.DBus.Properties', 'Get', arg,
        GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 5000, None)
    items=res.get_child_value(0).get_variant().unpack()
except GLib.Error as error:
    raise SystemExit(f'WATCHER UNAVAILABLE: {error}')

def sni_id(service):
    if service.startswith('/'):
        # Path-style registration: item belongs to the sender/our app bus name.
        destination='io.github.yanjingchen.SnapMark'
        path=service
    elif '@/' in service:
        destination,path=service.split('@',1)
    else:
        destination,path=service,item_path
    try:
        reply=bus.call_sync(destination,path,'org.freedesktop.DBus.Properties',
            'Get',GLib.Variant('(ss)',('org.kde.StatusNotifierItem','Id')),
            GLib.VariantType.new('(v)'),Gio.DBusCallFlags.NONE,1500,None)
        return reply.get_child_value(0).get_variant().unpack()
    except GLib.Error:
        return None

found=[]
for item in items:
    name=sni_id(item)
    if name=='snapmark':
        found.append(item)
print('WATCHER_TOTAL=',len(items))
print('SNAPMARK_REGISTERED=',found)
if len(found)!=1:
    raise SystemExit(f'FAIL: expected exactly 1 SnapMark SNI, saw {len(found)}')
print('SINGLE_TRAY_REGISTRATION=PASS')
PY

echo '===== Recent relevant GNOME logs ====='
journalctl --user -b --no-pager 2>/dev/null \
  | grep -Ei 'SnapMark: status indicator|Using Brute-force mode for StatusNotifierItem io.github.yanjingchen.SnapMark' \
  | tail -n 20 || true

echo 'Inspect the panel visually: exactly one icon should appear.'
