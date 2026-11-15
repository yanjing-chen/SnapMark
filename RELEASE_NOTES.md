# SnapMark v1.1.2 — Stable release

SnapMark 1.1.2 is the native GNOME screenshot editor, annotation and optional local Ollama OCR release. It promotes the 1.1.2-rc3 source to a stable release, without replacing any earlier GitHub tag.

## Changes since v1.1.1

- Fix duplicate status indicator icons on Ubuntu GNOME 51 / Wayland. The native DEB/AppImage register the existing `/StatusNotifierItem` object path, rather than requesting an extra status notifier bus name. The single-icon fix was confirmed on the user's Ryzen 8845HS.
- Add image-only clipboard monitoring using GTK4's event-driven formats and MIME stream reading. Images copied from a webpage can be opened by the status menu action **编辑/识别当前图片** / **Edit/Recognize Current Image**. OCR remains a separate, manually initiated action in the editor.
- Keep the status-menu action available when clipboard image monitoring is enabled, reconcile clipboard content on demand, and provide a visible message if no image is readable. The implementation handles Wayland focus-delivery retries, bounded stream reads, and duplicate content without periodic background polling.
- Pure text, link, and HTML-only clipboard content is not read or recorded. The clipboard image monitoring setting can be disabled independently of GNOME screenshot file monitoring.
- Retain the original file event watcher, ScreenshotSession expiry behavior, OCR model management, and Ollama keep-alive settings.
- Distribute both native system-GTK4 DEB and x86_64 AppImage (host GTK preferred with bundled fallback).

## Release files

- `SnapMark-1.1.2-x86_64.AppImage`
- `snapmark_1.1.2-1_amd64.deb`
- `SnapMark-1.1.2-Full-Source.zip`
- `SHA256SUMS.txt`

## Environment and verification

Ubuntu 26.10 / GNOME 51 / Wayland is the target environment. The single-tray fix was accepted on the user's 8845HS. Automated unit tests and Xvfb smoke checks do not replace real Wayland clipboard or AppImage usability testing. This release does not install or change Ollama, OCR models, GPU drivers, or desktop extensions.
