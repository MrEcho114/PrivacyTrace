# PT-906-B1 创意来源定稿与作品介绍补齐

- 日期：2026-10-23
- 任务：Issue [#220](https://github.com/MrEcho114/PrivacyTrace/issues/220)（父票 #107，来源 #197）
- 范围：报名系统「创意来源」字段定稿；包内 `03_作品介绍文档/作品介绍.md` 新增「创意来源与原创贡献」节，并导出 A4 PDF
- 事实来源：`#197` 复核终报、`#74` §4 第 09 项与 §6.3、包内 `03`/`05`/`source` 原文、仓库实现。文案只写有锚点的事实。

## 一、结论

1. 系统字段定稿 278 字（汉字 223），可直接粘贴，见第二节。
2. `03` 新增一节的全文见第三节，五个三级小节，原「能做什么 / 边界 / 组成」正文未改动，只改了一行目录说明（见第六节）。
3. 包内 `03` 没有 tracked 源，只活在 `.scratch/package-final/` 的打包副本里，而且那个包正被 B3/B4 并发重建。本页交定稿文本、排版源与执行步骤，由打包会话（B5）并入并重冻结。
4. PDF 已实测产出：2 页 A4、397,107 B、SHA-256 `17E2221B…`，元数据只剩 `/Title`，字节级零工具链残留。第 1、2 页均渲染后逐页看过。

## 二、系统字段定稿（「创意来源」，278 字）

```text
移动应用的隐私合规核验一直靠人工。这边翻反编译结果找敏感调用点，那边读隐私政策找对应声明。两边对不上时，说不清缺的是哪一句话、哪一段代码。第三方 SDK 把调用链层层包起来，人工在几十页政策里更难找到对应的一句。核对工具的常见做法是给一个“合规”或“不合规”的结论，指不出证据落在哪个类、哪条指令、哪句话。PrivacyTrace 把两端各自能定位的东西连起来：APK 侧定位到类、方法和字节码偏移，政策侧定位到原句与码点区间。连得上就是一条可复核的对应关系，连不上就报缺口和 UNKNOWN。静态线索只表示潜在能力，不证明实际采集，也不替代人工法律判断。
```

字数：含标点 278、汉字 223、句子 8。系统「创意来源」的字数上限在仓库内**查无实数**（`#197` 只写「受系统字数上限约束」），字段按 ≤300 字预算定稿。

## 三、`03` 新增节全文

插在开头定位段与边界引用块之后、`## 能做什么` 之前。

```markdown
## 创意来源与原创贡献

### 创意来源

移动应用的隐私合规核验一直靠人工。这边翻反编译结果找敏感调用点，那边读隐私政策找对应声明。两边对不上时，说不清缺的是哪一句话、哪一段代码。第三方 SDK 把调用链层层包起来，人工在几十页政策里更难找到对应的一句。

核对工具的常见做法是给一个“合规”或“不合规”的结论，指不出证据落在哪个类、哪条指令、哪句话。被质疑时，双方只能把材料重新翻一遍。

APK 的静态内容可以定位到字节偏移。政策原文可以定位到码点区间。PrivacyTrace 把这两端连起来：连得上就是一条可复核的对应关系，连不上就报缺口和 UNKNOWN。

### 创新点

**一、双向可定位的证据对齐。** 静态侧的证据定位串带 `apk_sha256`、`dex`、`caller`、`offset_bytes`、`target`。政策侧带 `start_offset`、`end_offset` 和 `codepoints [start,end)`，写入时校验按该区间切出的文本等于所引原句。两端共用一套证据模型，一条对照结论能同时回到字节码位置和政策原句。

**二、按字段分域的证据状态。** 静态证据只能取 `STATIC_POTENTIAL`，政策声明只能取 `DECLARED`，混用直接报错。对照结论有六个值：`EXACT_MATCH`、`CATEGORY_MATCH`、`NOT_DECLARED`、`POLICY_SOURCE_CONFLICT`、`AMBIGUOUS_DISCLOSURE`、`INSUFFICIENT_EVIDENCE`。政策侧另记 `completeness`、`extraction_status`、`review_status`、`attachments_status` 四组状态。用途、接收方、传输范围、时间范围在证据不足时保持 `UNKNOWN`。状态不合并，不随交付升级，`UNKNOWN` 不会变成“没问题”。

**三、绑定生成时点的离线回放报告。** 导出报告时，程序写入两个时点：分析生成时点 `analysis_generated_at`、回放包生成时点 `offline_package_built_at`，并标记 `presentation_mode="OFFLINE_REPLAY"`。离线包用 `manifest.json` 记录逐文件 SHA-256。查看器启动时校验文件集与哈希，不一致就拒绝；查看过程只读，写操作返回 405。评委看到的报告和当时跑出来的报告是同一份。

**四、在独立冻结的真值上做受控基准评测。** 受控场景自带源码、政策和特征文件。`ground-truth.json` 在本版首次算法运行前冻结，`.sha256` 固定其字节，后续修订另建版本，不能按系统输出回改。定位参考由固定版本的 Android Build Tools `dexdump -d` 生成，独立于被测扫描器用的 Androguard，不读预测、报告或扫描器偏移。十二个场景的 36 行三方案比较里，本系统与两个朴素方案（权限＋关键词、API＋扁平规则）的状态一致数分别是 12/12、2/12、4/12。这组数字量的是对受控目标状态的对齐情况，跟准确率无关，也不外推到真实应用。

### 实现方案

主线是：APK 与政策材料 → 本机或部署 API → 隔离扫描 → 静态证据与政策候选对照 → Web 或 Android 报告。

- **Web**：Vue 3、TypeScript、Vite，做材料工作台、任务状态、报告与证据下钻；
- **API**：Python、FastAPI、Pydantic，做输入与政策处理、作业与持久任务、规则对照、报告模型；
- **静态分析**：Androguard 与受限 Docker Worker，解析 Manifest / DEX，按规则约束提取敏感调用线索；
- **部署运行时**：PostgreSQL、Redis、Celery、mTLS Runner，负责持久任务、投递、隔离执行与健康检查；
- **Android 端**：Tauri 2 壳层，原生模块负责选应用、读包集合与上传，界面复用 Web 侧实现；
- **规则数据**：团队把 taxonomy 与 SDK 签名做成版本化数据文件（当前 taxonomy 0.3.0、SDK 签名 1.0.0），跨端用 JSON Schema 契约约束输入、结果与报告。

### 完成状态

团队完成开发与内部验收。R01–R04 全部 PASSED，含 1 项既有豁免 `dedicated-scan-host-verification`。pytest `1578 passed / 179 skipped`，`65` 项端到端用例通过，四个入口验收 4/4（browser、frontend、live（真实 Docker）、mobile）。验收摘要与浏览器证据随包提供，见 `05_补充成果材料/`。

120 秒 1080p 演示片和离线回放包已随包交付。内部验包通过不等于已公开发布，也不等于已在竞赛平台提交。

### 原创贡献

团队设计并实现系统架构、静态证据模型、规则对照逻辑与验收脚本。证据定位口径（`offset_bytes` 是相对方法指令区起点的字节偏移）由团队独立定义，并另建定位参考核对。

团队构建受控场景、政策文本与预期答案，在运行前冻结。本文的评测数字由团队在受控环境实际执行得到，未由工具生成或补齐。

生成式 AI 用于样板代码与文档排版等辅助环节，工具清单和代表性工作流见 `07_AI工具使用补充说明/`。AI 输出进入代码或文档前由团队筛选、修改与重写。本文的技术口径与数字以仓库实现和随包收据为准。
```

> **口径说明（不属于 03 正文）**：上面这段的 `1578 passed / 179 skipped` 与 `65` 项端到端引用的是包内 `05_补充成果材料/验收摘要.md` 的 R01 收据（`deccced` 重建时点）。本票随后在 base `912b523` 上复跑的本地闸门为 `1619 passed, 200 skipped` 与 `61 passed, 4 skipped`（见「本地闸门与 CI」）。两组数字是不同时点的不同运行，不能互相替代；对外引用必须带来源，且 **skip 不计入「通过」**。

## 四、定稿取舍

| 决定 | 取值 | 理由 |
| --- | --- | --- |
| 字段字数预算 | ≤300 字，单段 | 系统上限查无实数；300 是保守上限，实测 278 字留了改稿余量 |
| 创意归因层 | 领域痛点 → 方法学缺口两级 | 全程可复核、天然过匿名化；个人动机不编造 |
| 字段内创新条数 | 2 项（双向对齐、缺口与 UNKNOWN） | 300 字放不下四项；四项全在 `03` 展开 |
| 创新点总数 | 4 项 | 上限按 `#74` §4 第 09 项「2–4 项」；四项都有代码锚点 |
| 原创贡献口径 | 分工陈述，不写任何百分比 | `07` 要如实披露 AI 参与；写「100% 自主」与披露冲突 |
| 03 结构 | 定位段后新增一节，五小节 | 顺序对齐 `#74` §4 第 09 项的叙述次序 |
| 文档格式 | Markdown 为源 + A4 PDF | `#74` 建议 PDF；PDF 会重开 Check 2，故必须清元数据 |
| 落地方式 | 文本交打包会话并入 | `03` 无 tracked 源，包正被并发重建 |

术语方面本票**未新增 GLOSSARY 条目**：创意来源、创新点、原创贡献是报名系统的表单语汇，不属于 PrivacyTrace 的产品领域语言；写进术语表会把它当成系统概念。三者在文案里的分工由本页固定。

## 五、依据（每条都能点回去）

- 双向对齐：`apps/api/src/privacytrace/apk_worker.py:509-512`（`offset_bytes`、`caller`、`target`）；`apps/api/src/privacytrace/policy_intake.py:436-453`（`start_offset`/`end_offset`/`codepoints`）；`apps/api/src/privacytrace/models.py:54-66`、`:288-294`（区间切出的文本必须等于原句）。
- 状态分域：`models.py:24-30`（`MatchStatus` 六值）、`:56-57`（`STATIC_POTENTIAL`/`DECLARED`）、`:68-72`（混用报错）、`:111-114`（四字段锁 `UNKNOWN`）、`:126-129`（政策侧四组状态）。
- 离线回放：`scripts/export-offline.py:114`、`:156-158`（双时点与 `OFFLINE_REPLAY`）；`apps/api/src/privacytrace/pipeline.py:177`；`01_作品及成果文件/demo-web/viewer.py:11-23`、`:35-36`（包内路径，哈希校验与 POST 405；仓库内对应实现是 `scripts/offline-viewer.py`）。
- 受控评测：`benchmarks/controlled-v2/README.md`（真值冻结口径）；`benchmarks/locator-reference-v1/README.md:4`（`dexdump -d` 独立于被测扫描器）；`01_作品及成果文件/source/README.md:117`（12/12、2/12、4/12 及其口径）。
- 实现方案与技术栈：`01_作品及成果文件/source/README.md:86-95`、`:12`、`:99`；`rules/taxonomy.v0.3.json:2`；`rules/sdk-signatures.v1.0.json:2-3`。
- 完成状态：`05_补充成果材料/验收摘要.md:23-27`；`deployment-summary.json:53-71`（`ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER`、豁免 `dedicated-scan-host-verification`）；`source/README.md:113`（内部验包 ≠ 已发布/已提交）。
- 反例（不可引用）：`docs/architecture.md` 是 2026-10-02 的 ADR 快照，数据流图里写着 `APK 导入 · 待实现`、`LLM 候选抽取 · 待实现`。写成现状会被评委反打。

## 六、待并入包内的改动（给 B5）

1. 用第三节全文替换 `03_作品介绍文档/作品介绍.md`，插入位置见该节开头说明。
2. 唯一一处对既有正文的改动：`## 组成` 里 `03_作品介绍文档/` 那行由「本文件」改为「本文件及其 PDF 导出（正文一致，Markdown 为源；PDF 另含界面预览图）」。原因是补了 PDF，目录只写「本文件」会与实际内容矛盾。
3. 新增 `03_作品介绍文档/作品介绍.pdf`。制品与排版源在打包会话的工作目录 `.scratch/issue197/proposed/`：`03-作品介绍.pdf`（397,107 B，`17E2221B…`）、`03-作品介绍-print.html`、`03-pdf-scrub.py`、`03-pdf-check.py`。
4. 重冻结时一并重算 `00_材料清单.md` 与 ZIP 哈希。**`828c5224…94ab1` / 41,192,137 B 与「630 文件 / 97 目录」口径自本批改动起失效**。
5. `.scratch/audit-materials/` 与 `audit-rules/rules-20261023.md:91` 引用的是基线 `deccced`，不是 `deccced-anon`，不能当 anon 的新校验清单。

### Check 2 必须重开

`#197` 原结论「全包 0 PDF、0 Office 文件，元数据对象不存在，Check 2 不适用」不再成立，而且**已经被 B3 先重开**：`07_AI工具使用补充说明/AI工具使用说明.docx` 于 02:12:37 进入包内，是第一个 Office 元数据对象。本票 PDF 是第二个。落地后两个都要复扫。

本次 PDF 的清理结果（`03-pdf-check.py` 实测）：`/Title` = `PrivacyTrace 作品介绍`；`/Author`、`/Subject`、`/Keywords`、`/Creator`、`/Producer`、`/Trapped` 全部移除；无 `/Metadata` XMP 流；原始字节扫描 `Skia`、`HeadlessChrome`、`Edg/`、`msedge`、`python-docx`、`LibreOffice`、`Oasis`、`C:\Users` 为 0 命中。

### 复现命令

在本仓库根目录执行，无需联网、无需装依赖：

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --headless=new --disable-gpu --no-pdf-header-footer `
  --virtual-time-budget=4000 --print-to-pdf="raw.pdf" `
  ([uri]::new("$PWD\.scratch\issue197\proposed\03-作品介绍-print.html").AbsoluteUri)
python .scratch\issue197\proposed\03-pdf-scrub.py raw.pdf .scratch\issue197\proposed\03-作品介绍.pdf
python .scratch\issue197\proposed\03-pdf-check.py .scratch\issue197\proposed\03-作品介绍.pdf
```

输入不变时输出逐字节一致（已复算验证）。踩过的坑：Edge 默认写 `/Creator=…HeadlessChrome…`、`/Producer=Skia/PDF m154`，`/Title` 不设就是 HTML 文件名；用 `PdfWriter(clone_from=…)` 删 `/Metadata` 后原始字节仍残留工具链字符串，必须用全新 `PdfWriter()` 重建页面。

## 七、刻意不写的表述

| 不写 | 原因 |
| --- | --- |
| 「核心算法 100% 自研」「完全无 AI 参与」「AI 代码比例」 | 本票范围外明令禁止；`07` 会披露 AI 参与，写了自相矛盾 |
| 「零豁免全绿」「所有检查全部通过」 | R04 有 1 项既有豁免 `dedicated-scan-host-verification`（`WAIVED_BY_USER`） |
| 「收据齐全」「完整内部验收收据随包」 | `deployment-summary.json` 引用的 6 个 `acceptance-r*.json` 不在包内；`验收摘要.md:3` 自称评审版不随包提供内部收据 |
| 「已公开发布」「已提交竞赛平台」 | `source/README.md:113` 明确划界 |
| 「统一状态机」「状态枚举共 N 个」 | 状态按字段分域声明，没有单一枚举；合并即失实 |
| 「准确率 12/12」 | 12/12 是对照状态一致数；改说准确率是另一个主张 |
| 引用 `docs/architecture.md` 的数据流图 | 旧 ADR 快照，图里有「待实现」 |
| 「Windows 直接可跑」 | `04` 要求 Linux/WSL2 + Docker |

## 八、验证记录

| 项 | 结果 |
| --- | --- |
| 系统字段字数 | 278 含标点 / 223 汉字 / 8 句（≤300 预算） |
| PDF 规格 | 2 页，209.9 × 297.0 mm（A4），397,107 B |
| PDF 字体 | 全部嵌入，渲染器 `missingFonts` 为空，文本可检索 |
| PDF 元数据 | 仅 `/Title`；无 `/Metadata`；工具链字符串 0 命中 |
| 视觉审查 | 第 1、2 页渲染图逐页看过：无溢出、无缺字、图注不与正文挤压 |
| 关键 token 复扫 | `12/12`、`2/12`、`4/12`、`1578 passed`、`179 skipped`、`dedicated-scan-host-verification`、`taxonomy 0.3.0`、`OFFLINE_REPLAY` 均在；`100%`、`准确率提升`、`零豁免`、`收据齐全`、`统一状态机`、`——`、`而不是` 均 0 命中 |
| 匿名化 | 正文无校名、姓名、学号、邮箱、账号；全文人工复读一遍 |
| 与 `#74` §4 第 09 项比对 | 背景、定位、创新、实现方案、完成状态、原创贡献六项齐全 |

未做的检查：未对成品包整体复算哈希（包正被并发重建，数值立即过期）；未运行 `bash scripts/check.sh` 以外的专项验收入口（本票无源码改动）。

### 本地闸门与 CI

- `bash scripts/preflight.sh`（base `912b523`）：`All checks passed!`
- `bash scripts/check.sh`：`PrivacyTrace checks passed.`
  - `pytest apps/api/tests`：1619 passed, 200 skipped（10:14）
  - `pytest tests/e2e`：61 passed, 4 skipped（15.08s）
  - `ruff check` 两段：All checks passed；`verify-user-study-pack.py`、`export-schema.py` 与契约 diff：无差异
  - `@privacytrace/web`：137 pass / 0 fail；`npm run build` 成功
- 中央 CI（PR #245，head `3327fae`）：`themasterplan-check`、`acceptance`、`actual-linux-deployment`（9m43s）、`linux-images-and-smoke`、六场景、十二场景全部 pass，`challenger` 按配置 skipping。无重跑，期间未改代码。

## 九、已知风险

1. **包在并发变动**。2026-10-23 02:02–02:13 之间 `07` 的 md 与 docx、`00_材料清单.md`、`source/README.md`、`App.vue`、`contracts.generated.ts`、`05/验收摘要.md` 都被其他票改过，还出现了 `deccced-anon-b4/` 工作副本；ZIP 已重命名为 `PrivacyTrace_322234.zip.stale-before-PT-906-B3`。本页任何哈希都不是当前值。
2. **`03`「能做什么」第 4 条**写「以事实 / 声明 / 推断 分层展示」，而推断层 `ContextualHint` 目前只预留结构（`models.py:101-104`、`docs/architecture.md:28`）。这是既有口径，本票按范围未改，建议另开票核实后统一。
3. **`07` 与 `03` 的 AI 口径必须对得上**。`03` 只说「AI 用于样板代码与文档排版，详见 07」；`07` 的清单若写成别的范围，两处就打架。B3 完成后建议交叉比对一次。
