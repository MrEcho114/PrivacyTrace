# CI 时间预算与 PR 门禁矩阵

PR 的等待时间由**最长的那条 workflow** 决定，不是所有 workflow 相加。改任何门禁
之前先看这一页，否则容易优化错对象：把 4 分钟的门禁压到 3 分钟，PR 一秒都不会变快。

## 1. 基线（2026-10-23 实测）

同一次 push 触发的五个 workflow，真实 job 墙钟：

| workflow | 墙钟 | 主要成本 |
| --- | --- | --- |
| Deployment Acceptance | **9m48s** | 单个步骤 `deploy/check_acceptance.sh` 占 9m37s |
| Spec30 Integration | 7m04s | 六个场景 + 断网回放 274s，装环境 130s |
| Check | 4m43s | `apps/api/tests` 3m19s（1758 passed / 178 skipped），其余约 64s |
| Browser Acceptance | 3m17s | Chromium + 7 段浏览器验收 |
| Deployment Baseline | 3m01s | 构建 api/web 镜像 + 配置与合成冒烟 |

五个并行跑，整批从创建到结束 **9m51s** —— 也就是所有人感知到的"CI 很慢"。

## 2. 长板归因（Deployment Acceptance，按 receipt 时间戳）

| 阶段 | 耗时 | 说明 |
| --- | --- | --- |
| 镜像构建 5 次 | 55s | api / web / runner / scanner / 回滚基线 |
| 两次 `provision up` | 48s | 两份 owned 实例 |
| R1 + R2 | 23s | 部署 + 业务闭环 |
| R2 清理的限流冷却 | 61s | **承重**：给 R2 自己的 33 个请求留 60/min 窗口 |
| R3 | 1s | 隔离 |
| R4 | 164s | 故障恢复，`oom_and_timeout` 单项 78s |
| R5 | 134s | 备份恢复与回滚，`credential_rotation` 49s |
| R6 | 84s | 容量与凭据审计 |
| 写 receipt | 5s | |

R2→R3 有数据依赖（R3 读 R2 写进 Runner ledger 的两次扫描），R4/R5/R6 都在动同一套
实验室（重启服务、转凭据、换 volume、停 worker），**只能串行**。这 9 分钟没有水分。

## 3. 当前矩阵（`pull_request` 触发）

`main` 的 push 一律不过滤，合入后仍然产出全量证据；PR 上按改动路径选择门禁。
下表是路径矩阵与并行改造后的**单次实测**（PR #304，五条门禁全部触发的那一类）：

| PR 改动 | 会跑的 workflow | 墙钟 |
| --- | --- | --- |
| 只有文档 | Check + Deployment Baseline | 约 3m30 |
| `apps/mobile/**` | 上面 + Browser Acceptance | 约 3m30 |
| `apps/web/**` | 上面 + Spec30 Integration | 约 3m30 |
| `apps/api/**` | 上面 + Deployment Acceptance | 约 6m00 |
| `deploy/**`、Dockerfile | 上面 + Deployment Acceptance | 约 6m00 |

同一批（PR #304，09:31:21 创建、09:37:20 结束，**5m59s**，改造前 9m51s）：

| workflow | 改造后 | 改造前 |
| --- | --- | --- |
| Deployment Acceptance | 5m59s（R1–R4 job 5m56s + R5–R6 job 4m53s 并行，27 + 13 = 40 项全 PASS） | 9m48s |
| Spec30 Integration | 3m04s | 7m04s |
| Deployment Baseline | 3m32s | 3m01s |
| Check | 2m57s | 4m43s |
| Browser Acceptance | 2m33s | 3m17s |

单次样本受 runner 负载影响（Spec30 基线那次 7m04s、这次 3m04s），不要把某一列
当成稳态；要判断改动是否有效，看同一批里最长的那个 workflow。

路径清单写在各 workflow 的 `on.pull_request.paths` 里，改之前先确认那条门禁真的
不读你要排除的目录（例如 `scripts/verify-*.cjs` 会读 `docs/design/**` 与
`docs/acceptance/165/**`，所以 Browser Acceptance 没有排除文档）。

## 4. 两处并行

- **Deployment Acceptance 拆成两个 job**：R1–R4 与 R5–R6 之间没有数据依赖，并行后
  实测 5m59s（原单步 9m37s / workflow 9m48s），代价是 CI 总分钟数约 +11%，以及证据
  从一个 receipt 变成两个（`issue81-r1-r4` / `issue81-r5-r6`，两份 artifact 必须同时
  存在才算完整）。`deploy/check_acceptance.sh` 的默认阶段仍是 `all`，本地与手动复现
  照旧一条命令。
- **`apps/api/tests` 用 pytest-xdist**：1936 个用例的 89% 时间在 test body（不是
  fixture），没有可抽的热点，唯一证据中立的杠杆是跨进程并行。`--dist loadfile` 保证
  同文件同 worker；`PRIVACYTRACE_PYTEST_WORKERS=0` 回串行，给数字则固定 worker 数。
  Check 从 4m43s 降到 2m57s。

## 5. 强制全跑

三条重型门禁都保留 `workflow_dispatch`：在 Actions 里手动选分支运行即可跳过路径
过滤。改了共享接口、想提前拿到全量证据时用它，不要为了这个去改 `paths`。

## 6. 注意事项

- 仓库当前**没有 required status checks**（`rulesets` 为空，`branches/main/protection`
  返回 404）。如果以后启用分支保护，被路径过滤掉的 workflow 不会产生状态，永远
  pending —— 那时要么把矩阵改成 job 级 `if`，要么接受这些门禁不设为必需项。
- 门禁被跳过时 PR 上不会出现该检查，不要误读成"通过了"。
