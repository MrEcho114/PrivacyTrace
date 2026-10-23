# PrivacyTrace · 作品展示片（严肃展示版 · 90 s）

面向竞赛的作品展示视频。同项目的《作品评审片（专家评审版 · 120 s）》是另一支片子：

| | 作品评审片 120 s | 作品展示片 90 s（本片） |
| --- | --- | --- |
| 目的 | 向专家逐段举证、交代边界与缺口 | 展示作品是什么、怎么用、跑出来什么样 |
| 叙事 | 定位 / 创新 / 关键实现 / 真实成果 / 原创贡献 | 片头 / 作品 / 操作 / 证据 / 报告 / 结果 / 结语 |
| 语气 | 论证、防御性（保留 H12 失败、AI 披露、四类数字） | 陈述、克制（只保留必要边界） |
| 画面 | 深色证据审阅台、琥珀强调、等宽标注 | 暖纸展厅、陶土单强调、衬线大标题、博物馆式图注 |
| 素材 | 静态截图 + 报告长图 | 真实界面录制（Android App 实录，五段窗口）+ 静态图版 |
| 时长 | 120.000 s | 90.000 s |

> **v0.2（批次 `20261023-v02`）**：以 `origin/main` 的 `f81ca201b932a11e24a9f7175a9583150d44e9ed` 为唯一基线，2026-10-23 重采三张界面图与操作录屏，片内图注升级为「日期 @ 提交」。数字、叙事、章节、配乐与节拍未改。

## 文件

```
showcase/privacytrace-90s/
├─ README.md                             本文件
├─ BEATS.md                              分镜与事实绑定表
├─ materials.json                        素材清单：文件名、字节、SHA-256、采集提交与日期
├─ film-showcase.html                    确定性时间轴（window.__seek(t)，可重渲）
├─ frames.sh                             从录制重建 10 fps 抽帧（assets/android-rec/）
├─ qa.py                                 媒体质检（ffprobe / 黑场 / 冻结 / 响度）
├─ contact-sheet.py                      12 个章节点联系表
├─ score.py                              原创配乐合成脚本（80 BPM / 90 s）
├─ score-provenance.json                 配乐溯源（速度、结构、SHA-256）
├─ capture-provenance.json               录制的溯源（批次、URL、动作脚本、状态覆盖、静态图来源）
├─ assets/
│  ├─ recording-android.mp4              原始界面录制（16.83 s / 1920×1080）
│  ├─ stills/                            Android App / Android App 报告 / Android App 报告截图
│  ├─ soundtrack-90s.m4a                 原创配乐
│  └─ android-rec/                               10 fps 抽帧（168 张，不入库；跑 frames.sh 重建）
└─ delivery/
   ├─ PrivacyTrace-作品展示-90s.mp4       最终成片（H.264 / AAC）
   ├─ contact-sheet.png                  12 个章节点联系表
   └─ qa.json                            质检结果（流信息 / 黑场 / 冻结 / 响度）
```

渲染用的 168 张抽帧（`assets/android-rec/`）不入库，跑 `bash frames.sh` 从 `assets/recording-android.mp4` 重建。本地交付副本（同样不入库）另存于 `tmp/materials-v02/`。

EAC 工程 `dd433382-7f8f-4e65-a47a-b8c2c9aea687`，项目「PrivacyTrace 作品展示片（严肃展示版 90s）」，模板 `motion-promo-film`；v0.2 渲染 job `5169273e-358e-4fcd-becd-0f962b518aea`。

## 规格

- 90.000 s / 1920×1080 / 30 fps / H.264 High / AAC 96 kHz 立体声
- 无旁白；字幕烧录在画面内；原创器乐，无采样、无人声
- 六个章节；主切点落在 80 BPM 的 3.000 s 小节网格上（30 小节 = 90 s）

## 叙事

1. 片头（0–9 s）：作品名与一句话定位「只对照，不判定。」
2. 作品（9–21 s）：四步流程（APK 与政策材料 → 核对政策声明 → 扫描与对照进度 → 对照报告）与Android App 图版。
3. 操作（21–45 s）：真实界面录制，五段窗口：导入 → 候选与「定位原句」→ 五阶段流程演示 → 报告三条结果 → 证据面板切换。
4. 证据（45–60 s）：一条证据的两个终点。左边 DEX 方法与偏移，右边政策原句与 `[0, 18)` 码点区间。下接三层分离、保留未知、真值冻结。
5. 报告（60–72 s）：Android App 的持久化回放报告长图与证据详情（移动视口模拟）；均标注采集日期与提交。
6. 结果（72–84 s）：四类数字分列，各自绑定提交与日期。
7. 结语（84–90 s）：只对照，不判定。

## 素材与溯源

| 素材 | 来源 | 标注口径 |
| --- | --- | --- |
| Android App 实录 | 本机前端 dev server（`127.0.0.1:6173`，`f81ca20`），2026-10-23，Playwright recordVideo | 「Android App 实录 · 开发版 · 持久化回放样本 · 剪辑节奏，非实时速度」 |
| Android App 截图 | `showcase/materials-20261023-v02/capture-android-flow.cjs`，2026-10-23 @ `f81ca20` | 「开发版 · 2026-10-23 @ f81ca20 · 持久化回放样本」 |
| Android App 报告 | 同一脚本；`gkd-s1-first` 持久化回放全页（780×4438，390 CSS px） | 「PLATE 02 · 持久化回放 · 2026-10-23 @ f81ca20」 |
| Android App 证据 | `showcase/materials-20261023-v02/capture-android-flow.cjs`；生产移动壳 + 假原生桥，390 CSS px | 「PLATE 03 · 视口模拟（非真机）· 2026-10-23 @ f81ca20」 |
| 示例证据 | `samples/demo/evaluation-input.json`（人工构造示例） | 「人工构造的静态片段 · 非真实 App」 |
| 数字 | 工程 `65b49f7`、部署 `65b49f7`、受控 `b0b3c74`、真实样本 2026-10-09 | 每栏脚注写提交与日期 |

素材清单 `materials.json` 记录每个文件的字节、SHA-256、采集提交与日期；`python showcase/validate_materials.py` 在文件缺失、哈希不符、图注缺 token 或 QA 超界时失败。

## 片内的边界标注

- 界面仍在开发。界面镜头标「开发版」与「2026-10-23 @ f81ca20」，不称最终视觉。
- 项目只有一个前端：Android App；Android App 画面是 Chromium 移动视口模拟（生产移动壳 + 假原生桥），不是 Android 真机（ADR-0004）。
- 操作演示使用持久化回放样本（真实 APK 静态报告，原生成 2026-10-03），不证明实际采集；证据章节示例为人工构造。
- 报告长图来自 `fixtures/acceptance-jobs/gkd-s1-first.json` 的持久化回放（原生成 2026-10-03），不是 2026-10-23 新扫描。
- 录制按剪辑节奏播放，窗口之间跳切，画面标了「非实时速度」。
- 受控 12/12 是名义状态一致数，不是准确率；P/R/F1 = N/A。
- 真实样本 1 个（GKD v1.12.1，2026-10-09），三条结果全为 `INSUFFICIENT_EVIDENCE`，本轮未重扫。
- 片尾披露分镜与排版由 AI 辅助、产品画面为真实界面录制；不写「100% 独立完成」，不给 AI 代码比例，不写「开源」。

## 质检

机器质检结果在 `delivery/qa.json`。要点（v0.2）：

- 时长 90.000 s、1920×1080、30 fps、H.264 High 共 2700 帧、AAC 96 kHz 立体声、13,418,327 B。
- SHA-256 `7de0686c08650ec68f6a31c23733a1a5bb2e011bf5e850b22719a5caa409c03e`。
- 黑场 0 段。全片走暖纸底，收尾收在白纸。
- 响度 −16.1 LUFS，真峰 −1.5 dBFS，LRA 2.3。
- 冻结检测报 20 段长停留，最长一段约 7.1 s。这些停留是展厅式阅读节奏；逐帧复核能看到停留段里的文字上浮与图版推进，不是编码卡帧。
- EAC 渲染自检：同一时间点连拍两张，逐像素一致（`deterministic: true`，`meanDifference: 0`；`missingAssets: []`）。
- 人工抽帧复核：`delivery/contact-sheet.png` 的 12 个章节点逐张看过构图、文字与图注，未发现遮挡与错位。

## 重渲

```bash
bash frames.sh                       # 抽帧 -> assets/android-rec/f_0001.jpg …（168 张）
python score.py                      # 配乐 -> assets/soundtrack-90s.m4a
python qa.py                         # 质检 -> delivery/qa.json
python contact-sheet.py              # 联系表 -> delivery/contact-sheet.png
# 渲染（EAC render-template）
#   templateId=motion-promo-film, duration=90, fps=30, scale=1,
#   htmlPath=showcase/privacytrace-90s/film-showcase.html,
#   audioPath=showcase/privacytrace-90s/assets/soundtrack-90s.m4a
# 渲染后回填 materials.json 的成片哈希：
node showcase/materials-20261023-v02/build-materials.cjs
# 评审片的 manifest 会引用 materials.json，需再重生成一次：
python showcase/privacytrace-review/build_manifest.py
python showcase/validate_materials.py
```

成片与源素材之间的对应关系：`film-showcase.html` 按 `assets/android-rec/` 的帧号索引播放（10 fps），
镜头窗口与抽帧时刻写在文件顶部的 `WINDOWS` 表里，与 `BEATS.md` 的分镜表一一对应。
