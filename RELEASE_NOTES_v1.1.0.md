# SnapMark v1.1.0 · 正式版

SnapMark 1.1 正式版基于已完成实机验收的 OCR4 Fix4 代码发布。

## 主要更新

- 内置 PaddleOCR-VL 等 Ollama 兼容视觉 OCR 模型的识别界面；OCR 不再以插件形式提供。
- 删除旧 Local AI Runtime、独立 llama.cpp 推理管理、轻量 ONNX OCR 与 Translation 插件。
- 支持图形界面安装/选择已存在的 OCR 模型、导入 GGUF 目录以及模型驻留秒数设置；具体模型兼容性取决于 Ollama。
- 截图菜单改为“编辑/识别当前截图”：首次启动禁用，截图后在用户设定的时间内启用，点击仅打开编辑器，OCR 需手动启动。
- 截图监听、历史记录、画笔标注、高亮、马赛克、图层与撤销等既有功能保留。
- 提供 x86_64 AppImage 与完整源码 ZIP；不捆绑 Ollama、模型权重或系统 CUDA 驱动。

## 已知限制与要求

- OCR 需要用户自行安装的 Ollama 服务，以及 Ollama 支持的视觉模型。GGUF 与 mmproj 的兼容性依赖 Ollama 版本与模型架构。
- Ubuntu 上的 GNOME 托盘图标取决于系统支持 StatusNotifierItem 的扩展。
- CI 中的 Xvfb 图形测试不能完全取代 Ubuntu GNOME Wayland 实机验收。
- 不会删除或修改用户现有的 Ollama 模型与 SnapMark 个人设置。
