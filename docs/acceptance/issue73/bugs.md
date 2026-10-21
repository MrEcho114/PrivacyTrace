# 缺陷记录与汇报

#81 完成并关闭后立即开展本机测试，发现的问题在新的本机运行目录中记录。环境准备不停止，也不把工具安装失败直接称为产品 BUG。当前未执行最终场景，不能据此报告“零 BUG”或最终通过。

每条记录包含：编号、严重程度、类别（产品缺陷／环境问题／测试设施缺口）、被测源码/客户端/镜像版本、关联场景、前置条件、最短复现步骤、预期结果、实际结果、脱敏证据及 SHA256、影响、复现次数和处理状态。未经复现的疑点单列，缺少条件的案例使用 BLOCKED，不计作 BUG 或通过。

报告按影响排序：越权/材料泄露/删除复活优先，其次主流程不可用和错误报告，再到可恢复失败与界面问题。发现高影响问题先停止对应案例、保存证据，避免继续污染结果；独立无风险案例继续执行。修复如涉及其他 owner 的产品文件，先核对交接并串行处理。用户要求汇报 BUG 不等于要求隐瞒已修问题，修复前后证据均保留。

向用户汇报时列出已确认 BUG 的编号、影响、复现摘要、证据和当前状态，并另列环境阻塞/未测范围。原始请求、访问材料、个人 Key、APK 和本机私有路径不得直接发到 GitHub；公开附件逐项脱敏审查。参见[运行模板](run-template.json)的 `bug_refs` 和[场景表](scenarios.md)。

## BUG-01 自动政策发现在交付拓扑下不可用（2026-10-21）

- **编号**：BUG-01
- **严重程度**：高
- **类别**：**产品缺陷**（控制面在隔离部署中调用了本机 Docker 路径）
- **被测版本**：main `aa414073859463abfaa133c1d12ac1f24c93eeb7`；`privacytrace-api:issue81-test`、`privacytrace-runner:issue81-test`
- **关联场景**：H01、H04、H07、H10（自动政策）；客户端“自动准备政策并继续”
- **前置条件**：交付的隔离/持久化拓扑（有 PostgreSQL + Runner，控制面无 Docker socket），真实 Android 客户端或等价访问材料
- **最短复现**：

```text
POST /api/v1/web/drafts                       -> 200
POST /api/v1/web/drafts/{id}/package-set      -> 200   (经 Runner inspect_metadata)
POST /api/v1/web/drafts/{id}/sources/discover -> 503   {"detail":"ISOLATED_INSPECTION_UNAVAILABLE"}
GET  /api/v1/web/drafts/{id}                  -> 200   (revision 不变，无新来源)
```

- **预期结果**：从 APK 元数据发现受控政策 URL 并建立来源（进入抓取/提取），返回 2xx
- **实际结果**：`discover` 返回 503；客户端显示 `SERVER_BUSY`，自动来源为零；同一环境上传路径正常
- **脱敏证据**：`evidence/bug-01-discover-503-default-config.txt`（交付默认配置）、`evidence/bug-01-discover-503-adapted-lab.txt`（移动实验配置）
- **影响**：交付拓扑下移动端“自动政策”主路径不可用；`deploy/acceptance` 的 R1–R6 收集器不调用 `sources/discover`，因此远端 CI 与本地 R1–R6 全绿无法覆盖该缺陷
- **复现次数**：2（两种配置各一次）
- **根因**：`apps/api/src/privacytrace/web_intake.py:1290` 的 `_discover_sources` 直接调用模块级 `inspect_package_isolated`（本机 Docker），而 `DurableWebIntake` 明确要求控制面无 Docker socket，上传路径走的是注入的 `self.runner.inspect_metadata`；`web_api.py` 的 `web_error` 把非输入类 `ScanError` 映射为 503 `ISOLATED_INSPECTION_UNAVAILABLE`
- **处理状态**：**已修复并在本机复验**（2026-10-21 下午）
- **验收影响（首轮）**：H01/H04/H07/H10 记为 FAILED，其余组合继续；不得以“R1–R6 全绿”替代该失败

### 修复记录（2026-10-21 下午）

- **修复分支/提交**：`codex/issue73-discover-inspector-fix` @ `0a3d61e`，Draft PR #127
- **改动**：`WebIntake` 新增 `inspect_metadata(path, *, timeout)`，默认仍走本地受限容器（单机模式行为不变）；`DurableWebIntake` 覆写为 `self.runner.inspect_metadata(...)`；`_discover_sources` 改调 `self.inspect_metadata(...)`，保留原有预算超时；新增 2 个回归测试
- **权威验证**：`bash scripts/check.sh` 在干净 C 盘 worktree 全绿（1516 passed / 200 skipped；ruff、web 111 单测、build 全过）。D 盘 worktree 出现的 2 例 e2e 15s 超时已用 pristine 基线（0 failed）与 C 盘（0 failed）对照，排除与本改动相关
- **API 层复验**：同一实验室实例、同一夹具 APK、同一 `replay-discover.py`，`discover` 由 `503 ISOLATED_INSPECTION_UNAVAILABLE` 变为 `200` 且新增 `Auto Discovered Policy` 来源（`http://1.1.1.1/policy.html`），revision 2→3；随后 `DELETE` 返回 `{"deleted":true,"cleanup_pending":false}`，再读 404。证据：`evidence/bug-01-fixed-discover-200.md`
- **客户端复验**：H01（单 APK + 自动政策）与 H02（单 APK + 网页辅助补入）在真实 Android 客户端上端到端 `SUCCEEDED`，并完成原生“删除远端材料”双确认与服务端删除
- **遗留口径**：实验室未配置服务端模型，自动候选提取产出 0 条，因此两例报告已生成但**不含政策声明对照**；H01/H02 只算“主链路通过”，不算完全通过。H04/H07/H10 仍需在 splits 与第二实例就绪后复验
- **附带修复的环境问题**（非产品缺陷，已持久化）：容器 `NO_PROXY` 缺 `1.1.1.1`（来源是 Docker CLI `proxies.default`）、netns DNAT 回程缺 `10.215.134.0/24` 路由、dockerd 重启后 ACCEPT 被 `DOCKER-FORWARD` 挤压（改写进 `DOCKER-USER`）、容器无默认路由需显式 `/32` 路由；由 `policy-egress.sh` 与 `pt73-policy-egress.service` 幂等保证
