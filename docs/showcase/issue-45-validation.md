# Issue #45 展示影片验收

状态：Gemini 完全重写后的新稿八项本地验收完成。核验日期 2026-10-14；这是影片交付候选，不包含合并、公开托管、部署、Release 或正式赛事提交。任务范围和唯一会话见 [当前执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/45#issuecomment-6164068934)。

## 交付与绑定

- [H.264 MP4](../../showcase/privacytrace/delivery/PrivacyTrace-1080p.mp4)：180 秒，1920×1080，30 fps，5400 帧，17,443,403 字节；字幕烧录，原创器乐背景音乐，无旁白。
- [可搬迁源码 ZIP](../../showcase/privacytrace/delivery/PrivacyTrace-Source.zip)：解压后直接打开 `index.html`，无需网络或安装制作工具。JSON 时间表、绘制源码、原始截图、音乐、字体、OFL 和验证附件均在包内。
- [manifest.json](../../showcase/privacytrace/delivery/manifest.json) 绑定最终 MP4、ZIP、视觉源码集合及捕获版本。MP4 SHA256 `ddecdb2d6f6e8ee8b950f005f3bf265e7218b524a7a34f25045ccf17d68ad7e4`；视觉源码 SHA256 `ccadcba67f19c9c5fafbd6382d635685b72542293a63c5f94e8e291b667a4e5b`。ZIP SHA256 `7eb64595b72fba4eec3fab2394729aa36138afe143b50f384c58569066149f76`。
- 源包播放、修改和重做命令见 [README](../../showcase/privacytrace/README.md)；素材身份和许可见 [ASSETS](../../showcase/privacytrace/ASSETS.md)。本仓库只提交交付物和验证收据，帧缓存、原 WAV、运行日志、store、依赖和取材 APK 留在忽略目录。

## 对照八项 Acceptance Criteria

| 验收项 | 实际观察与记录 |
| --- | --- |
| 本地离线 HTML 与五项控制 | Chromium 在导航前 `offline=true`，从 `file://` 加载；播放／暂停、重播、滑块 seek、全屏及键盘／焦点共 7 项通过。1080p 和全屏均容纳画面及控制栏；1440、768、390 宽度无水平溢出。实际 HTML 连续播放到 180 秒；解压到新目录后再次离线播放／暂停及 7 点 seek 通过 |
| 实际 MP4、规格、字幕和音乐 | FFprobe 读取 H.264／yuv420p、30/1、5400 帧、1080p、180 秒；AAC 48kHz 双声道覆盖 180 秒。11 个解码关键帧与 Chromium 同时点比较，最大平均 RGB 误差小于 4；字幕在视频像素中。音乐由原创合成参数生成，无语音输入 |
| 连贯用户路径 | 20 镜头连续覆盖 0–180 秒，8 段叙事保留；同一 job 的 APK、多来源、候选原句／修改、阶段、报告、API 与政策来源组成主路径。其它状态明确切换为带编号的历史受控摘要 |
| 受控、合成、真实和回放标识 | 产品镜头持续显示“构造输入／人工政策／实录回放”；宿主／第三方原句有独立人工夹具标识。阶段停留是编辑时长，字幕不称其为实际等待时长。真实样本只显示历史元数据和边界；没有现场扫描或全文复核声明 |
| 数据和技术事实 | main `6d781fde…` 的新录制来源与历史六场景分别绑定；2/6、3/6、6/6 保留分母、弃判 0/1/2 和失败 0/0/0，不称通用准确率。静态 API 是潜在线索；政策是声明；主案例两条结果均证据不足 |
| 关键帧、跳转、解码和音频 | 20 镜头中点与 40 切换边界逐帧哈希一致，包含打乱顺序 seek；原生 Canvas 导出与实际浏览器截图 RGB 完全相同；MP4 全片严格解码成功，黑帧为 0；冻结检测匹配阅读段且没有跨切镜或意外冻结结尾。最终 HTML／MP4 各实际连续播放到 180 秒，无媒体错误 |
| 素材许可和私有数据 | 字体保留各自 SIL OFL；音乐和动画原创；截图为本次人工输入实录。源码包采用名单生成，不含凭证、真实 APK、反编译全文、数据库、真实政策全文、帧或依赖。最终 ZIP 的 48 个文件哈希通过，另有索引 `files.json`；1 个实际可用凭证的字节扫描与文本私有路径扫描均为 0 匹配 |
| 源码、说明、预览、影片和验收记录 | HTML 与 MP4 同一确定性时间函数；本目录提供制作方法、最终分镜和验证记录，ZIP 带独立播放资源。已核对正式材料页面，下方列明其与本次选择的差异 |

## 文案来源

用户明确将文案交给 Gemini 完全重写并给予更高措辞权限。实际采用完整稿第 4 版与 Gemini 自作的第 5 版事实修订，见 [copy-provenance.json](../../showcase/privacytrace/copy-provenance.json)。20 镜标题、字幕、旁注及片头／片尾／统计说明与采用稿逐字匹配；主代理改写措辞为 0，仅作数据映射和按词换行。初稿中的责任、运行时、复现及候选检查混同等问题交回 Gemini 修订，未复用未完成或旧会话残留输出。原始政策引句、API、enum、数字及日期保留。

导入截图是文件已选择、提交前状态；字幕作为操作说明，后续作业证明上传实际发生。起始进度帧仍显示等待处理，约 3.7 秒来自后台事件，15 秒为包括结束画面的整段编辑时长。两条静态线索分别包括 MANIFEST 和 API，不误称两条 API 调用。

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

| 实际执行 | 结果／收据 |
| --- | --- |
| `pwsh -NoProfile -File scripts/check.ps1` | 权威入口通过；API 617 passed、20 skipped，前端 46 passed；Ruff、治理、契约、类型与构建通过。保留既有 Starlette 弃用 warning。20 项 Docker 集成跳过不是通过；本片另行实际取材 Docker 收据为 true |
| `node showcase/privacytrace/verify.cjs` | 实际断网导航、7 控制、20 关键帧、40 边界通过；[browser.json](evidence/browser.json) |
| `node showcase/privacytrace/render.cjs` | 5400 张实际 Chromium 画布帧，外网请求被阻断的回环导帧，FFmpeg 编码成功；[render-result.json](evidence/render-result.json) |
| `python showcase/privacytrace/verify-media.py` | 全片解码、黑帧／冻结／音频／关键帧对应通过；[media.json](evidence/media.json)。响度 −18.92 LUFS，true peak −4.13 dBTP，无中段静音 |
| `node showcase/privacytrace/verify.cjs --video --full` | 最终实际 HTML／MP4 各完整连续播放到 180 秒，9 个 MP4 seek，无脚本错误／外网请求；[browser-and-video.json](evidence/browser-and-video.json) |
| `node showcase/privacytrace/verify-server.cjs` | 11 个实际检查通过，包括 Range、HEAD、空文件、无效请求、服务目录和资产根／子项链接拒绝；[server.json](evidence/server.json) |
| `python showcase/privacytrace/package.py`、`node showcase/privacytrace/verify-package.cjs` | 最终交付哈希、48 文件哈希、解压后实际离线播放、凭证字节／私有路径核验通过；[package.json](evidence/package.json) |
| 新 Python Ruff、JS 语法、独立审查 | 通过。只读审查覆盖事实／字幕、镜头代表帧及工程打包；修复了服务／资产链接边界和纯哈希提前加载 Playwright 的问题。浏览器加载失败、播放或解码结论仍由实际收据支持 |

提交前重跑权威检查时，既有 DNS 超时测试出现 `0.0500000000001819 <= 0.05` 失败，单独运行亦复现。固定 monotonic 时钟为 4096.0 后先确认稳定失败，再将系统 DNS 和公共 DNS 的剩余预算共同限制在调用方指定值内；原断言未放宽，13 项政策抓取测试通过。这是附带的最小超时上界修复，未扩展抓取能力、改接口或安全条件。影片取材仍绑定修复前 main `6d781fde…`，原捕获收据未改。

仓库交付 SHA 的远端 CI 以关联 PR 检查记录为准。现有 CI 验证应用／治理／受控集成；没有声称远端 CI 运行了本片的全部解码与播放工具。本片相应验收是本机实际收据。

## 正式材料格式差异

2026-10-14 核对 [2026 官方电脑版作品提交流程](https://www.cmit.cn/html/liucheng/show-277-45689-1.html)：作品／答辩视频至少 1 个、最多 2 个，每个不超过 1G；视频与答辩 PPT 至少提交一种，PPT 不超过 200MB；参赛打包文件支持 ZIP／RAR／7Z，不超过 10GB。此页面没有规定视频时长、分辨率、帧率或容器。

本片约 17MB，源码 ZIP 约 27MB，低于对应大小上限；180 秒、1080p、30 fps、H.264 MP4 是用户选择，并非官方要求。源码 ZIP 是影片维护包，未充当完整赛事资料包。赛道／分类及另行说明可能改变适用要求，正式提交仍按 [Issue #43](https://github.com/MrEcho114/PrivacyTrace/issues/43) 的最后确认；本次没有代填、上传或提交，也没有修改 #19／#43。

## 已知边界

本片通过浏览器实际音频播放、整轨解码、响度和峰值测量核验配乐，没有声称人类听感或审美认可。项目整体公开分发许可、正式赛事资质与材料仍由团队决定；本任务仅交付独立影片候选。控制截图／哈希不推导实际采集、可达性或全文政策复核。

同时运行 HTML 和 MP4 的无头浏览器记录包含丢帧计数；最后一个定期样本在 167.58 秒为 15 个 dropped frames（计数也包含之前的 9 次 seek）。媒体最终到达 ended／180 秒；这证明完整播放，未声称本机浏览器渲染零丢帧。文件自身的 5400 帧由独立完整解码验证。
