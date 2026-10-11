# Acceptance Test Matrix: PT-808 异常边界与来源/投递双维度浏览器端验收

- **Milestone**: M1 (PT-808 真实浏览器异常边界、防 XSS 渲染、来源与投递标注、可选本地备注重评)
- **Execution Date**: 2026-10-10（第三轮复核修复后重跑）

> **关于提交锚定的准确说明（修正上一版的不实声明）**
>
> 上一版本矩阵声称 SHA 与收据一致，但两者实际不同，该声明已删除。现在按实际关系陈述：
>
> | 项目 | 值 |
> |---|---|
> | 最后一次跑浏览器验收时的 HEAD | 见 `evidence/browser-proof.json` 的 `git_commit`（唯一权威来源） |
> | 该字段是否成功锚定 | 见同文件 `git_commit_anchored`；为 `false` 时视为**未证明**，不得当成通过依据 |
> | 锚定之后的提交 | 仅包含本矩阵与收据/截图等**文档与证据**变更，不改动被测代码 |
>
> 判定规则：若 `git_commit_anchored` 为 `true`，则以该 SHA 为准；矩阵正文不再复制 SHA，
> 避免复制件过期后仍被当作证据。**文档更新时间不是重跑测试的证明。**

- **Test Environment**:
  - **OS**: Windows 11 Pro (x64)
  - **Runtime**: Node.js v24.17.0, Python 3.12.13
  - **Browser Engine**: Headless Chromium 156.0.8078.4 (Playwright v1.64.0，仓库 devDependency)
  - **Frontend Dev/Preview**: Vite v7.3.6, Vue v3.5.13
  - **Backend API**: FastAPI / Uvicorn，运行于**隔离端口**（默认 8123，可用 `PRIVACYTRACE_ACCEPTANCE_API_PORT` 覆盖）
  - **Data Store**: 每次运行在系统临时目录新建**一次性 store**，由 `fixtures/acceptance-jobs/` 播种；仓库 `data/` 目录全程只读

---

## 0. 可复现性说明（相对此前版本的修正）

早期版本的本矩阵在干净检出上**无法复现**，问题有三处，现已修正：

| 早期问题 | 现状 |
|---|---|
| 脚本探测 `C:/Users/Oasis/...` 等机器专属 Playwright / Chromium 路径 | 已删除；`playwright` 声明为仓库 devDependency，浏览器由 Playwright 自行解析（`PRIVACYTRACE_CHROMIUM` 可覆盖） |
| 依赖 git-ignored 的 `data/jobs/gkd-s1-first.json` | 已改为入库的最小 fixtures：`fixtures/acceptance-jobs/*.json` |
| 通过 `netstat` + `taskkill /F /PID` 强杀 8000 端口上的**任意**进程 | 已删除；脚本只终止**自己 spawn 的子进程**；端口被占用时直接报错退出 |
| TC-05 直接改写持久化报告，再在 `finally` 中整体回写快照 | 已删除；TC-05 在隔离 store 上运行，不再触碰真实报告文件 |
| 收据 SHA 依赖可执行 shell（`execSync git rev-parse`），受限环境直接记 `unknown` | 已改为**纯文件解析** `resolveGitCommit()`：支持 `.git` 为目录（普通检出）或为文件（linked worktree）、detached HEAD、loose ref 与 `packed-refs`、`commondir` 重定向；不再 spawn 任何 shell |
| 资源获取（API/Vite/Chromium）在 `try/finally` **之外**，异常退出会泄漏子进程与临时目录 | 已改为**全部资源收进最外层 `try/finally`**；`stopChildren()` 用 `process.kill(pid,0)` 做真实存活探测，超时后保留 store 并**以非零退出报告**，不再静默删除 |
| POSIX 下 `process.kill(-pid)` 打不到进程组（`spawn` 未设 `detached`），服务器存活且端口残留 | 已抽出 `scripts/lib/process-control.cjs`：POSIX 用 `detached: true` 建独立进程组后按组终止，Windows 用 `taskkill /T` |
| `WEB_PORT` 被占用时复用前端，仅比对 job id 与 fixture 名的交集即可通过 | 已改为**直接拒绝复用**：端口占用即报错退出，不尝试证明一个身份不可证的服务 |
| 旧版（无 `source_origin`）持久化记录升级后触发 `ValidationError`，且 `list()` 因单条坏记录整体失败 | 已加**读取期迁移**：缺字段记为 `UNKNOWN`（不猜测为 `REAL_SCAN`），磁盘原始字节不变；`list()` 跳过无法解析的记录 |

复现命令：

```bash
npm ci
npm run fixtures:acceptance   # 可选：重新生成 fixtures
npm run acceptance:browser
```

---

## 1. Acceptance Test Matrix

| 编号 | 验收项描述 | 归属需求 | 验证手段 / 测试工具 | 状态 | 产物 / 证据索引 | 说明 / 未测原因 |
|---|---|---|---|---|---|---|
| **TC-01** | **长文本渲染与候选条款分页交互**<br>验证 200,000 字符政策长文本渲染、候选条款分页 (20 条/页)、全文展开/收起/再展开，以及 Unicode 码点原句高亮与双向定位 | R1 | Playwright Headless Chromium 驱动真实交互 | **TESTED_PASSED** | `evidence/screenshots/tc01-long-text-pagination.png`<br>`evidence/browser-proof.json` | 2,000 条候选条款正确按 20 条/页分页 (100 页)；`<pre v-if>` 按需单实例挂载，折叠即卸载；`<mark>` 正确高亮。 |
| **TC-02** | **恶意输入安全转义与防 XSS 渲染**<br>对包含 `<script>`、`<img>`、`<svg>` 等恶意注入 payload，前端严格作为纯文本渲染，杜绝脚本执行；验证 CSP 头与 0 **未捕获页面异常** | R2 | Playwright 动态 payload 注入与 DOM / Console 探针 | **TESTED_PASSED** | `evidence/screenshots/tc02-xss-defense.png`<br>`evidence/browser-proof.json` | `window.__xss_executed` 保持 `undefined`；DOM 中 0 可执行注入节点；CSP 策略头生效；**0 未捕获页面异常**（`pageerror`）。注意：为覆盖负路径，控制台仍会记录非零 HTTP 错误日志（409/404），这是预期行为，不等于"控制台无任何错误"。 |
| **TC-03** | **异常状态提示与字节码边界降级**<br>验证 partial、硬失败 (ZIP_INVALID)、**真实超时 (SCAN_TIMEOUT)**、用户取消 (CANCELLED) 的可复现结构化提示；409 终态友好处理；缺失 JADX 时以 Dalvik 字节码与 byte offset 作为降级依据，不伪造 JADX | R3 | 受控测试夹具 (`ui-controlled-*.json`) 回放与 HTTP 边界测试 | **TESTED_PASSED** | `evidence/screenshots/tc03-partial-bytecode-fallback.png`<br>`evidence/screenshots/tc03-structured-error-failed.png`<br>`evidence/screenshots/tc03-timeout-failed.png`<br>`evidence/screenshots/tc03-job-cancelled.png` | `failed_dex: ["classes2.dex"]` 与 `UNAVAILABLE_BYTECODE_FALLBACK` 如实呈现；错误信息结构化解析卡片展示；**新增真实超时用例 `ui-controlled-timeout`（错误码 `SCAN_TIMEOUT`），断言超时提示、根因与终态下不渲染报告卡片**；Dalvik 指令与 `offset_bytes` 真实呈现。 |
| **TC-04** | **来源与投递双维度标识（含旧记录未知来源）**<br>由后端显式 `source_origin`（不可变：`SYNTHETIC` / `CONTROLLED` / `REAL_SCAN` / `UNKNOWN`）与 `delivery_mode`（每次响应：`LIVE_GENERATED` / `PERSISTED_REPLAY`）两个**正交**字段分别标注；展示 `job.created_at` 原生成时间戳；核对 S1/PT-910 证据链 | R4 | 来源选择器切换与 DOM 双徽章断言 | **TESTED_PASSED** | `evidence/screenshots/tc04-source-synthetic.png`<br>`evidence/screenshots/tc04-source-controlled.png`<br>`evidence/screenshots/tc04-source-real-scan-s1.png` | **来源分类不再依赖 `sample_id` 命名前缀**，改读后端 `AnalysisJob.source_origin`；两个徽章独立断言（来源徽章 + 投递徽章并排）。反向用例：`sample_id=CONTROLLED-LOOKALIKE` + `source_origin=REAL_SCAN` 必须判为 `REAL_SCAN`；重载后的报告必须显示 `PERSISTED_REPLAY` 且**不得**声称"本次生成"。`UNKNOWN` 专用于本字段引入前写入的记录，**不得**被读成真实扫描。样本卡片与出处区均展示 `job.created_at`。 |
| **TC-05** | **可选本地备注重评与数据持久化**<br>支持提交可选本地备注（非必填），触发后端规则重算；原子落盘持久化；重载页面后回显一致；`authority` 锁定为 `UNAUTHENTICATED_LOCAL_EVENT` | R5 | 前端表单交互 + API 校验 + 页面重载 | **TESTED_PASSED** | `evidence/screenshots/tc05-optional-notes-review.png`<br>`evidence/browser-proof.json` | 备注为空时保存按钮保持可用且提交成功；有备注时正确呈现；页面刷新后 100% 完整回显；严格锁定未认证审计身份。**运行于隔离 store，不再读取或回写任何持久化真实报告。** |
| **TC-06** | **隔离容器 Docker 端到端扫描**<br>在隔离 Docker 容器内执行 APK 反编译与扫描的完整端到端生命周期测试 | R6 | Pytest Docker 模式 (`PRIVACYTRACE_DOCKER_TESTS=1`) | **UNTESTED** | N/A (Pytest 自动 skip) | 本地 Windows 宿主环境未启动 Docker 守护进程，属测试前置环境依赖，不影响主线逻辑与浏览器验收。 |
| **TC-07** | **工程契约与 JSON Schema 同步守护**<br>运行 Pydantic 契约同步脚本，验证前后端模型契约无 Diff | R6 | `scripts/export-schema.py` + Git 状态检查 | **TESTED_PASSED** | `packages/contracts/*.schema.json`<br>`apps/web/src/contracts.generated.ts` | 契约 0 diff。本轮契约变化：`AnalysisJob.source_origin` 枚举为 `SYNTHETIC` / `CONTROLLED` / `REAL_SCAN` / `UNKNOWN`；`Report.delivery_mode` 为 `LIVE_GENERATED` / `PERSISTED_REPLAY`。 |

---

## 2. Quality Gate Verification Results

以下为在 `fix/pr33-code-review`（第三轮复核修复后）的实测结果：

| # | 门禁项 | 命令 | 结果 |
|---|---|---|---|
| 1 | 后端单元与集成测试 | `uv run --project apps/api --extra worker pytest apps/api/tests -q` | **322 passed, 11 skipped, 2 failed** |
| 2 | 代码静态分析 (Ruff) | `uv run --project apps/api ruff check apps/api/src apps/api/tests scripts` | **All checks passed!** |
| 3 | 前端类型检查与构建 | `npm run build --workspace @privacytrace/web`（`vue-tsc --noEmit` + Vite） | **通过，0 error** |
| 4 | 契约导出验证 | `uv run --project apps/api python scripts/export-schema.py` + `git diff --exit-code` | **0 diff（幂等）** |
| 5 | 前端单元测试 | `npm run test --workspace @privacytrace/web` | **28 / 28 pass, 0 fail** |
| 6 | 浏览器端自动化验收 | `npm run acceptance:browser` | **TC-01…TC-05 全部 PASSED，EXIT=0**，收据 `git_commit_anchored: true` |
| 7 | Challenger 对抗压力套件 | `node scripts/challenger-adversarial-suite.cjs` | **全部通过**，0 page error、0 XSS；资源清理完整（浏览器关闭、服务终止、临时 store 删除） |

> 门禁 #7 此前**不在任何 CI 入口内**（`scripts/check.sh` 只跑 pytest / ruff / 契约 / 前端构建），
> 这正是它与页面和契约脱节却长期无人察觉的原因。本矩阵如实记录其实际运行结果，
> 但不声称它已被 CI 守护。

### 关于门禁 #1 的失败（**非本次改动引入**）

```
FAILED apps/api/tests/test_job_creation.py::test_one_reservation_wins_across_processes_and_survives_restart
FAILED apps/api/tests/test_job_creation.py::test_concurrent_pipeline_never_scans_both_inputs_for_one_id
```

- 失败原因：`PermissionError: [Errno 13] Permission denied: ...\.lock`，Windows 平台下跨进程 `msvcrt.locking` 争用。
- **归因验证**：在**原始 Head**（未含本次任何改动）上重跑同样两条用例，得到**相同**的 `F.....F` 结果 → 属**既有环境问题**，与本 PR 的修复无因果关系。
- 另注：`test_governance_cli.py::test_local_source_installs_commit_objects_not_dirty_executor[True/False]`
  是**负载敏感**用例——全量并发时可能触发 `subprocess.TimeoutExpired (40s)`，单独运行时 **3/3 稳定通过**
  （实测 3.05–3.54s）。因此全量运行的失败数在 **2~4** 之间浮动，两种情形均为既有问题。
- 建议：不在本 PR 内处理（会扩大改动面）；另开 issue 跟踪 Windows 下 `JobStore` 跨进程锁的健壮性。
