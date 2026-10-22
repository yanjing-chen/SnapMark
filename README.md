# SnapMark 1.0.0

**SnapMark** is a GTK4/libadwaita screenshot annotation editor for Ubuntu GNOME Wayland (x86_64).

**简体中文:** SnapMark 是一款面向 Ubuntu GNOME Wayland 的 GTK4/libadwaita 截图编辑与标注工具。主程序不内置 AI 推理后端；OCR 和翻译属于可选插件。

## Workflow / 截图工作流

- Use GNOME's **Print Screen** to capture a screenshot. GNOME's selection interface is unchanged; SnapMark does **not** replace the system screenshot UI.
- Open a saved screenshot, choose **Open Clipboard Image**, or browse **Screenshot History** from the indicator menu. Screenshots are not subjected to a second selection step.
- Annotate with text, shapes, drawing, highlighter, mosaic, blur and eraser; copy or save an edited PNG.
- GNOME status indicator offers Open, Open Clipboard Image, Screenshot History, Preferences, Restart, Quit. The standalone About menu item is removed; About remains in Preferences.
- OCR and Translation can be installed independently, explicitly enabled and rolled back without reinstalling the base application.

## Release components

| Component | Version | Delivery |
|---|---|---|
| SnapMark | 1.0.0 | `SnapMark-1.0.0-x86_64.AppImage` or `SnapMark-x86_64.flatpak` |
| Official OCR plugin | **1.0.2** | `SnapMark-ocr-1.0.2.zip` and `.sha256` |
| Official Translation plugin | **1.0.2** | `SnapMark-translation-1.0.2.zip` and `.sha256` |
| Optional Local AI Runtime | 1.0.0 | Shared external installation; **not bundled**, managed separately |

Translation 1.0.2 depends on enabled OCR 1.0.2. Never remove other applications' Local AI Runtime installations, models, or user configuration when installing SnapMark.

**English and Simplified Chinese** are the only UI languages shipped. OCR and Translation support live, scrollable streaming previews: follow newly generated output, pause to browse earlier text, then return to the bottom to resume following. Final validated results remain editable and can be copied or saved.

## Install / Run

On Ubuntu x86_64 GNOME Wayland, after checking the downloaded `.sha256` file:

```bash
chmod +x SnapMark-1.0.0-x86_64.AppImage
./SnapMark-1.0.0-x86_64.AppImage
```

For the Flatpak bundle, **install it only if you choose to**:

```bash
flatpak install --user ./SnapMark-x86_64.flatpak
flatpak run io.github.yanjingchen.SnapMark
```

Install optional plugin ZIP archives in **Preferences → Plugins**, and select **1.0.2** for OCR before activating Translation. A shared external Runtime and compatible models must be configured separately for high-performance OCR and translation.

For local development on Ubuntu GNOME Wayland:

```bash
bash scripts/run-local.sh
```

## Sources and validation

The Code01-Ver2-0 (Ryzen 7 6800H) integrated GTK version completed full automated regression and eight hands-on GUI checks on 2026-10-22. Release binaries require separate AppImage and Flatpak acceptance before publication. Xvfb CI smoke tests do not replace actual GNOME Wayland GUI testing.

More details: [Release notes](docs/RELEASE_V1.0.0.md) and [C3 distribution notes](docs/C3_DISTRIBUTION.md).

Licensed under MIT. Only install executable Python plugin archives from releases you trust.
