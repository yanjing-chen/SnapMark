# SnapMark B3-2 集成 Runtime 应用管理

目标：Code01-Ver2-0 的 Runtime 0.8.0 → 1.0.0 升级，先隔离 HOME 实测，后才在生产环境人工确认。

官方标签 `local-ai-runtime-v1.0.0`，源码 `cb10db5f8bb1bf0590c245001e268d1f7cc60fa0`。
固定应用包 `Local-AI-Runtime-1.0.0-linux-x86_64.tar.gz`；固定 SHA256
`a87749de1c16fc43055292def788fc04f90389b11b07d7b17ddf05c0dca09953`。
`SHA256SUMS` 的 SHA256 为 `2811525dd2669cef32656d1fed5e97a73a56bcf1f272fe8bf0e87b21cdb207df`。

- Download & verify: 下载应用包与 SHA256SUMS，双重校验并安全检查 tar 成员，只存用户缓存；不安装。
- Backup: 备份受控的程序、入口、服务文件和三个 JSON；不复制/删除任何 GGUF 或 CPU/Vulkan/CUDA 包。
- Install: 必须用户确认、已校验应用包、先自动备份；使用固定发行包自身的 `install-user.sh --no-systemd`，创建官方等效用户级 service unit。不自动启动/重启服务。Runtime 0.8.0 可以继续运行，直到用户明确选择 Restart。
- Rollback: 确认后恢复最近一次备份中原有的文件，删除在备份时不存在的受控程序文件；不自动重启。
- Start/Stop/Restart: 用户操作，GTK 确认，用户级 systemctl；可能影响其他客户端。
- Uninstall: 显式确认、先备份、停止并禁用服务，只删除应用程序文件、入口和 service unit，保留配置、模型和推理后端。
- Remove settings: 额外的显式破坏性选择，仅删除 `config.json`、`preferences.json`、`custom-models.json`。永不删除外部 GGUF、数据根目录或 GPU 后端包。

所有 UI 操作异步执行，失败显示错误且不会自动重试。离线隔离测试使用临时 HOME 和注入的服务执行器，绝不触碰 Code01 的真实 Runtime。升级后必须单独点击 Restart 才能切换实际正在运行的服务版本。GitHub 推送/Release 由用户单独批准。

当前风险：运行中的 Runtime 程序仍引用旧 Python 文件，覆盖旧应用文件后再 Restart 才能使用新代码；因此生产升级前先做好备份和回滚计划。UI 的回滚仅恢复文件，不会恢复当前运行进程。模型服务及持久化配置涉及多客户端，务必确认没有其他任务运行。
