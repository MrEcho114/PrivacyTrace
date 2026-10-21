# 前端打磨第二轮：Pioneer × 真实 Android 竖屏

状态：2026-10-21 第二轮设计合同。父票 [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)，子票 #142–#146。
基线与集成：`origin/main` `6e0122d1a84999de82c458f51c826248698c97dc`；集成分支 `codex/frontend-round2`。
本文件之后的修改必须同步更新「实现差异」一节；不得把未实现的条目写成已完成。

## 1. 为什么有第二轮

第一轮 A–E 解决的是「响应式 Web 在窄屏不溢出、可触控、焦点不丢」；它没有把 `MobileApp.vue` 变成 Android 应用界面。当前 390×844 实图（`docs/acceptance/issue144/evidence/after-*.png`）仍能看出：

- 顶部是 Web 品牌条（Logo + 用途 + 无返回/无标题层级），不是 Android 顶栏；
- 每一屏都重复一块巨大的「当前分析材料」面板，长 URL/哈希把首屏吃掉；
- 四步流程是 2×2 按钮网格，不是应用内的步骤/进度条；
- 主操作在超长页面最底部（候选页要滚过整张编辑表单），不是固定底部操作栏；
- 证据、政策全文、设置仍是桌面面板/整页内联；
- 触控目标 44px、按钮按下无 state layer、输入 14px（Android WebView 聚焦会放大）；
- 没有 Android 系统返回/滚动位置恢复；没有 edge-to-edge 与系统栏颜色。

因此第二轮不是换主题，而是把 **移动端 Tauri/Android 入口** 做成真正的 Android 应用外壳，同时保留 Pioneer 的颜色、字体、字号角色、圆角、状态语义与业务事实边界。

## 2. 设计决定（可执行）

### 2.1 安卓平台层（来源：Material 3 / Android 平台指引 / Emil mobile-native，见 §10）

| 决定 | 实现 |
| --- | --- |
| Android 触控目标 ≥48dp | 移动端按钮、列表行、标签页、图标按钮最小 `48px`；视觉图标 24px，用 padding 扩展命中区 |
| Edge-to-edge + 安全区 | `viewport-fit=cover`；`env(safe-area-inset-top/right/bottom/left)` 进入 app bar、内容、底栏、sheet；`theme-color` 匹配顶栏 |
| 系统返回可预测 | 步骤页有返回箭头；Android 返回键/`popstate` 返回上一步并恢复滚动与焦点；根步骤才交给系统退出 |
| 顶栏 | 56px + safe-top；左返回、标题（Pioneer 衬线 20px）、右侧设置图标按钮；滚动时吸顶 |
| 底部操作栏 | 固定 + safe-bottom；主操作全宽 48px；次操作文字按钮；键盘打开时随 `--keyboard-inset` 上移 |
| 触控反馈 | 按下 state layer + `scale(.98)`（按钮）/行背景变化；只在 `(hover:hover) and (pointer:fine)` 启用 hover；`touch-action: manipulation`；去掉 tap highlight |
| 输入不缩放 | 移动端 `input/textarea/select` 字号 ≥16px；不禁止用户缩放 |
| 滚动/高度 | app shell 用 `100dvh`；`overscroll-behavior: none`；内容底部留出 action bar + safe-area 的空间 |
| 弹层 | 证据/政策 = bottom sheet（Reka Dialog 行为）；设置 = 全屏 page-like dialog；均有明确关闭、Esc、焦点返回、滚动锁定 |
| 列表/卡片 | 16px 边距、12px 卡片圆角、8px 节奏；点击行整行可点，右侧 chevron；不用桌面 hover 当反馈 |

### 2.2 Pioneer 视觉合同（不变）

画布 `#F6F5F1`、正文面 `#FDFCFA`、正文 `#2C3547`、辅助 `#64696F`、主操作 `#333C50`、分隔 `#D9D7D2`、控件边框 `#858D92`、薄荷 `#DCE9DF`；衬线标题/无衬线正文/等宽代码/哈希；UNKNOWN、PARTIAL、UNREVIEWED、附件未检查语义不升级。桌面宽屏层级仍归 B；本轮不新增插画、纹理、庆祝、桌宠或第二套视觉。

## 3. Token 与组件合同（A #142）

唯一变量文件仍是 `apps/web/src/theme.css`。新增（名称固定，C/D/E 消费）：

```css
/* Android portrait shell */
--m-touch: 48px;
--m-appbar-height: 56px;
--m-actionbar-min-height: 64px;
--m-gutter: 16px;
--m-card-radius: 12px;
--m-sheet-radius: 20px;
--m-font-title: 1.25rem;    /* 20px */
--m-font-section: 1rem;     /* 16px */
--m-body: 0.875rem;         /* 14px，阅读区可用 15px */
--m-caption: 0.75rem;       /* 12px */
--m-line-body: 1.65;
--m-state-hover: rgba(44, 53, 71, .06);
--m-state-press: rgba(44, 53, 71, .12);
--m-state-selected: rgba(51, 60, 80, .08);
--m-scrim: rgba(44, 53, 71, .42);
--m-shadow-bar: 0 1px 2px rgba(44, 53, 71, .08);
--m-shadow-sheet: 0 -8px 32px rgba(44, 53, 71, .18);
```

E 在 A 之后新增动效 token（同一文件）：
`--m-duration-press: 120ms; --m-duration-enter: 200ms; --m-duration-exit: 150ms; --m-ease-standard: cubic-bezier(.2, 0, 0, 1); --m-ease-decelerate: cubic-bezier(0, 0, 0, 1);`

组件：
- `UiSheet.vue`（新增，Reka UI 2.11.0 Dialog 家族，MIT）：props `title`、`description?`、`initialFocus?`；slot `default`、`close`；事件 `close`。DOM 类：`ui-sheet-overlay`、`ui-sheet`、`ui-sheet-handle`、`ui-sheet-head`、`ui-sheet-body`、`ui-sheet-close`。默认 bottom sheet（`max-height: min(88dvh, 720px)`），`detail` 变体可用于全屏证据页；内部滚动 `overscroll-behavior: contain`。不得复制 Reka 源码，不新增渲染库。
- `UiIcon.vue` 增加 `back`、`close`、`settings`、`chevron-right`、`refresh`、`check`，统一 24px、`stroke-width=1.5`、`currentColor`、`aria-hidden`。
- `pioneer-design.json` 增加 `mobile` 段：`touchTarget: 48`、`appBarHeight: 56`、`actionBarMinHeight: 64`、`inputFontSize: 16`、`sheetRadius: 20`；保留既有键，以免既有断言失效。设计文档记录来源与差异。
- 不新增全局 CSS reset、不引入第二套主题、不改 `main.ts` 导入顺序。

A 的交付：token 映射表、UiSheet/UiIcon 源码、定向 `scripts/verify-frontend-round2.cjs` 中可复用的设计断言、390/1440 组件截图、NOT_RUN。A 不重写 `App.vue`/`workbench.css`/`MobileApp.vue`。

## 4. 移动应用外壳（C #144）

### 4.1 结构（`MobileApp.vue` + 新 `apps/web/src/mobile/mobile.css`）

```text
.mobile-workspace
  a.skip-link
  header.m-appbar        ← 返回 | h1#page-title | 设置
  nav.m-steps            ← 4 步：已完成/当前/未来（未来禁用）
  main#workspace-content.m-main
    .m-context           ← 仅候选/进度/报告：应用名 + 版本 + 「更换」；不重复大面板
    <step content>
  footer.m-actionbar     ← 主操作 + 次操作（按步骤）
  <UiSheet> 证据/政策（见 4.4）
```

- 标题：import「应用与政策」、candidates「检查政策候选」、progress「分析进度」、report「对照报告」；`h1` 可 `tabindex=-1` 供焦点落点。
- 返回：`step !== 'import'` 时显示；候选→import、进度→candidates、报告→progress（或回 import？按现有 `state.maxStep` 与业务不倒退；报告返回 progress 保留报告可回看）。返回按钮与系统返回都调用同一 `goStep()`，由它保存/恢复滚动位置并把焦点落到 `h1`。
- 步骤条：4 段紧凑横向；`aria-current="step"`；已完成/当前/未来文字可见；未来 `disabled`；320px 不换行成 2 行（可横向省略标签，保留编号+短标签）。
- 材料上下文：import 显示完整「当前分析材料」卡；其他步骤只显示一行上下文（应用名、版本、origin 可展开），不再渲染大面板。现有 `MaterialContext`（B 票）优先复用。
- 底部操作栏：
  - import：主「自动准备政策并继续」；次「重新读取材料」（有 context 时）/禁用。
  - candidates：主「保存候选并开始分析」；次「修改材料」（等价现有 back）。
  - progress：成功主「查看报告」，否则主「刷新进度」；次「取消分析」/终态「重试为新的分析」。
  - report：不显示固定操作栏；报告内操作保留。
  - 按钮必须复用 `UiButton`，不得复制业务函数；`busy` 时主按钮 busy。
- 隐藏各页原有 `.flow-footer` 的移动端呈现（仅移动外壳中 `display:none`），避免双主操作；`CandidatePage` 的编辑表单内「保存候选」仍保留。
- 页面标题不再在内容区重复；import 的说明保留为一条 lead 文案。

### 4.2 候选页

- 保留现有候选列表与编辑逻辑；列表行 ≥48px、选中 state layer、右侧 chevron；「添加候选」为文字按钮。
- 移动端分段标签（政策原文/候选声明）视觉改成 Android segmented control，保留现有 roving tabindex/aria。
- 编辑表单字段 16px、label 在上、错误贴近字段；保存/删除按钮 48px；不新增确认弹窗（删除候选已有即时行为，维持）。
- 编辑区很长时，底部主操作栏仍可达；键盘打开时不被遮住。

### 4.3 导入/进度/报告

- 导入：政策来源卡改为可折叠行（title + 状态 + 展开正文），状态标签使用 `StatusTag`；模型设置入口保留 details，但触发按钮 48px。
- 进度：阶段列表为 Android 时间线（左侧圆点/线，当前阶段高亮）；状态文本 `role=status`，失败 `role=alert`。
- 报告：复用 `App.vue` 报告内容；移动端把 `.sample-card`、`.metrics`、`.report-section`、`.coverage-card` 等重排为 16px/12px 卡片；证据行改为整行按钮 + chevron；`details` 成为列表行。
- 报告顶部来源切换/刷新迁移到 app bar 或上下文行，不新增功能。

### 4.4 证据 bottom sheet（复用与边界）

- 把 `App.vue` 中现有 `#evidence-panel` 抽取为 `components/EvidencePanel.vue`（props：`issue`、`report`、`taxonomy`、`statusLabels`、`kindLabels`、`sourceLabels`；事件：`close`、`open-policy`）。桌面仍内联渲染；移动端由 `MobileApp`/`App.vue` 传入 `sheet` 模式，包在 `UiSheet` 内。
- sheet 内容/逻辑必须与桌面完全一致：解释、证据卡、原句前置/后置、候选条款分页、完整政策跳转。不得复制或遗漏 UNKNOWN/PARTIAL/UNREVIEWED 文案。
- 打开时阻止背景滚动、焦点进入 sheet；关闭/Esc/返回键恢复触发按钮与滚动位置；「完整政策」跳转先关闭 sheet，再定位到政策块（现有 `openPolicy`）。
- 设置：`UiDialog` 在移动端呈现为全屏 page-like（顶栏「服务与存储设置」+ 关闭），保留 Reka 焦点循环；不改成第二套表单。

### 4.5 平台层（C + E 边界）

- `index.html`：`viewport-fit=cover, interactive-widget=resizes-content`；`theme-color` 与顶栏一致；不禁止缩放。
- `mobile.css` 统一 `-webkit-tap-highlight-color: transparent`、`touch-action: manipulation`、`user-select` 仅控件、`overscroll-behavior`、16px 输入、`@media (hover:hover) and (pointer:fine)` 门控；不把 `user-select:none` 放 body。
- `viewport.ts` 已有 soft-keyboard inset；C 把它接到 action bar / sheet 底部，不得新增第二套监听。
- 滚动位置：每个 step 记录 `scrollY`；返回/前进恢复；数据轮询原地更新不重置位置（D 验证）。

## 5. 无障碍（D #145）

在 C 的 shell 上补齐，不改视觉方向：
- app bar `header` + `h1`；返回/设置按钮 `aria-label`；设置按钮 `aria-haspopup="dialog"`。
- 步骤 `nav[aria-label]`，当前 `aria-current="step"`，禁用未来步骤；状态变化不重复播报。
- 主内容 `main#workspace-content`；skip link 跳到这里；焦点落点不被 sticky bar 遮挡（`scroll-margin`）。
- 底部操作栏 `footer[role=group][aria-label]`；按钮可访问名称来自可见文字；busy/disabled 语义正确；不嵌入 live region。
- 证据 sheet：`role=dialog`、`aria-modal=true`、`aria-labelledby`/`aria-describedby`；焦点陷阱由 Reka；打开聚焦标题/关闭；关闭返回触发按钮；Esc/返回键关闭；背景 `aria-hidden`/inert；滚动锁定。
- 候选 tabs、details/summary、分页、删除确认、字段错误关联、`role=status`/`alert` 的 D 票既有结论全部保留并回归。
- 键盘：Tab 顺序符合视觉；焦点环 3px navy 不被裁切；200% 字体下无横向滚动；硬件键盘可完成主路径。
- 读屏顺序：app bar → 步骤 → 内容标题/上下文 → 内容 → 操作栏；所有图标装饰性 `aria-hidden`。
- 验证：扩展现有 `scripts/verify-issue145-a11y.cjs`（AX tree、focus、Esc、背景 aria-hidden、返回焦点、live region 不嵌套按钮），并新增 390×844 证据。

## 6. 动效（E #146）

- 复用现有 CSS/Vue Transition，不引入动效库；只对 `transform`/`opacity`/`background-color` 做过渡，禁止 `transition: all`。
- 定义并使用 A 之后新增的 motion token；按下 120ms、sheet 进入 200ms/退出 150ms、步骤切换 160ms（透明度 + 4px 位移）。
- 状态层按压反馈不是唯一反馈：颜色/图标/文字同时变化；高频操作不做自定义动画。
- `prefers-reduced-motion: reduce`：所有过渡/关键帧立即完成，`scroll-behavior:auto`，JS 平滑滚动改为 `auto`；sheet 无位移。
- 数据轮询/原地更新不因动画重新挂载、不抢焦点、不延迟操作；长文本/后台恢复/低性能下不遮挡。
- 扩展 `scripts/verify-issue146-motion.cjs`，保留 17 项与两条反证。

## 7. 桌面（B #143）

- 以 `origin/codex/issue143-workbench-hierarchy` `40247ba` 为来源，rebase 到当前 main；保留 `hierarchy.css`、`MaterialContext.vue` 与 1920/1440/1280 证据。
- 只改宽屏层级/密度/信息重复；不接管移动布局、焦点、动效。
- 复用 A 的 token；桌面上不应用 48px 移动触控规则（保持 36px 按钮契约）。
- `MaterialContext` 作为 C 的可复用组件；C 消费其接口，不复制。
- 复跑 `node scripts/verify-issue143-hierarchy.cjs`、`npm run acceptance:frontend` 与 1440/1920 截图。

## 8. 文件归属与整合顺序

| 范围 | 唯一 owner | 文件 |
| --- | --- | --- |
| token/UiSheet/UiIcon/契约 | A | `theme.css`、`components/UiSheet.vue`、`components/UiIcon.vue`、`scripts/fixtures/pioneer-design.json`、`docs/design/issue142*` |
| 桌面层级 | B | `hierarchy.css`、`components/MaterialContext.vue`、`pages/*` 桌面部分、`App.vue` 桌面部分、`docs/design/issue143*` |
| 移动外壳/证据抽取 | C | `mobile/MobileApp.vue`、`mobile/mobile.css`、`mobile/viewport.ts`、`components/EvidencePanel.vue`、`App.vue` 移动部分、`pages/CandidatePage.vue` 移动部分、`index.html`、`docs/acceptance/issue144*` |
| 语义/焦点 | D | `App.vue` 语义、`MobileApp.vue` aria、`pages/*` a11y、`scripts/verify-issue145-a11y.cjs`、`docs/acceptance/issue145*` |
| 动效 | E | `theme.css` motion token、`mobile.css`/`workbench.css`/`style.css` 动效规则、`App.vue` 滚动、`scripts/verify-issue146-motion.cjs` |

整合顺序：**A → B → C → D → E**。后整合者必须基于 `codex/frontend-round2` 最新树重跑受影响检查；同一文件同一时刻只允许一个 owner 写入。任何跨 owner 的接口变更先在 `codex/frontend-round2` 的交接评论/本文件登记。

分支：A `codex/issue142-round2`、B `codex/issue143-round2`、C `codex/issue144-round2`、D `codex/issue145-round2`、E `codex/issue146-round2`；全部从 `codex/frontend-round2` 切出，完成后由 Lead 串行合并。最终唯一交付入口是 `codex/frontend-round2` 的 PR（吸收旧 #152/#154/#156 的取舍）。

## 9. 验证与证据矩阵

必须运行：
1. `node scripts/verify-frontend-round2.cjs`（新增；C/D 共同维护）：390×844 全流程、320×568、768×1024、844×390 横屏、200% 字号、键盘、硬件返回、evidence sheet 焦点、无横向溢出、48px 命中、16px 输入、reduced-motion。
2. 既有 `npm run acceptance:frontend`、`npm run acceptance:mobile`、`npm run acceptance:motion`（E 提供）、`node scripts/verify-issue145-a11y.cjs`、`node scripts/verify-issue143-hierarchy.cjs`。
3. 权威 `bash scripts/check.sh`（Git Bash）或 `powershell -NoProfile -File scripts/check.ps1`；修复本次引入失败，保留历史失败。
4. 截图：`docs/acceptance/frontend-round2/`；每张图注明平台、视口、场景、状态、fixture/mock/离线、采集时间、源码 SHA；Android 真机/模拟器 `NOT_RUN`（本机无 adb/emulator/SDK），不以 Chromium 390 冒充。
5. 桌面 1920×1080、1440×900、1280×720 归 B；移动 390×844 优先，320/768/横屏为边界；200% 字号与 reduced-motion 至少各一组。
6. 性能/体积：记录 CSS/JS 产物前后大小（`npm run build` 输出），不引入新运行时库；依赖无变化。

## 10. 技能与来源（固定版本，边界如实）

- 本地 `ui-ux-pro-max`（`C:\Users\Oasis\.agents\skills\ui-ux-pro-max`）：`--domain web` 的 Android 触控/返回/模态规则；只作建议，不覆盖 Pioneer。
- [Emil Kowalski `mobile-native`](https://github.com/emilkowalski/skills/blob/0b85d4b36ad772ed2c46a66522ede1c8a26f9929/skills/mobile-native/SKILL.md)（MIT）：平台层 CSS/meta、hover 门控、safe-area、输入缩放、tap feedback；本轮作为平台层检查清单，不安装、不引入依赖。固定到添加该 skill 的提交 `0b85d4b36ad772ed2c46a66522ede1c8a26f9929`。
- [Emil `animate` / `review-animations`](https://github.com/emilkowalski/skills/blob/85e8e2363b713506e1d5b6e07a0eb2da66be1bc3/skills/animate/SKILL.md)（MIT）：E 沿用 #146 已固定版本。
- [Material 3 / Android 平台指引](https://developer.android.com/develop/ui/compose/system/material-insets)：edge-to-edge、系统栏 insets、返回、48dp；只引用公开规范，不复制素材。
- [Reka UI Dialog](https://reka-ui.com/docs/components/dialog)（MIT，2.11.0）：sheet/模态行为；不复制源码。
- Pioneer 设计来源与 token 映射见 `docs/design/issue142-theme-and-primitives.md` 与 `docs/design/issue-44-provenance.md`；不复制 Figma 图像/业务。

## 11. 非目标与 NOT_RUN

- 不新增业务流程、API、生成契约、规则判定、凭证桥接、账号/存储中心、Dashboard。
- 不做主题探索、插画、角色、视频、动画库、第二套组件库、全站换库。
- 不合并/部署/发布；不把浏览器模拟写成 Android APK 实机通过。
- 本轮 `NOT_RUN`：真实 Android 真机/模拟器（本机无 adb/emulator/Android SDK）、真实软键盘 IME、系统级字体缩放/捏合、真实读屏、真实模型/Docker、Tauri APK 构建。
- 证据边界不变：权限是能力、invoke 是静态潜在线索、政策是声明；UNKNOWN/PARTIAL/UNREVIEWED/附件未检查持续可见。

## 12. 实现差异记录（每次提交追加）

- 2026-10-21：合同建立；A/B/C 并行，D/E 待外部会话结束后由 Lead 接手。
- 2026-10-21 A（`1c031c9`，合并 `b4d39e8`）：新增 §3 的 17 个 `--m-*` token、`UiSheet.vue`（Reka Dialog，bottom/detail）、6 个图标、`pioneer-design.json.mobile`、`verify-round2-primitives.cjs`（15/15）与 390/1440 组件证据。类型检查/构建/111 单测通过；产品入口尚未消费（由 C 接入）。差异：`UiIcon` 视觉尺寸统一为 24px（后续以桌面验收确认导航图标密度）。
- 2026-10-21 B（`937daf6`，合并 `b995fa0`）：吸收第一轮 `hierarchy.css`/`MaterialContext.vue`，补第二轮桌面守卫与 1280/1440/1920 证据；`verify-issue143-hierarchy.cjs` 在整合树 10/10。桌面按钮仍 36px，无移动触控规则泄漏。
- 2026-10-21 C（`67999c6`，合并 `9d9ee20`）：`MobileApp.vue` 重写为 Android 外壳（56px 顶栏/返回/标题/设置、单行四步条、紧凑材料行、固定 64px 操作栏、100dvh/safe-area/`--keyboard-inset`、48px/16px、state layer、hover 门控、硬件返回与逐步滚动恢复），抽出 `EvidencePanel.vue`，移动证据进 A 的 `UiSheet`，设置用 `detail` 全屏；`verify-frontend-round2.cjs` 20 组 + 23 图。与 B 的桌面层级回归双向复跑。
- 2026-10-21 E（外部 head `c1a11f8`，合并 `f7867db` + `3a14031`）：并入第一轮 motion/hover/reduced-motion；新增 `--m-duration-*`/easing token、`UiSheet` 200ms 进入、步骤 160ms 进入、按钮/候选行 120–150ms；`prefers-reduced-motion` 全部即时。sheet 退出为即时卸载（未实现 150ms exit），已写入 #146 round-2 记录。
- 2026-10-21 D（外部 PR #158 head `5f12bcf`，合并 `79f45d7`）：并入第一轮原地刷新/焦点/live region/对比度；在 C 外壳上复核顶栏 h1/返回设置名称、步骤 `aria-current`、操作栏 group、忙提示文本与停止按钮分离、证据 sheet 的 `dialog`/`aria-modal`/labelledby/describedby、scrim/Esc/返回关闭与焦点返回；`verify-issue145-a11y.cjs` 14 项桌面回归 + round-2 脚本新增移动语义断言。
- 2026-10-22 整合次序实际为 A → B → C → E → D（E 先于 D 合并；D 只增加语义，不改视觉，重跑全部脚本通过）。第二轮最终唯一交付入口是 `codex/frontend-round2` 的 PR；旧 #152/#154/#156/#158 作为来源记录，不并行实现第二套。
- 2026-10-22 交付：集成 PR [#160](https://github.com/MrEcho114/PrivacyTrace/pull/160)（head `25ab23e`）；A–E 汇总与证据见 `docs/acceptance/frontend-round2/20261022.md`。\n- 2026-10-22 视觉复验修正：程序化聚焦 h1 不再画控件式焦点环；候选来源元信息在移动端用 `·` 节奏，不再糊成一行；sheet 进入动效纳入 reduced-motion；桌面来源面板不再重复来源标题（B 的层级守卫）。
