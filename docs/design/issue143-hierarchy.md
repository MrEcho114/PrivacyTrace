# Issue #143 宽屏视觉层级

任务：[#143 [前端打磨 B] 复用成熟组件，收敛现有工作台与报告的视觉层级](https://github.com/MrEcho114/PrivacyTrace/issues/143)，父票 [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)。

- 第一轮（2026-10-21）：从 main `83f42ea2b8a59e34c84d348ef996973643bb5a94` 建分支 `codex/issue143-workbench-hierarchy`，head `40247ba`（PR #152），执行记录见 [Issue 评论](https://github.com/MrEcho114/PrivacyTrace/issues/143#issuecomment-6314108386)。
- 第二轮（2026-10-21）：分支 `codex/issue143-round2`，从 `codex/frontend-round2`（= `origin/main` `6e0122d1a84999de82c458f51c826248698c97dc`）切出，用 `git merge --no-ff origin/codex/issue143-workbench-hierarchy` 吸收第一轮，合并提交 `cb02e17`；宽屏守卫提交 `ddb4588`。本文件与证据按第二轮实测更新。

## 范围

只调整桌面/宽视口（1920×1080、1440×900、1280×720）的现有页面层级和布局组合：

- 导入材料、检查候选、分析进度、对照报告、已有报告、实时进度；
- 复用现有 `UiButton/UiField/StatusTag/UiIcon` 与 `WorkflowApp.vue/LiveWorkflow.vue/pages/*`、`App.vue` 报告查看器；
- 不新增业务流程、不改 API/生成契约/规则判定、不改上传/抓取/模型链路，不新增依赖或设计系统；
- 移动端重排/触控/大字归 C，状态语义/焦点归 D，动效归 E。本票没有改 `style.css`、`workbench.css`、`SettingsPanel.vue`、`main.ts`、`theme.css`（A 所有）或锁文件；页面级 `hierarchy.css` 由 `WorkflowApp.vue`/`App.vue` 引入。

## 实际差分

证据为第二轮在 1920×1080 / 1440×900 / 1280×720 各一张；场景、数据来源与采集条件见 [round2/README.md](issue143/evidence/round2/README.md)。

| 页面 | 调整 | 第二轮证据（1920/1440/1280） |
| --- | --- | --- |
| 已有报告 / 实时报告 | 报告身份（应用名、包名、版本、来源/投递徽标）和三项指标先于对照表；来源选择与“刷新任务与报告”合并为一条工具栏；成功任务的 job 信息收成一条紧凑元数据行，失败/取消仍保留完整告警面板；`report-provenance`、输入来源状态与 DEX 范围移到对照表、证据和 SDK 之后；`report-provenance` 改为安静边注 | [1920](issue143/evidence/round2/reports-1920.png) / [1440](issue143/evidence/round2/reports-1440.png) / [1280](issue143/evidence/round2/reports-1280.png) |
| 报告查看器内部 | 统一 `h2` 面板标题到 16/24；表格头、状态标签、分割线、输入框消费 Pioneer 角色；指标合并为一条三段摘要；证据按钮复用 `.ui-button` 契约，分页/政策跳转/任务操作统一为 32px 次级操作；长包名/网址/哈希/中文错误文本不挤出操作 | [证据面板 1920](issue143/evidence/round2/reports-evidence-1920.png) / [1440](issue143/evidence/round2/reports-evidence-1440.png) / [1280](issue143/evidence/round2/reports-evidence-1280.png) |
| 示例报告 | 来源摘要使用 auto-fit 网格（宽屏同一行、窄屏回落），来源单元格保持左侧阅读线；“查看线索详情”改用同一 `.ui-button` 次级操作，不再与真实报告的证据按钮分成两套 | [1920](issue143/evidence/round2/example-report-1920.png) / [1440](issue143/evidence/round2/example-report-1440.png) / [1280](issue143/evidence/round2/example-report-1280.png) |
| 检查候选 | 来源标题留在来源切换按钮；类型/版本/完整度/未复核/附件/适用范围合并为原文与候选之间的一条紧凑上下文；失败来源在上下文里直接标出“来源获取失败”；删除原文面板内重复的来源标题和类型标签 | [1920](issue143/evidence/round2/example-candidates-1920.png) / [1440](issue143/evidence/round2/example-candidates-1440.png) / [1280](issue143/evidence/round2/example-candidates-1280.png) |
| 分析进度 | 当前阶段卡片高度随内容、顶部对齐；增加真实离散“阶段 1 / 5”，不造百分比/ETA；实时进度把页标题和材料版本放在内容之前，状态/job id 收为摘要行，事件时间线增加完成/当前/失败视觉；完成后报告页仍保留“新建材料版本”入口 | 示例：[1920](issue143/evidence/round2/example-progress-1920.png) / [1440](issue143/evidence/round2/example-progress-1440.png) / [1280](issue143/evidence/round2/example-progress-1280.png)；实时：[1920](issue143/evidence/round2/live-progress-1920.png) / [1440](issue143/evidence/round2/live-progress-1440.png) / [1280](issue143/evidence/round2/live-progress-1280.png) |
| 实时报告 | 页标题在前、材料版本入口紧随，已保存报告正文在后；不重复大面板 | [1920](issue143/evidence/round2/live-report-1920.png) / [1440](issue143/evidence/round2/live-report-1440.png) / [1280](issue143/evidence/round2/live-report-1280.png) |
| 导入材料 | 来源失败原因和重试提示紧贴来源标题；来源脚注补齐“正文完整度未知 / 全文未复核 / 附件未检查”；保留 APK 选择/拖放、多来源、失败恢复和底部主操作 | [1920](issue143/evidence/round2/example-import-1920.png) / [1440](issue143/evidence/round2/example-import-1440.png) / [1280](issue143/evidence/round2/example-import-1280.png) |
| 离线回放入口 | 注入 `presentation=offline` 的只读包仍挂载现有报告查看器，不出现工作台外壳；保存报告选择、持久化回放徽标和报告内容仍可达 | [1920](issue143/evidence/round2/offline-reports-1920.png) / [1440](issue143/evidence/round2/offline-reports-1440.png) / [1280](issue143/evidence/round2/offline-reports-1280.png) |
| 设置 / 政策助手 | 未改组件和字段；设置弹窗由 A 票收敛，政策助手保持既有字段/错误/回填链路 | 不新增截图；`verify-policy-assist.cjs` / `verify-frontend-flow.cjs` 覆盖 |

## 复用与 token 映射

- 组件：`UiButton`（主/次/轻/危险/busy）、`UiField`（标签/帮助/错误）、`StatusTag`（neutral/info/wait/success/error）、`UiIcon`、报告查看器 `ExistingReports` 和候选/来源既有数据与事件均未复制。
- `MaterialContext`（`revision` / `draftId` / `busy` / `showRefresh`，事件 `new` / `refresh`）是各步材料版本条的唯一实现；第二轮给它加了可选默认插槽，调用方（C 的移动端上下文行）可补入应用名/版本/origin，而不是复制组件；桌面调用不带插槽内容，行为不变。
- 颜色：`--canvas`、`--surface`、`--surface-muted`、`--ink`、`--muted`、`--navy`、`--border`、`--control`、`--mint`、`--success`、`--slate`、`--notice`、`--rose`、`--error`、`--radius`、`--radius-panel`。第二轮核对 `theme.css`：本票所需变量均已存在，未新增或修改 token。
- 版式：Pioneer 28/40 页标题、16/24 面板标题、14px 正文、12px 元数据；代码/哈希继续等宽。未引入新尺寸体系。
- 桌面操作保持 36px 按钮 / 40px 字段；32px 为表格/证据阅读区内的次级操作尺寸。移动端仍由既有 `max-width: 560px` 规则回落到 44px 触控目标（新规则用 `min-width: 561px` 限定）。

## 第二轮：底座迁移与收尾

- 合并方式：`git merge --no-ff origin/codex/issue143-workbench-hierarchy`（`40247ba`）到 `codex/frontend-round2`（`6e0122d`）。**无冲突**：第一轮改动与 `83f42ea..6e0122d` 之间的提交（其中 `76b9f4d` 统一 Pioneer 主题并复用 Reka dialog）没有重叠的改动区间，Git 自动生成合并提交。
- 自动合并不等于语义正确，因此合并后重跑了全部检查：第一轮的 9 组断言在新树上全部通过，本轮再加 1 组桌面 36px 断言，共 10 组。
- 保留：`hierarchy.css`、`MaterialContext.vue`、`scripts/verify-issue143-hierarchy.cjs`、`package.json` 的 `acceptance:hierarchy`、Browser Acceptance 的宽屏回归步骤与证据归档、第一轮的 16 张 before/after 图、本文件。
- 第二轮代码增量只有 2 个文件：
  - `apps/web/src/components/MaterialContext.vue`：新增可选默认插槽（props/事件不变），供 C 的移动端上下文行复用；桌面调用不带插槽内容。
  - `scripts/verify-issue143-hierarchy.cjs`：每个宽视口断言首个 `.ui-button` 的计算 `min-height` 仍为 `36px`（防止移动 44/48px 触控规则泄漏到桌面）；报告证据态截图改为聚焦 `#evidence-panel`，让截图真的显示所截状态；`verification.json` 记录 `captured_at`。
- 主题差异：`#150` 的 Pioneer 主题统一（`76b9f4d`）在本票之前已并入 main，所以第一轮 before/after 截图（基线 `83f42ea`）不再代表当前主题。第二轮在合并后的树上重采 1920/1440/1280 证据，`docs/design/issue143/evidence/round2/` 才是当前视觉状态的证据，第一轮图保留为层级意图的历史对照。
- 第二轮未触碰：`theme.css`（A）、`workbench.css`、`style.css`、`main.ts`、`SettingsPanel.vue`、`index.html`、锁文件；无新依赖、无新 API/契约、无新业务行为、无新视觉方向。

## 验证

### 第二轮（当前树 `codex/issue143-round2`）

- `node scripts/verify-issue143-hierarchy.cjs`（= `npm run acceptance:hierarchy`）：PASS，10 组断言；1920/1440/1280 × 9 个场景共 27 张截图；回执见 [`evidence/round2/verification.json`](issue143/evidence/round2/verification.json)（`commit` `ddb4588`、`dirty: false`、`captured_at` `2026-10-21T13:07:46Z`、`errors: []`）。覆盖长 APK 名/长包名/长网址/哈希、候选来源上下文、进度阶段数、示例报告来源摘要、真实报告身份顺序与 token、证据下钻、实时进度模板、实时报告材料入口、离线只读入口、三视口 36px 操作契约。
- `npm run acceptance:frontend`（`verify-frontend-flow.cjs` + `verify-policy-assist.cjs`）：PASS。示例四步、真实报告模拟、五种尺寸、键盘/焦点/设置，以及政策助手 10 项检查均通过；`pioneer-design.json` 的桌面 36px / 移动 44px 契约同时被既有守卫复核。本机主工作树的管理预览占用了脚本默认的 5184 端口，因此本轮按脚本支持的显式入口，用本工作树自己的 5192 开发服务器运行（`PRIVACYTRACE_FRONTEND_URL=http://127.0.0.1:5192`，服务的是待验证的这一棵树）。
- `npm run typecheck`（`vue-tsc --noEmit`）：PASS。
- `npm run build`：PASS，`dist/assets/index-*.css` 37.05 kB（gzip 7.59 kB）、`index-*.js` 241.47 kB（gzip 86.68 kB）；`npm run test --workspace @privacytrace/web` 111 项通过。第二轮未新增依赖或运行时库。
- `bash scripts/check.sh`（Git for Windows Bash）：`CHECK_EXIT=0`，脚本最后打印 `PrivacyTrace checks passed.`；覆盖 `uv sync` + themasterplan verify、API 与 e2e pytest、ruff、`npm run test --workspace @privacytrace/web`（111 项通过）、`npm run build`。若把 bash 的 stderr 直接并入 PowerShell 管道，本机 PowerShell 会把进度行记成 `NativeCommandError` 并让包装进程以 1 退出（第一轮已记录的环境行为），因此本轮把 stderr 单独落盘后记录真实退出码。

### 第一轮（历史记录，基线 `83f42ea`）

- `node scripts/verify-issue143-hierarchy.cjs`：PASS，9 组断言（当时口径）；截图与 `verification.json` 在 `tmp/issue143-hierarchy/`。
- `npm run acceptance:frontend`：PASS。
- 权威入口：`bash scripts/check.sh` 通过（`CHECK_EXIT=0`；API/Web 测试、类型检查、生产构建全通过，构建 `index-*.js` 约 206 kB）。本机 `pwsh` 不在 PATH；`powershell -NoProfile -File scripts/check.ps1` 在同一次运行里同样打印 `PrivacyTrace checks passed.`，但 PowerShell 5.1 会把 bash 的 stderr 进度行当成 `NativeCommandError` 而让包装脚本以 1 退出（既有环境行为，未改共享脚本）。因此以同一入口的 Git Bash 运行结果为权威记录。
- 独立视觉审阅代理对照 before/after 截图检查阅读顺序、密度、重复信息、遮挡和操作辨识度；据此修正了指标上移、来源/存档元数据后移、实时材料身份下移到页标题后、阶段卡片不再拉满等高、候选中重复标题移除、长徽标不拆行、示例报告证据按钮复用同一 `.ui-button` 契约。
- 真实 Docker 扫描、真实模型、真机/模拟器本轮都没有执行；live 场景使用 mock draft/running job，`reports` 使用确定性 mock 报告。这些截图证明浏览器布局行为，不证明真实 APK 或政策核验。

## 剩余边界与 NOT_RUN

- 归属：移动端 48px 触控/安全区/底部操作栏归 C；焦点环、状态语义归 D；动效归 E。本票只加桌面 36px 守卫，不接管这三类；`hierarchy.css` 里桌面规则均限定在 `min-width: 561px`，窄屏仍走既有 44px 触控与卡片布局。
- `workbench.css` 的 `.report-page-title` 规则在本票把 reports 视图统一到 `.page-heading` 后已无模板使用；该文件不属本票范围，未清理，留给后续整合决定。
- 报告查看器的程序化焦点（进入步骤后聚焦 `#page-title`）仍会出现焦点环，语义归 D；本票没有删除焦点行为。
- 真实 FAILED/CANCELLED 报告的长错误文本和删除确认展开态没有单独截图；既有 `verify-frontend-flow.cjs` 覆盖短失败态，本票不新增业务状态。`reports` / `live-*` / `offline` 截图的数据来自脚本内 mock fixture。
- 本轮 `NOT_RUN`：真实 APK 静态扫描、Docker worker、真实模型请求、Android 真机/模拟器、真实系统读屏、Tauri APK 构建；桌面截图是 headless Chromium 的浏览器行为，不是 Android 实机结果。
- Figma 本次没有重新实时读取；使用父票固定节点（824:1279 / 824:1276）和仓库已记录的 [Pioneer 来源](issue-44-provenance.md)。

## 历史证据（第一轮，基线 `83f42ea`）

第一轮的 `evidence/before-*` 与 `evidence/after-*`（16 张）保留为层级意图的历史对照；其中的 after 图早于 `#150` 主题统一，不代表当前主题，当前视觉状态请看 `evidence/round2/`。
