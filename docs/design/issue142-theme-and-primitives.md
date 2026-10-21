# Issue #142 · Pioneer 主题与基础组件交接

来源任务：[子票 #142](https://github.com/MrEcho114/PrivacyTrace/issues/142)，父规格 [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)。实现基线 main `83f42ea2b8a59e34c84d348ef996973643bb5a94`。当前执行记录见 [Issue 评论](https://github.com/MrEcho114/PrivacyTrace/issues/142#issuecomment-6313511394)。

本次整理既有主题，采用 **Reka UI 2.11.0 的 Dialog**。保留 UiButton、UiField、StatusTag、UiIcon、原生 select/details 与全部业务数据流。没有新增产品页面；比较页面仅由忽略目录中的测试夹具提供。

## 设计来源与映射

2026-10-21 实时读取 Figma 的设计上下文、截图与颜色变量。页面节点 `824:1276` / `824:1278` 的上下文工具返回未选择图层，改为读取其可定位子节点；未把失败请求写成成功。`824:1382` 的变量定义调用成功，组件页结构由 metadata 核对。

| 节点／变量或样式 | 现有 token／本次整理 | 组件与调用点 | 来源与最小差异 |
| --- | --- | --- | --- |
| [颜色 824:1382](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=824-1382)，palette-canvas / surface / surface-muted | `--canvas #F6F5F1`、`--surface #FDFCFA`、`--surface-muted #EEEDEA`，移至 `theme.css` | 工作台、报告、离线报告、Tauri 共用 `main.ts`；面板、表单、UiDialog | 复用原变量名；删除报告旧绿色硬编码及 shell 二次颜色覆盖 |
| 同节点 ink / secondary / navy / silver / control-border | `--ink #2C3547`、`--muted #64696F`、`--navy #333C50`、`--border #D9D7D2`、`--control #858D92` | UiButton、UiField、原生报告来源 select、表格、说明 | 分隔线与控件边框分开；保留业务布局 |
| 同节点 mint / rose；[状态 830:1379](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=830-1379) | `--mint #DCE9DF`、`--success #35644B`、`--slate #DDE2E9`、`--notice #EDE4D6`、`--rose #EBDADA`、`--error #934342` | StatusTag 的 neutral/info/wait/success/error；原报告 clear/review、回放标签 | 成功仍需文字事实；错误不使用薄荷。UNKNOWN 不升级为成功；当前业务自行选择既有 tone，不改判定 |
| [按钮 830:1276](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=830-1276)，action-hover / risk / on-action | 新增 `--navy-hover #212A3B`、`--danger #B25352`、`--on-action #F9F9F9` | UiButton 四变体，busy/disabled；报告原生按钮 | 保留外部 props；补主按钮按下、危险按下与禁用字段样式，不新增状态机。主按钮沿用既有 surface 对比文字合同 |
| [字体 824:1422](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=824-1422) | `--font-display` / `--font-body` / `--font-code` | 页面标题与设置标题；正文/操作；代码、哈希 | 复用本地 Noto woff2，无远程字体请求；Microsoft YaHei / SimSun / system-ui / Consolas 回退。保留正文14px、阅读15px、桌面按钮36px、手机触控44px；不搬用 F9 密集字号 |
| [字段 830:1353](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=830-1353)，space / radius | 原 `--radius 8px`，整理 `--radius-panel 12px`、`--space-4/8/12/16/24/32` | UiField、UiButton、面板、候选与任务阶段组合 | 保留40px输入与既有响应式尺寸。原本12px面板统一引用变量；已有特殊尺寸不强行网格化 |
| [组件合同 824:1438](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=824-1438) | 颜色与几何改变不改变业务 | PolicyAssist、ImportPage、CandidatePage、ProgressPage、ExampleReport、App | 专有组合继续消费既有声明／证据／阶段；不复制业务逻辑 |
| [当前 F9 824:1279](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=824-1279) | 父规格视觉约束，以上子节点是本次直接实现来源 | 仅变量与控件角色 | 不搬入 Agent 会话、窗口三点、插画；设计静态模拟不是运行证据 |

唯一颜色与字体定义位于 `apps/web/src/theme.css`，由 `main.ts` 在页面样式之前导入。`style.css` 与 `workbench.css` 只消费这些值。没有 `pioneer-*` 与旧变量并行的第二套主题，没有库默认 CSS 或全量组件注册。

## 复用盘点与迁移成本

| 能力 | 既有实现与调用点 | 本次决定／成本 |
| --- | --- | --- |
| 按钮 | UiButton：primary/secondary/quiet/danger、busy/disabled/type；工作流各页 | 保留接口，只整理样式；换库需要改大量调用，收益不足 |
| 字段 | UiField：label/id/help/error 与 describedby 插槽；导入、候选、设置 | 保留原输入／校验；补 disabled 的主题值。调用方仍负责绑定实际 aria，D 票负责最终审查 |
| 状态 | StatusTag；各阶段、来源、设置状态 | 保留五种 tone 与调用文案，不把标签做成可交互组件 |
| 图标 | UiIcon 的既有四种本地 SVG | 原样复用，未下载或复制 Figma 图标 |
| Dialog | SettingsPanel 的原生 dialog + 手写 Tab 循环 | 使用一个 UiDialog 薄封装，删除 keepFocus / showModal 生命周期；保留 close/clear 事件及请求取消、凭证清空逻辑 |
| 来源选择 | ImportPage/CandidatePage 原生 select，App 的 `#report-source`、报告筛选 | 原生键盘、选项、v-model 已满足；统一边框主题，无替换成本，无额外 Select/Popover |
| 来源切换／移动阅读切换 | CandidatePage 的来源按钮组、既有 mobile-panel-tabs | 保留既有业务语义；不为外观强塞 ARIA Tabs。D 票按当前接口处理最终键盘语义 |
| 证据展开 | details/summary、报告的显式打开／关闭与移动行内展开 | 原生 details 与现有证据定位已覆盖；不引 Accordion/Collapsible 状态机 |
| 分页／反馈 | App 的候选每页20条、前后页按钮；现有 notice、status、alert | 保留数据分页与文案；无需求证明须引入 Pagination/Toast 框架 |
| Drawer / Tooltip | 当前范围没有需要迁移的使用点 | 不安装第二套库、不预造封装；后续有明确使用场景再消费 Reka 导出 |
| 专有组合 | 政策来源／候选、静态线索＋原句、任务阶段 | 保留组合，仅消费公共 token；没有新的专有数据接口 |

## Naive UI / Reka 比较

候选均为 MIT。实测版本 Naive UI **2.45.3**、Reka UI **2.11.0**；比较环境 Vue **3.5.26**，生产锁使用仓库既有 Vue **3.5.43**。比较夹具对同一设置弹窗采用各库的模态能力，来源选择与证据展开均复用原生 select/details：不把已满足的两类场景换库。

| 指标 | Reka | Naive |
| --- | --- | --- |
| 实际导入 | Dialog 家族8个导出 | NConfigProvider、NModal（dialog preset） |
| 适配 Vue 源码字节（含相同正文） | 909 B | 1,352 B |
| 主题适配 | 复用项目 class，overlay＋dialog 的局部几何 | common＋Dialog themeOverrides；仍需处理浮层字体继承 |
| 按需生产 JS／gzip（含同一 Vue 运行时） | 96,771 / 35,746 B | 211,536 / 70,864 B |
| 共享 CSS／gzip | 28,771 / 6,378 B | 相同；Naive 部分样式在 JS 内运行时生成 |
| 实际 Chromium 行为 | Tab 焦点留在弹窗、Escape、返回触发点均通过；原生来源与证据可操作；0 pageerror | 同项通过；0 pageerror |
| 可观察外观 | 正文面、文字、12px圆角及项目 Noto 字体链直接继承 | 同色与圆角通过覆写；模态根计算字体仍为 v-sans，进一步对齐需要局部适配 |
| 维护成本 | 为已有 CSS 提供行为，生产薄封装24行，API小 | 适合大量采用库表单时减少代码；此处与现有按钮/字段重叠较多，额外保留主题覆写层 |

选择 **Reka** 的依据是本范围的实测体积与适配差异，不是星数，也不代表 Naive 的能力不足。没有评估全部组件或做完整库性能基准；表格统计JS/CSS产物，共用本地字体不计入库增量。相关一手接口：[Reka Dialog](https://reka-ui.com/docs/components/dialog)、[Naive 源码与许可](https://github.com/tusen-ai/naive-ui)。实际采用版本在 `apps/web/package.json` 以精确版本固定，锁文件仅加入 Reka 及所需依赖；Naive 仅在忽略的探针目录中。

复现（从仓库根目录；工具目录不会进入产品包）：

```powershell
npm ci
npm install --prefix tmp/issue142-probe --ignore-scripts --save-exact vue@3.5.26 reka-ui@2.11.0 naive-ui@2.45.3
node docs/design/issue142/build-probes.mjs
node node_modules/vite/bin/vite.js tmp/issue142-probe --config docs/design/issue142/probe-vite.config.mjs --host 127.0.0.1 --port 5193 --strictPort
# 另一终端，在同一仓库根目录：
node docs/design/issue142/check-probes.cjs
```

[构建结果](issue142/evidence/library-build.json)、[浏览器结果](issue142/evidence/library-browser.json)、[Reka截图](issue142/evidence/reka-probe-1440.png)、[Naive截图](issue142/evidence/naive-probe-1440.png)。截图是受控夹具，不代表实际模型、APK扫描或真实设备。

## UiDialog 接口与后续整合

`components/UiDialog.vue` 在调用方挂载时打开；props 为必需的 `title/description` 与可选的 `initialFocus` 元素 ID；默认插槽为内容，`close` 命名插槽为关闭按钮；关闭请求发送 `close`，父组件负责卸载。class/其余 attrs 显式透传给 DialogContent。使用 Reka DialogTitle/Description 生成关联标识，使用 DialogPortal/Overlay 提供模态层，保留 dialog 标签方便既有浏览器检查定位。

外部点击不丢弃设置表单；Escape 交由 Reka 发送关闭请求，原 WorkflowApp 仍返回设置入口焦点。焦点循环、动态禁用控件、屏幕阅读器背景隔离由库提供，没有自写焦点陷阱或宽泛 wrapper 框架。SettingsPanel 中模型地址、凭证保存、网络目标与请求取消代码保持原逻辑。

A 票维护 token 与接口；B/C/D/E 在各自范围消费。D 的全站硬件键盘、aria、焦点可见性最终修复仍归 D，不以本次定向验证替代；C 的设备软键盘/安全区与 E 的动效也未代验。

## 前后截图与验证

同一 Chromium、同一1440×900视口、同一受控页面场景；基线从准确 main 导出，除了截图前重置 dialog 滚动位置，未改产品实现。报告截图中的 REAL_SCAN 等值来自既有确定性 API 夹具，不是本次真实APK扫描。

| 场景 | 修改前 | 修改后 |
| --- | --- | --- |
| 设置 | [before](issue142/evidence/settings-before-1440.png) | [after](issue142/evidence/settings-after-1440.png) |
| 报告与原生选择 | [before](issue142/evidence/reports-before-1440.png) | [after](issue142/evidence/reports-after-1440.png) |
| 设置390px | — | [after](issue142/evidence/settings-after-390.png) |

生产构建基线 CSS 29.75 KB / gzip 6.83 KB，JS 204.33 KB / gzip 73.43 KB；本次 CSS 30.31 KB / gzip 6.74 KB，JS 239.35 KB / gzip 86.19 KB。JS gzip 增约12.76 KB，用于实际模态行为；没有整库注册和全量 CSS。

本票定向检查在既有 `scripts/verify-frontend-flow.cjs` 中覆盖：运行时替换 surface/control 后，真实报告面板与原生来源选择跟随同一 token；设置可访问名称和描述、初始关闭按钮焦点、aria-hidden 背景、点击外部不丢输入、长模型名、禁用字段不进入正反向 Tab、Escape返回入口。原有五尺寸流程、候选原句与枚举、来源切换、取消/重试、证据、mock报告与10项真实HTTP政策辅助检查继续运行。设置320px/200%字体下无页面或弹窗横向溢出，末端控件可滚动并聚焦；`acceptance:mobile` 的真实Vue＋模拟桥接流程亦通过（不是真机）。首次新增断言误用了入口名而非弹窗实际标题，已修正并复跑，不改产品文案规避测试。

最终权威检查与交付SHA的CI结果在 PR Verification 和当前执行记录回写。首次 Docker 构建因依赖下载连接重置失败，未计通过；历史记录保留，不用浏览器结果替代 Docker。

未覆盖：真实 Android / OEM、设备软键盘、真实模型质量、公网部署、全站读屏人工体验、B–E整票验收。静态线索、声明和 UNKNOWN/PARTIAL/UNREVIEWED/附件未检查的含义不变。

## 来源与许可

项目既有组件、字体文件和图标原样沿用；Figma仅作为设计变量/角色参考，未复制其业务或图像资源。Reka 源码依赖许可证 [MIT全文](issue142/reka-ui-LICENSE.txt) 随本票保存，上游 [仓库](https://github.com/unovue/reka-ui)。Naive 的 MIT 仅用于探针比较，未进入生产依赖。

依赖审计：生产依赖 `npm audit --omit=dev` 为0项；全量审计仍报告基线已有的 Vite 开发工具告警，本票未升级范围外工具链。

## 第二轮：Android 竖屏 token、UiSheet 与图标（2026-10-22）

来源合同：`.scratch/round2/lead/docs/design/frontend-round2-android-pioneer.md` §2/§3/§8/§9/§10（本轮集成时随父票 #141 进入 `docs/design/`）。本轮只补 #142 的 token 与基础组件；移动外壳（#144）、桌面层级（#143）、语义/焦点（#145）与动效（#146）不在本票范围内，也未在本票验收。

### Token 映射

`apps/web/src/theme.css` 仍是唯一变量文件；下列变量名与值由合同 §3 固定，不改名、不删旧 token。行内注释记录了合同路径、Pioneer Figma 节点与 Android 平台指引。

| token | 值 | 来源与推导 | 预期消费方 |
| --- | --- | --- | --- |
| `--m-touch` | `48px` | Android 48dp 最小触控目标（平台规范）；24px 视觉图标用 padding 扩大命中区 | C/D 的按钮、列表行、图标按钮 |
| `--m-appbar-height` | `56px` | Material 3 top app bar 高度；不含 safe-top | C |
| `--m-actionbar-min-height` | `64px` | 48px 主按钮 + 上下各 8px 留白，保证底部操作栏可触达 | C |
| `--m-gutter` | `16px` | Android/Material 16dp 屏幕边距；与既有 `--space-16` 同值，但语义限定为移动外壳 | C/D |
| `--m-card-radius` | `12px` | 与既有 `--radius-panel` 12px 一致，避免移动端出现第二套圆角 | C |
| `--m-sheet-radius` | `20px` | 合同固定值（bottom sheet 顶部圆角）；Figma 未提供该变量，不是逐节点量取值 | UiSheet、C 的证据弹层 |
| `--m-font-title` | `1.25rem`（20px） | §2.1 固定「标题 Pioneer 衬线 20px」；位于桌面 heading 28px、`mobileHeading` 24px 的下一档 | C 顶栏标题、UiSheet 标题 |
| `--m-font-section` | `1rem`（16px） | 移动端分区标题；与输入 16px 同值但契约不同（输入字号来自 WebView 聚焦缩放防护） | C/D |
| `--m-body` | `0.875rem`（14px） | Pioneer 正文 14px；长文阅读可用既有 15px，本 token 不强制覆盖 | C/D |
| `--m-caption` | `0.75rem`（12px） | Pioneer 辅助字号 | C/D |
| `--m-line-body` | `1.65` | 移动端正文行高；既有正文 1.6–1.7，取中间值 | C/D |
| `--m-state-hover` / `--m-state-press` | `rgba(44, 53, 71, .06)` / `.12` | 由 `--ink #2C3547` 加 alpha 的状态层，对应 Material state layer 的 6%/12%，不新增颜色 | C/E |
| `--m-state-selected` | `rgba(51, 60, 80, .08)` | 由 `--navy #333C50` 加 alpha；选中/当前项与 hover 区分 | C/D |
| `--m-scrim` | `rgba(44, 53, 71, .42)` | 由 `--ink` 推导的弹层遮罩；比桌面 `--overlay`（.3）更实，保证 sheet 前景分离 | UiSheet、C |
| `--m-shadow-bar` / `--m-shadow-sheet` | `0 1px 2px rgba(...,.08)` / `0 -8px 32px rgba(...,.18)` | 由 `--ink` 推导；sheet 阴影朝上，因为底边贴视口 | A/C |

§3 的 motion token（`--m-duration-*`、`--m-ease-*`）归 E，本票没有提前写入，也没有把动效写成已实现。

### UiSheet（`components/UiSheet.vue`，新增）

- 行为来自 Reka UI **2.11.0** Dialog 家族（MIT，既有生产依赖）：`DialogRoot/Portal/Overlay/Content/Title/Description/Close`。没有复制 Reka 源码，没有新增渲染库或依赖。模态遮罩、焦点进入/循环、Esc、背景 `aria-hidden`、body 滚动锁定由库提供（overlay 负责 scroll lock）。
- 接口：`title`（必填）、`description?`、`initialFocus?`（元素 ID，缺省聚焦 `.ui-sheet-close`）、`variant?: 'bottom' | 'detail'`（默认 `bottom`）。默认插槽是正文；`close` 插槽是关闭按钮内容（默认 `UiIcon name="close"`）；默认关闭按钮、点击遮罩或 Esc 都经 `update:open` 发出 `close`，由父组件卸载。打开前的焦点由 Reka 记录并在关闭后恢复，父组件也可自行管理（与 `UiDialog` 的既有约定一致）。
- DOM 类：`ui-sheet-overlay`、`ui-sheet`、`ui-sheet-handle`、`ui-sheet-head`、`ui-sheet-title`（合同外，仅用于测量/焦点定位）、`ui-sheet-close`、`ui-sheet-description`、`ui-sheet-body`。关闭按钮带 `aria-label="关闭"`，图标 `aria-hidden`；标题由 `DialogTitle` 生成 `aria-labelledby` 关联。
- 几何：bottom 默认 `max-height: min(88dvh, 720px)`，宽度 `min(100%, 640px)`（桌面居中，不把 sheet 拉满 1440）；detail 变体 `inset: 0`、`100dvh` 全屏。正文 `overflow-y: auto` 且 `overscroll-behavior: contain`；左右/底部安全区使用 `env(safe-area-inset-*)`，detail 额外加顶部安全区。关闭按钮 48×48（`--m-touch`），标题 20px 衬线（`--m-font-title`），圆角 `--m-sheet-radius`。
- `description` 缺省时仍渲染一个 `display:none` 的空 `DialogDescription`，避免 `aria-describedby` 指向不存在的节点；这是实现细节，不改变可选接口。
- 动效保持静态：本组件没有 transition/animation。按压/进入/退出由 E 在 #146 统一添加并遵守 `prefers-reduced-motion`；本票不认领动效验收。

### UiIcon

在既有 4 个图标之外加入 `back`、`close`、`settings`、`chevron-right`、`refresh`、`check`。全部 24px、`viewBox="0 0 24 24"`、`fill="none"`、`stroke="currentColor"`、`stroke-width="1.5"`、圆头连接、`aria-hidden="true"`/`focusable="false"`。路径是手写的通用 24px 几何，不是 Figma 导出，也没有下载图标库；既有 4 个图标保留名称与行为，渲染尺寸按 §3「统一 24px」由 20px 改为 24px，布局由既有 `.ui-icon`（`flex-shrink: 0`）与局部 CSS 尺寸覆盖。

### `pioneer-design.json`

新增机器可读镜像，既有键值不动：

```json
"mobile": { "touchTarget": 48, "appBarHeight": 56, "actionBarMinHeight": 64, "inputFontSize": 16, "sheetRadius": 20 }
```

它只是断言/文档镜像，CSS 的唯一事实源仍是 `theme.css`；两处数值由 `scripts/verify-round2-primitives.cjs` 交叉校验，改一处必须同时改另一处。

### 验证与限制

本分支 `codex/issue142-round2`（HEAD 以提交为准），2026-10-22：

- `node scripts/verify-round2-primitives.cjs`：17 个 §3 token、旧 token 未改名、JSON 镜像、UiIcon/UiSheet 静态合同、无 `transition: all`、四份证据文件存在。
- `npm run typecheck`（vue-tsc --noEmit）：通过。
- `npm run build`（apps/web）：通过；产物 CSS 30.80 kB / gzip 6.91 kB、JS 240.37 kB / gzip 86.64 kB。UiSheet 尚未被产品入口引用，因此没有进入当前 bundle；这不是接入完成的证据。
- 浏览器夹具：Vite 7.3.6 + Playwright Chromium（版本见 json），`390×844` 与 `1440×900`，`deviceScaleFactor: 1`。夹具在 gitignored `tmp/round2-a/`，是受控组件夹具，不是产品页面或真实数据。

| 截图 | 场景 | 视口 | 说明 |
| --- | --- | --- | --- |
| [ui-sheet-bottom-390.png](issue142/evidence/ui-sheet-bottom-390.png) | UiSheet 默认 bottom | 390×844 | 390×720、20px 顶部圆角、正文可滚动（scrollHeight 712 > clientHeight 587）、关闭按钮 48×48、初始焦点在关闭按钮 |
| [ui-sheet-bottom-1440.png](issue142/evidence/ui-sheet-bottom-1440.png) | UiSheet 默认 bottom | 1440×900 | 宽度 640 居中、高度仍受 720 上限约束 |
| [ui-sheet-detail-390.png](issue142/evidence/ui-sheet-detail-390.png) | detail 变体 | 390×844 | 全屏 390×844、无圆角 |
| [ui-sheet-metrics.json](issue142/evidence/ui-sheet-metrics.json) | 几何与行为 | 两种视口 | Chromium 版本、开合、Esc、焦点返回、`overscroll-behavior: contain`、无横向溢出 |

限制与 NOT_RUN：

- Chromium 视口模拟不是 Android WebView/真机；桌面 Chromium 的 `env(safe-area-inset-*)` 为 0，刘海/手势条真实留白未验证。
- 未验证真实 Android 系统返回键、软键盘 IME 与键盘内 `100dvh` 行为（#144/#145 范围）、真实读屏、真实设备字体缩放；未构建 APK；未跑 `bash scripts/check.sh`（由 Lead 在整合树执行）。
- 未接产品入口：本轮不修改 `App.vue`、`MobileApp.vue`、`workbench.css`、`pages/*`；UiSheet 的真实接入与 390×844 全流程由 C/D 验证。
- `--m-sheet-radius`、`--m-touch` 等值来自合同/平台规范，不是在 Figma 逐节点量取的；来源与差异以本节表格为准，不把设计规范写成运行结果。

