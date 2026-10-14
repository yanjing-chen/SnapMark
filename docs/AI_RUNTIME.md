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

## v0.6.0-B2-A: read-only model state and local GGUF bundle inspection

`/health` provides `runtime_version`, `backend_preference`, `backend_running`,
`active_backend`, and `current_model`. These are independent from the **backend
reported by** `/v1/runtime/backends`, which is not evidence of an *active*
inference process. Models returned by `/v1/models?refresh=1` have separate
`installed` and `capabilities` fields. A model marked `installed: true` is not
necessarily loaded or currently capable of serving inference requests.

**Choose model files** accepts multiple `.gguf` files. **Choose model folder**
inspects a single directory (no recursion). Models are grouped by matching
names: a main `.gguf` plus any matching `-mmproj.gguf` are one logical model,
and a `-00001-of-00003.gguf` split sequence is checked for missing parts.
Inspection reads only each file's `GGUF` header and metadata from its filename,
not the complete GGUF payload. It does NOT prove compatibility, integrity, or
inference success. Ambiguous names, missing projectors, split parts or differing
quantizations require manual review rather than automatic pairing.

This preview does not copy, download, overwrite, register, or execute model
files. The existing Runtime model registry and global backend preference are
left untouched. Runtime 0.8.0 registration API, release download URL and
checksum must be verified before B2-B can provide an actual **Register** or
**Install Runtime** action. No dummy button claims success.

## v0.6.0-B2-B: confirmed local-model registration

Runtime source revision `3d9c8dd` (0.8.0) has `POST /v1/models/inspect`
(non-mutating) and `POST /v1/models/custom` (registry **upsert**, mutating),
with `GET /v1/models/custom` and `GET /v1/models?refresh=1` for collision
checks. It supports `model_path` and `mmproj_path` on a single logical model.

After selecting a local GGUF bundle, click **Inspect with Runtime…** to query
Runtime's inspector. Inspection is not registration. A review dialog lists the
proposed model ID, type, main GGUF, projector path, context and GPU layers.
Clicking **Register model** explicitly opts into an external Runtime registry
change. All network operations run in background threads; no model weights
are downloaded, moved or copied, and Runtime's global backend preferences and
running service are not intentionally changed. A newly registered model is
not automatically loaded.

To prevent unintentional overwrites, the first implementation allows only new
IDs. Both catalog and custom registries are checked before inspection and
again just before registration, and source-file size/mtime must be unchanged.
**Note:** Runtime's registration API is an *upsert*, not an atomic create-only
API; concurrent changes by a different client in the small interval between
check and POST are not completely preventable. This is not a guaranteed
transactional lock across processes.

Registration intentionally requires a **local HTTP loopback** endpoint (not
remote URLs or HTTPS) because the service must access the selected local file
paths. Projector bundles with multiple ambiguous projectors or split GGUF
weights are preview-only pending proven Runtime compatibility. Installed
catalog models are never overwritten by this flow.

Runtime **one-click installation remains deferred** until a concrete stable
installer/download and digest verification policy is known. The standalone
Runtime installation remains under user control.
