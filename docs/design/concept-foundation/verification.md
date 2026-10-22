# 验证与截图

这些是**实际构建产物在 Chromium 中的合成材料界面**，不是真实 APK/Android 实机，也不是用户上传的概念图重画。概念来源见 [规范](README.md)，已采纳文案见 [#167 合同](copy-contract-167.md)。

本轮还落实[六项UI/UX布局合同](ux-layout-contract.md)：单流程、约55:45、当前条目上下文、选中/复核/结论分层、唯一主操作区与对象明确的按钮。

## 已执行

| 检查 | 结果 / 边界 |
| --- | --- |
| `npm run acceptance:design` | 158 项通过，28 张实际浏览器截图；5 种视口、空/未知/长文本、320/390 的 200% 文字、证据选择/定位/返回焦点、政策原文、字段/等待/禁用、skip link、减少动效、旧入口隔离 |
| 视觉合同 | 白色主要面板、仅顶栏米白、红主操作/白字、四色品牌与唯一重点信息条、1px 直角面板、Pioneer 三类字体角色；6 种错误样式/字体/字号注入被守卫拒绝 |
| UI/UX关联 | 五视口流程唯一/当前步骤；左选中项、右证据编号/对象/条数一致；引用排他；主操作对象更新；报告元数据默认折叠、展开保留事实 |
| 字号与首屏 | 标题48px/手机36px，条目28/24px，区段22/20px，阅读正文16px；同时验证主标题/条目相对正文的显著比例。1280×720 第一条“查看对应证据”完整位于首屏（底边约656px） |
| 文案与来源状态 | 报告唯一新h1、对照节名、单全局示例标记、同一状态行真实渲染断言通过；3项状态函数测试覆盖缺失未知、正文完整不等于已复核、附件事实独立 |
| `npm run acceptance:frontend` | 既有导入/候选/报告/设置/焦点流程通过；14 个 mock 报告请求、12 项手机断言、政策辅助 10 项 HTTP/UI 检查通过 |
| 独立需求/标准审阅 | 基座初版完整审阅及本轮文案复看无未修阻塞；来源复核/正文完整度/附件事实独立，提取和覆盖保留，完整业务迁移另列DS清单 |
| 独立视觉审阅 | 本轮重要字体清楚、双端比例协调；六项布局独立复看无阻塞；320px/200%按钮窄列与元数据逐字换行已修正并复看，主操作四行完整可达；1280首条证据入口仍在首屏 |
| 权威 `npm run check` | 本轮通过：API 1567 passed / 200 skipped，e2e 61 passed / 4 skipped，前端 126 passed；schema/治理/lint/构建通过。六项UI/UX布局修正并吸收main 45c409d（#148移动轮询修复）后，同一权威检查再次通过；原前端回归与设计158项也已重跑；最终提交的远端权威检查另由PR CI核对 |
| CI 接线回归（历史） | 基座初版CI发现容器缺少design.html与Linux Vite彩色输出ready误判，已在先前提交修复；本轮沿用该接线。旧提交的绿色结果不代替本轮最终SHA验证 |

200%检查保持320/390 CSS像素视口，将根文字放大到200%；不是把视口缩成160/195 CSS像素。除完整长图外，另外截取首屏、条目及主操作视口，验证文字与触控入口可读、无覆盖。

[verification.json](evidence/verification.json) 包含代码输入 SHA-256、生成时间、逐项结果及28张截图哈希。仓库保留以下8张代表图，其余由专项命令生成，并由CI工件归档。输入哈希覆盖设计组件、样式、共享copy、Vite入口、package.json、构建接线与验证脚本；最终交付SHA记录在PR/Issue中。

## 实际截图

- [1440 桌面完整报告](evidence/report-1440.png)
- [1280×720 首屏](evidence/report-1280-viewport.png)
- [390 手机完整报告](evidence/report-390.png)
- [390 组件展示页](evidence/components-390.png)
- [320 / 200% 报告](evidence/large-text-320-report.png)
- [320 / 200% 组件展示](evidence/large-text-320-gallery.png)
- [320 / 200% 条目视口](evidence/large-text-320-finding-viewport.png)
- [320 / 200% 主操作视口](evidence/large-text-320-action-viewport.png)

## 范围和未执行项

- 本轮不调用业务API、模型服务或真实扫描；合成材料全局标记“示例体验 · 固定材料”，材料身份保留。
- Android APK/WebView、物理真机、真实IME、安全区、系统字体与TalkBack：**NOT_RUN**。
- 完整导入→候选→进度→报告新视觉与#167全站文案接入：留给DS后续开发；既有业务回归通过不表示这些页面已改为本次视觉/文案。
- 没有合并、部署、发布或关闭原任务；skipped不计入通过。
- 无新增运行依赖，复用已选Vue/UiButton/UiField/StatusTag和Pioneer本地字体。此次构建的独立设计资产约17.30kB JS / 17.17kB CSS（gzip7.19 / 4.12kB，另有与现有入口共享的Vue/控件chunk）；这不是整站包体差值。

## 2026-10-22 DS 接入

本节记录 `codex/design-integration-165` 本轮把 #165 布局与 #167 文案接进真实业务入口后的实际检查。上面的“已执行”一节只证明设计基座版本，不代替本节。

### 命令与结果

记录来源：`docs/acceptance/issue165/20261022.md` 与 `docs/acceptance/issue165/copy-contract.json`。验收对象为产品代码 `cdbb2d5`（含 merge `origin/main` `e17d2e3` 后的移动轮询与视觉/标准审阅修复）；此后只提交验收记录与截图，不再改 `apps/web/src`。`copy-contract.json` 在干净工作树运行，记录 `commit=639eee1`、`dirty=false`；`639eee1` 只比 `cdbb2d5` 多文档提交，产品代码一致。

| 命令 | 结果 | 关键计数 | 证据 |
| --- | --- | --- | --- |
| `npm run test --workspace @privacytrace/web` | PASS | 132/132（126 既有 + 6 copy-contract） | 终端输出 `tests 132 / pass 132 / fail 0` |
| `PRIVACYTRACE_FRONTEND_URL=http://127.0.0.1:5191 npm run acceptance:frontend` | PASS（exit 0） | frontend-flow：brand 103 项、reports 15 项移动断言；policy-assist：10 项真实 HTTP/UI | `tmp/issue44-ui/verification.json`、`tmp/issue72-policy-assist/verification.json` |
| `node scripts/verify-copy-contract.cjs`（acceptance:frontend 的合同阶段；无 env，自启 dev server，干净树） | PASS | 42 checks / 23 张截图 | [copy-contract.json](../../acceptance/issue165/copy-contract.json)、[截图目录](../../acceptance/issue165/screenshots/) |
| `PRIVACYTRACE_FRONTEND_URL=http://127.0.0.1:5191 node scripts/verify-issue143-hierarchy.cjs` | PASS | 11 checks | `tmp/issue143-hierarchy/verification.json` |
| `PRIVACYTRACE_FRONTEND_URL=http://127.0.0.1:5191 node scripts/verify-issue146-motion.cjs` | PASS | 20 checks | `tmp/issue146-motion/verification.json` |
| `PRIVACYTRACE_FRONTEND_URL=http://127.0.0.1:5191 node scripts/verify-issue145-a11y.cjs` | PASS | 14 checks | `tmp/issue145-a11y/verification.json` |
| `node scripts/verify-mobile-flow.cjs` | PASS | 13 组（含移动品牌位） | `tmp/issue72-native/walkthrough.json` |
| `node scripts/verify-mobile-reading.cjs` | PASS | 7 checks / 8 screenshots | `tmp/mobile-reading/verification.json` |
| `node scripts/verify-frontend-round2.cjs` | PASS | 21 checks / 23 screenshots | `tmp/issue144-round2/evidence/mobile-round2-walkthrough.json` |
| `node scripts/verify-round2-primitives.cjs` | PASS | 15/15 | 终端输出 |
| `npm run build && node scripts/verify-design-foundation.cjs` | PASS | 158 checks / 28 screenshots | `tmp/concept-foundation/verification.json` |
| `node scripts/verify-browser-acceptance.cjs` | PASS（exit 0，TC-01～TC-05 全跑） | 见运行日志 | `tmp/browser-acceptance.log`；`evidence/` 历史 receipt 未被覆盖 |
| `node scripts/verify-frontend-preview.cjs` | PASS | preview 生命周期/所有权/失败恢复 | `tmp/frontend-preview/verification.json` |
| `node scripts/verify-live-flow.cjs` | NOT_RUN | 本机无 Docker（`docker` 命令不存在） | 见下方 NOT_RUN |
| `bash scripts/check.sh`（Git for Windows Bash，在 `cdbb2d5` 工作区） | PASS（exit 0，末行 `PrivacyTrace checks passed.`） | 含 API pytest、tests/e2e、ruff、schema 导出、品牌资产校验、前端 132/132 单测与构建 | Lead 执行的权威检查输出 |

本节按已提交的验收记录填写，未把 NOT_RUN 写成通过；`acceptance:frontend` 因本机 5184 被其他 worktree 占用，显式复用 5191 受管预览。权威 `bash scripts/check.sh` 由 Lead 在 `cdbb2d5` 工作区执行并通过，见上表；此后仅文档与截图提交。

### 检查项

| 检查项 | 期望（脚本断言） | 结果 |
| --- | --- | --- |
| 单 `#page-title` | 六个面（导入/候选/进度/示例报告/设置/存档）每次恰好一个 `#page-title`，文本来自 `frontendCopy.pageTitles`；同时恰好一个 `h1` | PASS（六个面逐一断言） |
| 单流程导航 | 恰好一个 `nav.flow-nav`、四个步骤、恰好一个 `aria-current="step"`；旧 `.step-nav` 为 0 | PASS（导入/候选/进度/报告/存档逐一断言） |
| 五视口（1440 / 1280 / 768 / 390 / 320） | 每个视口无横向滚动；`.report-columns` 在 ≤896px 为 `stacked`、以上为 `columns`；流程条保持一行 | PASS（1440/1280/768/390/320 无横滚；`.report-columns` 与断点一致；流程条单行） |
| 200% 根文字（320 / 390 视口） | 无横向滚动，红色主操作仍可见 | PASS（390/320 均无横滚，主操作可见） |
| 单示例标记 | 恰好一个“示例体验 · 固定材料”；已退役标记（固定示例内容 / 示例阶段已切换 / 仅示例有效）为 0 | PASS |
| 表头与 `data-label` | 对照表表头为 `数据类型` / `证据`，每个单元格都有 `data-label`；已退役的 `依据` / `隐私数据` 不回归 | PASS（旧标签 0 处） |
| 统一来源状态行 | 导入每个来源、候选来源条、报告来源摘要与实际值展开行都渲染 `来源未复核 · 正文完整度未知 · 附件未检查`，且不出现“已复核” | PASS（三处入口 + 展开的逐来源行） |
| 单红主操作与对象 | 示例报告恰好一个红色主操作，文案包含当前选中对象；切换条目后对象同步 | PASS（切换后文案变为“设备标识”） |
| 选择与证据区 | 恰好一个条目为当前选择（`aria-pressed`），其 `aria-controls` 指向唯一证据区；切换后仍只有一个当前项；“返回刚才的操作”把焦点还给触发行 | PASS |
| 存档嵌入 | 存档页单 h1（本机存档报告）、无当前流程步、嵌入视图不渲染第二品牌栏与第二 hero | PASS（1440/390 无横滚） |
| 设置弹窗 | 打开后仍只有一个 h1；1440/390 无横向滚动 | PASS |
| 无业务请求 | 示例流程不调用 scan/report API；存档只读取任务列表；浏览器无页面错误 | PASS（示例流程 ledger 为空；存档请求仅 `/api/v1/jobs`；`pageErrors: []`） |

### 截图

[`docs/acceptance/issue165/screenshots/`](../../acceptance/issue165/screenshots/) 目录内共 26 张：copy-contract 产出 23 张（42 checks），另有 3 张 #169 品牌截图（见 #169 节）。独立视觉审阅指出旧截图没有报告首屏与移动主操作帧，已重拍：

- [import-1440](../../acceptance/issue165/screenshots/import-1440.png)、[candidates-1440](../../acceptance/issue165/screenshots/candidates-1440.png)、[progress-1440](../../acceptance/issue165/screenshots/progress-1440.png)
- 报告首屏（scrollTop=0）：[report-1440-top](../../acceptance/issue165/screenshots/report-1440-top.png)、[report-1280-top](../../acceptance/issue165/screenshots/report-1280-top.png)、[report-768-top](../../acceptance/issue165/screenshots/report-768-top.png)、[report-390-top](../../acceptance/issue165/screenshots/report-390-top.png)、[report-320-top](../../acceptance/issue165/screenshots/report-320-top.png)
- 报告交互帧（选中第二行 + 证据区）：[report-1440](../../acceptance/issue165/screenshots/report-1440.png)、[report-1280](../../acceptance/issue165/screenshots/report-1280.png)、[report-768](../../acceptance/issue165/screenshots/report-768.png)、[report-390](../../acceptance/issue165/screenshots/report-390.png)、[report-320](../../acceptance/issue165/screenshots/report-320.png)
- 移动主操作帧：[report-390-action](../../acceptance/issue165/screenshots/report-390-action.png)、[report-320-action](../../acceptance/issue165/screenshots/report-320-action.png)
- 200% 根文字首屏：[report-390-200-top](../../acceptance/issue165/screenshots/report-390-200-top.png)、[report-320-200-top](../../acceptance/issue165/screenshots/report-320-200-top.png)；200% 主操作帧：[report-390-200](../../acceptance/issue165/screenshots/report-390-200.png)、[report-320-200](../../acceptance/issue165/screenshots/report-320-200.png)
- [settings-1440](../../acceptance/issue165/screenshots/settings-1440.png)、[settings-390](../../acceptance/issue165/screenshots/settings-390.png)
- [archive-1440](../../acceptance/issue165/screenshots/archive-1440.png)、[archive-390](../../acceptance/issue165/screenshots/archive-390.png)

其他脚本截图位置：`tmp/issue44-ui/screenshots/`、`tmp/concept-foundation/`、`tmp/issue144-round2/evidence/`、`tmp/mobile-reading/`、`tmp/issue72-native/`、`tmp/issue143-hierarchy/`、`tmp/issue145-a11y/`、`tmp/issue146-motion/`、`tmp/issue72-policy-assist/`。`docs/acceptance/issue144/round2/` 为历史证据，本轮未替换。所有截图都是 Chromium 合成示例，不是真机或真实扫描证据。

### 失败与修复记录

- 实现缺陷（已修复并复跑）：`label.text-upload` 在 390px 仍是 44px，Lead 在 `style.css` 的 ≤896px/coarse 媒体块补 48px（`24ee58b`），并给 Reka 传送到 `<body>` 的设置弹窗单独补 48px（`8d63e49`）；`MobileApp.vue` 进度卡硬编码“报告已生成”，改为 `frontendCopy.stages.SUCCEEDED`（`a0ab4db`）。
- 验收脚本问题（非产品缺陷）：`verify-browser-acceptance` 首次并行运行因端口/时序竞争失败，串行重跑 exit 0，失败日志保留在 `tmp/browser-acceptance.log`；`verify-frontend-preview` 首次运行因 `dev:stop` 与所有权控制面收尾竞争留下孤儿 daemon，人工确认后终止并清理 `tmp/frontend-preview/state.json`，重跑通过；`verify-frontend-round2` 的输出改到 `tmp/issue144-round2/evidence/`，未替换 `docs/acceptance/issue144/round2/` 历史截图。
- 守卫断言按合同同步：9 个旧浏览器守卫与单测 mock 因四步名/报告名/表头/状态行/证据区结构变化而失效，已按用户采纳的新合同同步，未删除测试面、未放宽行为断言；分类明细见 `20261022.md` §3。品牌 `<img>` 的 `naturalWidth` 口径修正属于守卫问题，不改变产品断言强度。

### 独立视觉审阅与修复

独立视觉审阅（只读，逐张读取截图并做像素核对）确认 176px 侧栏、1.15:1 双栏、字号层级、四色带、唯一红主操作、状态语义与品牌图形达标，同时指出四类问题；已修复并复跑：

1. 取证方式：旧截图在“选中条目→滚动到证据区”之后拍摄，报告页没有首屏。`verify-copy-contract.cjs` 新增 `resetScroll`，五视口补拍 scrollTop=0 首屏；移动端补拍“当前对象 + 全宽 56px 主操作”帧；200% 补首屏与主操作帧。断言从 `isVisible()` 改为实际滚动可达 + 高度/宽度校验，并新增 1280×720 首条证据入口在首屏内的断言。
2. 选中态边框缺失：`tbody td { border: 0 }` 特异性压过 `.finding-type` 的 3px 左边框。改为在 `td.finding-type` 上声明边框宽度，窄屏卡片把 3px 边移到 `tr` 上；1440/768/390 截图可见“文字 + 边框”。
3. 200% 层级倒置：导航/侧栏动作原用 rem，放大后 26px 反超 20px 区段标题。改为 `clamp(12px, .8125rem, 15px)`（窄屏 `clamp(11px, .75rem, 13px)`），200% 时导航仍低于 h1 36px 与区段 22/20px。
4. 身份块与状态样式：`.sample-monogram` 加 `aspect-ratio: 1` 与 `flex: 0 0 auto`，长包名允许在块内换行；来源状态行移到数量之前；两栏面板标题统一 22px；存档错误态改为中性文字 + 双线边框（不再出现第二处红）；桌面主操作维持 45px（fine pointer），≤896/coarse 为 56px，与 `pioneer-design.json` 的 `actionMinHeight`/`actionMinHeightNarrow` 一致。

审阅建议但未改的项：示例报告使用单行来源计数（真实报告保留三格计数）；进度页面板标题“示例材料”属于材料身份；候选页“待检查/已检查”是候选检查状态，与报告“条目复核”是不同语义；30px 品牌槽位保持不放大以不改变顶栏度量。上述差异记录在此，不作为未完成项。

复核轮（code-review 双轴）已修：移动证据改为列表下方内联证据区（复用同一 `EvidencePanel`，无 sheet/overlay；首条自动选中、返回保留所选条目）；条目复核状态与结论标签分离；删除重复的“材料/人工构造示例”行；证据区标题回到 22/20px；`--pt-*` 与 design foundation 增加颜色 token 相等性单测；部署构建上下文 allowlist 纳入 `apps/web/public/brand/**`（容器内图标不再 404）；`acceptance:copy` 折叠进 `acceptance:frontend`，不再单独占 CI 入口。

### NOT_RUN

- 真实 APK / 真实受限 Docker 扫描 / 真实模型服务：`verify-live-flow.cjs` NOT_RUN（本机无 Docker）。
- Android WebView、真机、真实软键盘 IME、安全区（display cutout）、系统字体缩放、TalkBack：NOT_RUN；移动相关脚本只是 Chromium 模拟。
- 真实离线导出包（`?presentation=offline` 由导出包写入 meta）：NOT_RUN；离线顶栏断言用 Playwright 注入 meta 模拟。
- 真实读屏（NVDA/VoiceOver）：NOT_RUN。
- 合并、发布、部署：未执行，也不在本记录声明范围内。

## #169 品牌接入（2026-10-22）

品牌工作在本分支继续交付：`afaa300`（入库 Concept C 资产并接入 Web 图标）、`286fae1`（三处顶栏品牌位）、`cbf056a`（Android 图标覆盖管线与校验接线）、`5781ffc`（补品牌顶栏截图并静音品牌桩告警）。验收记录见 `docs/acceptance/issue165/20261022.md` §4.3 与 `tmp/brand-assets/verification.json`。本节只记 #169，不回填 #165 的数字。

### 资产与接入事实

- `brand/` 源资产 29 个文件（除 `brand/README.md` 与 `brand/SHA256SUMS` 外），随图标包原字节入库；`brand/SHA256SUMS` 是逐文件清单，`verify-brand-assets.cjs` 已在权威检查中逐条比对并检测未列入清单的资产。
- `apps/web/public/brand/` 的 4 个分发副本由 `verify-brand-assets.cjs` 逐字节比对源文件（symbol SVG、favicon SVG、icon-192、icon-512）。
- `brand/android/res/` 20 个 launcher 资源：2 个 adaptive XML、3 个 drawable 矢量、5 个密度各 3 张位图；`scripts/apply-brand-android-icons.cjs` 负责覆盖，`scripts/verify-brand-assets.cjs` 已由 `scripts/check.sh` 第 43 行接线。
- 三处顶栏品牌位：工作台 `.workspace-brand .brand-mark`（`WorkflowApp.vue`）、离线报告 `.topbar .brand-icon`（`App.vue`）、移动 `.m-appbar-brand`（`MobileApp.vue`，仅导入步渲染）；图标 link 在 `apps/web/index.html`（favicon SVG、512 PNG、apple-touch-icon 192）。

### 检查项

| 检查项 | 结果 |
| --- | --- |
| favicon / 512 PNG / apple-touch-icon / symbol 同源 200，内容可解析 | PASS（`verify-frontend-flow.cjs` 品牌断言，随 103 项一起运行） |
| 工作台品牌 `<img>`：`complete`、`currentSrc`、`decode()`、渲染框、`naturalWidth>0`，品牌槽无字母占位，链接 accessible name 保留 | PASS |
| 1440/1280/768/390/320 与 200% 根文字下，品牌不遮挡标题与“项目设置”按钮 | PASS |
| 移动 appbar 导入步品牌 `<img>` 解码、同源资产 200、无字母占位；非导入步不渲染品牌槽且保留返回按钮 | PASS（`verify-mobile-flow.cjs` 13 组） |
| 离线报告入口 `.topbar .brand-icon` 品牌 `<img>` 解码、同源资产 200、无字母占位 | PASS（`verify-issue143-hierarchy.cjs` 11 checks） |
| Web 分发副本与 `brand/` 源逐字节一致（4 对） | PASS（17 checks / 46 文件 / 幂等 true） |
| Android 源 20 个文件齐全，adaptive XML 结构合法、`@drawable` 引用存在且为有效 vector | PASS（同上） |
| 覆盖管线在模拟 res 树上：文件集合一致、逐字节哈希一致、保留无关模板资源、二次运行幂等 | PASS（同上） |
| 覆盖管线失败用例：目标目录缺失、模板漂移（缺 `ic_launcher_round.xml`）均以非零退出并给出原因 | PASS（exit 1 / matched true） |

品牌颜色与尺寸规则记录在 `brand/README.md` §3–§4；本轮校验针对文件一致性与 Android 资源结构，没有逐色值/逐尺寸的浏览器取证，按“静态资源规则”而非“视觉验收”理解。

### 截图与证据

- 品牌专属截图（由 brand-topbar 的真实 Chromium 断言运行产出，`5781ffc` 入库）：
  - [brand-topbar-1440.png](../../acceptance/issue165/screenshots/brand-topbar-1440.png)：工作台顶栏品牌位
  - [brand-mobile-390.png](../../acceptance/issue165/screenshots/brand-mobile-390.png)：移动 appbar 品牌位
  - [brand-offline-1440.png](../../acceptance/issue165/screenshots/brand-offline-1440.png)：离线报告顶栏品牌位
- 其余品牌断言随 `verify-frontend-flow`、`verify-mobile-flow`、`verify-issue143-hierarchy` 运行，截图在各脚本的 `captureWidths` 输出目录（如 `tmp/issue44-ui/screenshots/`）。
- `tmp/brand-assets/verification.json`：17 项检查、46 个文件哈希、2 个失败用例、`idempotent: true`、`errors: []`。

### NOT_RUN

- Android Gradle `assemble`/构建、APK 打包与实机安装。
- 真实设备 Launcher 的圆形/圆角裁剪、主题图标（monochrome/themed icon）与不同厂商桌面效果。
- Tauri `android init` 重初始化流程的端到端验收；本轮只验证资源映射与覆盖脚本在模拟 res 树上的行为。
- Tauri 平台图标重新生成（`tauri icon`）；本轮只替换源 `apps/mobile/src-tauri/icons/icon.png`。
- 真实浏览器标签页、Safari apple-touch-icon、PWA 主屏图标的渲染截图；本轮只验证 link 路径与文件一致性。
- `brand/SHA256SUMS` 全量比对已纳入 `scripts/check.sh`（`verify-brand-assets.cjs`，29/29 通过）；Gradle/实机项仍为 NOT_RUN。
- 部署与商店资源提交。
