# 素材与制作来源

| 内容 | 来源／许可与使用方式 |
| --- | --- |
| 产品截图 `assets/stills/*.png` | 本任务通过实际 Chromium 捕获 PrivacyTrace main `6d781fde97fe69169db916ab473224a24ed5ce93`。构造 APK 和人工短政策来自项目已有二进制构造器及本任务 `capture_app.py`。原始 PNG 没有涂改；镜头运行时裁切／放大，旁注另行标为摘录。每张 PNG 的 SHA256、时间、视口与捕获区域在 `capture-provenance.json` |
| 片头、线条、镜头、字幕与统计摘要 | Gemini4 用户交接包提供深黑视觉、20 镜顺序与裁切；用户随后明确要求 Codex 自行使用写作 skill 重写文案。现行标题、字幕和批注由 Codex 编辑，保留原始引句、结果、数字与事实边界，来源见 `copy-provenance.json`。Pioneer Cinematic v8 为节奏／局部聚焦／时间轴参考，没有复制其角色、图像、文案、音乐或成片画面 |
| `assets/soundtrack.m4a` | 本任务 `soundtrack.py` 以固定参数、正弦振荡器、程序噪声与原创编排生成；无第三方录音、采样或语音。原 WAV 留在忽略的制作目录，不进源码包。音频参数和 SHA256 在 `audio-provenance.json` |
| Noto Sans SC、Noto Serif SC 字体 | 复用项目 `apps/web/public/fonts`，字体以 SIL Open Font License 1.1 提供。可搬迁源码包包含原 WOFF2 和各自 `assets/fonts/licenses/*-OFL.txt`，未修改字库 |
| 历史六场景摘要 | `benchmarks/controlled/` 冻结人工输入、`docs/stages/spec30/comparison.json` 及验证记录，日期 2026-10-11。只呈现状态、定义与数字；没有改真值或把新模型候选混进历史评测 |
| GKD 1.12.1 真实样本边界文字 | 仓库 `docs/stages/s1-pr29-real-sample-verification-20261009.md`：扫描核验日期 2026-10-09、政策快照 2026-10-03／v1.0。影片只用元数据、三条证据不足与未核验状态；没有原 APK、真实政策全文、图标、厂商截图或反编译全文 |
| Vue 与产品组件 | 只以本项目实际界面的截图出现。电影播放器使用浏览器原生 Canvas／HTML，没有打包 Vue、Vite 或应用依赖。项目整体源码许可仍由团队决定，本片不另行替项目授予公开分发或赛事提交许可 |
| Playwright、Chromium、FFmpeg、Python 库 | 本机制作用具。源码包含调用脚本，包内没有这些运行时或 `node_modules`。独立制作需自行准备，纯播放不需安装 |

素材哈希与电影源码指纹分别记录。最终 MP4、源码 ZIP 与验证附件哈希在 `delivery/manifest.json` 中绑定，不把某一张截图或旧 CI 当作新影片验收。

整个源包按明确名单生成：电影源码、本地素材、字体和许可、来源记录及验证附件。私有 APK、job store、凭证、真实政策全文、原始模型响应、依赖、帧缓存和本机日志均不进入包。
