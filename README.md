# SnapMark v1.1.0

SnapMark 是面向 **GNOME / GTK4 / libadwaita** 的截图标注与本地 OCR 工具。1.1 正式版将 OCR 集成到主程序，通过本机 **Ollama** 服务调用用户安装或导入的视觉语言模型；不再依赖插件框架、翻译插件、ONNX 轻量 OCR 或自研 Local AI Runtime。

[English summary](#english-summary)

## 核心功能

- 使用 GNOME 原生截图选区界面，保存截图后由 SnapMark 监听并在编辑器中打开；仍支持打开本地图像和截图历史。
- 支持箭头、矩形、椭圆、直线、自由画笔、文字、马赛克、模糊、高亮、橡皮擦；图层编辑、撤销/重做、复制及 PNG 保存。
- **内置 OCR**：编辑器内手动点击 OCR，识别原始截图或 OCR 选取区域，结果可编辑、复制、保存 TXT。
- **Ollama 模型管理**：选择并启用 OCR 模型、下载模型、导入含主 GGUF 与兼容视觉投影 GGUF（mmproj）的目录；模型导入能力以所用 Ollama 版本及模型格式实际支持为准。
- 模型清单支持刷新；只从 SnapMark 列表删除不影响 Ollama 文件，刷新可以重新发现仍存在的模型；真正删除 Ollama 模型后不能通过刷新恢复。
- OCR 请求可配置模型驻留时间（秒，`keep_alive`），不更改 Ollama 全局配置。
- 状态栏 **“编辑/识别当前截图”**：刚启动时不可用；新截图在指定有效期内启用，超时禁用；点击只在编辑器中打开截图，**不会自动 OCR**。有效期在截图设置中调整，默认 60 秒。
- 简体中文、英文界面；单独 AppImage，无须安装 Local AI Runtime。已在 NVIDIA RTX 5070 / Ubuntu 26.10 GNOME 51 环境完成主要 GUI 功能的用户测试；GitHub CI 使用 Ubuntu 24.04 构建 x86_64 AppImage。

## 依赖

SnapMark 主程序使用 Python 3、PyGObject、GTK4、libadwaita 与 Cairo；使用本机 `http://127.0.0.1:11434` 上的 Ollama 进行 OCR。Ollama 与 OCR 模型**不打包**到 AppImage。第一次使用 OCR 前请安装 Ollama，并通过设置页添加兼容的视觉 OCR 模型。导入单独的主模型与 mmproj GGUF 并不保证所有架构均得到 Ollama 支持。

Ubuntu 原生源码运行（已安装 Ollama 的机器）：

```bash
sudo apt update
sudo apt install -y python3 python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-pango-1.0 gir1.2-gdkpixbuf-2.0
bash scripts/run-local.sh
```

构建 x86_64 AppImage（还需要 curl、相关 GTK 库及 AppImage 工具下载网络）：

```bash
bash scripts/build-appimage.sh
```

正式版本默认输出 `dist/SnapMark-1.1.0-x86_64.AppImage`。

## GitHub 正式发布

从干净的完整源码 ZIP 解压后，在 **Ryzen 6800H 本地**运行 `scripts/publish-v1.1.0-6800h.sh`。发布程序将检查 GitHub 身份及仓库状态、在本机备份所有远程分支与标签、以普通快进提交更新 `main`、验证 Actions、推送 `v1.1.0` 标签触发 GitHub Release；成功验收 Release 后删除远程除 `main` 外的其余分支。**不强制推送、不删除旧标签、不删除其他 GitHub Releases。** 详见 [`docs/RELEASE-6800H.md`](docs/RELEASE-6800H.md)。

## 项目结构

| 路径 | 功能 |
| --- | --- |
| `snapmark/app.py`, `watch.py`, `screenshot_session.py` | GNOME 截图监听、状态栏生命周期、快捷入口过期状态 |
| `snapmark/editor.py`, `model.py`, `paint.py`, `filters.py` | GTK4 截图编辑器与非破坏标注 |
| `snapmark/ocr_builtin.py`, `ocr_ollama.py`, `ocr_selection_c2.py` | 内置 OCR、Ollama API、选区 |
| `snapmark/preferences.py`, `preferences_sidebar_c2e.py` | 设置、模型选择与 Ollama 管理 |
| `snapmark/tray.py`, `history_c2g.py` | 状态栏菜单与截图历史 |
| `.github/workflows/appimage.yml` | 测试、构建 AppImage、通过标签发布 Release |
| `scripts/` | 本地运行、AppImage 构建及 6800H 发布脚本 |

## English summary

SnapMark v1.1.0 is a GTK4/libadwaita screenshot editor for GNOME with built-in OCR using a **separately installed local Ollama service**. It retains screenshot markup, image history, editable OCR text, user-selectable vision models, and a time-limited tray shortcut that opens the screenshot without automatically recognizing text. The app does not bundle Ollama or model weights. Only x86_64 AppImage builds are published; there are no Flatpak/DEB packages.

License: MIT.
