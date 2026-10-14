# SnapMark plugin packaging contract — API v1 (v0.6.0-A1)

This is the *foundation* of the interface for official executable Python
plugins. There are no OCR or Translation release packages yet. **Not a general
third-party plugin marketplace.** Untrusted Python plugins can execute with
the same permissions as SnapMark; a SHA256 checksum is not a digital signature.

## Official ZIP archive

`plugin.json` must be in the archive root (all files under the package root):

```json
{
  "id": "ocr",
  "version": "0.1.0",
  "api_version": 1,
  "min_host_version": "0.6.0",
  "dependencies": {},
  "entrypoint": "main:register"
}
```

For Translation, include `"dependencies": {"ocr": "0.1.0"}`.

ZIP archive constraints: max 20 MiB compressed, max 40 MiB total unpacked,
max 350 entries, regular files and directories only, no symlinks or path
traversals. This is deliberately a *code-only* package, not a model bundle.

For OCR v0.1.0, official GitHub Release tag **`ocr-v0.1.0`** contains:

- `SnapMark-ocr-0.1.0.zip`
- `SnapMark-ocr-0.1.0.zip.sha256`

Translation follows the same pattern under tag `translation-v0.1.0`.
Checksum sidecar format: `sha256sum SnapMark-ocr-0.1.0.zip` output.
Only official `yanjing-chen/SnapMark` releases (not drafts/prereleases) are
offered in the manager. An initial empty list means packages are not published.

## Runtime registration

Plugin's `main.py` exposes `def register(host): ...`; the host supports:

```python
def register(host):
    host.register_toolbar_action('ocr', 'OCR', callback)
    host.register_preferences_page('ocr', 'OCR', build_preferences_page)
    host.register_result_panel('ocr', 'OCR Result', build_result_widget)
```

The callbacks and builders above are **supplied by the plugin**, and execute
on the GTK main thread. `build_preferences_page(editor)` must return a GTK4
widget (usually `Adw.PreferencesPage`); `build_result_widget(editor)` returns a
GTK4 widget. Buttons should not invoke blocking model inference on GTK's main
thread. A future API revision will need to version-control changes to these
signatures; plugins must declare compatible API and minimum host version.

Once a plugin is activated, restart SnapMark to load its code and UI safely.
Disabling OCR makes Translation unavailable without erasing its settings.
Plugin archives are stored under `$XDG_DATA_HOME/snapmark/plugins/<id>/<version>`.
Configuration is under `$XDG_CONFIG_HOME/snapmark/plugins.json`. Installer
never adds system packages, runs scripts from ZIPs, or modifies Runtime.

## Planned before the first plugin release

- Improve plugin-process isolation and ensure installation remains transactional
  across power loss and concurrent instances.
- Verify the interface on actual GNOME Wayland and within AppImage.
- Confirm GitHub Release tags/asset names with the packaging workflows.
- Support a clean restart prompt instead of requesting users to reopen manually.

See README.md Roadmap for all post-v0.6.0 features (PP-OCRv5/v6 refresh,
Advanced OCR, runtime models, OCR-result translation).
