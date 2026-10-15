# C2-B：轻量 OCR 安装与模型注册（OCR 0.1.6）

在 Preferences → OCR 的 **Lightweight OCR setup** 中操作：

1. **Install / update engine…**：由用户确认，使用 ~/.local/bin/uv 将 PaddlePaddle 3.3.1 和 PaddleOCR 3.7.0 安装进 ~/.local/share/snapmark/ocr-venv（Python 3.12）。不碰系统 Python 或 Local AI Runtime。
2. **Download model…**：由用户确认，下载官方 PP-OCRv6 small 检测与识别模型到 ~/.local/share/snapmark/ocr-models；权重按官方哈希校验，成功后自动登记为轻量 OCR 模型。当前仅实现 small，其他型号仍需手动注册或后续开发。
3. **Save OCR Preferences**：模式选择仍分 lightweight/high_performance；编辑器只显示符合模式、注册及存在验证条件的模型。

注意：不调用下载按钮就不会联网；不能保证用户网络可直接访问 Hugging Face。安装后需关闭并重新打开编辑器，使新插件加载。若首次安装失败，把弹窗详情发给开发者。其他型号未实现自动下载。

运行约束：GTK4 主进程不导入 PaddleOCR；安装工作在后台线程执行，实际推理在独立子进程执行。模型文件未下载或安装前会提示缺失，不会偷偷下载。

官方来源： https://www.paddleocr.ai/ 和 https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det 及 https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec
