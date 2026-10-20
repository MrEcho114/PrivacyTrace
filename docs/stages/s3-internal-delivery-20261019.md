# S3 内部交付 · 2026-10-19

用户在完成 [#5](https://github.com/MrEcho114/PrivacyTrace/issues/5) 的本次会话中明确：**本次仅完成内部交付，正式提交另行跟踪**。本文件固定内部交付的组成；赛事上传、签章、匿名评审材料、分发授权和真实回执继续由 [#20](https://github.com/MrEcho114/PrivacyTrace/issues/20) 跟踪。内部阶段关闭不表示已参赛提交，也不修改项目许可证。

## 固定版本

| 内容 | 固定来源 | 内部用途 |
| --- | --- | --- |
| 六场景离线回放 | #18，`9e56771bca0c1c8db947f4c1d59ee76795ac40ea` | 预生成报告、代码证据、政策引用和全文的回放 |
| 原六场景评测 | #25，`323780c9a77d7de2bb1857b1b67b4f05fd94a525` | 原实验的报告、JSON、表格及复算入口 |
| 120 秒影片及可编辑源码 | #45 / PR #58，`b3106d13a785a08265fe3a9cb60ab3fd3fafb970`，已合入 `4cae1fd7e2ddb68345f389aa19535d2fc3db26ec` | 实录素材编排的操作回放，含字幕和原创配乐，无旁白 |
| 技术说明、贡献与 AI 使用、许可说明 | [项目介绍](../project-introduction-draft.md) 第 4–7 节及本文件；汇总基线 `6f2b0892fd195b02b37aca5c79644815f3ce9979` | 内部事实清单，保留未知与历史时点；不是匿名报名终稿 |

各产物分别绑定自己的版本。影片取材于 `6d781fde97fe69169db916ab473224a24ed5ce93` 的新构造 APK 和人工短政策，不是六场景离线包的新界面。#18 原包没有重新构建或替换。冻结对象是所列文件及摘要，不宣称 10/17 已完成全仓库代码冻结；main 和后续 Android / 公网 PR 可独立继续研发。

机器可读来源与摘要见 [交付索引](s3-internal-delivery-20261019.json)。替换文件需生成新的归档清单、重验受影响路径，不把本次证据迁移到新版本。

## 内部包与运行

内部归档 `PrivacyTrace-S3-internal-20261019.zip` 包含：

- `01_replay/`：从 #18 原归档逐字节提取的 `offline/`，含 viewer、前端、六报告、comparison 和 Vue/Vite 许可。
- `02_film/`：原 MP4、可编辑 HTML 源码 ZIP、影片 manifest 与素材许可说明。
- `03_materials/`：技术说明、六场景报告/数据/表格/复算脚本、影片说明及本交付索引。
- `04_evidence/`：#18 原始 ZIP、原断网证明/DOM/截图/日志、影片原验收记录，以及本次完整性、HTTP 回放和媒体解码核验收据。
- `manifest.json`：所有文件的大小与 SHA-256；`README.txt`：运行与限制。外层 ZIP 摘要另存，避免自引用。

内包不含 APK、DEX、数据库、模型响应或密钥。原 #18 证明原样保留。重新下载的原 ZIP 实算为 `8e7cb5e96b383205322374eb9cec0c30fa911fc2aba2b0fc8c11bb592b966cef`，24 个成员；运行包 manifest 为 `430a9fcf0255191d95d98902ed8d9bf846016b43f86d7240407502d1a4f79a44`。

在已预装 Python 3.11+ 和浏览器的机器上，进入 `01_replay/`，运行：

```text
python -B viewer.py --port 8765
```

打开 `http://127.0.0.1:8765`，切换六报告，展开 C02 代码证据、政策引用与全文；`/comparison.html` 展示三方案表。viewer 启动时校验运行包文件集合和摘要，额外文件也会拒绝启动，不在该目录存放日志或缓存。

`02_film/PrivacyTrace-1080p.mp4` 可直接播放；`PrivacyTrace-Source.zip` 解压后打开 `index.html`，可暂停、拖动时间轴和全屏，无需模型、Node 或联网。影片为 120 秒、1920×1080、30 fps；MP4 SHA-256 为 `8c61fd272be4dfa4ea450db7c37458777f22283970f671e22789e9b60fe1bcf4`，源码 ZIP 为 `62111a4ec2aa14b0573afef29d998a4e885ef364a2ea6f253efa2e3411b53df2`。

## 核验与证据边界

- #18 原收据为 clean checkout、11 阶段成功；原 proof 记录 fresh `--network=none`、仅 `lo`、六报告/六来源、C02 三项展开及零页面错误。本次重新核对 receipt → proof → DOM / manifest → 全部运行文件的摘要关联。**这是原 10/13 独立断网运行证据的复核**；本次本地 HTTP 回放不冒充新的干净断网实验。
- 本次核对 MP4/源码 ZIP 与原 manifest，校验源码 ZIP CRC 和逐文件清单，并重新执行 MP4 完整解码及规格检查。原 HTML 连续播放、seek、浏览器控制证据见 [影片验收](../showcase/issue-45-validation.md)，不把本次解码说成重做全部浏览器或听感验收。
- [原评测](pt903-20261012/report.md) 的 `recalculate.py --check` 复算已归档结果：六场景、三方案、18 行，名义状态一致 2/6、3/6、6/6，失败 0/0/0、弃判 0/1/2；P/R/F1 为 N/A，CPU/RSS/I/O 和人工工时未测。这不是后续十二场景实验，也不是真实 App 全局精度。
- GKD 1.12.1 仅为 10/09 历史案例，未重扫；真实 APK、完整真实政策和反编译全文不进入本包。权限是能力，invoke 是静态潜在线索，PARTIAL / UNREVIEWED / NOT_CHECKED 和 UNKNOWN 不因内部交付改变。
- 本次权威工程检查、最终交付 SHA 的 Check / Browser Acceptance / Spec30 Integration 与内部 ZIP 摘要在 [#5 当前记录](https://github.com/MrEcho114/PrivacyTrace/issues/5#issuecomment-6260049721) 回写。新 CI 产物不是本次冻结的 #18 原包，不混用摘要。

## 贡献、AI 与许可

项目介绍第 5 节保留截至 10/13 的公开工作记录；GitHub 账号不能单独证明学生本人完成全部代码，也不能据此补造未留痕的成员分工、工时或人类复核。本次事实核对、材料索引和内部打包由 Codex 执行，Luna 仅只读审计；未新增政策模型调用、真实样本扫描、成员访谈或原创性签署。

影片来源另见 [ASSETS.md](../../showcase/privacytrace/ASSETS.md)：产品实录 PNG、Codex 镜头/字幕代码、程序生成原创音乐，Noto 字体 OFL 文本随源码包。#18 内含 Vue 3.5.43 / Vite 7.3.6 许可副本；预装 Python/浏览器由使用者自行准备。根目录没有项目 LICENSE，**项目源码公开许可仍待团队决定，仅内部核验**。

本包不是正式参赛包。对外使用前由 #20 核对实际上传栏目、匿名化、素材/源码分发权、团队贡献与 AI 披露、最终版本及真实回执。#74 继续供正式提交跟踪；其所述 `docs/competition/2026-submission-guide.md` 在本次 main 基线不存在，不将该归档声明作为已核验证据。

## 阶段收尾

#18/#19/#25/#30/#43/#45 既有关闭状态与原验收时点保留。#5 按用户新范围接受内部交付后关闭；#20 保持开放，#74 正式指南跟踪不随本阶段关闭。文档 PR 仅交付索引修订，合并由用户决定；本次不执行 merge、Release、部署、公开发布或赛事提交。
