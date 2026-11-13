# SnapMark v1.1.1 — Stable Release

This stable release retains the **SnapMark v1.1.0 application behavior** including
GNOME screenshot file monitoring, GTK clipboard change notifications, time-limited
tray access, in-editor manually triggered OCR, annotations and Ollama model handling.
No background screenshot clipboard polling has been introduced.

## Packaging improvements

- **Native DEB (`amd64`)** for Ubuntu/GNOME. Uses system Python, PyGObject,
  GTK4, libadwaita and Cairo. Its release-candidate equivalent has been
  tested successfully on a Ryzen 8845HS machine.
- **AppImage (`x86_64`)** prefers a compatible system GTK4/Python runtime
  and falls back to bundled runtime where needed. Explicit modes can be selected
  using `SNAPMARK_APPIMAGE_GTK_MODE=auto|system|bundled`.
- **Full source archive and SHA256SUMS.txt** accompany the binaries.
- Ollama, OCR model weights and GPU drivers remain separate and untouched.

This version is **stable** (not a pre-release). The AppImage's host/bundled runtime
modes are exercised in GitHub Actions using Xvfb, but actual GNOME/Wayland and
GPU-specific validation should continue across hardware configurations.
