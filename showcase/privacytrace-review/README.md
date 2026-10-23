# PrivacyTrace · 作品评审材料（专家版）

面向竞赛专家评审的视频 + PPT，按「定位 / 创新 / 关键实现 / 真实成果 / 学生原创贡献」组织。

## 文件

- 视频：[`delivery/PrivacyTrace-Review-1080p.mp4`](delivery/PrivacyTrace-Review-1080p.mp4)（120.000 s，1920×1080，30 fps，H.264/AAC，原创配乐，无旁白；Android App 单一前端，390×844 移动视口模拟）
- PPT：[`delivery/PrivacyTrace-Review.pptx`](delivery/PrivacyTrace-Review.pptx)（10 页，v0.3 学术论文风，逐页渲染图 + 备注；源 `deck/academic.html`）
- 说明：[`delivery/README.md`](delivery/README.md)
- 分镜 / 事实绑定：[`delivery/BEATS.md`](delivery/BEATS.md)
- SHA-256 / ffprobe / QA：[`delivery/manifest.json`](delivery/manifest.json)
- 界面采集清单：[`capture/manifest.json`](capture/manifest.json)（第 6 页的移动 App 截图，含提交、日期、视口与哈希）

## 边界

- H12（J × splits × 手机模型）失败，复现 2 次，保留为 `11 通过 / 1 未通过`。
- 受控 12 场景：状态一致 12/12；API 基线 4/12；权限 + 关键词 2/12。
- 真实 App 仅 1 个历史样本（GKD v1.12.1），3 条结论均为 `INSUFFICIENT_EVIDENCE`。
- 界面：Android App 390×844 移动视口模拟（生产 `MobileApp.vue` + 假原生桥）。
- 提交状态以报名系统实际提交与回执为准；本目录只固定材料版本与哈希。

## 生成

1. 采集移动 App 截图（生产 Vue + 受控 native bridge；输出 `capture/` 与 `capture/manifest.json`）：

   ```bash
   node scripts/capture-review-deck-shots.cjs
   ```

2. 渲染并装配 PPTX（源 `deck/academic.html`，`od-hps-academic-paper`；逐页 1920×1080，写入 `deck/qa.json`）：

   ```bash
   node scripts/render-academic-deck.cjs
   python showcase/privacytrace-review/deck/build_academic_pptx.py   # 需要 python-pptx
   ```

3. 材料级校验（截图过期、旧日期混入、哈希不符都会失败）：

   ```bash
   node scripts/verify-academic-deck.cjs
   ```

视频源：`delivery/film-review.html`（单文件确定性时间线，`window.__seek(t)`）。
