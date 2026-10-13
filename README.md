# SnapMark

A minimal GNOME-native screenshot annotation editor, made with **Python 3 + GTK4 + libadwaita**. No Qt dependency.

SnapMark is a *new* project, independent of Flameshot OCR. It preserves the native GNOME `Print Screen` UI. When GNOME creates a screenshot file, a lightweight background watcher detects it and opens a SnapMark editor window for annotation.

**Version:** v0.1.0, initial implementation / testing candidate. This is not a verified GNOME 50 production release.

## First-stage features

- GNOME native Print Screen handling is retained; SnapMark never takes over the key.
- Automatic editor opening on newly created screenshots in the GNOME Screenshots folder.
- Rectangle, ellipse, arrow, line, freehand pen and text annotation.
- Color palette, stroke width, fill opacity, undo/redo.
- Open existing images, fit/zoom/scroll, original-resolution PNG export, PNG clipboard copy.
- Native GNOME styling through libadwaita, inheriting appearance/accent from the system.
- AppImage **only** in GitHub Actions. No DEB package.

## How the capture bridge works

GNOME's Print Screen interface normally stores screenshots in the user's XDG Pictures/Screenshots folder. SnapMark watches that folder with `Gio.FileMonitor`. It waits for the new file to stop changing, and then opens the editor. No system hotkeys, GNOME settings or screenshot application internals are modified.

**Limitations:** If a screenshot is copied only to the clipboard without creating a file, directory monitoring will not see it. Some GNOME configurations save screenshots somewhere else: the detection path must then be adjusted or a later integration must be added. GNOME Wayland can prevent background applications from automatically receiving focus, even if a new editor window is presented. Both behaviors need actual GNOME 50 acceptance testing.

## Local development — Ryzen 7 6800H / Ubuntu GNOME Wayland

Install system runtime dependencies (no pip/virtualenv necessary):

```bash
sudo apt update
sudo apt install -y python3 python3-gi python3-cairo python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0
```

Run directly from the extracted project folder:

```bash
bash scripts/run-local.sh
```

Open an image:

```bash
bash scripts/run-local.sh --open="$HOME/Pictures/example.png"
```

Launch the screenshot watcher (keeps running and opens an editor after saved screenshots):

```bash
bash scripts/run-local.sh --watch
```

For per-user installation and login autostart:

```bash
bash scripts/install-local.sh
bash scripts/enable-autostart.sh
```

The autostart script installs a single desktop entry into `~/.config/autostart`, and starts monitoring this session. It does not modify GNOME's Print Screen shortcut. Disable future autostart with `bash scripts/disable-autostart.sh`.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+O | Open image |
| Ctrl+S | Save annotated PNG |
| Ctrl+C | Copy annotated PNG |
| Ctrl+Z | Undo |
| Ctrl+Shift+Z / Ctrl+Y | Redo |
| Ctrl+0 | 100% zoom |

Text tool: click the picture, enter the text and press Enter.

## Automated verification

Run static compilation and model tests locally:

```bash
/usr/bin/python3 -m compileall -q snapmark
/usr/bin/python3 -m unittest discover -s tests -v
```

CI runs these tests, launches the GTK application in Xvfb, assembles a GTK4/libadwaita AppDir, packages it using appimagetool, and checks that the produced AppImage starts in Xvfb. **Xvfb testing is not a substitute for real GNOME Wayland testing.** AppImage GTK4 bundling is experimental until verified in Actions and on the Ryzen 7 6800H machine.

### AppImage build

Ubuntu 24.04 is the baseline runner. The artifact and release asset consist **only of** `SnapMark-0.1.0-x86_64.AppImage`. Build from source with `bash scripts/build-appimage.sh` after installing the CI dependencies. On machines using another Python runtime, use the GitHub Actions build for the most reproducible result.

## Create the new GitHub repository

On the **Ryzen 7 6800H machine**, install and log into the GitHub CLI first (`gh auth login`), then from the *extracted SnapMark directory* run:

```bash
bash scripts/create-github-repo.sh
```

The script verifies the `yanjing-chen` account, refuses to overwrite an existing `yanjing-chen/SnapMark` repository, requests confirmation before creating a **public** repository, creates a local initial commit, and pushes `main`. It does not rewrite any existing Git history. The push triggers Actions automatically.

## Architecture

- `snapmark/app.py`: application lifecycle and command line, GTK single-instance process.
- `snapmark/editor.py`: native libadwaita editor UI, canvas gestures and image export.
- `snapmark/paint.py`: Cairo drawing and Pango text rendering.
- `snapmark/model.py`: independent annotations, undo/redo, zoom calculations.
- `snapmark/watch.py`: GNOME screenshot file monitoring.
- `scripts/assemble-appdir.py`: bundle Python, GI modules, GTK libraries and typelibs.

## Scope

Initial version concentrates on screenshot annotation and export. More tools, further preferences and separate OCR development can be evaluated later.

License: MIT.
