# PrivacyTrace · 作品展示片（90 s）

展示作品是什么、如何操作、报告提供哪些依据。暖纸底、陶土色强调，无旁白，保留原有 80 BPM 原创配乐。

本轮按用户授权重写两片文案，统一结语为「隐私分析，有据可查。」副句为「从代码位置到政策原句，保留可复核的依据。」采集批次仍为 `20261023-v02`，界面基线仍为 `f81ca20`；没有重新采集或扫描 APK。

## 成片与源文件

- `delivery/PrivacyTrace-作品展示-90s.mp4`：90.000 s，1920×1080，30 fps，H.264 / AAC。
- `film-showcase.html`：确定性时间轴，`window.__seek(t)` 等待当前录制帧解码完成。
- `delivery/contact-sheet.png`：从最终 MP4 抽取的 12 个章节点。
- `delivery/qa.json`：ffprobe、黑场、冻结段与响度实测。
- `delivery/render-proof.json`：源文件、配乐、成片哈希，全片解码与跨章节 seek 实测。
- `materials.json`：当前成片与素材身份；字节数、SHA-256 以此文件为准。
- `BEATS.md`：分镜与历史事实来源。`capture-provenance.json`：采集来源。

## 本轮调整

操作段保留完整手机画面，旁边放大同一录制帧的局部，并显示当前操作说明。放大画面直接裁自原始录制，没有另造 UI 或状态。五段窗口与原片时间轴一致。

报告段放大两台设备，先看报告，再看证据；长图只移动到所需局部并停留，滚动距离受实际图片高度约束。结果段保留四类数字、来源和限定，增大字号。章节来回跳转时，所有场景按绝对时间重算，避免保留上一次 seek 的状态。

## 分镜

| 时间 | 内容 |
| --- | --- |
| 0–9 s | 片名、定位「从静态线索到原始依据」 |
| 9–21 s | 导入材料、核对候选、分析进度、对照报告 |
| 21–45 s | 五段真实界面录制，加同帧局部放大 |
| 45–60 s | 人工构造示例：代码位置与政策原句 |
| 60–72 s | Android App 报告与证据详情局部 |
| 72–84 s | 工程、部署、受控评测、历史真实样本，四类结果分别列出 |
| 84–90 s | 「隐私分析，有据可查。」与片名 |

## 取材与数字

所有界面图注为 `2026-10-23 @ f81ca20`。Android App 画面来自生产 `MobileApp.vue` 加假原生桥的 Chromium 390×844 移动视口模拟。报告来自 `fixtures/acceptance-jobs/gkd-s1-first.json` 持久化回放，原生成于 2026-10-03；不是本轮新扫描。

原始录制为 390×844、30 fps、16.833008 s。截图为 780×1688（导入/候选）、780×4438（报告）、780×6258（证据）。168 张 10 fps JPEG 抽帧不入库，可从录制重建。

工程 1578 passed / 179 skipped、e2e 65、Web 111，以及部署 40 pass / 0 fail / 0 skip，绑定 `65b49f7`（2026-10-21）。受控场景 12/12、两基线 4/12 与 2/12，绑定 `b0b3c74`，为名义状态一致数。真实样本只有 GKD v1.12.1 一例（2026-10-09），三条结论均为证据不足。本片不展开 H12，评审片保留 11 通过 / 1 未通过。

证据示例为人工构造静态片段；静态线索、政策声明与推断分开。分镜和文案由 AI 辅助，产品画面来自移动视口录制。PPT、参赛包、上传与合并不在本轮范围内。

## 复跑

从仓库根目录运行，需 Node.js、仓库 Playwright、Chromium、ffmpeg/ffprobe；Python 质检需要 Pillow。Windows 若浏览器装在用户目录，可设置 `PLAYWRIGHT_BROWSERS_PATH` 指向该目录。

```bash
bash showcase/privacytrace-90s/frames.sh
node showcase/render-films.cjs 90s check
node showcase/render-films.cjs 90s stills
node showcase/render-films.cjs 90s render 4
python showcase/finalize-films.py
python showcase/validate_materials.py
```

渲染为 PNG 逐帧输入 H.264（CRF 18、yuv420p），直接复用原始 AAC 音轨；没有重混配乐。`check` 对章节点正序、逆序和重复 seek 比较 PNG SHA-256，并检查五个操作状态的画布截图不同。`render` 完成后执行整片音视频解码；最终记录由 `finalize-films.py` 汇总，不能套用原 EAC job 的自检结论。
