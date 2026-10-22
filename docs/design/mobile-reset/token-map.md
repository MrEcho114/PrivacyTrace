# PrivacyTrace 移动端 token 映射表（Pioneer / round2 → Claude 移动基线）

> 契约版本 **0.1.0** · baseline **od-ds-claude** · scope **mobile-app-only**
> 机器可读契约：[`mobile-design.tokens.json`](mobile-design.tokens.json)
> 对比度实算：`node docs/design/mobile-reset/contrast.mjs`
> 只读现状：[`apps/web/src/theme.css`](../../../apps/web/src/theme.css)、[`apps/web/src/mobile/mobile.css`](../../../apps/web/src/mobile/mobile.css)、[`scripts/fixtures/pioneer-design.json`](../../../scripts/fixtures/pioneer-design.json)、[`verify-frontend-flow.cjs`](../../../scripts/verify-frontend-flow.cjs)、[`verify-frontend-round2.cjs`](../../../scripts/verify-frontend-round2.cjs)

## 0. 读法与迁移策略

- **旧值**取自 `apps/web/src/theme.css` 与设计 fixture 的当前真值；**新值**已在 2026-10-23 两轮迁移落地（第二轮起共享组件经 `--ui-*` 语义别名取 `--mt-*`），本表保留 raw token 映射，别名清单见规范 §11.3。
- **新变量**统一使用 `--mt-*` 命名空间；JSON 的键去掉 `--mt-` 前缀即得（深色章节的 CSS 名例外，见 `meta.cssVarOverrides`）。
- **字号命名**：字号统一使用 `--mt-text-*`（如 `--mt-text-caption`），避免与颜色 `--mt-caption` 同名覆盖；颜色仍写 `--mt-caption`。
- 迁移期采用**作用域双调色板**：桌面 `:root` 旧变量保持旧值；移动根 `.mobile-workspace` 使用 `--mt-*`；共享组件消费语义别名（桌面映射 Pioneer，移动映射 `--mt-*`）。旧别名**不**指向新值，桌面断言先保绿。详见 **D3**。
- 旧变量被拆分或合并时，在「迁移备注」里写明职责去向；不要把一个旧变量机械地替换成同名新变量。
- 本文件只列迁移与验收影响，**不修改**产品代码、fixture、断言或截图。
- **映射行数**：121 行（颜色 46 / 字体与字号 21 / 间距圆角 28 / 移动壳几何 17 / 动效 9）；`contrast` 共 31 组，29 组通过、2 条暖砂组合按 **D1** 保持 `pass:false`（禁用态豁免）。

---

## 1. 颜色

### 1.1 旧变量 → 新变量

| 旧变量 / 旧值 | 新变量 | 新值 | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--canvas` `#f6f5f1` | `--mt-bg` | `#f5f4ed` | App 主画布 | 冷灰白换暖纸底；桌面冻结后只服务移动壳 |
| `--surface` `#fdfcfa` | `--mt-surface` | `#faf9f5` | 卡片、面板、输入、sheet | 与画布只差一档，靠 1px 描边分层 |
| `--surface-muted` `#eeedea` | `--mt-surface-warm` | `#e8e6dc` | 禁用底、骨架、次要分区带 | 旧变量也当面板底用；面板底改 `--mt-surface`，暖砂只给禁用/骨架/分区带 |
| `--ink` `#2c3547` | `--mt-fg` | `#141413` | 标题、主正文、关键值 | 藏青黑换暖黑；对卡片 17.50:1 |
| `--muted` `#64696f` | `--mt-muted` | `#5e5d59` | 辅助说明、来源行副文案 | 新增 `--mt-fg-2` / `--mt-caption` 两级（见 1.2），旧 muted 不要一律当 caption |
| `--navy` `#333c50`（实心底 / 主操作） | `--mt-accent-strong` | `#b04b25` | 主按钮实心底、需要 AA 的强调面 | 藏青不再作强调色；象牙白字 5.14:1 |
| `--navy` `#333c50`（文字 / 图标 / 链接） | `--mt-accent-text` | `#a8431f` | 文字操作、链接、quiet 按钮 | 旧 navy 的文字用法拆到这里；对画布 5.46:1 |
| `--navy-hover` `#212a3b` | `--mt-accent-strong-hover` | `#a24522` | primary hover | 仅 `(hover: hover) and (pointer: fine)`；active 用 `--mt-accent-strong-active` |
| `--border` `#d9d7d2` | `--mt-border` | `#f0eee6` | 装饰分隔、行内线 | 旧 border 同时承担控件边；控件边拆到 `--mt-border-control` |
| `--control` `#858d92` | `--mt-border-control` | `#87867f` | 按钮、字段、关闭键的可见边界 | 非文本 3.47:1 ≥3；仍不得做正文或 12px 标签 |
| `--mint` `#dce9df` | `--mt-success-bg` | `#eef6e8` | 成功底 | 配 `--mt-success` 文字 4.91:1；不得只靠底色表意 |
| `--success` `#35644b` | `--mt-success` | `#0f7a3c` | 成功文字 | 语义文字档 |
| `--slate` `#dde2e9` | `--mt-info-bg` | `#eaf2fb` | 信息 / 进行中底 | 旧 slate 还用于选中底；选中态改 accent-text + 下划线/✓，不再用整块底色 |
| `--notice` `#ede4d6` | `--mt-warn-bg` | `#fbf3d9` | 等待 / 待复核底 | 配 `--mt-warn` 文字 5.34:1；UNREVIEWED/PARTIAL 仍保留文字 |
| `--rose` `#ebdada` | `--mt-danger-bg` | `#fbeceb` | 错误 / 失败底 | 配 `--mt-danger` 文字 5.25:1 |
| `--error` `#934342` | `--mt-danger` | `#b53333` | 错误文字 | 与旧 `--danger` 合并为一档 |
| `--danger` `#b25352` | `--mt-danger` | `#b53333` | 危险实心按钮底 | 实心用 `--mt-accent-on` 字 5.72:1；旧 error/danger 两值合并 |
| `--gold` `#c6af94` | `--mt-border-soft` | `#e8e6dc` | 引文边、标记装饰线 | 金色退役；装饰线不承担识别，也不得做文字 |
| `--on-action` `#f9f9f9` | `--mt-accent-on` | `#faf9f5` | 实心按钮文字 | 与卡片同色；不再引纯白 `#ffffff` |
| `--overlay` `rgba(44,53,71,.3)` | `--mt-scrim` | `rgba(20,20,19,.45)` | 模态 / sheet 遮罩 | 更深更暖；桌面对话框与移动 sheet 共用一个 token |
| `--m-state-hover` `rgba(44,53,71,.06)` | `--mt-state-hover` | `rgba(20,20,19,.06)` | hover 叠层 | **D2-A 已定案**；只叠加、不改布局；仅 fine pointer |
| `--m-state-press` `rgba(44,53,71,.12)` | `--mt-state-press` | `rgba(20,20,19,.12)` | 按下叠层 | **D2-A 已定案**；只叠加、不改布局；规范 §8.4/§9.1 已统一用 `--mt-state-press`（.12） |
| `--m-state-selected` `rgba(51,60,80,.08)` | `--mt-state-selected` | `rgba(20,20,19,.08)` | 选中叠层 | **D2-A 已定案**；只叠加、不改布局；选中仍保留 accent-text + 下划线/✓ 冗余，叠层不是唯一编码 |
| `--m-scrim` `rgba(44,53,71,.42)` | `--mt-scrim` | `rgba(20,20,19,.45)` | 移动 sheet 遮罩 | 与 `--overlay` 合并为同一 token |
| `--m-shadow-bar` `0 1px 2px rgba(44,53,71,.08)` | `--mt-shadow-bar` | `0 -1px 2px rgba(20,20,19,.06)` | 操作栏向上投影 | 旧投影向下；新操作栏向上；顶栏改用 1px `--mt-border-soft` 描边 |
| `--m-shadow-sheet` `0 -8px 32px rgba(44,53,71,.18)` | `--mt-elev-4` | `0 -8px 32px rgba(20,20,19,.18)` | bottom sheet 投影 | 几何不变，墨色换暖黑 |

### 1.2 新增语义色（无旧变量）

| 新变量 | 新值 | 语义 | 约束 |
| --- | --- | --- | --- |
| `--mt-fg-2` | `#3d3d3a` | 次级正文、表格正文、按钮文字 | 对卡片 10.34:1 |
| `--mt-caption` | `#6b6a63` | ≤14px 三级文字、时间戳、单位 | 对卡片 5.15:1；暖砂上非禁用场景不达标（见 **D1**） |
| `--mt-meta` | `#87867f` | 仅非文本（描边/图标）与 ≥24px 大字 | 对卡片 3.47:1；**禁止**正文/12px 标签；暖砂上非禁用场景 2.92（见 **D1**） |
| `--mt-accent` | `#c96442` | 大字号标题、图标、选中标记、进度 | 对画布 3.54:1；仅大字/非文本，**禁止**正文/按钮文字 |
| `--mt-accent-text` | `#a8431f` | 文字操作、链接、quiet 按钮 | 对画布 5.46:1 |
| `--mt-accent-strong-active` | `#974120` | primary 按下 | 象牙白字 6.45:1 |
| `--mt-danger-active` | `#a92e2e` | danger 按钮按下 | 象牙白字 6.39:1；来自规范 §8.1，D5 已补入 |
| `--mt-focus` | `#1f6fb2` | `:focus-visible` 外环、信息语义 | 对画布 4.79 / 卡片 5.01 / 暖砂 4.22，均 ≥3 |
| `--mt-border-soft` | `#e8e6dc` | 卡片边、列表行线、输入内元素 | 装饰，不承担识别 |
| `--mt-handle` | `#d1cfc5` | sheet 把手 | 装饰，不承担识别；来自规范 §8.6，D5 已补入 |
| `--mt-info` | `#1f6fb2` | 信息 / 进行中文字 | 对 info 底 4.68:1，余量最小，勿再调浅 |
| `--mt-warn` | `#8a5a00` | 警告 / 待复核文字 | 对 warn 底 5.34:1 |
| `--mt-neutral-fg` | `#3d3d3a` | 中性 / 未知文字 | 对中性底 8.71:1 |
| `--mt-neutral-bg` | `#e8e6dc` | 中性 / 未知底 | 与 `--mt-surface-warm` 同值，语义分开 |
| `--mt-bg-inverse` | `#141413` | 深色章节、报告封面 | 单页 ≤1 段；不是主题切换 |
| `--mt-surface-dark` | `#30302e` | 深色章节内的次级面 | 只用于嵌套 |
| `--mt-fg-inverse` | `#faf9f5` | 深色章节文字 | 对深色底 17.50:1 |
| `--mt-muted-inverse` | `#b0aea5` | 深色章节辅助文字 | 8.29:1 |
| `--mt-accent-inverse` | `#d97757` | 深色章节强调 | 对 `#141413` 5.90:1；附录 A 未给变量名，本表建议名 |
| `--mt-border-inverse` | `rgba(250,249,245,.16)` | 深色章节分隔线 | 装饰；来自规范 §4.2，不在目标色表原清单内 |

---

## 2. 字体与字号

### 2.1 字体栈

| 旧变量 / 旧值 | 新变量 | 新值 | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--font-body` `'Noto Sans SC', 'Microsoft YaHei', system-ui, sans-serif` | `--mt-font-sans` | `"Anthropic Sans", Inter, "Noto Sans SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif` | UI、正文、标签 | Anthropic Sans 不随包分发，只作首选名；实际回落 Inter / 自托管 Noto Sans SC / 系统字体 |
| `--font-display` `'Noto Serif SC', SimSun, serif` | `--mt-font-serif` | `"Anthropic Serif", Georgia, "Noto Serif SC", "Songti SC", serif` | 页面/卡片衬线标题 | SimSun 退役；Anthropic Serif 不分发，实际回落 Georgia / Noto Serif SC |
| `--font-code` `Consolas, 'Courier New', monospace` | `--mt-font-mono` | `"SF Mono", "JetBrains Mono", ui-monospace, Consolas, monospace` | 哈希、包名、URL、代码 | 只给证据字段，不做正文 |
| （无） | `--mt-font-reading` | `"Noto Serif SC", Georgia, "Songti SC", serif` | 政策原文、报告引文 | 长文阅读专用；与 UI 无衬线明确分工，不混用 |

### 2.2 字号阶梯

> 字号统一 `--mt-text-*`，避免与颜色 `--mt-caption` 同名覆盖。

| 旧变量 / 旧值 | 新变量 | 新值（size / line-height / weight / family） | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--m-font-title` `1.25rem`（20px） | `--mt-text-title-m` | `1.25rem` / 1.3 / 500 / serif | 顶栏、分区、sheet 标题 | 字号不变；行高 26px，改衬线；旧变量只有裸字号 |
| `--m-font-section` `1rem`（16px） | `--mt-text-title-s` | `1.0625rem` / 1.4 / 500 / serif | 卡片标题、来源标题 | 16→17px；行高 23.8px；旧 section 多为无衬线，改衬线 |
| `--m-body` `.875rem`（14px） | `--mt-text-body` | `1rem` / 1.6 / 400 / sans | 工作区正文、说明 | 14→16px，本轮最大视觉变化；内容高度、行数、截图全部变化 |
| `--m-caption` `.75rem`（12px） | `--mt-text-caption` | `.875rem` / 1.45 / 400 / sans | 元数据、辅助说明 | 12→14px；12px 只保留给 `label`（状态标签/小标注）；字段标签用 caption 14/500 |
| `--m-line-body` `1.65` | `--mt-text-body` / `--mt-text-body-l` | 1.6 / 1.75 | 正文行高 | 统一 1.65 退役：工作区 1.6，政策/引文 1.75 |
| fixture `body.fontSize` `14px` | `--mt-text-body` | `16px` | 桌面/移动共用正文 | `assertDesign` 的 `body` 断言需要改 |
| fixture `heading` `28px / 40px` | `--mt-text-title-l`（封面用 `--mt-text-display`） | `24px / 30px`（封面 32 / 36.8） | 页面标题 | 常规页面降到 24；32 只给封面/空态；lineHeight 用计算值 30/36.8 |
| fixture `mobileHeading` `24px / 34px` | `--mt-text-title-l` | `24px / 30px` | 移动页面标题 | 字号不变，行高 34→30 |
| fixture `button.fontSize` `14px` | `--mt-text-control` | `16px / 20px` | 按钮 | 字号 14→16，行高 20，500 |
| fixture `field.fontSize` `14px` | `--mt-text-control` | `16px / 20px` | 输入值 | 16px 防 iOS 聚焦缩放 |
| （无） | `--mt-text-display` | `2rem` / 1.15 / 500 / serif / `-0.01em` | 封面主标题、空状态主标题 | 每屏至多一处；仅封面/空态 |
| （无） | `--mt-text-title-l` | `1.5rem` / 1.25 / 500 / serif | 页面标题 | 报告、设置、空状态副标题 |
| （无） | `--mt-text-body-l` | `1.0625rem` / 1.75 / 400 / sans（阅读用 reading） | 政策正文、报告引文 | 17/1.75；配 `--mt-font-reading` |
| （无） | `--mt-text-control` | `1rem` / 1.25 / 500 / sans | 按钮、输入、标签、导航 | 控件专用，不用于长文 |
| （无） | `--mt-text-label` | `.75rem` / 1.35 / 500 / sans / `.01em` | 状态标签、小标注（字段标签用 caption 14/500） | 12px 只做短标签，不做正文 |
| （无） | `--mt-text-overline` | `.6875rem` / 1.5 / 500 / sans / `.05em` | 章节小标 | 中文不强制全大写 |
| （无） | `--mt-text-mono` | `.875rem` / 1.6 / 400 / mono | 哈希、包名、URL | `overflow-wrap: anywhere`；不截断证据 |

---

## 3. 间距、圆角（含层级）

### 3.1 间距

| 旧变量 / 旧值 | 新变量 | 新值 | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--space-4` `4px` | `--mt-space-4` | `4px` | 4px 基数 | 保留 |
| `--space-8` `8px` | `--mt-space-8` | `8px` | 8px 节奏 | 保留；图标与文字、同组按钮间距 |
| `--space-12` `12px` | `--mt-space-12` | `12px` | 紧凑分区 | 保留 |
| `--space-16` `16px` | `--mt-space-16` | `16px` | 页面边距、字段组、卡片内边距 | 保留；正文左右边距固定 16 |
| （无） | `--mt-space-20` | `20px` | 宽松卡片内边距、按钮水平内边距 | 新增 |
| `--space-24` `24px` | `--mt-space-24` | `24px` | 分区间距 | 保留 |
| `--space-32` `32px` | `--mt-space-32` | `32px` | 大分区间距、章节留白 | 保留 |
| （无） | `--mt-space-40` | `40px` | 章节上下留白 | 新增 |
| （无） | `--mt-space-48` | `48px` | 触控目标、封面留白 | 新增；与 `--mt-touch` 同值但语义分开 |
| 正文左右边距 `--m-gutter` `16px` | `--mt-gutter` | `16px` | 页面边距 | 同值，改名；内容最大宽 560 |
| 卡片内边距（mobile.css 硬编码 `16px`） | `components.card.padding` | `16px` | 默认卡片 | 新增语义 token |
| 卡片内边距（带主操作/阅读） | `components.card.padding` | `20px` | 宽松卡片 | 新增语义 token |
| 分区间距（旧无 token） | `space.semantics.sectionGap` | `24px / 32px` | 卡片/分区之间 | 默认 24，大分区 32 |

### 3.2 圆角

| 旧变量 / 旧值 | 新变量 | 新值 | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--radius` `8px` | `--mt-radius-control` | `12px` | 按钮、输入、分段控件、操作栏按钮 | 圆角变大；状态标签另用 tag 6 |
| `--radius-panel` `12px` | `--mt-radius-card` | `16px` | 卡片、面板、对话框 | 对话框改 L3 + card 圆角 |
| `--m-card-radius` `12px` | `--mt-radius-card` | `16px` | 移动卡片、列表容器、通知 | 与 `--radius-panel` 合并为一个 token |
| `--m-sheet-radius` `20px` | `--mt-radius-sheet` | `24px` | bottom sheet 顶部两角 | 20→24；底部两角为 0 |
| （无） | `--mt-radius-field` | `12px` | 字段 | 与 control 同值，语义分开（目标清单单列） |
| （无） | `--mt-radius-tag` | `6px` | 状态标签、微型容器 | 新增 |
| （无） | `--mt-radius-pill` | `999px` | 胶囊 CTA | 只给空状态/封面主 CTA |
| （无） | `--mt-radius-circle` | `50%` | 图标按钮、头像位 | 新增 |

### 3.3 阴影与层级

| 旧变量 / 旧值 | 新变量 | 新值 | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--m-shadow-bar` `0 1px 2px rgba(44,53,71,.08)` | `--mt-shadow-bar` | `0 -1px 2px rgba(20,20,19,.06)` | 操作栏上投影 | 旧投影向下；新操作栏向上；顶栏改用 1px `--mt-border-soft` 描边 |
| `--m-shadow-sheet` `0 -8px 32px rgba(44,53,71,.18)` | `--mt-elev-4` | `0 -8px 32px rgba(20,20,19,.18)` | bottom sheet | 几何不变，墨色换暖黑 |
| （无） | `--mt-elev-0` | `none` | 主内容、列表、正文 | 平面 + 表面色差；默认无阴影 |
| （无） | `--mt-elev-1` | `1px solid var(--mt-border-soft)` | 卡片、字段、只读面板 | 1px 描边承担分层 |
| （无） | `--mt-elev-2` | `0 0 0 1px rgba(20,20,19,.08)` | 可点卡片按下、fine pointer hover | 环影，不做上移 |
| （无） | `--mt-elev-3` | `0 4px 24px rgba(20,20,19,.05)` | 浮起小面板、对话框 | 大范围低不透明度 |
| （无） | `--mt-elev-4` | `0 -8px 32px rgba(20,20,19,.18)` | bottom sheet | 与旧 sheet 投影同几何 |

---

## 4. 移动壳几何

| 旧变量 / 旧值 | 新变量 | 新值 | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--m-touch` `48px` | `--mt-touch` | `48px` | 触控目标 | 同值；所有交互 ≥48×48，相邻 ≥8 |
| `--m-appbar-height` `56px` | `--mt-appbar` | `56px` | 顶栏高度 | 另加 `safe-top`；底部 1px `--mt-border-soft` |
| `--m-actionbar-min-height` `64px` | `--mt-actionbar` | `64px` | 底部操作栏最小高 | 另加 `safe-bottom`；主按钮 48 全宽 |
| `--m-gutter` `16px` | `--mt-gutter` | `16px` | 左右边距 | 同值；内容最大宽 560 |
| `--m-actionbar-actual`（运行时 JS 测量） | `--mt-actionbar-actual` | 运行时值 | 操作栏实际高度 | 不进设计 token 契约；`MobileApp.vue` 继续 `setProperty`，仅改前缀 |
| （无） | `--mt-stepnav` | `48px` | 步骤导航高度 | 新增；当前项 2px 下划线，整项可点 |
| （无） | `--mt-input-height` | `56px` | 字段高度 | 旧移动输入 min-height 48；规范 §8.2 定 56 |
| （无） | `--mt-input-font-size` | `16px` | 输入字号 | 旧硬编码 `max(16px, 1rem)`，改 token |
| （无） | `--mt-content-height` | `100dvh` | 内容视口高度 | 旧 `.mobile-workspace min-height: 100dvh` |
| （无） | `--mt-content-max` | `560px` | 内容最大宽 | 旧 `.m-main max-width: 720px`，收窄到 560 |
| （无） | `--mt-content-min-viewport` | `600px` | 居中的最小视口 | ≥600px 时内容居中，仅增左右外边距 |
| （无） | `--mt-safe-top` | `env(safe-area-inset-top, 0px)` | 状态栏安全区 | 旧 inline `env()`，改可复用变量 |
| （无） | `--mt-safe-bottom` | `env(safe-area-inset-bottom, 0px)` | 手势条安全区 | 旧 inline `env()` |
| （无） | `--mt-keyboard-inset` | `var(--keyboard-inset, 0px)` | 软键盘偏移 | 旧 inline `var()`；操作栏随键盘上移 |
| `.m-main max-width: 720px` | `--mt-content-max` | `560px` | 内容宽 | 桌面宽退出移动壳；横屏也单列 |
| `.m-row min-height: 48px` | `components.listRow.minHeight` | `56px` | 列表行高 | 整行可点；两行时按内容 |
| `.m-step min-height: 48px` | `--mt-stepnav` | `48px` | 步骤项 | 同值；步骤导航总高 48 |

---

## 5. 动效

| 旧变量 / 旧值 | 新变量 | 新值 | 语义 | 迁移备注 |
| --- | --- | --- | --- | --- |
| `--motion-color` `150ms` | `--mt-duration-press` | `120ms` | 颜色反馈、按下回落 | 150→120ms，更快；颜色变化归入 press |
| `--ease-color` `ease` | `--mt-ease-standard` | `cubic-bezier(.2, 0, 0, 1)` | 颜色缓动 | 浏览器默认 ease 换自定义减速曲线 |
| `--m-duration-press` `120ms` | `--mt-duration-press` | `120ms` | 按下回落 | 同值 |
| `--m-duration-enter` `200ms` | `--mt-duration-enter` | `200ms` | sheet / 步骤进入 | 同值；断言 0.2s 不变 |
| `--m-duration-exit` `150ms` | `--mt-duration-exit` | `150ms` | 关闭、退场 | 同值；比进入快 |
| `--m-ease-standard` `cubic-bezier(.2, 0, 0, 1)` | `--mt-ease-standard` | 同值 | 默认减速 | 仅改名 |
| `--m-ease-decelerate` `cubic-bezier(0, 0, 0, 1)` | `--mt-ease-decelerate` | 同值 | 浮层进入 | 仅改名 |
| （无） | `--mt-duration-reduced` | `0ms` | `prefers-reduced-motion: reduce` | 旧用 `@media` 块逐条归零；新在 root 统一归零 |
| 旧 `transition` 白名单靠注释约束 | `motion.allowedProperties` | `transform, opacity, background-color, border-color, box-shadow` | 可动画属性 | 禁止 `transition: all`；不做视差/装饰自动播放 |

---

## 6. 契约与验收影响面

> 只列需要发生的变化；本轮**不修改**下列任何文件。

### 6.1 `scripts/fixtures/pioneer-design.json`

推荐路径（与规范 §12 一致）：**不要就地重写**，新增 `scripts/fixtures/mobile-design.json` 承接新契约，`pioneer-design.json` 保留给冻结的桌面工作台。新 fixture 的键应与 `mobile-design.tokens.json` 同构：`version`、`tokensFile`、`colors`（40 项：34 个目标色 + `border-inverse` / `danger-active` / `handle` / `state-*` 补充）、`typography`（rootPx / families / scale）、`geometry`（appbar / stepnav / actionbar / touch / inputFontSize / inputHeight / contentMaxWidth / contentMinViewport / sheetRadius）、`states`（focus / press / selected / disabled）。

如果主代理决定就地替换 `pioneer-design.json`，需要新增/替换的键：

| 键 | 现值 | 目标值 / 动作 | 连带影响 |
| --- | --- | --- | --- |
| `roles` | 14 个旧角色 | 替换为 40 个新色 token；键名与 `--mt-*` 对齐（`bg`、`surface`、…、`dark-accent`），或新增 `mobileRoles` 并让 `assertDesign` 读 `--mt-` 前缀 | `lib/frontend-guards.cjs` 的 `assertDesign` 读取 `--` + key，必须同步 |
| `body.fontFamily` / `fontSize` | `Noto Sans SC` / `14px` | `Anthropic Sans` / `16px`（可选加 `lineHeight: 25.6px`） | `assertStyle(body)` 断言 |
| `heading.fontFamily` / `fontSize` / `lineHeight` | `Noto Serif SC` / `28px` / `40px` | `Anthropic Serif` / `24px` / `30px`（封面 32 / 36.8） | `assertStyle(#page-title)`；≤520px 走 `mobileHeading` |
| `mobileHeading.fontSize` / `lineHeight` | `24px` / `34px` | `24px` / `30px` | 窄屏标题断言 |
| `button` | `14px` / `8px` / `36px` | `16px` / `12px` / `48px` | 移动按钮；桌面冻结时保留旧值或退役 |
| `mobileButton.minHeight` | `44` | `48` | 触控断言（`assertTouchTargets`）自动跟随 |
| `mobileButton.maxWidth` | `560` | 保留 560 | 它是断言断点，不是内容最大宽；内容宽另由 `contentMaxWidth` 表达 |
| `field` | `14px` / `8px` / `40px` | `16px` / `12px` / `56px` | 字段字号/高度断言 |
| `mobile.sheetRadius` | `20` | `24` | sheet 圆角 |
| `mobile.*` | `touchTarget/appBarHeight/actionBarMinHeight/inputFontSize` | 保留 `48/56/64/16`；新增 `stepNavHeight: 48`、`contentMaxWidth: 560`、`contentMinViewport: 600`、`fieldHeight: 56` | 移动断言覆盖面 |
| 顶层 | 无 `tokens` 引用 | 新增 `"tokens": { "file": "docs/design/mobile-reset/mobile-design.tokens.json", "version": "0.1.0", "baseline": "od-ds-claude" }` | 契约可追溯 |

> `scripts/verify-round2-primitives.cjs` 第 100–123 行 `deepEqual` 了 `pioneer-design.json` 的完整键集合与 `mobile` 对象，第 49–89 行还逐字锁定旧 `theme.css` 的值。作用域双调色板下这些旧值保持不变，脚本可继续绿；只有决定就地迁移 `pioneer-design.json` 时才需要同批更新它。

### 6.2 桌面冻结套件与新增移动断言

D3 已定案：`scripts/verify-frontend-flow.cjs` + `lib/frontend-guards.cjs` + `pioneer-design.json` 保持旧值，**不改断言**，桌面先保绿。新契约由新增的 `assertMobileDesign` 承担，建议：

- 新增 `scripts/fixtures/mobile-design.json`（从 `mobile-design.tokens.json` 派生）；
- 新增 `assertMobileDesign(page)`，只读取 `.mobile-workspace` 作用域的计算样式；
- 负向控制注入 `--mt-accent-strong: #ff00ff`，不要动 `--navy`。

| 检查 | 目标 |
| --- | --- |
| `.mobile-workspace` 的 `--mt-*` | 40 个色 token；字号读 `--mt-text-*`；几何 |
| `body` / 卡片正文 | 16px、1.6、`Anthropic Sans` 栈 |
| `#page-title` / 卡片标题 | 24/30、17/23.8、衬线 |
| `.ui-button` | 48 高、12 圆角、16/20；primary = accent-strong + accent-on |
| `.ui-field` | 56 高、12 圆角、16px；border-control 边 |
| `--mt-focus` | `:focus-visible` 2px 环 |
| 状态标签 | neutral / info / wait / success / error 的语义底档 |
| 触控 / 字段 | 48px / 16px 下限 |
| 视口 | 320 / 390 / 600+、200% 根字号 |

> 只有产品决定提前退役桌面（D6）时，才需要按旧迁移方案改 `assertDesign`：`--` + role → `--mt-` + role、body 16、button 48、primary accent-strong、field border-control、info-bg；否则不要把桌面断言改成 `--mt-*`。

### 6.3 `scripts/verify-frontend-round2.cjs`

| 行号 | 当前断言 | 需要修改为 | 原因 |
| --- | --- | --- | --- |
| 262 | scrim `rgba(44, 53, 71, 0.42)` | `rgba(20, 20, 19, 0.45)` | `--mt-scrim` |
| 327 | `/Noto Serif SC/` | `/Anthropic Serif/`（声明的第一族） | 新 serif 栈；旧断言仍可能因回落栈命中，但不足以证明新基线 |
| 328 | title 20px | 保持 20px | `title-m` 仍是 20px |
| 342 | theme-color `#fdfcfa` | `#faf9f5` | 顶栏改用 `--mt-surface` |
| 343 | `rgb(253, 252, 250)` | `rgb(250, 249, 245)` | 同上 |
| 541 | sheet 进入 `0.2s` | 保持 0.2s | `--mt-duration-enter` 仍 200ms |
| 776 | 源码含 `var(--m-touch` / `var(--m-scrim` | `var(--mt-touch` / `var(--mt-scrim`；若保留别名则可不改 | 变量改名 |
| 595–654 | 截图文件名与基线 | 重拍，不覆盖旧图 | 视觉全面变化 |
| 48px / 16px / 100dvh / safe-area | 当前断言 | 保持不变 | 新契约维持这些下限 |

### 6.4 同批连带（简报未点名，但会被 token 改名/改值影响）

- `scripts/verify-round2-primitives.cjs`：第 40–89 行锁定旧 `theme.css` 值，第 100–123 行锁定 `pioneer-design.json` 键，第 183 行还要求文档出现 `--m-touch`。作用域双调色板下旧值保持，脚本可继续绿；但新增的 `--mt-*` 块与 `mobile-design.json` 需要新的移动断言覆盖，不能让它成为唯一覆盖。
- `scripts/verify-issue146-motion.cjs:143–151`：桌面继续读 `--motion-color`（150ms），保持不动；移动新组件改用 `--mt-duration-press`（120ms），应另建移动动效断言或按作用域读取。
- `scripts/verify-issue145-a11y.cjs:367–390`：桌面继续读旧 token，保持绿；移动新增断言补 `--mt-*` 对比度（正文/次级/三级、meta 仅大字、focus 三底）。
- `scripts/verify-mobile-flow.cjs:186–189`：字段 ≥16px / ≥48px 的断言在 56px 新字段下仍通过；无需改逻辑。
- `scripts/verify-mobile-reading.cjs`：200% 根字号断言不受字号阶梯影响；但阅读字号 15→17、衬线切换会改变行数，应补视觉复核。
- `apps/web/src/mobile/MobileApp.vue:88–93`：`--m-actionbar-actual` 是运行时测量变量，不是设计 token；若移动壳改前缀，只需同步 `setProperty` 与 `mobile.css` 的消费点。
- `apps/web/src/theme.css`：唯一变量文件。`:root` 旧变量保持旧值服务桌面；新增 `.mobile-workspace` 作用域的 `--mt-*` 块；共享组件消费语义别名（桌面→Pioneer，移动→`--mt-*`）。`apps/web/src/mobile` 内不得再出现硬编码十六进制（规范 §11）。

### 6.5 截图基线重拍

| 目录 | 规模 | 重拍范围 | 说明 |
| --- | --- | --- | --- |
| `docs/acceptance/issue144/round2/` | 23 PNG + 说明 | 390×844、320×568、844×390、200% 根字号 | 移动壳：几何、标题字体/字号、theme-color、scrim 全部变化 |
| `docs/acceptance/mobile-reading/` | 8 PNG | 政策原文/引文阅读态 | 阅读字号 15→17、阅读衬线 |
| `docs/acceptance/issue136/evidence/final-package-*/android` | 11 PNG | 仅当它是当前发布回归集 | 否则作为历史证据，不覆盖 |
| `docs/acceptance/issue145/evidence/` | 13 PNG | **不重拍** | 桌面 a11y 套件冻结，旧值保留 |
| `docs/acceptance/issue146/evidence/` | 9 PNG | **不重拍** | 桌面动效套件冻结，旧值保留 |
| `docs/acceptance/issue129–135/`、`issue73/` | 桌面截图 | **不重拍** | 桌面工作台冻结，保留为历史基线 |

- 新截图目录建议：`docs/acceptance/mobile-reset/`（或下一 Issue 号），文件名保留视口与状态；**旧图不删不覆盖**。
- 截图说明至少记录：token 版本 `0.1.0`、commit SHA、视口、根字号、是否 reduced-motion、Chromium 模拟而非真机。
- 重拍时机：组件迁移完成后，而不是 token 文件落地时——token 本身不改变像素。

---

## 待决策（主代理已定案，2026-10-23）

> 对比度数据来自 `contrast.mjs` 实算。以下各条为本轮定案；D4 标记已解决。

### D1. 暖砂两个非禁用组合（已按禁止规则定案）

主代理定案：维持“暖砂仅用于禁用/骨架/分区带”，`--mt-caption` `#6b6a63` 与 `--mt-meta` `#87867f` 均不改值。`contrast` 中两条继续 `pass:false`，`usage` 已改写为“仅禁用态豁免、非禁用场景禁止使用”。

- `--mt-caption` / `--mt-surface-warm` = **4.34** < 4.5（14px 文本）
- `--mt-meta` / `--mt-surface-warm` = **2.92** < 3.0（非文本）

目标清单要求的 29 组契约配对全部通过。若未来放开暖砂上的非禁用内容，再评估候选：caption `#66645d`（4.73）、meta `#807e77`（3.25）。

### D2. 交互状态层（已定案：选 A）

已采纳 A：新增 `--mt-state-hover: rgba(20,20,19,.06)`、`--mt-state-press: rgba(20,20,19,.12)`、`--mt-state-selected: rgba(20,20,19,.08)`，写入 JSON `colors`（keys 为 `state-hover/state-press/state-selected`），并在 token-map 1.1 建立旧 `--m-state-*` 映射。

- 只叠加、不改布局；规范 §8.4/§9.1 已统一用 `--mt-state-press`（.12）。
- `components.states` 的 hover / 按下层、quiet 与 listRow 按下背景已引用新 token；selected 保留 accent-text + 下划线/✓ 的冗余编码。

### D3. 作用域双调色板（已定案）

规范 §11 已改为作用域别名：旧 `--canvas/--navy/--m-*` 在 `:root` **保持旧值**服务桌面；移动根 `.mobile-workspace` 使用 `--mt-*`；共享组件消费语义别名（桌面映射 Pioneer、移动映射 `--mt-*`）。旧别名**不**指向新值，桌面断言先保绿；移动断言由新增 `assertMobileDesign` 承担。

### D4. 规范附录 B 数值勘误（已解决）

已按实算 `6.45` 勘误规范附录 B；`--mt-border-soft` 已标注“对画布 1.13 / 对卡片 1.19”。无需决策。

### D5. 一次性值 token 化（已定案）

已补入并引用：

- `--mt-danger-active` `#a92e2e`（danger 按下，象牙白字 6.39）
- `--mt-handle` `#d1cfc5`（sheet 把手）
- `--mt-shadow-bar` `0 -1px 2px rgba(20,20,19,.06)`（操作栏上投影）

JSON 的 `colors` / `elevation` 与 `components` 已引用；规范附录 A / §8.1 / §8.6 已引用这些 token。

### D6. 桌面验收套件（已定案）

桌面 `verify-frontend-flow.cjs` 与 `pioneer-design.json` **冻结保留**，旧断言先保绿；另建 `assertMobileDesign` 覆盖 `.mobile-workspace`。桌面套件的退役时间点待产品决策，不在本轮删除或改写。
