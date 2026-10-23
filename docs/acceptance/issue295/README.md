# #295 / PT-MOB-202 移动端 UI/UX 后续修订 — 实施记录

- 日期：2026-10-23
- 基线：`9fcfcd7d00af4c6ce8bd06b773aa0ac4b11150ec`（origin/main，含 #292/#293）。实施期间 origin/main 前进到 `5900470`（#294 APK casefold，与前端无关）；本分支未包含该提交。
- 分支：`codex/pt-mob-202-uiux`；实现提交 `54764d674ef8fc4f21663e17433503602caf3ef5`，随后一个小修 `4ae4668`（进度页无 job 时不渲染“取消分析”、关闭设置时清空删除确认）；工作树 `.agents/worktrees/pt-mob-202-uiux`。
- 依据：Issue #295 正文 + 2026-10-23 用户转述的 GPT6 ASTRA 两轮审阅意见（排版/可读性、按钮体系与操作层级）。
- 阻塞说明：票面 **Blocked by #274**（PR #289 仍 OPEN）。本次按用户直接指令先实施，未改写 #274 负责的保存确认接缝；合并前需按协作清单回读 #289 产物与最终 main。

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
| `npm run acceptance:reading` | 8 项通过；内部代码断言改为“中文语义首屏可见 + 来源标识展开后可见 `REAL_SCAN`/`REPLAY`”。在 `54764d6` 上复跑：`source 54764d6…, dirty=false`，截图逐字节一致 |
| `npm run acceptance:motion` | 20 项通过 |
| `npm run acceptance:frontend` | 通过（含冻结桌面回归、copy contract 42 项） |
| `npm run acceptance:hierarchy` | 11 项通过 |
| `PRIVACYTRACE_ACCEPTANCE_API_PORT=8199 npm run acceptance:browser` | 通过（桌面报告流程、徽标与时间戳；默认 8123 被本机其他服务占用，脚本按设计拒绝复用） |

失败终态另用仓库自带的 round-2 deterministic bridge（`failJob: true`）在真实 Chromium 里截取：底栏为「刷新状态」+「重新分析」，`role="alert"` 显示桥返回的真实失败原因，任务 ID 收在“任务详情”内；截图见本目录 `progress-failed-*.png`。

未通过或有保留：

- `node scripts/verify-frontend-round2.cjs`：该脚本不在 `package.json`/CI 入口内，最后一段“inline evidence 返回后恢复滚动位置”断言在本分支失败（`before 580, after 0`）。同一合同在 `acceptance:mobile` 的“inline evidence: opening twice … restores focus and the exact scroll position”断言中通过。原因未定：面板变短后 `scrollIntoView` 真正产生了滚动，而该脚本在 150ms 内点击“返回”，落点被后续滚动覆盖；已把等待改为 700ms 仍未复现基线结果，标注为**未解决的手工脚本差异**，不作为通过项。
- 仓库根 `npm run acceptance:design` 在 CI workflow 中被引用，但 `package.json` 没有该脚本（基线即如此，未在本票处理）。

## 4. 截图

“改后”截图存放在本目录，均由 `acceptance:mobile` / `acceptance:reading` 的真实 Chromium + mocked native bridge 生成：

| 文件 | 场景 |
| --- | --- |
| `import-320-200-after.png` | 导入已选材料，320px，200% 根字号（主操作独占一行） |
| `import-320-after.png` | 导入已选材料，320px，默认字号 |
| `candidates-320-200-after.png` | 候选页，320px，200%（材料摘要换行、来源标签栏、候选列表行） |
| `candidates-390-after.png` | 候选页长来源标题，390px |
| `candidates-390-reading-after.png` | 候选页，390px（reading 套件视角） |
| `progress-320-200-after.png` | 进度页，320px，200%（失败/进行中底栏不再挤占正文） |
| `progress-failed-390-after.png` | 失败终态，390px：真实失败原因 + 「重新分析」主操作、「刷新状态」次操作、任务详情折叠 |
| `progress-failed-320-200-after.png` | 失败终态，320px，200% |
| `report-320-200-after.png` | 报告，320px，200%（说明不再叠行） |
| `progress-failed-390-after.png` | 失败终态，390px：真实失败原因 + 「重新分析」主操作、「刷新状态」次操作、任务详情折叠 |
| `progress-failed-320-200-after.png` | 失败终态，320px，200% |
| `import-empty-390.png` | 导入空态：空状态卡片承载唯一主 CTA，没有固定底栏 |
| `material-delete-confirm-390.png` | 删除材料二次确认：作用对象、后果、确认/取消 |
| `settings-390.png` | 服务与存储设置（全屏 sheet） |
| `evidence-inline-390.png` | 行内证据：静态线索 → 政策原句 → 未知项 → 技术详情 |
| `report-390-200-after.png` | 报告，390px，200% |

“改前”截图只在 ASTRA 审阅时提供的本机忽略目录里（`320-import-200.png`、`390-report-200.png`、`320-candidates.png`、`390-evidence-sheet.png`、`390-progress-failed.png` 等），未上传；本目录不复制旧图，避免与历史证据混淆。

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

