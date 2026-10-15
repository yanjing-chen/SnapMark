# SnapMark

SnapMark is a lightweight screenshot annotation editor for the GNOME desktop.
Built in **Python 3**, **GTK4 / PyGObject**, and **libadwaita**.

**Version:** v0.6.0-A1 development candidate (plugin framework, not the completed
v0.6.0 release). GUI acceptance on Ubuntu GNOME Wayland and AppImage CI for this
candidate remain unverified. Earlier v0.5.0 editing features are preserved.

## Workflow

Press GNOME's normal **Print Screen**, select an area, and save the screenshot.
SnapMark monitors the screenshot directory and automatically opens the saved
image for markup. No system shortcut replacement is necessary. A file-only
monitor cannot detect a screenshot copied exclusively to the clipboard.

Alternatively, open a local image directly (Ctrl+O).

## Editor

- **Select** an annotation layer to move, resize, recolor, change text, or delete.
- **Arrow, rectangle, ellipse, line, triangle, pen** and **text**.
- **Highlight** has Freehand and Straight line modes in the right properties panel above Color; **Mosaic**, **Blur** and the eraser remain available.
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

## Official plugin manager — v0.6.0-A1 development

Preferences → **Plugins** manages two optional official plugin IDs: **OCR**
and **Translation**. No model or Local AI Runtime is installed by this step.
Click **Refresh** to check published releases in the official SnapMark repository,
then choose a release, **Install**, and **Use Version** to enable it.
You may keep multiple compatible versions installed, select older ones or
uninstall versions. Disabling OCR also makes Translation unavailable without
deleting its saved selection. Translation needs an enabled OCR plugin.
Reopen SnapMark after changes to reload plugin buttons/pages/result views.

Official plugin tags will use `ocr-vX.Y.Z` and `translation-vX.Y.Z`, with
`SnapMark-ocr-X.Y.Z.zip` / `SnapMark-translation-X.Y.Z.zip` and adjacent `.sha256`
assets. **These packages have not yet been published**, so Refresh can
legitimately return zero versions. The manager validates file integrity,
manifest API/dependencies and ZIP paths before installing into
`$XDG_DATA_HOME/snapmark/plugins` (default `~/.local/share/snapmark/plugins`).
It loads plugin code only once explicitly enabled at app startup. Installing
an executable Python plugin is inherently privileged at the user's own account
level; install only releases from the trusted project repository.

The code includes an extension API for toolbar actions, custom preferences
pages and result panels; actual OCR/Translation implementations come in later
versions. Runtime integration and its separate Preferences page are scheduled
for v0.6.0-B and are **not implemented in A1**.

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
`SnapMark-0.6.0-a1-x86_64.AppImage`. It bundles Python, GTK4, libadwaita,
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
- `snapmark/plugins.py`, `snapmark/plugin_host.py`, `snapmark/plugin_ui.py` — plugin manager and extension API.
- `.github/workflows/appimage.yml` — test and AppImage CI.

Copyright © SnapMark contributors. License: MIT.

## v0.4.1 editing improvements

- The image eraser clears original image pixels to transparent PNG pixels (undoable).
- The blur and mosaic filters respect the Opacity slider.
- Custom colors use a compact four-color picker button.
- Preferences are non-modal; GNOME system file chooser dimming while open is normal.
- A tray host may be required to display StatusNotifierItem icons on GNOME.

## v0.5.0 highlight mode and Save button

- **One Highlight toolbar tool**: Freehand draws along mouse movement, while
  Straight line keeps the start and end points. Change modes above the Color
  options. Both retain color, width, opacity, layer editing, and undo/redo.
- **Save** uses the libadwaita blue suggested-action style.

## Roadmap

*A checkbox is marked complete only after the corresponding implementation and
applicable tests pass. GUI/Wayland and GitHub CI acceptance remain pending until
verified on the target machine. The Roadmap is updated with each release.*

### v0.6.0 — Plugin foundation and Local AI Runtime

- [x] **A1:** Official plugin ZIP manifest schema and API v1.
- [x] **A1:** Official GitHub release discovery; manual install and version selection.
- [x] **A1:** SHA256 checks, safe ZIP extraction, version coexistence and uninstall.
- [x] **A1:** Enable/disable, OCR prerequisite for Translation, dependency checks.
- [x] **A1:** Plugin hooks for toolbar actions, preferences pages, result panels.
- [x] **A1:** README Roadmap and offline plugin regression tests.
- [ ] **A:** Complete real GTK / GNOME Wayland GUI and AppImage smoke acceptance.
- [ ] **A:** Publish the first official OCR/Translation plugin ZIPs and checksum assets.
- [ ] **A:** Verify release selection, upgrade, downgrade and rollback with published assets.
- [ ] **B:** Preferences → AI Runtime, default-off integration toggle.
- [ ] **B:** Detect/connect existing Runtime at `http://127.0.0.1:8111`.
- [ ] **B:** Verify real Runtime APIs for model listing/registration/backend status.
- [ ] **B:** Optional Runtime installer **without** bundled AI models; avoid changing running services.
- [ ] **B:** Runtime installation/connection error and recovery tests.


<!-- SNAPMARK_RUNTIME_B1_ROADMAP -->
**v0.6.0-B1 progress — code complete, real-desktop validation pending:**

- [x] Separate Preferences → AI Runtime page; integration disabled by default.
- [x] Connect to existing `127.0.0.1:8111` via read-only API calls.
- [x] Display service health, registered models, and Runtime-reported backend.
- [x] Auto backend preference by default; no global backend changes.
- [x] Integration settings stored independently; disable never stops Runtime.
- [x] Offline tests for connection failures, bad URLs and configuration safety.
- [ ] **B1 acceptance:** GNOME Wayland GUI, live Runtime 0.8.0 API, and AppImage CI.
- [ ] **B2:** Verified Runtime installer, safe local-model registration and related tests.

See `docs/AI_RUNTIME.md` for supported API calls and current limitations.


<!-- SNAPMARK_RUNTIME_B2A_ROADMAP -->
**v0.6.0-B2-A — developed; real GNOME Wayland / AppImage acceptance pending:**

- [x] Separate model installed state from loaded model and actively running inference backend.
- [x] Display Runtime 0.8.0 health and actual active backend (when running).
- [x] Local GGUF multi-file and folder selection; group main + mmproj + split shards.
- [x] Offline completeness checks, read-only preview and regression tests.
- [x] Read-only Runtime OpenAPI registration diagnostics.
- [ ] **B2-A acceptance:** GNOME Wayland GUI and GitHub Actions AppImage.
- [ ] **B2-B:** Verify Runtime 0.8.0 write API and install artifacts/checksums.
- [ ] **B2-B:** Implement real model registration and optional verified Runtime installer.

The current model-file chooser is a **preview, not a model registration**.
No model is uploaded, downloaded, or changed. See `docs/AI_RUNTIME.md`.

### v0.7.0 — Lightweight OCR plugin

- [ ] PP-OCRv5 **and** PP-OCRv6, with model-family and model/size/language selection.
- [ ] Separate dependency environment and process; CPU operation without Runtime.
- [ ] Whole-image and original-pixel selected-region OCR even after zoom.
- [ ] Model list **Refresh Models** from independently updated online catalog.
- [ ] Scheduled, verified catalog synchronization; offline cache and compatibility checks.
- [ ] User-confirmed model download; v5 and v6 coexist and function offline.
- [ ] Editable OCR text (correct, add, paste, delete) and original/annotation separation.
- [ ] Bottom resizable OCR panel; copy/save TXT, protect edits on re-OCR.
- [ ] OCR elapsed time independently in seconds, two decimals.

### v0.8.0 — Advanced OCR plugin

- [ ] Lightweight / Advanced selection and shared editable result panel.
- [ ] Connect existing Local AI Runtime, choose compatible user-loaded OCR model.
- [ ] No automatic PaddleOCR-VL 1.6 download.
- [ ] Backend capabilities CPU/Vulkan/CUDA where actually supported.
- [ ] Per-model prompt, temperature and streaming controls, capability-guarded.
- [ ] Request cancellation, timeouts, loading and inference errors.

### v0.9.0 — Translation plugin (requires OCR)

- [ ] Independent official ZIP and compatibility/dependency checks.
- [ ] Translate **current edited OCR text**, including manually added/pasted text.
- [ ] Translate button exists only inside the OCR result panel.
- [ ] User-selected translation model in existing Runtime, no automatic download.
- [ ] Source/target language, prompt, temperature and streaming settings.
- [ ] Independent Translation elapsed time and error/cancellation handling.

### v0.10.0 — OCR + Translation integration

- [ ] OCR-only single result area; with Translation, resizable two-column source/target.
- [ ] Separate copy/save actions for source and translation.
- [ ] Source edits mark translation stale; explicit Translate refresh, not automatic.
- [ ] Streaming display, editable text survives compatible plugin upgrades.
- [ ] **No combined OCR + Translation time**; each is displayed separately.

### v1.0.0 — Stable release and QA

- [ ] Screenshot monitoring, layers, markup, undo/redo, copy/save regression.
- [ ] GNOME Wayland manual acceptance; verify AMD 680M and NVIDIA where available.
- [ ] Multilingual OCR/translation (Chinese, English, Dutch), large-image/long-text tests.
- [ ] Plugin security, upgrades/downgrades, Runtime disconnect/reconnect, model cache.
- [ ] GitHub Actions AppImage build + bundled startup smoke; release documentation.

**Publishing:** single `yanjing-chen/SnapMark` repository. Main program tags
`snapmark-vX.Y.Z` produce **AppImage only**, while `ocr-vX.Y.Z` and
`translation-vX.Y.Z` produce independent **ZIP** plugins with `.sha256` files.
No DEB/RPM, no embedded advanced AI models.

<!-- SNAPMARK_RUNTIME_B2B_ROADMAP -->
**v0.6.0-B2-B — local registration implemented; real GNOME/Runtime acceptance pending:**

- [x] Verify Runtime 0.8.0 `/v1/models/inspect`, `/v1/models/custom` and `mmproj_path` contracts from source/tests.
- [x] Local-only GGUF inspection using Runtime's own metadata/compatibility analyzer.
- [x] Display model ID, purpose, main file, mmproj and settings before registration.
- [x] Separate, explicit user confirmation for a Runtime registry write; never copy/download models.
- [x] Reject existing model IDs; reject changed files, ambiguous bundles and unverified GGUF shards.
- [x] Refresh registered models after successful registration.
- [x] Automated fake-Runtime regression tests for inspect/register/duplicate/race safeguards.
- [ ] **B2-B acceptance:** Confirm main GGUF + mmproj registration on the real Ryzen 7 6800H Runtime 0.8.0; GitHub Actions AppImage.
- [ ] **B2-C:** Optional safe one-click Runtime installation after verifying official release artifact checksums, supported platform, and upgrade strategy.

This action is opt-in: **Inspect with Runtime… → Review → Register model**. Registration updates the external Local AI Runtime registry only after explicit confirmation; the files remain where the user selected them. It never auto-loads a model or modifies global CPU/Vulkan/CUDA preferences. See `docs/AI_RUNTIME.md`.

<!-- SNAPMARK_B2C1_ROADMAP -->
### v0.6.0-B2-C1 — Runtime lifecycle/status (local acceptance pending)

- [x] Read `/health` `startup_preload`, `idle_unload_seconds` and loaded model separately.
- [x] Display accurate **startup preload / idle unload / running model** status in Preferences → AI Runtime.
- [x] Identify a connected existing Runtime and recommend reusing it; do not install twice.
- [x] Show the official releases page and keep installation explicitly opt-in.
- [x] Add lifecycle parsing and UI regression checks without modifying Runtime configuration.
- [ ] **Real GNOME Wayland acceptance** on Ryzen 7 6800H and GitHub Actions AppImage test.
- [ ] **B2-C2:** Verify official release packages, checksums, installation and rollback procedure before enabling one-click installation.
- [ ] **B2-C2:** Confirm Runtime 0.8.0 supported idle-unload / startup-preload *write* API and global-setting consent policy, then expose editing controls.
- [ ] **v0.8 / v0.9:** Advanced OCR / Translation request their remembered models on demand; verify auto-switch and idle release in real inference.

**Default policy:** No model is preloaded by SnapMark; Runtime owns the inference
backend and idle unloading. Reading status does not change the shared Runtime.
`0` idle seconds is displayed verbatim, without assuming that it means
"immediate" or "disabled". Models and Runtime are never downloaded automatically.


<!-- SNAPMARK_RUNTIME_B2C2_IDLE_ROADMAP -->
### v0.6.0-B2-C2 — custom idle-unload time (source candidate)

- [x] Implement a strictly opt-in, single-field Runtime 1.0.0+ preferences client.
- [x] Add the 0–86400-second timeout editor under Preferences → AI Runtime.
- [x] Require explicit confirmation; 0 disables automatic model unloading.
- [x] Preserve Runtime 0.8.0 read-only behavior and validate version/API support.
- [x] Verify the request's response, persisted preference, and live manager status.
- [x] Test consent, old-version refusal, stale settings, invalid values, and error paths with a local fake HTTP server.
- [ ] **Code01 acceptance:** full existing tests and GNOME Wayland UI acceptance.
- [ ] **Real 1.0.0 acceptance:** after SnapMark's separately approved Runtime 0.8.0 → 1.0.0 upgrade,
      confirm timeout persists, dynamically changes, and does not affect screenshot editing.

B2-C2 does not install/upgrade Runtime, select a backend, preload/unload a model,
or push to GitHub. Installation and rollback remain a separately gated next phase.
