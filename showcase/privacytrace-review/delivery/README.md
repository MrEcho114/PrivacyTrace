# PrivacyTrace · 作品评审片（120 s）

按定位、创新、关键实现、真实成果、团队贡献组织。深色底、琥珀色强调，保留原 96 BPM 原创器乐，无旁白。

本轮按用户授权重新梳理文案，结语为「隐私分析，有据可查。」副句为「从代码位置到政策原句，保留可复核的依据。」界面仍使用 `20261023-v02` 批次（`2026-10-23 @ f81ca20`），没有重采集、重扫 APK 或改动 PPT。

## 文件与验证

| 文件 | 用途 |
| --- | --- |
| `PrivacyTrace-Review-1080p.mp4` | 120.000 s / 1920×1080 / 30 fps / H.264 yuv420p + 原始 AAC |
| `film-review.html` | 确定性时间轴，按绝对时间重建全部场景 |
| `render-proof.json` | 本轮源文件/配乐/成片哈希、正逆序与重复 seek、全片解码结果 |
| `manifest.json` | 当前文件字节数、SHA-256、ffprobe、黑场和响度实测 |
| `contact-sheet.png` | 最终 MP4 的代表帧 |
| `poster.png` | 最终 MP4 的 8.5 s 片名帧 |
| `materials.json` | 共享采集批次与素材哈希 |
| `BEATS.md` | 分镜及历史事实来源 |

## 本轮调整

手机报告与证据详情使用同一位置、同一尺寸，切换时保留设备位置。长图移到关键局部后停留；实现细节页使用短交叉淡化，并增大参数与说明字号。流水线五节点收进左侧区域，不再越出画面或被手机挡住。结果标题与四张统计卡之间留出间距。

两片文案由两个 GPT-6 Luna 子代理按 humanizer-zh 分别整理，主代理核对并整合。原事实数字、代码片段、政策引文、提交与日期保留。

## 复跑

从仓库根目录运行，环境要求见 `showcase/privacytrace-90s/README.md`。

```bash
node showcase/render-films.cjs review check
node showcase/render-films.cjs review stills
node showcase/render-films.cjs review render 4
python showcase/finalize-films.py
python showcase/validate_materials.py
```

渲染中间文件位于忽略目录 `tmp/film-render/review/`。`finalize-films.py` 汇总本轮实测，重建清单；不复用旧 EAC 的 job 或固定通过标志。

## 评审 PPT

| 项 | 值 |
| --- | --- |
| 文件名 | `PrivacyTrace-Review.pptx` |
| 版本 | v0.3（学术论文风；`od-hps-academic-paper`，MIT，`lewislulu/html-ppt-skill`） |
| 页数 / 备注 | 10 / 10 |
| 字节数 | 1,114,540 B |
| SHA-256 | `c57840cb80dfe8036ab2c8a3751bcf2236471d6814b5d91ee94fc56195860069` |
| 结构 | 封面 / 目录 / 定位 / 创新 / 关键实现 / 新版 Android App / 真实成果 I / 真实成果 II / 原创贡献 / 结语与材料 |
| 界面图 | 第 6 页：2026-10-23 采集，390×844 DPR 3，提交 `f81ca20`；清单见 `../capture/manifest.json` |
| 源 / 生成 | `../deck/academic.html` → `node scripts/render-academic-deck.cjs` → `python ../deck/build_academic_pptx.py` |
| 备注 | 每页含演讲备注；每页是 1920×1080 渲染图，文字不可编辑；事实、数字与边界与影片同一组 |
| 校验 | `node scripts/verify-academic-deck.cjs`（20 项） |
| 边界 | 不是真机、不是 APK 扫描结论；上传前需人工确认视觉与匿名化 |

## 数字与绑定（片内可核）

- 工程门禁：`1578 passed / 179 skipped`、e2e `65`、Web 单测 `111`、生产构建通过；绑定 `65b49f7`（2026-10-21）。
- 部署验收：`40 pass / 0 fail / 0 skip`；四入口 4/4；唯一既有豁免 `dedicated-scan-host-verification`（用户授权）；同绑定 `65b49f7`。
- 受控评测：12 情景状态一致 `12 / 12`、API 基线 `4 / 12`、权限+关键词 `2 / 12`；36 行、执行失败 0；绑定 `b0b3c74`。
- H 矩阵：`11 通过 / 1 未通过`；H12（J × splits × 手机模型）失败，复现 2 次；绑定 `2626152`（2026-10-22）。
- GKD v1.12.1（仅 1 个历史样本）：`6 证据 / 3 行为 / 2 声明 / 3 问题`，3 条结论均 `INSUFFICIENT_EVIDENCE`；2026-10-09 历史记录，本轮未重扫。
- 离线回放：24 成员 / 18 行对照；绑定 `9e56771`（2026-10-13）。

## 素材与交付范围

手机画面为生产 `MobileApp.vue` 加假原生桥的 Chromium 390×844 移动视口模拟。报告与证据来自 `gkd-s1-first` 历史持久化回放，原生成 2026-10-03；本轮未重扫。示例代码/政策原句为人工构造材料。截图与录制的来源见 `capture-provenance.json`。

H12 失败保留为 11 通过 / 1 未通过；受控 12/12 是名义状态一致数；GKD 仅一例历史样本，三条结论均为证据不足。工程与评测数字分别绑定历史提交，不表示本轮重新获得了这些验证结果。

音轨为 `showcase/privacytrace/soundtrack.py` 原有原创合成器乐，seed 451014，无采样、无人声；本轮直接复用 `assets/soundtrack.m4a`。PPT 仍归 #265；参赛包、系统上传与合并没有在本轮执行。
