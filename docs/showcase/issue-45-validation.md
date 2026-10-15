# Issue #45 两分钟展示影片验收

2026-10-15：按用户“学习 Pioneer、加入好看的镜头、控制两分钟、发挥创造力”的最新授权，完成 120 秒／18 镜原创编排并通过下列工程验收。当前范围、唯一会话与交付 SHA 见[执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/45#issuecomment-6164068934)。`9e225977` 的 180 秒影片及更早候选保留在原提交，不作为本轮证据。本次没有合并、发布、部署或正式提交。

## 交付与绑定

- [H.264 MP4](../../showcase/privacytrace/delivery/PrivacyTrace-1080p.mp4)：120 秒、1920×1080、30 fps、3600 帧，15,207,468 字节；字幕烧录，原创器乐，无旁白。
- [离线源码 ZIP](../../showcase/privacytrace/delivery/PrivacyTrace-Source.zip)：25,264,645 字节，解压打开 `index.html` 即可播放。包含本地字体、截图、配乐、分镜、透视相机代码与验证附件。
- [manifest.json](../../showcase/privacytrace/delivery/manifest.json)：MP4 `8c61fd272be4dfa4ea450db7c37458777f22283970f671e22789e9b60fe1bcf4`；ZIP `62111a4ec2aa14b0573afef29d998a4e885ef364a2ea6f253efa2e3411b53df2`；视觉源码 `1f44b21d1fe37acee280d613ebff4d6f70a236fa9d1881f51db6349fafcc5f81`。
- [两分钟镜头与文字稿](issue-45-cinematic-120.md)、[播放与重做](../../showcase/privacytrace/README.md)、[来源与许可](../../showcase/privacytrace/ASSETS.md)。

## 对照八项 Acceptance Criteria

| 验收项 | 本轮实际结果 |
| --- | --- |
| 本地离线 HTML 与控制 | 导航前设置 offline，file URL 实际播放；7 项控制通过，1440／768／390 宽度无水平溢出。HTML 完整到 120 秒。搬迁源码包再做离线播放、暂停及 18 点 seek |
| 实际 MP4 规格与音轨 | H.264／yuv420p、1080p、30/1、3600 帧、120 秒；AAC 48kHz 双声道、120 秒。18 个解码帧与 HTML 导出比较，最大平均 RGB 误差 1.8406 |
| 连贯用户路径与镜头 | 18 镜覆盖 0–120 秒；开场拆开安装包，9 秒空间长廊，16–74 秒同一任务导入／候选／报告／代码，74 秒双页对照，83 秒来源，89 秒后单列历史测试，113 秒收成报告 |
| 身份与回放标识 | 构造 APK、人工政策、实录回放与历史日期／案例编号保留；原创空间段标为镜头／流程／摘录示意。约 3.7 秒来自原扫描事件，镜头停留是编辑时间 |
| 数据与技术事实 | 原 PNG、引句、偏移、版本与未知状态不变；主报告两条均为证据不足；历史 2/6、3/6、6/6 是六场景状态一致数，弃判 0/1/2、失败 0/0/0，不称准确率 |
| 完整播放、跳转、运动与解码 | 18 中点、36 边界与移动中打乱 seek 像素一致；18 镜各检进入变化、阅读像素完全静止、退出变化；原始导帧另有 54 对相机核验。6 个实际批注绘制样本无两标题重叠。HTML／MP4 各完整播放到 120 秒；18 点编码 seek、全片严格解码、无检测到的异常黑段、冻结与音频检查通过 |
| 许可与私有内容 | 10 张截图字节不变；Noto 字体 OFL 随包，原创音乐无采样。搬迁包核验 49 个文件哈希，另有 files.json；实际可用凭证字节、文本私有路径 0 匹配；包无 APK、数据库、依赖或帧缓存 |
| 源码、说明与证据 | 同一分镜时长驱动控制、相机、导出、音乐及媒体验收；HTML／MP4 绑定同一视觉源码；源码 ZIP、制作说明与六份本轮收据齐备 |

## 创作与独立复核

直接观看 Pioneer v8 实际成片的取样帧并读其分镜，提炼物理面板厚度、景深、正面阅读和首尾呼应，自行实现分层安装包、三屏长廊、代码／政策对照和报告收拢。没有复制 Pioneer 素材、角色、文案或音乐。`cinema.js` 的解析透视与纹理网格按绝对时间求值，运动段有短暂对焦，产品阅读段直接绘制清晰原图。

独立只读复核查看 17 张入场／阅读／收尾帧，未发现接缝、正文裁切、主文遮挡或结果升级；根据建议增加片头卡组与标题的间距。主代理另查看关键帧。固定帧仅证明采样状态，连续时间通过真实播放及运动／静止检查补充；不据此推断用户认可审美。

片头在 5.2 秒后停稳，其他进入／退出时长来自分镜。冻结检查仅接受声明的阅读段；编码缓动尾部容差 0.4 秒，原始帧进出变化与静止检查仍严格。最后退出相机实际移动，未用尾帧冻结填时。

## 取材与事实范围

#44 已 closed，[PR #57](https://github.com/MrEcho114/PrivacyTrace/pull/57) 合并 main `6d781fde97fe69169db916ab473224a24ed5ce93`。取材使用此版本；该 main 的 [Check](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38534809969)、[Browser Acceptance](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38534809579)、[Spec30 Integration](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38534809536) 均成功。这些 CI 证明前置版本，不代替本片验收。

[capture-provenance.json](../../showcase/privacytrace/capture-provenance.json) 记录 2026-10-14 新构造二进制 APK、job `27aa4ea8914e48c38a7964d7f145121c`、两份独立人工 HTTP 政策及一个被拒私网来源。两个真实 `deepseek-flash` 请求产生 3 个候选；浏览器逐字定位、修改条件并保存，再经普通上传 lane 和真实受限 Docker 生成持久化报告。隔离收据的容器创建、输入移除和清理核验均为 true。

HTTP 政策和 DNS 是本地取材夹具；没有把这次操作称作真正厂商官网抓取。模型只接收人工政策短文，不接收 APK／代码。候选的 checked 是浏览器操作与出处核验事实，不是人类语义或全文复核。主案例保留 PARTIAL／UNREVIEWED／NOT_CHECKED；API 位置 `classes.dex`、`run()V`、offset 6 和 `getLastKnownLocation` 来自同一报告。原始 PNG 未涂改，电影只裁切／放大并另列摘录。

历史事实不重新评测或改真值：

- [Issue #18](https://github.com/MrEcho114/PrivacyTrace/issues/18) 当前为 closed；已验收内部回放包绑定 `9e56771bca0c1c8db947f4c1d59ee76795ac40ea`，包 SHA256 `8e7cb5e96b383205322374eb9cec0c30fa911fc2aba2b0fc8c11bb592b966cef`。本片另有自己的 capture／render／playback 收据，不拿旧包或旧 CI 冒充新影片。
- [Issue #25](https://github.com/MrEcho114/PrivacyTrace/issues/25) 当前为 closed，[PR #54](https://github.com/MrEcho114/PrivacyTrace/pull/54) 已合并。六场景比较原执行 SHA `323780c9a77d7de2bb1857b1b67b4f05fd94a525`，见 [comparison.json](../stages/spec30/comparison.json) 与 [verification-summary.json](../stages/spec30/verification-summary.json)。原逐作业输出／完整 stdout 未保存的部分仍是资料缺口；影片只用可核对的历史摘要，不声称补齐了原运行凭据。
- C02 原句“我们访问精确位置。”、C03“本自建测试应用访问位置信息，用于静态规则测试。”、C05“本自建测试应用不访问精确位置。”、C06“后续正文和适用范围尚未提供。”分别来自 [冻结输入](../../benchmarks/controlled/)，状态和案例编号分开呈现。
- GKD 1.12.1 只采用 [2026-10-09 真实样本记录](../stages/s1-pr29-real-sample-verification-20261009.md) 的元数据、3 条证据不足及未知边界；政策快照为 2026-10-03／v1.0，不声称当前政策、实际采集、违法、安全、完整行为或附件已核验。

## 验证命令与证据

| 实际执行 | 本轮结果 |
| --- | --- |
| `pwsh -NoProfile -File scripts/check.ps1` | 617 API passed、20 skipped、46 前端 passed；Ruff、治理、契约、类型、构建通过。既有 Starlette warning 保留；跳过不称通过 |
| `node showcase/privacytrace/verify.cjs` | 7 控制、18 中点、36 边界、18 相机阶段检查；[browser.json](evidence/browser.json) |
| `node showcase/privacytrace/render.cjs` | 实际生成 3600 帧、外网请求阻断；[render-result.json](evidence/render-result.json) |
| `python showcase/privacytrace/verify-media.py` | 全片严格解码、无检测到的异常黑段、阅读段与 54 对相机帧、18 个编码帧通过；响度 -18.90 LUFS、峰值 -3.63 dBTP，无中段静音；[media.json](evidence/media.json) |
| `node showcase/privacytrace/verify.cjs --video --full` | HTML／MP4 各到 ended／120 秒，无脚本／媒体错误和外网请求；[browser-and-video.json](evidence/browser-and-video.json) |
| `node showcase/privacytrace/verify-server.cjs` | 11 项通过；[server.json](evidence/server.json) |
| `python showcase/privacytrace/package.py`、`node showcase/privacytrace/verify-package.cjs` | 文件绑定、搬迁后离线播放、18 点 seek 与私有内容扫描通过；[package.json](evidence/package.json) |

上一候选的 DNS 剩余预算最小修复保留原提交；本轮仅改影片与说明，没有新后端、接口、规则或基准修改。完整最终 diff 与独立源码审阅完成后推送；远端 CI 绑定最终 SHA，以当前执行记录与 PR 为准，不代替本机影片验收。

## 正式材料格式差异

2026-10-14 核对 [2026 官方电脑版作品提交流程](https://www.cmit.cn/html/liucheng/show-277-45689-1.html)：作品／答辩视频至少 1 个、最多 2 个，每个不超过 1G；视频与答辩 PPT 至少提交一种，PPT 不超过 200MB；参赛打包文件支持 ZIP／RAR／7Z，不超过 10GB。此页面没有规定视频时长、分辨率、帧率或容器。

本片约 15.2MB，源码 ZIP 约 25.3MB，低于对应大小上限；120 秒、1080p、30 fps、H.264 MP4 是用户选择，并非官方要求。源码 ZIP 是影片维护包，未充当完整赛事资料包。赛道／分类及另行说明可能改变适用要求，正式提交仍按 [Issue #43](https://github.com/MrEcho114/PrivacyTrace/issues/43) 的最后确认；本次没有代填、上传或提交，也没有修改 #19／#43。

## 已知边界

没有人类听感或审美签字。原截图只代表捕获区域，部分底缘有下一节内容截断；当前焦点另有完整特写。参考三屏长廊是概览，阅读使用后续大图。

双页面同时播放的无头浏览器最后定期样本在 106.91 秒记录 8 个 dropped frames，计数包含之前 18 次 seek；最终到 ended／120 秒，文件本身 3600 帧独立完整解码。没有声称浏览器零丢帧。
