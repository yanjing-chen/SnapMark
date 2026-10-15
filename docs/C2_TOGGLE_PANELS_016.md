# SnapMark C2：工具栏切换面板与图标化控件（0.1.5 / 0.1.2）

## 显示规则

- 打开编辑器默认不显示 OCR / Translation 结果面板，保留完整画布。
- 点击工具栏 OCR：仅显示 OCR 面板（下方全宽）；再点关闭后不显示结果面板。
- 点击工具栏 Translation：自动选中 OCR，打开 OCR + Translation 左右双栏；Translation 选中时 OCR 不能独立关闭。
- 再点工具栏 Translation：翻译面板关闭，OCR 仍显示全宽；再关闭 OCR 才彻底收起。
- 工具栏开关仅控制显示；Run OCR 和 Translate 仅在面板内由用户明确点击后执行。无自动推理。
- 两栏默认近似 50%/50%，中间可手动拖动。隐藏/显示不清除原有编辑文本。

## 界面与模型

- OCR 上部为图标、紧凑模型下拉框、Run OCR；文本区可编辑，耗时在左下，Copy / Clear / Save 在右下。
- 翻译顶部一行排列翻译模型、目标语言及 Translate；中间为可编辑译文；耗时左下，Clear / Copy / Save 右下。
- 下拉菜单未注册模型时留空，不显示冗长提示；点击运行但未准备好时弹出错误。
- 模型仍只从 Preferences 注册、安装；OCR/Translation 用途隔离以及 OCR 高性能/轻量模式过滤沿用上一版。
- 不修改 Local AI Runtime、其模型/后端、300 秒自动卸载设置，不推送 GitHub。

## 验收注意

离线代码测试和模拟控件行为不能代替 Code01 的 GTK4/Wayland 真机验收。请用测试记录确认当前状态，并观察工具栏两个切换按钮、文本保留、分隔线、下拉框是否正常。
