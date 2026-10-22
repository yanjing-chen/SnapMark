# SnapMark 1.0.0 — Release notes / 发布说明

Stable GTK4/libadwaita screenshot editing and annotation for GNOME Wayland.

- Base editor with annotation layers, PNG copy/save, clipboard image and screenshot history.
- GNOME system screenshot selection remains native and separate.
- GNOME tray menu: Open, Open Clipboard Image, Screenshot History, Preferences, Restart, Quit. About is in Preferences only.
- Optional OCR **1.0.2** and Translation **1.0.2**: full streaming preview with automatic following and manual scroll interruption/resumption; validated results are editable and copyable/savable.
- Bilingual UI: English and Simplified Chinese.
- Optional external shared Local AI Runtime **1.0.0**; not bundled and not altered by this release.

**Frozen official plugin SHA256:**

- `SnapMark-ocr-1.0.2.zip`: `b46bcb2358368ab39b5170da0a73b7de6d8c755a451eb5c8d904fad5226afca4`
- `SnapMark-translation-1.0.2.zip`: `bb864f36dbd7b01c9c55681c427be5e52238dc153ad7fe1c6ef8883cf6bc7289`

The two archives are identical to the C3 v5 validated plugin build; do not change or re-version them. Translation requires enabled OCR 1.0.2. The AppImage checksum is produced from the actual verified AppImage build artifact, never guessed. No Flatpak is distributed in 1.0.0.

The central `snapmark-v1.0.0` release provides only the validated AppImage, source archive and both frozen 1.0.2 plugins. Separate `ocr-v1.0.2` / `translation-v1.0.2` release tags are also necessary for in-app online plugin discovery.

**Note**: Release engineering is distinct from GitHub publication. Do not claim a release is available until its GitHub page and asset checksums have been verified.
