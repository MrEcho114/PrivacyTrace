# 视频材料批次 20261023-v02

Issue #264 的一次性采集批次：两支片子（90 s 展示片、120 s 评审片）共用同一冻结提交、同一天、同一批界面素材。

| 项 | 值 |
| --- | --- |
| 批次号 | `20261023-v02` |
| 冻结基线 | `f81ca201b932a11e24a9f7175a9583150d44e9ed`（origin/main，2026-10-23） |
| 采集日期 | 2026-10-23（Asia/Shanghai） |
| 工作树 | `.agents/worktrees/video-v02` |
| 界面服务 | `npm run dev:start`，`PRIVACYTRACE_WEB_PORT=6173`，代理到 API `127.0.0.1:8123` |
| 录屏 | EAC `record-browser` job `6321fa62-3863-48dd-b684-63313dac31cb`（28.0 s / 1920×1080 / 30 fps） |

## 复跑步骤

1. 安装依赖并启动前端（提交 `f81ca20` 的内容）：

   ```powershell
   npm ci
   $env:PRIVACYTRACE_WEB_PORT = '6173'
   $env:PRIVACYTRACE_API_ORIGIN = 'http://127.0.0.1:8123'
   npm run dev:start
   ```

2. 用 `fixtures/acceptance-jobs/` 的临时副本启动 API（不读写本机真实数据）：

   ```powershell
   $store = New-Item -ItemType Directory -Force -Path tmp/materials-store
   Copy-Item fixtures/acceptance-jobs/*.json $store
   $env:PRIVACYTRACE_STORE_ROOT = (Resolve-Path $store).Path
   uv run --project apps/api uvicorn privacytrace.main:app --host 127.0.0.1 --port 8123
   ```

3. 采集三张界面图：

   ```powershell
   node showcase/materials-20261023-v02/capture-stills.cjs
   node showcase/materials-20261023-v02/capture-mobile-report.cjs
   ```

   输出默认写到 `tmp/materials-v02/capture/out/`，可用 `MATERIALS_OUT` 覆盖。

4. 录屏（EAC 工具调用，语义选择器脚本见 `showcase/privacytrace-90s/capture-provenance.json` 的 `actions`）：

   ```text
   eac_job_submit(projectId=dd433382-7f8f-4e65-a47a-b8c2c9aea687, type="record-browser",
                  params={url:"http://127.0.0.1:6173/", actions:[...]})
   ```

5. 抽帧与重渲：

   ```powershell
   Copy-Item <record-browser 输出 mp4> showcase/privacytrace-90s/assets/recording-browser.mp4
   bash showcase/privacytrace-90s/frames.sh
   ```

   两片各自的渲染参数写在 `showcase/privacytrace-90s/README.md` 与
   `showcase/privacytrace-review/delivery/README.md`；渲染后回填
   `materials.json` 的成片哈希，再跑材料级校验：

   ```powershell
   python showcase/validate_materials.py
   ```

## 采到的素材

| 文件 | 尺寸 | 来源 |
| --- | --- | --- |
| `ui-import.png` | 1920×1080 | 工作台加载固定演示材料后整屏截图 |
| `report-desktop.png` | 1440×2978 | 「已有报告」加载 `job:gkd-s1-first` 持久化回放，1440 宽全页截图 |
| `report-mobile.png` | 780×6258（390 CSS px） | 生产 `MobileApp.vue` + 假原生桥，390 宽移动视口、展开第一条证据后全页截图 |
| `recording-browser.mp4` | 1920×1080 / 28.0 s | 工作台固定演示流程实录（五段窗口见 `film-showcase.html` 的 `WINDOWS`） |

## 边界

- 桌面工作台是工程验收介质与离线回放载体，不是客户端（ADR-0004）。
- Android 前端截图是生产 MobileApp.vue 的 Chromium 移动视口模拟，不是 Android 真机；片内图注写明「Android 前端 · 视口模拟（非真机）」。
- 报告长图来自 `fixtures/acceptance-jobs/gkd-s1-first.json` 的持久化回放（原生成 2026-10-03），不是 2026-10-23 新扫描；截图日期是 2026-10-23。
- 示例流程为固定演示材料（SYNTHETIC），不证明实际采集。
