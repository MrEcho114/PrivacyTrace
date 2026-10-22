# PrivacyTrace 前端设计规范 · Apple 基线

- 状态：**已废弃（superseded）**。2026-10-23 起由 [移动端 Claude 规范](../frontend-design-spec-mobile.md) 替代，仅作历史参考，不再作为实施依据。
- 归档原因：前端范围收窄到仅移动端 App，视觉基线由 Apple 改为 Claude；本草案面向桌面工作台与多档视口，且它引用的 `apple-reset/` 配套文件未随仓库提交。
- 当时适用：`apps/web`（桌面工作台、报告阅读、设置）与移动 Web 壳（`apps/web/src/mobile/`）；Android 原生壳的尺寸合同继续沿用
- 当时基线：Apple 设计体系（od-ds-apple），OpenDesign 打包，MIT；外部路径 `vendor/open-design/...` 指 EAC 设计库，不在本仓库内
- 当时配套：规范站与审计在 `apple-reset/`，未包含在归档中，链接失效属预期
- 当时范围：**只交付规范层**。`apps/web` 的产品代码、`theme.css`、契约快照与验收脚本当时不改；实施顺序见 §11。

## 0. 一句话

界面退到证据后面：中性三色打底，只有一种蓝色代表"可操作"，用 1px 线和表面色差分层，颜色只做语义不做装饰。

## 1. 定位与边界

### 这个规范管什么

| 管 | 不管 |
| --- | --- |
| 颜色、字体、字号、间距、圆角、阴影、动效的取值与语义 | 业务信息架构、页面路由、数据接口 |
| 组件几何与交互状态（默认/悬停/按下/焦点/禁用/等待） | 组件内部状态机与业务判定 |
| 桌面、平板、移动 Web、Android 壳的尺寸映射 | 品牌 Logo、插画、APK 图标等资产设计 |
| 可访问性下限（对比度、触控、焦点、缩放、动效偏好） | 用户审美认可；规范通过不等于用户喜欢 |

### 与旧规范的关系

Pioneer 仍是历史来源，不是被推翻的错误：颜色、字号、控件状态当年按 Figma 固定过，文档与截图保留原样即可。本规范在其上做一次**视觉体系重置**：

- 保留：信息层次、控件类型集合（按钮/字段/状态/对话框/sheet）、移动端触控与安全区合同、14px 起的密集操作字号档。
- 替换：暖灰画布 → 白/`#f5f5f7`；藏青主操作 → Apple 蓝；衬线标题 → 无衬线；8/12px 圆角 → 分级圆角；文字内嵌的暖色状态 → 高对比语义色。
- 不追溯改动：历史报告、receipts、旧截图保持原 SHA 与当时结论。

### 事实、判断与建议

文中数值分三类，别混：

1. **来源值**：Apple 包 `tokens.css` / `DESIGN.md` 的真实 token；
2. **计算值**：本规范用 WCAG 相对亮度公式实测的对比度，脚本与结果见附录 B；
3. **建议值**：为适配中文数据密集工作台而定的新值（双档正文、语义色深色文本档等）。

## 2. 设计原则

1. **内容先行**：证据、政策原文、哈希和判定结果是画面主体；装饰预算接近零。
2. **一种强调**：只有 `#0071e3` 代表可操作与当前选中；其余颜色都是事实语义。
3. **密度分档**：营销页松（首屏/空状态）、工作台紧（15px 正文）、阅读页宽（17px/1.75）。一套 token，三种档位。
4. **边界优先于阴影**：层级用 1px 线与表面色差表达；阴影只给真正浮起的层（对话框、sheet、可点卡片悬停）。
5. **事实不靠颜色**：状态必须有文字标签，颜色只是冗余编码；UNKNOWN 不因颜色升级为成功。
6. **克制的动效**：只动 `transform`、`opacity`、`background-color`；`prefers-reduced-motion` 下一律即时。

## 3. 色彩

### 3.1 结构色

| token | 值 | 用途 | 备注 |
| --- | --- | --- | --- |
| `--pt-bg` | `#ffffff` | 工作台主画布、表格、表单 | 默认背景 |
| `--pt-bg-subtle` | `#f5f5f7` | 分区带、只读区、悬停行、分段控件槽 | 替代旧 `--canvas` / `--surface-muted` |
| `--pt-bg-inverse` | `#000000` | 首屏、空状态、报告封面章节 | 只做章节，不做工作台背景 |
| `--pt-surface` | `#ffffff` | 卡片、面板、弹层表面 | 与背景同值，靠描边分层 |
| `--pt-surface-raised` | `#fbfbfd` | 卡片悬停、次级面板 | 比白更轻的暖白 |
| `--pt-graphite` | `#272729` | 深色章节内的控制条 | 黑底上的次级面 |
| `--pt-graphite-2` | `#2a2a2c` | 深色章节内更深一档 | 只用于嵌套 |

### 3.2 文字与描边

| token | 值 | 白底对比度 | 用途 |
| --- | --- | --- | --- |
| `--pt-ink` | `#1d1d1f` | 16.83:1 | 标题、主正文、关键值 |
| `--pt-ink-2` | `#424245` | 10.01:1 | 次级正文、表格正文 |
| `--pt-muted` | `#6e6e73` | 5.07:1 | 辅助说明、时间戳、单位 |
| `--pt-meta` | `#86868b` | 3.62:1 | **仅**非文本（描边/图标）与 ≥24px 大字 |
| `--pt-ink-inverse` | `#f5f5f7` | 19.29:1（对 `#000`） | 深色章节文字 |
| `--pt-border` | `#d2d2d7` | 1.29:1 | 装饰性分隔线、卡片边 |
| `--pt-border-soft` | `#e8e8ed` | 1.16:1 | 表格行线、内部分隔 |
| `--pt-border-strong` | `#86868b` | 3.62:1 | 控件边框（满足 3:1 非文本对比） |
| `--pt-border-inverse` | `rgba(255,255,255,.16)` | — | 黑底分隔线 |

### 3.3 强调与链接

| token | 值 | 用途 | 实测 |
| --- | --- | --- | --- |
| `--pt-accent` | `#0071e3` | 主按钮填充、焦点环、当前项 | 白字 4.70:1（AA） |
| `--pt-accent-hover` | `#0066cc` | 主按钮悬停 | 白字 5.57:1 |
| `--pt-accent-active` | `#005bb5` | 主按钮按下 | 白字 6.64:1 |
| `--pt-accent-on` | `#ffffff` | 主按钮文字 | — |
| `--pt-link` | `#0066cc` | 正文内链接、文字操作 | 白底 5.57:1；浅灰底 5.11:1 |
| `--pt-link-inverse` | `#2997ff` | 黑底链接 | 6.96:1 |
| `--pt-focus` | `#0071e3` | `:focus-visible` 外环 | 4.70:1（≥3:1） |
| `--pt-focus-halo` | `rgba(0,113,227,.24)` | 4px 柔光外环 | 辅助，不单独承担可见性 |

> 为什么 hover 变深而不是变浅：Apple 原包用 `#0077ed`（更亮），白字只有 4.32:1，不达 AA。规范统一取深一档，保留"可点"的视觉增量，不放宽对比度。

### 3.4 语义色（文本档 / 底档 / 实心档分开）

| 语义 | 文本 token | 底 token | 实心 token | 实测 |
| --- | --- | --- | --- | --- |
| 成功 | `--pt-success` `#146c33` | `--pt-success-bg` `#e7f5ec` | `--pt-success-solid` `#15803d` | 文本/底 5.79:1；白字/实心 5.02:1 |
| 警告 | `--pt-warn` `#8a5a00` | `--pt-warn-bg` `#fff8e1` | `--pt-warn-solid` `#b45309` | 文本/底 5.58:1；白字/实心 5.02:1 |
| 危险 | `--pt-danger` `#b42318` | `--pt-danger-bg` `#fdecea` | `--pt-danger-solid` `#dc2626` | 文本/底 5.75:1；白字/实心 4.83:1 |
| 信息 | `--pt-info` `#0066cc` | `--pt-info-bg` `#eaf2fd` | — | 4.94:1 |
| 中性 | `--pt-neutral-fg` `#424245` | `--pt-neutral-bg` `#f5f5f7` | — | 9.20:1 |

规则：

- **文本档**永远比**实心档**深一档；浅底上的文字只用文本档，实心填充配白字。
- 状态色不得单独承担语义：`StatusTag` 必须带文字，颜色是冗余。
- 禁用态统一 `#f5f5f7` 底 + `#86868b` 字，属 WCAG 免除项，但需 `aria-disabled` 或 `disabled`。

### 3.5 明确禁止

- `#eab308` 作为文字（白底 1.92:1）或浅底上的文字。
- `#dc2626` 文字压 `#fdecea`（4.22:1）——用 `#b42318`。
- `#86868b` 做正文、表格正文或 12px 标签；它只做描边、图标与 ≥24px 辅助字。
- 两套强调色并存（旧藏青 + Apple 蓝）；迁移期只允许一个页面一套。
- 用颜色表达"已复核/未复核"而不写文字；用蓝色表示"装饰"。
- 大面积黑底出现在工作台数据区（黑只属于首屏、空状态、报告封面）。

## 4. 排版

### 4.1 字体栈与许可

| 角色 | 栈 | 许可/落地 |
| --- | --- | --- |
| 正文与控件 | `Inter`, `SF Pro Text`, `Noto Sans SC`, `Microsoft YaHei`, `system-ui` | Inter 为 SIL OFL；Noto Sans SC 为 SIL OFL；两者**自托管 woff2**，禁止字体 CDN |
| 展示标题 | `Inter Tight`, `Inter`, `SF Pro Display`, `Noto Sans SC`, … | Inter Tight 为 SIL OFL；缺字时回落 Noto Sans SC |
| 等宽 | `SF Mono`, `JetBrains Mono`, `ui-monospace`, `Consolas` | 只用于哈希、包名、URL、代码 |
| 引文（可选） | `Noto Serif SC`, `Songti SC`, serif | 仅长文引用块，不用于标题/控件；默认不启用 |

SF Pro 只作为本机首选名回退，**不随包分发**。实施时新增 `apps/web/public/fonts/InterVariable.woff2` 与 `InterTight-Variable.woff2`，`font-display: swap`，并保留现有 Noto Sans SC 变量字体文件与 OFL 许可记录。

### 4.2 字号阶梯

| 角色 | size | line-height | weight | tracking | 用途 |
| --- | --- | --- | --- | --- | --- |
| `display-xl` | 56px | 1.02 | 600 | -0.03em | 首屏主标题（≤1 处/页） |
| `display-l` | 48px | 1.05 | 600 | -0.025em | 空状态主标题 |
| `display-m` | 40px | 1.08 | 600 | -0.02em | 报告封面标题 |
| `title-l` | 28px | 1.14 | 600 | -0.01em | 页面标题（桌面） |
| `title-m` | 24px | 1.20 | 600 | -0.005em | 分区标题、移动页标题 |
| `title-s` | 19px | 1.32 | 600 | 0 | 卡片标题、面板标题 |
| `body-l` | 17px | 1.75 | 400 | 0 | 报告阅读、政策正文 |
| `body` | 15px | 1.60 | 400 | 0 | 工作台正文、表格正文 |
| `control` | 14px | 1.43 | 400 | -0.006em | 按钮、字段、标签、导航 |
| `micro` | 12px | 1.35 | 400 | 0.01em | 元数据、行内说明 |
| `legal` | 11px | 1.45 | 400 | 0.01em | 法务、极小注（不承载关键信息） |

规则：

- 中文正文行高不低于 1.5；`body` 15px → 24px 行高；`body-l` 17px → 30px。
- 展示级（≥40px）允许负字距；中文展示标题负字距不超过 `-0.02em`，避免字挤。
- 数字对齐：表格数字、计数、版本号加 `font-variant-numeric: tabular-nums`。
- 不在同一屏并列两个 `display` 级标题；`display` 只出现在章节入口。
- 旧规范中的衬线页面标题（Noto Serif SC 28/40）取消，统一 `title-l` 无衬线；`heading` 的 40px 行高改为 32px。

### 4.3 长文本与断行

- 哈希、包名、URL 用等宽 + `overflow-wrap: anywhere`；容器宽度不足时优先换行，禁止横向滚动。
- 政策正文用 `body-l`，段落间距 `--pt-space-16`，段内不缩进；引用块左侧 2px `--pt-border` + `--pt-space-16` 内边距。
- 中文与拉丁混排：Inter 与 Noto Sans SC 之间由字体栈回退控制，不手工插空格；标点用全角。

## 5. 间距、布局与章节节奏

### 5.1 间距

4px 基数、8px 节奏：

`2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 120`

| 场景 | 值 |
| --- | --- |
| 图标与文字 | 8 |
| 控件内边距（水平） | 16（默认）/ 20（大按钮） |
| 字段组间距 | 16 |
| 卡片内边距 | 20（紧凑）/ 24（默认） |
| 分区上下留白（桌面） | 96 / 120 |
| 分区上下留白（移动） | 48 / 64 |
| 章节过渡 | 120（黑↔浅灰↔白） |

### 5.2 容器与栅格

| 容器 | 宽度 | 用途 |
| --- | --- | --- |
| 工作台 | 1200px | 列表、表格、双栏证据 |
| 阅读 | 880px | 报告正文、政策对照 |
| 表单 | 640px | 导入、设置、单任务流 |

- 桌面 12 列 / 间距 24 / 边距 24；平板 8 列 / 间距 20 / 边距 24；移动 4 列 / 间距 16 / 边距 16。
- 表格与证据列表允许满宽，但正文列不超过 880px。
- 不做全宽 4K 拉伸：>1440px 只增外边距。

### 5.3 章节节奏（三种表面，一套语言）

| 表面 | 用法 | 限制 |
| --- | --- | --- |
| 黑 `#000000` | 首屏、空状态、报告封面 | 单页 ≤1 段；不进入工作台数据区 |
| 浅灰 `#f5f5f7` | 分区带、说明区、只读信息、分段控件槽 | 可与白交替，形成章节呼吸 |
| 白 `#ffffff` | 表格、表单、卡片、正文 | 默认工作表面 |

深色章节内的文字用 `--pt-ink-inverse`，链接用 `--pt-link-inverse`，描边用 `--pt-border-inverse`；不要在白底语义下复用黑底颜色。

## 6. 圆角、描边与层级

### 6.1 圆角分级

| token | 值 | 用途 |
| --- | --- | --- |
| `--pt-radius-tag` | 5px | 状态标签、微型容器 |
| `--pt-radius-control` | 8px | 按钮、分段控件容器、输入内元素 |
| `--pt-radius-field` | 12px | 输入框、select、小面板 |
| `--pt-radius-card` | 18px | 卡片、对话框、面板 |
| `--pt-radius-sheet` | 28px | 移动 bottom sheet 顶部 |
| `--pt-radius-capsule` | 56px | 首屏/空状态胶囊按钮 |
| `--pt-radius-pill` | 980px | 极长胶囊（仅首屏 CTA） |
| `--pt-radius-circle` | 50% | 图标按钮、媒体控件 |

不允许"全站一个圆角"。同一组件类固定一档；胶囊只用于强调型 CTA，不用于工作台密集按钮。

### 6.2 描边

- 控件：1px `--pt-border-strong`（3.62:1，满足非文本对比）。
- 卡片/面板：1px `--pt-border-soft`。
- 表格行线：1px `--pt-border-soft`，最后一行不加线。
- 焦点：`outline: 2px solid var(--pt-focus); outline-offset: 2px;` + `box-shadow: 0 0 0 4px var(--pt-focus-halo)`。
- 不用 2px 以上的彩色边框做装饰；不用内阴影模拟凹陷。

### 6.3 层级

| 层级 | 处理 | 用途 |
| --- | --- | --- |
| L0 | 平面 + 表面色差 | 主内容、表格、正文 |
| L1 | 1px 描边 | 卡片、字段、只读面板 |
| L2 | `0 4px 16px rgba(0,0,0,.06), 0 1px 3px rgba(0,0,0,.04)` | 可点卡片悬停 |
| L3 | `0 12px 40px rgba(0,0,0,.16)` | 对话框、桌面浮层 |
| L4 | `0 -8px 48px rgba(0,0,0,.22)` | 移动 bottom sheet（向上投影） |
| 遮罩 | `rgba(0,0,0,.40)` | 模态背景；不再用带色遮罩 |

## 7. 组件

所有组件：`box-sizing: border-box`；无 `transition: all`；可见焦点；禁用不进 Tab 序列（原生 `disabled`）或 `aria-disabled` 且不可激活。

### 7.1 按钮 `ui-button`

| 属性 | 紧凑 | 默认 | 触屏 |
| --- | --- | --- | --- |
| 高度 | 32 | 36 | 44（移动 Web）/ 48（Android 壳） |
| 水平内边距 | 12 | 16 | 16 |
| 字号/字重 | 14 / 500 | 14 / 500 | 14 / 500 |
| 圆角 | 8 | 8 | 8（胶囊仅 CTA） |

变体：

| 变体 | 默认 | 悬停 | 按下 | 焦点 | 禁用 | 等待 |
| --- | --- | --- | --- | --- | --- | --- |
| primary | 蓝底白字 | `--pt-accent-hover` | `--pt-accent-active` + `scale(.98)` | 2px 环 | 灰底灰字 | 文案不变 + 16px 旋转指示 + `aria-busy` |
| secondary | 白底 + 1px 强描边 + 墨字 | 底 `#f5f5f7`、描边转墨色 | `scale(.98)` | 同上 | 同 primary | 同 primary |
| quiet | 链接蓝文字，无底 | 下划线 + `#005bb5` | 下划线保持 | 同上 | 灰字 | 文字 + 指示 |
| danger | `#dc2626` 底白字 | `#b42318` | `#991b1b` + `scale(.98)` | 同上 | 灰底灰字 | 同 primary |

- primary 一屏只应有一个；同组操作 ≥3 个时改用 secondary/quiet。
- 等待态不改变按钮宽度（用固定最小宽或占位指示），避免布局跳动。
- 胶囊按钮（`--pt-radius-capsule`）只用于首屏与空状态的主 CTA。

### 7.2 字段 `ui-field`

- 高度 40 桌面 / 48 移动 Web / 56 Android；圆角 12；底白；1px `--pt-border-strong`。
- 字号来源：桌面 14；移动 Web 输入 16（防 iOS 聚焦缩放）；Android 16。
- 标签 14/500 墨色，与输入间距 8；帮助 12 `--pt-muted`；错误 12 `--pt-danger` 并 `aria-describedby` 关联。
- 焦点：描边转 `--pt-accent` + 2px 外环 + 4px 柔光；不改变布局尺寸。
- 错误：描边 `--pt-danger`，错误文案不依赖颜色（带文字/图标）。
- 禁用：底 `#f5f5f7`、字 `#86868b`、无焦点环。
- 占位符用 `--pt-muted`，`opacity: 1`（不用浏览器默认浅灰）。

### 7.3 状态标签 `status-tag`

| tone | 文字 | 底 | 说明 |
| --- | --- | --- | --- |
| neutral | `#424245` | `#f5f5f7` | 未知/未开始/中性元数据 |
| info | `#0066cc` | `#eaf2fd` | 进行中、信息性判定 |
| wait | `#8a5a00` | `#fff8e1` | 等待、待复核、排队 |
| success | `#146c33` | `#e7f5ec` | 已完成/已复核，必须有文字事实 |
| error | `#b42318` | `#fdecea` | 失败/冲突/解析错误 |

- 几何：高 22，水平内边距 8，圆角 5，字号 12/500；不使用纯实心高饱和底。
- 标签不可交互（不承担点击），不做成按钮。

### 7.4 卡片 `card`

- 白底、1px `--pt-border-soft`、圆角 18、内边距 24（紧凑 20）。
- 默认无阴影；仅可点击卡片在 `hover` 时上移 1px + L2 阴影，200ms。
- 标题 19/600；元信息 12 `--pt-muted`；正文 15。
- 卡片内不再嵌套第二层卡片；需要分组用 1px 分隔线 + 16 间距。

### 7.5 顶部导航

- 桌面 44，移动 Web 56，Android 壳 56（沿用现合同）。
- 玻璃：`background: rgba(255,255,255,.72); backdrop-filter: blur(20px) saturate(180%)`；底部 1px `rgba(0,0,0,.08)`。
- 深色章节变体：`rgba(0,0,0,.72)` + `--pt-border-inverse` + `--pt-ink-inverse`。
- 标题居中或左对齐二选一，全站一致；不放大标题抢占内容。
- 不可用透明度低于 0.72 的玻璃，避免正文穿透干扰。

### 7.6 分段控件 `segmented`

- 槽：`#f5f5f7`、圆角 8、内边距 2；项：高 28（紧凑）/ 32，圆角 6，14/500。
- 选中项白底 + L1 阴影 + 墨字；未选中 `--pt-muted`。
- 用于 2–5 个互斥视图切换；超过 5 个改用下拉或标签页。

### 7.7 表格与证据列表

- 行高 44 桌面 / 56 移动（两行时按内容）；表头 12/600 `--pt-muted`、`letter-spacing: .02em`、白底、吸顶。
- 行线 1px `--pt-border-soft`；悬停行 `#fbfbfd`；选中行 `#f5f5f7` + 左侧 2px `--pt-accent` 内嵌标记。
- 数字右对齐 + `tabular-nums`；长哈希/包名等宽且可断行。
- 排序/筛选等控件 32 高，出现在表头上方一行，不与表头混排。

### 7.8 对话框与 bottom sheet

| | 对话框（桌面） | bottom sheet（移动） |
| --- | --- | --- |
| 表面 | 白 | 白 |
| 圆角 | 18 | 28（顶部两角） |
| 阴影 | L3 | L4 |
| 遮罩 | `rgba(0,0,0,.40)` | 同 |
| 宽度/高度 | 560（max） | `min(100%, 640px)`，`max-height: 88dvh` |
| 内边距 | 24 | 20，含 `env(safe-area-inset-bottom)` |
| 关闭 | 右上 44×44 | 顶部把手 36×4 + 关闭 48×48 |
| 焦点 | 初始聚焦首控件；关闭后归还触发点 | 同 |

- Esc、点遮罩、显式关闭都要可用；点击外部不丢弃已填内容（沿用现约定）。
- 遮罩不用带色（旧 `rgba(44,53,71,.42)` 退役）。

### 7.9 空状态与首屏

- 黑或 `#f5f5f7` 章节；`display-l` 标题 + `body-l` 说明 + 一个胶囊主 CTA，最多一个次链接。
- 不堆插画、不使用 emoji；图标最多一个 24px 线性图标。
- 空状态文案必须说明"下一步做什么"，不写营销形容词。

## 8. 响应式与移动壳

### 8.1 断点

| 断点 | 宽度 | 行为 |
| --- | --- | --- |
| compact | ≤320 | 单列、边距 16、按钮 44、隐藏非必要列 |
| mobile | 321–640 | 单列、卡片纵排、触控 44、输入 16 |
| tablet | 641–833 | 1–2 列、边距 24 |
| desktop | 834–1023 | 双栏开始、表格完整列 |
| wide | 1024–1240 | 工作台 1200 容器、三栏证据 |
| large | ≥1441 | 只增外边距，不拉伸正文 |

验收尺寸 320 / 390 / 768 / 1024 / 1440 保持不变；Apple 的 374/640/833/1023/1240 只作为行为拐点，不对应新验收视口。

### 8.2 移动硬约束（沿用并加严）

- 触控目标 ≥44 CSS px（移动 Web），Android 壳 ≥48；相邻目标间距 ≥8。
- 输入 16px 起，防 iOS 聚焦缩放；200% 根字号下不出现页面级横向溢出。
- `100dvh` + `env(safe-area-inset-*)`；软键盘弹起时主操作仍可达。
- 横屏与平板（`pointer: coarse`）同样按触控尺寸，不因宽度变大退回鼠标尺寸。
- 报告阅读在移动端用 `body-l` 17/1.75，单行不出现超长 URL 溢出。

## 9. 动效

| token | 值 | 用途 |
| --- | --- | --- |
| `--pt-duration-fast` | 120ms | 按下、悬停颜色 |
| `--pt-duration-base` | 200ms | 常规状态切换 |
| `--pt-duration-slow` | 300ms | 面板/章节进入 |
| `--pt-duration-exit` | 200ms | 关闭、退场（比进入快） |
| `--pt-ease-standard` | `cubic-bezier(.2,0,0,1)` | 默认减速 |
| `--pt-ease-emphasized` | `cubic-bezier(.16,1,.3,1)` | 浮层进入 |
| `--pt-ease-exit` | `cubic-bezier(.4,0,1,1)` | 浮层退场 |

- 只允许 `transform`、`opacity`、`background-color`、`border-color`、`box-shadow` 过渡。
- 不使用 `transition: all`；不自动播放装饰动画。
- `prefers-reduced-motion: reduce` 下时长归零、取消位移与缩放，保留即时可见状态。
- 按压反馈立即生效（不加缓动），释放时按 base 时长回落。

## 10. 无障碍

- 正文对比度 ≥4.5:1；大字（≥24px 或 ≥19px 加粗）与图形/控件边界 ≥3:1。
- 焦点：`:focus-visible` 2px 环 + 2px 偏移，任何背景可见；不用 `outline: none`。
- 语义：状态标签带文字；错误用文字 + `aria-describedby`；图标 `aria-hidden`。
- 键盘：Tab 顺序符合阅读顺序；对话框焦点循环与 Esc；关闭后焦点归还触发点。
- 缩放：200% 根字号、320px 宽度下无横向滚动、无内容裁切；文本可重排。
- 动效偏好、对比度模式（`forced-colors`）下保留边界与焦点。
- 颜色不作为唯一编码：所有状态、成功/失败、选中态都有文字或形状冗余。

## 11. Pioneer → Apple 迁移

### 11.1 token 映射

| 旧 token（Pioneer） | 旧值 | 新 token（Apple） | 新值 | 说明 |
| --- | --- | --- | --- | --- |
| `--canvas` | `#f6f5f1` | `--pt-bg-subtle` | `#f5f5f7` | 暖灰退场 |
| `--surface` | `#fdfcfa` | `--pt-surface` | `#ffffff` | 近白改纯白 |
| `--surface-muted` | `#eeedea` | `--pt-bg-subtle` | `#f5f5f7` | 与画布合并 |
| `--ink` | `#2c3547` | `--pt-ink` | `#1d1d1f` | 藏青墨改中性墨 |
| `--muted` | `#64696f` | `--pt-muted` | `#6e6e73` | 对比度 5.07:1 |
| `--navy` | `#333c50` | `--pt-accent` | `#0071e3` | 主操作换蓝，藏青退役 |
| `--border` | `#d9d7d2` | `--pt-border` | `#d2d2d7` | 冷灰取代暖灰 |
| `--control` | `#858d92` | `--pt-border-strong` | `#86868b` | 控件边框 |
| `--mint` | `#dce9df` | `--pt-success-bg` | `#e7f5ec` | 成功底 |
| `--success` | `#35644b` | `--pt-success` | `#146c33` | 文本档 |
| `--slate` | `#dde2e9` | `--pt-info-bg` | `#eaf2fd` | 信息底 |
| `--notice` | `#ede4d6` | `--pt-warn-bg` | `#fff8e1` | 等待底 |
| `--rose` | `#ebdada` | `--pt-danger-bg` | `#fdecea` | 危险底 |
| `--error` | `#934342` | `--pt-danger` | `#b42318` | 文本档 |
| `--navy-hover` | `#212a3b` | `--pt-accent-hover` | `#0066cc` | 悬停 |
| `--danger` | `#b25352` | `--pt-danger-solid` | `#dc2626` | 实心危险 |
| `--gold` | `#c6af94` | 退役 | — | Apple 体系无琥珀强调色；警告用语义档 |
| `--on-action` | `#f9f9f9` | `--pt-accent-on` | `#ffffff` | 反白文字 |
| `--overlay` | `rgba(44,53,71,.3)` | `--pt-scrim` | `rgba(0,0,0,.4)` | 无彩遮罩 |
| `--radius` | `8px` | `--pt-radius-control` | `8px` | 值不变、语义收窄 |
| `--radius-panel` | `12px` | `--pt-radius-field` / `--pt-radius-card` | `12px` / `18px` | 面板拆成字段与卡片两档 |
| `--font-display` | Noto Serif SC | `--pt-font-display` | Inter Tight → Noto Sans SC | 衬线标题退役 |
| `--font-body` | Noto Sans SC 14px | `--pt-font-sans` + `body` | Inter + Noto Sans SC 15px | 双字体分工、正文加 1px |
| heading | 28/40 | `title-l` | 28/32 | 行高收紧 |
| mobile heading | 24/34 | `title-m` | 24/29 | 行高收紧 |
| `--m-sheet-radius` | `20px` | `--pt-radius-sheet` | `28px` | 更接近 Apple sheet |
| `--m-card-radius` | `12px` | `--pt-radius-card` | `18px` | 卡片统一 |
| `--m-touch` | `48px` | `--pt-touch-android` | `48px` | 值不变 |
| `--m-appbar-height` | `56px` | `--pt-appbar` | `56px` | 值不变 |
| `--m-font-title` | `20px` | `title-s` | `19px` | 层级微调 |

### 11.2 会影响到的契约与验收（实施阶段）

- `scripts/fixtures/pioneer-design.json`：颜色角色、`heading.fontFamily`、正文 14px、按钮/字段 8px 圆角、`mobile.sheetRadius` 都需按本规范更新，并与新 token 交叉校验。
- `scripts/verify-frontend-flow.cjs` 的 `assertDesign` 会断言旧字体、字号、配色、圆角；实施时必须逐项改到新值，**不能**为了过测把断言删掉。
- 截图与视觉基线：全部重拍；旧截图不覆盖，作为历史证据保留。
- 具体失败项清单由当时的现状审计给出（`apple-reset/current-audit.md`，未包含在归档中）。

### 11.3 建议实施顺序

1. token 层：新建 `--pt-*` 变量与 Inter 字体文件，旧变量保留别名指向新值，保证页面仍可用。
2. 基础组件：按钮、字段、状态标签、卡片、分段控件、导航；一次只改一个组件并跑该组件的断言。
3. 工作台与桌面壳：背景、表格行高、圆角、焦点环。
4. 移动壳：sheet 圆角/阴影、触控、safe-area、输入字号。
5. 页面级：导入、候选、进度、报告、设置；报告阅读切 `body-l`。
6. 契约与验收：更新 `pioneer-design.json` 与 `assertDesign`，重拍截图，跑 `scripts/check.sh` 与前端验收。
7. 删除旧别名与 `--gold` 等退役 token。

## 12. 验收清单

- [ ] 除 token 文件外，产品样式无硬编码 16 进制颜色（`grep -rIn "#[0-9a-fA-F]\{3,6\}" apps/web/src --include=*.css` 只命中变量文件）。
- [ ] 正文对比度 ≥4.5:1；控件边框 ≥3:1；焦点环在任意背景可见。
- [ ] 320 / 390 / 768 / 1024 / 1440 五档无页面级横向溢出；200% 根字号仍成立。
- [ ] 移动 Web 触控 ≥44、Android 壳 ≥48；移动输入 16px。
- [ ] `prefers-reduced-motion: reduce` 下无动画、无位移。
- [ ] 状态标签、错误提示、选中态都有文字或形状冗余，不靠颜色。
- [ ] 深色章节只出现在首屏/空状态/报告封面。
- [ ] 无字体 CDN 请求；Inter 与 Noto Sans SC 自托管。
- [ ] 焦点顺序与阅读顺序一致；对话框 Esc/遮罩/关闭可用，焦点归还。
- [ ] 契约快照与新 token 值一致；`scripts/check.sh` 通过。
- [ ] 新旧截图并存，历史证据未被覆盖。

## 13. 限制与未覆盖

- 本轮只定规范，**没有改任何产品代码、样式、契约或验收脚本**；上面所有新值都是目标态，不是现状。
- 没有做浏览器实机验收、真机（Android/iOS）验证、读屏人工测试；对比度是按 WCAG 公式计算的静态值，不替代实机检查。
- 字体文件未下载、未加入仓库；发布前需核对 Inter / Noto 的 OFL 文本与文件来源。
- 用户审美认可不在本规范能力范围内；规范和规范站的通过，只代表规则自洽与可执行。

## 14. 来源与许可

- Apple 设计体系：EAC 库条目 `od-ds-apple`，OpenDesign 打包（v0.25.1），MIT；派生自 apple.com 首页、Environment、Store、购买页与配件页。本文引用其 `DESIGN.md`、`tokens.css`、`design-tokens.json` 的角色与数值，不复制其图像资源。
- Pioneer：旧规范来源，保留在 [issue-44 provenance](../issue-44-provenance.md) 与 [issue142](../issue142-theme-and-primitives.md)，作为历史记录。
- 字体：Inter / Inter Tight（SIL OFL 1.1）、Noto Sans SC / Noto Serif SC（SIL OFL 1.1）；SF Pro 为 Apple 系统字体，不分发。
- 对比度计算：WCAG 2.1 相对亮度公式，脚本与结果见附录 B。

## 附录 A：CSS token 草案

```css
:root {
  /* 结构 */
  --pt-bg: #ffffff; --pt-bg-subtle: #f5f5f7; --pt-bg-inverse: #000000;
  --pt-surface: #ffffff; --pt-surface-raised: #fbfbfd;
  --pt-graphite: #272729; --pt-graphite-2: #2a2a2c;

  /* 文字 */
  --pt-ink: #1d1d1f; --pt-ink-2: #424245; --pt-muted: #6e6e73;
  --pt-meta: #86868b; --pt-ink-inverse: #f5f5f7;

  /* 描边 */
  --pt-border: #d2d2d7; --pt-border-soft: #e8e8ed; --pt-border-strong: #86868b;
  --pt-border-inverse: rgba(255,255,255,.16);

  /* 强调 */
  --pt-accent: #0071e3; --pt-accent-hover: #0066cc; --pt-accent-active: #005bb5;
  --pt-accent-on: #ffffff; --pt-link: #0066cc; --pt-link-inverse: #2997ff;
  --pt-focus: #0071e3; --pt-focus-halo: rgba(0,113,227,.24);

  /* 语义 */
  --pt-success: #146c33; --pt-success-bg: #e7f5ec; --pt-success-solid: #15803d;
  --pt-warn: #8a5a00; --pt-warn-bg: #fff8e1; --pt-warn-solid: #b45309;
  --pt-danger: #b42318; --pt-danger-bg: #fdecea; --pt-danger-solid: #dc2626;
  --pt-info: #0066cc; --pt-info-bg: #eaf2fd;
  --pt-neutral-fg: #424245; --pt-neutral-bg: #f5f5f7;

  /* 遮罩与阴影 */
  --pt-scrim: rgba(0,0,0,.4);
  --pt-shadow-1: 0 1px 2px rgba(0,0,0,.04);
  --pt-shadow-2: 0 4px 16px rgba(0,0,0,.06), 0 1px 3px rgba(0,0,0,.04);
  --pt-shadow-3: 0 12px 40px rgba(0,0,0,.16);
  --pt-shadow-4: 0 -8px 48px rgba(0,0,0,.22);

  /* 字体 */
  --pt-font-sans: "Inter", "SF Pro Text", "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
  --pt-font-display: "Inter Tight", "Inter", "SF Pro Display", "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
  --pt-font-reading: "Noto Serif SC", "Songti SC", serif;
  --pt-font-mono: "SF Mono", "JetBrains Mono", ui-monospace, Consolas, monospace;

  /* 字号 */
  --pt-text-display-xl: 56px; --pt-text-display-l: 48px; --pt-text-display-m: 40px;
  --pt-text-title-l: 28px; --pt-text-title-m: 24px; --pt-text-title-s: 19px;
  --pt-text-body-l: 17px; --pt-text-body: 15px; --pt-text-control: 14px;
  --pt-text-micro: 12px; --pt-text-legal: 11px;

  /* 间距 */
  --pt-space-2: 2px; --pt-space-4: 4px; --pt-space-8: 8px; --pt-space-12: 12px;
  --pt-space-16: 16px; --pt-space-20: 20px; --pt-space-24: 24px; --pt-space-32: 32px;
  --pt-space-40: 40px; --pt-space-48: 48px; --pt-space-64: 64px; --pt-space-80: 80px;
  --pt-space-96: 96px; --pt-space-120: 120px;

  /* 圆角 */
  --pt-radius-tag: 5px; --pt-radius-control: 8px; --pt-radius-field: 12px;
  --pt-radius-card: 18px; --pt-radius-sheet: 28px; --pt-radius-capsule: 56px;
  --pt-radius-pill: 980px; --pt-radius-circle: 50%;

  /* 动效 */
  --pt-duration-fast: 120ms; --pt-duration-base: 200ms; --pt-duration-slow: 300ms;
  --pt-duration-enter: 300ms; --pt-duration-exit: 200ms;
  --pt-ease-standard: cubic-bezier(.2, 0, 0, 1);
  --pt-ease-emphasized: cubic-bezier(.16, 1, .3, 1);
  --pt-ease-exit: cubic-bezier(.4, 0, 1, 1);

  /* 布局与触控 */
  --pt-container-workbench: 1200px; --pt-container-reading: 880px; --pt-container-form: 640px;
  --pt-gutter: 24px; --pt-gutter-mobile: 16px;
  --pt-navbar: 44px; --pt-appbar: 56px;
  --pt-touch-web: 44px; --pt-touch-android: 48px;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --pt-duration-fast: 0ms; --pt-duration-base: 0ms; --pt-duration-slow: 0ms;
    --pt-duration-enter: 0ms; --pt-duration-exit: 0ms;
  }
}
```

## 附录 B：对比度计算

脚本（Node，仓库根目录可直接运行）：

```bash
node -e "const h=x=>x.replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(c=>c<=.03928?c/12.92:((c+.055)/1.055)**2.4);const L=x=>{const[r,g,b]=h(x);return .2126*r+.7152*g+.0722*b};const cr=(a,b)=>{const l=[L(a),L(b)].sort((x,y)=>y-x);return ((l[0]+.05)/(l[1]+.05)).toFixed(2)};for(const[a,b]of[['#1d1d1f','#ffffff'],['#6e6e73','#ffffff'],['#86868b','#ffffff'],['#0071e3','#ffffff'],['#0066cc','#ffffff'],['#146c33','#e7f5ec'],['#8a5a00','#fff8e1'],['#b42318','#fdecea'],['#ffffff','#0071e3'],['#ffffff','#15803d'],['#ffffff','#dc2626'],['#2997ff','#000000']])console.log(a,'on',b,cr(a,b))"
```

| 组合 | 比值 | 结论 |
| --- | --- | --- |
| `#1d1d1f` / `#ffffff` | 16.83 | AA / AAA |
| `#424245` / `#ffffff` | 10.01 | AA / AAA |
| `#6e6e73` / `#ffffff` | 5.07 | AA |
| `#6e6e73` / `#f5f5f7` | 4.66 | AA |
| `#86868b` / `#ffffff` | 3.62 | 仅非文本/大字 |
| `#0071e3` / `#ffffff` | 4.70 | AA（文字） |
| `#0066cc` / `#ffffff` | 5.57 | AA |
| `#ffffff` / `#0071e3` | 4.70 | AA |
| `#ffffff` / `#0066cc` | 5.57 | AA |
| `#ffffff` / `#005bb5` | 6.64 | AA |
| `#146c33` / `#e7f5ec` | 5.79 | AA |
| `#ffffff` / `#15803d` | 5.02 | AA |
| `#8a5a00` / `#fff8e1` | 5.58 | AA |
| `#ffffff` / `#b45309` | 5.02 | AA |
| `#b42318` / `#fdecea` | 5.75 | AA |
| `#ffffff` / `#dc2626` | 4.83 | AA |
| `#2997ff` / `#000000` | 6.96 | AA |
| `#f5f5f7` / `#000000` | 19.29 | AAA |
| `#0077ed` / `#ffffff`（白字） | 4.32 | **不通过**，故禁用 |
| `#eab308` / `#ffffff` | 1.92 | **不通过**，故禁用为文字 |
| `#dc2626` / `#fdecea` | 4.22 | **不通过**，改用 `#b42318` |
| `#86868b` / `#e8e8ed` | 2.97 | **不通过**，不可作文字 |
