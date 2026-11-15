> 历史设计分析（来自外部提案）；不代表 1.1.2-rc3 最终实现。当前实现详见 README 与源码。

# SnapMark 1.1.2-rc3 剪贴板监听：分析与改进

适用环境：Ubuntu 26.10 "Stonking Stingray"、GNOME Shell 51、**Wayland**、Python 3.14.8、PyGObject 3.57.1。
本次改动全部落在 SnapMark 自身代码里：**纯 GTK4/Wayland，无 Shell 扩展、无 X11/XWayland、无新依赖、无后台轮询**。

---

## 一、结论先行

"复制图片/截图后，右键托盘的『编辑/识别当前图片』常常是灰的，必须先把软件界面完整打开（唤醒）才行" —— 这不是偶发 bug，而是 rc2 设计的必然结果：

- rc2 把 `Gdk.Clipboard::changed` 当作**唯一**的剪贴板数据源；
- Wayland 出于安全，Mutter 只把 `wl_data_device.selection`（剪贴板 owner 变化）发给**拥有键盘焦点的客户端**；
- SnapMark 以 `start_minimized=true` 后台常驻、没有窗口、没有焦点 → 收不到任何通知 → 缓存里没有图 → 菜单项 disabled；
- 打开界面 = 窗口获得焦点 = compositor 补发当前 selection offer = `changed` 触发 = 按钮变亮。这正是"唤醒"的真相。

`app.py::start_watching()` 的注释其实已经承认了这点（"GdkClipboard.changed is insufficient on some GNOME 51 sessions while the application is minimized"），但只补了截图**文件**监视，完全没覆盖"网页复制图片、聊天软件复制图片、只存剪贴板的截图"这些没有文件落盘的场景。

纯 Wayland 下，应用层无法让后台进程在"复制发生的那一刻"被动收到通知（compositor 安全模型）。但可以把 GNOME 剪贴板插件的**实现方式**借鉴过来，把"被动等通知"改成"事件 + 主动对账"，从而做到：**按钮随时可按，按下去自动取到图，不需要手动唤醒、不需要重新复制**。

---

## 二、GNOME 剪贴板插件的实现方式（借鉴了什么）

Pano、Clipboard History、GPaste 这类扩展在 Shell 侧用 `Meta.Selection::owner-changed` 订阅剪贴板变化，再用 `Meta.SelectionSource.get_mimetypes()` 协商，最后 `read_async()` / `read_finish()` 拿到 `Gio.InputStream` 分块读取。本机实测确认（GNOME 51 / Meta 51 typelib）：

```
Meta.Selection 信号: owner-changed
Meta.SelectionSource.get_mimetypes() -> list
Meta.SelectionSource.read_async(mimetype, cancellable, callback)
Meta.SelectionSource.read_finish(result) -> Gio.InputStream
```

GTK4 应用层有完全对应的 API（本机 PyGObject 反射确认）：

```
Gdk.Clipboard.read_async(mime_types:list, io_priority, cancellable, callback)
Gdk.Clipboard.read_finish(result) -> (Gio.InputStream or None, out_mime_type:str)
Gio.InputStream.read_bytes_async(count, io_priority, cancellable, callback)
Gio.InputStream.read_bytes_finish(result) -> GLib.Bytes
```

**可借鉴、且与"是否 Shell 扩展"无关的实现思想**（这正是其他 AI 容易漏掉的部分）：

1. owner-change 事件只是 **hint**，真实状态必须靠主动读 `get_formats()` / `get_mimetypes()` 并 `read_async` 去核对（reconcile）；
2. **按 MIME 协商读原始字节流**，而不是赌工具包能把任意 `image/*` 反序列化成单一类型；
3. **分块读取 + 大小上限 + 取消 in-flight 请求 + 内容哈希去重**，避免事件风暴和重复入库；
4. 在生命周期关键点（启动、窗口激活、菜单打开）**主动对账一次**，而不是只等事件；
5. 内容保留到被替换，而不是用一个 30/60 秒倒计时把它废掉。

rc2 只做了第 2 步的一半（只看 formats，不读流），第 1、3、4、5 步全缺。

---

## 三、这个代码包实现得好不好

### 做得好的地方

- **没有后台轮询**，`clipboard_images.py` 先判 MIME 元数据再决定要不要读数据；文本、HTML、URL、`x-gnome-copied-files` 一律不读 payload，隐私处理干净。
- 图片格式判定抽成纯函数，可脱离 PyGObject 做单元测试。
- 文件监视 + 剪贴板双通道、`ScreenshotSession` 限时缓存、`--watch` / `start_minimized` / 0–3600 秒可配超时。
- 单托盘修复做对了：`tray.py` 用对象路径 `/StatusNotifierItem` 注册，让 Ubuntu AppIndicators 的 brute-force 扫描与显式注册算出同一个 id，Flatpak 分支保留独立策略。
- 测试体系完整：114 个用例，含大量 AST 静态源码契约，能在无 GTK 的 CI 里跑。

### 问题清单（按严重度）

| # | 级别 | 问题 |
|---|------|------|
| 1 | P0 | `changed` 是唯一数据源；Wayland 后台无焦点必然收不到。文件监视只兜住"保存为文件的截图"，兜不住复制图片。 |
| 2 | P0 | `AboutToShow` / `AboutToShowGroup` 只 `refresh_clipboard_status()` 读**缓存**，右键这么自然的时机完全没用来读剪贴板。 |
| 3 | P0 | 菜单项 `enabled` 绑 `recent_screenshot_eligible()`。在无法确知剪贴板状态的后台场景，默认"灰"几乎总是错的。 |
| 4 | P1 | 默认 60s（你的配置是 30s）后快捷项过期变灰；`ScreenshotSession` 把"剪贴板里还有没有这张图"错误地简化成时间窗口。 |
| 5 | P1 | 只有 `read_texture_async` 一条路；`image/jpeg`、`image/webp` 等若 GDK 无法转成 Texture，180ms×3 后**静默**放弃，没有任何日志。 |
| 6 | P1 | generation 竞态：`_record_screenshot_file()` 里递增 generation 会取消所有 in-flight 剪贴板读取；GNOME 截图同时产生文件+剪贴板，两条通道互相打架。`_clipboard_changed` 在检查开关之前就递增 generation。 |
| 7 | P1 | 启动时从不对账当前剪贴板，只能等未来某次 owner 变化。 |
| 8 | P2 | 全链路无诊断日志，信号有没有到、为什么读失败，用户和开发者都看不见。 |
| 9 | P2 | `watch.py::_check_stable` 用 `st_mtime < start_time - 3` 过滤，`seen` 超过 400 条全清；文件名靠前缀白名单，换个截图工具就漏。 |

---

## 四、本次改动

| 文件 | 改动 | 对应问题 |
|------|------|----------|
| `snapmark/clipboard_images.py` | 新增 `image_mime_types()`（按优先级列出真实 image MIME）与 `image_to_png()`（PNG 直通；其他经 GdkPixbuf → Gdk.Texture 转 PNG，32MB 上限）。原 `clipboard_image_state()` 语义不变。 | 5 |
| `snapmark/app.py` | `quick_action_available()` 让菜单项始终可点（乐观 UI，点击即按需获取） | 3 |
| 同上 | `probe_clipboard_now()`：借鉴插件的"事件只是 hint、主动对账"，在 **4 个时机**触发 —— 启动后 350ms、托盘菜单打开、快捷项点击、窗口打开/present 后 150ms。0.4s 节流 + generation 取消 in-flight，**没有后台定时轮询**。 | 1、2、7 |
| 同上 | 新增 MIME 字节流通道：`read_async(mime_types)` → `read_finish()` → `read_bytes_async` 分块读 → `image_to_png()` → 哈希去重 → `ScreenshotSession.record()` → 刷新 dbusmenu。原 `read_texture_async` 通道保留，双通道互补。 | 5 |
| 同上 | `_accept_image()` 统一入口：内容哈希去重、递增 generation、刷新菜单、打印 `clipboard image cached (mime, N bytes)` 等诊断日志。 | 6、8 |
| 同上 | `open_recent_screenshot()` 缓存为空时自动 `_ensure_focus_for_clipboard()` present 窗口拿焦点（把手动"唤醒"自动化），probe 成功后 `_load_pending_into_editor()` 用 `EditorWindow.load_image()` 把图片灌进刚打开的窗口。 | 1、4 |
| 同上 | `_on_shutdown()` 清理待打开超时源 | — |
| `snapmark/tray.py` | 新增 `clipboard_probe` 回调；`AboutToShow` / `AboutToShowGroup` 先 probe 再刷新；保留 `clipboard_ready() if index == 2 else True` 与 `needsUpdate=True` 契约 | 2 |
| `tests/test_clipboard_stream.py` | MIME 协商、PNG 归一化、原分类语义回归 | — |
| `tests/test_quick_action_contract.py` | 静态源码契约 + 真实去重/缓存方法行为测试 | — |

**刻意没动的**：`_clipboard_changed` / `_retry_clipboard_image` / `_read_clipboard_screenshot` 三个方法（保持原有事件通道与全部 AST 契约测试），`ScreenshotSession` 的过期语义（用"按需重新 record 刷新时间戳"达到等效效果，不破坏现有 5 个测试），`watch.py`（与本次目标无关，问题 9 留给后续）。

**保持不变**：无轮询、无 X11、无 Shell 扩展、无新依赖；文本/HTML/URI/文件列表仍不读 payload；`changed` 信号、文件监视、单托盘路径注册、限时 session、OCR 需二次点击，全部保留。

---

## 五、验证

- 本机（无 GTK4 图形会话）：`python3 -m unittest discover -s tests -v` → **132 tests, OK (skipped=13)**；改动前基线 114 tests OK，新增 18 个用例。
- 语法：`python3 -m compileall -q snapmark/app.py snapmark/tray.py snapmark/clipboard_images.py` 通过。
- API 签名通过本机 PyGObject 反射核对，不是凭记忆写的。

真机验收（Ubuntu 26.10 / GNOME 51 / Wayland，**注销重登**，Alt+F2 → r 在 Wayland 无效）：

1. `journalctl --user -b -f | grep -i snapmark` 观察日志。
2. 复制网页图片 → 右键托盘 → 应看到 `SnapMark: clipboard image cached (...)`，`编辑/识别当前图片` 始终可按。
3. 点击它 → 编辑器打开并直接加载那张图；**不需要再复制一次，也不需要事先唤醒软件**。
4. 等超过 30/60 秒再右键 → 按钮仍可按；点击后自动补读并加载。
5. GNOME 截图（保存到 `~/图片/截图`）→ 原文件监视路径照常工作。
6. 复制文本/链接 → 不应出现 `clipboard image cached`，不触发 OCR。
7. 在首选项关闭"剪贴板图片监视" → 复制图片不缓存，截图文件监视仍生效。

---

## 六、残留限制（必须说清楚）

- 纯 Wayland 下，**后台、无焦点的应用仍然无法在"复制发生的那一刻"被动收到通知**。这是 Mutter 的安全模型，应用层绕不过去（干净的解法只有 Shell 侧 `Meta.Selection`，或接受 XWayland；本次按你的要求两者都不用）。
- 所以"复制完按钮自动变亮"不能 100% 保证；本次保证的是：**按钮永远可点，点下去应用自己拿焦点并读到当前剪贴板图片**。代价是点击时会打开编辑器窗口 —— 这正是获取焦点所必需的，而且图片会直接加载进这个窗口，不会多弹一个空窗。
- 若将来要"复制即亮"，需要产品层面决定是否引入 Shell 侧桥；那是另一个方案，不是本次代码缺陷。
- 本环境没有真实 GTK4 图形会话，GUI 行为需按上面 7 步在你的机器上验收；纯逻辑与源码契约测试已全部通过。
