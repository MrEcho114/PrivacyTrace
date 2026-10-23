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

画面重构为冷白、深蓝与单一蓝色强调。片头先给代码位置和政策原句两个完整画幅，连线建立对应关系，再引出产品名；45 秒的证据段沿用同样的两端构图，明确标注人工构造示例。

20–22 s 保留同源手机画布的连续移动与放大。五段操作录制使用 30 fps / 505 帧；手机里的裁切区域带描边，连线接到右侧从同一帧抽出的局部。放大区域随当前步骤展开，不另造 UI 或状态。

报告与证据在同一设备位置切换，长图移动到所需局部后停留。结果段由四栏累积改为四类结果依次占据主画幅，侧栏显示当前类别，事实数字静止呈现。结语保留「隐私分析，有据可查。」与既有副句。

保留原曲，纸张气流与木质接触声重新对齐片头、结果及贡献等切换。音效由脚本原创合成，无外部录音样本。两遍响度处理目标为 −16 LUFS、真峰上限 −2 dBTP；最终 AAC 实测见 QA。全部场景按绝对时间重算，保证跨章节 seek 不残留状态。

## 分镜

| 时间 | 内容 |
| --- | --- |
| 0–9 s | 代码位置与政策原句先后出现，连线建立关系，再引出片名 |
| 9–21 s | 导入材料、核对候选、分析进度、对照报告 |
| 21–45 s | 五段真实界面录制，加同帧局部放大 |
| 45–60 s | 人工构造示例：代码位置与政策原句 |
| 60–72 s | Android App 报告与证据详情局部 |
| 72–84 s | 工程、部署、受控评测、历史真实样本，四类结果分别列出 |
| 84–90 s | 「隐私分析，有据可查。」与片名 |

## 取材与数字

所有界面图注为 `2026-10-23 @ f81ca20`。Android App 画面来自生产 `MobileApp.vue` 加假原生桥的 Chromium 390×844 移动视口模拟。报告来自 `fixtures/acceptance-jobs/gkd-s1-first.json` 持久化回放，原生成于 2026-10-03；不是本轮新扫描。

原始录制为 390×844、30 fps、16.833008 s。截图为 780×1688（导入/候选）、780×4438（报告）、780×6258（证据）。505 张 30 fps JPEG 抽帧不入库，可从录制重建。

工程 1578 passed / 179 skipped、e2e 65、Web 111，以及部署 40 pass / 0 fail / 0 skip，绑定 `65b49f7`（2026-10-21）。受控场景 12/12、两基线 4/12 与 2/12，绑定 `b0b3c74`，为名义状态一致数。真实样本只有 GKD v1.12.1 一例（2026-10-09），三条结论均为证据不足。本片不展开 H12，评审片保留 11 通过 / 1 未通过。

证据示例为人工构造静态片段；静态线索、政策声明与推断分开。分镜和文案由 AI 辅助，产品画面来自移动视口录制。PPT、参赛包、上传与合并不在本轮范围内。

## 复跑

从仓库根目录运行，需 Node.js、仓库 Playwright、Chromium、ffmpeg/ffprobe；Python 质检需要 Pillow，混音脚本需要 numpy。Windows 若浏览器装在用户目录，可设置 `PLAYWRIGHT_BROWSERS_PATH` 指向该目录。

```bash
bash showcase/privacytrace-90s/frames.sh
python showcase/mix-film-sound.py
node showcase/render-films.cjs 90s check
node showcase/render-films.cjs 90s stills
node showcase/render-films.cjs 90s render 4
python showcase/finalize-films.py
python showcase/validate_materials.py
```

渲染为 PNG 逐帧输入 H.264（CRF 18、yuv420p），使用 `assets/soundtrack-polished.m4a` 新混音；原曲 `soundtrack-90s.m4a` 仍保留。音效时点、合成种子、原曲哈希和两遍处理参数见 `assets/sound-provenance.json`。`check` 对章节点正序、逆序和重复 seek 比较 PNG SHA-256，并检查五个操作状态的画布截图不同。`render` 完成后执行整片音视频解码；最终记录由 `finalize-films.py` 汇总，不能套用原 EAC job 的自检结论。

渲染证明还记录完整素材目录树的 SHA-256（包括 505 张派生帧）；检查或渲染过程中素材变化会直接失败。定稿再次核对当前素材树与两份证明，避免渲染后换图却沿用旧记录。
