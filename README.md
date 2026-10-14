# SnapMark

SnapMark is a lightweight screenshot annotation editor for the GNOME desktop.
Built in **Python 3**, **GTK4 / PyGObject**, and **libadwaita**.

**Version:** v0.4.0 development candidate. Ubuntu GNOME 50 Wayland graphical
acceptance and the first v0.4.0 GitHub Actions AppImage build are not yet verified.

## Workflow

Press GNOME's normal **Print Screen**, select an area, and save the screenshot.
SnapMark monitors the screenshot directory and automatically opens the saved
image for markup. No system shortcut replacement is necessary. A file-only
monitor cannot detect a screenshot copied exclusively to the clipboard.

Alternatively, open a local image directly (Ctrl+O).

## Editor

- **Select** an annotation layer to move, resize, recolor, change text, or delete.
- **Arrow, rectangle, ellipse, line, triangle, pen** and **text**.
- **Highlight** translucent brush, **Mosaic**, **Blur** and annotation eraser.
- Custom stroke/fill colors via GTK color chooser; recent custom choices are stored.
- Undo/redo, editable layer list, adjustable properties panel, original-pixel PNG export.
- Copy screenshot as PNG (Ctrl+C), save PNG (Ctrl+S), fit/zoom and scrolling.

Blur is a rectangular non-destructive region filter (two-pass box blur). Its width
control sets the blur radius. It works with selection/layer history and preserves
original source pixels. Rendering a very large blur rectangle may be slower.

## General preferences

Open **Preferences** from the window menu (Ctrl+,):

- **Start automatically on login** — adds a user-level `.desktop` launcher.
- **Start minimized** — starts with no editor window *only when a status notifier
  host is available*. Otherwise it opens a window so the user can recover it.
- **Screenshot Folder** — choose a folder, or use the small revert icon in
  the same row to return to automatic GNOME screenshot-folder detection.

Preferences are stored in `$XDG_CONFIG_HOME/snapmark/preferences.json`
(or `~/.config/snapmark/preferences.json`).

## Status indicator

SnapMark implements the StatusNotifierItem interface, including a small icon
and basic menu actions: Open, Preferences, Quit. GNOME Shell does not always
show status indicators by itself: a compatible host such as the Ubuntu
AppIndicator/KStatusNotifierItem Shell extension must be enabled. Without a
host, the editor remains usable and the minimized preference never hides the
last recovery window. The indicator is not required for screenshot monitoring.

Use Ctrl+Q to quit the application, including its background watcher.

## Run locally (Ryzen 7 6800H, Ubuntu GNOME Wayland)

```bash
sudo apt update
sudo apt install -y python3 python3-gi python3-cairo python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0
bash scripts/run-local.sh
```

The app can stay running in the background. For an existing screenshot directory
watcher without an editor window use `bash scripts/run-local.sh --watch`.

To install locally for the current user (optional):

```bash
bash scripts/install-local.sh
bash scripts/enable-autostart.sh
```

## AppImage-only releases

GitHub Actions on Ubuntu 24.04 builds **only**
`SnapMark-0.4.0-x86_64.AppImage`. It bundles Python, GTK4, libadwaita,
GI typelibs and image loaders. It does not build DEB packages.

```bash
python3 -m compileall -q snapmark
python3 -m unittest discover -s tests -v
```

The workflow also performs an Xvfb GUI smoke test. This is not a substitute
for a real GNOME Wayland test. The AppImage needs a usable desktop session.

## Shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+O | Open image |
| Ctrl+C | Copy annotated PNG |
| Ctrl+S | Save annotated PNG |
| Ctrl+Z | Undo |
| Ctrl+Shift+Z / Ctrl+Y | Redo |
| Ctrl+0 | Actual size |
| Ctrl+, | Preferences |
| Ctrl+Q | Quit app and watcher |
| Delete / Backspace | Delete selected annotation |

## Code structure

- `snapmark/app.py` — one-instance application and watcher lifecycle.
- `snapmark/tray.py` — D-Bus status indicator, no GTK3 required.
- `snapmark/editor.py` — GTK4 UI, tools, layers, file dialogs.
- `snapmark/model.py` — geometry and undo/redo snapshots.
- `snapmark/paint.py` and `snapmark/filters.py` — Cairo rendering and blur.
- `snapmark/watch.py`, `snapmark/screenshot_paths.py` — GNOME screenshot detection.
- `snapmark/preferences.py` — settings and autostart launcher.
- `.github/workflows/appimage.yml` — test and AppImage CI.

Copyright © SnapMark contributors. License: MIT.
