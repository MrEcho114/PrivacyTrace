# #295 / PT-MOB-202 移动端 UI/UX 后续修订 — 实施记录

- 日期：2026-10-23
- 基线：`9fcfcd7d00af4c6ce8bd06b773aa0ac4b11150ec`（origin/main，含 #292/#293）；交付期间 rebase 到 `4d55a46`，再由 Astra 的 `f301f39` 带回 `origin/main`（含 #274/#289 的合并提交 `8c7a844`）。
- 分支：`codex/pt-mob-202-uiux`；实现 `32bbb91`、小修 `d5ac81d`、审阅处置 `3584384`、Astra 细化 `29ea350`、交接 `9847e08`、接管整合 `57a8ae9`（cherry-pick 自 Astra 未推送的 `5fff115`，patch-id 一致）；工作树 `.agents/worktrees/pt-mob-202-uiux`。
- 依据：Issue #295 正文 + 2026-10-23 用户转述的 GPT6 ASTRA 两轮审阅意见（排版/可读性、按钮体系与操作层级），以及 Astra 在 §8 交接的两批细化（规范 §16.1 / §16.2）。
- 阻塞说明：**票面 Blocked by #274 已解除**——PR #289 于 `8c7a844` 合入 main 并已带回本分支；PR #302 仍为 draft，合并与解除 draft 由人类决定。

## 1. 复现与判断

ASTRA 的两轮截图位于本机忽略目录 `tmp/frontend-visual-acceptance-20261023/shots/`（不随仓库分发）。在基线代码上核对到的缺陷：

1. `320×568`、200% 根字号：`.m-actionbar` 主按钮被次按钮挤压，逐字竖排；固定栏几乎占满视口。
2. `390` 报告说明 `.shell .section-heading .subtle` 固定 `line-height: 20px`，0.8125rem 字号放大到 200% 时叠行。
3. 步骤导航固定 48px 高 + `white-space: nowrap; overflow: hidden`，200% 下标签被裁成单字，序号挤出圆圈。
4. 候选页来源切换是带描边的厚按钮，候选行逐行套卡片；材料摘要/来源/状态那一段长到首屏看不到候选。
5. 报告首屏看不到 `PARTIAL`、待复核等限制；`REAL_SCAN`/`PERSISTED_REPLAY` 内部代码在首屏标签里。
6. 证据卡先铺方法签名、规则版本、原始 JSON，政策原句被推后。
7. 失败态同时出现「分析未完成」多处文案，主操作仍是「刷新进度」；时间戳直接用服务原始字符串。

## 2. 实施内容（按票面七项）

| 项 | 实现 |
| --- | --- |
| 大字号可用性 | 底栏改 flex-wrap；主操作 `min-width: min(100%, 11em)`，放不下时独占一行；步骤导航高度随内容、标签可换行、序号圆圈与字号同比例；报告标题/说明改相对行高（1.35/1.5），覆盖 `hierarchy.css` 的固定 px；材料摘要与“更换材料”在 200% 下分成两行 |
| 按钮体系 | 每屏一个陶土实心主操作；底栏次操作改中性文字；来源切换改无描边标签栏（选中 2px 下划线、可横滚）；候选选择改列表行（容器一条描边、行间分隔线、选中状态层 + 2px 下划线）；删除材料统一危险色并在原位二次确认 |
| 动作位置与文案 | 主按钮收敛为「选择应用」「准备政策」「保存并分析」「重新分析」；“重新读取材料”移回材料卡，候选步的“修改材料”由材料条上的“更换材料”承担；失败态突出“重新分析”，刷新降为次要 |
| 候选页减负 | 材料摘要压缩；“候选声明 N”计数只在标签页出现一次；来源短名 + 当前来源完整标题紧随其后；候选列表去嵌套 |
| 报告层级 | 报告摘要新增“结果状态”块：扫描范围 `PARTIAL`/完整 + 待复核条目数；内部来源/投递代码移入“来源标识”折叠；移动端移除与行内入口重复的底部主操作 |
| 证据与进度 | 移动证据卡改为“静态线索 → 政策原句 → 未知项 → 技术详情”；静态上下文（接收方/目的/时间范围）保留 `UNKNOWN` 原文；哈希默认缩略、可展开复制；任务 ID 收入“任务详情”；时间戳转本地可读格式并保留原始 ISO 值；失败原因只显示服务返回的内容，缺省写“服务尚未返回失败原因” |
| 辅助流程 | `.policy-assist` textarea 空态 3.5rem 起、按内容增高（`field-sizing: content`），检查按钮紧邻输入框 |

规范同步：[`docs/design/frontend-design-spec-mobile.md`](../../design/frontend-design-spec-mobile.md) 新增 §16，记录本次对大字号几何、底栏换行、按钮层级、行高与证据顺序的明确例外；默认字号下的契约（56/48/48/64、12/16/24 圆角）不变。

## 3. 验证

| 命令 | 结果 |
| --- | --- |
| `npm run typecheck --workspace @privacytrace/web` | 通过 |
| `npm run build` | 通过 |
| `npm run test --workspace @privacytrace/web` | 通过 |
| `npm run acceptance:mobile` | 22 组通过；新增 200% 断言：`import/200%/320` 底栏 75px、主按钮 288×58、步骤标签 1 行；`candidates/200%/320` 同上；`progress/200%/320` 底栏 141/568px；`report/200%/320` 说明行高 42px/28px |
| `npm run acceptance:reading` | 8 项通过；内部代码断言改为“中文语义首屏可见 + 来源标识展开后可见 `REAL_SCAN`/`REPLAY`”。在 `32bbb91` / `1b96c80` 上复跑：`dirty=false`，截图逐字节一致 |
| `npm run acceptance:motion` | 20 项通过 |
| `npm run acceptance:frontend` | 通过（含冻结桌面回归、copy contract 42 项） |
| `npm run acceptance:hierarchy` | 11 项通过 |
| `PRIVACYTRACE_ACCEPTANCE_API_PORT=8199 npm run acceptance:browser` | 通过（桌面报告流程、徽标与时间戳；默认 8123 被本机其他服务占用，脚本按设计拒绝复用） |

失败终态另用仓库自带的 round-2 deterministic bridge（`failJob: true`）在真实 Chromium 里截取：底栏为「刷新状态」+「重新分析」，`role="alert"` 显示桥返回的真实失败原因，任务 ID 收在“任务详情”内；截图见本目录 `progress-failed-*.png`。

未通过或有保留：

- `node scripts/verify-frontend-round2.cjs`：该脚本不在 `package.json`/CI 入口内，最后一段“inline evidence 返回后恢复滚动位置”断言在本分支失败（`before 580, after 0`）。同一合同在 `acceptance:mobile` 的“inline evidence: opening twice … restores focus and the exact scroll position”断言中通过。原因未定：面板变短后 `scrollIntoView` 真正产生了滚动，而该脚本在 150ms 内点击“返回”，落点被后续滚动覆盖；已把等待改为 700ms 仍未复现基线结果，标注为**未解决的手工脚本差异**，不作为通过项。
- 仓库根 `npm run acceptance:design` 在 CI workflow 中被引用，但 `package.json` 没有该脚本（基线即如此，未在本票处理）。

## 4. 截图

“改后”截图存放在本目录，均在接管整合后的 HEAD 重新生成（`acceptance:mobile` / `acceptance:reading` 与仓库自带的 deterministic bridge）：

| 文件 | 场景 |
| --- | --- |
| `import-320-200-after.png` | 导入已选材料，320px，200% 根字号（主操作独占一行） |
| `import-320-after.png` | 导入已选材料，320px，默认字号 |
| `candidates-320-200-after.png` | 候选页，320px，200%（材料摘要换行、来源标签栏、候选列表行） |
| `candidates-390-after.png` | 候选页长来源标题，390px |
| `candidates-390-reading-after.png` | 候选页，390px（reading 套件视角） |
| `progress-320-200-after.png` | 进度页，320px，200%（底栏不再挤占正文） |
| `progress-failed-390-after.png` | 失败终态，390px：真实失败原因 + 「重新分析」主操作、「刷新状态」次操作、任务详情折叠 |
| `progress-failed-320-200-after.png` | 失败终态，320px，200% |
| `report-320-200-after.png` | 报告，320px，200%（说明不叠行、状态与限制前置） |
| `report-390-200-after.png` | 报告，390px，200% |
| `import-empty-390.png` | 导入空态：空状态卡片承载唯一主 CTA，没有固定底栏 |
| `material-delete-confirm-390.png` | 删除材料二次确认：作用对象、后果、确认/取消 |
| `settings-390.png` | 服务与存储设置（全屏 sheet） |
| `evidence-inline-390.png` | 行内证据：静态线索 → 政策原句 → 未知项 → 技术详情 |

Astra 交接的对比证据（`design-takeover/`，来自其本机未推送提交；两份 JSON 的 `source_sha` 指向 `5fff115`，与本分支 `57a8ae9` patch-id 相同）：

| 文件 | 场景 |
| --- | --- |
| `candidates-before.png` / `candidates-after.png` | 候选页减负前后（390px） |
| `candidates-large.png` | 候选页 320px / 200% |
| `import-after.png` | 导入页收敛后（390px） |
| `report-before.png` / `report-after.png` | 报告详情统一前后（390px） |
| `report-details.png` | 「报告来源与技术详情」展开（390px） |
| `reading.json` / `refinements.json` | 两套验收的检查项与截图清单 |

本轮细化行为证据（`refinements/`，`scripts/verify-issue295-refinements.cjs` 生成）：

| 文件 | 场景 |
| --- | --- |
| `save-rejected-390.png` | 保存被拒后保留编辑、不显示假成功 |
| `hash-copy-failed-390.png` | 剪贴板被拒时的可见、可重试状态 |
| `candidate-delete-confirm-390.png` / `-320-200.png` | 候选删除原位二次确认（含 200%） |

“改前”截图只在 ASTRA 审阅时提供的本机忽略目录里（`320-import-200.png`、`390-report-200.png`、`320-candidates.png`、`390-evidence-sheet.png`、`390-progress-failed.png` 等），未上传；`design-takeover/` 的 before/after 是 Astra 为第二批细化留的对照，不替换历史证据。

## 5. 未验证（NOT RUN）

- 真实 Android WebView / 真机：软键盘实际高度、safe-area、系统字号、TalkBack 朗读顺序。
- 模拟器与 844×390 真机横屏；`768×1024` 目前只有 Chromium 视口结果。
- 系统级字号（Android font scale）与浏览器 200% 根字号不等价，本记录只声明后者。
- 用户审美认可：机器断言与代理审阅都不代替。

## 6. 共享边界

- 未改 `apps/api`、桌面专用布局与视觉；`hierarchy.css` 未改（移动覆盖写在 `mobile.css`）。
- `CandidatePage.vue`、`EvidencePanel.vue`、`App.vue` 的桌面分支保持原有结构与文案；用 `markdown`/`v-if="!mobile"` 隔离移动行为。
- 未改 #274 负责的保存确认逻辑；候选保存反馈沿用现状，合并顺序需回读 #289。

## 7. 独立视觉审阅与处置（2026-10-23）

独立只读审阅（子代理，按本规范 §16 与实际截图，不参与实现）给出的结论与处置：

**必须修 → 已修**

1. 报告的蓝色“存档报告查看 · PERSISTED REPLAY / 分析生成时点：2026-10-14T08:06:00Z”主阅读流泄漏内部投递代码与原始 ISO 时间。
   → 移动端只保留中文语义（“存档报告查看”/“离线回放”），时间改本地可读、原始值进 `datetime`/`title`，投递代码收进“来源标识”折叠；桌面保持冻结原文案（`verify-browser-acceptance` 的 `OFFLINE REPLAY · 离线回放` 断言不受影响）。
2. 进度进行中的“取消分析”与“刷新状态”同权同形、无中断语义，且排在“刷新”之前。
   → 取消改为危险文字色、排在“刷新状态”之后，状态卡补“取消只停止本次分析，材料会保留”。

**建议修 → 已修**

- 折叠入口补可见 ▾（材料条自带的“详情 >”不重复加）
- 哈希缩略值补“展开与复制”提示
- 候选列表容器改透明底，减少“卡片套卡片”观感
- 分段控件按 `8em` 换行，200% 下不再 3+1 断行
- “查看 N 条证据”整行不拆，chevron 跟随文本
- 报告条目头左对齐、状态标签靠右
- 材料条“更换材料”改中性文字

**未在本次处理（记录为下一轮）**

- 320/200 顶栏标题 2–3 行：规范未给顶栏增高例外，记录为首屏空间代价；若要收，需要补 §16 或调标题字号。
- 报告信息架构：蓝色 provenance 块、“报告版本、权限与全部政策快照”、“报告来源与版本”与页脚仍分散在结论之后；合并属于结构改动，不在本票几何/层级范围。
- 超长来源标题（fixture 120 字符）在 200% 下展开 6 行；真实数据概率低，建议下一轮加“2 行 + 展开”。
- “保存并分析”（底栏）与“保存候选”（表单）的语义边界：涉及 #274 保存接缝，待其合并后统一。
- 步骤可见短名 APK/核对/扫描/报告 与 §6.2 的 导入/候选/进度/报告 不一致：已在本票补充的 §16 记录“可见短名 + aria-label 全名”的约定。

审阅未能评估、现已补图的界面：导入空态、删除材料确认、设置页、行内证据（见 §4 截图表）。

## 8. 交接（2026-10-23，转 @OasisViridis 接手）

交接点：`codex/pt-mob-202-uiux` 的细化提交 `29ea350`，本记录随后以单独的交接提交追加（只改本文件）。PR #302 仍为 draft，`mergeable_state=clean`。

**已完成**

- #295 / PT-MOB-202 实现：大字号几何、底栏主操作收敛、候选与报告信息减负、证据排序、哈希可展开复制；本轮补充材料名/来源名两行预览与原位展开、超大字号顶栏随正文滚动、移动候选删除原位二次确认、哈希复制失败可见可重试（规范 §16.1）。
- 远端 CI 在 `29ea350` 全绿：Check、Browser Acceptance、Deployment Baseline、Deployment Acceptance、Spec30 Integration。
- 本机复验：`npm run typecheck`、`npm run build`、`npm run test --workspace @privacytrace/web`（152 passed）、`node scripts/verify-issue295-refinements.cjs`（5 项通过、8 张截图、`dirty=false`）。
- 前置 #274 / #289 已于 2026-10-23 合入 main（`8c7a844`），本分支已带回，票面阻塞可据此复核。

**交给接手会话的剩余项**

1. 真机验收（本票唯一硬缺口）：Android WebView 软键盘实际高度、safe-area、系统字号（font scale）、TalkBack 朗读顺序；模拟器与 844×390 横屏仍未跑。
2. 证据重拍：`docs/acceptance/issue295/` 的 14 张截图未随 §16.1 细化重拍；本轮 8 张细化截图只写在本机忽略目录 `tmp/issue295-refinements`，需要按 §4 的做法在干净工作树重跑并逐字节复跑。
3. `scripts/verify-frontend-round2.cjs` 末段“行内证据返回后恢复滚动位置”仍不通过（before 580 / after 0），原因未定，未作为通过项。
4. `scripts/check.sh` 在本机有 8 项 apps/api `ISOLATED_INSPECTION_UNAVAILABLE` 失败；干净 `origin/main` 上同样失败（隔离扫描不可用），远端 CI 已绿，接手时以 CI 为准。
5. 人类决定：是否解除 draft、是否合并；用户审美认可不由机器代替。

**接手约定**

- 按 `AGENTS.md` 与 `docs/agents/skills-workflow.md` §6 先回读 Issue #295 当前执行记录，确认唯一执行会话后再开工；本文件只是交接材料，不构成新的授权。
- 合并、发布、部署不在本交接授权内。

## 9. 设计接管收尾（2026-10-23）

本节接 §8 继续记录：从 Astra 交接、未推送提交的整合，到新 HEAD 上的复核。PR #302 仍为 draft，Issue #295 仍 OPEN；合并、发布、部署不在本轮授权内，§8 的接手约定继续有效。

### 9.1 接管点与提交谱系

| 提交 | 作用 |
| --- | --- |
| `29ea350` | Astra 第一批细化（规范 §16.1），§8 记录的交接点 |
| `9847e08` | 交接提交，只改本文件（§8） |
| `5fff115` | Astra 第二批细化（规范 §16.2），留在本机、未推送 |
| `57a8ae9` | 把 `5fff115` cherry-pick 到 `9847e08` 之上，保留原作者与日期；两者 `git patch-id` 均为 `0901811848439e597f0370e5efa9af2e813060c1` |
| `f301f39` | 分支合入 `origin/main`，带回 `8c7a844`（#274 / PR #289 的合并） |

- 阻塞解除：#274 的交付 PR #289 于 `8c7a844` 合入 main，`f301f39` 已把产物带回本分支；票面 Blocked by #274 据此不再成立。
- 比较 `5fff115` 与 `57a8ae9` 要看补丁而不是整棵树：两者基线不同，`57a8ae9` 额外包含 §8 交接文档与 main 带来的 `apps/api` 变更。

### 9.2 Astra 两批细化的内容

第一批（`29ea350`，规范 [§16.1](../../design/frontend-design-spec-mobile.md)）：

1. 新增 `MobileReadableName`：材料名与来源名默认最多两行，只有实际溢出时才出现原位「展开完整名称」，切换来源重置展开；正文完整度、复核与附件状态不折叠。
2. 顶栏保持原字号与完整标题；实测高度超过 96px（两个最小触控行）时改为随正文滚动，不缩小用户字号，恢复正常字号后回到吸顶行为。
3. 候选表单说明「保存候选」只保存当前编辑并把该条标为已检查、不启动分析；候选步底栏紧邻说明「保存全部候选，创建新分析」，逐条检查仍可选，不提升全文与附件复核状态。
4. 移动候选删除降为危险色次操作，原位二次确认并写明作用对象与政策原文/其他候选的保留范围；确认时焦点进入，取消后回到发起按钮且不发写请求；桌面分支不变。
5. `HashValue` 复制被拒时给出可见、可重试的状态说明，完整值保留供选择复制；只有剪贴板写入完成后才播报成功，重复点击去抖。
6. `mobile.css` 为固定底栏与键盘高度预留滚动空间，候选来源标题的两行裁切只在收起时生效。
7. 新增 `scripts/verify-issue295-refinements.cjs`：320/390 与 200% 根字号下的判据与截图（Chromium + mocked native bridge）。

第二批（`5fff115` → `57a8ae9`，规范 [§16.2](../../design/frontend-design-spec-mobile.md)）：

1. 候选页减负：移除与标签重复的「候选声明」标题和列表外层卡片，检查计数移到标题行；页面顺序为材料 → 来源及状态 → 原文/候选切换 → 计数与添加 → 候选列表 → 编辑表单，390×844 首条摘要与底栏之间至少留一个 48px 触控行。
2. 报告详情统一：首屏保留中文来源/查看方式、静态边界、扫描范围、待复核条目与政策复核/完整度/附件状态；来源标识、生成时间、服务/材料版本与政策快照统一收进「报告来源与技术详情」，移除独立 provenance 横幅与摘要卡里的第二个「来源标识」入口。
3. SDK 归属：折叠态先给本次命中情况与「静态存在不证明实际运行或采集」/「未命中不代表没有 SDK」，通用方法说明放进「如何理解 SDK 归属」，coverage 限制继续外显。
4. 材料删除在导入页与设置页都改为中性文字发起、危险色实心确认；确认出现后焦点进入确认按钮，取消后回到发起按钮。
5. 视觉取舍：沿用暖纸、象牙、正文/辅助色与主操作/危险色；衬线用于标题与政策阅读、无衬线用于控件；单列、一个底栏主操作、有限分隔线，不加第二套色彩、卡片阴影或新动效，不改流程可达规则、保存接缝与桌面布局。
6. 验证脚本随第二批更新：细化脚本增加「材料删除焦点进入/恢复、取消不写服务」判据并补整页截图；`verify-mobile-reading.cjs` 同步改为断言统一的「报告来源与技术详情」入口。

### 9.3 本轮收尾记录

- 整合未推送提交：`git cherry-pick -x 5fff115` → `57a8ae9`；`git patch-id` 前后均为 `0901811848439e597f0370e5efa9af2e813060c1`，确认补丁一致。
- 带回证据：`design-takeover/`（7 张 PNG + `reading.json` + `refinements.json`）已从 Astra 本机工作树未跟踪目录复制进本目录并随本节提交。
- 在新 HEAD（`57a8ae9`）重跑验收：9 条命令全部退出码 0 —— `typecheck`、`build`、web 单测 152、`acceptance:mobile` 22 组、`acceptance:reading` 8 项（`dirty=false`）、`acceptance:motion` 20 项、`acceptance:frontend`（Brand 103 / Reports 15 / Policy assist 10 / Copy contract 42）、`acceptance:hierarchy` 11 项、`acceptance:browser`（PORT=8199，TC-03/04/05）。
- 重拍主证据：§4 的 14 张已按新 HEAD 重新生成；随后在干净工作树复跑，重生成文件与提交逐字节一致。最终交付 SHA 取 PR #302 的 head（本文件随该 head 提交，避免在文件内自引用一个尚未存在的哈希）。
- 手工矩阵：`node scripts/verify-frontend-round2.cjs` 在 `c178b25` 全量通过（21 组、23 张截图，`source c178b25`）；接管前记录的「返回后恢复滚动位置」失败（before 580 / after 0）在当前报告结构上不再复现。
- 回归守卫加固（2026-10-23 只读复查发现）：`acceptance:mobile` 的行内证据滚动恢复原本从 0 起点开始，`|0-0|<=2` 恒真，等于从未恢复过非零位置；`verify-frontend-round2.cjs` 也有同样风险。现两处都在打开前断言 `before > 0`，`acceptance:mobile` 起点改为 420（该页 maxScroll≈2548）。加固后两套各自通过（22 组 / 21 组），旧版「假通过」不再可能；此前 before 580 / after 0 是旧布局下 harness 采样与产品点击时刻错位，不是产品缺陷，产品侧未改。
- 证据对齐：`design-takeover/` 两份 JSON 的 `source_sha` 保留 `5fff115`——那是 Astra 生成它们时的真实提交，且与本分支 `57a8ae9` patch-id 相同；不把证据里的历史 SHA 改写成新哈希。§4 的主证据绑定最终交付 SHA。

### 9.4 仍未完成

1. 真机验收（本票唯一硬缺口）：Android WebView 软键盘实际高度、safe-area、系统字号（font scale）、TalkBack 朗读顺序；模拟器与 844×390 横屏仍未跑。
2. 本机 `scripts/check.sh` 有 8 项 `apps/api` `ISOLATED_INSPECTION_UNAVAILABLE` 失败；干净 `origin/main` 上同样失败（隔离扫描不可用），以远端 CI 为准。
3. 人类决定：是否解除 draft、是否合并；用户审美认可不由机器断言或代理审阅代替。

