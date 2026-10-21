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
- **处理状态**：已复现、已定位；本轮验收不修改产品源码（需另开分支按 owner 规则交付修复与回归）
- **验收影响**：H01/H04/H07/H10 记为 FAILED，其余组合继续；不得以“R1–R6 全绿”替代该失败
