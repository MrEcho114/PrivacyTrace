# Issue #64：review 修订后的评测证据

本报告处理 [PR #76 的两项 P2](https://github.com/MrEcho114/PrivacyTrace/pull/76#pullrequestreview-5543031984)，取代旧版对“政策片段已校验”和“三方案定位 12/12”的指标解读。上一版 [完整归档](../README.md)、收据和逐文件哈希保持原字节，供追溯。场景、原始独立真值、规则及算法状态预测均保持不变。

## 修复与统计口径

- 当前序列化材料经既有 `EvaluationInput` 契约重新校验，检查文档身份、快照 UTF-8 哈希和原句 Unicode 码点区间。`policy_span_validation` 保存实际核对的证据 ID、文档哈希及错误码；失败返回 false、保留 `POLICY_EVIDENCE_INVALID`，门禁拒绝通过。没有增加第二套政策语义判断。
- comparison schema 升为 **2**。`shared_scanner_api_evidence_verified` 检查共享扫描结果是否符合独立真值；`scheme_prediction_evidence_locator_validated` 只核对该方案目标预测实际引用的证据 ID、API 完整描述符、上下文、规则版本、caller、DEX 和 offset。无目标输出、仅引用权限或错误 API 引用不会继承共享扫描的成功数。
- C01 预期没有敏感 invoke，共享扫描核对其缺席；逐方案 API 定位为 **null / N/A**。状态一致率仍以全部 12 项或 6 项为分母，API 定位有独立适用分母 11 或 5。权限基线按设计输出能力线索，其 API 定位 0 不解释为权限定位错误。
- 共享政策材料通过数按报告计数：十二场景 **12/12 份材料**，合计 **10 个实际原句片段**；C04/C06/C10 无候选原句，`checked_evidence_ids=[]`，不声称抽取或目标原句定位成功。原六场景为 **6/6 份材料、4 个原句片段**。每份文档仍检查快照及引用完整性。

## 实际重跑结果

| 场景集 | 方案 | 状态一致 / 全分母 | 共享扫描核对 | 方案引用 API 定位 / 适用数 | API 不适用 |
| --- | --- | ---: | ---: | ---: | ---: |
| 十二场景 | permission_keyword | 2/12 | 12/12 | 0/11 | 1 |
| 十二场景 | api_flat | 4/12 | 12/12 | 11/11 | 1 |
| 十二场景 | privacytrace | 12/12 | 12/12 | 11/11 | 1 |
| 原六场景 | permission_keyword | 2/6 | 6/6 | 0/5 | 1 |
| 原六场景 | api_flat | 3/6 | 6/6 | 5/5 | 1 |
| 原六场景 | privacytrace | 6/6 | 6/6 | 5/5 | 1 |

逐项数据：[十二场景 comparison.json](pt907/evaluation/comparison.json)、[可读比较表](pt907/evaluation/comparison.md)，以及 [原六场景 comparison.json](spec30/evaluation/comparison.json)、[可读比较表](spec30/evaluation/comparison.md)。执行失败、partial、截断均为 0；权限基线在 C12 无目标输出，仍留在全分母。预测文件保留非目标发现和实际引用，无法支撑的对应关系仍保留证据不足状态。

## 验证版本与证据

修订实现提交 **`b933e8e03b3f9363f17db365fa0454543d243351`**，已整合 main `e5124b0`。两套运行均从干净提交开始，收据 `dirty_checkout=false`；后续归档提交只增加本版报告与证据。

- [十二场景收据](pt907/integration-receipt.json)：两次真实构建、12 APK 哈希一致并匹配原锁、36 行比较、**19 项**源码 CLI/HTTP 回归、12 场景真实 Chromium 通过。
- [原六场景收据](spec30/integration-receipt.json)：两次构建、18 行比较、**9 项**源码 CLI/HTTP 回归、浏览器及新容器内独立断网回放通过。断网证明见 [offline-proof.json](spec30/offline-proof/offline-proof.json)。
- 新增 **17 项工程回归**覆盖摘录/offset/document_id/快照篡改、Unicode 码点、无目标、仅 Manifest、错误 API ID/映射/定位和门禁。原缺陷测试先失败，修复后通过；工程回归不计入场景总数。
- 本地权威入口 `PRIVACYTRACE_DOCKER_TESTS=0 bash scripts/check.sh`：API **793 passed / 20 skipped**、Web **46 passed**；治理、Ruff、准备包、schema 零差异、类型与生产构建通过。本机 cgroup v1 的完整 Docker probe 限制仍保留；最终完整 Docker 门禁以 PR 最新交付 SHA 的 CI 为准，不能用本地跳过结果代替。
- [manifest.json](manifest.json) 固定本版归档文件哈希。归档前重新核对两套全部 54 行计分、18 份预测哈希、原句切片、文档哈希、实现与 Git 对象哈希、收据证据哈希。公开材料仅含自建受控数据及允许的证据，不含 APK、job store、完整政策原件、本机路径或原始执行日志。

首次本地重跑遇到旧 builder 对 Dockerfile heredoc 的缓存兼容问题，编译失败后保留全部 36 行失败分母；见 [失败比较](failures/legacy-builder/evaluation/comparison.json) 和 [失败收据](failures/legacy-builder/integration-receipt.json)。改用既有 BuildKit 和任务输出权限后重跑成功，没有改代码、真值或放宽扫描隔离条件。浏览器依赖下载的一次 502 仅作环境准备失败记录，不声称生成了成功验收结果。

十二场景真值 SHA256 仍为 `0beb0e990c27668658c24341978f871082dc53952affcff1b444d7eb864baeb3`；六场景为 `9a0a10392d2d052f95e78c69231c27556120c0eff131a403f05d6f5c8cc10c40`。这仍是自建受控集结果；不推导真实 App 泛化、实际采集或合法性结论，P/R/F1 仍为 N/A，未测成本保持未测。旧报告所列 C11 固定短语词表局限继续适用。
