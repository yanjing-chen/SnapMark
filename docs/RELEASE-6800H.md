# SnapMark 1.1 正式发布：6800H 本地操作

**只需要本机安装 Git、GitHub CLI、Python3 和 GNOME/PyGObject 依赖，且有 GitHub 帐户 `yanjing-chen` 的推送权限。** 发布操作全部在用户的 Ryzen 6800H 本地执行，不会从 ChatGPT 远程登录 GitHub。

## 自动发布流程

1. 用 `SnapMark-1.1.0-Release-Full-Source.zip` 解压得到 `SnapMark-1.1.0` 完整源码目录。
2. 验证内部版本号 `1.1.0`、运行 Python 语法及单元测试，并创建本地完整源码 ZIP。
3. 校验 GitHub 登录账户、默认分支 `main`，拒绝覆盖现有的 `v1.1.0` 标签或 Release。
4. 在 `~/下载` 独立克隆 `yanjing-chen/SnapMark`，将所有 Git refs 导出为 `.bundle` 备份和 SHA256 校验文件。
5. 将完整 1.1 源码替换进该克隆的工作树，**在原 `main` 历史上正常新增提交**，不强制推送，不删除历史提交。
6. 推送 `main`，等待 Actions 测试与 AppImage 构建成功。
7. 推送带注释的 `v1.1.0` 标签；标签触发新的 Actions 构建，并自动发布包含 AppImage、完整源码 ZIP 与 SHA256SUMS 的 Release。
8. 确认 Release 的三个资产都已出现，**最后**删除 GitHub 上除 `main` 外的全部远程分支。原有 Git 标签和 Releases 不会被删除。

如果任何检查、推送、Actions 或 Release 步骤失败，脚本会停止，**不会开始后续删除远程分支**。GitHub 分支保护设置可能阻止部分删除，脚本会报告剩余分支。已经推送 `main` 或标签后不能简单地假定整轮可以回滚；备份 bundle 可用于人工恢复历史。

## 6800H 复制命令

将完整源码 ZIP 保存到 `~/下载`，运行：

```bash
bash <<'BASH'
set -Eeuo pipefail
if [[ -f "$HOME/下载/SnapMark-1.1.0-Release-Full-Source.zip" ]]; then
  BASE="$HOME/下载"
elif [[ -f "$HOME/Downloads/SnapMark-1.1.0-Release-Full-Source.zip" ]]; then
  BASE="$HOME/Downloads"
else
  echo '请先下载 SnapMark 1.1 完整源码 ZIP 到下载文件夹'; exit 1
fi
sudo apt update
sudo apt install -y git gh python3 python3-gi python3-gi-cairo python3-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0 gir1.2-pango-1.0
if ! gh auth status >/dev/null 2>&1; then
  gh auth login -p https -w
fi
gh auth setup-git
if [[ -e "$BASE/SnapMark-1.1.0" ]]; then
  echo "为避免覆盖，目录已存在：$BASE/SnapMark-1.1.0"; exit 1
fi
python3 -m zipfile -e "$BASE/SnapMark-1.1.0-Release-Full-Source.zip" "$BASE"
bash "$BASE/SnapMark-1.1.0/scripts/publish-v1.1.0-6800h.sh"
BASH
```

首次使用 GitHub CLI 需要一次浏览器授权。版本升级脚本不会安装、重启或卸载用户的 Ollama 服务，也不会删除 Ollama 模型。

## 验证

- Actions: <https://github.com/yanjing-chen/SnapMark/actions>
- Releases: <https://github.com/yanjing-chen/SnapMark/releases/tag/v1.1.0>
- `main`: <https://github.com/yanjing-chen/SnapMark/tree/main>
- 源码本地备份：`~/下载/SnapMark-release-backups/SnapMark-before-v1.1.0-日期.bundle`
- 发布日志：`~/下载/SnapMark-release-v1.1.0-日期.log`

CLI 发布前如已有 `v1.1.0` 同名标签或 Release，脚本会直接停止。不要删除旧标签或强制重推；应分析旧发布状态再决定是否采用新的补丁版本号。
