# 验收 H 最终本机执行记录（R01 / R02 / R03 / R04）

- **票**：#136（父票 #128，`[验收 H][PT-MOB-301] 仓库/Web 回归、冻结版本与交付包冷启动`）
- **执行**：父票协调会话接管，2026-10-22（UTC 2026-10-21 17:33 起）
- **被测源码**：`65b49f7ffecd8aee5eede21d69b310300dd32ca6`（D #161 / G #153 合并后的 main）
- **证据目录**：`docs/acceptance/issue136/evidence/final-65b49f7/`
- **执行机**：WSL2 Ubuntu 24.04（内核 6.18.33.2-microsoft-standard-WSL2），Docker 29.7.2 / Compose v5.5.0，8 vCPU，16 GiB，磁盘可用 921 GB，Python 3.12.3，Node 24.20.0，uv 0.11.23

## 1. 结论

| 案例 | 结论 | 关键实测 |
| --- | --- | --- |
| R01 仓库检查 | **PASSED** | `CI=true bash scripts/check.sh` 退出码 0，`PrivacyTrace checks passed.`；1578 passed / 179 skipped（pytest），65 passed（e2e），Web 单测 111 pass，`vue-tsc` + `vite build` 成功；实际启用 Docker 扫描用例 |
| R02 Spec30 六场景 | **PASSED** | `--suite spec30`：`passed=true`，`scenario_count=6`，12 个 stage 全部 exit 0，含受控镜像构建、六场景对比、浏览器证据与独立离线回放 |
| R02 Spec30 十二场景 | **PASSED** | `--suite pt907`：`passed=true`，`scenario_count=12`，9 个 stage 全部 exit 0，含十二受控场景与浏览器证据 |
| R03 四入口 | **PASSED（4/4）** | `acceptance:browser` PASSED（回执锚定 `65b49f7`）；`acceptance:frontend` PASSED（10 项真实 HTTP/UI 检查）；`acceptance:live` PASSED（LOCAL_HTTP_FIXTURES_WITH_TEST_DNS_TARGET，真实受限 Docker 扫描）；`acceptance:mobile` PASSED（开发走查，mock 原生桥，无 APK 扫描） |
| R04 部署专项 | **PASSED** | `bash deploy/check_acceptance.sh` 退出码 0；最终收据 `ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER`，**40 pass / 0 fail / 0 skip**（R1 1 / R2 13 / R3 1 / R4 12 / R5 4 / R6 9），`pass_rate_of_verified=1.0`；唯一豁免为既有 `dedicated-scan-host-verification`（`blocks_this_acceptance=false`） |
| 交付包运行 / 停启 | **BLOCKED** | 票面记录的 64,261,830 B 候选包（SHA-256 `6ba1fbde…`）在本机不可定位：按精确字节数在 D:、C:、WSL 全盘搜索无结果；仓库 `data/deliveries/s3-internal-20261019/PrivacyTrace-S3-internal-20261019.zip` 为 43,890,746 B 的另一产物，不是该候选包。因此「新目录解压 → 安装 APK → 单包/splits 主线 → 停启恢复」未执行，记 BLOCKED，不冒充 PASSED |
| 最终 APK 竖屏证据 | **NOT_RUN** | 无最终候选 APK 与冻结包，未截图；不使用旧 SHA、浏览器模拟或设计图补位 |

## 2. R01 仓库检查

```bash
cd <repo> && CI=true bash scripts/check.sh
```

- 起始/结束：`2026-10-21T17:41:47Z` → `2026-10-21T17:52:18Z`（UTC），退出码 0。
- 摘要：`1578 passed, 179 skipped, 3 warnings in 299.23s`；e2e `65 passed`；Web `111 pass`；`PrivacyTrace checks passed.`。
- 完整日志：[r01/check.log](evidence/final-65b49f7/r01/check.log)。
- 已知假失败说明：`scripts/check.sh` 在本机 Linux/WSL 下可自举（`python3 -m venv`）；Windows Git Bash 侧的历史 `bin/python` 问题未在本轮复现（BUG-136-01 仅在本轮环境记为“未复现”，不改变历史记录）。
- 运行期间仓库内 `evidence/` 下的浏览器截图与 `browser-proof.json` 被 R03 写为已跟踪文件，导致 `git status` 有 11 个已跟踪改动；`apps/`、`scripts/`、`deploy/`、`rules/` 等源码路径无改动（`git diff --stat` 仅 evidence/*）。

## 3. R02 Spec30 六 / 十二

```bash
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py --suite spec30 --output tmp/spec30-ci
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py --suite pt907  --output tmp/spec30-pt907
```

- 六场景：run `20261021T181741Z-b9af7130f56b`，`passed=true`，`commit_sha=65b49f7`；受控工具链归档（build-tools / platform / JDK）经 SHA-256 校验后离线构建；浏览器使用 Playwright 1.62.1 + chromium。
- 十二场景：run `20261021T183141Z-1873ecdffa7a`，`passed=true`，`commit_sha=65b49f7`。
- 两份 `integration-receipt.json` 记录 `dirty_checkout=true`：原因是测试自身写入了 `evidence/` 下已跟踪文件与 `tmp/` 未跟踪目录；源码路径未改。回执同时给出各阶段 `evidence_sha256`。
- 收据：[r02-spec30/](evidence/final-65b49f7/r02-spec30/)、[r02-pt907/](evidence/final-65b49f7/r02-pt907/)。
- 首次尝试曾因网络中断（工具链归档下载被截断、Playwright 1.62.1 未安装）失败；失败过程与修复（改用可续传下载、npmmirror 安装浏览器）在会话记录中，未改写为成功。

## 4. R03 四入口

| 入口 | 命令 | 结果 | 收据 |
| --- | --- | --- | --- |
| browser | `npm run acceptance:browser` | PASSED，`git_commit=65b49f7`，`git_commit_anchored=true` | [r03/browser-proof.json](evidence/final-65b49f7/r03/browser-proof.json) |
| frontend | `npm run acceptance:frontend` | PASSED：前端流程 + 报告流程 12 项移动断言 + policy assist 10 项真实 HTTP/UI 检查 | 运行日志（会话） |
| live | `npm run acceptance:live` | PASSED：LOCAL_HTTP_FIXTURES_WITH_TEST_DNS_TARGET，3 candidates、2 captured policies、保留失败、真实 Docker、刷新任务与存储报告 | [r03/verification.json](evidence/final-65b49f7/r03/verification.json) |
| mobile | `npm run acceptance:mobile` | PASSED：`result=PASS`，生产 Vue + mock 原生桥；无 APK 扫描、无付费模型、无 Android UI 执行 | [r03/walkthrough.json](evidence/final-65b49f7/r03/walkthrough.json) |

首次 `browser`/`frontend` 失败原因为子进程 PATH 中没有 `uv`（执行机自设环境），补 PATH 后复跑通过；`live` 首次失败为容器内 `uvicorn` shebang 指向旧路径，重建 venv 后复跑通过。以上均为执行机环境问题，不是产品缺陷。

## 5. R04 部署专项

```bash
cd <clean-clone> && bash deploy/check_acceptance.sh
```

- 最终运行：`2026-10-21T19:35:25Z` 收据，`source_sha=65b49f7`，退出码 0，`conclusion=ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER`，40/0/0，`pass_rate_of_verified=1.0`。
- 两套彼此独立的 compose 实验室（各含 web/api/worker/dispatcher/gateway/runner/postgres/redis），实际构建 api/web/runner/scanner 镜像，执行 R1–R6（部署、业务闭环、隔离、故障注入恢复、备份恢复、容量与秘密审计）。
- 唯一豁免：`dedicated-scan-host-verification`（独立扫描主机/VM 分离与跨主机防火墙持久化），`blocks_this_acceptance=false`，生产要求不变。
- 首轮运行（`2026-10-21T19:08:08Z`）失败已保留：R1/R3 采集器断言失败、R2 `health=502`、R4 2/10、R5 0/4、R6 5/9。根因为 Docker 客户端 `proxies` 配置被注入容器环境，Caddy 反代 `api:8000` 时走了外部代理导致 502；把内部服务名与私网段加入 `noProxy` 后复跑全绿。这是执行机环境问题，不是产品回归。
- 收据：[r04/](evidence/final-65b49f7/r04/)（含首轮失败与最终成功，均保留原时间与 `source_sha`）。

## 6. 交付包与竖屏证据缺口

- 精确字节数 64,261,830 的候选包在本机不可定位（Windows D:/C: 递归、WSL `/root` `/home` `/tmp` `/opt` 均无命中），GitHub Actions artifacts 中也没有该包（最大 artifact 为 25 MB 的浏览器证据）。
- 因此本记录不重算该包哈希、不声称冷启动/安装/停启通过；历史记录（哈希/条目/CRC/解压）仍只对当时产物成立。
- 最终 APK 竖屏截图组依赖冻结后的实际 APK 与设备；本轮未执行，记 `NOT_RUN`。
- BUG-136-02（包内 `demo.html` 引用不存在的 `fonts/`）仍需在最终打包时修复；因候选包不可定位，本轮未复测。

## 7. 边界

- R03 `mobile` 是开发走查（mock 原生桥），`live` 使用受控二进制夹具与测试 DNS 目标；两者都不替代真机/OEM/公网/外部模型质量结论。
- R01/R02 运行在含测试写入的检出上（`dirty_checkout=true`），源码路径未改；R04 在干净克隆上运行。
- 本记录只证明 `65b49f7` 上的 R01–R04 本机结果，不代表父票 #128 通过，也不替代最终冻结包复测。
