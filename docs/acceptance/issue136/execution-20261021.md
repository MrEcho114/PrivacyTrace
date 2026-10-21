# 验收 H 本机执行记录（R01 / R03 / 交付包）

- **票**：#136（父票 #128，`[验收 H][PT-MOB-301] 仓库/Web 回归、冻结版本与交付包冷启动`）
- **执行人 / 会话**：`Onikamicpj` / 本机代理会话，2026-10-21
- **执行时间**：2026-10-21 15:48–17:20 (UTC+8) / 07:48–09:20Z
- **被测版本**：`ffadeb06af70072b5ee2d931ee565e5b7e546acd`（main，PR #127 合并后）
- **工作方式**：detached HEAD，工作区干净，未改动、未推送任何远程分支

> 本记录只陈述本机实际执行得到的观察。未执行项标 `NOT_RUN` 或 `BLOCKED`，不以下游推断、CI 结果或历史证据顶替本机结论。
> 本记录不构成对作品合规性、真实设备行为、公网部署或赛事提交结果的判定。

## 0. 环境

| 项 | 值 |
| --- | --- |
| OS | Windows（Git Bash） |
| Node / npm | v22.22.2 / 10.9.7 |
| Python / uv | 3.13.14 / 0.11.23（uv 由 `python -m pip install uv==0.11.23` 现场装入项目内缓存） |
| Playwright | 1.64.0 |
| 浏览器 | Chromium 155.0.4283.62（系统 Edge，经 `PRIVACYTRACE_CHROMIUM` 指定，未执行 `playwright install`） |
| Docker / adb / Java | **全部缺失**；`wsl.exe` 被宿主安全策略拒绝启动 |

## 1. 结论

| 案例 | 本机状态 | 依据 |
| --- | --- | --- |
| **R01** 仓库检查 | **部分通过（11/13）** | §2 |
| **R02** Spec30 六/十二 | **BLOCKED** | 需真实隔离 Docker 扫描 |
| **R03** 浏览器与前端验收 | **PASSED** | §3 |
| **R04** 部署专项 | **BLOCKED** | 需固定版本镜像与受限配置 |
| 交付包哈希 / 清单 / 冷启动 | **PASSED** | §4 |
| 离线回放（断网可看） | **PASSED**（范围如声明） | §5 |

## 2. R01 执行记录

`check.sh` 的权威入口是 Git Bash 中的 `bash scripts/check.sh`（`docs/agents/local-environment.md` §2）。该脚本在本机 bootstrap 阶段即失败，原因见 §7.1；以下按脚本原有顺序逐项执行等价命令，每项单独记录退出码。

| # | 项目 | 命令 | 结果 | 观察 |
| --- | --- | --- | --- | --- |
| 1 | 整体入口 | `bash scripts/check.sh` | **FAILED** | 第 8 行 `bin/python` 不存在，见 §7.1 |
| 2 | 工具引导（等价） | `<venv>/Scripts/python.exe -m pip install uv==0.11.23` | **PASSED** | uv 0.11.23 装入 `.themasterplan/cache/check-tools` |
| 3 | 依赖同步 | `uv sync --project apps/api --locked --extra worker` | **PASSED** | 退出码 0 |
| 4 | 治理校验 | `python .themasterplan/bin/themasterplan.py verify --root .` | **PASSED** | `{"ok": true, "status": "OK", "issues": []}` |
| 5 | 后端测试 | `pytest apps/api/tests` | **8 failed**（收集 1717） | §2.1 |
| 6 | 端到端测试 | `pytest tests/e2e` | **PASSED** | 61 passed / 4 skipped / 退出码 0 |
| 7 | 静态检查 A | `ruff check apps/api/src apps/api/tests scripts/*.py` | **PASSED** | All checks passed |
| 8 | 静态检查 B | `ruff check --config apps/api/pyproject.toml deploy tests/e2e` | **PASSED** | All checks passed |
| 9 | 用户研究包 | `python scripts/verify-user-study-pack.py` | **PASSED** | `issues: 0` / `result: OK`（question-bank=14, answer-key=50, assignment=8, observations=72） |
| 10 | 契约导出 | `python scripts/export-schema.py` | **PASSED** | 重新导出成功 |
| 11 | 契约零漂移 | `git diff --exit-code -- packages/contracts apps/web/src/contracts.generated.ts` | **PASSED** | 退出码 0，无漂移 |
| 12 | 依赖锁一致性 | `npm ci --dry-run` | **PASSED** | 退出码 0，"added 50 packages" |
| 13 | 前端单测 | `npm run test --workspace @privacytrace/web` | **PASSED** | 111 tests / 111 pass / 0 fail |
| 14 | 生产构建 | `npm run build` | **PASSED** | `vue-tsc --noEmit` + `vite build`，3.03s，204.33 kB JS / 29.75 kB CSS |

第 12 项说明：`check.sh` 第 40 行执行 `npm ci`，该命令会先删除现有 `node_modules` 再重装。本机 npm 源响应在 12s 量级，重装中途失败会留下残缺依赖，因此**未执行 `npm ci` 本体**，改用 `--dry-run` 验证 `package-lock.json` 与 `package.json` 一致。这不是 PASSED 的等价替代，网络稳定时应完整重跑。

### 2.1 8 个失败：全部为隔离扫描不可用

```text
test_pr88_evidence_integrity.py::test_registered_package_set_identity_is_bound_before_report[False]
test_pr88_evidence_integrity.py::test_registered_package_set_identity_is_bound_before_report[True]
test_e2e_r6_opaque.py::test_tier2_missing_base_apk_in_package_set
test_e2e_r6_opaque.py::test_tier4_end_to_end_collector_export_to_report_receipts
test_challenger_m1_2_empirical_m1.py::test_candidate_unreviewed_semantics_and_insufficient_evidence
test_challenger_m1_2_split_dex.py::test_single_apk_pipeline_end_to_end_backward_compatibility
test_e2e_pt_mob_102.py::test_r3_f29_non_blocking_unreviewed_candidate_start
test_e2e_pt_mob_102.py::test_t4_real_world_multisplit_end_to_end_workflow
```

两种表现，同一根因：

- 上传 / 发现路径：`503 {"detail":"ISOLATED_INSPECTION_UNAVAILABLE"}`
- 扫描流水线：job `FAILED != SUCCEEDED`，随后 `Job report is not available`

`apps/api/src/privacytrace/isolated_scan.py:32` 的 `docker_prefix()` 在 `os.name == "nt"` 时返回 `["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "env", ... "docker", ...]`。本机 `wsl.exe` 被宿主安全策略直接拒绝启动，`web_api.py:60` 遂把非输入类 `ScanError` 映射为 503。

**同一 SHA 的对照**：Actions 在 `ffadeb06` 上 Check / Browser Acceptance / Spec30 Integration / Deployment Baseline / Deployment Acceptance 五个 workflow 均 `success`（2026-10-21T07:41Z 触发）。该对照只说明这些用例在具备 Docker 的环境中通过了同一提交，**不改变本机 8 项 `FAILED` 的原始状态**，也不能替代本机运行。

### 2.2 汇总行缺失与基线

| 项 | 值 |
| --- | --- |
| `ffadeb06` 收集用例数 | **1717**（`pytest --collect-only`） |
| `ffadeb06` 本机失败 | **8**（清单见 §2.1） |
| `ffadeb06` 完整汇总行 | **未捕获**（原因见 §7.2，非测试结果本身） |
| 同一命令在 `68015de` 的完整汇总（基线） | `8 failed, 1506 passed, 200 skipped in 423.60s`（共 1714 用例） |

`ffadeb06` 比 `68015de` 多 3 个用例（PR #127 新增），失败数量与失败用例集合均无变化。

拆分复核（独立 `--basetemp`，摘要可正常输出）：`test_pr88_evidence_integrity.py` + `test_e2e_r6_opaque.py` + `test_challenger_m1_2_empirical_m1.py` + `test_challenger_m1_2_split_dex.py` → **6 failed, 104 passed, 4 skipped in 31.28s**；`test_e2e_pt_mob_102.py` 的 2 个失败已单独确认。

## 3. R03 浏览器与前端验收

| 脚本 | 命令 | 结果 | 观察 |
| --- | --- | --- | --- |
| 浏览器验收 | `npm run acceptance:browser` | **PASSED** | TC-01…TC-06 全部 PASSED，`overall_status: PASSED` |
| 前端流程 | `npm run acceptance:frontend` | **PASSED** | 见下 |
| 预览生命周期 | `npm run acceptance:preview` | **PASSED** | start/stop、check 恢复、外部进程保护全部通过 |

**acceptance:browser 收据**（脚本自动生成，锚定提交）：见 `evidence/browser-proof-ffadeb06.json`

- `git_commit`: `ffadeb06af70072b5ee2d931ee565e5b7e546acd`
- `git_commit_anchored`: `true`
- `timestamp`: `2026-10-21T08:20:40.099Z`
- `overall_status`: `PASSED`
- 覆盖：TC-01 长文本分页、TC-02 XSS 防御、TC-03 结构化错误 / 超时 / 取消与 409 恢复、TC-04 来源与交付徽章 + `created_at`、TC-05 无备注与有备注提交及持久化、TC-06

**acceptance:frontend 覆盖分类**（按票面要求区分 Mock / 预置输入 / 真实外部）：

- 真实浏览器 + 真实本地 HTTP：`verify-policy-assist.cjs` 的 **10 项**检查通过，**无模型请求、无 APK 上传**（合成政策文本）。
- **Mock**：报告流为 **13 个被 mock 的报告请求**、11 条移动端断言通过；不等同真实 Docker 扫描产出的报告。
- 预置输入：import、引用校验、枚举编辑、增删、来源切换、持久化隔离、取消/重试、报告证据、响应式布局、焦点与设置通过（5 个视口 1440 / 1920 / 1280 / 768 / 390）。

> 边界：R03 验证的是界面与前端契约，Mock 部分不得当作真实扫描或真实模型的证据。

## 4. 交付包复核

| 项 | 观察 |
| --- | --- |
| SHA-256 | `6ba1fbde366fb6acc8ff3054313c7177f43141d08620cf228c9f82b1e9e46967` |
| 字节数 | 64,261,830 |
| 条目 | 436 = **435 文件 + 1 空目录** |
| 解压后大小 | 67,957,481 字节 |
| 根目录 | 单一 `PrivacyTrace_322234/` |
| CRC | `zipfile.testzip()` 返回 None，**全通过** |
| 目录结构 | `00_材料清单.md` + `01_作品及成果文件`(407) / `02_作品展示视频`(3) / `03_作品介绍文档`(2) / `04_运行或使用说明`(3) / `05_补充成果材料`(16) / `06_第三方资源说明`(1) / `07_AI工具使用补充说明`(2) / `08_学籍等专项材料`(1) |
| 冷启动 | 解压到全新目录，436 条目全部落盘，9 个顶层条目与包内一致 |
| 与既有记录一致性 | 与 2026-10-21 打包记录（同 SHA、同 435 文件、CRC 通过）完全一致 |

## 5. 离线回放验证（断网可看）

方法：Playwright 1.64 驱动系统 Edge，打开包内 `01_作品及成果文件/demo-web/demo.html`，并**显式强制离线**：

- `context.setOffline(true)` —— 浏览器上下文进入离线状态；
- `context.route(/^https?:\/\//i, route => route.abort('internetdisconnected'))` —— 另外拦截并中止所有 http(s) 请求，被中止的 URL 全量记入收据 `blocked_external_requests`。

因此"断网可看"不是靠"观察到 0 次 HTTP 请求"推断，而是网络通道被主动切断后的实际加载与交互结果。脚本见 `verify-demo-offline.cjs`，收据见 `evidence/demo-offline-receipt.json`，截图见 `evidence/` 下 4 张。

### 5.1 交互路径与逐页断言

按包内说明的真实路径点击，每步断言关键内容出现：

| 步骤 | 动作 | 断言 | 结果 |
| --- | --- | --- | --- |
| 1 | 打开 `file://…/demo.html` | `status 200`、标题含 `PrivacyTrace`、H2 含「导入分析材料」 | PASSED（135 ms） |
| 2 | 点击「体验示例」 | 正文出现 `paperboat-example.apk` 与两份政策名（纸舟地图隐私政策、云点统计服务说明） | PASSED |
| 3 | 点击「检查候选」 | H2 含「检查政策候选」，正文含「政策原文」「候选声明」 | PASSED |
| 4 | 点击「进入流程演示」 | H2 含「分析流程演示」，正文含「核对输入」 | PASSED |
| 5 | 点击「进入下一阶段」 | 页面推进到「静态线索」阶段 | PASSED |
| 6 | 390×844 视口 | `scrollWidth - innerWidth = 0` | PASSED |

三页（导入 / 候选 / 流程演示）在离线状态下**全部可达**，与包内 `说明.txt` §三 的声明一致。

### 5.2 允许的失败请求（协议 + 路径双约束）

两轮修订后，白名单不再只看错误类型、也不只看路径，而是**同时约束协议与包内路径**：

| 规则 id | 协议 | 包内路径 | 依据 |
| --- | --- | --- | --- |
| `declared-font-fallback` | 仅 `file:` | `fonts/NotoSansSC-Variable.woff2`、`fonts/NotoSerifSC-Variable.woff2` | `说明.txt` 已声明字体回退；包内无 `fonts/` 目录（见 §5.5） |
| `backend-unavailable` | 仅 `file:` | `api/v1/*` | 静态版无后端，`说明.txt` §四 已声明 |

**为什么必须带协议**：若只按路径截取，`https://example.com/api/v1/x` 会被归一成 `api/v1/x` 而误命中白名单。现在协议为 `http:` / `https:` 时一律判 DENIED。

本次共 3 个失败请求，**3 个均为 `file:` 协议且命中白名单、0 个越界**。

控制台错误**按条数与错误码配额逐一消解**，不是"存在同码请求就算归因"：

- 每个已放行的失败请求，为其错误码贡献 1 个配额；
- 每条控制台错误必须消耗一个未被认领的配额，扣不掉即计入 `unexplained`；
- 因此"出现 3 条 `ERR_FILE_NOT_FOUND`、但只有 2 个字体请求放行"这种情形会被判 FAILED。

另设独立检查 `no_external_network_attempt`：把 `blocked_external_requests` 与 `requestfailed` 中协议为 `http(s)` 的条目**合并去重**后统计，非 0 即失败。

### 5.3 退出码语义与三组负向验证

脚本行为：`overall_status = PASSED` 时 `exit 0`；任一检查未通过 `exit 1`；用法或执行异常 `exit 2`。

脚本内置两个注入开关，用于证明判定不是"看起来严"：

| 场景 | 参数 | 期望 | 实测 |
| --- | --- | --- | --- |
| 正常回放 | 无 | PASSED / exit 0 | ✅ `no_external_network_attempt — 0` |
| **同错误码、非白名单资源** | `--inject-missing-resource` | FAILED / exit 1 | ✅ `DENIED [file:] __missing_resource__.png`；控制台 5 条错误中 **1 条 unexplained** |
| **外部 http(s) 尝试** | `--inject-external-request` | FAILED / exit 1 | ✅ `no_external_network_attempt — 1 external http(s) attempt: https://example.com/__external__.png` |
| 页面不存在 | 传入不存在的路径 | FAILED / exit 1 | ✅ `checks_failed: 6`，`0 allowed, 1 denied` |

第二组直接回应"相同错误码、非白名单资源"：注入的 `__missing_resource__.png` 与字体同为 `ERR_FILE_NOT_FOUND`，但因路径不在白名单、且配额已被两个字体请求占满，被正确判为越界。

第三组暴露并修掉了一个真实盲区：**CSP 可能先于路由拦截外部资源**，此时请求不会进入 `blocked_external_requests`，只能从 `requestfailed` 的协议判断；现判定已合并两处来源去重统计。

### 5.4 未覆盖部分

静态版中「分析进度」「对照报告」两个步骤按钮**不存在**，与 `说明.txt` §四「完整的对照报告页在单文件模式下不可达，需按方式一启动服务」一致，因此不计为失败，但也不得表述为"报告页离线可用"。

### 5.5 执行中发现的包内问题（BUG-136-02）

`demo.html` 引用了 `fonts/NotoSansSC-Variable.woff2` 与 `fonts/NotoSerifSC-Variable.woff2`（页面中解析到 `01_作品及成果文件/fonts/…`），但包内 `01_作品及成果文件/demo-web/` 下只有 `assets/`（CSS + JS），**没有 `fonts/` 目录**，因此两个字体请求均 404，回退到系统字体。

- **影响**：不影响功能与布局；`说明.txt` 末尾已声明「字体使用系统回退字体渲染，视觉与完整版略有差异，不影响布局与可读性」。
- **性质**：交付包完整性瑕疵（引用了包内不存在的文件），记为 `BUG-136-02`。
- **处理**：本验证不把"字体加载成功"作为 PASSED 条件，而是把这两个**具体请求**列为已声明允许项；若将来补齐字体文件，白名单应同步收紧到零。

结论：离线回放按包内声明范围 **PASSED**——在无网络、无后端、无任何环境安装的条件下，导入 / 候选 / 流程演示三页可达且可交互，报告页不在支持范围内。

## 6. 未验证边界与 BLOCKED

| 项 | 状态 | 原因 | 需要什么才能完成 |
| --- | --- | --- | --- |
| R02 Spec30 six / twelve | **BLOCKED** | `scripts/validate-spec30.py` 内部先 `docker_prefix() + build` 构建受控镜像，六 / 十二场景跑在该镜像中 | Linux + Docker Engine + `playwright@1.62.1` + chromium |
| R04 部署专项 | **BLOCKED** | `deploy/check_acceptance.sh` 首行要求 `id -u = 0`，构建 api/web/runner/scan 四个镜像并做上线、回滚与恢复 | **Linux + root** + Docker + compose v2 + 干净已提交工作区 |
| R01 中 8 个扫描类用例 | **FAILED（环境）** | 见 §2.1 | 同上：Linux + Docker |
| `npm ci` 本体 | **NOT_RUN** | 见 §2 第 12 项 | 网络稳定时重跑即可 |
| 真实 Android 设备 / 模拟器行为 | **NOT_RUN** | 无 adb、无模拟器、无 Java | 专用模拟器目标或真机 |
| 单包 / splits 的真实非空报告 | **BLOCKED** | 依赖真实扫描 | 同 R02 |
| 外部模型质量 | **NOT_RUN** | 未配置模型端点 | 自带模型端点 |

> 交接说明：上述四项需要 Linux + Docker 的项已整理为 [R02-R04-handoff.md](R02-R04-handoff.md)（环境要求、逐条命令、产物位置、交回方式与禁止事项），可直接交给具备条件的执行人。

不得由本记录外推：真实设备或 OEM 行为、公网部署与公网 TLS 信任、商店审核、外部模型质量、赛事提交结果。

## 7. 执行中发现的问题

### 7.1 `scripts/check.sh` 在 Windows 上无法自举（测试设施缺口）

详见 [bugs.md](bugs.md) BUG-136-01。

### 7.2 宿主批量删除策略会截断 pytest 摘要（环境问题，非仓库缺陷）

本机运行环境对单轮删除超过 50 个文件的操作有确认拦截。pytest 在 session 结束时清理 `pytest-of-<user>/garbage-*`（本轮 494 个文件）触发拦截，进程在打印 `N failed, M passed` 摘要**之前**被终止，导致：

- 首轮 `pytest tests/e2e` 进度条全绿却被记为退出码 1（**假失败**）；
- 全量 `pytest apps/api/tests` 丢失汇总行，只能靠进度条数 `F`。

规避：加 `--basetemp=<新目录>`，避免 pytest 删除旧垃圾目录；此时摘要正常输出。已按此方式复核 `tests/e2e` = **61 passed / 4 skipped / 退出码 0**。

另有两类失败组合（记录以免他人重复踩）：

- **全量 + `--basetemp` 指向仓库内 `tmp/`**：两次运行分别跑到 19m58s / 12m44s 仍停在进度 20%，已中止；拆分到 4 个文件（104 用例）时 31s 完成，说明是特定用例在全量顺序下的长时间阻塞。
- **绕过 `uv run` 直接用 `apps/api/.venv/Scripts/python.exe -m pytest`**：额外产生 30 个 `E`（fixture 级错误），该跑法**不可采信**。权威方式仍是 `uv run --project apps/api --locked --extra worker pytest`。

## 8. 证据清单

| 文件 | 说明 |
| --- | --- |
| `evidence/browser-proof-ffadeb06.json` | acceptance:browser 收据副本（锚定 `ffadeb06`）。仓库原 `evidence/browser-proof.json` 未改动；本副本仅把 `step_sequences` 中两处本机绝对截图路径改写为仓库相对路径，其余字段未改 |
| `evidence/demo-offline-receipt.json` | 离线回放收据。由脚本在收集阶段就规范化路径，不含本机盘符；含逐项 `checks`、`pages_reached`、`failed_requests`（每条含 allow/deny 与命中的规则 id）、`console_errors.unexplained` 与 `blocked_external_requests` |
| `evidence/demo-offline-import-1440.png` | 导入页（离线，1440×900） |
| `evidence/demo-offline-candidates-1440.png` | 候选页（离线，1440×900） |
| `evidence/demo-offline-flow-1440.png` | 流程演示页（离线，1440×900） |
| `evidence/demo-offline-flow-390.png` | 流程演示页（离线，390×844） |
| `verify-demo-offline.cjs` | 离线回放验证脚本：显式离线 + 请求拦截 + 逐页内容断言 + 按资源路径的错误白名单 + 非零退出码。在仓库内执行即可解析 `playwright`；输出目录建议给临时路径，避免在仓库里留下产物 |
