# PrivacyTrace · 作品评审片（120 s）

按定位、创新、关键实现、真实成果、团队贡献组织。深色底、琥珀色强调，保留原 96 BPM 原创器乐，无旁白。

本轮按用户授权重新梳理文案，结语为「隐私分析，有据可查。」副句为「从代码位置到政策原句，保留可复核的依据。」界面仍使用 `20261023-v02` 批次（`2026-10-23 @ f81ca20`），没有重采集、重扫 APK 或改动 PPT。

## 文件与验证

| 文件 | 用途 |
| --- | --- |
| `PrivacyTrace-Review-1080p.mp4` | 120.000 s / 1920×1080 / 30 fps / H.264 yuv420p + 新混音 AAC |
| `film-review.html` | 确定性时间轴，按绝对时间重建全部场景 |
| `render-proof.json` | 本轮源文件/配乐/成片哈希、正逆序与重复 seek、全片解码结果 |
| `manifest.json` | 当前文件字节数、SHA-256、ffprobe、黑场和响度实测 |
| `contact-sheet.png` | 最终 MP4 的代表帧 |
| `poster.png` | 最终 MP4 的 8.5 s 片名帧 |
| `materials.json` | 共享采集批次与素材哈希 |
| `BEATS.md` | 分镜及历史事实来源 |

## 本轮调整

采用深蓝底、浅蓝强调和无衬线大字。创新段先展示代码位置与政策原句，证据示例退场后，三条原则依次独占主画幅。实现段先给完整五节点路线，再收起路线，切换四页大号参数；报告与证据沿用同一设备位置，长图到关键局部后停留。

成果段依次展示工程、部署、受控评测和 H 矩阵/GKD，每次只显示当前一类。三方案比较保留共同的 12 格分母，按阅读顺序展开；H12 失败复现 2 次和单一历史 GKD 样本的三条证据不足完整保留。最后再给出工程、受控和真实样本的关系图。

贡献段分成团队工作、AI 用途/披露、提交记录三拍；前一拍退出后下一拍进入，避免卡片与账本叠加。结语仍为「隐私分析，有据可查。」与既有副句。两名 GPT-6 Luna 按 humanizer-zh 整理的文案由主代理核对整合，原事实数字、代码片段、政策引文和历史提交绑定保留。

原 96 BPM 音乐保留，少量原创合成声效重新对齐新镜头。无外部录音样本；两遍响度处理目标 −16 LUFS、真峰上限 −2 dBTP，最终 AAC 实测见 manifest.json。

## 复跑

从仓库根目录运行，环境要求见 `showcase/privacytrace-90s/README.md`。

```bash
python showcase/mix-film-sound.py
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

音轨为 `showcase/privacytrace/soundtrack.py` 原有原创合成器乐，seed 451014，无采样、无人声；原曲 `assets/soundtrack.m4a` 保留；本轮渲染使用 `assets/soundtrack-polished.m4a`，事件、种子、原曲哈希和混音参数见 `assets/sound-provenance.json`。PPT 仍归 #265；参赛包、系统上传与合并没有在本轮执行。

渲染与 seek 证明同时绑定完整素材目录树，定稿核对源文件、音轨、素材树和成片身份。混音溯源记录的是 loudnorm 滤镜输出、编码前的测量，成片 QA 记录编码后实际电平。
