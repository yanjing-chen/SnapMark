# SnapMark 1.1.2 – Ubuntu GNOME 51 single-tray fix (retained)

Base: complete v1.1.1 source. The user verified that the application is launched only once;
Ubuntu's `ubuntu-appindicators@ubuntu.com` extension may show **two indicators** for
the same D-Bus exported `/StatusNotifierItem` object. This is a registration / discovery
identifier mismatch, not two startup entries.

## Minimal program fix

In `snapmark/tray.py`, native DEB/AppImage instances no longer acquire
`org.freedesktop.StatusNotifierItem-<pid>-1` on GApplication's shared D-Bus connection.
The app exports the existing object at `/StatusNotifierItem` and registers the **path**
with the status notifier watcher. On Ubuntu's extension the registration resolves to
`bus.get_unique_name()@/StatusNotifierItem`, matching its brute-force scanner.

Flatpak registration retains `io.github.yanjingchen.SnapMark.StatusNotifierItem` and
its existing RequestName behavior. The original rc1 tray patch itself did not alter autostart, screenshot, image, OCR or
settings logic. Version rc2 adds a separate clipboard image filter and setting.

## Regression and limitations

`tests/test_single_tray_registration.py` exercises the actual TrayIndicator.start,
_register, and stop methods with an isolated mock session bus and models Ubuntu's
indicator-id calculation. It covers native, Flatpak, and watcher restart paths.
Run `python3 -m unittest discover -s tests -v` and `bash scripts/smoke-tray-8845hs.sh`.

This packaged source is the **v1.1.2 stable release** based on the rc3 candidate.
Previously published v1.1.1 tags and assets are retained. It has not been validated in a real Ubuntu 26.10 GNOME 51 Wayland
session from this environment; tests must be completed on the user's 8845HS.

Real-world checks: log out and sign back in after installing DEB; verify one indicator,
one running SnapMark process, valid SNI properties, menu functions including OCR,
and no `Using Brute-force mode for StatusNotifierItem io.github.yanjingchen.SnapMark`.

The behavior of KDE/Ayatana SNI host implementations and Flatpak needs separate
hands-on acceptance; the GNOME extension path-style registration is supported,
but independent host implementations can differ.
