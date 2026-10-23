# PrivacyTrace · 作品评审材料（专家版）

面向竞赛专家评审的视频 + PPT，按「定位 / 创新 / 关键实现 / 真实成果 / 学生原创贡献」组织。

**v0.2（批次 `20261023-v02`）**：以 `f81ca201b932a11e24a9f7175a9583150d44e9ed` 为唯一基线，2026-10-23 重采界面素材并重渲评审片；PPT 未改（唯一汇报 PPT 由 #265 负责）。

## 文件

- 视频：[`delivery/PrivacyTrace-Review-1080p.mp4`](delivery/PrivacyTrace-Review-1080p.mp4)（120.000 s，1920×1080，30 fps，H.264/AAC，原创配乐，无旁白）
- PPT：[`delivery/PrivacyTrace-Review.pptx`](delivery/PrivacyTrace-Review.pptx)（10 页，可编辑，含逐页备注）
- 说明：[`delivery/README.md`](delivery/README.md)
- 分镜 / 事实绑定：[`delivery/BEATS.md`](delivery/BEATS.md)
- 素材清单 / 采集溯源：[`delivery/materials.json`](delivery/materials.json)、[`delivery/capture-provenance.json`](delivery/capture-provenance.json)
- SHA-256 / ffprobe / QA：[`delivery/manifest.json`](delivery/manifest.json)
- 重渲脚本：[`build_manifest.py`](build_manifest.py)（用真实文件重算 manifest）

## 边界

- H12（J × splits × 手机模型）失败，复现 2 次，保留为 `11 通过 / 1 未通过`。
- 受控 12 场景只写“状态一致”，不是真实 App 的准确率；P/R/F1 按协议 N/A。
- 真实 App 仅 1 个历史样本（GKD v1.12.1），3 条结论均为 `INSUFFICIENT_EVIDENCE`。
- 前端仍在开发；界面素材统一标注「开发版 · 2026-10-23 @ f81ca20」，最终视觉可能变化。
- 项目只有一个前端：Android App；Android App 画面是 Chromium 移动视口模拟（非真机）。
- 报告长图来自持久化回放 fixture（原生成 2026-10-03），不是本批次新扫描。
- 不宣称 100% 独立、不给 AI 代码比例、不宣称开源。
- Issue #200 / #107 已改为「PPT + 视频都要」；系统两个栏目分别上传，上传时间与系统反馈仍待人工记录。

## 生成

PPT 生成脚本：`deck/build_deck.py`（python-pptx；输入图在同目录）。
视频源：`delivery/film-review.html`（单文件确定性时间线，`window.__seek(t)`）。
采集：`showcase/materials-20261023-v02/`（批次说明与两个 Playwright 脚本）。
重渲后：`node showcase/materials-20261023-v02/build-materials.cjs` → `python showcase/privacytrace-review/build_manifest.py` → `python showcase/validate_materials.py`。
