# C2 OCR: hosted ONNX build and simplified Preferences

This stage changes **Preferences → OCR** to a two-mode simplified page and adds
GitHub Actions build candidate for Linux x86_64 ONNX dependencies.

- Main SnapMark remains Python 3.14 / GTK4.
- Do **not** run PaddlePaddle compilation/installation on Code01.
- GitHub Actions builds a Node/ONNX component archive using prebuilt
  ONNX Runtime bindings and `esearch-ocr`, using native dependencies installed
  **on the GitHub runner**.
- The published artifact is **not yet a tested OCR engine**: image/model adapters,
  ONNX model ZIP validation and actual GNOME Wayland recognition tests must be
  completed before enabling `Download…` in the lightweight UI.
- The existing Python OCR worker is retained in the code for rollback but its
  local Paddle installer buttons are removed from the default Preferences UI.
- High-performance OCR still requires Runtime image inference integration.
- No model downloads or Runtime modifications happen during patch application.

See upstream https://github.com/xushengfeng/eSearch-OCR (Apache-2.0)
and https://github.com/microsoft/onnxruntime. Check redistribution licenses
and native-library dependencies before bundling into AppImage.
