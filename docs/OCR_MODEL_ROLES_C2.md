# SnapMark C2 — OCR / Translation model-role separation (candidate)

Editor layout:
- OCR Run OCR button stays in upper-right; the independent Time label is on the lower-right action row before Copy/Clear/Save.
- Translation has a registered translation-model selector at the top, a separate target-language selector and Translate button, and an independent bottom Time label before Clear translation/Copy/Save.
- One OCR plugin = full width; OCR+translation = draggable half/half split. Initial canvas/side-property dividers are calculated after GTK maps widgets, not from fixed pixel sizes.

Model eligibility:
- Preferences → OCR selects `Lightweight OCR` or `High-performance Runtime OCR`, never both menus at once.
- Lightweight models are accepted only when explicitly registered in OCR Preferences and both expected local detection/recognition folders and the configured Python interpreter exist. Registration does not download any files. This release does not yet implement the model installation/downloading GUI; users provide local files in Preferences.
- High-performance OCR names are discovered read-only from the local Runtime `/v1/models` list only if `installed: true`, `capabilities.ocr: true`, and if `type` is given it must be `ocr`. **Runtime high-performance OCR inference is not implemented in this patch**; Run OCR explains this. Runtime must remain unchanged.
- Translation names are likewise fetched from the local Runtime only if `installed: true`, `capabilities.translation: true`, and if `type` is given it must be `translation`. OCR-only models are never included. Selection is saved and revalidated immediately before translation. Source language is automatically detected by the model.
- SnapMark editor never installs, downloads or registers models. Local lightweight OCR registration and mode are on Preferences → OCR; Runtime GGUF registration is on Preferences → AI Runtime.

Changes in this patch are intentionally staged before any real Code01 operations. GTK behavior and real Runtime inference must be tested on Code01 before declaring release readiness.
