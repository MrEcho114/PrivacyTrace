# R02 引擎套件端到端验收（Spec30 六场景 + PT-907 十二场景，2026-10-23）

状态：**PASSED**（两个 suite 均在基线 `83a7983ee6e9bd580dfe41623e06f83c435b9d34` 上以 CI 等价 Linux 环境实际执行通过）。本文件只登记实际执行过的运行；首跑与 Windows 试跑的 FAILED 原样保留，不用重跑覆盖。状态只使用 PASSED / FAILED / BLOCKED / NOT_RUN。

判据：按 `.github/workflows/spec30-integration.yml` 的 `source-browser-offline` 矩阵（`spec30`、`pt907`）本地等价执行，入口为 `scripts/validate-spec30.py`；源码两次构建的 APK 哈希必须一致且与 `artifacts.lock.json` 相符，之后才进入隔离 worker、CLI/HTTP、浏览器与（spec30）独立断网回放。口径与 [最新基线全流程验收](e2e-latest-baseline-20261023.md) 一致：只认同一基线实际执行的证据。

## 1. 结论

| Suite | 基线 | 权威运行目录 | 开始 UTC → 结束 UTC | 耗时 | 退出码 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| spec30（六场景 + 独立断网回放） | `83a7983`（tree `b3922fa3e808b6c9f6a4f4c19be00e3f3b53652f`） | `tmp/e2e/20261023/spec30-run3/` | 2026-10-23T00:52:03Z → 00:55:06Z | 183 s | 0 | **PASSED** |
| pt907（十二场景 + 浏览器证据） | `83a7983`（同上） | `tmp/e2e/20261023/pt907/` | 2026-10-23T00:55:38Z → 00:59:05Z | 207 s | 0 | **PASSED** |

`integration-receipt.json`：spec30 `passed=true`、`scenario_count=6`、`dirty_checkout=false`、12/12 stage 退出码 0；pt907 `passed=true`、`scenario_count=12`、`dirty_checkout=false`、9/9 stage 退出码 0。两者 `commit_sha` 均为 `83a7983ee6e9bd580dfe41623e06f83c435b9d34`。

判定口径：同一基线上，环境缺陷（Docker 死代理、容器 egress、镜像源、非 root 输出权限）修复后重跑通过，首失败证据全部保留在第 5 节；若评审要求「首次执行即通过」，本轮不满足，但失败原因均不指向产品行为。早期在 `a1a6386` 上的首跑不适用于本基线，只作为环境缺陷的证据。

## 2. 基线、代码与环境

- 被测源码：`origin/main` = `83a7983ee6e9bd580dfe41623e06f83c435b9d34`，tree `b3922fa3e808b6c9f6a4f4c19be00e3f3b53652f`（共享 worktree 已快进到该 SHA；权威运行使用 WSL 原生 clone，`git rev-parse HEAD` 与 `HEAD^{tree}` 逐字节核对一致，`dirty_checkout=false`）。
- 权威执行环境：WSL `Ubuntu-24.04`（Ubuntu 24.04.4 LTS，内核 6.18.33.2-2，WSL 2.7.11.0），非 root 用户 `oasis`（uid 1000，与 CI runner 非 root 前提一致）；clone 位于 `/home/oasis/pt907-src`。
- Docker：Server `29.7.2`，`/etc/docker/daemon.json` 已由 Lead 修复为 `registry-mirrors: ["https://docker.m.daocloud.io", "https://docker.1ms.run"]`、`mtu: 1280`、去死代理；`iptables -P FORWARD` 由 DROP 恢复为 ACCEPT（`docs/agents/local-environment.md` §4 记录的已知环境假失败）。
- 工具链：Node `v24.17.0`（与 CI 固定值一致）、npm `11.13.0`、uv `0.11.23`、Playwright `1.62.1`、Chromium `151.0.7922.34`（`chromium-1234`，Linux 版，`playwright install --with-deps chromium` 实际下载）。
- 受控构建：JDK Temurin `17.0.20.1+1`、Build Tools `35.0.0`、Android `35 revision 2`；归档来自 `dl.google.com`/Adoptium 锁定 URL，两次构建 APK 哈希一致（spec30 6 个 APK/12 个源码哈希；pt907 12 个 APK/24 个源码哈希）。
- 端口：WSL 网络命名空间内 `8000/5173/8765` 空闲，权威运行全部使用 CI 默认端口（不再受 Windows 宿主 5173 被其他会话占用影响）。
- 与 CI 的已知差异：本地 venv 使用 WSL 系统 CPython `3.12.3`（CI runner 为 python3.12.x 补丁版本）；worker 容器仍为锁定的 `python:3.12.13-slim`。Node 精确固定 24.17.0。

## 3. 实际命令（本地等价）

准备（Windows 侧与 WSL 侧各一次；WSL 侧为权威环境）：

```bash
npm install --prefix tmp/spec30-browser --no-save --package-lock=false playwright@1.62.1
node tmp/spec30-browser/node_modules/playwright/cli.js install --with-deps chromium   # Windows 侧无 --with-deps
/home/oasis/pt907-tools/bin/uv sync --project apps/api --locked --extra worker
npm ci
```

执行（WSL clone `/home/oasis/pt907-src` 内；`--playwright-modules` 默认值就是 `<root>/tmp/spec30-browser/node_modules`，已显式传入以固定证据）：

```bash
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py \
  --suite spec30 --output tmp/e2e/20261023/spec30-run3 --playwright-modules tmp/spec30-browser/node_modules
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py \
  --suite pt907  --output tmp/e2e/20261023/pt907      --playwright-modules tmp/spec30-browser/node_modules
```

spec30 stage 及实测耗时（`integration-receipt.json`）：build-a 23.2 s、build-b 17.4 s、rebuild-hashes 0、worker-build 39.4 s、six-scenarios 28.0 s、independent-dex-locations 0.8 s、source-cli-regressions 13.6 s、web-build 11.7 s、export-offline 0.3 s、browser-fixtures 0.3 s、controlled-browser 18.7 s、independent-offline 5.8 s。pytest `9 passed`（1 条既有 Starlette/httpx 弃用警告）。

pt907 stage：build-a、build-b、rebuild-hashes、worker-build、twelve-scenarios、independent-dex-locations、source-cli-regressions（pytest `19 passed`）、web-build、controlled-browser 全部退出码 0。

## 4. `integration-receipt.json` 关键字段与场景状态

### 4.1 方案汇总（`evaluation/comparison.json` → `summaries`）

| Suite | 方案 | 总数 | status_agreement | failures | abstentions | missing_target_predictions | execution_failures |
| --- | --- | --- | --- | --- | --- | --- | --- |
| spec30 | permission_keyword | 6 | 2 | 0 | 0 | 0 | 0 |
| spec30 | api_flat | 6 | 3 | 0 | 1 | 0 | 0 |
| spec30 | privacytrace | 6 | **6** | 0 | 2 | 0 | 0 |
| pt907 | permission_keyword | 12 | 2 | **1** | 0 | 1 | 0 |
| pt907 | api_flat | 12 | 4 | 0 | 1 | 0 | 0 |
| pt907 | privacytrace | 12 | **12** | 0 | 3 | 0 | 0 |

`failures` 是既有 benchmark 对「未给出目标预测」的计数，不是执行崩溃：`execution_failures` 在两个 suite、三个方案上均为 0，`coverage.status` 全部 `COMPLETE`（6/6、12/12），`truncated_outputs=0`。spec30 的 2/6、3/6 与 [spec30 验证记录](../stages/spec30-verification.md) 的历史结果一致；pt907 的 C12 `permission_keyword` `actual=null` 是名义基线（仅权限+精确短语）在该场景未给出预测，见 4.2 与 4.4 的「失败项」。

### 4.2 spec30 每场景状态（expected / permission_keyword / api_flat / privacytrace）

| 场景 | expected | permission_keyword | api_flat | privacytrace |
| --- | --- | --- | --- | --- |
| C01 | INSUFFICIENT_EVIDENCE | EXACT_MATCH ✗ | INSUFFICIENT_EVIDENCE ✓ | INSUFFICIENT_EVIDENCE ✓ |
| C02 | EXACT_MATCH | EXACT_MATCH ✓ | EXACT_MATCH ✓ | EXACT_MATCH ✓ |
| C03 | CATEGORY_MATCH | NOT_DECLARED ✗ | NOT_DECLARED ✗ | CATEGORY_MATCH ✓ |
| C04 | NOT_DECLARED | NOT_DECLARED ✓ | NOT_DECLARED ✓ | NOT_DECLARED ✓ |
| C05 | AMBIGUOUS_DISCLOSURE | EXACT_MATCH ✗ | EXACT_MATCH ✗ | AMBIGUOUS_DISCLOSURE ✓ |
| C06 | INSUFFICIENT_EVIDENCE | NOT_DECLARED ✗ | NOT_DECLARED ✗ | INSUFFICIENT_EVIDENCE ✓ |

### 4.3 pt907 每场景状态（expected / permission_keyword / api_flat / privacytrace）

| 场景 | expected | permission_keyword | api_flat | privacytrace |
| --- | --- | --- | --- | --- |
| C01 | INSUFFICIENT_EVIDENCE | EXACT_MATCH ✗ | INSUFFICIENT_EVIDENCE ✓ | INSUFFICIENT_EVIDENCE ✓ |
| C02 | EXACT_MATCH | EXACT_MATCH ✓ | EXACT_MATCH ✓ | EXACT_MATCH ✓ |
| C03 | CATEGORY_MATCH | NOT_DECLARED ✗ | NOT_DECLARED ✗ | CATEGORY_MATCH ✓ |
| C04 | NOT_DECLARED | NOT_DECLARED ✓ | NOT_DECLARED ✓ | NOT_DECLARED ✓ |
| C05 | AMBIGUOUS_DISCLOSURE | EXACT_MATCH ✗ | EXACT_MATCH ✗ | AMBIGUOUS_DISCLOSURE ✓ |
| C06 | INSUFFICIENT_EVIDENCE | NOT_DECLARED ✗ | NOT_DECLARED ✗ | INSUFFICIENT_EVIDENCE ✓ |
| C07 | AMBIGUOUS_DISCLOSURE | EXACT_MATCH ✗ | EXACT_MATCH ✗ | AMBIGUOUS_DISCLOSURE ✓ |
| C08 | AMBIGUOUS_DISCLOSURE | EXACT_MATCH ✗ | EXACT_MATCH ✗ | AMBIGUOUS_DISCLOSURE ✓ |
| C09 | AMBIGUOUS_DISCLOSURE | EXACT_MATCH ✗ | EXACT_MATCH ✗ | AMBIGUOUS_DISCLOSURE ✓ |
| C10 | INSUFFICIENT_EVIDENCE | NOT_DECLARED ✗ | NOT_DECLARED ✗ | INSUFFICIENT_EVIDENCE ✓ |
| C11 | EXACT_MATCH | NOT_DECLARED ✗ | NOT_DECLARED ✗ | EXACT_MATCH ✓ |
| C12 | EXACT_MATCH | **null（未预测）** ✗ | EXACT_MATCH ✓ | EXACT_MATCH ✓ |

### 4.4 浏览器、断网回放与失败项

- **spec30 浏览器**（`browser-proof/browser-proof.json`）：Chromium `151.0.7922.34`，8 项检查全通过（C02 字节码/原句/完整政策下钻；C06 谨慎结果与来源切换；合成/受控来源分离；2000 条候选分页与 390px 无横向溢出；409 重试；取消请求与延迟旧响应；持久化 CANCELLED；离线六来源查看），`page_errors=[]`。
- **spec30 独立断网回放**（`offline-proof/offline-proof.json`）：`passed=true`、`external_network_blocked=true`、`interfaces=["lo"]`、`six_reports_http=true`、`real_browser_vue_loaded=true`、`page_errors=[]`、`playwright_version=1.62.1`、测试镜像 `sha256:5d6bd62b1edd363f60daf7995f62531d314dc7623c120fd941226ba7690e9c20`、包 manifest SHA256 `31aed62e2a537933957d6d0dbc71c27f66aa635b5e2cf8a98179e4ab2075573f`。断网容器只剩 loopback，外网连接（1.1.1.1:443）被拒，**允许的外部请求数 = 0**；6 份报告全部经 HTTP 读取成功。
- **pt907 浏览器**（`browser-proof/browser-proof.json`）：Chromium `151.0.7922.34`，12/12 场景 `state=SUCCEEDED`，`scenario_count=12`，`page_errors=[]`；每场景含 HTTP 报告哈希、代码定位与政策原句校验；脚本不包含独立断网回放阶段（CI 矩阵同样只要求 12 场景 + 浏览器证据）。
- **失败项**：两个 suite 均无执行失败、无崩溃、无 `page_errors`。spec30 的失败项只有名义方案的状态不一致（permission_keyword C01/C03/C05/C06；api_flat C03/C05/C06），是实验基线应有的结果；pt907 的 `permission_keyword C12` 未给出目标预测（`actual=null`，`analysis_status=SUCCEEDED`，`errors=[]`），按既有计数规则记 `failures=1 / missing_target_predictions=1`，属名义基线限制，不指向产品引擎。产品引擎（privacytrace）在 spec30 为 6/6、pt907 为 12/12。

## 5. 首次失败与不覆盖的证据（全部保留）

| 运行 | 基线 / 宿主 | 输出目录 | 开始→结束 UTC / 耗时 / exit | 状态 | 首个失败证据 |
| --- | --- | --- | --- | --- | --- |
| run1 | `a1a6386` / Windows+WSL Docker | `tmp/e2e/20261023/spec30/` | 00:21:08Z→00:23:03Z / 115.3 s / 1 | **FAILED**（环境） | `worker-build` 退出 1，`WORKER_BUILD_FAILED`：容器内 `uv sync` 拉 `opentelemetry-api==1.45.0` 报 `tunnel error … tcp connect error … deadline has elapsed`。根因：WSL 用户 `~/.docker/config.json` 把不可达 `http://172.20.10.3:7898` 注入每个构建步骤，且容器 FORWARD 链路为 DROP。构建前的 build-a/build-b 与哈希校验（`rebuild-hashes`）均通过，`comparison.json` 18 行 `actual=null` 保留。 |
| run2-aborted | `83a7983` / Windows | `tmp/e2e/20261023/spec30-run2-aborted-20261023T003825Z/` | 约 00:37:14Z 启动、00:38:25Z 中止 | **NOT_RUN**（主动中止） | Lead 修复 Docker 镜像源/重启 dockerd 窗口内按节奏中止，避免卡在 `docker.io` metadata；仅保留 build-a 部分日志，不作结果。 |
| run2 | `83a7983` / Windows | `tmp/e2e/20261023/spec30-run2/` | 00:41:14Z→00:47:23Z / 370.3 s / 1 | **FAILED**（OS 前提） | 12 个 stage 中 11 个退出 0（含 worker-build 189.5 s、six-scenarios 66.1 s、controlled-browser 13.2 s，比较结果与权威运行一致），最后一个 `independent-offline` 0.47 s 失败：`scripts/verify-offline.py:30` 要求 `--browser-runtime` 是 Linux daemon 绝对路径（`startswith("/")`），Windows 下 `playwright.chromium.executablePath()` 返回 `C:\...`，该 suite 在 Windows 宿主上天然无法完成断网回放。非产品行为缺陷；CI 为 ubuntu-latest。 |
| run3-root | `83a7983` / WSL root | `tmp/e2e/20261023/spec30-run3-root-attempt/` | 00:48:47Z→00:49:30Z / 43 s / 1 | **FAILED**（权限前提） | `build-a` 编译容器写 `/output/C01.apk` 报 `PermissionError: [Errno 13] Permission denied`。根因：`controlled_paths.output_user()` 对 uid=0 返回空，编译容器以非 root 用户写 root 拥有的输出目录；迁移到普通用户 `oasis` 后重跑。非产品行为缺陷。 |
| run3 | `83a7983` / WSL `oasis` | `tmp/e2e/20261023/spec30-run3/` | 00:52:03Z→00:55:06Z / 183 s / 0 | **PASSED** | —（权威结果） |
| pt907 | `83a7983` / WSL `oasis` | `tmp/e2e/20261023/pt907/` | 00:55:38Z→00:59:05Z / 207 s / 0 | **PASSED** | —（该 suite 首次执行即通过） |

## 6. 未覆盖边界与限制

1. 两个 suite 覆盖的是**自建受控源码场景**（6 个、12 个）与对应自建政策；没有留出集、没有统计泛化、没有 P/R/F1，也不对真实应用或「是否实际采集/是否违法」做结论。静态调用只是潜在线索。
2. 权威结果来自 WSL Linux 等价环境；**Windows 宿主无法完成 spec30 的 `independent-offline`**（`verify-offline.py:30` 的 OS 前提）。Windows 上 11/12 stage 通过的结果只作为辅助证据，不把 Windows 口径当作 suite PASSED。
3. pt907 按 CI 矩阵**没有独立断网回放阶段**，因此「离线外部请求数」只在 spec30 有实测字段（0）。pt907 的浏览器证据不包含离线包审查。
4. 本地 venv Python 为 WSL 系统 `3.12.3`，与 CI runner 的 python3.12.x 补丁版本或 worker 容器的 `3.12.13-slim` 不完全相同；不改变锁定依赖集与受控构建工具链。
5. 执行时宿主并非空闲：同一 Docker daemon 上还有约 24 个其他 lane 的容器在运行，耗时不是性能基准，CPU/峰值内存未测量（comparison 中保留 null）。
6. Docker 标签 `privacytrace-controlled-builder:1`、`privacytrace-worker:s1` 与其他 lane 共用，之后可能被重新打标签；run 时镜像 ID 以 `build-a.log` 记录为准（spec30 `sha256:ace7000253c8299fb09fd61e02c26ad5f0247baa9bfae5ebd934e9c5641352d7`，pt907 `sha256:023c45a94a230df63a2a479232ac92a2faf273cce2d69d685a9e0007bc723b61`）。
7. 本轮不合并、不 push、不改产品代码；证据保存在忽略目录，不随 Git 提交。

## 7. 证据路径与 SHA256（本机，`tmp/` 不进 Git）

spec30 权威运行 `tmp/e2e/20261023/spec30-run3/`（121 个文件，22,962,668 字节）：

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `run.log` | 1,149 | `1d9179fd56853a2c1487e380c3b1f5f9045eefcd8da4cfcaa14ca0bd60c73bf4` |
| `integration-receipt.json` | 2,258 | `e0dfa9217b081167e0ff9eb61f1c8d6198e134d7370c43d20d358e978ae5737d` |
| `evaluation/comparison.json` | 63,545 | `b2f58270ff6f509a94329fb5b0ee78e5945e2819d636f9e44b5f167c2de26e40` |
| `evaluation/location-reference-check.json` | 1,661 | `c27a49345e946ef99d983bf6cae9c86654a5f3e443f0b3d4b23a1d53cc725a6e` |
| `browser-proof/browser-proof.json` | 1,009 | `7b60387006061c40e805cbce0cb3b9f11ea846e92f7a46b370ad6aab3e61bee4` |
| `offline-proof/offline-proof.json` | 1,192 | `f2659a576467999d47473aaef6b3a5e182bc534d6a910b9904b6680a5e54f3ad` |
| `build-a/build-receipt.json` | 2,925 | `4755b9667c50a18b99713cf1fdf515b6bc5fae3491b907d290e153ad385104f7` |
| `build-b/build-receipt.json` | 2,925 | `4755b9667c50a18b99713cf1fdf515b6bc5fae3491b907d290e153ad385104f7` |
| `offline/manifest.json` | 2,631 | `31aed62e2a537933957d6d0dbc71c27f66aa635b5e2cf8a98179e4ab2075573f` |
| `independent-offline.log` | 7,857 | `2b267c6c7f1ba865a222378f8257c735363f10811535849889480cadfaee583d` |
| `controlled-browser.log` | 744 | `6f654581c80d78e80e3ec68b1fb921eae716315884667f80efff535832cbdc9b` |
| `six-scenarios.log` | 609 | `5eded2793864d44ae55c62e1e10612cb9912684d597bc73270c049d768ab8016` |

pt907 权威运行 `tmp/e2e/20261023/pt907/`：

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `run.log` | 989 | `384e64075d8a9b966e5b8779c85e6b2132080a274f219533c0436cd09796ff7e` |
| `integration-receipt.json` | 1,812 | `4e9212fb50f5a75fe7fdc9c6d542baa33b2a7eef12c0bac9c8be39d010b782c3` |
| `evaluation/comparison.json` | 116,019 | `2501911a27e5fb845116dd3ce50f2403ebcf0ab7cefa5648e3ee0d584116d186` |
| `evaluation/location-reference-check.json` | 3,030 | `73b0ea197a0fca8a6a047e59e6e90a05f87be68d74d697bf06f1b3bffdf5e439` |
| `browser-proof/browser-proof.json` | 6,094 | `c11df7bd0e16e733c68bd6cc8ec75b483b8d111a67ca5505f65fbba9fab9ba0d` |
| `build-a/build-receipt.json` | 4,671 | `49cae8c567143def4b08ad581f7e6cb801d6279f655bf771f2d2ffc584a13f7f` |
| `build-b/build-receipt.json` | 4,671 | `49cae8c567143def4b08ad581f7e6cb801d6279f655bf771f2d2ffc584a13f7f` |
| `controlled-browser.log` | 52 | `a80b1d63cdba5a5dec58a82ab1b809f0e71d2bdafac863d2b92827f84391e196` |
| `twelve-scenarios.log` | 611 | `8aa66b57cfb4831cd1f3052737df2c60da998d39b8f84783d22e9b613929552e` |
| `worker-build.log` | 2,627 | `0d89a12f42dec83875e1f67e38835ec2fd4cc171086f78500cb3d8dcb0139f23` |

失败与中止运行的证据（保留，不覆盖）：

| 运行 | 文件 | SHA256 |
| --- | --- | --- |
| run1（a1a6386） | `tmp/e2e/20261023/spec30/worker-build.log` | `0f37c53ebea720aaf9dbbd4ff546afb5dc7c7d04fee11953a8d4e1c875eb15dc` |
| run1 | `tmp/e2e/20261023/spec30/integration-receipt.json` | `91d0aef71bcf759be06488972ec925e9b35a1f42f1388bf5113c280c421b2e2a` |
| run1 | `tmp/e2e/20261023/spec30/run.log` | `84627c3c6f8480a054f09c310fc2e43992de903233c0121851eb84a3295a24d0` |
| run2（Windows） | `tmp/e2e/20261023/spec30-run2/independent-offline.log` | `b932b2932712e08b3ca8111cfadc3a193e57dec2e92a9a0fb7552001836e603d` |
| run2 | `tmp/e2e/20261023/spec30-run2/integration-receipt.json` | `af955288568f1fa3905ae1c06f8efd83b254818623527d7013de750418a710d1` |
| run2 | `tmp/e2e/20261023/spec30-run2/run.log` | `0e877dd7311ed2c8a6eb22f864497976b47c0bb52bfc271bb59b17b6700d1d2a` |
| run3-root | `tmp/e2e/20261023/spec30-run3-root-attempt/run.log` | `3de7e41ad3deb6376e716859c1edc300cf6d074d34e4fd6a59a5b1f75d1cf6d6` |
| run3-root | `tmp/e2e/20261023/spec30-run3-root-attempt/build-a.log` | `59daf89a0e1bf240c4d5f079c0537048a58cefc346804727d1d2dccfbc8c9f54` |
| run2-aborted | `tmp/e2e/20261023/spec30-run2-aborted-20261023T003825Z/build-a.log` | `304e07c64de12ab408d5c5dadfbe4fa5a1084c01e15afb76e560aa9017fab889` |

环境与命令的旁证：`tmp/spec30-browser/install.log`（Playwright 安装）、`tmp/spec30-browser/wsl-setup.log`（clone、Node 24.17.0、uv、Chromium 安装）、`tmp/spec30-browser/wsl-user-migration.log`（root→oasis 迁移与 uv sync）、`tmp/spec30-browser/*-wsl.meta.json`（基线 SHA、命令、UTC 起止、耗时、退出码）。

## 8. 附：与历史记录的对照

- spec30 的三方案一致数与失败/弃判数（2/6、3/6、6/6；failures 0；abstentions 0/1/2）与 [spec30 验证记录](../stages/spec30-verification.md) 的 10/11 结果一致；本次额外在 `83a7983` 上重新执行了源码两次构建、隔离扫描、CLI/HTTP、浏览器与独立断网回放。
- pt907 的 12 场景在 README 中定义为独立评测版本（C01–C06 复用、C07–C12 新增），本轮首次在 `83a7983` 上实际跑通完整验收；C12 的 `permission_keyword` 未预测已在 4.4 说明，不当作产品失败。
