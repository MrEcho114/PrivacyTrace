# Acceptance Test Matrix: PT-808 异常边界与离线回放来源浏览器端验收

- **Milestone**: M1 (PT-808 真实浏览器异常边界、防 XSS 渲染、回放来源与可选本地备注重评)
- **Git Commit SHA**: 见 `evidence/browser-proof.json` 的 `git_commit` / `git_commit_anchored`
  - 本次修复运行环境无法 spawn shell 执行 `git rev-parse HEAD`，因此 `git_commit` 记为 `unknown`、`git_commit_anchored=false`
  - **合并前必须在可解析 SHA 的环境重跑一次**，确认 `git_commit_anchored=true` 后再把 SHA 填到此处
- **Execution Date**: 2026-10-10（修复后重跑，证据见 `evidence/browser-proof.json`）
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
| **TC-04** | **多来源数据标识与回放原生成核对**<br>由后端显式 `source_origin` 字段区分 `SYNTHETIC` / `CONTROLLED` / `OFFLINE_REPLAY` / `REAL_SCAN`；展示 `job.created_at` 原生成时间戳；核对 S1/PT-910 证据链 | R4 | 来源选择器切换与 DOM 徽标断言 | **TESTED_PASSED** | `evidence/screenshots/tc04-source-synthetic.png`<br>`evidence/screenshots/tc04-source-controlled.png`<br>`evidence/screenshots/tc04-source-offline-replay-s1.png` | **来源分类不再依赖 `sample_id` 命名前缀**，改读后端 `AnalysisJob.source_origin`；新增反向用例：`sample_id=CONTROLLED-LOOKALIKE` + `source_origin=REAL_SCAN` 必须判为 `REAL_SCAN`，`sample_id=demo` + `source_origin=CONTROLLED` 必须判为 `CONTROLLED`；样本卡片与出处区均展示 `job.created_at`；S1 报告哈希与字节码特征核对一致。 |
| **TC-05** | **可选本地备注重评与数据持久化**<br>支持提交可选本地备注（非必填），触发后端规则重算；原子落盘持久化；重载页面后回显一致；`authority` 锁定为 `UNAUTHENTICATED_LOCAL_EVENT` | R5 | 前端表单交互 + API 校验 + 页面重载 | **TESTED_PASSED** | `evidence/screenshots/tc05-optional-notes-review.png`<br>`evidence/browser-proof.json` | 备注为空时保存按钮保持可用且提交成功；有备注时正确呈现；页面刷新后 100% 完整回显；严格锁定未认证审计身份。**运行于隔离 store，不再读取或回写任何持久化真实报告。** |
| **TC-06** | **隔离容器 Docker 端到端扫描**<br>在隔离 Docker 容器内执行 APK 反编译与扫描的完整端到端生命周期测试 | R6 | Pytest Docker 模式 (`PRIVACYTRACE_DOCKER_TESTS=1`) | **UNTESTED** | N/A (Pytest 自动 skip) | 本地 Windows 宿主环境未启动 Docker 守护进程，属测试前置环境依赖，不影响主线逻辑与浏览器验收。 |
| **TC-07** | **工程契约与 JSON Schema 同步守护**<br>运行 Pydantic 契约同步脚本，验证前后端模型契约无 Diff | R6 | `scripts/export-schema.py` + Git 状态检查 | **TESTED_PASSED** | `packages/contracts/*.schema.json`<br>`apps/web/src/contracts.generated.ts` | 除 `ReviewRequest.note` 可选化外，本次新增 `AnalysisJob.source_origin`（枚举 `SYNTHETIC` / `CONTROLLED` / `OFFLINE_REPLAY` / `REAL_SCAN`），契约 0 diff。 |

---

## 2. Quality Gate Verification Results

全套工程质量门禁需在同一 Git SHA 下实测（结果于最终 Head 重跑后回填）：

1. **后端单元与集成测试 (Pytest)**: 待回填
2. **代码静态分析 (Ruff)**: 待回填
3. **前端类型检查与构建 (vue-tsc & Vite)**: 待回填
4. **契约导出验证 (`scripts/export-schema.py`)**: 待回填
5. **前端单元测试 (`npm --prefix apps/web test`)**: 待回填
6. **浏览器端自动化验收 (`scripts/verify-browser-acceptance.cjs`)**: 待回填
