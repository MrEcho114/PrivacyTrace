# Issue #146 · 复用动效技能，校准现有微交互与减少动态效果

来源任务：[子票 #146](https://github.com/MrEcho114/PrivacyTrace/issues/146)，父规格 [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)。实现基线 `origin/main` `0ad5f565dc6f414ac2b9c35661296dc9352e3fef`（建分支时）。当前执行记录见 [Issue 评论](https://github.com/MrEcho114/PrivacyTrace/issues/146)。

本票在现有工作台上做一次有边界的动效校准：**没有新增页面、没有新增业务状态、没有引入动效运行库**。改动集中在 `apps/web/src/theme.css`、`workbench.css`、`style.css` 与 `App.vue` 的一处滚动调用，另加一个定向浏览器验收脚本。

## 授权、范围与共享边界

- 本票负责：动效机制、时长、性能属性、减少动态效果实现。
- 不属于本票：状态可感知语义、键盘导航与焦点样式（D / #145）；Pioneer 颜色与字体变量、基础组件接口（A / #142）；宽屏层级（B / #143）；窄屏触控与软键盘（C / #144）。
- 共享文件：`workbench.css`、`style.css` 由各票共用。本票只改「动效、hover 能力门控、减少动态效果」四类规则，不调整布局、层级、字号与颜色角色。
- 与 [#154（#144 移动打磨）](https://github.com/MrEcho114/PrivacyTrace/pull/154) 在 `workbench.css`/`style.css` 有文件交集。两者改动位置不重叠；按父票约定，**后整合的一方吸收最新 main**，本票不修改 #144 的触控、字号与面板切换规则。

## 变更前的动效盘点

只在真实浏览器里读取计算样式与事件行为，不依据样式表文本推断。

| # | 位置 | 触发 | 目的 | 变更前参数 | 减少动效行为 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `.ui-button`、`.nav-item`、`.source-tabs button`、`.candidate-item` 的颜色过渡 | hover / 按下 / 选中 | 反馈 | `background-color, border-color 150ms ease-out` | 被全局 `transition: none !important` 关闭 | 修改：合并为 `button` 上的一条规则并改用 token |
| 2 | `button:hover`（`style.css`、`workbench.css` 各一条）、`.ui-button.primary/quiet/danger:hover`、`.primary:hover` | 指针悬停 | 反馈 | 无门控，触摸设备同样命中 | 无 | 修改：整体包进 `@media (hover: hover) and (pointer: fine)` |
| 3 | `.ui-button:active:not(:disabled)` | 按下 | 按压反馈 | `translateY(1px)`，无过渡 | 不受影响（瞬时） | 保留：按下必须与指针事件同帧，不做缓动 |
| 4 | `.drag-active` | dragover / dragleave | 状态指示 | `border: 2px solid`，相对常态 `1px dashed` 改变边框宽度 | 无过渡，但回流仍发生 | 修改：改为 `border-color` + `inset box-shadow`，消除 1px 回流 |
| 5 | `.comparison-table td.row-evidence` | 窄屏展开证据 | 状态 + 空间变化 | `animation: evidence-slide-in .18s ease-out`（`opacity 0→1`、`translateY(-4px→0)`） | 被全局关闭 | 删除 |
| 6 | `@keyframes evidence-slide-in` | 同上 | 同上 | 同上 | 同上 | 删除（无引用） |
| 7 | `App.vue` `selectIssue()` | 点开对照结论 | 空间变化：把证据面板带入视野 | `scrollIntoView({behavior:'smooth'})` | **未生效**：显式 `behavior: 'smooth'` 不受 CSS `scroll-behavior: auto !important` 约束 | 修改：`prefers-reduced-motion` 时改用 `behavior: 'auto'` |
| 8 | `@media (prefers-reduced-motion: reduce)` 全局规则 | 用户偏好 | 无障碍 | `scroll-behavior:auto`、`animation:none`、`transition:none` 全部 `!important` | — | 保留（补注释说明为什么是「立即」而不是「更轻」） |
| 9 | `.skip-link:focus` | 键盘 Tab | 跳过链接可见性 | `opacity 0→1`，无过渡 | 无关 | 保留：焦点可见性不得延迟 |
| 10 | 设置弹窗（`UiDialog`）出现 | 显式打开 | — | 无入场动效，同帧可读 | 无关 | 保留：见下方决策 |

变更前的实测（Chromium，1440×900 与 390×844）：

- 触摸指针（`hasTouch`、`isMobile`）下 `matchMedia('(hover: hover) and (pointer: fine)')` 为 `false`，但 `page.hover()` 仍把按钮背景从 `rgba(0,0,0,0)` 改成 `rgb(238,237,234)` —— 触摸设备上的粘滞高亮确认存在。
- `.drag-active` 让拖拽区高度 `244px → 246px`、内部标签 `top` 下移 `1px` —— 布局跳动确认存在。
- 窄屏展开行时计算样式为 `animationName: evidence-slide-in`、`opacity: 0`、`transform: translateY(-4px)`，逐帧 `opacity` 从 0 递增 —— 内容在入场阶段不可读。
- `prefers-reduced-motion: reduce` 下 `scrollIntoView` 收到的仍然是 `behavior: 'smooth'`，滚动值与普通模式一致。

## 决策与理由

**删除窄屏证据行的入场关键帧。** 理由按优先级：

1. 同一动作在「已有报告」视图与宽屏示例报告里本来就是即时出现，只有窄屏示例报告有 180ms 位移入场 —— 这是本票要修的「节奏不一致」。
2. 它让用户主动要求阅读的证据在最初几帧 `opacity: 0`，与「业务结论不等待动画完成才可读」冲突；低性能设备上这段不可读时间会被放大。
3. 关键帧在反复开关时从零重放，不能从当前状态中断；展开/收起是用户可连点的动作。
4. 删除后减少动态效果模式的表现完全不变（该动画本来就被关闭），没有把差异转嫁给无障碍用户。

**不为证据面板或设置弹窗新增入场动效。** 两者都是显式打开、内容即事实的界面。Emil animate 技能的频率门要求「键盘触发或每天上百次的动作不动画」，而证据阅读属于「数据不应为了风格而移动」。本票把动效预算留在反馈上，不新增视觉方向。

**减少动态效果模式取「立即」而不是「更轻」。** 技能建议保留透明度/颜色过渡、只去掉位移。本项目 #146 明确要求「关闭位移/弹性和非必要动画，允许立即显现」，且一张全局 `transition: none !important` 更容易证明「没有任何状态等待动画」。差异记录在此，不假称两者等价。

**颜色反馈用 `ease` 而不是自定义强 `ease-out`。** 150ms 的颜色渐变没有可感知的加减速起点，自定义曲线在 150ms 内与 `ease` 无可见差异，增加 token 只会制造第二套词汇。

## 实施取值与理由

Figma 的 Pioneer 当前页与规范页没有给出动效数值（父票盘点只登记了颜色、字体、间距、圆角）。下表是本票的实现取值，**不是从源设计抄来的参数**。

| token | 值 | 用于 | 理由 |
| --- | --- | --- | --- |
| `--motion-color` | `150ms` | 所有按钮的颜色/边框反馈 | 落在技能给出的按压/小控件区间（100–160ms）内，保留变更前的既有节奏，避免无依据改速 |
| `--ease-color` | `ease` | 同上 | 颜色变化用默认缓动；无需自定义曲线（见上） |

新增变量放在 `theme.css` —— 仓库唯一的变量来源，`style.css` 与 `workbench.css` 只消费。没有第二套 `motion-*` 体系。

## 复用来源与许可

| 来源 | 固定版本 | 许可 | 用法与边界 |
| --- | --- | --- | --- |
| [Emil `animate` SKILL](https://github.com/emilkowalski/skills/blob/main/skills/animate/SKILL.md) | 文件提交 `85e8e2363b713506e1d5b6e07a0eb2da66be1bc3`（仓库 HEAD `2d228630ba1446365f614a108cb8252f1feda202`，2026-10-21 读取） | MIT | 采用：频率门、hover 指针门控、减少动效随动效一起发布、禁止 `transition: all`、300ms 预算、按压反馈即时。未采用：spring / Motion 运行库（无手势与弹性需求）、`@starting-style`（本票不加入场动效） |
| [Emil `review-animations` SKILL](https://github.com/emilkowalski/skills/blob/main/skills/review-animations/SKILL.md) | 同上仓库快照 | MIT | 用于十条非协商标准自检；其中「减少动效保留透明度过渡」与 #146「允许立即显现」冲突，按项目规范取立即显现，差异已在上一节记录 |
| [Vue Transition](https://vuejs.org/guide/built-ins/transition.html) | 文档，未引入依赖 | — | 未使用：本票没有新增过渡需求，现有 CSS transition 足够 |
| [Motion for Vue](https://motion.dev/docs/vue) | 未安装 | MIT | 未评估安装：本票没有手势、布局动画或可中断的连续运动，引入运行库无收益 |
| [onetake](https://github.com/feitangyuan/onetake) | 未安装 | PolyForm Noncommercial 1.0.0 | 仅记录为视频方向参考；本票不安装、不制作视频、不把其渲染流水线用作 UI 运行时 |

技能来源在仓库外读取，只落地适用于本项目的规则；没有安装技能、没有新增依赖、锁文件未变。

## 验证

- 定向脚本：`node scripts/verify-issue146-motion.cjs`（`npm run acceptance:motion`），17 项检查覆盖指针能力、按压即时性、拖拽零回流、弹窗即时可读、`transition: all` / 300ms 预算、触摸粘滞 hover、普通与减少动效两种模式的滚动行为、9 次连续开关、6× CPU 节流、可见性往返、窄屏证据行。脚本内有两条「守卫反证」：注入 `transition: all 400ms` 与无门控 hover 后，对应断言必须失败。
- 权威入口：`pwsh -NoProfile -File scripts/check.ps1`。
- 证据与原始结果：`docs/acceptance/issue146/`。
- 未运行/不互代：真实触屏设备上的 hover 表现（用 `hasTouch` 模拟）、操作系统级「减少动态效果」开关（用 `emulateMedia`）、真实后台挂起（用 DOM 可见性事件模拟）、真机 Tauri WebView、真机低性能（用 CDP 6× 节流）。以上均记为 NOT_RUN，不写成通过。
