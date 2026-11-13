# SnapMark v1.1.1 — 正式版构建与 GitHub 发布

本版只改变版本号与打包、CI 配置，**应用代码延续 1.1.0 正式版**；没有添加 1.5 秒剪贴板轮询。

## DEB

在 Ubuntu 24.04+ x86_64 安装构建工具后：

```bash
sudo apt install -y dpkg-dev python3
bash scripts/build-deb.sh
sudo apt install ./dist/snapmark_1.1.1-1_amd64.deb
/usr/bin/snapmark
```

DEB 安装系统原生 Python / GTK4 / libadwaita，安装包里不含 Ollama、GPU
驱动或 OCR 模型。不会启用或修改用户已有的自启动设置。先退出旧的 AppImage 进程。
卸载使用 `sudo apt remove snapmark`，不删除用户设置。

## AppImage

```bash
./SnapMark-1.1.1-x86_64.AppImage
SNAPMARK_APPIMAGE_GTK_MODE=system ./SnapMark-1.1.1-x86_64.AppImage
SNAPMARK_APPIMAGE_GTK_MODE=bundled ./SnapMark-1.1.1-x86_64.AppImage
```

- `auto`（默认）优先测试宿主机 GTK4 / Python 环境，具备完整依赖时调用宿主机 GTK；否则回退到自带的运行库。
- `system` 强制使用宿主机依赖，缺少则明确报错。
- `bundled` 强制使用 AppImage 自带依赖。

## Actions / Release

`.github/workflows/appimage.yml` 在 `main` 和 `v*` 标签上运行测试并构建两种安装包。
首次发布在本机执行：

```bash
bash scripts/publish-v1.1.1.sh
```

发布脚本：

1. 验证 GitHub 身份和 `main` 默认分支，检测 `v1.1.1` 不存在。
2. 本地编译与测试，构建 DEB，生成源码归档。
3. 克隆远程仓库并导出 **完整 Git bundle** 和 SHA256 备份。
4. 将完整源码作为普通提交更新 `main`，等待主分支 Actions 通过。
5. 在该成功提交上创建 `v1.1.1` 附注标签并推送，等待 Release Actions 通过。
6. 验证 AppImage、DEB、完整源码 ZIP、SHA256 及正式 Release 状态。

此过程不会强制推送、覆盖旧标签、删除分支或修改旧版 Release。

## GitHub Release 附件

- `SnapMark-1.1.1-x86_64.AppImage`
- `snapmark_1.1.1-1_amd64.deb`
- `SnapMark-1.1.1-Full-Source.zip`
- `SHA256SUMS.txt`

GitHub Actions 的 Xvfb smoke test 不能替代真实 GNOME/Wayland 测试。
