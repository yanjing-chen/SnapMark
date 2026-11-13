# SnapMark v1.1.1 · 正式版

SnapMark 是专为 GNOME 打造的 GTK4 / libadwaita 截图、标注和本地 OCR 软件。

**本版保留已在 Ubuntu 26.10 / Ryzen 8845HS 上验收通过的 1.1.0 截图监听和应用功能。**
相比 1.1.0，主要改善 Linux 安装包：新增使用系统 GTK4 的 `.deb`，
并让 AppImage 在满足条件的系统上优先使用系统 Python / GTK4 / libadwaita，
避免将 Ubuntu 24.04 打包的 GTK 环境强制用于不同的 GNOME 版本。

## 功能

- GNOME 截图、截图历史、编辑、标注、撤销/重做、复制和保存 PNG。
- 内置 OCR，使用用户独立安装的本地 Ollama 和兼容视觉模型；识别结果可编辑、复制和保存文本。
- OCR 模型可安装、导入、启用、移除和刷新；本地导入 GGUF/mmproj 取决于 Ollama 对模型架构的支持。
- 状态栏“编辑/识别当前截图”：仅对有效期内的新截图开放；点击后打开编辑器，需要手动启动 OCR。
- **事件驱动监听**：GNOME 截图文件监控和 GTK 剪贴板 changed 事件，不含每 1.5 秒的后台图片轮询。
- Ollama `keep_alive` 显存驻留秒数和截图快捷入口有效期可配置。

## 安装方式（Linux x86_64）

| 安装包 | 安装 / 启动 | GTK 来源 |
| --- | --- | --- |
| `snapmark_1.1.1-1_amd64.deb` | `sudo apt install ./snapmark_1.1.1-1_amd64.deb` | 系统 Python / GTK4 / libadwaita |
| `SnapMark-1.1.1-x86_64.AppImage` | `chmod +x ...AppImage && ./SnapMark-1.1.1-x86_64.AppImage` | 优先系统 GTK4，不兼容则回退自带运行时 |
| `SnapMark-1.1.1-Full-Source.zip` | 解压后 `bash scripts/run-local.sh` | 系统 Python / GTK4 |

`.deb` 已在 Ryzen 8845HS 的 Ubuntu/GNOME 实机上完成候选版验收；正式版应用逻辑不变。
**AppImage 的新运行模式仍应在你的 8845HS 上测试，不能把 DEB 的成功等同于 AppImage 通过验收。**

需要系统原生运行依赖时：

```bash
sudo apt update
sudo apt install -y python3 python3-gi python3-gi-cairo python3-cairo \
    gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-pango-1.0 gir1.2-gdkpixbuf-2.0
bash scripts/run-local.sh
```

AppImage 可通过环境变量调整 GTK 运行方式：

```bash
SNAPMARK_APPIMAGE_GTK_MODE=auto ./SnapMark-1.1.1-x86_64.AppImage
SNAPMARK_APPIMAGE_GTK_MODE=system ./SnapMark-1.1.1-x86_64.AppImage
SNAPMARK_APPIMAGE_GTK_MODE=bundled ./SnapMark-1.1.1-x86_64.AppImage
```

**软件包不包含 Ollama、OCR 模型、GPU 驱动或自研 Local AI Runtime，也不会自动安装它们。**

## 构建与 GitHub 发布

推送 `main`：GitHub Actions 自动测试并构建 AppImage / DEB。
推送 **`v1.1.1`** 标签：Actions 自动发布正式 GitHub Release，包含：

- `SnapMark-1.1.1-x86_64.AppImage`
- `snapmark_1.1.1-1_amd64.deb`
- `SnapMark-1.1.1-Full-Source.zip`
- `SHA256SUMS.txt`

用本源码完整 ZIP 在本机进行 GitHub 推送：`bash scripts/publish-v1.1.1.sh`。
发布脚本保留 Git 历史，预先备份仓库，不强制推送、不删除历史 Release 或分支。
详见 [打包与发布说明](docs/PACKAGING-AND-RELEASE.md)。

源代码：https://github.com/yanjing-chen/SnapMark · MIT License。
