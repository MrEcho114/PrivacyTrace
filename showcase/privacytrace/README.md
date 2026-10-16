# PrivacyTrace：从代码查到隐私政策

120 秒、1920×1080、30 fps。画面字幕与原创背景配乐，无旁白。对应 [Issue #45](https://github.com/MrEcho114/PrivacyTrace/issues/45)，制作方法见仓库 `docs/showcase/issue-45-production-plan.md`。

用户最新要求参考 Pioneer 加入有创造力的镜头，并将全片控制在两分钟。当前版本为 Codex 原创的 18 镜：安装包分层展开、三张真实界面的空间长廊、代码与政策双页对照、结尾收成报告。深黑画布与暖白字延续参考方向，真实操作保留原截图；政策引句、API、日期、结果及数字来自原记录。旧 Gemini4 的 180 秒与 20 镜安排已被本轮授权取代，归属见 `copy-provenance.json`。

## 播放

交付目录中的 `PrivacyTrace-1080p.mp4` 可以直接用本机播放器打开。`PrivacyTrace-Source.zip` 是可编辑源码：解压到新目录，直接打开 `index.html`，所有字体、图像与音乐均在包内；无需联网、Node、Python 或安装依赖。

HTML 提供播放／暂停、重播、时间轴跳转与全屏。未聚焦按钮或滑块时，空格播放／暂停，左右键跳 2 秒，R 回开头；也可用 Tab 访问按钮与原生滑块。初次打开默认暂停，声音随播放按钮开始。

少数浏览器限制本地文件音频或全屏时，可以在源码目录用 `node server.cjs`，然后打开终端显示的本机回环地址。服务不会向公网绑定。设置 `PORT` 可选择别的端口；端口已占用时启动失败，不终止其他服务。

从仓库预览时先执行：

```powershell
node showcase/privacytrace/prepare.cjs
node showcase/privacytrace/server.cjs
```

## 修改与重做

`storyboard.json` 是镜头、秒数、裁切、字幕与阅读摘录；`film.mjs` 编排画面，`cinema.js` 负责透视、景深、原创空间镜头和阅读停顿，纯时间函数 `window.__seek(seconds)` 驱动预览和导出。时间、进出镜头和阅读停顿由同一份分镜元数据驱动；读取段使用无滤镜的正面原图，运动段短暂变焦。修改 JSON 后执行 `node prepare.cjs` 更新本地 `data.js`，再重新打开 HTML。素材变化后必须重新验证和导帧；已有帧缓存的来源哈希不符时，导出器拒绝混用。

源码包内安装本地制作依赖后可重新导帧；播放本身不需要这些依赖：

```powershell
npm install --ignore-scripts --workspaces=false
npx playwright install chromium
node prepare.cjs
node verify.cjs
node verify-server.cjs
node render.cjs
python verify-media.py
node verify.cjs --video --full
python package.py
node verify-package.cjs
```

制作需要 Node 24、Playwright 1.64.0／Chromium、FFmpeg／FFprobe，以及 Python NumPy／Pillow。包内不分发这些运行时。导出在 PrivacyTrace 仓库内写入忽略的 `tmp/issue45-film/`；独立源码目录默认写入自身 `output/`。可用 `FILM_OUTPUT_DIR` 指定本机输出目录。

`soundtrack.py` 从原创器乐参数生成音乐，先输出本地 WAV 再转 AAC；现有 `assets/soundtrack.m4a` 已可离线播放。没有参考歌曲录音、语音或旁白素材。音轨、截图与影片来源分别记录在 `audio-provenance.json`、`capture-provenance.json` 和交付验证记录。

`capture.cjs`／`capture_app.py` 是重新录制产品素材的脚本，**需要完整 PrivacyTrace 仓库及影片所绑定的 main 版本**，不能仅在这个电影源码包运行。它们调用已有应用、既有环境凭证和受限 Docker；不会把 APK／代码发送到模型。不要将密钥写进命令或源码，也不要把本机 store 打包。

## 画面所代表的材料

主体是一份新构造位置 APK、两份人工政策与一个被拒的私网来源。生产网页上传、HTTP 操作、实际 DeepSeek 请求、原句校验、候选修改与受限 Docker 扫描在 2026-10-14 main `6d781fde97fe69169db916ab473224a24ed5ce93` 上实录。政策 HTTP 和 DNS 是本地取材夹具，影片持续标记“构造 APK／人工政策 · 操作回放”；空间镜头另标“镜头示意／流程示意／摘录示意”。画面中的“官网政策／SDK 政策”是构造输入的来源类型，不能据此视为真实网站或厂商政策。

影片播放不执行新扫描；实际步骤以截图重新编排，镜头停留不代表作业真实时长。主案例两条位置结果都是证据不足，政策仍为 PARTIAL／UNREVIEWED／NOT_CHECKED。自动保存候选只用于交互和引用检查的记录，不代替人工语义复核。

C02／C03／C05／C06 与 2/6、3/6、6/6 比较另行标为 2026-10-11 的历史受控摘要，保留弃判和失败；它们不是新网页任务的结果，也不是通用准确率。GKD 1.12.1 段只说明历史核验与未知边界，不包含真实 APK、完整真实政策或反编译全文。

素材与许可见 [ASSETS.md](ASSETS.md)。本次交付不包含合并、公开托管、Release、部署或正式赛事提交；120 秒／1080p 是本任务选择，不是已核实的官方赛事要求。
