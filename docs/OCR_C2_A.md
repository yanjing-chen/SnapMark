# SnapMark C2-A: local lightweight OCR plugin (development candidate)

**This is an intermediate development stage, not a completed v0.7 release.**

The code-only OCR plugin lives in `official_plugins/ocr` and is delivered as an
independent `SnapMark-ocr-0.1.0.zip` plugin archive through the existing
official PluginManager API v1. The ZIP is a LOCAL test package: do not upload
the same tag as a published release before GUI, model, and security acceptance.

## User workflow

1. Install/enable the LOCAL OCR plugin explicitly; restart SnapMark.
2. Open a screenshot. Use toolbar `OCR` for the full original image, or use
   **Select region** below the image to drag a rectangle in image coordinates.
3. The plugin displays results in a resizable bottom panel. Text is editable.
   Re-OCR appends instead of overwriting text; `Clear text` requires confirmation.
4. **Copy text** places the current text on the clipboard; **Save TXT…** saves
   UTF-8 text. The timer reports OCR inference only (seconds to 2 decimals).

## Isolated PP-OCR requirements

This phase will *not* use or modify `local-ai-runtime` (port 8111), its Python,
models, systemd unit, or its CPU/Vulkan/CUDA packages.

The OCR worker needs a separate Python interpreter with PaddleOCR 3.7+ and a
compatible local PaddlePaddle CPU runtime, supplied by the user or by a later
verified installer. It executes from the plugin folder, not on GTK main thread.
Default configured Python path:

`~/.local/share/snapmark/ocr-venv/bin/python`

Default offline model directory:

`~/.local/share/snapmark/ocr-models/`

For each chosen pair, place the official PaddleOCR **inference** model files in
both named folders. No folders are created or models downloaded automatically.

| Dropdown option | Detection folder | Recognition folder |
|---|---|---|
| PP-OCRv5 mobile | PP-OCRv5_mobile_det | PP-OCRv5_mobile_rec |
| PP-OCRv5 server | PP-OCRv5_server_det | PP-OCRv5_server_rec |
| PP-OCRv6 tiny | PP-OCRv6_tiny_det | PP-OCRv6_tiny_rec |
| PP-OCRv6 small | PP-OCRv6_small_det | PP-OCRv6_small_rec |
| PP-OCRv6 medium | PP-OCRv6_medium_det | PP-OCRv6_medium_rec |

Both full paths can be adjusted in **Preferences → OCR**. The worker checks
that both folders exist and contain files before importing PaddleOCR. Default
PaddleOCR document unwarping and orientation pipelines are explicitly disabled
to prevent third-party default model retrieval. The model installation and
verified online catalog remain C2-B work.

## Boundaries and known limitations

- Plugin code runs with SnapMark's user rights; only install self-built or
  official trusted packages. SHA256 verifies bits, not the publisher's identity.
- The PaddleOCR environment and model weights are **not** included in the ZIP.
- Local worker API uses PaddleOCR 3.x `PaddleOCR.predict()` and extracts
  `rec_texts` from its JSON result. Concrete model compatibility needs Code01
  live CPU acceptance before marking it production ready.
- Cancellation terminates this one worker process; it does not stop Runtime.
- OCR is source image only; annotations are neither submitted nor removed.
- Translation, model catalog refresh and advanced Runtime OCR are later stages.

## Packaging / activation

After applying the Code01 development patch and passing all regression tests:

```bash
cd ~/下载/SnapMark-v0.6.0-B1-BbXPkFje
python3 scripts/build-ocr-plugin-c2.py --output ~/下载
```

An opt-in local installation helper is shipped alongside the patch. It copies
only the plugin code to the SnapMark user plugin directory and updates
SnapMark's own `plugins.json`. It never writes to Local AI Runtime.
