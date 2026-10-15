# SnapMark C2 — OCR + Translation 双栏 UI（候选版）

2026-10-15：按用户确认的简洁工作流程实现；布局补丁修订 013。

- 左侧 OCR 顶部：**OCR model**、**OCR elapsed time**（运行时动态显示，保留两位小数）。
- 左侧中部：可以编辑的 OCR 结果；点击 Run OCR 总是识别 GNOME 已截取的**完整原图像素**，不识别之后添加的标注，不提供 OCR Area/二次框选。
- 左侧**右下角**只保留：`Run OCR`（运行期间变成 `Cancel OCR`）、`Copy text`、`Clear text`、`Save as TXT`。
- 右侧 Translation 顶部：**Target language** 下拉框，`Translate` 紧随其右。无源语言设置，由翻译模型自行识别。
- 右侧中部：可编辑的翻译结果；Translate 取用左侧**当前文本**，包含手工修改。
- 右侧**右下角**只保留：`Clear translation`、`Copy text`、`Save as TXT`。
- **只启用 OCR 时占据底部全宽；启用 OCR 和 Translation 时初始各占 50%，可拖动中央分隔线调整宽度。** 这两款插件可分开安装或启用。OCR 0.1.2 和 Translation 0.1.0 是不同、单独安装/启用的插件。Translation 声明依赖 OCR >=0.1.2。
- 翻译仅在点击 Translate 时请求本机 `http://127.0.0.1:8111/v1/chat/completions`；经 `/v1/models` 自动选择**已安装、标记为 translation-capable** 的模型，存在多个时优先 HY-MT。翻译结果不会自动覆盖推理期间手工修改的文本。
- 没有翻译模型时明确提示，不会下载模型、修改后端偏好、修改 Runtime 自动卸载秒数或把文本发送到云端。
- OCR Python/PaddleOCR 模型仍需手动准备：当前阶段的范围是 UI 与调用接口，不宣称完整识别已通过实机验证。

## 测试计划

1. 全部 220 项 Code01 原仓库测试通过后，再选择仅安装 OCR 或同时启用两插件（独立脚本）。
2. GUI 确认单面板全宽、双面板初始对半且可拖动；所有操作按钮均在所属面板的右下方；OCR 顶部模型和耗时、底部四按钮；右侧顶部只有目标语言 + Translate、底部三按钮。
3. 点 Run OCR：若 OCR 环境未安装，应有明确 GTK 弹窗；按现有计划在 C2-B 安装模型后进行真实 OCR。
4. 手工粘贴中文到左侧文本框，选择 Dutch，点 Translate；若没有已安装的 translation-capable 模型应弹窗，而不是静默失败。
5. 真实翻译的最终可用性仍需 Code01 上已安装模型及 8111 Runtime 现场验证。
