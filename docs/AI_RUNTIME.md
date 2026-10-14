# SnapMark AI Runtime Integration — v0.6.0-B1

This is a **read-only integration** with the independent project
[Local AI Runtime](https://github.com/yanjing-chen/local-ai-runtime).
SnapMark never modifies `~/.config/local-ai-runtime`, downloads models, installs
GPU drivers, starts/stops other applications' services, or alters the external
Runtime's global accelerator preferences.

## Preferences → AI Runtime

- Off by default. Enabling the switch permits a background connection check;
  disabling only stops further SnapMark integration and never shuts down Runtime.
- Default URL: `http://127.0.0.1:8111` (can be edited).
- **Save & Check** reads `/health`, `/v1/runtime/backends`, and
  `/v1/models?refresh=1`. Non-health endpoints may be unavailable; show a
  partial status rather than invent model names or GPU details.
- Backend preference defaults to **Auto**. CPU, Vulkan, and CUDA are recorded as
  SnapMark preferences only. They are **not applied** to the shared Runtime in
  v0.6.0-B1. Actual backend must come from Runtime's own status; hardware
  presence alone does not prove CUDA/Vulkan can run a selected model.
- View instructions opens the Runtime project's repository in the browser.
  One-click verified Runtime installation and model registration are still
  outstanding B2 work; no install/import UI should pretend to have succeeded.

SnapMark stores only its own integration settings at
`$XDG_CONFIG_HOME/snapmark/ai-runtime.json` (mode 0600). The external Runtime's
configuration/model registry/service remains untouched.

## Error handling and acceptance

- HTTP calls run on a worker thread; GTK is updated by GLib's main loop.
- On connection failure, display the reason without crashing or blocking
  screenshot editing. Stale callbacks from previously selected endpoints are
  ignored. Disabled integration does not contact the service.
- Run unit tests and GUI `--smoke-test`; real GNOME Wayland acceptance must
  confirm connecting to an existing v0.8.0 Runtime, reading the model list,
  and ensuring a switch-off leaves Runtime running.

## Future

v0.6.0-B2: verify a concrete signed/checksummed Runtime release installer and
its model registration API, then add an optional guided installer and safe local
model import. Advanced OCR and Translation will later request specific models
and backend behavior without silently changing a shared service globally.
