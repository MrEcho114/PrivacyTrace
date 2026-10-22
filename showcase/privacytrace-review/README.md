# PrivacyTrace · 作品评审材料（专家版）

面向竞赛专家评审的视频 + PPT，按「定位 / 创新 / 关键实现 / 真实成果 / 学生原创贡献」组织。

## 文件

- 视频：[`delivery/PrivacyTrace-Review-1080p.mp4`](delivery/PrivacyTrace-Review-1080p.mp4)（120.000 s，1920×1080，30 fps，H.264/AAC，原创配乐，无旁白）
- PPT：[`delivery/PrivacyTrace-Review.pptx`](delivery/PrivacyTrace-Review.pptx)（10 页，可编辑，含逐页备注）
- 说明：[`delivery/README.md`](delivery/README.md)
- 分镜 / 事实绑定：[`delivery/BEATS.md`](delivery/BEATS.md)
- SHA-256 / ffprobe / QA：[`delivery/manifest.json`](delivery/manifest.json)

## 边界

- H12（J × splits × 手机模型）失败，复现 2 次，保留为 `11 通过 / 1 未通过`。
- 受控 12 场景只写“状态一致”，不是真实 App 的准确率；P/R/F1 按协议 N/A。
- 真实 App 仅 1 个历史样本（GKD v1.12.1），3 条结论均为 `INSUFFICIENT_EVIDENCE`。
- 前端仍在开发；界面截图标注开发版 / 交付候选，最终视觉可能变化。
- 不宣称 100% 独立、不给 AI 代码比例、不宣称开源。
- Issue #200 / #107 已改为「PPT + 视频都要」；系统两个栏目分别上传，上传时间与系统反馈仍待人工记录。

## 生成

PPT 生成脚本：`deck/build_deck.py`（python-pptx；输入图在同目录）。
视频源：`delivery/film-review.html`（单文件确定性时间线，`window.__seek(t)`）。
