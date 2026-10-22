# #165 DS 接入记录

状态：2026-10-22，分支 `codex/design-integration-165`，本轮工作单元 `a61aeb7..a0ab4db`（12 个提交）。
本文件只记录已实现、可在当前分支核对的事实；未执行的项目集中在文末 NOT_RUN，实际命令结果见 [verification.md](verification.md) 的“2026-10-22 DS 接入”一节。本文件描述 `a61aeb7..a0ab4db` 这个工作单元的实现；此后同分支的其他改动（如品牌资产接入）不在本文范围，本文不据新 tip 回填。
关联文档：[设计基座](README.md)、[已采纳 #167 文案合同](copy-contract-167.md)、[六项 UI/UX 布局合同](ux-layout-contract.md)。

## 1. 范围与吸收关系

本轮把 #166 的设计基座（语义 token、字号层级、单流程、双栏、证据入口、唯一主操作）与 #167 的文案合同接进真实业务入口：桌面工作台、示例四步、真实导入/候选/进度/报告、本机存档、设置、Tauri 移动流程。不改作业状态机、API/生成契约、字段名、结论枚举和政策核算规则。

git 拓扑（`git log --graph --oneline`、`git show --no-patch --format='%h %p %s'`）：

| 提交 | 角色 |
| --- | --- |
| `f3db2b0` | 分支起点，PR #166 head（设计基座） |
| `112c9e4` | 并入的 `origin/main` 提交（PR #168 合并提交） |
| `62a4c35` | 把 `112c9e4` 并入本分支 |
| `9ec644e` | 并入的 `origin/codex/frontend-round2` head（PR #160 分支 head） |
| `40f740c` | 把 `9ec644e` 并入本分支 |
| `a61aeb7` `fe8ac80` `2ec43d0` `1159f92` | 文案单一来源、语义 token 迁入共享主题 |
| `dbb6f2b` `8721603` `5de9443` `750e39f` `a633161` | 桌面壳层与示例页、移动入口、真实报告与在线流程、窄屏标题修正 |
| `24ee58b` | 验收前清理最后一个无引用 copy 键 `reportTitle`、把 `--pt-action-hover` 对齐基座、补齐窄屏 48px 触控面（`label.text-upload`、`.report-filter select`、`.candidate-item`） |
| `8d63e49` | 设置弹窗（Reka 传送到 `<body>`）在窄屏单独保持 48px 触控目标 |
| `a0ab4db` | 移动进度卡的成功态标题改读 `frontendCopy.stages.SUCCEEDED`，不再另写“报告已生成” |

吸收取舍（可复算）：

- `apps/web/src/mobile/flow.ts` 保留 main 侧实现。`git diff 62a4c35 40f740c -- apps/web/src/mobile/flow.ts` 输出为空；`git diff 9ec644e 40f740c -- apps/web/src/mobile/flow.ts` 为 50 增 59 删。#160 侧基于 `pollEpoch` 与 `SERVER_BUSY` 退避的轮询改写没有进入本分支，本分支沿用 main 的轮询与恢复实现。
- 本地 fetch 时 `origin/main` 为 `e17d2e3`（PR #160 的合并提交），`9ec644e` 已在其中；`f3db2b0` 不在 `origin/main` 上（`git merge-base --is-ancestor` 返回 1）。
- 本轮不做合并、部署、发布，也不关闭 #165/#167 工单；这些动作不在本文件范围内。

## 2. 文件映射

| 实现文件 | 本轮责任 |
| --- | --- |
| `apps/web/src/copy.ts` | 四步名、报告名、页面标题、对照节名、表头、九阶段名、10 条边界事实、`policyStateLine()`；唯一文案来源 |
| `apps/web/src/theme.css` | 产品侧 `--pt-*` 语义角色（白工作面、`#ECE5D6` 顶栏、唯一红 `#D63A2C`、四色条、字号层级、控件高度）；旧 Pioneer token 未改；`--pt-action-hover` 与基座同为 `#b92e22`（`24ee58b` 对齐） |
| `apps/web/src/style.css` | 工作台壳层与示例页皮肤：176px 侧栏、≤896px 同 DOM 横排、报告 1.15fr:1fr、≤560 卡片表、唯一红主操作、触控高度（`24ee58b` 把 `label.text-upload`、`.report-filter select`、`.candidate-item` 一并抬到 `--pt-touch`；`8d63e49` 为传送到 `<body>` 的设置弹窗单独补 `.ui-dialog.settings-dialog` 的 48px 下限） |
| `apps/web/src/workbench.css` | 真实报告嵌入后的报告工作区：`.report-columns` 1.15fr:1fr、选中文字＋边框、证据上下文、主操作区、≤560 卡片表 |
| `apps/web/src/hierarchy.css` | 嵌入视图的标题层级、报告来源工具条、报告元数据顺序、短屏（≤800px 高）压缩 |
| `apps/web/src/WorkflowApp.vue` | 桌面单一四步侧栏与单品牌栏；存档视图唯一 h1 与 `archiveNoRescan`；以 `embedded` 复用报告主体 |
| `apps/web/src/App.vue` | 报告主体：非嵌入时唯一 h1、结论/证据双栏、报告元数据在证据区之后、嵌入模式抑制自身 h1/品牌/重复边界句、渲染 `facts` |
| `apps/web/src/LiveWorkflow.vue` | 真实四步：进度与报告页 h1、`frontendCopy.stages` 阶段标签、来源状态行、`archiveNoRescan` |
| `apps/web/src/components/EvidencePanel.vue` | 证据面板：条目编号/名称/关联数/结论、`notDeclared`、`candidateUnconfirmed`、文档来源状态行 |
| `apps/web/src/components/MobileReportSummary.vue` | 移动报告首屏：身份、来源徽标、范围、静态边界句、三格计数 |
| `apps/web/src/components/MobileMaterialContext.vue` | 移动材料上下文折叠与“更换材料” |
| `apps/web/src/pages/ImportPage.vue` | 第一步 h1、来源状态行 |
| `apps/web/src/pages/CandidatePage.vue` | 第二步 h1、`noCandidates`、`candidateUnconfirmed`、来源状态行 |
| `apps/web/src/pages/ProgressPage.vue` | 第三步 h1、九阶段中的可点击子集、阶段名改读 `frontendCopy.stages` |
| `apps/web/src/pages/ExampleReport.vue` | 示例报告：单 h1、双栏、条目编号/名称/关联数/结论、唯一红主操作、元数据折叠、静态边界句 |
| `apps/web/src/pages/SettingsPanel.vue` | `modelTextOnly` |
| `apps/web/src/components/PolicyAssist.vue` | `assistUnreviewed` |
| `apps/web/src/mobile/MobileApp.vue` | 移动壳层：应用栏唯一 h1、四步横排、`frontendCopy.stages`、来源状态行、底部操作栏 |
| `apps/web/src/mobile/mobile.css` | 移动视觉：单列、48px 触控与 56px 主操作、固定操作栏、安全区留白 |
| `apps/web/src/workflow.ts` | 删除旧示例阶段名 `stageNames`（核对输入/静态线索/政策候选/规则对照/报告） |
| `apps/web/index.html` | `theme-color` 由 `#fdfcfa` 改为 `#ece5d6` |

## 3. 六项布局规则的落地位置

| 规则 | 落地位置（选择器 / 组件 / 断点） |
| --- | --- |
| 导航重复：桌面仅一套四步流程，侧栏约 176px | `WorkflowApp.vue` 的 `.flow-nav`（数据来自 `frontendCopy.steps`），主区不渲染第二份步骤轨；`style.css` `.workbench .workspace-layout { grid-template-columns: 176px minmax(0, 1fr) }`、`.flow-nav button[aria-current]`；`@media (max-width: 896px)` 把同一 DOM 改为 `grid-template-columns: repeat(4, minmax(0, 1fr))`，当前步标记由左边框改为下边框；移动端 `MobileApp.vue` 的 `.m-steps` 使用同一份 `steps` |
| 空间失衡：宽屏约 55:45（实现 1.15:1），≤896px 单列 | `workbench.css` `.report-columns { grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 18px }` 与 `@media (max-width: 896px)` 单列；`style.css` 示例报告 `.report-columns` 与 `[data-layout="stacked"]`，`ExampleReport.vue` 用 `matchMedia('(max-width: 896px)')` 切换；`hierarchy.css` `@media (min-width: 897px) and (max-height: 800px)` 只压缩间距，不缩小字号 |
| 关联不直观：左条目编号/名称/关联数/结论，右证据上下文一致 | `App.vue` 桌面表行 `.report-row-number`、`查看 {{ issue.evidence_ids.length }} 条证据`、选中行 `.report-current-label`；移动 `App.vue` 的 `.m-issue-card`；`EvidencePanel.vue` 的 `.evidence-context`（`对应条目 NN · 名称 · N 条关联证据` 与 `对照结论：…`）；`workbench.css` `.report-row-number`、`.report-current-label`；报告元数据（`.report-provenance`、`.provenance`、`#sdk-panel`、`.coverage-card`）排在 `.report-comparison` 之后 |
| 状态模糊：结论/条目复核/政策来源三种语义，选中用文字＋边框 | 对照结论用 `statusLabels`（`App.vue`）；条目复核用 `requires_review` 追加 `· 条目待复核`（`App.vue` 表行与移动卡片、`EvidencePanel.vue`）；政策来源用 `policyStateLine()`；选中态为 `.report-table tbody tr.report-row-current td:first-child { border-left-color }`、`.report-conclusions tr.is-selected .finding-type`、`.candidate-item.selected`，宽度在未选中行预留 |
| 入口分散：每条目一处证据入口，唯一红主操作在结论列表末尾并写明对象 | 每条目一个 `.evidence-button`（`aria-pressed` + `aria-controls="evidence-panel"`），`App.vue` 的 `.report-actions` 与 `.report-primary-action` 位于 `.report-findings` 末尾，文案为 `查看「X」证据与政策原文`，`disabled` 绑定当前选择；`ExampleReport.vue` 的 `.report-action` 同构；红色只在 `.ui-button.primary`（`workbench.css`、`style.css`），提交 `5de9443` 把当前步选中从红色改为结构色 `--pt-structure` |
| 按键位置不明确：主操作标明对象，移动全宽，触控 48/56px，返回恢复触发点 | `style.css` `@media (max-width: 896px), (pointer: coarse)` 统一 `min-height: var(--pt-touch)`（含 `label.text-upload`、`.report-filter select`、`.candidate-item`，`24ee58b` 补齐；设置弹窗因 Reka 传送到 `<body>`，由 `8d63e49` 用 `.ui-dialog.settings-dialog` 单独兜底）与主操作 `var(--pt-action-height)`；`workbench.css` `.report-primary-action { min-height: var(--pt-action-height) }`；`mobile.css` `.m-actionbar` 与 `.m-actionbar .ui-button.primary`（全宽、56px）；返回逻辑在 `App.vue` 的 `returnToTrigger()` / `closeEvidence()`（恢复触发按钮与滚动位置）、`EvidencePanel.vue` 的“返回刚才的操作”、`ExampleReport.vue` 的 `returnToTrigger()` |

## 4. #167 最终去重清单

事实定义只有一处：`apps/web/src/copy.ts` 的 `frontendCopy.facts`。下表列出每个事实的渲染位置。

| 事实（`facts` 键） | 唯一位置 | 渲染组件 / 文件 |
| --- | --- | --- |
| `permission` 权限只代表应用申请过 | 权限清单旁 | `App.vue`（“Android 权限”折叠内）、`ExampleReport.vue`（仅当条目是 `uses-permission` 片段） |
| `staticRuntime` 静态线索不证明运行时采集 | 报告首屏 | `App.vue`（非嵌入 h1 下、嵌入 `.report-scope`）、`ExampleReport.vue` 的 `.report-boundary`、`MobileReportSummary.vue` 的 `.reading-boundary`；这些位置分属独立报告、嵌入报告、示例报告、移动报告等互斥入口，同一屏只出现一次 |
| `coverage` 规则集覆盖有限 | 扫描范围段 | `App.vue` 的 `.coverage-card`（DEX 处理范围） |
| `sdkAttribution` SDK 归属只到公开包前缀 | SDK 归属段 | `App.vue` 的“第三方 SDK 归属”节标题旁 |
| `notDeclared` “未找到声明”的五前提 | 证据面板 | `EvidencePanel.vue`，仅 `issue.status === 'NOT_DECLARED'` 时渲染 |
| `candidateUnconfirmed` 候选尚未确认对应 | 候选条款段 | `EvidencePanel.vue`（“相关候选条款（未确认匹配）”）、`CandidatePage.vue`（候选列表下方）；分属报告阅读与候选编辑两个工作面 |
| `noCandidates` 没有候选只说明尚未整理 | 候选页 | `CandidatePage.vue`，候选列表为空时 |
| `archiveNoRescan` 查看本机存档不会重扫 | 存档入口说明 | `WorkflowApp.vue`（存档视图 h1 下）、`LiveWorkflow.vue`（真实报告页 h1 下）、`App.vue` 的 `.report-provenance`（`v-if="!embedded"`，嵌入时不重复） |
| `modelTextOnly` 模型只接收政策文本 | 模型设置 | `SettingsPanel.vue` 的“模型连接”节 |
| `assistUnreviewed` 网页补入的来源仍是未复核 | 来源补入操作处 | `PolicyAssist.vue` 的回填确认区 |

统一来源状态行：`policyStateLine()`（`copy.ts`）是唯一实现，调用点共 9 个文件：`App.vue`（网页来源行与政策快照）、`ImportPage.vue`、`CandidatePage.vue`、`ExampleReport.vue`、`LiveWorkflow.vue`、`EvidencePanel.vue`、`mobile/MobileApp.vue`、`design/ReportExample.vue`、`design/ComponentGallery.vue`。提取状态单独保留，不随状态行合并。

范围说明：`facts` 之外仍存在按操作场景写的短句提到复核或完整度，例如 `LiveWorkflow.vue` 的候选提取结果提示、`CandidatePage.vue` 的保存提示、`mobile/flow.ts` 的补入提示。它们是操作结果说明，不是同一事实的重复警告；#167 的边界句去重范围以 `facts` 表为准，这些句子本轮没有收敛进 `copy.ts`。

被删除的重复句与旧键（`git diff 40f740c..a0ab4db -- apps/web/src/copy.ts`）：

- 第一批 10 个（`a61aeb7`，即 #167 合同列出的旧键）：`homeTitle`、`homeDescription`、`scopeHelp`、`demoTitle`、`candidateDescription`、`modelHelp`、`sourceRecovered`、`unsavedText`、`sampleOnly`、`realInputHelp`。
- 第二批 10 个（`1159f92`，迁移后确认无引用）：`emptyCandidates`、`stageFailed`、`reportDescription`、`fixedReport`、`importTitle`、`candidateTitle`、`progressTitle`、`cancelled`、`viewEvidence`、`attachmentsUnknown`。本轮任务说明里列的是 6 个名字，实际提交删除 10 个；以提交为准。
- 第三批 1 个（`24ee58b`，Lead 在验收前清理）：`reportTitle`（旧“分析报告”，已由 `frontendCopy.reportTitle` 取代）。
- 净删除 21 个键：`copy` 对象由 65 键变为 44 键，无新增键（用 `git show 40f740c:apps/web/src/copy.ts` 与 `git show a0ab4db:apps/web/src/copy.ts` 逐行对比可复算）；在 `a0ab4db` 上 44 个键均有 `copy.<键>` 引用，无孤儿键。
- 删除的重复渲染：`ImportPage.vue`、`CandidatePage.vue`、`ExampleReport.vue` 里硬编码的“正文完整度未知 / 全文未复核 / 附件未检查”三行改为 `policyStateLine()` 一行；`ExampleReport.vue` 顶部的 `copy.fixedReport` 标记与“固定报告的政策依据保留原始示例版本”说明删除，示例态只留 `frontendCopy.demoBadge`（`WorkflowApp.vue`）；示例报告对照表由 5 列（数据类型/静态线索/政策来源/对照结果/依据）收敛为 2 列（数据类型/证据）；`ProgressPage.vue` 的阶段名改读 `frontendCopy.stages`，面板标题由示例应用名“纸舟地图”改为“示例材料”，阶段详情里重复的 `copy.reportHelp` 删除。

`copy.reportTitle`（旧“分析报告”）已由 Lead 在验收前的 `24ee58b` 删除，`a0ab4db` 上的 `copy` 对象 44 键全部被引用（逐键 `git grep "copy.<键>"` 检查，无孤儿键）。

## 5. 九阶段、四步与页面标题的单一定义

- 四步：`copy.ts` 的 `steps`（APK 与政策材料 / 核对政策声明 / 扫描与对照进度 / 对照报告）是标签的唯一来源；步骤键与顺序仍在 `workflow.ts` 的 `Step`/`steps`（`import`/`candidates`/`progress`/`report`），桌面侧栏与移动步骤条按同一顺序渲染两处内容，不各自维护标签。
- 九阶段：`copy.ts` 的 `stageNames`（等待处理 / 核对材料 / 隔离扫描 APK / 装载政策原文 / 规则对照 / 生成报告 / 报告已生成 / 分析失败 / 已取消）与 `stageOrder`。消费者为 `App.vue`（任务状态、来源下拉、状态播报）、`LiveWorkflow.vue`（`stageLabel`）、`ProgressPage.vue`（示例子集）、`MobileApp.vue`（`stageName` 与移动进度卡标题）。`workflow.ts` 的旧 `stageNames`（5 个示例阶段名）已删除。
- 页面标题：`frontendCopy.pageTitles` 由 `steps` 与 `reportTitle` 派生（`import`/`candidates`/`progress` 取 `steps[0..2]`，`report` 取 `reportTitle`，`reports` 为“本机存档报告”）。桌面每页 h1 分别由 `ImportPage.vue`、`CandidatePage.vue`、`ProgressPage.vue`、`ExampleReport.vue`、`LiveWorkflow.vue`、`WorkflowApp.vue`（存档视图）渲染，移动由 `MobileApp.vue` 应用栏渲染。
- 单 h1：`App.vue` 只在非嵌入、非移动时渲染 `h1#page-title`；嵌入时由外层壳层持有唯一 h1（`WorkflowApp.vue` 存档视图、`LiveWorkflow.vue` 报告页），移动由 `MobileApp.vue` 应用栏持有。品牌栏同理，嵌入模式不再渲染第二份。
- 表头：`frontendCopy.table`（数据类型 / 证据）同时用于 `<th>` 与单元格 `data-label`（`App.vue` 的 `.report-table`、`ExampleReport.vue` 的 `.comparison-table`），窄屏卡片布局依赖 `data-label` 选择器。

## 6. 与 #166 设计基座的差异

| 项 | #166 基座 | 本轮接入 |
| --- | --- | --- |
| token 位置 | `apps/web/src/design/foundation.css` 自带一份 `--pt-*` | 语义角色串行迁入共享 `apps/web/src/theme.css`（`fe8ac80`、`2ec43d0`），产品入口从共享主题取用；旧 Pioneer token 未改，两套 token 并存于不同入口 |
| 独立设计入口 | `design.html` + `foundation.css` | 保留。`apps/web/vite.config.ts` 仍以 `{ app: 'index.html', design: 'design.html' }` 构建；`design/main.ts` 只导入 `foundation.css`，产品 `main.ts` 导入 `theme.css` + `style.css` + `workbench.css` |
| 基座组件消费文案 | 基座页面读 `frontendCopy` 与 `policyStateLine` | 未改；`MissionShell.vue`、`ReportExample.vue`、`ComponentGallery.vue` 继续读同一 `copy.ts`，因此基座与产品共用四步、报告名、对照节名、状态行 |
| 顶栏颜色落点 | 基座内 `--pt-header` | 产品侧新增 `index.html` 的 `theme-color: #ece5d6`（`1159f92`），供 Android 系统栏跟随 |
| hover 语义色 | `foundation.css` 的 `--pt-action-hover: #b92e22` | 产品侧 `theme.css` 同为 `#b92e22`（`24ee58b` 由 `#b32e22` 对齐），两套 token 取值一致 |

## 7. NOT_RUN

以下项目本轮没有执行，也不由浏览器合成材料替代：

- Android APK 实机安装与运行、WebView 内真实交互、物理真机、真实 IME、安全区（刘海/手势条）、系统字体缩放、TalkBack 读屏。
- 真实 APK 静态扫描、真实政策抓取、真实模型服务请求与生成契约数据下的报告。
- 合并、部署、发布、关闭 #165/#167 或其他工单；不改远端保护设置。
- 独立设计入口（`design.html`、`apps/web/src/design/*`、`apps/web/vite.config.ts`）本轮未改动（`git diff --stat 40f740c..a0ab4db -- apps/web/src/design apps/web/design.html apps/web/vite.config.ts` 输出为空）；其既有检查在验收中重跑并通过（158 checks / 28 screenshots），见 [verification.md](verification.md)。

## 8. 分支边界

此后同分支的 #169 品牌接入（brand/、BrandMark、Android 图标管线）不在本文 #165 范围，见 brand/README.md 与 verification.md 的 #169 小节。本文所述的 `a61aeb7..a0ab4db` 实现之后，品牌改动如触及本文列出的文件（顶栏、图标、`index.html`），不以本文的描述为准，以品牌任务自己的记录为准。
