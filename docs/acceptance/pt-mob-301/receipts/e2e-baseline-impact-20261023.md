# 基线影响分析：`deccced`/`2626152` → `a1a6386`（2026-10-23）

> 只读分析。本轮**未执行**任何验收 lane、未构建 APK、未运行测试、未改产品代码、未 push。
> 本文只记录 git 事实、既有收据事实，以及明确标注为「推断」的内容；任何未执行项都不写 `PASSED`。
> 工作区：`.agents/worktrees/codex/e2e-acceptance-20261023`（分支 `codex/e2e-acceptance-20261023`）。

## 0. 一句话结论

- `deccced..a1a6386` 共 **34** 个 first-parent 合入：产品代码 7、前端 7、工具/构建 4、纯文档 9、材料 6、撤销 1。
- 旧 H/N/F/R 的 `PASSED` 收据全部绑定更早 SHA（`ffadeb0`、`ba46f2a`、`d12eeb7`、`4208823`、`2626152`、`65b49f7` 等），**没有一份等于 `a1a6386`**；本基线建议 **must-rerun 37 项**（H 12 + N 11 + F 10 + R 04），可直接沿用的旧结论仅 **3 条**（N08 `BLOCKED`、F07-E `BLOCKED`、Web 同任务下钻 `NOT_RUN`）。
- 客户端面：**原生壳源码未变（仅图标资源）**，但 APK 内嵌的 web 资源从 `2626152` 到 `a1a6386` 全量变化（`App.vue` 286 行、`mobile.css` 1202 行、`MobileApp.vue` 171 行、`flow.ts` 80 行）。旧 APK `955d484b…6088` 只能作为「旧客户端 × 新服务端」混合组合的客户端输入，且结论限于**服务端面**，**不能**产出任何本基线客户端面结论。
- `#256` 只回退 6 个材料/文档 PR 与 3 处前端文案/注释/测试断言，不触碰业务逻辑；相对 `deccced` 的 `apps/` 净变更中**不含** `#256` 引入的行。

## 1. 基线事实

### 1.1 身份与实测命令

| 项 | 值 | 来源 |
| --- | --- | --- |
| 本轮基线 | `a1a6386ab4a18739445b8ffc1025c94e1af5b5d7`（Merge PR #256） | `git rev-parse HEAD` |
| 基线 tree | `90910c0b57a32165b221e4c15b16e2894dc93daa` | `git cat-file -p a1a6386` |
| 基线 parents | `b1092f8`（#215）+ `f57c92e`（revert 分支） | 同上 |
| 上一轮收口组合 | `deccced59d6dec7f442be4ce06b257403794bc46`，tree `79f648212ee992554109dbf41854ba359dedd9f4` | `git cat-file -p deccced` |
| 上一轮证据组合 | `262615242161e0371ec151a5f07ef19d360a35e3`，tree `1a662a23eb9eea57135391f3f2d63ca73456fc16` | `git cat-file -p 2626152` |
| 旧 APK 源 head | `2626152`（与 `017f031` 同产品树） | `docs/acceptance/issue136/h-mainline-final-20261022.md` |
| 旧 APK | `client-local-ca-2626152.apk`，157,543,412 B，sha256 `955d484ba0a01bcf0472e7d97b24fe0d84698af8c61b0efe38b762ca7d3e6088` | 收据 + 本轮对主检出 `.scratch/apk/` 重新 `Get-FileHash` 复核一致 |

> **更正协调入口文档的一处笔误**：`docs/acceptance/e2e-latest-baseline-20261023.md` 第 9 行把 tree 写成 `b1092f8e…`，该值是 `a1a6386` 的**第一父提交**（#215 合入），不是 tree。实测 tree 为 `90910c0b…`。建议收口前修正，避免下游回执引用错 tree。

规模摘要（`git diff --stat`）：

```text
$ git diff --stat deccced a1a6386 | tail -1
162 files changed, 11306 insertions(+), 856 deletions(-)
$ git diff --stat deccced a1a6386 -- apps/ | tail -1
50 files changed, 3140 insertions(+), 662 deletions(-)
$ git diff --stat 2626152 a1a6386 -- apps/mobile apps/web/src/mobile apps/web/src/App.vue | tail -1
7 files changed, 1282 insertions(+), 461 deletions(-)
```

### 1.2 `git log --first-parent deccced..a1a6386` 合入清单（34 条）

按「PR 号（无 PR 的直接提交单独标注）→ 类别 → 一句话影响」归类。类别只取主类别，跨类在影响里注明。

| # | 提交 | PR / 来源 | 类别 | 一句话影响 |
| ---: | --- | --- | --- | --- |
| 1 | `e5b4860` | #180 | 工具/验收 | 验收执行器去硬编码路径，新增 `agent-env-probe.sh`、`preflight.sh` 与路径测试；影响 F/N 重放与 R01 预检 |
| 2 | `d531452` | #178 | 前端 | UX 文案改写：`copy.ts`、`App.vue`、`MobileApp.vue`、`ImportPage.vue` 等 8 个 web 文件 + 3 个 verify 脚本 |
| 3 | `d40b0bc` | #176 | 前端 | 界面细节：`App.vue` 与 `foundation/style/theme/workbench` 四个 CSS 微调 |
| 4 | `313b8c9` | #206 | 文档 | 新增 ADR-0004「客户端是 Android App」 |
| 5 | `c28c792` | #210 | 文档 | `GLOSSARY.md` 补定义 |
| 6 | `4b103ec` | #211 | 文档 | `README.md` 更新 |
| 7 | `1c9a1ba` | #212 | 文档 | ADR-0001 注记 |
| 8 | `4156aa4` | #213 | 文档 | ADR-0004 状态更新 |
| 9 | `6ec43a3` | #188 | 产品代码（API） | 包集与 ZIP 内**重复 APK 文件名**一律拒绝（`CORRUPTED_FILE`） |
| 10 | `cbac3b7` | #185 | 产品代码（可观测性） | Celery 日志格式保留固定诊断码（`LEASE_LOST` 等可读） |
| 11 | `1fd1350` | #216 | 文档 | 新增提交前 E2E 方案 `docs/pre-submission-e2e-plan-20261021.md` |
| 12 | `e52cc71` | #217 | 工具/构建 | 本地端口参数化、PowerShell 包装、脚本错误处理；含 `apps/mobile/package.json` 的 `android:prepare` 改走 `run-powershell.cjs` |
| 13 | `c9aba84` | 直接提交（无 PR） | 前端 | 移动视觉层整体替换：81 文件，新增 mobile token/规范/证据，重写移动外壳与主题 CSS |
| 14 | `f23d3b1` | #229 | 文档/材料 | 新增赛事官方模板（docx/pdf）与清单，更新 AI 使用声明 |
| 15 | `912b523` | #227 | 工具 | 受控端口参数化：`local-ports.cjs`、`validate-spec30.py`、`verify-browser.cjs` |
| 16 | `3e6741d` | 直接提交（无 PR） | 前端 | 移动步骤条与排版收紧（`MobileApp.vue`、`mobile.css`） |
| 17 | `b258315` | #231 | 文档 | ADR-0004 指针改名为 ADR-0005 并同步文档 |
| 18 | `93348e1` | #235 | 文档/规则 | `AGENTS.md` 的 ADR 指针修正 |
| 19 | `5644be5` | #232 | 产品代码（API） | 候选只给 `start_offset` 时用摘要补 `end_offset`，不再拒绝合法单端区间 |
| 20 | `60764fe` | #242 | 文档 | 前端交付文档指针修正 |
| 21 | `cbb160a` | #244 | 产品代码（API） | 终态遥测失败（含 `StopIteration`）不再跳过连接/锁释放，改为固定诊断码 |
| 22 | `a01c3a5` | #250 | 产品+工具 | WSL 发行版改由 `PRIVACYTRACE_WSL_DISTRO` 配置；`wsl.py`、`isolated_scan.py`、`benchmark.py`、`check.sh`、`controlled_paths.py` |
| 23 | `5d6a14b` | #252 | 产品代码（API）+契约 | 收集结果/候选 ID/空 `condition` 契约边界；`WEB_CANDIDATE_ID_MAX=87`、`source` 可选、生成契约更新 |
| 24 | `61287b7` | #254 | 前端（移动） | 移动流：来源重试、开始前置条件、轮询恢复、模型结果令牌（#239/#243/#248/#249） |
| 25 | `2308360` | #251 | 产品代码（API） | LLM 响应体读取遵守整次抽取总 deadline，返回真实超时 |
| 26 | `767f955` | 直接提交（无 PR） | 前端（文案） | 删除免责声明与系统化措辞（`EvidencePanel`、`copy.ts`、`MobileApp`、`CandidatePage`） |
| 27 | `2dc955e` | #228 | 材料/文档 | PT-906-B2 运行环境材料；**被 #256 撤销** |
| 28 | `bfed3ca` | #234 | 材料 | 比赛汇报 deck（html/pdf/pptx + 图）；**被 #256 撤销** |
| 29 | `023ddf3` | #236 | 材料 | 第三方披露修订 + 依赖提取脚本；**被 #256 撤销** |
| 30 | `3e626a5` | #237 | 前端+材料 | AI 使用声明文案/生成注释/测试 + submission 文档；**被 #256 撤销** |
| 31 | `ad87e8f` | #245 | 材料/文档 | PT-906-B1 创作来源材料；**被 #256 撤销** |
| 32 | `06fee55` | #255 | 材料 | 90 秒作品展示（视频/节拍/截图/QA）；**被 #256 撤销** |
| 33 | `b1092f8` | #215 | 工具/构建 | `android:prepare` 在无 `pwsh` 时回退 Windows PowerShell 5.1；新增 Android prepare CI |
| 34 | `a1a6386` | #256 | 撤销 | 回退 #228/#234/#236/#237/#245/#255 六个合入（材料/文档 + 3 处前端文案/注释/断言） |

分类计数：产品代码 7（#188、#185、#232、#244、#250、#252、#251，#250 兼工具），前端 7（#178、#176、`c9aba84`、`3e6741d`、#254、`767f955`、#237），工具/构建 4（#180、#217、#227、#215），纯文档 9（#206、#210、#211、#212、#213、#216、#231、#235、#242），材料 6（#228、#234、#236、#245、#255、#229 的赛事源文件），撤销 1（#256）。共 34。

### 1.3 #256 revert 专项核实

**实际回退的是 6 个合入，不是 4 个。** `git log --oneline b1092f8..f57c92e` 显示 revert 分支逐条撤销：

```text
f57c92e Revert "Merge pull request #228 ..."
afd7469 Revert "Merge pull request #234 ..."
a6b2639 Revert "Merge pull request #236 ..."
c0c0c2f Revert "Merge pull request #237 ..."
50db554 Revert "Merge pull request #245 ..."
ac40ce3 Revert "Merge pull request #255 ..."
```

`git show --stat a1a6386`（对第一父 diff）摘要：

```text
35 files changed, 8 insertions(+), 2784 deletions(-)
```

文件分组：

| 分组 | 文件 | 性质 |
| --- | --- | --- |
| `apps/` 产品代码 | `apps/web/src/App.vue`（1/1 行）、`apps/web/src/contracts.generated.ts`（1/1 行）、`apps/web/tests/challenger_stress.test.ts`（1/4 行） | 仅 footer 文案、生成文件注释、测试断言；**无 API、无移动壳、无业务流程逻辑** |
| 工具 | `scripts/export-schema.py`（1/1 行） | 仅生成注释模板 |
| 文档 | `GLOSSARY.md`、`README.md`、`docs/ai-usage-disclosure.md` | 回到 2026-10-23 之前 |
| 材料（删除） | `docs/acceptance/issue223/*`、`docs/presentation/20261023/*`（html/pdf/pptx/图/说明）、`docs/stages/pt906-b1-creative-origin-20261023.md`、`docs/stages/pt906-b2-runtime-env-20261023.md`、`docs/submission/07-ai-usage-disclosure.md`、`showcase/privacytrace-90s/*`（视频/音频/截图/QA/脚本） | 比赛 deck、90 秒视频、第三方/AI/创作来源/运行环境材料全部撤出 |

**是否触及 `apps/` 产品代码：是，但只触及文案/注释/测试。** 证据：

```text
$ git diff --numstat a1a6386^1 a1a6386 -- apps/
1  1  apps/web/src/App.vue
1  1  apps/web/src/contracts.generated.ts
1  4  apps/web/tests/challenger_stress.test.ts
```

**相对 `deccced` 的净效果：对这三处 apps/ 行而言为零。** `#237` 是本区间内唯一改动这三处文案/注释/断言的合入，`#256` 把它们原样退回 `767f955` 状态；因此 `git diff deccced a1a6386 -- apps/` 中不含任何 `07_AI工具使用补充说明` / `仓库披露记录` 相关行。`App.vue` 相对 `deccced` 的 14 行差异全部来自 #176/#178/#254/`767f955` 等其它合入；`contracts.generated.ts` 相对 `deccced` 的 2 行差异来自 #252（`source?:` 可选），不是 #256。

对验收的含义：**#256 不改变 H/N/F/R 的业务行为**；它改变的是（a）客户端文案的一小段（旧 APK 本来也不等于本基线），（b）**对外交付材料完整性**——deck、90 秒视频、AI 使用声明、第三方披露、运行环境与创作来源材料在 `a1a6386` 上已不存在。后者不是 H/N/F/R 判据，但会让「提交材料」lane 出现实质缺口，需要在收口中单列。

## 2. 变更 → 验收场景映射

### 2.1 产品/前端/工具变更影响表

判定口径：**旧证据**指上一轮收口时被接受的那份本机执行证据；判定只回答「能否作为 `a1a6386` 的直接证据」，不评价旧执行本身。

| 变更 | 变更面（关键文件） | 直接影响验收项 | 判定 | 理由 |
| --- | --- | --- | --- | --- |
| #188 `6ec43a3` | `package_set.py`、`web_intake.py`；新增包集/ZIP 重名拒绝与 3 组测试 | **N03**（重名变体）、H04/H05/H06/H10/H11/H12（splits 校验路径）、R02 | **需重跑** | N03 的「重名」分支是新增拒绝逻辑；splits 类 H 走同一校验函数 |
| #185 `cbac3b7` | `runtime_worker.py` Celery 日志格式 + 日志测试 | F03（日志诊断探针）、F 组可观测性 | **需重跑（定向）** | 行为面不变，但 F03-D 旧结论「诊断码不可读」已被代码改变，旧探针结论失效 |
| #180 `e5b4860` | `deploy/acceptance/issue133/{controller,resign-web-cert}.sh`、`deploy/tests`、环境脚本 | F05/F06/N12 重放 harness、R01 预检 | **需重跑** | 执行器默认路径与必需参数改变，旧命令可直接失败 |
| #217 `e52cc71` | `scripts/lib/{local-ports,powershell}.cjs`、`run-powershell.cjs`、11 个 verify/检查脚本、`apps/mobile/package.json` | R01/R03、H/N 的 APK 构建入口 | **需重跑** | 端口分配与 Windows 构建链改变；验收脚本行为变更 |
| #178 `d531452` | `copy.ts`、`App.vue`、`MobileApp.vue`、`ImportPage.vue`、`ReportExample.vue`、3 个 verify 脚本 | R03（文案合同）、H/N 客户端面、报告文案 | **需重跑** | 文案是客户端与桌面 Web 的共同输出；旧 APK 不含 |
| #176 `d40b0bc` | `App.vue`、`foundation.css`、`style.css`、`theme.css`、`workbench.css` | R03（视觉/层级）、客户端共享样式 | **需重跑** | 桌面与共享 token 变化；`theme.css` 进入 APK 包 |
| `c9aba84` | 移动外壳/主题/规范（`MobileApp.vue`、`mobile.css`、`App.vue`、`theme.css`、`hierarchy.css` 等 81 文件） | R03、H/N 客户端面全部 UI 结论 | **需重跑** | 移动视觉层整体替换，且新增设计规范与品牌资产 |
| `3e6741d` | `MobileApp.vue`、`mobile.css` | H/N 客户端面、R03 移动断言 | **需重跑** | 步骤条与排版直接影响截图/视口/触控断言 |
| `767f955` | `EvidencePanel.vue`、`copy.ts`、`MobileApp.vue`、`CandidatePage.vue` + 3 个 verify 脚本 | R03（文案）、H/N 报告与证据面板文案 | **需重跑** | 免责声明/系统措辞被删，旧截图与文案断言不对应 |
| #254 `61287b7` | `mobile/flow.ts`、`MobileApp.vue`、`PolicyAssist.vue`、`mobile-polling.test.cjs`、`verify-mobile-flow.cjs` | **N12、F05/F06、H01–H12、N01–N04**（手机侧）；R03 mobile | **需重跑** | 新增来源重试、开始前置条件、轮询恢复、模型结果令牌；旧 APK 完全不含这些修复 |
| #252 `5d6a14b` | `web_intake.py`、`web_models.py`、`contracts.generated.ts`、两份 JSON schema、`policyAssist.ts` | **H02/H05/H08/H11**（网页辅助）、所有候选/报告 claim、**N10**、R03 policy-assist | **需重跑** | 候选 ID 上限、空 `condition` 规范化、外部收集 `source` 可选，直接改变契约边界 |
| #232 `5644be5` | `policy_intake.py`（`_candidate_span`）、新增候选区间测试 | **H01–H12** 的候选保存与引用区间、N10 | **需重跑** | 单端 offset 的接受/拒绝规则改变，旧断言可能过严或过松 |
| #251 `2308360` | `policy_llm_extractor.py`（deadline socket/分块读）、564 行 deadline 测试 | **H01/H02/H04/H05/H07/H08/H10/H11**（服务端抽取）、H03/H06/H09/H12（导入文本再抽取）、N09/N10 | **需重跑** | 总预算与超时语义改变；慢响应/截断的边界结论需重建 |
| #244 `cbb160a` | `runtime_worker.py`（`_finish_runtime`）、`durable_intake.py`、`web_intake.py` | **F05/F06/N12**（删除/取消后终态）、**F01–F04/F07**（每次 worker 执行） | **需重跑** | 终态事件失败后的资源释放路径被重写；删除后迟到终态是 F06 的核心断言 |
| #250 `a01c3a5` | `wsl.py`、`isolated_scan.py`、`benchmark.py`、`check.sh`、`controlled_paths.py` | **R01/R02/R04**、F 组全部容器/扫描路径 | **需重跑** | WSL 发行版选择影响 Docker 前缀与路径换算；旧命令可能指向错误发行版 |
| #227 `912b523` | `local-ports.cjs`、`validate-spec30.py`、`verify-browser.cjs` | **R02/R03** | **需重跑** | 受控端口不再硬编码；旧执行命令/端口假设失效 |
| #215 `b1092f8` | `apps/mobile/README.md`、`scripts/run-powershell.cjs`、`check.sh`、`.github/workflows/android-prepare.yml` | **H/N 的 APK 构建链**、R01 | **需重跑** | 仅构建工具，但决定本基线能否重建 APK；不改变已构建运行时 |
| #171（`deccced` 内已有） | `App.vue`、`MobileApp.vue`、`copy.ts`、`theme.css`、品牌资产等 49 文件 | H/N 客户端面、R03 | **已失效** | 上一轮已记录「#171 之后客户端面未复验」；本分析确认旧 APK 更旧，不能用 |
| #256 `a1a6386` | 6 个材料 PR + 3 处前端文案/注释/测试 | H/N（文案）、R03（文案合同）、交付材料 | **不影响行为面；材料缺口** | 相对 `deccced` 净变更为零；但删除 deck/视频/披露/阶段材料 |

### 2.2 旧收据逐项判定

判定只有三种：**需重跑**（本基线必须重新执行才能写状态）、**仍适用**（可带 SHA 与范围引用）、**已失效**（旧结论不能延续，必须重跑）。`BLOCKED`/`NOT_RUN` 的沿用项单独注明「不计通过」。

| 验收项 | 旧收据与组合 | 旧状态 | 本基线判定 | 说明 |
| --- | --- | --- | --- | --- |
| H01–H11 | `h-matrix-final-20261022.md`：`2626152` 树 + APK `955d484b` | `PASSED` | **需重跑** | 服务端 10 个 API 源文件变更；客户端 bundle 全量变化；旧 APK 不含 #254 |
| H12 | 同上（J/splits/模型，复现 2 次） | `FAILED` | **需重跑 / 旧结论已失效** | 失败原因未定位；#232/#251/#252/#254 均触及候选、抽取与移动流，既不能假设仍失败，也不能假设已修复 |
| N01–N04 | `issue129/README.md`：`ffadeb0` | `PASSED` | **需重跑** | #188 新增重名拒绝；客户端选包/确认链路变化 |
| N05–N07 | `issue132/README.md` + `review-20261022.md`：`ba46f2a` + dirty | `PASSED`（仅原组合） | **需重跑** | 收据自述「旧 N05–N07 仅保留原组合历史 PASSED，不提升为新集成版本」 |
| N08 | `issue132/review-20261022.md`：`ba46f2a` 现场 | `BLOCKED` | **仍适用（BLOCKED，不计通过）** | 14 个真实目标拒绝未执行；缺可直达真实私网的客户端网络，属环境边界，不因代码前进失效 |
| N09–N10 | `issue130/execution-20261021.md`：`ffadeb0` | `PASSED` | **需重跑** | #251 总 deadline、#232/#252 候选与引用契约 |
| N11 | `issue131/execution-20261021.md`：`ffadeb0` | `PASSED` | **需重跑** | #254 改模型结果令牌/重试；客户端与镜像均不同 |
| N12 | `issue133/execution-20261022.md`：`2626152` final | `PASSED` | **需重跑** | #244 直接改删除/取消后的终态清理 |
| F01–F04 | `issue134/execution-20261022.md`：`4208823` | `PASSED` | **需重跑** | #244 改 worker 终态清理与 durable event；镜像需按新树重建 |
| F05–F06 | `issue133/execution-20261022.md`：`2626152` final | `PASSED` | **需重跑** | 同 #244；F06 的「删除后迟到结果」正是被改路径 |
| F07 A–D | `issue134/execution-20261022.md`：`4208823` | `PASSED` | **需重跑** | #244/#250 影响 worker/runner；镜像与 WSL 发行版选择变化 |
| F07-E | 同上 | `BLOCKED` | **仍适用（BLOCKED）** | 无独立内核 VM，属环境边界；与基线代码无关 |
| F08–F10 | `issue135/README.md`：`d12eeb7` | `PASSED` | **需重跑** | 旧 SHA 早于 `deccced`；部署镜像/迁移/扫描路径均变化 |
| R01 | `issue136/execution-20261022.md`：`65b49f7` | `PASSED` | **需重跑** | `check.sh` 被 #217/#215/#250 修改；旧收据早于 #171/#174 |
| R02 | 同上 | `PASSED` | **需重跑** | `validate-spec30.py`、`isolated_scan.py`、`benchmark.py` 变更 |
| R03 | 同上（browser 回执锚定 `65b49f7`） | `PASSED` | **需重跑** | 14 个 `verify-*.cjs` + `verify_workflow.py` 变更，前端产品代码也变 |
| R04 | 同上 + `final-package-20261022.md` | `PASSED`（含 1 项既有豁免） | **需重跑** | 收据早于 #174 的 R4 注入前等待改动；产品/镜像均变 |

按上一轮收据文件的复用判定：

| 收据文件 | 绑定组合 | 可复用内容 | 判定 |
| --- | --- | --- | --- |
| `docs/acceptance/h-matrix-final-20261022.md` | `2626152` + APK `955d484b` | 方法、夹具身份、H12 失败现象 | **已失效**（旧客户端/服务端均非本基线）；H01–H12 全重跑 |
| `docs/acceptance/issue133/execution-20261022.md` | `2626152` final（服务端 4208823） | N12/F05/F06 的执行方法与环境配方 | **需重跑**（#244）；结果不得沿用 |
| `docs/acceptance/issue134/execution-20261022.md` | `4208823` | F01–F04/F07 的注入方法 | **需重跑**；仅 F07-E `BLOCKED` 可沿用 |
| `docs/acceptance/issue136/h-mainline-final-20261022.md` | `2626152` | 单包/splits 主线、停启恢复、Web 缺口探测 | 客户端面 **需重跑**；Web 缺口结论结构性沿用 |
| `docs/acceptance/issue136/execution-20261022.md` | `65b49f7` | R01–R04 的入口与耗时基线 | **已失效**（脚本与产品均变）；仅豁免事实可引 |
| `docs/acceptance/frontend-round2/20261022.md` | `376d658` 实现 / `65b49f7` 验收 | 浏览器模拟证据分层方法 | **已失效**（前端产品代码与 verify 脚本均变） |

### 2.3 统计与上一轮 7 项缺口的处置

| 项 | 数量 | 明细 |
| --- | ---: | --- |
| 本基线 must-rerun | **37** | H 12 + N 11（N01–N07、N09–N12）+ F 10 + R 4 |
| 可带 SHA 沿用的旧结论 | **3** | N08 `BLOCKED`、F07-E `BLOCKED`、Web 同任务下钻 `NOT_RUN`（均不计 `PASSED`） |
| 可折算为 `a1a6386` `PASSED` 的旧 `PASSED` | **0** | 所有旧 `PASSED` 收据 SHA 均不等于基线 |

上一轮接受的 7 项缺口在本基线的处置：

| 旧缺口 | 本基线判定 | 依据 |
| --- | --- | --- |
| H12 `FAILED` | 仍需在 H 重跑中重新判定；旧 FAILED 不得直接沿用为新基线结论 | 失败原因未定位；相关代码已变 |
| #171 后客户端面未复验 | **扩大为严重缺口**：`deccced→a1a6386` 又叠加 7 组前端变更；旧 APK 仍不能代表；无新 APK 则 H/N 客户端面 `BLOCKED` | 见 §3 |
| F07-E `BLOCKED` | 沿用 `BLOCKED` | 无独立内核可销毁 VM |
| F01 Android `NOT_RUN` | 沿用为缺口；需新 APK 才能补 | 恢复入口依赖客户端交互 |
| Web 同任务下钻 `NOT_RUN` | 沿用；结构性限制未变 | capability 只存 Android Keystore，remote mode 拒绝 `X-PrivacyTrace-Local`；`middleware.py`/`main.py` 在本区间无 diff |
| D08/N08 豁免 | N08 收据原文为 `BLOCKED`（不是 `PASSED`）；**`D08` 在仓库中查无此验收标识 → `UNKNOWN`** | `git grep 'D08'` 只命中 PT-D08 backlog/epic 文本与二进制噪声，无验收项定义；部署侧唯一豁免是 `dedicated-scan-host-verification`（`WAIVED_BY_USER`） |
| 覆盖边界 | 不变 | `x86_64` / API35 / MuMu / 受控政策源 / 受控模型 / 无公网 / 无真机 |

## 3. 客户端面结论

### 3.1 实测差异

```text
$ git diff --stat 2626152 a1a6386 -- apps/mobile apps/web/src/mobile apps/web/src/App.vue
 apps/mobile/README.md                |    2 +
 apps/mobile/package.json             |    2 +-
 apps/mobile/src-tauri/icons/icon.png |  Bin 1916 -> 9051 bytes
 apps/web/src/App.vue                 |  286 ++++----
 apps/web/src/mobile/MobileApp.vue    |  171 +++--
 apps/web/src/mobile/flow.ts          |   80 ++-
 apps/web/src/mobile/mobile.css       | 1202 ++++++++++++++++++++++++--------
 7 files changed, 1282 insertions(+), 461 deletions(-)

$ git diff --stat 2626152 a1a6386 -- apps/mobile/src-tauri
 apps/mobile/src-tauri/icons/icon.png |  Bin 1916 -> 9051 bytes
 1 file changed, 0 insertions(+), 0 deletions(-)
```

- **原生壳未变**：`apps/mobile/src-tauri/src/lib.rs`、`main.rs`、`capabilities/mobile.json`、`tauri.conf.json`、`Cargo.toml/lock` 在 `2626152..a1a6386` 之间无差异；`tauri.conf.json` 仍是 `version 0.1.0`、`identifier org.privacytrace.mobile`、`frontendDist ../../web/dist`。变化只有图标资源（`icon.png`）。
- **web 资源全量变化**：APK 构建的 `beforeBuildCommand` 是根目录 `npm run build`，即把 `apps/web/dist` 打进 APK。`2626152..a1a6386` 之间 `apps/web/src` 共 23 个文件变更（`App.vue` 286 行、`mobile.css` 1202 行、`MobileApp.vue` 171 行、`flow.ts` 80 行、`theme.css` 191 行，另含 `copy.ts`、`main.ts`、`PolicyAssist.vue` 等），另有 `apps/web/index.html`（theme-color/图标引用）与 `apps/web/public/brand/*`（#171 引入）变化。
- **构建脚本变化**：`apps/mobile/package.json` 的 `android:prepare` 改走 `scripts/run-powershell.cjs`（#217/#215），并保留品牌图标步骤；这是构建期脚本，不改变已构建 APK 的运行时。

### 3.2 旧 APK `955d484b` 的可用边界

旧 APK 是 `2626152` 树的产物（与 `017f031` 构建字节相同），其内嵌 web 包为旧 `index-BxZBQKot.js`。本轮在主检出 `.scratch/apk/` 复核：

```text
955d484b…6088  client-local-ca-017f031.apk  157543412 bytes
955d484b…6088  client-local-ca-2626152.apk  157543412 bytes
0be49358…8c17  client-local-ca-4208823.apk  157543412 bytes
```

| 用法 | 允许 | 说明 |
| --- | --- | --- |
| 「`2626152` 旧客户端 × `a1a6386` 新服务端」混合组合的服务端面冒烟 | **可作为输入（若实际跑通）；必须标注混合** | 可验证上传/队列/扫描/报告接口对新旧客户端的兼容；结论只能写服务端行为 |
| 作为原生壳静态事实的参照（包名、`versionCode 1000`、`x86_64`、debug 证书 `4172668f…`、仅 `localhost` 追加测试 CA） | **允许（限定为 `2626152` 产物事实）** | 壳源码未变，但 APK 仍是旧产物，不能外推新构建 |
| 本基线 H01–H12 / N01–N12 的客户端面 `PASSED` | **不允许** | web 包全量变化；旧 APK 不含 #254 的 #239/#243/#248/#249 修复 |
| 移动 UI/文案/布局/步骤条/轮询/恢复/重试/候选/证据面板结论 | **不允许** | `MobileApp.vue`、`flow.ts`、`mobile.css`、`copy.ts` 均不在旧 APK |
| 证明本基线 APK 可安装/启动/停启恢复 | **不允许** | 不是同一产物；本轮未重建 |

**结论：旧 APK 只能作为「旧客户端」参与混合组合，不能产出任何 `a1a6386` 客户端面结论。**

### 3.3 本基线 APK 重建能力（事实 + 推断）

本轮只做轻量存在性检查，**未执行构建**：

| 检查 | 结果 |
| --- | --- |
| `java` / `javac` / `gradle` / `adb` 在 PATH | 均未解析到 |
| `cargo` | 用户目录 `.cargo/bin/cargo.exe` 可解析，`cargo 1.99.1`；已装 target 为 `x86_64-linux-android`、`x86_64-pc-windows-msvc` |
| Android SDK | 目录存在，但 `platforms/`、`build-tools/`、`ndk/`、`platform-tools/`、`cmdline-tools/` 均不存在 |
| JDK | 常见安装路径未发现 |
| `adb` | 仅在 MuMu 自带目录存在（不在 PATH） |

> **与协调入口文档的差异**：该文档写「无 Rust/cargo」；实测 cargo 存在。写「无 Android SDK」；实测 SDK 目录存在但为空壳。两者都不足以构建，但原因不同。
>
> **推断（标注）**：按当前状态，在 18:00 冻结前完成 JDK/SDK/NDK 安装并成功重建 x86_64 debug APK 的可能性 **UNKNOWN**；本轮未尝试，不能写「可重建」或「已失败」。若 toolchain 不补齐，H/N 客户端面应记 `BLOCKED`，而不是用旧 APK 冒充。

## 4. 本轮验收建议矩阵

### 4.1 Lane 级建议

| Lane | 必须在本基线执行 | 入口/覆盖 | 可引用的旧证据 | 预计状态 |
| --- | --- | --- | --- | --- |
| **R01** | **是** | `PRIVACYTRACE_DOCKER_TESTS=1 bash scripts/check.sh`（权威入口，含 Docker 分支） | 无（`65b49f7` 的 R01 早于本区间且 `check.sh` 已变） | `PASSED`/`FAILED` 由实跑决定 |
| **R02** | **是** | `scripts/validate-spec30.py --suite spec30` 与 `--suite pt907` | 无 | 同上 |
| **R03** | **是** | `acceptance:browser/frontend/live/mobile/hierarchy/reading/motion/design/preview` + `verify:brand` | 无（前端产品代码与 verify 脚本均变） | 同上 |
| **R04** | **是** | 干净 clone：`bash deploy/check_acceptance.sh`（WSL root） | 仅「既有 `dedicated-scan-host-verification` 豁免」这一事实，不引用其通过结论 | 同上 |
| **F** | **是** | F01–F07（`deploy/acceptance/issue134/...`）+ F08–F10（`issue135` 部署演练） | 仅 F07-E `BLOCKED` | F07-E 预计 `BLOCKED`；F08–F10 取决于部署环境 |
| **H** | **是（若 APK 可重建）** | H01–H12 真实 APK + 两实例 + 受控政策/模型 | 仅「H12 历史上 `FAILED`」作为背景，不作为结论 | 无新 APK → **`BLOCKED`**；有则需全部重跑 |
| **N** | **是（N08 除外）** | N01–N07、N09–N12；N08 维持 `BLOCKED`（可选复探） | 仅 N08 `BLOCKED` | 无新 APK → 手机侧 `BLOCKED` |
| **Web 同任务下钻** | 否（结构性） | 旧探测已证明 remote mode 拒绝 local header、capability 只在 Keystore | 可带 `2626152` SHA 引用 `NOT_RUN` 结论 | `NOT_RUN` |
| **交付材料** | 是（收口检查） | deck/视频/AI 披露/第三方披露/阶段材料 | 无（#256 已删除） | 缺口，需用户决定是否恢复 |

### 4.2 建议执行顺序（按 2026-10-23 截止）

**共同前提**：所有 lane 的服务端镜像必须按 `a1a6386` 重新构建，并在回执中记录 image ID/digest；不得复用 `4208823`/`2626152` 的镜像充当本基线证据（旧 H/F 收据的镜像 rev 均早于本基线）。

1. **R01 先跑**：它是源码级权威门禁；若 R01 失败，后续 lane 的结论没有意义。
2. **R03 并行**：纯前端/浏览器，不依赖 Docker 长任务；但会写 `evidence/` 已跟踪文件，需按旧收据的做法设 `PRIVACYTRACE_EVIDENCE_DIR` 指向仓库外。
3. **R02 并行（WSL）**：脚本重复构建，耗时最长；与 R01 的 Docker 分支可能争资源，建议错峰。
4. **R04 + F**：部署与故障注入需独占 WSL/Docker 与端口；F05/F06/F07 会创建/删除容器，必须在 R04 之后或独立实验室。
5. **H/N**：只有在新 APK 构建并安装成功后启动；否则在 18:00 前记 `BLOCKED` 并保留 toolchain 证据。
6. **收口**：只做读回、哈希、缺口登记；未完成项写 `NOT_RUN`/`BLOCKED`。

### 4.3 预计只能 `BLOCKED` / `NOT_RUN` 的缺口

| 缺口 | 预计状态 | 原因 | 能否本轮消除 |
| --- | --- | --- | --- |
| 本基线 H01–H12 客户端面 | `BLOCKED` | 无本基线 APK；toolchain 不完整；旧 APK 不能替代 | 仅当 JDK/SDK/NDK 补齐并重建成功 |
| 本基线 N01–N07、N09–N12 手机侧 | `BLOCKED` | 同上 | 同上 |
| F07-E 宿主运行中重启 | `BLOCKED` | 无独立内核可销毁 VM | 否（环境边界） |
| N08 真实隔离拒绝 | `BLOCKED` | 14 个真实目标需可直达私网的客户端网络 | 否（除非网络条件改变） |
| Web 同任务下钻 | `NOT_RUN` | capability 只在 Android Keystore；remote mode 拒绝 local header | 否（安全模型决定） |
| 交付材料完整性 | 缺口 | #256 删除 deck/视频/AI 与第三方披露/阶段材料 | 需用户决定是否恢复/重做 |
| 真机 / `arm64-v8a` / API36 / 公网 / 外部模型质量 | 边界 | 与上一轮相同，不在本轮分母 | 否 |

## 5. 事实 / 推断 / UNKNOWN

**事实（可直接复核）**

- `a1a6386` tree `90910c0b…`；`deccced..a1a6386` 共 34 个 first-parent 合入。
- `#256` 回退 6 个 PR；`apps/` 只改 3 个文件、6 行，均为文案/注释/测试；就这三处 apps/ 行而言，相对 `deccced` 净变更为零。
- `deccced..a1a6386` 改 `apps/api/src` 10 个文件、`apps/web/src` 23 个文件、`apps/mobile` 3 个文件（含图标）。
- `2626152..a1a6386` 的原生壳源码（`src-tauri/src`、capabilities、conf、Cargo）无差异，只有 `icon.png` 变化。
- 旧 APK `955d484b…` 仍在主检出 `.scratch/apk/`，哈希与收据一致。
- `middleware.py`/`main.py` 在本区间无 diff，Web 同任务下钻的 remote-mode 限制仍在。
- 全部旧 H/N/F/R `PASSED` 收据的 SHA 均不等于 `a1a6386`。

**推断（有依据，但未执行验证）**

- 旧 H/N 收据不能作为本基线证据，因为客户端 bundle 与服务端 API 同时变化（依据：§1、§3 的 diff）。
- 若 toolchain 不补齐，H/N 客户端面只能 `BLOCKED`（依据：§3.3 的轻量检查，未尝试构建）。
- H12 的旧 `FAILED` 不能假定仍失败或已修复（依据：#232/#251/#252/#254 触及相关路径，但无运行结果）。
- #256 的材料删除会造成对外交付材料缺口（依据：`git show --stat a1a6386` 的删除清单）。

**UNKNOWN（不虚构）**

- `D08` 标识：仓库内 `git grep 'D08'` 无验收项命中；该名称的来源与含义 `UNKNOWN`。
- 本基线 APK 能否在截止前成功构建：`UNKNOWN`（未执行）。
- H12 在本基线是否仍失败：`UNKNOWN`（未执行）。
- #254 是否修复 #239/#243/#248/#249 的全部用户可见路径：`UNKNOWN`（代码存在，未运行）。
- N08 的 14 个真实目标本轮是否可达：`UNKNOWN`（未探测）。
- F08–F10 在本轮部署环境能否执行：`UNKNOWN`（未启动部署 lane）。

## 6. 附录：命令与输出摘要

```text
$ git rev-parse HEAD
a1a6386ab4a18739445b8ffc1025c94e1af5b5d7
$ git cat-file -p a1a6386 | head -1
tree 90910c0b57a32165b221e4c15b16e2894dc93daa
$ git log --first-parent --format='%H' deccced..a1a6386 | wc -l
34
$ git diff --shortstat a1a6386^1 a1a6386
35 files changed, 8 insertions(+), 2784 deletions(-)
$ git diff --shortstat deccced a1a6386 -- apps/
50 files changed, 3140 insertions(+), 662 deletions(-)
$ git diff --shortstat deccced a1a6386
162 files changed, 11306 insertions(+), 856 deletions(-)
$ git diff --shortstat 2626152 a1a6386 -- apps/mobile apps/web/src/mobile apps/web/src/App.vue
7 files changed, 1282 insertions(+), 461 deletions(-)
$ git diff --stat 2626152 a1a6386 -- apps/mobile/src-tauri
apps/mobile/src-tauri/icons/icon.png | Bin 1916 -> 9051 bytes
```

旧收据入口（均为既有文件，未修改）：

- H：`docs/acceptance/h-matrix-final-20261022.md`（`2626152`）
- H 主线：`docs/acceptance/issue136/h-mainline-final-20261022.md`（`2626152`）
- N12/F05/F06：`docs/acceptance/issue133/execution-20261022.md`（`2626152`）
- F01–F04/F07：`docs/acceptance/issue134/execution-20261022.md`（`4208823`）
- R01–R04：`docs/acceptance/issue136/execution-20261022.md`（`65b49f7`）
- N01–N04：`docs/acceptance/issue129/README.md`（`ffadeb0`）
- N05–N08：`docs/acceptance/issue132/README.md`、`docs/acceptance/issue132/review-20261022.md`（`ba46f2a`；N08 `BLOCKED`）
- N09/N10：`docs/acceptance/issue130/execution-20261021.md`（`ffadeb0`）
- N11：`docs/acceptance/issue131/execution-20261021.md`（`ffadeb0`）
- F08–F10：`docs/acceptance/issue135/README.md`（`d12eeb7`）
- 前端第二轮：`docs/acceptance/frontend-round2/20261022.md`（`376d658` 实现，`65b49f7` 验收）


---

## 附：工具链快照的后续更正（Lead，2026-10-23T02:30Z）

本文第 3 点写「cargo 存在但 Android SDK 为空壳、未发现 JDK，截止前能否重建 APK 为 UNKNOWN」——那是分析当时的快照。后续（同日 09:0x）工具链子代理已恢复完整构建链并在 `a1a6386` 构建出 APK；Lead 又在 `83a7983` 上重建了**带 #73 测试 CA 信任**的 APK（`CD33C6EC12E4B5BDB7F1FB40AD02F9D2AA1CEB1863CA971BE1329F04E51A345A`，含本基线 web 产物）。

因此：客户端面不再只能 BLOCKED，H 组最小组合可执行（H01/H04 lane 已启动）；但 H02/H03/H05–H12 与 N01–N12 仍需要两套实例、受控模型接收器与故障注入矩阵，未在本轮执行。本文其余判定（must-rerun 37 项、可沿用 3 条、旧 PASSED 折算 0）不变。
