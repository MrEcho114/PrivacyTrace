# Acceptance Test Matrix: PT-808 异常边界与离线回放来源浏览器端验收

- **Milestone**: M1 (PT-808 真实浏览器异常边界、防 XSS 渲染、回放来源与可选本地备注重评)
- **Git Commit SHA**: `b13b9548c49994de20ddf81e8c5e97b2dd71b08f`
- **Execution Date**: 2026-10-10T01:28:00Z
- **Test Environment**:
  - **OS**: Windows 11 Pro (x64)
  - **Runtime**: Node.js v24.17.0, Python 3.12.13
  - **Browser Engine**: Headless Chromium 152.0.7977.8 (Playwright v1.64.0)
  - **Frontend Dev/Preview**: Vite v7.3.6, Vue v3.5.13
  - **Backend API**: FastAPI / Uvicorn (local port 8000)

---

## 1. Acceptance Test Matrix

| 编号 | 验收项描述 | 归属需求 | 验证手段 / 测试工具 | 状态 | 产物 / 证据索引 | 说明 / 未测原因 |
|---|---|---|---|---|---|---|
| **TC-01** | **长文本渲染与候选条款分页交互**<br>验证 200,000 字符政策长文本渲染、候选条款分页 (20 条/页)、全文展开/收起/再展开，以及 Unicode 码点原句高亮与双向定位 | R1 | Playwright Headless Chromium 驱动真实交互 | **TESTED_PASSED** | `evidence/screenshots/tc01-long-text-pagination.png`<br>`evidence/browser-proof.json` | 2,000 条候选条款正确按 20 条/页分页 (100 页)；`<pre v-if>` 按需单实例挂载，折叠即卸载；`<mark>` 正确高亮。 |
| **TC-02** | **恶意输入安全转义与防 XSS 渲染**<br>对包含 `<script>`、`<img>`、`<svg>` 等恶意注入 payload，前端严格作为纯文本渲染，杜绝脚本执行；验证 CSP 头与 0 page errors | R2 | Playwright 动态 payload 注入与 DOM / Console 探针 | **TESTED_PASSED** | `evidence/screenshots/tc02-xss-defense.png`<br>`evidence/browser-proof.json` | `window.__xss_executed` 保持 `undefined`；DOM 中 0 可执行注入节点；CSP 策略头生效；控制台 0 未捕获 page errors。 |
| **TC-03** | **异常状态提示与字节码边界降级**<br>验证 partial、失败超时 (ZIP_INVALID)、用户取消 (CANCELLED) 的可复现结构化提示；409 终态友好处理；缺失 JADX 时以 Dalvik 字节码与 byte offset 作为降级依据，不伪造 JADX | R3 | 受控测试夹具 (`ui-controlled-*.json`) 回放与 HTTP 边界测试 | **TESTED_PASSED** | `evidence/screenshots/tc03-partial-bytecode-fallback.png`<br>`evidence/screenshots/tc03-structured-error-failed.png`<br>`evidence/screenshots/tc03-job-cancelled.png` | `failed_dex: ["classes2.dex"]` 与 `UNAVAILABLE_BYTECODE_FALLBACK` 如实呈现；错误信息结构化解析卡片展示；Dalvik 指令与 `offset_bytes` 真实呈现。 |
| **TC-04** | **多来源数据标识与回放原生成核对**<br>显式区分 `SYNTHETIC` (人工示例)、`CONTROLLED` (受控评测)、`OFFLINE_REPLAY` (离线回放) 与 `REAL_APK` (真实扫描)；展示 `job.created_at` 原生成时间戳；核对 S1/PT-910 证据链 | R4 | 来源选择器切换与 DOM 徽标断言 | **TESTED_PASSED** | `evidence/screenshots/tc04-source-synthetic.png`<br>`evidence/screenshots/tc04-source-controlled.png`<br>`evidence/screenshots/tc04-source-offline-replay-s1.png` | 来源卡片准确区分四类数据徽标与说明文案；样本卡片与出处区均完整展示 `job.created_at` ISO 与本地时点；S1 报告哈希与字节码特征核对一致。 |
| **TC-05** | **可选本地备注重评与数据持久化**<br>支持提交可选本地备注（非必填），触发后端规则重算；原子落盘持久化；重载页面后回显一致；`authority` 锁定为 `UNAUTHENTICATED_LOCAL_EVENT` | R5 | 前端表单交互 + API 校验 + 页面重载 | **TESTED_PASSED** | `evidence/screenshots/tc05-optional-notes-review.png`<br>`evidence/browser-proof.json` | 备注为空时保存按钮保持可用且提交成功；有备注时正确呈现；页面刷新后 100% 完整回显；严格锁定未认证审计身份，绝不冒充正式人工背书。 |
| **TC-06** | **隔离容器 Docker 端到端扫描**<br>在隔离 Docker 容器内执行 APK 反编译与扫描的完整端到端生命周期测试 | R6 | Pytest Docker 模式 (`PRIVACYTRACE_DOCKER_TESTS=1`) | **UNTESTED** | N/A (Pytest 9 项自动 skip) | 本地 Windows 宿主环境未启动 Docker 守护进程，属测试前置环境依赖，不影响主线逻辑与浏览器验收。 |
| **TC-07** | **工程契约与 JSON Schema 同步守护**<br>运行 Pydantic 契约同步脚本，验证前后端模型契约无 Diff | R6 | `scripts/export-schema.py` + Git 状态检查 | **TESTED_PASSED** | `packages/contracts/review-request.schema.json`<br>`apps/web/src/contracts.generated.ts` | `ReviewRequest.note` 更新为可选字段并赋予默认空字符串，JSON Schema 与 TypeScript 契约 0 diff。 |

---

## 2. Quality Gate Verification Results

全套工程质量门禁在同一 Git SHA 下实测结果：

1. **统一门禁脚本 (`scripts/check.ps1`)**:
   - **后端单元与集成测试 (Pytest)**: `269 passed, 9 skipped, 1 warning in 41.83s` (100% 通过)
   - **代码静态分析 (Ruff)**: `All checks passed!` (100% 通过)
   - **前端构建与类型检查 (vue-tsc & Vite)**: `15 modules transformed`, `built in 452ms` (100% 通过)
2. **契约导出验证 (`scripts/export-schema.py`)**:
   - `uv run --project apps/api python scripts/export-schema.py` 执行成功
   - 契约更新已固化，无任何未同步 Diff
3. **前端单元测试 (`npm --prefix apps/web test`)**:
   - 5/5 passed (100% 通过)
4. **浏览器端自动化验收 (`scripts/verify-browser-acceptance.cjs`)**:
   - 5/5 测试用例全数通过
   - 产出结构化证明文件 `evidence/browser-proof.json`
   - 产出 9 张全屏真实截图于 `evidence/screenshots/`
