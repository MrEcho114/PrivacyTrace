# PrivacyTrace 移动端现状审计（Claude 基线重置前）

- 审计对象：PrivacyTrace 移动端 App（Tauri/Android WebView 壳 + `apps/web/src/mobile/` 加载的移动界面）。
- 审计基线：当前工作树，`HEAD 017f031dbf84`，分支 `codex/issue145-native-busy-fix`（2026-10-22 读取）。工作树含其他会话的未提交改动；本文只描述读取时的移动端相关文件。
- 目标基线：`docs/design/frontend-design-spec-mobile.md`（v0.1，2026-10-23）与任务给定的 Claude 移动端 token。下文以「Spec」简称该文件；规范修订后行号可能漂移，引用以 §编号为准。
- 对齐：已按主代理 2026-10-22 的六条规范决策（操作栏投影、sheet/全页标题、附录 B 勘误、新状态 token、作用域化、暖砂规则）更新目标引用；P0/P1/P2 计数不变。
- 方法：阅读源码、契约快照、验收脚本与验收记录；**没有打开截图逐像素审查**，截图只按文件名、README/JSON 记录计数和引用，不臆造画面内容；没有修改任何产品代码、脚本或验收文件。
- 结论口径：先说事实，再在第 6 节给判断。所有差距都带 `文件:行号` 或脚本断言；没验证过的写「未验证」。

> 说明：主代理的 EAC 设计项目 `78b0e819-0312-481d-9347-d777020a7fe7` 与本审计是两条产物线。本文只是仓库内现状审计，不代替设计项目的成品与预览。

## 1. 范围

### 1.1 当前移动端入口

- 同一个 Vue 产物按运行环境分流：Tauri 内进入 `MobileApp.vue`，离线回放进入只读报告，普通浏览器仍是桌面 Web 工作台。`apps/web/src/main.ts:12-15` 的选择链是 `offline ? ExistingReports : isTauri() ? MobileApp : WorkflowApp`。
- Tauri 壳直接加载 `apps/web/dist`，没有第二套移动端 HTML 入口：`apps/mobile/src-tauri/tauri.conf.json:6` 的 `frontendDist` 为 `../../web/dist`；产品名与包标识见同文件 `:3-5`。
- 当前 Tauri 配置 `bundle.active = false`（`apps/mobile/src-tauri/tauri.conf.json:11`），仓库内不产出可分发包；Android 构建准备脚本固定 API36、关闭明文传输、关闭备份：`apps/mobile/prepare-android.ps1:9-18`、`:26`。
- 移动壳通过原生 bridge 调用上传/恢复/删除/取消/模型/工作流动作：`apps/web/src/mobile/bridge.ts:17-28`。上传来源对话框、应用选择器等原生 UI 不在 `apps/web/src/mobile/` 内，本文不审计。
- 软键盘补丁在 `main.ts` 全局安装（`apps/web/src/main.ts:13`），但只有移动壳挂载后才消费 `html.keyboard-open` 与 `--keyboard-inset`。

### 1.2 本审计看什么、不看什么

- 看：导入、候选、进度、报告、设置五个界面；移动壳、组件状态、移动硬约束、与 Claude 基线的差距、契约影响面。
- 不看：桌面工作台（`WorkflowApp.vue`、`App.vue` 的非 `mobile` 分支）、`apps/api`、原生 Kotlin 插件、真实 APK 扫描、真实模型、部署与发布。
- 「五个界面」是产品口径；代码里的流程轨道只有四步：导入、候选、进度、报告（`apps/web/src/mobile/MobileApp.vue:25-30`）。设置是顶栏按钮打开的全屏 sheet（`:226-228`、`:344-367`），**不是第五个流程步骤**，也不进入 `stepMeta`。下文按五屏描述，但会明确这一点。

## 2. 屏幕与流程清单

### 2.0 共享外壳

- 结构：`div.mobile-workspace` → skip link → `header.m-appbar` → `nav.m-steps` → `main#workspace-content.m-main` → `footer.m-actionbar` → 设置/证据 sheet。`apps/web/src/mobile/MobileApp.vue:218-344`。
- 顶栏：`position: sticky`、`min-height: calc(56px + safe-top)`、左返回（导入步隐藏）、中间 `h1#page-title`、右设置；标题用衬线 20px/500。`apps/web/src/mobile/mobile.css:42-90`；标题映射见 `MobileApp.vue:25-32`。
- 步骤导航：四列网格、单行、`aria-label="创建流程"`、`aria-current="step"`、未来步骤禁用、完成项显示 ✓。`MobileApp.vue:231-240`；样式 `mobile.css:92-140`。
- 底部操作栏：`position: fixed`、`min-height: calc(64px + safe-bottom)`、`role="group" aria-label="当前步骤操作"`；报告步不渲染。`MobileApp.vue:329-342`；样式 `mobile.css:459-478`。
- 内容区：最大宽 720、左右 16、底部预留「实测操作栏高度 + 24 + safe-bottom」；报告步不留操作栏高度。`mobile.css:143-151`；操作栏高度由 `ResizeObserver` 写到 `--m-actionbar-actual`，见 `MobileApp.vue:84-94`。
- 滚动：文档级（body）滚动，顶栏 sticky、操作栏 fixed；这是 round2 的刻意选择，用于保留 Tauri WebView 的原生滚动恢复与证据焦点契约。`mobile.css:1-10`；`MobileApp.vue:64-71`。
- 材料上下文：仅候选/进度显示一行紧凑上下文（导入/报告不显示）；可展开详情、右侧「更换」。`MobileApp.vue:243-244`；`apps/web/src/components/MobileMaterialContext.vue:9-24`。
- 标题：导入「应用与政策」、候选「检查政策候选」、进度「分析进度」、报告「对照报告」。`MobileApp.vue:25-30`。

### 2.1 导入

| 维度 | 事实 | 证据 |
| --- | --- | --- |
| 主体 | 无材料时一张空态卡（标题、说明、两个按钮）；有材料时「当前分析材料」卡（名称、APK SHA-256、分析服务 origin、删除远端材料）、政策来源折叠行、网页辅助收集、个人模型折叠区 | `MobileApp.vue:246-294` |
| 顶栏 | 无返回箭头，标题「应用与政策」，右侧设置；56 + safe-top | `MobileApp.vue:220-229` |
| 步骤导航 | 第 1 步当前；候选在无材料时禁用，进度/报告禁用 | `MobileApp.vue:231-240`、`:38-43` |
| 固定操作栏 | 次「重新读取材料」、主「自动准备政策并继续」；无材料时两者禁用 | `MobileApp.vue:330-333` |

要点：

- 空态卡：`h2`「选择要对照的应用」、边界说明、「选择应用并上传」主按钮、「恢复当前实例材料」次按钮。`MobileApp.vue:247-254`。
- 有材料卡：`m-card-head` 内「删除远端材料」quiet 按钮；材料名、哈希、长期保留说明、分析服务 origin。`MobileApp.vue:255-261`。
- 请求中提示：`.m-busy-notice` 内只有文本 `role="status"`，停止按钮是兄弟节点，不嵌在 live region。`MobileApp.vue:262`；验收断言 `scripts/verify-frontend-round2.cjs:782-783`。
- 政策来源：`details/summary` 行，行副文案固定「完整度未知 · 未复核 · 附件未检查」；展开显示 URL/正文。`MobileApp.vue:263-282`。
- 网页辅助收集：`PolicyAssist` 的 `details`，字段、复制指令、回填 JSON、检查、确认补入。`apps/web/src/components/PolicyAssist.vue:38-57`。
- 个人模型：`details`「使用手机上的个人模型」，模型名称/应用名称或包名两个 `mobile-field`，可查看完整指令，主按钮在未配置或空值时禁用。`MobileApp.vue:284-293`。

### 2.2 候选

| 维度 | 事实 | 证据 |
| --- | --- | --- |
| 主体 | 紧凑材料行 → 来源标签 → 来源状态行 → 分段控件（政策原文/候选声明）→ 两个 tabpanel → 候选编辑表单 | `CandidatePage.vue:81-112`；`MobileApp.vue:243-244`、`:296` |
| 顶栏 | 返回箭头（回导入）、标题「检查政策候选」、右侧设置 | `MobileApp.vue:221-228` |
| 步骤导航 | 第 2 步当前；导入可回，进度/报告仍禁用（直到候选保存/开始） | `MobileApp.vue:234-240`、`:38-43` |
| 固定操作栏 | 次「修改材料」、主「保存候选并开始分析」；busy 时主按钮等待 | `MobileApp.vue:334-337` |

要点：

- 移动端用 `CandidatePage` 的 `mobile` prop 隐藏页内大标题和 `.flow-footer`，避免与壳的 h1/操作栏重复。`apps/web/src/pages/CandidatePage.vue:81`、`:114`；`mobile.css:507`。
- 来源标签是横向可滚动的 `source-tabs`；来源状态行展示来源类型、版本、失败/完整度/未复核/附件未知等事实。`CandidatePage.vue:83-88`；`mobile.css:324-325`。
- 分段控件保留 roving tabindex：一个 tab stop，左右箭头/Home/End 移动焦点。`CandidatePage.vue:17-32`、`:90-93`。
- 两个面板：政策原文（可聚焦阅读区、原句 mark、重新提取/重新获取）、候选声明（数量、添加、列表、空文案、编辑表单）。`CandidatePage.vue:95-111`。
- 候选行整行可点，右侧 chevron；选中行用 state layer + 左侧内阴影。`CandidatePage.vue:102`；`mobile.css:271-290`。
- 编辑表单：政策原句 textarea、数据类型、声明方式、声明主体、条件、声明动作、声明目的、接收方；保存/删除在表单内，主操作栏仍可达。`CandidatePage.vue:103-110`。
- busy 时两个面板 `inert` + `aria-busy`。`CandidatePage.vue:94`。

### 2.3 进度

| 维度 | 事实 | 证据 |
| --- | --- | --- |
| 主体 | 状态卡（阶段文字 `role=status`、标题、job id、失败 alert/成功说明）→ 分析阶段时间线（圆点/线/时间）→ 无事件时说明 | `MobileApp.vue:298-315` |
| 顶栏 | 返回箭头（回候选）、标题「分析进度」、右侧设置 | `MobileApp.vue:221-228` |
| 步骤导航 | 第 3 步当前；按可达性允许回候选/导入 | `MobileApp.vue:234-240` |
| 固定操作栏 | 运行中：次「取消分析」、主「刷新进度」；失败/取消：次「重试为新的分析」、主「刷新进度」；成功：主「查看报告」，无次操作 | `MobileApp.vue:338-341`、`:195-200` |

要点：

- 阶段文案映射：等待处理、核对材料、静态扫描、装载政策、规则对照、生成报告、报告已生成、分析未完成、分析已取消。`MobileApp.vue:23`；当前阶段文字 `:61`。
- 失败状态：状态卡加 `failed` 类，`role="alert"` 文案「本次分析未完成…」，不出现「查看报告」。`MobileApp.vue:299-304`；验收断言 `verify-frontend-round2.cjs:760-768`。
- 时间线来自 `draft.jobs` 中当前 job 的 `events`；没有事件时显示占位说明。`MobileApp.vue:60`、`:306-315`。
- 自动轮询：首次 10s、之后 25s、带抖动；忙碌/错误有退避；后台轮询不得覆盖更新的前台操作（epoch）。`apps/web/src/mobile/flow.ts:9-11`、`:31-49`、`:188-234`。
- 前台主操作：成功打开报告，否则刷新进度；终态取消/重试走 `control`。`MobileApp.vue:195-200`；`flow.ts:235-240`。
- 轮询不重置滚动、不抢焦点：断言 `verify-frontend-round2.cjs:476-482`。

### 2.4 报告

| 维度 | 事实 | 证据 |
| --- | --- | --- |
| 主体 | `MobileReportSummary` 单一身份摘要 → 「隐私声明对照」问题行列表 → 证据 bottom sheet → 复用桌面报告章节（SDK 归属、DEX 覆盖、输入来源、生成来源、政策快照、页脚） | `App.vue:662-667`、`:720-737`、`:738-816` |
| 顶栏 | 返回箭头（回进度）、标题「对照报告」、右侧设置 | `MobileApp.vue:221-228` |
| 步骤导航 | 第 4 步当前；报告可回看，进度/候选/导入按可达性 | `MobileApp.vue:234-240` |
| 固定操作栏 | **不显示** `footer.m-actionbar`；报告内操作保留 | `MobileApp.vue:329`；断言 `verify-frontend-round2.cjs:497` |

要点：

- 移动报告走 `snapshot` 只读路径：`ExistingReports` 传入 `{ report, taxonomy }` 与材料信息，按 `report.job.id` 重新挂载。`MobileApp.vue:318-320`；`App.vue:11`、`:633-637`。
- 摘要卡：应用名、版本、来源/投递两个 badge、边界文案、三类计数（数据类型/政策来源/可查看证据）、可展开的「报告来源与版本」、更换材料。`MobileReportSummary.vue:23-56`。
- 问题行：整行按钮，含数据类型、状态 tag（`.tag clear/review`）、政策文档标签、证据条数、chevron；`aria-expanded`/`aria-controls="evidence-panel"`。`App.vue:720-728`。
- 证据 sheet：`UiSheet` 默认 bottom sheet，标题为「数据类型 · 状态」，描述「静态证据、政策原句与候选条款；关闭后回到触发该项的结论」；内部是同一 `EvidencePanel`（`heading=false`）。`App.vue:735-737`。
- 打开/关闭证据：记录触发按钮与 `scrollY`，移动端只 emit `evidenceOpen`；关闭后焦点回触发按钮并精确恢复滚动；`defineExpose` 供壳的返回键先关 sheet。`App.vue:56-85`；`MobileApp.vue:189-193`。
- 桌面的 `topbar`/`intro`/`table-scroll`/`metrics`/来源选择器在移动端隐藏；移动端没有报告来源切换器，进度页「刷新进度」是报告刷新入口。`App.vue:643-648`、`:662`、`:717-728`；`issue144/round2/20261022.md:37`。
- 移动快照下「人工复核备注」不渲染（`v-if="realReport && !offlineReplay && !snapshot"`），因为 `snapshot` 被传入。`App.vue:793`；`MobileApp.vue:319`。这是只读快照设计，不是隐藏按钮。

### 2.5 设置

| 维度 | 事实 | 证据 |
| --- | --- | --- |
| 主体 | 三段：模型连接（本机配置/端点/说明/设置按钮）、材料与存储（当前分析服务/删除/重新读取）、证据边界（静态线索、UNKNOWN/PARTIAL/UNREVIEWED/附件未检查） | `MobileApp.vue:344-367` |
| 顶栏 | 设置是 `UiSheet variant="detail"` 全屏页：sheet 自己的标题「服务与存储设置」+ 描述 + 关闭；底层 shell 顶栏被遮罩盖住 | `MobileApp.vue:344`；`UiSheet.vue:20-38` |
| 步骤导航 | 没有自己的步骤导航；底层四步条仍在 DOM 中但被模态遮挡 | `MobileApp.vue:231-240`、`:344-367` |
| 固定操作栏 | 不显示；操作在 sheet 正文内 | `MobileApp.vue:329`、`:350-360` |

要点：

- 打开：顶栏设置按钮记录触发元素、`settingsOpen = true`、`pushOverlay()` 入 history。`MobileApp.vue:178-182`、`:226-228`。
- 关闭：Esc 与返回键已验证（`verify-frontend-round2.cjs:394-404`）；关闭按钮有可访问名称「关闭」（`:388`），点击行为未单独断言；遮罩点击依赖 Reka 默认行为，设置 sheet 未单独断言。非返回键关闭会 `popOverlay()`，关闭后焦点回到触发按钮。`MobileApp.vue:183-188`、`:155-163`；`UiSheet.vue:21`。
- 全屏 detail：`inset: 0`、`height: 100dvh`、无圆角/无阴影、顶部 safe-top、内部滚动。`UiSheet.vue:67-70`；`mobile.css:532-544`。
- 设置不是第五步：`stepMeta` 只有 4 项，设置无独立路由；关闭后仍停在原步骤。`MobileApp.vue:25-30`、`:183-188`。
- 设置里的模型配置会调用原生 `configure_model`；Key 不进 JS。`bridge.ts:19-22`；`MobileApp.vue:350`。

### 2.6 流程、返回与滚动恢复

- 步骤可达性：导入永远可回；候选需要材料；进度需要材料且（有 job 或有报告）；报告需要报告。`MobileApp.vue:38-43`。
- 语义返回链：候选→导入、进度→候选、报告→进度。`MobileApp.vue:96-101`。
- history：前进 push，后退 `history.go`；跳过步骤时补齐中间 entry；流程重置时 replace。`MobileApp.vue:102-134`。
- `popstate`：先处理设置/证据 overlay，再处理步骤；无法解析时回退到语义上一步，避免壳卡死。`MobileApp.vue:145-177`。
- 每次步骤变化：保存上一屏 `scrollY`、焦点落到 `#page-title`（`preventScroll`）、恢复目标屏滚动、触发 160ms 进入动画。`MobileApp.vue:119-143`。
- 设置/证据 overlay 的 history 计数：`overlayEntries` 与 `ignoreNextPop`。`MobileApp.vue:73-76`、`:145-154`。
- 证据 sheet 的关闭先由 `App.vue` 还原焦点/滚动，再由壳 pop 一个 overlay entry。`App.vue:72-85`；`MobileApp.vue:189-193`。

## 3. 现有 token

### 3.1 定义位置

- 唯一变量文件是 `apps/web/src/theme.css`；`style.css:1` 只有 `:root { font-synthesis: none; }`，不定义设计 token。
- `--m-actionbar-actual` 不是 `theme.css` token，而是 `MobileApp.vue:84-94` 用 `ResizeObserver` 写入根元素的运行时测量值；`--keyboard-inset` 由 `viewport.ts:39` 写入，也不是主题 token。
- 当前 `apps/web/src` 没有任何 `--mt-*`：在 `apps/web/src` 的 CSS 与 Vue 文件中检索 `--mt-` 命中数为 0（2026-10-22 21:45 读取）。同批的 `docs/design/mobile-reset/mobile-design.tokens.json` 已在审计期间（21:55）由主代理创建，但还没有接进 `theme.css`；**契约存在不等于实现落地**。

### 3.2 颜色

Pioneer 基础色（`theme.css:5-10`）：

```text
--canvas        #f6f5f1
--surface       #fdfcfa
--surface-muted #eeedea
--ink           #2c3547
--muted         #64696f
--navy          #333c50
--border        #d9d7d2
--control       #858d92
--mint          #dce9df
--success       #35644b
--slate         #dde2e9
--notice        #ede4d6
--rose          #ebdada
--error         #934342
--navy-hover    #212a3b
--danger        #b25352
--gold          #c6af94
--on-action     #f9f9f9
--overlay       rgba(44, 53, 71, .3)
```

Round2 移动壳状态/浮层色（`theme.css:30-35`，全部是 `--m-*`）：

```text
--m-state-hover    rgba(44, 53, 71, .06)
--m-state-press    rgba(44, 53, 71, .12)
--m-state-selected rgba(51, 60, 80, .08)
--m-scrim          rgba(44, 53, 71, .42)
--m-shadow-bar     0 1px 2px rgba(44, 53, 71, .08)
--m-shadow-sheet   0 -8px 32px rgba(44, 53, 71, .18)
```

判断前的事实备注：

- 移动组件没有硬编码十六进制颜色；`mobile.css`、`UiSheet.vue`、`MobileApp.vue` 中未命中 `#rrggbb` 或 `rgba()` 的硬编码（`rgba()` 只出现在注释行号文本中）。
- 语义色没有成对的「文本档/底档」：success 只有文字值、mint 当底；notice 只有底值、wait 文字沿用 ink；error 只有文字值、rose 当底。`workbench.css:121-125`。
- 旧 `--overlay` 是桌面/旧弹层用；移动 sheet 用 `--m-scrim`。

### 3.3 字体

```text
@font-face 'Noto Sans SC'  /fonts/NotoSansSC-Variable.woff2   theme.css:2
@font-face 'Noto Serif SC' /fonts/NotoSerifSC-Variable.woff2  theme.css:3
--font-body    'Noto Sans SC', 'Microsoft YaHei', system-ui, sans-serif   theme.css:48
--font-display 'Noto Serif SC', SimSun, serif                 theme.css:49
--font-code    Consolas, 'Courier New', monospace             theme.css:50
根字体：font-family: var(--font-body); line-height: 1.6     theme.css:51-52
```

事实备注：

- 没有 Inter、Georgia、阅读衬线栈、SF Mono/JetBrains Mono；`--font-display` 已是衬线，所以标题至少是衬线，但回落顺序与目标不同。
- 政策原文 `.policy-reading` 没有 `font-family`（`workbench.css:137`），实际继承无衬线；移动端只改字号/行高/高度（`mobile.css:323`）。

### 3.4 字号与行高

```text
--m-font-title   1.25rem / 20px   [round2] theme.css:25
--m-font-section 1rem    / 16px   [round2] theme.css:26
--m-body         .875rem / 14px   [round2] theme.css:27
--m-caption      .75rem  / 12px   [round2] theme.css:28
--m-line-body    1.65             [round2] theme.css:29
```

事实备注：

- 移动壳正文/说明/按钮/字段全部吃 `--m-body` 14px；大段说明 `--m-caption` 12px。
- 桌面基线 body 也是 14px（`workbench.css:4`），按钮 14（`:99`），字段 14（`:81`），状态标签 12（`:121`）。移动壳只是覆盖了控件的最小高度和输入字号，没有重建字号阶梯。
- 报告摘要数字 `1.25rem`（`mobile.css:428`），报告标题 20（`MobileReportSummary.vue:64`），政策阅读 15（`workbench.css:137`、`mobile.css:323`）。

### 3.5 间距与几何

```text
--space-4/8/12/16/24/32   theme.css:12-13
--m-gutter                16px   [round2] theme.css:22
--m-touch                 48px   [round2] theme.css:19
--m-appbar-height         56px   [round2] theme.css:20
--m-actionbar-min-height  64px   [round2] theme.css:21
```

事实备注：

- 正文边距 16（`mobile.css:148`），顶栏 56 + safe-top（`:50`），操作栏 64 + safe-bottom（`:469`），触控 48（`:488`）。
- 内容最大宽 720（`mobile.css:146`），不是 Spec 的 560。

### 3.6 圆角

```text
--radius          8px    theme.css:11
--radius-panel    12px   theme.css:11
--m-card-radius   12px   [round2] theme.css:23
--m-sheet-radius  20px   [round2] theme.css:24
```

事实备注：

- 组件里还有未 token 化的圆角：步骤按钮 10（`mobile.css:112`）、text button 8（`:181`）、分段选中 9（`:306`）、移动按钮 10（`:489`）、输入 10（`:500`）、图标按钮 999（`:81`）、时间线圆点 50%（`:407`）。
- 卡片、上下文行、issue 卡、时间线、报告卡都用 `--m-card-radius`；标签用 `--radius`（8），不是目标 6。

### 3.7 动效

```text
--motion-color       150ms; --ease-color ease                     theme.css:39  [round1/通用]
--m-duration-press   120ms                                        theme.css:43  [round2]
--m-duration-enter   200ms                                        theme.css:44  [round2]
--m-duration-exit    150ms                                        theme.css:45  [round2]
--m-ease-standard    cubic-bezier(.2, 0, 0, 1)                    theme.css:46  [round2]
--m-ease-decelerate  cubic-bezier(0, 0, 0, 1)                     theme.css:47  [round2]
```

事实备注：

- `--m-duration-exit` 已定义，但 `UiSheet` 只有进入动画，关闭是即时卸载（`UiSheet.vue:41-48`、`:74-84`；`issue144/round2/20261022.md:77`）。
- reduced-motion 在移动 CSS 和 `UiSheet` 都有兜底（`mobile.css:547-551`；`UiSheet.vue:82-84`）。

## 4. 组件与状态

### 4.1 移动流程真实使用的组件

- `MobileApp.vue` 直接 import：`UiButton`、`UiIcon`、`UiSheet`、`PolicyAssist`、`CandidatePage`、`ExistingReports`（即 `App.vue`）、`MobileMaterialContext`。`MobileApp.vue:3-15`。
- `CandidatePage.vue` 再 import：`UiButton`、`UiField`、`UiIcon`、`StatusTag`。`CandidatePage.vue:3-6`。
- `App.vue` 移动分支 import：`EvidencePanel`、`UiSheet`、`UiIcon`、`MobileReportSummary`。`App.vue:7-10`。
- `MobileReportSummary.vue` 用 `UiIcon`、`UiButton`；`MobileMaterialContext.vue` 用 `UiButton`、`UiIcon`。
- `MaterialContext.vue` 只被桌面 `LiveWorkflow.vue:8` 使用，移动端没有用；移动端用的是 `MobileMaterialContext.vue`。`issue144/round2/20261022.md:38` 记录了不复用桌面组件的原因。

### 4.2 按钮

- 实现：`UiButton.vue:2` 定义 `primary/secondary/quiet/danger`、`busy`、`disabled`、`type`；默认 `secondary`。模板在 `UiButton.vue:4`。
- 基础样式：`.ui-button` 36px 高、8px 圆角、7×12 内边距、14px 字、500 字重（`workbench.css:99`）；primary 藏青底/象牙字（`:115`），quiet 透明底/继承 ink（`:117`），danger 红底/象牙字（`:118`），disabled 暖灰底/灰字（`:120`）。
- 移动覆盖：48px 最小高（`mobile.css:488`）、10px 圆角、10×14 内边距、14px 字、按下 `scale(.98)`、非 primary/danger 按下底色（`:489-491`）、primary hover 用 `--navy-hover`（`:511`）。
- 状态覆盖：
  - 默认：有；secondary 没有独立类规则，直接吃 base。
  - 按下：有，`scale(.98)` + state layer（`mobile.css:490-491`）。
  - 悬停：有，但只在 `(hover: hover) and (pointer: fine)`（`mobile.css:509-515`；`workbench.css:108-113`）。
  - 焦点：全局 `:focus-visible` 2px navy + offset 3（`workbench.css:15`）；没有按钮专属焦点样式。
  - 禁用：有，`disabled` 原生 + 暖灰底（`workbench.css:120`）；不进 Tab 序列。
  - 等待：有，但只是把 `…` 追加到文字后并 `disabled`（`UiButton.vue:4`），没有旋转指示、没有固定宽度；`aria-busy` 有。
- 事实缺口：quiet 按钮文字仍是 `--ink`，不是 accent 文字；primary 是藏青不是陶土；`--on-action` 是 `#f9f9f9` 不是 Spec 的 `#faf9f5`。

### 4.3 字段

- 实现：`UiField.vue:2-4` 提供 label、slot、help/error；error/help 通过 `aria-describedby` 关联（`:4`）。
- 基础样式：grid、label 14/500、输入 14px/40px/8px 圆角/control 边框（`workbench.css:79-85`）；invalid 边框变 `--error`（`:84`）；disabled 暖灰底（`:83`）；placeholder 用 `--muted`（`UiField.vue:8-9`）。
- 移动覆盖：输入/select/textarea 48px 最小高、10px 圆角、`font-size: max(16px, 1rem)`；textarea 最小 96；`.mobile-field` 单列；`.ui-field` 标签 14（`mobile.css:492-506`）。
- 状态覆盖：默认、placeholder、help、error、disabled、invalid 都有；焦点只有全局 outline，输入边框不转为 focus 色。
- 事实缺口：移动字段 48 高/10 圆角，目标 56/12；label/help 字号达标（14/12），但颜色是 Pioneer `--muted`。

### 4.4 状态标签

- `StatusTag.vue:1-3` 支持 `neutral/info/wait/success/error` 五 tone；样式在 `workbench.css:121-125`：自动高度、8px 圆角、12px 字、4×8 内边距、500 字重；`neutral` 用 `--surface-muted`，`info` 用 `--slate`，`wait` 用 `--notice`，`success` 用 `--mint`，`error` 用 `--rose`。
- 使用：候选来源类型、候选检查状态（`CandidatePage.vue:85`、`:95`、`:102`）。
- 报告另用一套 `.tag`：`clear/review` 两态，样式在 `hierarchy.css:128-130` 与 `style.css:48`；不是 `StatusTag`。`App.vue:723`。
- 事实缺口：没有固定 24 高、没有 10 横内边距、没有 6 圆角；两套标签体系并存。

### 4.5 卡片、行、上下文

- 卡片：`.m-card` 16 内边距、12 圆角、surface 底、1px border（`mobile.css:203-210`）；报告 sample/coverage/section 等 14 内边距、12 圆角（`:417-438`）；issue 卡 12 圆角（`:329`）。
- 行：政策来源 `details/summary` 最小 48、8×12 内边距（`mobile.css:234-252`）；候选行 12×40×12×14 内边距、12 圆角（`:273-287`）；issue 行最小 72、12×14（`:330-344`）；时间线行最小 48（`:402`）。
- 上下文：`MobileMaterialContext` 一行 summary 最小 48、右侧「更换」、展开详情（`MobileMaterialContext.vue:9-24`、`:28-42`）。
- 状态：卡片本身无按下/选中；issue 行有 active/hover（`mobile.css:351-354`）；候选行有 selected/active/hover（`:280-290`）；来源行只有 hover（`:512-513`）。
- 事实缺口：候选行 48 vs 目标 56；卡片 12 圆角 vs 16；卡片 padding 14/16 vs 16/20；报告卡内没有 L2 环影。

### 4.6 Sheet

- 实现：`UiSheet.vue` 用 Reka Dialog，`bottom` 默认 / `detail` 全屏；props `title`、`description?`、`initialFocus?`；事件 `close`。`UiSheet.vue:5-18`、`:20-38`。
- 样式：overlay 用 `--m-scrim` + fade；sheet 底部、宽 `min(100%, 640px)`、高 `min(88dvh, 720px)`、顶部 20 圆角、`--m-shadow-sheet`；handle 36×4；关闭 48×48；正文内部滚动（`overscroll-behavior: contain`）。`UiSheet.vue:41-66`。
- detail：`inset: 0`、`height: 100dvh`、无边框/无圆角/无阴影、顶部 safe-top。`UiSheet.vue:67-70`。
- 状态：打开动画、焦点进入（优先 `initialFocus`，否则关闭按钮）、`aria-modal=true`、`aria-labelledby`/`aria-describedby`、Esc/返回关闭、焦点陷阱（Reka）。证据 sheet 另断言了遮罩点击关闭（`verify-frontend-round2.cjs:556`）；设置 sheet 的遮罩关闭未单独断言。`UiSheet.vue:11-18`、`:24`、`:32-34`。
- 关闭：没有退出动画，组件直接卸载；`--m-duration-exit` 未被消费。
- 移动覆盖：证据 sheet `body:has(...)` scrim、底部 `--keyboard-inset`、`html.keyboard-open` 最大高度；设置 sheet 全屏底色/头部/正文 padding。`mobile.css:517-544`。

### 4.7 空态、错误/通知、加载

- 空态：
  - 导入：`m-card m-empty-card`，h2 20、两段说明、两个按钮（`MobileApp.vue:247-254`）。
  - 候选：只显示 `field-help` 空文案（`CandidatePage.vue:102`）。
  - 进度：只显示「任务创建后会在这里按时间顺序显示阶段记录。」（`MobileApp.vue:314`）。
  - 报告：只显示 notice「报告尚未载入，请返回进度刷新状态。」（`MobileApp.vue:321`）。
- 错误/通知：
  - `.m-error` 红字（`mobile.css:394`）；`.m-notice` 米色底、12 圆角、正文 14（`:357-364`）；`.m-busy-notice` 文本与停止按钮分列（`:367-374`）。
  - 报告/进度里的 `role="alert"`/`role="status"` 由模板给出（`MobileApp.vue:300-303`、`:323-326`；`App.vue:707`、`:709`）。
- 加载：
  - 没有 skeleton。导入读取材料时只有「正在读取材料…」文本（`MobileApp.vue:257`）；请求中只有「正在处理当前请求。」（`:262`）；按钮等待是追加 `…`（`UiButton.vue:4`）。
  - 进度页用阶段文字 + 时间线表达进行中（`MobileApp.vue:299-315`），不是骨架/百分比。
- 事实缺口：空态标题不是 24、导入空态两个 CTA；没有骨架；通知没有语义底/图标；错误只有红字。

### 4.8 选中/当前状态

- 步骤：`aria-current="step"` + 背景 `--m-state-selected` + 数字藏青底（`mobile.css:132-133`）；完成项绿色 + ✓（`:134-135`；`MobileApp.vue:235`）。
- 候选：选中行 `background: --m-state-selected` + `border-color: --navy` + `inset 3px 0 --navy`（`mobile.css:280`）。
- 分段：选中 tab surface 底 + ink 字 + 600（`mobile.css:312-317`）。
- 时间线：当前 dot 藏青 + 4px selected 环（`mobile.css:408`）。
- 事实缺口：选中/当前是藏青系，不是目标「陶土文字 + 2px 下划线/✓」；候选用左侧内阴影，不是下划线。

## 5. 移动硬约束现状

| 约束 | 代码实现 | 自动断言（Chromium 模拟） | 真机/人工 |
| --- | --- | --- | --- |
| 触控 ≥48 | 按钮/行/summary/输入统一 `min-height: var(--m-touch)`（`mobile.css:481-488`）；图标按钮 48×48（`:73-84`）；sheet 关闭 48（`UiSheet.vue:54-58`） | 48×48 断言 `verify-frontend-round2.cjs:87-115`；设置按钮 `[48,48]` `:334`；主操作 `:337`；候选行 `:426`；报告 13 控件、证据 sheet 18 控件见 `mobile-round2-walkthrough.json` | 未验证（真实触控几何） |
| 输入 ≥16 | `font-size: max(16px, 1rem)`（`mobile.css:492-501`） | 可见字段 ≥16 断言 `verify-frontend-round2.cjs:116-129`、`:428`；`verify-mobile-flow.cjs:184-189` | 未验证（真实 IME/系统缩放） |
| safe-area | 顶栏/正文/操作栏/sheet 都用 `env(safe-area-inset-*)`（`mobile.css:50-51`、`:148`、`:470`；`UiSheet.vue:45`、`:65`、`:69`；`index.html:8`） | 只断言 viewport meta 含 `viewport-fit=cover`（`verify-frontend-round2.cjs:339`）；Chromium `env()` 为 0 | 未验证（刘海/手势条实机） |
| 100dvh | `.mobile-workspace` `min-height: 100dvh`（`mobile.css:16`）；detail sheet `height: 100dvh`（`UiSheet.vue:68`） | shell 高度 ≥844（`verify-frontend-round2.cjs:344`）；设置高度 ≥843（`:386`） | 未验证（Android WebView 实际可视高） |
| 软键盘 | `viewport.ts` 发布 `--keyboard-inset`/`html.keyboard-open`（`viewport.ts:24-56`）；操作栏 `bottom: var(--keyboard-inset)`（`mobile.css:463`）；sheet 底部/最大高（`:519-520`）；页面预留 `scroll-padding-bottom`/body padding（`workbench.css:412-415`） | 模拟 460px 键盘：open/inset/barBottom/focus/bodyPadding/字段可达 `verify-frontend-round2.cjs:687-731` | 未验证（真实 IME） |
| 返回 | 顶栏返回与 `popstate` 共用语义链（`MobileApp.vue:96-177`）；overlay 先消费返回（`:114-118`、`:155-163`） | `history.back()` 模拟：候选→导入、标题焦点 `verify-frontend-round2.cjs:446-458`；设置/证据先关 `:398-404`、`:574`；壳回退 `:585` | 未验证（Android 系统返回键） |
| 滚动恢复 | 每步保存/恢复 `scrollY`（`MobileApp.vue:72`、`:119-144`）；证据打开/关闭保存 `scrollY`（`App.vue:56-85`）；轮询不重置（`MobileApp.vue:119-143` 只在 step 变化时动） | 前进恢复 320±4（`verify-frontend-round2.cjs:455-456`）；证据关闭恢复 `:550`；轮询不重置 `:480` | 未验证（WebView 原生滚动恢复） |
| 焦点管理 | 步骤切换焦点到 h1（`MobileApp.vue:138`）；设置关闭回触发（`:187`）；证据关闭回触发（`App.vue:78-81`）；sheet 打开焦点进 dialog（`UiSheet.vue:11-18`）；h1 程序化聚焦不画控件环（`mobile.css:69-72`） | 标题焦点 `verify-frontend-round2.cjs:451`；设置回触发 `:397`；证据回触发 `:549`、`:557`；焦点环 `:442-443`；h1 无环 `:348` | 未验证（TalkBack/硬件键盘） |
| reduced-motion | 移动 CSS 全局压缩过渡/动画，步骤进入关闭，chevron 关闭（`mobile.css:547-551`）；sheet 动画关闭（`UiSheet.vue:82-84`）；JS 平滑滚动降级（`App.vue:54-55`、`:64`） | 媒体查询、按钮/chevron 过渡、滚动行为 `verify-frontend-round2.cjs:742-745`；sheet 动画 none `:566` | 已验证（浏览器模拟） |
| 200% 根字号 | 字号使用 rem（`theme.css:25-29`）；固定行高改 `max(px, em)`（`workbench.css:22-27`）；操作栏高度实测并预留（`MobileApp.vue:84-94`） | 32px 根字号：操作栏增长、内容 padding 预留、320/390 无横向溢出 `verify-frontend-round2.cjs:657-681`；`verify-mobile-flow.cjs:249-256`、`:336-341` | 未验证（真实系统字体缩放/捏合） |
| 无横向溢出 | `overflow-wrap: anywhere`（`mobile.css:35-40`）；单列候选/报告卡；source tabs 横向滚动（`:324`） | 320/390/768/844×390 的 scrollWidth/bodyScrollWidth/越界元素断言 `verify-frontend-round2.cjs:72-80`、`:590-655`；`verify-mobile-flow.cjs:57-65` | 已验证（浏览器模拟） |
| edge-to-edge / theme-color | `viewport-fit=cover`、`interactive-widget=resizes-content`、`theme-color=#fdfcfa`（`index.html:8-10`）；顶栏背景 surface（`mobile.css:52`） | meta 含 cover/resizes-content、theme 值、顶栏色 `verify-frontend-round2.cjs:339-343` | 未验证（系统栏绘制/刘海实机） |
| 报告阅读长文 | 复用 `EvidencePanel` + `MobileReportSummary`；`policy-reading` 15/1.65（`mobile.css:323`） | `acceptance:reading` 7 组 + 8 图（`docs/acceptance/mobile-reading/verification.json`）；长政策正文可读/可展开 | 未验证（真实长文滚动/读屏） |
| 当前/选中语义 | `aria-current="step"`（`MobileApp.vue:234`）；候选 `aria-pressed`（`CandidatePage.vue:102`）；tab `aria-selected`/roving tabindex（`:90-93`） | 当前步 exactly one（`verify-frontend-round2.cjs:331`）；候选行 chevron/48（`:426-428`）；分段选中（`:418-420`） | 未验证（读屏播报） |

结论边界：上表的「已验证」只表示 Chromium headless + mocked native bridge 的自动化断言通过，不表示 Android WebView、真机、真实 IME 或 TalkBack 通过。`docs/acceptance/issue144/round2/20261022.md:57-64` 与 `docs/acceptance/frontend-round2/20261022.md:71-78` 明确列出设备项 `NOT_RUN`。

## 6. 与目标基线的差距

### 6.1 判断口径

- P0：规范重置的地基。不改就无法称为 Claude 移动基线，后续组件/界面改了也会返工。
- P1：单类组件或关键状态明显不符，影响一致性/可用性，但不阻断主流程。
- P2：细节、个别场景、规范内部待对齐或未覆盖项。
- 目标值主要引 `docs/design/frontend-design-spec-mobile.md`（Spec）；行号指该文件。当前值引 `theme.css`、`mobile.css`、`workbench.css`、组件源码。
- 对比度事实：按 WCAG 2.1 公式复算当前 Pioneer 组合，`ink/canvas` 11.27、`muted/surface` 5.40、`control/surface` 3.29、`on-action/navy` 10.48、`error/surface` 6.56、`success/mint` 5.45、`danger/surface` 4.82、navy 焦点/画布 10.76，均达到 AA（`control/surface` 3.29 达到 3:1 非文本）。**所以颜色 P0 是「基线身份不符」，不是当前可访问性回退；迁移时不能以「现在已达标」为由保留旧色。**
- 暖砂规则（Spec:135）：`--mt-surface-warm` 只用于禁用/骨架/分区带；`--mt-caption` 在其上 4.34、`--mt-meta` 2.92，均不达标，不得在暖砂上放非禁用的 14px 三级文字或图标/描边。
- 规范新增的状态/浮层 token：`--mt-state-hover/.press/.selected`（.06/.12/.08）、`--mt-danger-active #a92e2e`、`--mt-handle #d1cfc5`、`--mt-shadow-bar 0 -1px 2px rgba(20,20,19,.06)`；下文 #12/#14/#24/#25 直接引用。

### 6.2 颜色、字体、字号

| # | 类别 | 级别 | 现状（证据） | 目标值 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 1 | 颜色 | P0 | `theme.css:5-10` 的 19 个颜色全部是 Pioneer：canvas `#f6f5f1`、surface `#fdfcfa`、ink `#2c3547`、navy `#333c50`、border `#d9d7d2`、control `#858d92`、error `#934342`；没有任何 `--mt-*`（检索命中 0） | Spec:84-128：canvas `#f5f4ed`、surface `#faf9f5`、ink `#141413`、muted `#5e5d59`、caption `#6b6a63`、border-soft `#e8e6dc`、border-control `#87867f`、accent-strong `#b04b25`、accent-text `#a8431f`、focus `#1f6fb2` | 所有屏底色/文字/主操作/焦点仍是藏青暖灰，Claude 重置未开始 |
| 2 | 颜色 | P1 | `success/notice/error` 是分散的单值（`theme.css:7-9`）：success 只有文字值、mint 当底；notice 只有底值、wait 文字沿用 ink；error 只有文字值、rose 当底（`workbench.css:121-125`），没有「文本档/底档」成对 token | Spec:124-128：success/warn/danger/info/neutral 各自「文本 + 底」 | 状态标签、通知无法按目标配底色；迁移时需成对替换，避免中途对比度回退 |
| 3 | 颜色 | P1 | navy 同时用于主按钮（`workbench.css:115`）、步骤当前（`mobile.css:133`）、候选选中（`mobile.css:280`）、证据行动作（`mobile.css:349`）；单屏强调点明显超过 2 | Spec:46、108-116：唯一强调是陶土 `#c96442`；每屏 ≤2 处；其余用语义色/中性色 | 视觉焦点分散，主操作与选中态同色，不符合「一种强调」 |
| 4 | 颜色 | P2 | scrim `rgba(44,53,71,.42)`（`theme.css:33`），阴影也是蓝黑（`theme.css:34-35`） | Spec:270 `rgba(20,20,19,.45)`；Spec:260-269 暖黑阴影 | 浮层色调与暖纸底不统一，低对比场景显脏 |
| 5 | 字体 | P0 | UI 栈 `Noto Sans SC, Microsoft YaHei, system-ui`（`theme.css:48`），标题栈 `Noto Serif SC, SimSun`（`:49`），等宽 `Consolas, Courier New`（`:50`）；无 Inter/Georgia/阅读衬线/`--mt-font-*` | Spec:150-158：UI `Anthropic Sans/Inter/Noto Sans SC`；标题 `Anthropic Serif/Georgia/Noto Serif SC`；阅读 `Noto Serif SC/Georgia`；等宽 `SF Mono/JetBrains Mono/...` | 衬线内容/无衬线操作/等宽哈希的分工没有建立，阅读区仍继承无衬线 |
| 6 | 字体 | P1 | `.policy-reading` 15px/1.85，无 `font-family`（`workbench.css:137`；`mobile.css:323` 改 15/1.65），实际继承无衬线 | Spec:170、365：阅读 17/1.75 + 阅读衬线 | 政策原文与报告引文是最长阅读面，字号/行高/字体三处同时偏小偏密 |
| 7 | 字体 | P2 | 衬线标题字重混用：`.m-card h2` 600（`mobile.css:211`）、报告 sample h2 600（`:423`）、`UiSheet` 标题 600（`UiSheet.vue:53`），`MobileReportSummary` h2 500（`MobileReportSummary.vue:64`） | Spec:167-169：标题 500 | 同等级标题视觉重量不一致 |
| 8 | 字号 | P0 | 壳正文 14/1.65（`theme.css:27-29`；`mobile.css:21-22`），caption 12（`:28`）；桌面 body 14（`workbench.css:4`）、按钮 14（`:99`）、字段 14（`:81`）、标签 12（`:121`） | Spec:164-176：body 16/1.6、control 16、caption 14、label 12、title-s 17、title-m 20、title-l 24、body-l 17/1.75、display 32 | 正文/控件偏小一档，阅读区没有 17/1.75，所有界面密度和目标不一致 |
| 9 | 字号 | P2 | 报告没有 24px 页面标题：appbar h1 20（`MobileApp.vue:225`+`theme.css:25`），摘要 h2 20（`MobileReportSummary.vue:64`）；设置 sheet 标题 20（`UiSheet.vue:53`） | Spec:167：title-l 24（报告、全屏设置）；Spec:346：bottom sheet 20 / 全屏 detail 24 | 规范已拆分：sheet 20 / 全页 24；报告与全屏设置页仍只有 20，缺 24 档 |

### 6.3 圆角、层级、组件几何

| # | 类别 | 级别 | 现状（证据） | 目标值 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 10 | 圆角 | P1 | `--radius` 8、`--radius-panel` 12、`--m-card-radius` 12、`--m-sheet-radius` 20（`theme.css:11`、`:23-24`）；按钮/输入实际 10（`mobile.css:489`、`:500`），标签 8（`workbench.css:121`） | Spec:242-249：tag 6、control 12、card 16、sheet 24、pill 999、circle 50% | 卡片与浮层比目标更方，四个圆角层级没有拉开 |
| 11 | 圆角 | P2 | `mobile.css` 硬编码 8/9/10/999px（`:181`、`:306`、`:112`、`:489`、`:500`、`:81`），同类组件出现多档圆角 | Spec:251：同一组件类固定一档 | 迁移若只改 token，这些硬编码不会跟随 |
| 12 | 层级 | P1 | appbar 有 `--m-shadow-bar`（`mobile.css:53-54`），actionbar 也用它（`:472-473`）；当前值是 `0 1px 2px rgba(44,53,71,.08)`（`theme.css:34`）。顶栏本应只用 1px 边，操作栏本应向上 1px 投影 | Spec:260-269：顶栏 1px 边不投影；操作栏 `0 -1px 2px rgba(20,20,19,.06)`（`--mt-shadow-bar`，向上投影，与 L3 区分）；sheet L4 `0 -8px 32px rgba(20,20,19,.18)` | 当前 appbar 与 actionbar 共用向下 1px 的蓝黑阴影；操作栏方向/色值不对，顶栏不该有阴影 |
| 13 | 层级 | P2 | `.m-main` 最大宽 720（`mobile.css:146`） | Spec:216、234：单列内容最大宽 560，≥600 只增外边距 | ≥600 视口阅读行过长，偏离目标；不影响功能 |
| 14 | 组件几何 | P1 | `.ui-button` 移动覆盖 48 高、10×14 内边距、14px 字、10 圆角（`mobile.css:489`、`:481-488`）；quiet 仍用 `--ink` 文字（`workbench.css:117`）；danger 按下是 rose 底 + error 字（`:119`） | Spec:280-293：高 48、横内距 20、字 16/500、圆角 12；quiet 用 `--mt-accent-text`；danger 按下用 `--mt-danger-active #a92e2e` + `scale(.98)` | 高度达标，但字/内距/圆角/quiet 色四项不符；danger 按下也不是 `--mt-danger-active` |
| 15 | 组件几何 | P1 | 字段移动覆盖 48 高、10 圆角、16px 字（`mobile.css:492-501`）；label 14（`:504`）、help 12（`workbench.css:74`）；焦点只加全局 outline，边框不变（`workbench.css:15`、`:81`） | Spec:302-308：高 56、圆角 12、字 16；label 14；help 12；焦点边框转 focus + 2px 环 | 输入比目标矮 8px；焦点只靠外环，边框不改变 |
| 16 | 组件几何 | P1 | 卡片 padding 16/圆角 12（`mobile.css:203-210`）；报告卡 padding 14（`:417-438`）；候选行最小 48（`:481-488`、`:273-287`），issue 行 72（`:330-344`），上下文 summary 48（`MobileMaterialContext.vue:30`） | Spec:325-329：卡片圆角 16、padding 16/20；列表行 56；issue 72 达标 | 卡片/候选行偏紧，候选行比目标矮 8px |
| 17 | 组件几何 | P1 | 步骤条 `ol` padding 4（`mobile.css:94-101`）+ 按钮 48（`:103-110`），实际约 56；当前项背景+navy 数字（`:132-133`），完成项绿色（`:134-135`）+✓（`MobileApp.vue:235`） | Spec:215、334：导航 48；当前陶土文字+2px 下划线；完成 ✓ + muted；不可达 meta | 高度多约 8px；当前/完成态用藏青/绿色而非陶土+下划线 |
| 18 | 组件几何 | P1 | 操作栏 flex 同行，primary `flex: 1 1 auto`、非 primary `auto`（`mobile.css:466-478`）；导入、候选、进度运行/失败态都是次操作在左、主操作在右（`MobileApp.vue:330-341`） | Spec:217、335：主操作全宽 48，次操作文字按钮；只放主+一个次 | 有次操作时主操作没有占满，长文案/200% 时两按钮挤压，与目标操作栏结构不同 |
| 19 | 组件几何 | P2 | `UiSheet` 头部是标题后跟关闭（`UiSheet.vue:26-31`），全屏 detail 的关闭仍在右上 | Spec:347：全屏设置关闭在左上 | 全屏设置与 bottom sheet 的关闭位置没有区分 |

### 6.4 状态、无障碍

| # | 类别 | 级别 | 现状（证据） | 目标值 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 20 | 状态 | P1 | busy 只在按钮文字后追加「…」并 disabled（`UiButton.vue:4`），无 16px 旋转指示、无固定宽，宽度随文字变化 | Spec:290、296、379：文案不变 + 16px 指示 + `aria-busy`；宽度不跳 | 等待态可见性弱，长任务按钮会跳动 |
| 21 | 状态 | P1 | 两套状态标签：`StatusTag` 5 tone（`StatusTag.vue:1-3`；`workbench.css:121-125`，圆角 8、字 12、4×8 内边距、无固定高）；报告用 `.tag clear/review`（`App.vue:723`；`hierarchy.css:128-130`） | Spec:312-320：统一 StatusTag，高 24、padding 10、圆角 6、12/500，5 tone 文本+底 | 状态视觉不一致，报告与其他页不是同一组件 |
| 22 | 状态 | P1 | 空态：导入 h2 20 + 两个按钮（`MobileApp.vue:247-254`）；候选只给 field-help（`CandidatePage.vue:102`）；进度只给文案（`MobileApp.vue:314`）；报告未载入只给 notice（`:321`）。加载只有文本（`MobileApp.vue:257`、`:262`；`UiButton.vue:4`），无 skeleton（检索无命中） | Spec:358-359：空态 title-l 24 + body 16 + 一个 primary CTA；加载用暖砂 skeleton，静态不闪；暖砂只用于禁用/骨架/分区带（Spec:135） | 空态/加载没有统一层级；导入空态两个 CTA 与「一个 primary」不符；暖砂上的 caption/meta 不达标，不能拿来做骨架以外的文字底 |
| 23 | 状态 | P2 | 通知只有一种米色底 `--notice`（`mobile.css:357-364`），错误 `.m-error` 只有红字（`:394`），没有语义底/图标 | Spec:356：语义底 + 文本档 + 可选 20px 图标；错误 `role=alert` | 错误/通知/警告视觉区分弱（role 语义当前是对的） |
| 24 | 状态 | P2 | `UiSheet` 只有进入动画（`UiSheet.vue:41-48`、`:74-84`），关闭即时卸载；把手背景用 `--border`（`UiSheet.vue:51`）；验收记录写明退出 150ms 未实现（`issue144/round2/20261022.md:77`） | Spec:345、391：把手 36×4 用 `--mt-handle #d1cfc5`；exit 150ms，比进入快 | 关闭硬切；把手颜色也不是新的 `--mt-handle` |
| 25 | 状态 | P2 | 选中态用 navy：候选 `inset 3px 0 var(--navy)`（`mobile.css:280`）、tab 选中 surface（`:312-317`）、时间线当前 navy（`:408`）；状态层是 `--m-state-*` 的蓝黑 rgba(44,53,71,…)（`theme.css:30-32`） | Spec:334、378、383：选中 = 陶土文字 + 下划线/✓；状态层用 `--mt-state-hover/.press/.selected`（.06/.12/.08，暖黑） | 选中态仍是藏青；状态层颜色偏蓝，不是新暖黑 token |
| 26 | 无障碍 | P1 | 全局焦点 2px solid navy + offset 3（`workbench.css:15`）；移动断言只要求 width≥2、offset≥0（`verify-frontend-round2.cjs:442-443`），未校验颜色/offset | Spec:257：2px solid `#1f6fb2` + offset 2 | 焦点可见性通过，但焦点色与目标不符；脚本不会捕获此回归 |
| 27 | 无障碍 | P2 | CSS 中没有 `forced-colors`/`prefers-contrast` 规则（检索无命中） | Spec:408：forced-colors 下保留边界与焦点 | 高对比模式边界可能丢失，当前未验证 |

### 6.5 计数与实施含义

- P0：3 条（#1 颜色、#5 字体、#8 字号）。首三条也是这三条。
- P1：14 条（#2、#3、#6、#10、#12、#14、#15、#16、#17、#18、#20、#21、#22、#26）。
- P2：10 条（#4、#7、#9、#11、#13、#19、#23、#24、#25、#27）。
- 判断：P0 只解决「token 和排版语言」，界面仍会是 14px 藏青按钮 + 12px 卡片 + 20px 顶栏，不能称为 Claude 移动端。P1 的组件几何必须和 P0 同批完成，否则颜色换了但按钮/字段/步骤条/操作栏还是 Pioneer 几何。P2 可以在第一轮迁移后继续，但 #9（24 标题）、#11（硬编码圆角）、#19（全屏关闭位置）建议不要拖到最后一轮。
- 建议顺序（与 Spec:432-438 一致）：契约先行 → token 层加 `.mobile-workspace` 的 `--mt-*` 与共享组件语义别名 → 按钮/字段/标签/卡片/壳/sheet → 五个界面 → 无障碍与动效 → 验收截图。本文不执行。

## 7. 契约与验收影响面

### 7.1 为什么改规范会连带改这些文件

当前契约链是单向的：

```text
apps/web/src/theme.css
  → scripts/fixtures/pioneer-design.json（roles/body/heading/button/field/mobileButton）
  → scripts/lib/frontend-guards.cjs 的 assertDesign（读 CSS 变量 + 计算样式）
  → scripts/verify-frontend-flow.cjs（调用 assertDesign）
```

`assertDesign` 会逐个比较 `--canvas/--surface/...` 的 CSS 变量值（`frontend-guards.cjs:43-44`），再比较 body/heading/button/field 的字体、字号、圆角、最小高与颜色（`:45-51`）。规范 §11 已定案作用域化：`theme.css` 继续保留 Pioneer 变量服务桌面；`--mt-*` 只在 `.mobile-workspace` 作用域内声明；共享组件改消费 `--ui-*` 语义别名，桌面根映射 Pioneer、移动根映射 `--mt-*`（Spec:416-419、423）。因此直接把 `:root` 改成 Claude 会让 `acceptance:frontend` 失败；正确做法是保留桌面根值、另立移动契约与 `assertMobileDesign`。round2 脚本里硬编码的视觉值（serif 20px、`#fdfcfa`、scrim 色、sheet 0.2s）仍要逐条更新。

### 7.2 现存文件/脚本

| 文件 | 类型 | 为什么必须同步 | 处理原则（本文不修改） |
| --- | --- | --- | --- |
| `scripts/fixtures/pioneer-design.json` | 契约快照 | `roles` 14 色、body/heading/button/field 字号、`mobileButton`、`mobile` 段都在这里（`:3-15`）；`assertDesign` 直接读它 | 桌面根保持旧值；迁移期保留旧快照让桌面继续过；新增 `mobile-design.json` 后再决定退役。Spec:416-419、432 明确「不全局覆盖、不提前删断言」 |
| `scripts/lib/frontend-guards.cjs` | 断言库 | `assertDesign`（`:38-52`）、`assertMobileButtonContract`（`:32-36`）、负向反证（`:121-126`）都绑定旧值 | 先加 `assertMobileDesign` 读 `.mobile-workspace` 的 `--mt-*`；旧 `assertDesign` 继续断言桌面 Pioneer，保留到桌面正式退役 |
| `scripts/verify-frontend-flow.cjs` | Web 验收 | 第 `:19` 行调用 `assertDesign`；移动断言在 `:163-341`、200% 在 `:431-448`、reduced-motion 在 `:734` | 桌面冻结期间旧快照/旧断言保持不变；移动视觉断言拆到独立 guard/脚本，不拿移动值改旧 fixture |
| `scripts/verify-frontend-round2.cjs` | 移动壳验收 | 硬编码 `theme-color #fdfcfa`（`:342`）、appbar 色 `rgb(253,252,250)`（`:343`）、scrim `rgba(44,53,71,.42)`（`:262`）、标题 `Noto Serif SC` 20px（`:327-328`）、sheet 0.2s（`:541`） | 保留工程断言（48/16/100dvh/键盘/返回/焦点），把视觉值改为读新 token/快照 |
| `scripts/verify-mobile-flow.cjs` | 移动端到端 | 320/390/768、长文本、200%、48、16、键盘、coarse pointer（`:57-341`） | 行为断言可保留；若字号/圆角变化，更新截图与尺寸断言 |
| `scripts/verify-mobile-reading.cjs` | 报告阅读验收 | 报告摘要、材料行、设置、长文、320/768/200%（`:63-142`） | 增加 17/1.75 阅读字体、24 页面标题等断言；旧截图另存 |
| `scripts/verify-issue145-a11y.cjs` | 无障碍验收 | 对比度函数 `:51`、AI disclosure 对比度 `:218-219`、焦点/证据行为 `:223-259` | 新配色后重新计算阈值；焦点色/offset 加入断言 |
| `scripts/verify-issue146-motion.cjs` | 动效验收 | 绑定共享 `--motion-color`（`:143-151`）与 reduced-motion（`:282-308`）；sheet 的 200ms 进入由 round2 脚本断言（`verify-frontend-round2.cjs:541`） | 若旧 motion token 改名/别名，更新这些断言；退出动画补测 |
| `scripts/verify-round2-primitives.cjs` | 组件/token 原语 | 逐个断言 17 个 `--m-*` 值（`:68-88`）、pioneer 键（`:114-122`）、UiSheet DOM（`:159-170`） | 新增 `--mt-*` 断言；旧 `--m-*` 在别名期保留 |
| `apps/web/index.html` | 入口 | `theme-color #fdfcfa`（`:10`）跟顶栏走；目标 surface `#faf9f5` | 顶栏色确定后同步 meta；viewport 行 `:8` 不变 |
| `package.json` | 验收入口 | `acceptance:mobile`/`acceptance:reading`/`acceptance:motion`/`acceptance:frontend` 的清单在 `:16-23` | 若新增独立 `acceptance:mobile-design`，在此登记；否则把新 guard 接进现有入口 |
| `docs/design/frontend-round2-android-pioneer.md` | 设计合同 | 文件自己规定「修改必须同步更新实现差异」一节（`:5`、`:206-217`） | 追加「视觉层被 Claude 规范替换、工程约束不变」的记录，不倒改历史 |

> 本表不含 `apps/web/src/theme.css` 本身：它是实现落点，按 Spec §11 在 `.mobile-workspace` 内新增 `--mt-*`，不在契约文件清单里重复计数；桌面根变量保持旧值。

### 7.3 截图基线

| 目录 | 数量/记录 | 性质 | 处理原则 |
| --- | --- | --- | --- |
| `docs/acceptance/issue144/round2/` | 23 PNG + `mobile-round2-walkthrough.json` | round2 移动壳视觉基线（Chromium，mock bridge） | 新视觉需重拍；**不要覆盖**，新建目录并保留旧 SHA/记录 |
| `docs/acceptance/mobile-reading/` | 8 PNG + `verification.json` | 报告阅读/摘要/设置基线（Chromium，source SHA `e700c8389573`） | 报告排版/字号变了就重拍；旧图保留 |
| `docs/acceptance/issue144/evidence/` | 21 PNG + JSON | 第一轮响应式/触控/大字修复的历史证据 | 历史证据，不再作为新基线 |
| `docs/acceptance/issue136/evidence/final-package-00f9263/android/` | 11 PNG + `report.md` | 真实 Android 模拟器（MuMu）候选 APK 证据，但流程在启动分析时被 `UPLOAD_CONFLICT_REFRESH` 阻断 | 保留为「真机部分证据」；**不能**当作当前五屏或报告/设置的基线；不与 Chromium 图混用 |

合计 4 组、63 张 PNG。`issue136` 的记录明确：竖屏截图 11 张，上传/材料/候选可达，任务/报告未取得（`android/report.md:5-7`、`:198-205`）；最终包记录也把 Android 竖屏链路标为 PARTIAL/NOT_RUN（`final-package-20261022.md:51-57`）。

### 7.4 同批新增契约与待新增 fixture

| 文件 | 状态 | 原因 |
| --- | --- | --- |
| `scripts/fixtures/mobile-design.json` | 审计结束时仍不存在 | Spec:426、432 要求新增机器可读契约，承接 `--mt-*`、几何、状态；在它出现前，`assertDesign` 仍只能读旧 fixture |
| `docs/design/mobile-reset/mobile-design.tokens.json` | 已创建（21:55，19,447 B），未逐行复核 | Spec:426、475 的机器可读 token 契约；其中已声明 `--mt-*` 命名空间与颜色/字号/几何 |
| `docs/design/mobile-reset/token-map.md` | 已创建（21:59，31 KB），未逐行复核 | Spec:475 的旧 token → `--mt-*` 映射与迁移决策；含旧 `--canvas/--navy/--m-*` 的去向 |
| `docs/design/mobile-reset/contrast.mjs` | 已创建（21:55，6.4 KB），未运行 | Spec:476、550 的对比度核算脚本；属于工具，不是契约断言 |

影响面计数：**12 个现存文件 + 4 组 63 张截图 + 3 个同批新增文件（tokens、token-map、contrast）+ 1 个待新增 fixture**。同批还有 `spec-site.html`（21:58），是规范展示产物，不计入契约影响面。

## 8. 未覆盖与不确定项

### 8.1 只能靠真机/人工判断的项

- 真实 Android WebView/APK：当前没有「当前 HEAD 构建的 APK 五屏证据」。`issue136` 的候选 APK 只到候选页，任务/报告/设置未取得（`android/report.md:198-219`）。
- 真实 safe-area：刘海、挖孔、手势导航条的实际 inset；Chromium 的 `env()` 为 0，只验证了 meta 和 CSS 消费点（`issue144/round2/20261022.md:61`）。
- 真实软键盘 IME：`--keyboard-inset` 是注入 `visualViewport` 模拟的 460px（`verify-frontend-round2.cjs:687-704`），不是真实输入法；Gboard/搜狗/系统键盘的高度变化与 `interactive-widget` 支持未验证。
- 系统字体缩放/捏合缩放：200% 指根字号 CSS 放大，不等于 Android 系统字体缩放或页面缩放（`issue144/round2/20261022.md:62`；`issue144/20261021.md:86`）。
- TalkBack/读屏、硬件键盘 Tab 顺序、焦点环在真实屏幕的可见度：自动化只验证 DOM/焦点/颜色值，不等于读屏体验。
- 触控手感、滚动惯性、sheet 把手拖动关闭：把手目前是装饰性 `div`（`UiSheet.vue:25`），没有拖拽手势；是否需要拖动关闭未定义。
- 低亮度/强光下的对比度、字体实际渲染宽度（Anthropic Serif/Sans 不随包分发，实际回落 Georgia/Noto，Spec:458）。
- 视觉审阅：本审计**没有打开截图逐像素检查**，不能评价构图、密度、首屏遮挡、文字裁切或审美；这些需要独立视觉审阅代理或人工看新图。

### 8.2 本审计没做

- 没有修改 `apps/`、`scripts/`、`docs/` 其他文件；没有 `git add/commit/push`；没有联网；没有跑会改状态的构建或验收脚本。
- 没有跑 `npm run build`、`npm run acceptance:*`、`scripts/check.sh`；本文的「已验证」全部来自现有脚本源码与验收记录，不是本次重跑结果。
- 没有审查原生 Kotlin 插件、上传/模型/工作流的网络行为、Tauri 打包/签名、Docker/APK 扫描。
- 没有审查桌面工作台与移动 Web 的独立设计；`acceptance:frontend` 的桌面断言仍存在，但不在本次设计目标内。

### 8.3 快照与漂移风险

- 当前工作树是 `codex/issue145-native-busy-fix` 的脏树（`HEAD 017f031dbf84`），含其他会话未提交改动；本文行号以读取时为准，后续并行修改 `theme.css`/`mobile.css` 会使行号漂移。
- 现有截图的源码 SHA 早于当前 HEAD：round2 walkthrough 记录 `376d65813e9c`（`mobile-round2-walkthrough.json`），mobile-reading 记录 `e700c8389573`（`verification.json`），当前 HEAD 是 `017f031dbf84`。它们不是当前代码的成片，不能直接作为新视觉验收基线。
- `docs/design/frontend-design-spec-mobile.md` 是 v0.1 目标态，不是现状；标题层级已确认：报告页 24、bottom sheet 20、全屏设置整页 24，本文按此记录。
- `docs/design/mobile-reset/` 的同批产物在本轮并行任务中生成（21:55–22:10）：`mobile-design.tokens.json`、`token-map.md`、`contrast.mjs`、`spec-site.html`。本审计只读了 tokens JSON 头部、token-map 头部与 contrast.mjs 注释，未逐行复核；`scripts/fixtures/mobile-design.json` 仍未创建。

## 附录：证据索引

- 移动入口与流程：`apps/web/src/main.ts`、`apps/web/src/mobile/MobileApp.vue`、`flow.ts`、`bridge.ts`、`viewport.ts`、`mobile.css`。
- 组件：`UiButton.vue`、`UiField.vue`、`UiIcon.vue`、`UiSheet.vue`、`StatusTag.vue`、`MobileMaterialContext.vue`、`MobileReportSummary.vue`、`PolicyAssist.vue`、`EvidencePanel.vue`、`CandidatePage.vue`、`App.vue`。
- Token/桌面共享样式：`theme.css`、`workbench.css`、`hierarchy.css`、`style.css`。
- 契约/断言：`scripts/fixtures/pioneer-design.json`、`scripts/lib/frontend-guards.cjs`、`verify-frontend-flow.cjs`、`verify-frontend-round2.cjs`、`verify-mobile-flow.cjs`、`verify-mobile-reading.cjs`、`verify-issue145-a11y.cjs`、`verify-issue146-motion.cjs`、`verify-round2-primitives.cjs`。
- 壳/配置：`apps/mobile/src-tauri/tauri.conf.json`、`apps/mobile/README.md`、`apps/mobile/prepare-android.ps1`、`apps/web/index.html`、`package.json`。
- 验收记录：`docs/design/frontend-round2-android-pioneer.md`、`docs/acceptance/issue144/20261021.md`、`docs/acceptance/issue144/round2/20261022.md`、`docs/acceptance/mobile-reading/verification.json`、`docs/acceptance/frontend-round2/20261022.md`、`docs/acceptance/issue136/evidence/final-package-00f9263/android/report.md`、`docs/acceptance/issue136/final-package-20261022.md`。
- 截图计数：round2 23、issue144/evidence 21、mobile-reading 8、issue136/android 11；共 63 张，均未在本次审计中打开逐像素审查。

---

审计执行：mobile-auditor（灰泽满 / hzm），只读审计，写入范围仅本文件。
