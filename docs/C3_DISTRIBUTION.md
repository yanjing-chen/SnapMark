# SnapMark C3 1.0.0 distribution contract

This document describes release engineering and is not a claim of an already-published GitHub release.

- **Frozen versions:** SnapMark 1.0.0; OCR **1.0.2**; Translation **1.0.2**; shared optional Runtime 1.0.0.
- Host source is feature-frozen following 8/8 Code01 GNOME Wayland GUI acceptance on 2026-10-22.
- The base AppImage includes no plugins, model files, runtime binaries or user preferences. Users install optional verified ZIPs separately.
- Translation 1.0.2 requires OCR 1.0.2. Freeze ZIP digests rather than rebuilding changed plugin code under the same version.
- Plugin manager online Refresh expects GitHub release tags `ocr-v1.0.2` and `translation-v1.0.2`, with matching ZIP and `.sha256` assets. The main `snapmark-v1.0.0` release may also provide both ZIP files for convenience.
- `snapmark-v1.0.0` must **not** be pushed until the legacy tag-triggered AppImage workflow has had automatic publish logic removed in its tagged commit.
- Use a dedicated release candidate branch `release/snapmark-v1.0.0`, not a force push to `main`. Build and smoke-test the AppImage before publication; Flatpak is not distributed.
- Runtime 1.0.0 is externally shared. Do not package, reinstall, stop or alter it as part of base SnapMark release engineering.
- User data, installed plugins, caches and existing local worktrees must not be edited by release staging.
- Two UI languages only: English and Simplified Chinese.

Run source tests and staged builds on Code01 or in CI. Validate true Wayland indicator restart, optional plugins, portal/file access, editor operations and streaming previews for AppImage, not just source checkout.
