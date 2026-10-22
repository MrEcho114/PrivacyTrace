# PrivacyTrace 设计基座 · 已选 GPT 双端概念

状态：用户于 2026-10-22 通过 grill-with-docs 确认本轮交付；关联 [#165](https://github.com/MrEcho114/PrivacyTrace/issues/165)、父任务 [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)、共享规范 [#142](https://github.com/MrEcho114/PrivacyTrace/issues/142)。

## 1. 已确定的设计树

| 决策 | 用户确认 | 实施边界 |
| --- | --- | --- |
| 取代范围 | 保留逻辑，替换视觉与布局 | 保留业务/API、成熟组件和已验证交互；最新补充明确复用旧 Pioneer 字体，采用新配色和布局 |
| 移动证据阅读 | 定位到下方证据区 | 显式点击后切换对应证据、滚动并聚焦，提供返回触发按钮；本报告示例不使用底部 sheet |
| 本轮规模 | 设计规范＋基础组件展示页＋双端报告示例 | 导入、候选、进度和真实业务接入由 DS 后续完成 |
| 接入方式 | 独立预览与开发基座 | 不接管现有报告入口，不修改原生桥或业务状态机；用户稍后向 DS 交接 |
| 重点信息 | 强调色或四色条标出最高信息区 | 本报告仅在“对照结论”面板顶部加窄四色条，红色继续用于关键操作 |
| 字体设计 | 复用并采纳旧 Pioneer | Noto Serif SC 展示标题；Noto Sans SC 正文/操作/区段标题；Consolas / Courier New 技术标识 |
| 重要文字 | 字号显著放大、保持协调 | 桌面标题48/结论条目28/区段22px；手机36/24/20px；状态18、正文16、主操作17px |
| UI/UX布局 | 用户指定六项修正 | [单流程、55:45、证据关联与集中操作合同](ux-layout-contract.md)；独立示例落实，完整接入留DS |
| 文案合同 | 用户采纳 #167 并融入 #165 | [完整采用决定、20项用户故事承接与DS剩余接入](copy-contract-167.md)；本轮示例同步新命名、状态行与去重规则 |

此次没有新增领域概念，沿用 [GLOSSARY](../../../GLOSSARY.md) 的静态证据、政策快照、候选声明、离线回放。视觉 token 不进入领域词汇表；无需额外 ADR。

## 2. 设计来源与取代关系

**当前视觉权威是用户提供并选定的两张概念图：**

- [桌面参考原图](reference/desktop-concept.png)
- [手机参考原图](reference/mobile-concept.png)

它们决定整体排布、白色工作面、米白顶栏、细线面板、四色身份条、字号层级与单红主操作。像素不是业务契约；示例图中的固定数字、状态及水印不能照抄成产品事实。

以下仅保留历史来源，不再作为视觉验收目标：

1. DS Flight Binder：分支 `codex/nasa-punk-design` @ `e4917fa`，父票[提案记录](https://github.com/MrEcho114/PrivacyTrace/issues/141#issuecomment-6322023803)。用户明确废弃其视觉方向，未要求删除其历史或业务实现。
2. 已被否决的三张 NASA 换肤草稿，不得作为本轮通过截图。
3. 原 Pioneer 的旧配色与本规范冲突时被取代；**字体设计按用户后续明确要求继续采用**，成熟组件接口、焦点/触控/状态交互与可追溯来源继续复用。之前“替换衬线标题”的建议由本决定撤回。

来源优先级：用户最新明确决定 → 本规范/选定两图 → 既有业务和无障碍合同 → 历史设计。既有检查报告只证明原版本，不能升级为本轮视觉通过。

## 3. 视觉 token

唯一实现位置：[foundation.css](../../../apps/web/src/design/foundation.css)。独立入口不导入旧全局主题，避免两套级联互相覆盖；接入产品时由共享主题 owner 将这些语义角色串行迁入统一主题，不能将本入口再嵌入旧 App 全局样式中。

| 角色 | CSS token | 值 / 规则 |
| --- | --- | --- |
| 阅读工作面 | `--pt-paper` | #FFFFFF；正文、侧栏、主要面板和画布 |
| 顶栏 | `--pt-header` | #ECE5D6；仅品牌顶栏，不能扩展到整页 |
| 正文 | `--pt-ink` | #252A2E |
| 结构/焦点/次级文字 | `--pt-structure` / `--pt-muted` | #4C5A68 |
| 次级分隔 | `--pt-rule` | #BFC7CF；只作非交互内容分隔 |
| 唯一鲜艳操作色 | `--pt-action` | #D63A2C；主按钮白字，其他操作中性描边/下划线 |
| 识别条 | `--pt-stripe-1…4` | #4C5A68 / #7A7F4E / #D2A85E / #A8432F |
| 正文/操作/区段标题 | `--pt-font-body` | 复用旧 Pioneer：本地 Noto Sans SC，Microsoft YaHei / system-ui / sans-serif 回退 |
| 展示标题 | `--pt-font-display` / `--pt-type-report` | 保留Pioneer字体：本地 Noto Serif SC，SimSun / serif；按最新要求显著放大为48px/60px、600字重，手机36px/45px |
| 编号/技术标签 | `--pt-font-code` | 复用旧 Pioneer：Consolas / Courier New / monospace；具体系统呈现允许差异 |
| 控件高度 | `--pt-control` | 桌面至少 36px；手机至少 48px；正文输入 16px 起 |
| 面板 | — | 白底、1px 深色结构边、直角；不堆阴影 |
| 重点层级 | `--pt-type-finding/panel/conclusion` | 条目28px/手机24px；区段22/20px；实际结论状态18px，与辅助标签拉开明显层级 |
| 阅读/操作 | `--pt-type-reading/action` | 阅读正文16px；证据入口16px，主操作17px/至少56px高；元数据保持13–14px，仅补充技术标签10–11px |

红/白对比约 4.67:1；红/米白约 3.72:1，不能把红色小号字放到米白顶栏。状态不用四色身份条编码；UNKNOWN/PARTIAL/UNREVIEWED 均保留明确文字。失败通过文案和边线样式识别，不再引入第二种鲜艳颜色。

## 4. 布局与装饰预算

桌面：外设备框 → 米白顶栏/四色条 → 左任务索引＋主区四步定位 → 报告身份 → 三格计数 → 左结论/右证据。1440 保留参考图留白；矮桌面视口适当压缩顶栏和计数留白，使 1280×720 第一条完整证据操作可见。

手机：无侧栏与设备外框；米白品牌顶栏/四色条 → 四步定位 → 报告身份 → 三格计数 → 结论/主操作 → 证据。主操作先于次要来源详情。正文正常流，无覆盖内容的固定底栏。768 采用单列阅读布局；大字允许内容增高与自然换行。

- 顶栏一条品牌身份色带；按用户后续补充，每页再选择一个最重要的信息区，以窄四色条或强调色标记。本轮报告在“对照结论”面板上缘加入 4px 四色条；红色继续用于关键操作。不能把所有面板/结果都标成重点，也不能将强调色解释为风险等级。外框两个角铆钉，不在每个面板重复铆钉。
- 警示斜纹仅用于静态证据边界的窄左边；斜纹可用局部 repeating-linear-gradient，不是大面积渐变。
- 无霓虹、全息、大渐变、扫光、闪烁、自动装饰动画。
- 磨损/贴纸/手写只在不影响内容的边缘酌情使用；本轮为阅读克制省略仿脏纹理，不引入图片纹理或多余提示。
- 小号英文仅作补充；中文按钮与状态完整。四步编号是真实流程顺序，计数来自数据，不使用虚构 STOW/设备编号伪装产品字段。
- 图中 GPT 水印、VISUAL RECONSTRUCTION、DESIGN STUDY 日期、Verify original source 手写笔记属于概念来源，不进入产品 UI。

## 5. 复用组件合同

| 组件 | 接口与用途 | 状态/交互 |
| --- | --- | --- |
| 既有 UiButton | 直接复用 `variant/busy/disabled/type` | 不复制按钮逻辑；等待 disabled + aria-busy；手机 48px |
| 既有 UiField | 直接复用 `label/id/help/error`、slot describedby | label/错误关联保留，输入 16px，无外部请求 |
| 既有 StatusTag | 直接复用 tone/slot | 同一中性色系，状态文字明确，wait 虚线/error 双线 |
| MissionShell | `gallery?: boolean`＋默认 slot | 品牌、识别条、流程概览、skip link、main；步骤是静态示例概览，不提供假业务导航 |
| InstrumentPanel | `title, label?, priority?`＋默认 slot | 共用 padding/边线；每页仅一个 priority 面板带四色重点条 |
| ReportMetrics | `types, sources, evidence` | 只展示当前数据计数；数量不等于风险/安全评分 |
| StaticBoundary | 无业务输入 | 权限能力、调用线索、政策声明的真实边界 |
| ReportExample | `report: DesignReport` | 数据驱动；点击对应证据筛选引用并定位/聚焦；返回恢复焦点；政策详情显式展开 |

[model.ts](../../../apps/web/src/design/model.ts) 是展示层输入，不是第二套 API/规则引擎。后续适配生成契约时，将 API 原值分别映射到展示字段；不得在组件中重新推断是否声明/实际采集。没有引用的候选条款不能伪装成规则确认的证据。

示例材料清楚标记 DEMO/合成材料、未连接分析服务，所有示例文本人工合成，不包含真实 APK、完整第三方政策或个人信息。界面演示没有网络业务请求、存储或上传。

## 6. 事实状态映射与 DS 接入清单

| 展示 | 后续真实来源与边界 |
| --- | --- |
| 来源 | `job.source_origin`；REAL_SCAN 只表示真实 APK 静态扫描来源，不证明本次实时生成 |
| 送达方式 | `delivery_mode`；LIVE_GENERATED / PERSISTED_REPLAY 与数据来源是两个维度 |
| 覆盖 | 实际 result coverage/DEX 成功失败与限制；UNKNOWN 不能默认 COMPLETE |
| 复核/提取/完整性/附件 | 每份实际政策文档状态分别显示，不用“政策已获取”替代完整复核 |
| 数量 | 数据类型去重、政策来源和当前可追溯证据分别计数，不表示质量或风险 |
| 结论/证据 | 实际问题与 evidence_ids、document_id/定位绑定；缺失保留空/未知，不自行补齐 |
| 适用性 | 保留应用/版本/完整政策与上下文，NOT_DECLARED 不能在缺复核等前提时升级为确定结论 |

后续由用户交给 DS 的完整前端工作：

1. 读取本规范与示例，确认最新 main/#160 组合版本及共享文件 owner，再串行迁移主题。当前 PR 不替换 #160 的既有业务增量。
2. 编写生成契约→展示模型的适配层，复用已有 EvidencePanel/材料/摘要组件的语义和事件；本轮仅展示，不能照搬合成数据到真实报告。
3. 将视觉应用到导入、候选、进度、设置和 Tauri 手机流程；保留既有 busy/取消/重试/删除/错误恢复与原生桥。
4. 移动报告采用本轮下方证据区；其他适合 sheet 的业务继续使用已选 Reka，不整站换组件库。
5. 保留包名、哈希、适用版本、覆盖限制、政策复核、附件等可展开的真实信息。不要为了像示意图而删事实。
6. 运行 A–E、reading 与新的 design 检查，重新对照截图；接入产品需要对应 Android/WebView/IME/安全区/字体/TalkBack 验证，本轮浏览器结果不替代。
7. 未经用户授权不合并、部署或关闭旧票。
8. 将[已采纳#167合同](copy-contract-167.md)应用于全部业务入口；当前基座已提供统一命名与状态格式接缝，旧页面迁移/十个旧键清理/阶段统一/表格守卫同步仍待完整接入。

9. 按[实用UI/UX布局合同](ux-layout-contract.md)接入单一流程、证据选择上下文、状态分层与操作位置；真实数据、返回/恢复和设备验收逐项补证。

## 7. 预览与验证

```powershell
npm ci
$env:PRIVACYTRACE_WEB_PORT='5191'
npm run dev:start
# 浏览器：/design.html；组件：/design.html?view=components
npm run acceptance:design
npm run dev:stop
powershell -NoProfile -File scripts/check.ps1
```

可访问状态：`?state=empty`、`?state=unknown`、`?state=long`。生产构建同时输出 index.html 与 design.html；独立样式只由设计入口加载，原业务入口不变。设计页 noindex。

容器构建同样精确包含 design.html：deploy/Dockerfile 的 COPY、Dockerfile.dockerignore 与 audit_context.py 的单文件 allowlist 同步维护。没有扩大到复制整个页面目录或私有材料。专项预览用 strictPort 并清理 Vite 终端色码后核对自身启动地址，兼容 Linux CI 彩色输出，不复用端口上的未知服务。

专项脚本验证构建产物与真实 Chromium：五种视口、200% 文字、长文本/空/未知、字段错误/等待/禁用、键盘 skip/focus、移动证据定位与返回、政策展开、减少动态效果、无业务 API 请求与原业务入口隔离；注入错误面板底色/主色/身份条，证明视觉守卫会拒绝漂移。结果与截图在 `tmp/concept-foundation`；CI Browser Acceptance 同步运行并上传。

[验证与截图索引](verification.md) 记录实际执行结果。浏览器模拟与设计合成材料不是 Android APK/物理真机或真实服务证据。

## 8. 技能指导

使用用户显式指定的 frontend-design：紧凑 token 计划 → 对照已选概念 → 实现 → 实际截图批评；用户固定的 NASA-punk 方向和后续恢复 Pioneer 字体决定优先于通用技能的审美默认值。grill-with-docs 的 grilling/domain-modeling 已完成上述决策，后续重点标记与字体补充直接纳入同一规范，未凭空扩充领域模型。

既有调研采用 [Impeccable 指南](https://github.com/pbakaus/impeccable/tree/dad8dbb3aac21ad1fa236c110315ef4abece23e8/.agents/skills/impeccable)、UI/UX Pro Max、make-interfaces-feel-better 的层次/克制/触控/焦点方法。Impeccable 仅阅读文档，未安装或声称运行其检测器。继续复用 Vue 3 / 已选 Reka 和现有控件；不新增运行时库、字体 CDN、全局工具或动效依赖。onetake 是视频方向，不作为 UI 运行时。
