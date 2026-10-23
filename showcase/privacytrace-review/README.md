# PrivacyTrace · 作品评审材料（专家版）

面向竞赛专家评审的视频 + PPT，按「定位 / 创新 / 关键实现 / 真实成果 / 学生原创贡献」组织。

## 文件

- 视频：[`delivery/PrivacyTrace-Review-1080p.mp4`](delivery/PrivacyTrace-Review-1080p.mp4)（120.000 s，1920×1080，30 fps，H.264/AAC，原创配乐，无旁白）
- PPT：[`delivery/PrivacyTrace-Review.pptx`](delivery/PrivacyTrace-Review.pptx)（10 页，v0.2，可编辑，含逐页备注）
- 说明：[`delivery/README.md`](delivery/README.md)
- 分镜 / 事实绑定：[`delivery/BEATS.md`](delivery/BEATS.md)
- SHA-256 / ffprobe / QA：[`delivery/manifest.json`](delivery/manifest.json)
- 界面采集清单：[`capture/manifest.json`](capture/manifest.json)（第 2 / 4 页的移动 App 截图，含提交、日期、视口与哈希）

## 边界

- H12（J × splits × 手机模型）失败，复现 2 次，保留为 `11 通过 / 1 未通过`。
- 受控 12 场景只写“状态一致”，不是真实 App 的准确率；P/R/F1 按协议 N/A。
- 真实 App 仅 1 个历史样本（GKD v1.12.1），3 条结论均为 `INSUFFICIENT_EVIDENCE`。
- 前端仍在开发；PPT 第 2 / 4 页是 2026-10-23 的移动 App 开发版截图（固定合成材料），不是最终视觉，也不是真机或 APK 扫描证明。
- 桌面工作台按 ADR-0005 冻结，是工程验收与离线回放介质，不是客户端；PPT 不再把它当作当前界面。
- 不宣称 100% 独立、不给 AI 代码比例、不宣称开源。
- 提交状态以报名系统实际提交与回执为准；本目录只固定材料版本与哈希。

## 生成

1. 采集移动 App 截图（生产 Vue + 受控 native bridge；输出 `capture/` 与 `capture/manifest.json`）：

   ```bash
   node scripts/capture-review-deck-shots.cjs
   ```

2. 生成 PPTX（读取 `capture/manifest.json`，校验每张图的提交、视口、DPR 与 SHA-256，再输出 `deck/PrivacyTrace-Review.pptx` 与 `deck/qa.json`）：

   ```bash
   python deck/build_deck.py        # 需要 python-pptx、Pillow、lxml
   ```

3. 材料级校验（截图过期、旧日期混入、哈希不符都会失败）：

   ```bash
   node scripts/verify-review-deck.cjs
   ```

视频源：`delivery/film-review.html`（单文件确定性时间线，`window.__seek(t)`）。
