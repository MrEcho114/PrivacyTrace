# PT 任务清单

来源：简报第 20–22 页。下方 Epic 表保留建仓时的任务分解；当前排期以 [GitHub 总计划 #1](https://github.com/MrEcho114/PrivacyTrace/issues/1) 与阶段计划为准，部分后续工单编号含义已有调整，不按编号强行合并。“已实现”不等于真实样本最终验收通过。

## 2026-10-09 当前交付索引

PR #27 与 #28 的增量已在独立分支整合，面向已合并 S0 的 `main`；两条来源 PR 保持原状态，未自动关闭或合并。最新代码/冲突取舍与验证见 [整合报告](stages/s1-integration-report-20261009.md)，下方 10/05 排期表是历史快照，不覆盖本节。

- S1 仍为 Draft / `PENDING_HUMAN_AB`，最终版本须重新绑定 A/B comment。
- 保留 APK 默认退出删除、1 GiB 累计配额、主/清理错误链及 DEX/有限行为识别边界；补齐 versionCode 范围与同名双权限 SDK 条件证据。
- S2 待办保留 #17 的异常浏览器矩阵，并加入来源值严格校验/新来源类型的契约测试、进程强制退出后的陈旧非终态作业识别与恢复测试。这两项是 #28 的非阻塞建议，本轮不设计完整调度器。
- 当前优先：新整合版本的代码复核 → Issue #15 双人人工核验 → S2 受控场景和公平基准。历史预约日期不代表任务已完成。

## 2026-10-05 当前进度与优先顺序

| 阶段 / 任务 | 当前状态 | 下一步 |
| :--- | :--- | :--- |
| S0 / PR #26 | 已合并至 main（`d4a685d`） | 保留既有契约与规则边界 |
| S1 / PR #27 | 隔离解析、政策摄取、本地 JSON 作业、报告界面已实现；Draft / `PENDING_HUMAN_AB` | 完成本轮缺陷修复复审及 A/B comment |
| PT-101 / PT-102 / #10 | SDK-23 权限与十六进制版本号修复，回归通过 | 复审条件定位与容器 CI |
| PT-004 / #13 | 跨进程原子登记修复，四进程抢占测试通过 | 核验同名任务在扫描前拒绝 |
| PT-807 / #14、PT-808 / #17 | 示例与真实任务来源隔离；前端回归接入 CI | 完整异常流程测试仍属 S2 |
| S2 / #16、#25、#17 | 受控场景、基准评测与完整异常回归仍待实施 | 10/09–10/16；10/12 止损评估 |

当前优先：S1 四项修复复审 → A/B 真实样本核验 → S2 受控场景与基准评测。具体任务、输入输出和验收见 [S1 修复与交接计划](stages/s1-hardening-plan.md)。历史表中的“待开发”不覆盖本节的最新状态。

## Epic 0 · 项目骨架 · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-001 | Repository / Monorepo | 本地骨架与 GitHub 公开仓库 PrivacyTrace 就绪 |
| PT-002 | Backend 基础项目 | 骨架已实现 |
| PT-003 | Frontend 基础项目 | 骨架已实现 |
| PT-004 | Database Schema | SQL 基线；持久化待实现 |
| PT-005 | AnalysisJob 数据结构 | 类型基线；调度待实现 |
| PT-006 | Sample App 管理 | 登记模板 |

## Epic 1 · APK 基础分析 · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-101 | APK Metadata | 待开发 |
| PT-102 | packageName / versionCode / versionName | 待开发 |
| PT-103 | SHA-256 | 待开发 |
| PT-104 | Manifest 提取 | 待开发 |
| PT-105 | Permission 解析 | 待开发 |
| PT-106 | Component 解析 | 待开发 |
| PT-107 | Error Handling | 待开发 |

## Epic 2 · Privacy Taxonomy · 内核

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-201 | 一级类别 | 初版展示分类 |
| PT-202 | 二级数据类型 | 初版层级 |
| PT-203 | Permission → DataType | 部分映射 seed |
| PT-204 | API → DataType | 单条示例；Scanner 待实现 |
| PT-205 | Policy Phrase → DataType | 短语 seed；抽取待实现 |
| PT-206 | Ruleset Versioning | 初版规则版本 |

## Epic 3 · Sensitive API Scanner · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-301 | DEX / 反编译结果读取 | 待开发 |
| PT-302 | Sensitive API Ruleset | 待开发 |
| PT-303 | API 调用位置提取 | 待开发 |
| PT-304 | Class / Method 信息 | 待开发 |
| PT-305 | DataType Mapping | 待开发 |
| PT-306 | Evidence JSON | 待开发 |

## Epic 4 · SDK Detection · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-401 | SDK Signature Schema | 合成 signature seed |
| PT-402 | 常见 SDK Signature | 待开发 |
| PT-403 | SDK Detection | 待开发 |
| PT-404 | SDK → Vendor | 待开发 |
| PT-405 | SDK → Potential DataType | 待开发 |
| PT-406 | SDK Evidence | 待开发 |

## Epic 5 · Policy Pipeline · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-501 | PolicyDocument Schema | 类型基线 |
| PT-502 | Policy Source Type | 四类来源模型 |
| PT-503 | Snapshot | 合成快照校验 |
| PT-504 | Policy Hash | 快照哈希校验 |
| PT-505 | 文本切分 | 待开发 |
| PT-506 | LLM Structure Extraction | 待开发 |
| PT-507 | DataType Normalization | 待开发 |
| PT-508 | Purpose Extraction | 待开发 |
| PT-509 | Recipient Extraction | 待开发 |
| PT-510 | Policy Sentence Evidence | 原句与文档引用校验 |

## Epic 6 · Policy Ambiguity Rules · 内核

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-601 | DataType Specificity | 待开发 |
| PT-602 | Purpose Specificity | 待开发 |
| PT-603 | Recipient Specificity | 待开发 |
| PT-604 | Catch-all Clause | 待开发 |
| PT-605 | Category vs Exact Match | 初版规则 |
| PT-606 | POLICY_SOURCE_CONFLICT | 初版规则 |

## Epic 7 · Consistency Engine · 内核

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-701 | EXACT_MATCH | 初版纯规则/解释；真实样本待核验 |
| PT-702 | CATEGORY_MATCH | 初版纯规则/解释；真实样本待核验 |
| PT-703 | NOT_DECLARED | 初版纯规则/解释；真实样本待核验 |
| PT-704 | Policy Source Conflict | 初版纯规则/解释；真实样本待核验 |
| PT-705 | Ambiguous Disclosure | 初版纯规则/解释；真实样本待核验 |
| PT-706 | Insufficient Evidence | 初版纯规则/解释；真实样本待核验 |
| PT-707 | Evidence Status | 初版纯规则/解释；真实样本待核验 |
| PT-708 | Explanation Generator | 初版纯规则/解释；真实样本待核验 |

## Epic 8 · 普通用户报告 · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-801 | App Report 首页 | 合成报告骨架；真实样本待接入 |
| PT-802 | Privacy Consistency Matrix | 合成报告骨架；真实样本待接入 |
| PT-803 | DataType Detail | 合成报告骨架；真实样本待接入 |
| PT-804 | Issue Detail | 合成报告骨架；真实样本待接入 |
| PT-805 | Policy Explanation | 合成报告骨架；真实样本待接入 |
| PT-806 | Natural Language Template | 合成报告骨架；真实样本待接入 |
| PT-807 | Evidence Drill-down | 合成报告骨架；真实样本待接入 |

## Epic 9 · Evidence Explorer · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-901 | Manifest Evidence | 合成证据展示 |
| PT-902 | Code / API Evidence | 合成证据展示 |
| PT-903 | SDK Evidence | 合成证据展示 |
| PT-904 | Policy Sentence Evidence | 合成证据展示 |
| PT-905 | Evidence Relationships | 待开发 |
| PT-906 | Timeline / Graph | 待开发 |

## Epic 10 · Controlled Benchmark · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-1001 | Benchmark Test App | 待开发 |
| PT-1002 | Ground Truth Schema | 空模板；未标注 Ground Truth |
| PT-1003 | 20–30 Test Cases | 待开发 |
| PT-1004 | Automated Evaluation | 待开发 |
| PT-1005 | Precision / Recall / F1 | 待开发 |
| PT-1006 | Error Analysis | 待开发 |

## Epic 11 · Real-world Benchmark · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-1101 | 样本选择 | 待开发 |
| PT-1102 | 官方渠道获取 | 待开发 |
| PT-1103 | 版本记录 | 待开发 |
| PT-1104 | Policy 收集 | 待开发 |
| PT-1105 | 系统分析 | 待开发 |
| PT-1106 | 人工复核 | 待开发 |
| PT-1107 | Case Study | 待开发 |

## Epic 12 · 用户实验 · P0

| 编号 | 任务 | 建仓状态 |
|---|---|---|
| PT-1201 | 测试问题设计 | 待开发 |
| PT-1202 | 用户任务设计 | 待开发 |
| PT-1203 | 理解正确率 | 待开发 |
| PT-1204 | 完成时间 | 待开发 |
| PT-1205 | 主观理解度 | 待开发 |
| PT-1206 | 结果分析 | 待开发 |

## P1 · Dynamic Analysis · 暂缓

| 编号 | 任务 | 状态 |
|---|---|---|
| PT-D01 | 标准 Android 模拟器 | 暂缓；静态真实闭环完成后再评估 |
| PT-D02 | Sensitive API Hook | 暂缓；静态真实闭环完成后再评估 |
| PT-D03 | Network Capture | 暂缓；静态真实闭环完成后再评估 |
| PT-D04 | RAW_MATCH | 暂缓；静态真实闭环完成后再评估 |
| PT-D05 | TRANSFORM_MATCH | 暂缓；静态真实闭环完成后再评估 |
| PT-D06 | Third-party Endpoint | 暂缓；静态真实闭环完成后再评估 |
| PT-D07 | Dynamic Evidence Model | 暂缓；静态真实闭环完成后再评估 |
| PT-D08 | Static / Dynamic Merge | 暂缓；静态真实闭环完成后再评估 |
