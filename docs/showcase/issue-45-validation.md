# Issue #45 展示影片验收

状态：用户返回的 Gemini4 完整导演稿已集成并通过本轮八项工程验收。核验日期 2026-10-15；用户审美认可另行决定。当前范围、唯一会话与最终 PR/head 见 [执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/45#issuecomment-6164068934)。上一版 d160a39 的影片与收据随原提交保留，不充当本轮验收。本次没有合并、发布、部署或正式提交。

## 交付与绑定

- [H.264 MP4](../../showcase/privacytrace/delivery/PrivacyTrace-1080p.mp4)：180 秒，1920×1080，30 fps，5400 帧，18,239,722 字节；字幕烧录，原创器乐配乐，无旁白。
- [可搬迁源码 ZIP](../../showcase/privacytrace/delivery/PrivacyTrace-Source.zip)：26,747,256 字节，解压后直接打开 `index.html` 离线播放。包含完整本地字体、音乐、原始截图、可编辑时间表、绘制代码与验证附件；播放无需安装制作工具。
- [manifest.json](../../showcase/privacytrace/delivery/manifest.json) 绑定 MP4 `9210570a59585ebdd25325bb720e95716d0de4af5480318f2c6b174c28ff95a5`、ZIP `7a3d64cb87a14b5e2d1d74cbf483f9316bbb004c7f80214aa125844b9ce60104`、视觉源码 `d30e2328a32d47b2f01882ba587a37ec00a3aca7865dd46bc7337b42b261dd48` 与原捕获版本。
- 播放与重做见 [README](../../showcase/privacytrace/README.md)，来源与许可见 [ASSETS](../../showcase/privacytrace/ASSETS.md)。制作缓存、APK、store、依赖与日志保留在忽略目录。

## 对照八项 Acceptance Criteria

| 验收项 | 本轮实际结果 |
| --- | --- |
| 本地离线 HTML 与控制 | 导航前 `offline=true`，从 `file://` 加载；7 项播放／暂停、重播、滑块、全屏和键盘检查通过；1440、768、390 宽度无水平溢出。HTML 实际连续播放至 180 秒；新目录解压后离线播放／暂停和 8 点 seek 通过 |
| 实际 MP4 规格、字幕与音乐 | H.264／yuv420p、1080p、30/1、5400 帧、180 秒；AAC 48kHz 双声道覆盖 180 秒。12 个实际解码帧与 HTML 画布比较，最大平均 RGB 误差 2.0965；字幕在像素中，配乐为原创程序器乐 |
| 连贯用户路径 | 20 镜连续覆盖 0–180 秒，按 Gemini4 的 7 个章节标签编排；主任务从导入持续走至报告、API、条款和政策快照，历史场景在 132 秒后另列 |
| 素材身份与回放标识 | 保留构造 APK、人工政策、实录回放及历史日期／编号。约 3.7 秒来自原后台事件，镜头停留为剪辑时长；没有现场执行或全文复核声明 |
| 数据与技术事实 | 新取材绑定 main `6d781fde…`，历史六场景单独绑定；保留 2/6、3/6、6/6、弃判 0/1/2 和失败 0/0/0。权限是能力，API 是潜在线索；主任务两条结果均为证据不足，未知状态未升级 |
| 关键帧、切换、解码及音频 | 20 中点、40 边界按打乱顺序 seek 后像素哈希一致。批注相接切换的 9 个实际 Canvas 绘制样本未同时绘出两个标题；正文受同一透明度控制。全片严格解码、0 黑帧、阅读静止段检查通过；结尾镜头没有意外冻结。HTML／MP4 各实际连续播放至 180 秒，12 点 MP4 seek 通过 |
| 来源、许可及私有数据 | 10 张原始 PNG 与返回包逐字节一致；Noto 字体保留 OFL，音乐无第三方采样或语音。搬迁包 48 个文件哈希通过，另有 `files.json`；实际可用凭证字节和文本私有路径扫描均为 0 匹配，包不含 APK、数据库或依赖 |
| 源码、说明、预览、成片与记录 | 同一确定性时间函数驱动 HTML 与导帧；提供可编辑源码 ZIP、MP4、制作方案、导演原稿、逐项记录及 6 份本轮收据。正式材料格式核对保留其核对日期和适用边界 |

## Gemini4 原稿与唯一授权修正

用户返回完整导演包 SHA256 `e35abb2ba02f686ee2ac73b551f905fb8900dc13a548290c95f25db5b252a475`。采用其深黑 #080909 画布、暖白字、三色细线、深色历史案例卡和 20 镜顺序；原文保存在 [导演交接稿](gemini4-director-review.md)。作者“完整观看”“verified”等自述没有被当成本轮独立验收。

用户明确只批准 quote 镜“左侧高亮定位”改为“左侧原文列出”，因为截图只高亮第一句。对整个采用 JSON 与原始 JSON 作深度比较，只有这项已批准差异；其余标题、字幕、旁注、章节、裁切、原句、API、日期和数字均保留。归属、原始文件哈希和采用文案哈希见 [copy-provenance.json](../../showcase/privacytrace/copy-provenance.json)。

技术适配包括 file:// 使用经典 defer 脚本、手机控制换行、节点长文字按既有字框缩放、旧批注退完再显示新批注。批注重叠守卫先在原实现 53.36 秒实际失败，再在修复后通过；不是仅检查源码字符串。原创音乐按 11／102／132／173 秒章节安排到既有乐节，未使用 Pioneer 音轨。

片头相机在第 7 秒进入阅读停留；编码冻结检测以噪声阈值将 6.9 秒起的缓动末尾判为近静止。补充未压缩帧检查：207→209、209→210 帧仍分别有 5231、9694 个像素变化，210→300 帧完全相同。冻结守卫据此允许末尾 0.1 秒加一帧的阈值容差，保留真实运动和停留检查，没有修改影片或取消全片冻结检测。

独立代表帧审阅未发现影片字幕或批注越界。code、caution、sources 的原应用截图底缘仍有非焦点下节内容被视口截断；API 卡、当前候选等焦点信息完整，后续 trace／edit 特写分别展示相应条款和编辑内容。本片没有声称每张截图包含全部页面内容，保留导演裁切与原 PNG。

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
| `pwsh -NoProfile -File scripts/check.ps1` | 617 API passed、20 skipped、46 前端 passed；Ruff、治理、契约、类型和构建通过。既有 Starlette warning 保留。跳过项未声称通过；取材受限 Docker 收据仍绑定原捕获 |
| `node showcase/privacytrace/verify.cjs` | 离线导航、7 控制、20 镜、40 边界和批注切换通过；[browser.json](evidence/browser.json) |
| `node showcase/privacytrace/render.cjs` | 实际 Chromium 导出 5400 帧，外网请求阻断；[render-result.json](evidence/render-result.json) |
| `python showcase/privacytrace/verify-media.py` | 全片严格解码、黑帧、冻结、音轨和 12 个编码帧对应通过；响度 -18.88 LUFS，true peak -4.13 dBTP，无中段静音；[media.json](evidence/media.json) |
| `node showcase/privacytrace/verify.cjs --video --full` | 最终 HTML／MP4 各实际连续播放至 180 秒，12 点 MP4 seek，无脚本／媒体错误或外网请求；[browser-and-video.json](evidence/browser-and-video.json) |
| `node showcase/privacytrace/verify-server.cjs` | 11 项服务／链接边界检查通过；[server.json](evidence/server.json) |
| `python showcase/privacytrace/package.py`、`node showcase/privacytrace/verify-package.cjs` | 最终交付哈希、48 文件哈希、实际搬迁离线播放和私有内容扫描通过；[package.json](evidence/package.json) |
| 新 Python Ruff、JS 语法、完整 diff 与独立审阅 | 通过；只读事实／工程与实际代表帧审查分开，最终代码与原稿唯一差异另有完整比较 |

上一候选 d160a39 中的 DNS 剩余预算最小修复及其稳定回归保持原提交；本轮没有新增后端、接口、规则或基准改动。CRLF 视觉输入以 Git `-text` 保留核验字节，`cr-at-eol` 仅使差异检查识别合法行尾，不忽略其它行尾空格。

远端工程 CI 以当前执行记录及 PR 的最终交付 SHA 为准；CI 没有代替本机影片解码、播放或人类审美验收。

## 正式材料格式差异

2026-10-14 核对 [2026 官方电脑版作品提交流程](https://www.cmit.cn/html/liucheng/show-277-45689-1.html)：作品／答辩视频至少 1 个、最多 2 个，每个不超过 1G；视频与答辩 PPT 至少提交一种，PPT 不超过 200MB；参赛打包文件支持 ZIP／RAR／7Z，不超过 10GB。此页面没有规定视频时长、分辨率、帧率或容器。

本片约 18.2MB，源码 ZIP 约 26.7MB，低于对应大小上限；180 秒、1080p、30 fps、H.264 MP4 是用户选择，并非官方要求。源码 ZIP 是影片维护包，未充当完整赛事资料包。赛道／分类及另行说明可能改变适用要求，正式提交仍按 [Issue #43](https://github.com/MrEcho114/PrivacyTrace/issues/43) 的最后确认；本次没有代填、上传或提交，也没有修改 #19／#43。

## 已知边界

实际音频播放、整轨解码、响度与峰值测量已通过；没有人类听感或审美签字。项目整体公开分发许可、正式资质和材料由团队决定，本任务只交付影片候选。

双页面同时播放的无头浏览器最后一个定期样本在 167.55 秒记录 19 个 dropped frames（计数包含之前 12 次 seek）。媒体最终到达 ended／180 秒，文件自身 5400 帧独立完整解码；没有声称浏览器零丢帧。
