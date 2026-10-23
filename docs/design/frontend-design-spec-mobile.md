# PrivacyTrace 移动端设计规范 · Claude 基线

- 状态：v0.1 规范重置（2026-10-23）；同日完成移动端迁移落地（代码已改，记录见 [implementation-20261023.md](mobile-reset/implementation-20261023.md)）
- 客户端范围：以 [ADR-0004（客户端 = Android App）](../adr/0004-client-is-android-app.md) 为准；本规范只覆盖 Android/Tauri 移动 App，桌面 Web 冻结并保留历史来源，退役条件见 [ADR-0005](../adr/0005-frontend-contract-retirement.md)。
- 适用：**仅移动端 App** —— Android/Tauri 壳（`apps/mobile/`）、移动界面（`apps/web/src/mobile/`），以及移动报告复用的共享呈现（`App.vue` 的 mobile 分支、`CandidatePage.vue`、`components/`、`theme.css` 的移动根语义别名）
- 不在范围：桌面 Web 工作台、移动 Web 的独立设计、`apps/api` 后端（由隔壁会话负责）
- 设计基线：Claude 设计体系（EAC 库条目 `od-ds-claude`），OpenDesign 打包（v0.25.1），MIT；源文件在 EAC 设计库，不在本仓库
- 版式参考：移动应用模板（EAC 库条目 `od-mobile-app`），MIT；只借手机框与单屏叙事，不搬示例内容
- 前序草案：[Apple 基线草案（已被本规范替代）](archive/frontend-design-spec-apple-superseded-20261023.md)
- 配套产物：现状审计、token 契约与对比度核算、规范站（本轮同批交付，链接见 §15）

## 0. 一句话

App 退到证据后面：暖纸画布、单一陶土强调、衬线只讲内容、无衬线只做操作；一层 1px 细线和表面差分层，颜色只承担事实语义。

## 1. 范围收窄与边界

### 1.1 这次重置改变了什么

| 维度 | 之前（Pioneer / round2 / Apple 草案） | 现在（本规范） |
| --- | --- | --- |
| 前端范围 | 桌面工作台 + 移动 Web + Android 壳 | **只做移动端 App**；桌面工作台冻结，不再作为设计目标 |
| 视觉基线 | Pioneer（暖灰 + 藏青 + 衬线）、Apple 草案（纯白 + 蓝） | Claude（暖纸 + 陶土 + 衬线/无衬线分工） |
| 交付形态 | 响应式 Web 的多档视口 | 单个 Android 竖屏 App 外壳，320 起；≥600px 只增左右边距（内容最大宽 560） |
| 成功标准 | 五档视口不溢出、契约快照一致 | 真机尺寸下可读、可触、可返回，证据状态不丢失 |

### 1.2 管什么，不管什么

| 管 | 不管 |
| --- | --- |
| 移动 App 的颜色、字体、字号、间距、圆角、层级、动效取值与语义 | 业务信息架构、页面路由、数据接口、后端行为 |
| 组件几何与交互状态（默认/按下/焦点/禁用/等待/选中） | 组件内部状态机与业务判定 |
| Android 竖屏壳、底部 sheet、返回与焦点行为 | 桌面工作台、平板/折叠屏专属布局、iOS 原生实现 |
| 可访问性下限（对比度、触控、缩放、动效偏好） | 用户审美认可；规范通过不等于用户喜欢 |
| 与现有契约/验收的差异和迁移顺序 | 规范范围外的产品代码改动 |

### 1.3 事实、判断、建议

文中数值分三类，别混：
1. **来源值**：Claude 设计体系 `DESIGN.md` / `tokens.css` 的真实 token；
2. **计算值**：按 WCAG 2.1 相对亮度公式实测的对比度（附录 B）；
3. **建议值**：为中文数据密集的移动界面派生、并已通过对比度校验的新值（如 `--mt-accent-strong`、`--mt-caption`、`--mt-border-control`）。

## 2. 设计原则

1. **内容先行**：证据、政策原文、哈希和状态是画面主体；没有装饰插画、emoji、庆祝动画。
2. **一种强调**：陶土色是唯一的品牌强调，每屏 ≤2 处——一个主操作 + 一个当前选中；其余颜色都是事实语义。
3. **衬线讲内容，无衬线做操作**：页面标题、分区标题、卡片标题用衬线；按钮、字段、标签、导航用无衬线；等宽只给哈希、包名、URL、代码。
4. **边界优先于阴影**：层级用 1px 描边与表面色差表达；阴影只给真正浮起的层（sheet、底部操作栏、按下环影）。
5. **事实不靠颜色**：UNKNOWN、PARTIAL、UNREVIEWED、附件未检查必须有文字；颜色只是冗余编码，不从颜色推断结论。
6. **克制动效**：只动 `transform`、`opacity`、`background-color`、`border-color`、`box-shadow`；`prefers-reduced-motion` 下一律即时。

## 3. 设计基线：Claude 体系与移动化取舍

### 3.1 保留 Claude 的部分

- 暖纸画布 `#f5f4ed`、象牙白表面 `#faf9f5`、近黑文字 `#141413`，所有中性色带黄褐底调；
- 衬线标题（单字重 500）+ 无衬线 UI 的分工；
- 陶土品牌色 `#c96442`；
- 环影（ring shadow）表达交互层级，重投影几乎不用；
- 大留白、章节化阅读节奏；移动端取中段圆角（控件 12 / 卡片 16 / sheet 24），不照搬网页 8–32 的全区间。

### 3.2 为移动 App 做的移动化取舍（记录差异，不写成 Claude 原值）

| Claude 原值 | 移动端取舍 | 原因 |
| --- | --- | --- |
| 陶土 CTA 配象牙白字 3.70:1 | 主按钮实心改 `#b04b25`（5.14:1） | 3.70 不达 AA；14–16px 按钮文字必须 ≥4.5:1 |
| 网页 Hero 64px / 分区 52px | 移动 display 32px / title-l 24px | 竖屏 320–390px 宽度下，营销级字号会挤掉内容 |
| `#87867f` 三级文字 | 只做非文本与 ≥24px；≤14px 文字改用 `#6b6a63` | 3.47:1 不达正文 AA |
| 控件依赖环影无实边 | 控件加 1px `#87867f` 实边（3.47:1） | 移动端环影在低亮度屏上不可靠，3:1 非文本对比必须过 |
| Focus Blue `#3898ec` | 焦点/信息改 `#1f6fb2` | `#3898ec` 对暖纸底只有 2.77:1，焦点环必须 ≥3:1 |
| 桌面 1200px 容器、多列 | 单列，内容最大宽 560px | App 只做一列；≥600px 视口只增外边距 |
| 按钮/控件 8px、卡片 8px | 控件 12 / 卡片 16 / sheet 24 | 触屏目标更大，12–16 更易辨识边界；不沿用网页小圆角 |
| L4 浮层 `0 4px 24px .05` | sheet `0 -8px 32px .18` | 移动 sheet 需要与内容分离；底栏只用 1px 向上投影 |
| success `#17a34a` / warn `#eab308` | 文本档 `#0f7a3c` / `#8a5a00` | 原值做文字 3.13 / 1.82 不达 AA；实心仍按语义底档使用 |
| title-l 25 / overline 10 / mono 15 | title-l 24 / overline 11 / mono 14 | 竖屏行宽与中文行高取舍；差 ≤1px，层级不变 |
| 手绘有机插画 | 不使用插画 | 无资产、装饰预算接近零（设计体系本身是 MIT，不是授权问题） |

### 3.3 不追溯改动

Pioneer 仍是历史来源，不是被推翻的错误：颜色、字号、控件状态当年按 Figma 固定过，`docs/design/issue-44-provenance.md`、`issue142-theme-and-primitives.md` 与旧截图保留原样。round2 的 Android 壳合同（`docs/design/frontend-round2-android-pioneer.md`）继续有效。本规范替换它的**视觉层**，并补少量移动交互规则（滚动沿用文档级、sheet 关闭位置、程序化聚焦例外）；不推翻 48dp 触控、56dp 顶栏、edge-to-edge、返回与滚动恢复等工程约束。

## 4. 色彩

### 4.1 结构色

| token | 值 | 用途 | 备注 |
| --- | --- | --- | --- |
| `--mt-bg` | `#f5f4ed` | App 主画布 | 暖纸底，全屏默认 |
| `--mt-surface` | `#faf9f5` | 卡片、面板、输入框、sheet | 与画布只差一档，靠描边分层 |
| `--mt-surface-warm` | `#e8e6dc` | 禁用底、骨架屏、次要分区带 | 比象牙白更暖一档 |
| `--mt-fg` | `#141413` | 标题、主正文、关键值 | 17.50:1（对卡片） |
| `--mt-fg-2` | `#3d3d3a` | 次级正文、表格正文、按钮文字 | 10.34:1 |
| `--mt-muted` | `#5e5d59` | 辅助说明、来源行副文案 | 6.26:1（对卡片） |
| `--mt-caption` | `#6b6a63` | ≤14px 三级文字、时间戳、单位 | 5.15:1（对卡片），计算值 |
| `--mt-meta` | `#87867f` | **仅**非文本（描边/图标）与 ≥24px 大字 | 3.47:1；不得做正文/12px 标签 |
| `--mt-bg-inverse` | `#141413` | 深色章节、报告封面 | 单页 ≤1 段 |
| `--mt-surface-dark` | `#30302e` | 深色章节内的次级面 | 只用于嵌套 |
| `--mt-fg-inverse` | `#faf9f5` | 深色章节文字 | 17.50:1（对 `#141413`） |
| `--mt-muted-inverse` | `#b0aea5` | 深色章节辅助文字 | 8.29:1 |

### 4.2 描边

| token | 值 | 用途 | 对比度 |
| --- | --- | --- | --- |
| `--mt-border` | `#f0eee6` | 装饰性分隔、卡片内分隔 | 1.10（装饰，不承担识别） |
| `--mt-border-soft` | `#e8e6dc` | 卡片边、列表行线、输入内元素 | 对画布 1.13 / 对卡片 1.19（装饰） |
| `--mt-border-control` | `#87867f` | 按钮、字段、sheet 关闭键的可见边界 | 对卡片 3.47；对画布 3.31；暖砂 2.92 仅禁用 |
| `--mt-border-inverse` | `rgba(250,249,245,.16)` | 深色章节分隔 | — |

### 4.3 强调与链接

| token | 值 | 用途 | 实测 |
| --- | --- | --- | --- |
| `--mt-accent` | `#c96442` | 大字号标题、图标、选中标记、进度指示 | 对画布 3.54（仅大字/非文本） |
| `--mt-accent-strong` | `#b04b25` | 主按钮实心底、需要 AA 的强调面 | 象牙白字 5.14 |
| `--mt-accent-strong-hover` | `#a24522` | 主按钮悬停（仅 fine pointer） | 5.84 |
| `--mt-accent-strong-active` | `#974120` | 主按钮按下 | 6.45 |
| `--mt-accent-text` | `#a8431f` | 文字操作、链接、quiet 按钮 | 对画布 5.46 |
| `--mt-accent-on` | `#faf9f5` | 实心强调上的文字 | — |
| `--mt-focus` | `#1f6fb2` | `:focus-visible` 外环、信息语义 | 对卡片 5.01，对画布 4.79 |

> 为什么主按钮比品牌色深一档：Claude 原值 `#c96442` 配象牙白只有 3.70:1，正常文字不达 AA。主按钮保留陶土色相、压深到 5.14:1；品牌色本身继续用于大字与非文本，不降级对比度要求。

### 4.4 语义色（文本档 / 底档分开）

| 语义 | 文本 token | 文本值 | 底 token | 底值 | 实测 |
| --- | --- | --- | --- | --- | --- |
| 成功 | `--mt-success` | `#0f7a3c` | `--mt-success-bg` | `#eef6e8` | 4.91 |
| 警告/待复核 | `--mt-warn` | `#8a5a00` | `--mt-warn-bg` | `#fbf3d9` | 5.34 |
| 危险/失败 | `--mt-danger` | `#b53333` | `--mt-danger-bg` | `#fbeceb` | 5.25 |
| 信息/进行中 | `--mt-info` | `#1f6fb2` | `--mt-info-bg` | `#eaf2fb` | 4.68 |
| 中性/未知 | `--mt-neutral-fg` | `#3d3d3a` | `--mt-neutral-bg` | `#e8e6dc` | 8.71 |

规则：
- **文本档永远配底档**；实心语义面（如危险按钮）用文本档做底、象牙白做字（`#faf9f5` on `#b53333` = 5.72）。
- 状态色不得单独承担语义：`StatusTag` 必须带文字，颜色只是冗余。
- 禁用态统一 `#e8e6dc` 底 + `#87867f` 字，属 WCAG 免除项，但必须有 `disabled` 或 `aria-disabled`。
- 深色章节内：文字 `--mt-fg-inverse` `#faf9f5`、辅助 `--mt-muted-inverse` `#b0aea5`、强调 `--mt-accent-inverse` `#d97757`（对 `#141413` 5.90）、边界 `--mt-border-inverse` `rgba(250,249,245,.16)`。`--mt-accent-inverse` 只用在 `#141413` 上；`#30302e` 上只有 4.24，不用它做文字。
- 暖砂底 `--mt-surface-warm` 只用于禁用、骨架、分区带：`--mt-caption` 在其上 4.34:1、`--mt-meta` 2.92:1，均不达标；不得在暖砂上放非禁用的 14px 三级文字或图标/描边。

### 4.5 明确禁止

- `#c96442` 做正文/按钮文字（3.70:1）；实心按钮统一用 `--mt-accent-strong`。
- `#87867f` 做正文、表格正文或 12px 标签；它只做描边、图标与 ≥24px 辅助字。
- `#3898ec` 做焦点环（对暖纸 2.77:1）；焦点统一 `#1f6fb2`。
- `#eab308` 做文字（对卡片 1.82:1）或任何浅底文字。
- 两套强调色并存（Pioneer 藏青 + 陶土）；迁移期只允许一个界面一套。
- 用颜色表示"已复核/未复核"而不写文字；用陶土色表示装饰。
- 大面积黑底出现在数据区（黑只属于封面、空状态、报告封面）。
- 纯白 `#ffffff` 做页面背景（这一套体系的底色必须带暖调）。

## 5. 排版

### 5.1 字体栈与许可

| 角色 | 栈 | 落地 |
| --- | --- | --- |
| 衬线标题/卡片标题 | `"Anthropic Serif", Georgia, "Noto Serif SC", "Songti SC", serif` | Anthropic Serif 不随包分发，只作首选名；Latin 回落 Georgia，中文回落自托管 Noto Serif SC（SIL OFL） |
| 无衬线 UI/正文 | `"Anthropic Sans", Inter, "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif` | Anthropic Sans 不随包分发；Inter 可选，当前回落自托管 Noto Sans SC（SIL OFL） |
| 阅读（政策原文/报告引文） | `"Noto Serif SC", Georgia, "Songti SC", serif` | 用自托管衬线做长文阅读，与 UI 明确分工 |
| 等宽 | `"SF Mono", "JetBrains Mono", ui-monospace, Consolas, monospace` | 只给哈希、包名、URL、代码；不做正文 |

- 仅使用仓库已有 `apps/web/public/fonts/NotoSansSC-Variable.woff2` 与 `NotoSerifSC-Variable.woff2`；**不新增字体文件、不改字体 CDN**。字体许可文件保留在 `apps/web/public/fonts/licenses/`。
- 不禁止用户缩放；不用 `user-scalable=no`。

### 5.2 字号阶梯（移动端单档密度）

| 角色 | size | line-height | weight | 字体 | 用途 |
| --- | --- | --- | --- | --- | --- |
| `display` | 32px / 2rem | 1.15 | 500 | 衬线 | 封面主标题、空状态主标题（≤1 处/屏） |
| `title-l` | 24px / 1.5rem | 1.25 | 500 | 衬线 | 页面标题（报告、设置） |
| `title-m` | 20px / 1.25rem | 1.30 | 500 | 衬线 | 顶栏标题、分区标题 |
| `title-s` | 17px / 1.0625rem | 1.40 | 500 | 衬线 | 卡片标题、来源标题 |
| `body-l` | 17px / 1.0625rem | 1.75 | 400 | 无衬线 / 阅读衬线 | 政策正文、报告引文 |
| `body` | 16px / 1rem | 1.60 | 400 | 无衬线 | 工作区正文、说明 |
| `control` | 16px / 1rem | 1.25 | 500 | 无衬线 | 按钮、输入、标签、导航 |
| `caption` | 14px / .875rem | 1.45 | 400 | 无衬线 | 元数据、辅助说明 |
| `label` | 12px / .75rem | 1.35 | 500 | 无衬线 | 状态标签、小标注（字段标签用 caption 14/500，见 §8.2） |
| `overline` | 11px / .6875rem | 1.50 | 500 | 无衬线 | 章节小标（全大写 Latin，中文不强制） |
| `mono` | 14px / .875rem | 1.60 | 400 | 等宽 | 哈希、包名、URL、代码片段 |

规则：
- 中文正文行高不低于 1.5；`body-l` 17/1.75 用于政策原文与报告引文。
- 展示级（≥32px）允许 `-0.01em` 字距；中文不压缩字距。
- 表格数字、计数、版本号加 `font-variant-numeric: tabular-nums`。
- 一屏不同时出现两个 `display` 级标题；`display` 只给封面/空状态。
- 报告阅读区用 `body-l` + 阅读衬线；UI 控件仍是无衬线，两者不混用。

### 5.3 长文本与断行

- 哈希、包名、URL 用等宽 + `overflow-wrap: anywhere`；容器不足时换行，禁止页面级横向滚动。
- 政策正文段落间距 16，段内不缩进；引用块左侧 2px `--mt-border-soft` + 16 内边距。
- 中文与拉丁混排由字体栈回落控制，不手工插空格；标点用全角。
- 报告标题、来源标题允许两行；超过两行用 `-webkit-line-clamp: 2` 并保证 `title`/`aria-label` 能读到全文。

## 6. 间距、布局与移动壳

### 6.1 间距

4px 基数、8px 节奏：`4, 8, 12, 16, 20, 24, 32, 40, 48`。

| 场景 | 值 |
| --- | --- |
| 正文左右边距 | 16 |
| 卡片内边距 | 16（默认）/ 20（带主操作或阅读内容） |
| 卡片/分区之间 | 16 / 24 |
| 字段组之间 | 16 |
| 图标与文字 | 8 |
| 按钮水平内边距 | 20 |
| 章节上下留白 | 32 / 40 |
| 列表行最小高度 | 56（两行时按内容） |

### 6.2 移动壳解剖（Android 竖屏，edge-to-edge）

| 区域 | 尺寸 | 规则 |
| --- | --- | --- |
| 状态栏安全区 | `env(safe-area-inset-top)` | 顶栏背景延伸到状态栏后；系统栏图标设为深色（浅色顶栏上必须用深色图标） |
| 顶栏 | 56 + safe-top | 左返回 48×48（导入步隐藏）、标题 `title-m` 衬线、右设置 48×48；吸顶；底部 1px `--mt-border-soft` |
| 步骤导航 | 48 | 四步（导入/候选/进度/报告）；当前项陶土色文字 + 2px 下划线；完成项 ✓；不可达项禁用；整项 ≥48 高 |
| 内容区 | 单列 | 左右 16；内容最大宽 560（≥600px 视口居中）；`100dvh` 计算，底部留出操作栏 + safe-bottom |
| 底部操作栏 | min 64 + safe-bottom | 主按钮 48 高、全宽（左右 16）；次操作文字按钮；顶部 1px 边 + 向上 1px 投影（`0 -1px 2px rgba(20,20,19,.06)`）；键盘弹起时随 `--mt-keyboard-inset` 上移（运行时由 `--keyboard-inset` 映射） |
| Sheet | 顶部圆角 24 | 证据/政策详情用 bottom sheet；设置用全屏 detail；把手 36×4；关闭 48×48；`max-height: min(88dvh, 720px)`；内部滚动 |

- 滚动沿用文档级（body）滚动：顶栏 `sticky`、操作栏 `fixed`，`100dvh` 只用于高度计算。这是 round2 返回/滚动恢复与 Tauri WebView 原生滚动恢复的现状合同（`MobileApp.vue` 用 `window.scrollY/scrollTo`，`verify-mobile-flow.cjs` 断言 scrollY）。若改为内容区滚动，必须同批改恢复逻辑与断言并重新验收，不能只改 CSS。
- 返回：顶栏返回 + Android 系统返回/`popstate` 回到语义上一步并恢复滚动与焦点；根步交给系统退出。
- 焦点：步骤切换后焦点落到页面标题（`tabindex="-1"`），不落到第一个输入框；sheet 关闭后焦点归还触发按钮。
- 软键盘：输入 16px 防 WebView 聚焦缩放（iOS WebView 为主，Android 同档保持可读）；操作栏上移，主操作不被键盘遮挡。
- 横屏/大屏：不做双栏；横屏保持单列，必要时限制内容宽 560 并增加左右边距。

- 设置是顶栏打开的整页 sheet，不是第五个流程步骤；步骤导航始终四项（导入/候选/进度/报告）。

### 6.3 断点（最小集合）

| 宽度 | 行为 |
| --- | --- |
| 320–359 | 紧凑：隐藏非必要元数据、按钮文字可换行、卡片内边距 16 |
| 360–599 | 默认：单列、卡片 16、触控 48 |
| ≥600 | 仅增左右外边距，内容最大宽 560；不引入桌面布局 |

验收尺寸：移动行为以 `verify-mobile-flow.cjs` / `verify-mobile-reading.cjs` 的 320/390/768 + 200% 根字号为准；真实 Android 竖屏以 390×844、320×568 和横屏 844×390 **待真机复核**；≥600 视口现由 768 覆盖（内容最大宽 560），新增 600+ 独立用例前不宣称已验证。桌面 1280/1440/1920 仍由冻结的 `acceptance:frontend` 保护，不作为移动设计验收。

## 7. 圆角、描边与层级

### 7.1 圆角分级

| token | 值 | 用途 |
| --- | --- | --- |
| `--mt-radius-tag` | 6px | 状态标签、微型容器 |
| `--mt-radius-control` | 12px | 按钮、输入、分段控件、底部操作栏按钮 |
| `--mt-radius-card` | 16px | 卡片、列表容器 |
| `--mt-radius-sheet` | 24px | bottom sheet 顶部两角 |
| `--mt-radius-pill` | 999px | 胶囊 CTA（仅空状态/封面） |
| `--mt-radius-circle` | 50% | 图标按钮、头像位 |

不允许"全站一个圆角"；同一组件类固定一档；胶囊只用于强调型 CTA。

### 7.2 描边

- 控件：1px `--mt-border-control`（对卡片 3.47:1、对画布 3.31:1，满足非文本对比；暖砂上 2.92 只用于禁用）。
- 卡片/列表容器：1px `--mt-border-soft`；行内分隔 1px `--mt-border`。
- 焦点：`outline: 2px solid var(--mt-focus); outline-offset: 2px;`，不改变布局尺寸。
- 不用 2px 以上彩色边框做装饰；不用内阴影模拟凹陷。

### 7.3 层级

| 层级 | 处理 | 用途 |
| --- | --- | --- |
| L0 | 平面 + 表面色差 | 主内容、列表、正文 |
| L1 | 1px 描边 | 卡片、字段、只读面板 |
| L2 | 环影 `0 0 0 1px rgba(20,20,19,.08)` | 可点卡片按下、按钮 hover（fine pointer） |
| L3 | `0 4px 24px rgba(20,20,19,.05)` | 浮起小面板、对话框 |
| L4 | `0 -8px 32px rgba(20,20,19,.18)` | bottom sheet（向上投影） |
| 操作栏 | `0 -1px 2px rgba(20,20,19,.06)` | 底部操作栏（向上投影，与 L3 区分） |
| 遮罩 | `rgba(20,20,19,.45)` | 模态/sheet 背景，暖黑不带蓝 |

## 8. 组件

所有组件：`box-sizing: border-box`；无 `transition: all`；可见焦点；禁用不进 Tab 序列（原生 `disabled`）或 `aria-disabled` 且不可激活。

### 8.1 按钮

| 属性 | 值 |
| --- | --- |
| 高度 | 48（全部尺寸；小屏也不低于 48） |
| 水平内边距 | 20（全宽按钮可用 16） |
| 字号/字重 | 16 / 500 无衬线 |
| 圆角 | 12 |
| 最小宽度 | 48；同组按钮间距 ≥8 |

变体与状态：

| 变体 | 默认 | 按下 | 焦点 | 禁用 | 等待 |
| --- | --- | --- | --- | --- | --- |
| primary | `--mt-accent-strong` 底 + `--mt-accent-on` 字 | `--mt-accent-strong-active` + `scale(.98)` | 2px `--mt-focus` 环 | 暖砂底 + `--mt-meta` 字 | 文案不变 + 16px 旋转指示 + `aria-busy` |
| secondary | 象牙白底 + 1px `--mt-border-control` + `--mt-fg-2` 字 | 象牙白底 + `--mt-state-press` 叠加 + `scale(.98)`（不换暖砂） | 同上 | 同上 | 同上 |
| quiet | 透明底 + `--mt-accent-text` 字 | 下划线保持 + 按下层 | 同上 | `--mt-meta` 字 | 文字 + 指示 |
| danger | `--mt-danger` 底 + `#faf9f5` 字 | `--mt-danger-active` + `scale(.98)` | 同上 | 同上 | 同上 |

- 一屏只应有一个 primary；同组操作 ≥3 个时改用 secondary/quiet。
- 等待态不改变按钮宽度（固定最小宽或占位指示），避免布局跳动。
- 只有 `(hover: hover) and (pointer: fine)` 才启用 hover；触屏用按下层反馈，去掉 tap highlight。
- 胶囊按钮只给空状态/封面的主 CTA。

### 8.2 字段

- 高度 56；圆角 12；象牙白底；1px `--mt-border-control`；字号 16（输入值）。
- 标签 14/500 `--mt-fg`（caption 档加粗；`label` 12/500 只给状态标签与小标注），与输入间距 8；帮助 12 `--mt-muted`；错误 12 `--mt-danger` 并 `aria-describedby` 关联。
- 焦点：描边转 `--mt-focus` + 2px 外环；不改变布局尺寸。
- 错误：描边 `--mt-danger`，错误文案带文字/图标，不只靠颜色。
- 禁用：暖砂底、`--mt-meta` 字、无焦点环。
- 占位符用 `--mt-muted`，`opacity: 1`。
- textarea 最小高度 96；select 用原生控件，不改系统滚动行为。

### 8.3 状态标签

| tone | 文字 | 底 | 说明 |
| --- | --- | --- | --- |
| neutral | `#3d3d3a` | `#e8e6dc` | 未知/未开始/中性元数据（UNKNOWN） |
| info | `#1f6fb2` | `#eaf2fb` | 进行中、信息性判定 |
| wait | `#8a5a00` | `#fbf3d9` | 等待、待复核（UNREVIEWED / PARTIAL） |
| success | `#0f7a3c` | `#eef6e8` | 已完成/已复核，必须有文字事实 |
| error | `#b53333` | `#fbeceb` | 失败/冲突/解析错误 |

- 几何：高 24，水平内边距 10，圆角 6，字号 12/500；不交互、不做成按钮。
- 状态标签必须带文字；同一屏出现多个状态时保持顺序稳定（先事实、再完整度、再复核、再附件）。

### 8.4 卡片与列表行

- 卡片：象牙白底、1px `--mt-border-soft`、圆角 16、内边距 16（带主操作/阅读内容用 20）；默认无阴影。
- 可点卡片按下时加 L2 环影 + `scale(.995)`，不做上移。
- 标题 17/500 衬线；元信息 14 `--mt-caption`；正文 16。
- 卡片内不嵌套第二层卡片；分组用 1px 分隔线 + 16 间距。
- 列表行：最小高 56，整行可点，右侧 chevron 20（现状 24，迁移时改；新增 token `--mt-chevron: 20px`）；主文案 16/500，副文案 14 `--mt-muted`；按下层 `--mt-state-press`。

### 8.5 顶栏、步骤导航、操作栏

- 顶栏：见 §6.2；标题不放大、不居中与左对齐混用（统一左对齐）。
- 步骤导航：整行 48 高，四项各 ≥48×48，相邻目标间距 ≥8（现状 2px，属迁移项）；当前项文字 `--mt-accent-text` + 2px 下划线；完成项 ✓ + `--mt-muted`；不可达项 `--mt-meta` + 禁用；不能只靠颜色区分当前/完成，✓ 与下划线是冗余编码。
- 操作栏：只放当前步的主操作与一个次操作；主操作全宽 48；报告步不显示操作栏（阅读态），设置入口留在顶栏。

### 8.6 Sheet 与全屏设置

| | bottom sheet | 全屏 detail（设置） |
| --- | --- | --- |
| 表面 | 象牙白 | 象牙白 |
| 圆角 | 顶部 24 | 无（全屏） |
| 阴影 | L4 | 无 |
| 遮罩 | `rgba(20,20,19,.45)` | 无 |
| 把手 | 36×4，`--mt-handle` | 无 |
| 标题 | 20 衬线 500 | 24 衬线 500 |
| 关闭 | 48×48 顶部右侧 | 48×48 顶部左侧 |
| 高度 | `min(88dvh, 720px)` | `100dvh` |
| 行为 | 内部滚动、焦点陷阱、Esc/返回关闭、焦点归还 | 同左 |

- 点击遮罩关闭；不丢弃已填内容（沿用现约定）。
- 全屏 detail 需要 UiSheet 增加 detail 行为（无遮罩、关闭左置、无把手）；实现该变体前，沿用现有遮罩与右上关闭不算回归，但迁移验收要记录这条差异。
- UiSheet 通过 `DialogPortal` 挂到 `<body>`；移动 token 必须靠 `body.is-mobile-app` 的 `--ui-*` 映射继承（见 §11），不能只声明在 `.mobile-workspace`，否则 sheet/设置会落回 Pioneer 值。
- 关闭后焦点回到触发按钮；打开时聚焦首个可交互控件（或标题）。

### 8.7 通知、错误、空状态、加载

- 通知：圆角 12、内边距 12、14/1.45；语义底 + 文本档 + 可选 20px 图标（`aria-hidden`）；错误 `role="alert"`。
- 关键失败不用 toast 一闪而过；在内容区保留可重试的说明。
- 空状态：衬线 `title-l` 24 + `body` 16 + 一个 primary CTA；不堆插画、不用 emoji。
- 加载：骨架用暖砂块，静态不闪烁（`prefers-reduced-motion` 下完全静止）；进度只显示阶段，不显示无依据的百分比/倒计时。

### 8.8 报告的阅读态

- 报告封面用深色章节（`#141413`）一次，正文回到暖纸/象牙白。
- 证据列表按数据类型分组；行内哈希/包名用等宽 14 并可断行。
- 证据详情、政策全文在 bottom sheet 中阅读；政策原文用 `body-l` + 阅读衬线 17/1.75。
- UNKNOWN、PARTIAL、UNREVIEWED、附件未检查必须出现在结果附近，不能只放在展开的"详情"里。

## 9. 交互状态与动效

### 9.1 状态清单

| 状态 | 规则 |
| --- | --- |
| 默认 | 无装饰；边界清楚 |
| 按下 | 按下层立即出现（≤16ms，不等 120ms）；按钮 `scale(.98)`；释放按 120ms 回落 |
| 焦点 | 仅 `:focus-visible` 显示 2px 环；任何背景可见 |
| 禁用 | 暖砂底 + `#87867f` 字；`disabled` 或 `aria-disabled`；不参与点击 |
| 选中 | 陶土色文字 + 下划线/✓；同时有形状冗余 |
| 等待 | 文案不变 + 指示器 + `aria-busy`；宽度不跳 |
| 错误 | 语义底 + 文本说明 + `role="alert"`；可重试入口保留 |
| 空 | 说明"下一步做什么"，一个主 CTA |

状态层统一用三个 token，只叠加、不改变布局：`--mt-state-hover`（`.06`）、`--mt-state-press`（`.12`）、`--mt-state-selected`（`.08`）。

### 9.2 动效 token

| token | 值 | 用途 |
| --- | --- | --- |
| `--mt-duration-press` | 120ms | 按下回落、颜色变化 |
| `--mt-duration-enter` | 200ms | sheet/步骤进入 |
| `--mt-duration-exit` | 150ms | 关闭、退场（比进入快） |
| `--mt-ease-standard` | `cubic-bezier(.2,0,0,1)` | 默认减速 |
| `--mt-ease-decelerate` | `cubic-bezier(0,0,0,1)` | 浮层进入 |

- 只允许 `transform`、`opacity`、`background-color`、`border-color`、`box-shadow` 过渡。
- 不使用 `transition: all`；不自动播放装饰动画；不做视差。
- `prefers-reduced-motion: reduce` 下时长归零、取消位移与缩放，保留即时可见状态。

## 10. 无障碍

- 正文对比度 ≥4.5:1；大字（≥24px 或 ≥19px 加粗）与图形/控件边界 ≥3:1。
- 触控目标 ≥48×48 CSS px，相邻目标间距 ≥8；整行可点的列表行高度 ≥56。
- 输入字号 16px 起（防 iOS WebView 聚焦缩放；Android WebView 同档保持可读）；不禁止缩放；200% 根字号、320px 宽下无页面级横向滚动、无内容裁切。
- 焦点：`:focus-visible` 2px 环 + 2px 偏移；步骤切换后程序化聚焦的标题是例外，不画控件式焦点环（键盘 `:focus-visible` 仍画）；sheet 焦点陷阱与归还。
- 语义：每个步骤一个 `h1`；分区 `h2`；状态标签带文字；错误用文字 + `aria-describedby`；图标 `aria-hidden`。
- 键盘/读屏：Tab 顺序符合阅读顺序；对话框 Esc/返回可关；底栏按钮有可读名称（不用纯图标承担主操作）。
- 颜色不作为唯一编码：状态、成功/失败、选中态都有文字或形状冗余。
- `forced-colors` 下保留边界与焦点；动效偏好下保留即时状态。

## 11. Token 落地方式与作用域

### 11.1 为什么必须作用域化

桌面 Web 工作台与移动 App 共用 `UiButton`、`UiField`、`StatusTag`、`UiSheet`、`UiIcon` 等组件；桌面仍被冻结的 Pioneer 契约钉住。若把 `:root` 直接改成 Claude，桌面会被动换肤，现有 `assertDesign` 断言也会失败。因此：

- `theme.css` 继续保留 Pioneer 变量（桌面根）；`--mt-*` 原始 token 声明在 `:root`——命名空间隔离，桌面不消费，不产生视觉变化；
- 共享组件改为消费语义别名（`--ui-accent`、`--ui-surface`、`--ui-radius-control` 等）：`:root` 映射到 Pioneer 值；移动应用挂载时给 `<body>` 加 `is-mobile-app`，由 `body.is-mobile-app` 把 `--ui-*` 重映射到 `--mt-*`。UiSheet 通过 `DialogPortal` 挂到 body，必须靠这层 body 映射才能拿到移动 token；
- 不重指 `--canvas`/`--navy`/`--m-*` 的旧值；不在共享组件里写移动专用几何；
- 等桌面工作台正式退役（产品决策）后，再删除别名与 Pioneer 变量。

### 11.2 文件与命名

- 唯一变量文件仍是 `apps/web/src/theme.css`（round2 合同）：新增 `:root { --mt-* }` 与 `body.is-mobile-app { --ui-* }` 区块；旧 `--canvas`/`--navy`/`--m-*` 在桌面与迁移期保留。
- 新增移动样式放在 `apps/web/src/mobile/`；共享组件只改"消费别名"这一层，不在此轮改桌面视觉。
- 移动根样式值不硬编码十六进制颜色；守卫不能用朴素 grep（会命中 `#144/#145` 工单号与注释），应剔除注释/工单号，或直接用 stylelint 规则；`theme.css` 是变量文件，允许出现色值。
- 机器可读契约：`docs/design/mobile-reset/mobile-design.tokens.json`（随规范交付）；实现阶段由 `scripts/fixtures/mobile-design.json` 承接断言（已落地）。

### 11.3 共享组件语义别名（实现清单）

别名只覆盖共享组件用到的语义，不是全量 token；新增别名词必须同时给桌面根与移动根两套值，不能只写移动值。

| 语义别名 | 桌面根（Pioneer，保持旧值） | 移动根（Claude） | 消费组件 |
| --- | --- | --- | --- |
| `--ui-surface` | `--surface` `#fdfcfa` | `--mt-surface` `#faf9f5` | UiSheet、UiButton secondary、CandidatePage |
| `--ui-surface-muted` | `--surface-muted` `#eeedea` | `--mt-surface-warm` `#e8e6dc` | UiField 禁用、骨架、分区带 |
| `--ui-fg` | `--ink` `#2c3547` | `--mt-fg` `#141413` | 全部组件 |
| `--ui-fg-2` | `--ink` `#2c3547` | `--mt-fg-2` `#3d3d3a` | 按钮/字段文字 |
| `--ui-muted` | `--muted` `#64696f` | `--mt-muted` `#5e5d59` | 帮助文字、副文案 |
| `--ui-border` | `--border` `#d9d7d2` | `--mt-border` `#f0eee6` | 行内分隔线、装饰线 |
| `--ui-border-soft` | `--border` `#d9d7d2` | `--mt-border-soft` `#e8e6dc` | 卡片、列表容器 |
| `--ui-border-control` | `--control` `#858d92` | `--mt-border-control` `#87867f` | 按钮、字段 |
| `--ui-accent` | `--navy` `#333c50` | `--mt-accent-strong` `#b04b25` | 主按钮实心底 |
| `--ui-accent-hover` | `--navy-hover` `#212a3b` | `--mt-accent-strong-hover` `#a24522` | 主按钮悬停 |
| `--ui-accent-text` | `--navy` `#333c50` | `--mt-accent-text` `#a8431f` | quiet/链接 |
| `--ui-accent-on` | `--surface` `#fdfcfa` | `--mt-accent-on` `#faf9f5` | 主按钮文字（`frontend-guards.cjs` 冻结断言要求 `.ui-button.primary` 的文字为 `roles.surface`；`--on-action` 只保留给旧 `.primary`） |
| `--ui-danger-on` | `--on-action` `#f9f9f9` | `--mt-accent-on` `#faf9f5` | 危险按钮文字；与 `--ui-accent-on` 解耦，避免改桌面危险按钮 |
| `--ui-focus` | `--navy` `#333c50` | `--mt-focus` `#1f6fb2` | 焦点环 |
| `--ui-success` / `--ui-success-bg` | `--success` `#35644b` / `--mint` `#dce9df` | `--mt-success` / `--mt-success-bg` | StatusTag success |
| `--ui-warn` / `--ui-warn-bg` | `--ink` `#2c3547` / `--notice` `#ede4d6` | `--mt-warn` / `--mt-warn-bg` | StatusTag wait |
| `--ui-danger` / `--ui-danger-text` / `--ui-danger-bg` | `--danger` `#b25352` / `--error` `#934342` / `--rose` `#ebdada` | `--mt-danger` / `--mt-danger` / `--mt-danger-bg` | 危险按钮、StatusTag error |
| `--ui-danger-active` | `--rose` `#ebdada`（文字 `--error`） | `--mt-danger-active` `#a92e2e` | 危险按钮按下 |
| `--ui-info` / `--ui-info-bg` | `--ink` `#2c3547` / `--slate` `#dde2e9` | `--mt-info` / `--mt-info-bg` | StatusTag info |
| `--ui-neutral-fg` / `--ui-neutral-bg` | `--ink` `#2c3547` / `--surface-muted` `#eeedea` | `--mt-neutral-fg` / `--mt-neutral-bg` | StatusTag neutral |
| `--ui-scrim` | `--overlay` `rgba(44,53,71,.3)` | `--mt-scrim` `rgba(20,20,19,.45)` | UiSheet 遮罩 |
| `--ui-canvas` | `--canvas` `#f6f5f1` | `--mt-bg` `#f5f4ed` | 报告/代码块/页面底 |
| `--ui-radius-control` | `--radius` `8px` | `--mt-radius-control` `12px` | 按钮、字段 |
| `--ui-radius-field` | `--radius` `8px` | `--mt-radius-field` `12px` | 字段 |
| `--ui-radius-tag` | `--radius` `8px` | `--mt-radius-tag` `6px` | StatusTag |
| `--ui-radius-card` | `--radius-panel` `12px` | `--mt-radius-card` `16px` | 卡片 |
| `--ui-shadow-ring` | `none`（Pioneer 用边框） | `0 0 0 1px rgba(20,20,19,.08)` | 可点卡片按下 |
| `--ui-shadow-bar` | `--m-shadow-bar` `0 1px 2px rgba(44,53,71,.08)` | `--mt-shadow-bar` `0 -1px 2px rgba(20,20,19,.06)` | 操作栏 |
| `--ui-state-hover` | `--m-state-hover` `rgba(44,53,71,.06)` | `--mt-state-hover` `rgba(20,20,19,.06)` | 共享组件悬停 |
| `--ui-state-press` | `--m-state-press` `rgba(44,53,71,.12)` | `--mt-state-press` `rgba(20,20,19,.12)` | 共享组件按下 |
| `--ui-state-selected` | `--m-state-selected` `rgba(51,60,80,.08)` | `--mt-state-selected` `rgba(20,20,19,.08)` | 共享组件选中 |
| `--ui-radius-sheet` | `--m-sheet-radius` `20px` | `--mt-radius-sheet` `24px` | UiSheet 顶部 |
| `--ui-shadow-sheet` | `--m-shadow-sheet` `0 -8px 32px rgba(44,53,71,.18)` | `--mt-shadow-sheet` `0 -8px 32px rgba(20,20,19,.18)` | UiSheet |
| `--ui-handle` | `--border` `#d9d7d2` | `--mt-handle` `#d1cfc5` | UiSheet 把手 |
| `--ui-duration-enter` | `--m-duration-enter` `200ms` | `--mt-duration-enter` `200ms` | UiSheet 进入 |
| `--ui-duration-exit` | `--m-duration-exit` `150ms` | `--mt-duration-exit` `150ms` | UiSheet 退场 |
| `--ui-ease-decelerate` | `--m-ease-decelerate` `cubic-bezier(0,0,0,1)` | `--mt-ease-decelerate` 同值 | UiSheet 进入 |
| `--ui-font-body` | `--font-body` | `--mt-font-sans` | 全部组件 |
| `--ui-font-display` | `--font-display` | `--mt-font-serif` | 标题 |
| `--ui-touch` | 40px（fine）/ 44px（coarse） | 48px | 可交互元素 |
| `--ui-button-height` | 36px（fine）/ 44px（coarse） | 48px | UiButton |
| `--ui-field-height` | 40px（fine/coarse，保持冻结契约） | 56px | UiField |

桌面触控与按钮高度必须保留现有两档（fine/coarse）：`pioneer-design.json` 的 `mobileButton.minHeight` 与 `frontend-guards.cjs` 在 ≤560px 断言 44px，不能压成一个 36/40 的单值。以上别名是共享组件的实现清单；共享组件类（`.ui-button`/`.ui-field`/`.status-tag`/`.ui-sheet`）必须消费 `--ui-*`，`mobile.css` 的移动专属覆盖可继续消费 `--mt-*`（移动自有样式），两者在 `body.is-mobile-app` 内取同一组值。

## 12. 现状差距与实施顺序

现状细节与逐条证据见配套的 [现状审计](mobile-reset/current-audit.md)；下列顺序已于 2026-10-23 执行，记录、验收结果与已知偏差见 [迁移实施记录](mobile-reset/implementation-20261023.md)。

1. **契约先行**：新增 `scripts/fixtures/mobile-design.json`（token、几何、状态），`assertMobileDesign` 先接上；`pioneer-design.json` 保留到桌面工作台正式退役，不提前删断言；退役触发条件与复审点见 [ADR-0005](../adr/0005-frontend-contract-retirement.md)。
2. **Token 层**：`theme.css` 增加 `.mobile-workspace` 的 `--mt-*` 区块与共享组件语义别名；桌面根保持 Pioneer；不新增字体文件；48/56/64 几何同步。
3. **基础组件**：按钮 → 字段 → 状态标签 → 卡片/列表行 → 顶栏/步骤导航/操作栏 → sheet。一次只改一个组件并跑对应断言。
4. **四个步骤 + 设置页**：导入 → 候选 → 进度 → 报告，另加顶栏打开的全屏设置；报告阅读切 `body-l` + 阅读衬线；空态/错误/加载一起改。
5. **无障碍与动效**：焦点环、reduced-motion、200% 根字号、键盘/返回、软键盘。
6. **验收与证据**：`acceptance:mobile` 与移动截图重拍（320/390、200%、横屏；≥600 现由 768 覆盖）；旧截图不覆盖，保留为历史证据。
7. **清理**：只删移动迁移期别名与退役的移动 token；桌面 Pioneer token 与断点保留到产品决定退役，不顺手删（触发条件见 [ADR-0005](../adr/0005-frontend-contract-retirement.md)）。

## 13. 验收清单

- [ ] `apps/web/src/mobile/**` 样式值无硬编码十六进制颜色（`theme.css` 变量块豁免；守卫剔除注释/工单号，或用 stylelint）；共享组件通过语义别名取色，桌面 Pioneer 断言保持不变。
- [ ] 正文对比度 ≥4.5:1；控件边 ≥3:1；焦点环在画布、卡片、暖砂上均可辨。
- [ ] 320/390/768、200% 根字号、横屏无页面级横向溢出；≥600 视口只增边距，内容最大宽 560。
- [ ] 触控 ≥48；输入 16px；底栏在软键盘弹起时仍可达。
- [ ] `prefers-reduced-motion: reduce` 下无动画、无位移。
- [ ] 状态标签、错误提示、选中/完成态都有文字或形状冗余。
- [ ] 深色章节只出现在封面/空态/报告封面。
- [ ] 无字体 CDN 请求；只使用仓库已有 Noto 变量字体。
- [ ] 返回/滚动恢复/焦点归还/焦点陷阱行为可复现。
- [ ] 契约快照与新 token 一致；`scripts/check.sh` 与移动验收通过。
- [ ] 新旧截图并存，历史证据未被覆盖。

## 14. 限制与未覆盖

- 迁移已落地：产品代码、样式、契约与验收脚本已按本规范改动；真机项仍未验证。
- 没有做真机（Android/iOS）验证、读屏人工测试、低亮度/强光屏实拍；对比度是按 WCAG 公式计算的静态值，不替代实机检查。
- Anthropic Serif/Sans 是定制字体，本仓库不分发；实际渲染以 Georgia / Noto Serif SC、Noto Sans SC 为准，字面宽度与 Claude 官方页面会有差异。
- 暖纸底 + 陶土强调是审美选择；规范通过只代表规则自洽、可执行，不代表用户认可外观。
- 桌面工作台、移动 Web 独立设计不在本规范内；它们的产品去留属于后续产品决策，不由本规范替代。

## 15. 来源与许可

| 来源 | 用途 | 许可 |
| --- | --- | --- |
| od-ds-claude（OpenDesign v0.25.1） | 色彩、字体分工、圆角、环影、版式节奏的基线 | MIT |
| od-mobile-app（OpenDesign v0.25.1） | 规范站的手机框与单屏叙事参考 | MIT |
| Pioneer（Figma 824:1382 / 824:1422） | 历史来源与业务信息层次 | 项目内既有来源，见 `issue-44-provenance.md` |
| round2 Android 壳合同 | 56 顶栏、48 触控、edge-to-edge、返回/滚动恢复 | 项目内文档 |
| Noto Sans SC / Noto Serif SC | 中文 UI 与阅读字体 | SIL OFL 1.1 |

配套产物（本轮同批交付）：
- 规范站：[spec-site.html](mobile-reset/spec-site.html)（单文件、离线可开）
- 现状审计：[current-audit.md](mobile-reset/current-audit.md)
- token 契约：[mobile-design.tokens.json](mobile-reset/mobile-design.tokens.json)、[token-map.md](mobile-reset/token-map.md)
- 对比度脚本：[contrast.mjs](mobile-reset/contrast.mjs)
- 迁移实施记录：[implementation-20261023.md](mobile-reset/implementation-20261023.md)

## 16. 大字号与操作层级（#295 / PT-MOB-202，2026-10-23）

本节是 §5.2、§6.2、§8.1、§8.5、§8.8 的明确例外，按 PT-MOB-202 实施；默认字号下的几何契约（56 顶栏、48 步骤轨、48 触控、64 底栏、12/16/24 圆角）不变。

- **步骤导航**（覆盖 §6.2 的固定 48 行高）：48 仍是默认行高与最小触控高度；200% 根字号下 `height` 改为按内容增高，标签允许完整换行，序号圆圈与数字随字号等比放大。禁止裁字、逐字竖排或只靠颜色区分当前步骤。
- **底部操作栏**（覆盖 §6.2/§8.5 的“主操作全宽 + 一次操作”）：每步只保留一个主操作。主操作设 `min-width: min(100%, 11em)`，同排放不下时换行独占一行，次操作退出同排竞争，不做逐字竖排。报告阅读步、以及未选择材料的导入空态不挂固定底栏（空态主 CTA 留在空状态卡片内）；栏高增长时正文底部留白取实测高度 `--m-actionbar-actual`，无栏时退回安全区。
- **按钮层级**（§8.1 的落地细则）：一屏至多一个陶土实心主操作；次操作用中性文字（`--mt-fg-2`）或轻量样式，不再复用强调色。来源切换是标签栏（无描边、选中 2px 下划线、可横滚、短名互不重复且当前来源完整标题随行可见）；候选选择是列表行（容器一条描边、行间 1px 分隔线、选中状态层 + 2px 下划线），不再逐行套卡片。删除材料统一危险色，并在原位二次确认作用对象与后果。
- **行高**（覆盖 §5.2 的固定像素行高）：移动报告内标题与说明改用相对行高（标题 1.35、说明 1.5），覆盖 `hierarchy.css` 为桌面冻结保留的 24/22/20px 固定值；桌面不继承这些覆盖。
- **证据与报告**（§8.8 的阅读顺序）：移动证据卡先给静态线索、政策原句与未知项，方法签名、规则版本、原始 JSON 收进“技术详情”；来源与投递的内部代码（`REAL_SCAN` / `PERSISTED_REPLAY`）进入“来源标识”折叠，首屏只保留中文语义与必要限制（扫描范围 PARTIAL、待复核条目数）。
- **时间与标识**：移动壳统一显示本地可读时间，原始 ISO 值保留在 `datetime`/`title`；任务 ID、材料标识收进“任务详情/报告来源与版本”；哈希默认缩略，可展开看完整值并复制。来源/投递的内部代码（`REAL_SCAN`、`PERSISTED_REPLAY`、`OFFLINE_REPLAY`）不进入主阅读流，只在“来源标识”折叠内出现。
- **可发现性与中断操作**（2026-10-23 独立视觉审阅后补充）：移动壳内所有 `<details>` 的 summary 统一带 ▾ 指示（材料条自带的“详情 >”不重复加）；“取消分析”这类中断性操作使用危险文字色、排在“刷新状态”之后，并在状态卡说明“只停止本次分析，材料会保留”；分段控件在 200% 根字号下按整行换行，不做 3+1 断行。
- **验收**：`verify-mobile-flow.cjs` 在 320/390 的 200% 场景断言主操作不逐字竖排、底栏不超过视口 40%、当前步骤标签完整不裁切；`verify-mobile-reading.cjs` 断言报告说明使用相对行高，且内部代码只在“来源标识”展开后可读。

## 附录 A：CSS token 草案

作用域：原始 `--mt-*` 在 `:root` 声明（命名空间隔离，桌面不消费）；`--ui-*` 别名在 `body.is-mobile-app` 重映射（见 §11.3），旧 Pioneer 变量保持旧值。

```css
:root {
  /* 结构 */
  --mt-bg: #f5f4ed; --mt-surface: #faf9f5; --mt-surface-warm: #e8e6dc;
  --mt-bg-inverse: #141413; --mt-surface-dark: #30302e;
  /* 文字 */
  --mt-fg: #141413; --mt-fg-2: #3d3d3a; --mt-muted: #5e5d59;
  --mt-caption: #6b6a63; --mt-meta: #87867f;
  --mt-fg-inverse: #faf9f5; --mt-muted-inverse: #b0aea5;
  /* 描边 */
  --mt-border: #f0eee6; --mt-border-soft: #e8e6dc; --mt-border-control: #87867f;
  --mt-border-inverse: rgba(250, 249, 245, .16);
  /* 强调 */
  --mt-accent: #c96442; --mt-accent-strong: #b04b25;
  --mt-accent-strong-hover: #a24522; --mt-accent-strong-active: #974120;
  --mt-accent-text: #a8431f; --mt-accent-on: #faf9f5; --mt-accent-inverse: #d97757;
  --mt-focus: #1f6fb2;
  /* 语义 */
  --mt-success: #0f7a3c; --mt-success-bg: #eef6e8;
  --mt-warn: #8a5a00; --mt-warn-bg: #fbf3d9;
  --mt-danger: #b53333; --mt-danger-bg: #fbeceb; --mt-danger-active: #a92e2e;
  --mt-info: #1f6fb2; --mt-info-bg: #eaf2fb;
  --mt-neutral-fg: #3d3d3a; --mt-neutral-bg: #e8e6dc;
  /* 遮罩与阴影 */
  --mt-scrim: rgba(20, 20, 19, .45);
  --mt-handle: #d1cfc5;
  --mt-state-hover: rgba(20, 20, 19, .06);
  --mt-state-press: rgba(20, 20, 19, .12);
  --mt-state-selected: rgba(20, 20, 19, .08);
  --mt-shadow-1: 0 1px 2px rgba(20, 20, 19, .06);
  --mt-shadow-bar: 0 -1px 2px rgba(20, 20, 19, .06);
  --mt-shadow-ring: 0 0 0 1px rgba(20, 20, 19, .08);
  --mt-shadow-3: 0 4px 24px rgba(20, 20, 19, .05);
  --mt-shadow-sheet: 0 -8px 32px rgba(20, 20, 19, .18);
  /* 实现补充（token-map 引用，避免同名缺失） */
  --mt-shadow-0: none;
  --mt-elev-1: 1px solid var(--mt-border-soft);
  --mt-elev-2: var(--mt-shadow-ring);
  --mt-elev-3: var(--mt-shadow-3);
  --mt-elev-4: var(--mt-shadow-sheet);
  /* 字体 */
  --mt-font-serif: "Anthropic Serif", Georgia, "Noto Serif SC", "Songti SC", serif;
  --mt-font-sans: "Anthropic Sans", Inter, "Noto Sans SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  --mt-font-reading: "Noto Serif SC", Georgia, "Songti SC", serif;
  --mt-font-mono: "SF Mono", "JetBrains Mono", ui-monospace, Consolas, monospace;
  /* 字号（统一 --mt-text-*，避免与颜色 --mt-caption 冲突） */
  --mt-text-display: 2rem; --mt-text-title-l: 1.5rem; --mt-text-title-m: 1.25rem; --mt-text-title-s: 1.0625rem;
  --mt-text-body-l: 1.0625rem; --mt-text-body: 1rem; --mt-text-control: 1rem;
  --mt-text-caption: .875rem; --mt-text-label: .75rem; --mt-text-overline: .6875rem; --mt-text-mono: .875rem;
  /* 间距 */
  --mt-space-4: 4px; --mt-space-8: 8px; --mt-space-12: 12px; --mt-space-16: 16px;
  --mt-space-20: 20px; --mt-space-24: 24px; --mt-space-32: 32px;
  --mt-space-40: 40px; --mt-space-48: 48px;
  /* 圆角 */
  --mt-radius-tag: 6px; --mt-radius-control: 12px; --mt-radius-card: 16px;
  --mt-radius-sheet: 24px; --mt-radius-pill: 999px; --mt-radius-circle: 50%; --mt-radius-field: 12px;
  /* 几何 */
  --mt-gutter: 16px; --mt-appbar: 56px; --mt-stepnav: 48px; --mt-actionbar: 64px;
  --mt-touch: 48px; --mt-input-height: 56px; --mt-content-max: 560px; --mt-chevron: 20px;
  --mt-input-font-size: 1rem; --mt-content-height: 100dvh; --mt-content-min-viewport: 100dvh;
  --mt-safe-top: env(safe-area-inset-top, 0px); --mt-safe-right: env(safe-area-inset-right, 0px);
  --mt-safe-bottom: env(safe-area-inset-bottom, 0px); --mt-safe-left: env(safe-area-inset-left, 0px);
  --mt-keyboard-inset: 0px;
  /* 动效 */
  --mt-duration-press: 120ms; --mt-duration-enter: 200ms; --mt-duration-exit: 150ms;
  --mt-ease-standard: cubic-bezier(.2, 0, 0, 1);
  --mt-ease-decelerate: cubic-bezier(0, 0, 0, 1);
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --mt-duration-press: 0ms; --mt-duration-enter: 0ms; --mt-duration-exit: 0ms;
  }
}
```

`--ui-*` 别名不写进这段；按 §11.3 在 `body.is-mobile-app` 重映射，UiSheet 的 body portal 才能继承。

## 附录 B：对比度核算

脚本：`node docs/design/mobile-reset/contrast.mjs`（读取同目录 token JSON，按 WCAG 2.1 计算）。

| 组合 | 比值 | 结论 |
| --- | --- | --- |
| `#141413` / `#f5f4ed` | 16.72 | AAA |
| `#141413` / `#faf9f5` | 17.50 | AAA |
| `#3d3d3a` / `#faf9f5` | 10.34 | AAA |
| `#5e5d59` / `#f5f4ed` | 5.98 | AA |
| `#5e5d59` / `#faf9f5` | 6.26 | AA |
| `#6b6a63` / `#faf9f5` | 5.15 | AA |
| `#6b6a63` / `#f5f4ed` | 4.93 | AA |
| `#87867f` / `#faf9f5` | 3.47 | 仅非文本/大字 |
| `#faf9f5` / `#b04b25` | 5.14 | AA |
| `#faf9f5` / `#a24522` | 5.84 | AA |
| `#faf9f5` / `#974120` | 6.45 | AA |
| `#a8431f` / `#f5f4ed` | 5.46 | AA |
| `#c96442` / `#f5f4ed` | 3.54 | 仅大字/非文本 |
| `#1f6fb2` / `#faf9f5` | 5.01 | AA |
| `#1f6fb2` / `#f5f4ed` | 4.79 | AA |
| `#1f6fb2` / `#e8e6dc` | 4.22 | 非文本 3:1 通过（不用于正文） |
| `#0f7a3c` / `#eef6e8` | 4.91 | AA |
| `#8a5a00` / `#fbf3d9` | 5.34 | AA |
| `#b53333` / `#fbeceb` | 5.25 | AA |
| `#faf9f5` / `#b53333` | 5.72 | AA |
| `#1f6fb2` / `#eaf2fb` | 4.68 | AA |
| `#3d3d3a` / `#e8e6dc` | 8.71 | AAA |
| `#faf9f5` / `#141413` | 17.50 | AAA |
| `#b0aea5` / `#141413` | 8.29 | AAA |
| `#d97757` / `#141413` | 5.90 | AA |
| `#3898ec` / `#faf9f5`（原焦点蓝） | 2.90 | **不通过**，故焦点改 `#1f6fb2` |
| `#c96442` / `#faf9f5`（原陶土实心） | 3.70 | **不通过**（正文），故实心改 `#b04b25` |
| `#eab308` / `#faf9f5` | 1.82 | **不通过**，禁用为文字 |
| `#87867f` / `#e8e6dc` | 2.92 | **不通过**，不可做文字或非禁用图标 |
