# Issue #143 宽屏视觉层级

任务：[#143 [前端打磨 B] 复用成熟组件，收敛现有工作台与报告的视觉层级](https://github.com/MrEcho114/PrivacyTrace/issues/143)，父票 [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)。
2026-10-21 由本会话从 main `83f42ea2b8a59e34c84d348ef996973643bb5a94` 建分支 `codex/issue143-workbench-hierarchy` 执行。执行记录见 [Issue 评论](https://github.com/MrEcho114/PrivacyTrace/issues/143#issuecomment-6314108386)。

## 范围

只调整桌面/宽视口（1920×1080、1440×900、1280×720）的现有页面层级和布局组合：

- 导入材料、检查候选、分析进度、对照报告、已有报告、实时进度；
- 复用现有 `UiButton/UiField/StatusTag/UiIcon` 与 `WorkflowApp.vue/LiveWorkflow.vue/pages/*`、`App.vue` 报告查看器；
- 不新增业务流程、不改 API/生成契约/规则判定、不改上传/抓取/模型链路，不新增依赖或设计系统；
- 移动端重排/触控/大字归 C，状态语义/焦点归 D，动效归 E。本票没有改 `style.css`、`workbench.css`、`SettingsPanel.vue`、`main.ts` 或锁文件（A 票正在改这些共享文件），只新增页面级 `hierarchy.css` 并由 `WorkflowApp.vue`/`App.vue` 引入。

## 实际差分

| 页面 | 调整 | 证据 |
| --- | --- | --- |
| 已有报告 / 实时报告 | 报告身份（应用名、包名、版本、来源/投递徽标）和三项指标先于对照表；来源选择与“刷新任务与报告”合并为一条工具栏；成功任务的 job 信息收成一条紧凑元数据行，失败/取消仍保留完整告警面板；`report-provenance`、输入来源状态与 DEX 范围移到对照表、证据和 SDK 之后；`report-provenance` 改为安静边注 | [before](issue143/evidence/before-reports-1920-viewport.png) / [after](issue143/evidence/after-reports-1920-viewport.png)，[1280 before](issue143/evidence/before-reports-1280-viewport.png) / [after](issue143/evidence/after-reports-1280-viewport.png) |
| 报告查看器内部 | 统一 `h2` 面板标题到 16/24；表格头、状态标签、分割线、输入框消费 Pioneer 角色；指标合并为一条三段摘要；证据按钮复用 `.ui-button` 契约，分页/政策跳转/任务操作统一为 32px 次级操作；长包名/网址/哈希/中文错误文本不挤出操作 | [after 长文本](issue143/evidence/after-reports-longtext-1920.png) |
| 示例报告 | 来源摘要使用 auto-fit 网格（宽屏同一行、窄屏回落），来源单元格保持左侧阅读线；“查看线索详情”改用同一 `.ui-button` 次级操作，不再与真实报告的证据按钮分成两套 | [before](issue143/evidence/before-report-1440-viewport.png) / [after](issue143/evidence/after-report-1440-viewport.png) |
| 检查候选 | 来源标题留在来源切换按钮；类型/版本/完整度/未复核/附件/适用范围合并为原文与候选之间的一条紧凑上下文；失败来源在上下文里直接标出“来源获取失败”；删除原文面板内重复的来源标题和类型标签 | [before](issue143/evidence/before-candidates-1440-viewport.png) / [after](issue143/evidence/after-candidates-1440-viewport.png) |
| 分析进度 | 当前阶段卡片高度随内容、顶部对齐；增加真实离散“阶段 1 / 5”，不造百分比/ETA；实时进度把页标题和材料版本放在内容之前，状态/job id 收为摘要行，事件时间线增加完成/当前/失败视觉；完成后报告页仍保留“新建材料版本”入口 | [before](issue143/evidence/before-progress-1440-viewport.png) / [after](issue143/evidence/after-progress-1440-viewport.png)，[实时进度](issue143/evidence/after-live-progress-1440.png)，[实时报告](issue143/evidence/after-live-report-1440.png) |
| 导入材料 | 来源失败原因和重试提示紧贴来源标题；来源脚注补齐“正文完整度未知 / 全文未复核 / 附件未检查”；保留 APK 选择/拖放、多来源、失败恢复和底部主操作 | [before](issue143/evidence/before-import-1440-viewport.png) / [after](issue143/evidence/after-import-1440-viewport.png) |
| 离线回放入口 | 注入 `presentation=offline` 的只读包仍挂载现有报告查看器，不出现工作台外壳；保存报告选择、持久化回放徽标和报告内容仍可达 | [after](issue143/evidence/after-offline-reports-1440.png) |
| 设置 / 政策助手 | 未改组件和字段；设置弹窗由 A 票收敛，政策助手保持既有字段/错误/回填链路 | 不新增截图；验收脚本覆盖 |

## 复用与 token 映射

- 组件：`UiButton`（主/次/轻/危险/busy）、`UiField`（标签/帮助/错误）、`StatusTag`（neutral/info/wait/success/error）、`UiIcon`、报告查看器 `ExistingReports` 和候选/来源既有数据与事件均未复制。
- 颜色：`--canvas`、`--surface`、`--surface-muted`、`--ink`、`--muted`、`--navy`、`--border`、`--control`、`--mint`、`--success`、`--slate`、`--notice`、`--rose`、`--error`。
- 版式：Pioneer 28/40 页标题、16/24 面板标题、14px 正文、12px 元数据；代码/哈希继续等宽。未引入新尺寸体系。
- 桌面操作保持 36px 按钮 / 40px 字段；32px 为表格/证据阅读区内的次级操作尺寸。移动端仍由既有 `max-width: 560px` 规则回落到 44px 触控目标（新规则用 `min-width: 561px` 限定）。

## 验证

- `node scripts/verify-issue143-hierarchy.cjs`（`npm run acceptance:hierarchy`）：PASS，9 组断言。覆盖长 APK 名/长包名/长网址/哈希、候选来源上下文、进度阶段数、示例报告来源摘要、真实报告身份顺序与 token、证据下钻、实时进度模板、实时报告页材料入口、离线只读入口；截图与 `verification.json` 在 `tmp/issue143-hierarchy/`。
- `npm run acceptance:frontend`（`verify-frontend-flow.cjs` + `verify-policy-assist.cjs`）：PASS。示例四步、真实报告模拟、1440/1920/1280/768/390、键盘/焦点/设置，以及政策助手 10 项检查均通过。
- 权威入口：Git for Windows Bash `bash scripts/check.sh` 通过（`CHECK_EXIT=0`；API/Web 测试、类型检查、生产构建全通过，构建 `index-*.js` 约 206 kB）。本机 `pwsh` 不在 PATH；`powershell -NoProfile -File scripts/check.ps1` 在同一次运行里同样打印 `PrivacyTrace checks passed.`，但 PowerShell 5.1 会把 bash 的 stderr 进度行当成 `NativeCommandError` 而让包装脚本以 1 退出（既有环境行为，未改共享脚本）。因此以同一入口的 Git Bash 运行结果为权威记录。
- 独立视觉审阅代理对照 before/after 截图检查阅读顺序、密度、重复信息、遮挡和操作辨识度；已据此修正：指标上移、来源/存档元数据后移、实时材料身份下移到页标题后、阶段卡片不再拉满等高、候选中重复标题移除、长徽标不拆行、示例报告证据按钮复用同一 `.ui-button` 契约。
- 真实 Docker 扫描、真实模型、真机/模拟器本轮都没有执行；`live-progress` 使用 mock draft/running job，`reports` 使用确定性 mock 报告。这些截图证明浏览器布局行为，不证明真实 APK 或政策核验。

## 剩余边界

- A 票正在独立会话改 `workbench.css/style.css/main.ts/SettingsPanel.vue`；本票只消费现有 token 名称，A 合入后需要在集成分支复核一次视觉与 `verify-frontend-flow.cjs`（本票未改该脚本）。
- C 票负责 320/390/768 的移动重排、触控、大字；D 票负责焦点/状态语义的最终修复；E 票负责动效。本票没有把这三类工作写成本票完成。
- 报告查看器的程序化焦点（进入步骤后聚焦 `#page-title`）仍会出现焦点环，语义归 D；本票没有删除焦点行为。
- 真实 FAILED/CANCELLED 报告的长错误文本和删除确认展开态没有单独截图；既有 `verify-frontend-flow.cjs` 覆盖短失败态，本票不新增业务状态。`reports` 与 `offline` 截图的数据来自 mock fixture。
- Figma 本次没有重新实时读取；使用父票固定节点（824:1279 / 824:1276）和仓库已记录的 [Pioneer 来源](issue-44-provenance.md)。
