# PT 任务清单

来源：简报第 20–22 页。全部未分配人员和截止日期。“初版”只说明已有骨架或纯规则实现，不等于真实样本验收通过。

当前优先：真实样本 PT-101~107 → API 证据 PT-301~306 → 政策 PT-501~510 → 真实闭环验收。

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
