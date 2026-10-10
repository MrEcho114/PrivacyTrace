## Problem Statement

团队需要在 2026-10-17 代码冻结前交付一份可验证的竞赛作品，证明静态证据可追溯、信息不足时能够谨慎降级，而不是堆功能或提前宣称优于基线。

目前已有本地扫描和报告链路，但自建源码的受控评测工程、独立真值、三方案公平比较和独立环境离线交付仍需补齐。真实分析保留未知适用信息，不能仅增加 APK 就声称多状态评测已经成立；工程回归用例数也不能代替评测集规模。

本规范仅综合最近开发路径讨论 Q1–Q11 的已确认决定。

## Solution

交付“人工辅助对照”的受控评测与本地演示闭环：先以“明确对应／证据不足”两个场景跑通，再扩到六个保底场景；同时保留一个真实 App 案例。各方案使用相同材料进行比较，结果不理想也如实呈现。

分析通过本地 CLI 执行，浏览器查看报告。受控评测与真实 App 分开信任边界，实时执行与离线回放明确区分。新增能力集中于受控输入、公平评测、可重复源码构建和可靠交付，不扩张成公网服务或自动政策理解系统。

## User Stories

1. As a team developer, I want controlled APKs built from source, so that the scenarios can be independently rebuilt.
2. As a team developer, I want pinned build dependencies and recorded artifact hashes, so that evaluation inputs can be identified and reproduced.
3. As an evaluator, I want manually prepared policy candidates linked to their original sentences, so that semantic inputs are inspectable rather than presented as automatic extraction.
4. As an evaluator, I want ground truth frozen before execution, so that expected answers cannot be changed to match system outputs.
5. As an evaluator, I want prediction inputs separated from expected answers, so that the evaluated algorithms cannot read their labels.
6. As a team developer, I want a clearly identified controlled evaluation entry point, so that known test facts do not weaken real-app analysis safeguards.
7. As an analyst, I want unknown real-app metadata and unverified policies preserved, so that controlled test assumptions are not applied to real applications.
8. As an evaluator, I want permission-only scenarios distinguished from API invocation evidence, so that capabilities are not described as observed collection.
9. As an evaluator, I want explicit disclosure, category disclosure, missing disclosure, negative statements and incomplete information evaluated separately, so that supported decision boundaries are visible.
10. As an evaluator, I want all three comparison schemes to receive the same materials, so that input advantages do not silently bias the comparison.
11. As an evaluator, I want the API baseline to use the same invocation evidence and complete descriptors, so that it is not deliberately weakened.
12. As an evaluator, I want per-scenario expected and actual results with evidence references, so that errors can be explained rather than hidden behind one score.
13. As an evaluator, I want failures, partial results and abstentions retained, so that coverage is not inflated by removing difficult inputs.
14. As an evaluator, I want counting units and measurable targets declared before execution, so that any metrics have clear denominators.
15. As a competition reviewer, I want conclusions linked to code locations and policy sentences, so that I can inspect their basis.
16. As a competition reviewer, I want uncertainty and analysis limits clearly displayed, so that static clues are not mistaken for collection, illegality or safety findings.
17. As a presenter, I want local CLI analysis and browser report viewing, so that I can demonstrate the complete workflow without building a public service.
18. As a presenter, I want live analysis and offline replay visibly distinguished, so that saved reports are not presented as newly generated results.
19. As a presenter, I want long-text and abnormal-report interactions checked in an actual browser, so that successful API responses do not mask an unusable interface.
20. As a delivery maintainer, I want an offline package verified in an independent or clean environment, so that delivery does not depend on the development machine or an external model key.
21. As a delivery maintainer, I want credentials, private data and unauthorized binaries excluded from distributable materials, so that packaging does not create a new disclosure risk.
22. As a team coordinator, I want a two-scenario checkpoint on October 12 and code freeze on October 17, so that blocked work is identified before the deadline.
23. As a team coordinator, I want experiment reductions explicitly reconfirmed, so that the six-scenario minimum is not silently changed when implementation becomes difficult.
24. As a team coordinator, I want engineering tests, controlled evaluations and the real-app case reported separately, so that overlapping evidence is not double-counted.

## Implementation Decisions

### 范围与模块

- 核心价值为证据可信与谨慎降级，公平评测提供支撑，界面做到演示顺畅。
- 保底为 **1 个真实 App 案例 + 6 个自建受控场景**，余力扩展至 8 个。真实案例可使用已留存的版本绑定材料，但不得冒充本次重新运行或完整真值。
- 三个模块为：APK 源码与可重复构建；受控输入与公平评测；浏览器异常与离线交付。沿用现有隔离扫描、规则引擎、作业报告与浏览器链路。
- 受控工程须保留源码、构建方式、锁定的依赖版本、产物和输入哈希。具体 JDK、SDK、构建工具版本实施时核实，不在本规范臆定。
- 本期政策候选采用人工整理并核对，单列人工工作量；不得声称完成自动政策理解或自动抽取准确率评测。

### 受控输入与真值

- 补充明确标识的受控评测入口，仅自建样本实际核对过的版本、适用范围及政策事实可作为已知输入。
- 与真实 App 分开信任边界，不全局放宽验证，不补造真实样本未知信息，不改写历史报告或原始政策。
- 独立真值在运行前从场景定义及政策原文冻结。候选声明属于输入特征，预期判定属于评测标签；被测方案不读取标签，运行后由评测器比较。
- 具体受控输入格式、CLI 参数及报告契约扩展尚未指定；在上述边界内实现最小适配，不据此设计新调度系统或另一套判定引擎。

### 保底场景与预期

| 场景 | 定义 | 预期判定 |
|---|---|---|
| C01 | 权限能力存在，但没有对应敏感调用 | INSUFFICIENT_EVIDENCE |
| C02 | 调用与明确数据类型声明对应 | EXACT_MATCH |
| C03 | 声明只覆盖上位类别 | CATEGORY_MATCH |
| C04 | 完整核验且适用的政策没有对应声明 | NOT_DECLARED |
| C05 | 否定描述与静态调用同时存在 | AMBIGUOUS_DISCLOSURE，不认定承诺被违反 |
| C06 | 政策或适用信息不完整 | INSUFFICIENT_EVIDENCE |

- 六个场景覆盖 **5 类状态**，不宣称六状态全覆盖。静态调用不代表运行时执行。
- C07 多来源冲突、C08 Multidex 为有余力才开展的扩展场景，不阻塞保底交付。已有工程回归不能代替独立受控场景。
- 场景须有可重复源码构建、配对政策、预期答案及版本/哈希；手工构造二进制 fixture 不替代该交付。

### 公平比较与结果

- 三组方案：权限 + 关键词；同一 API 证据和完整方法描述符 + 扁平匹配；本方案规则对照。
- 各组获得相同政策与证据材料，明示各方案使用的信息；基线不得靠错误描述符或人为删减输入制造劣势。
- 输出逐场景预期/实际、映射与定位核对、误判/弃判、覆盖、失败留痕和耗时。若报告 P/R/F1，先固化可测目标、计数单位和分母口径，零分母记 N/A。
- 不悄悄删除失败、partial 或弃判样本，不预设本方案更优，不将小样本结果宣传为统计代表性或商业 App 全局召回率。

### 展示与交付

- 本地 CLI 执行分析，浏览器查看报告；不新增网页 APK 上传或多人公网服务。
- 实时执行与离线回放分别标识来源及生成时点，回放不能冒充现场扫描。
- 离线交付应在独立或干净环境实际验证，不依赖外部大模型密钥；未经断网运行验证，不称离线验收完成。
- 交付物需核对分发授权，排除凭证、私有数据及未授权二进制；本规范不授权发布、部署或正式提交比赛。

## Testing Decisions

### 高层测试接缝

沿用最近讨论已确认的 **CLI／受控评测 runner → 持久化报告与 HTTP → 实际浏览器** 链路。runner 作为主验收入口组合现有能力；HTTP 报告和浏览器是外部观察点，不新增私有函数测试入口。

- 只验外部行为、产物、状态、证据定位与失败反馈，不以实现细节或直接调用私有状态处理函数作为完成标准。
- 可重复构建验证源码真实生成 APK；扫描必须经过实际隔离入口，不用合成 JSON 代替 APK 端到端评测。
- 最先跑通 C02／C06：验证受控入口能分别产生明确对应和证据不足，并能通过三方案 runner、HTTP 报告及浏览器观察。
- 随后运行 C01–C06，全量保留成功、失败、partial 与弃判记录；输入特征与预期答案不串线。
- 验证受控信息不会迁入真实 App，真实未知信息及未核验状态仍保留。
- 浏览器验证原文/代码下钻、长文本、异常数据、来源切换、取消和失败提示；未测试项不称通过。
- 独立环境实际断网验证离线报告查看，并确认回放标签和生成时点。
- 复用现有 APK CLI、流水线/HTTP、前端组件和浏览器验证经验，运行项目现有权威检查；工程测试、受控评测和真实案例分列，不相加。CI 结果绑定交付版本，不借用旧结果。

### 检查点与完成标准

- **2026-10-10～12**：构建工程及 C02／C06 最小闭环，贯穿实际扫描、受控输入、三方案 runner、HTTP 与浏览器。
- **2026-10-13～15**：扩至六场景，完成实际比较和误差记录，补浏览器异常验证。
- **2026-10-16**：独立/干净环境离线验证及材料事实核对。
- **2026-10-17**：代码冻结，随后只处理交付阻塞问题和材料整理。
- 完成以实际构建、六场景运行、可核对输入/证据、三方案比较、浏览器和独立环境验证为准；规范发布和工程测试数量不代表功能已完成。

**10/12 止损**：最小双场景闭环未通，取消 C07／C08 并停止非必要修改。若多状态评测仍有实质阻塞，重新与用户确认降低实验目标；不能悄悄减少六场景保底、伪造运行或放松真实输入限制。

## Out of Scope

- 实时 LLM 政策抽取、自动政策理解及其准确率实验。
- 动态分析、运行时采集证明、SDK 扩展、高阶代码分析。
- 网页 APK 上传、多人公网服务、完整调度器或新增身份系统。
- 自动给出合法性、安全性、实际采集或商业 App 全局召回率结论。
- 把多来源冲突、Multidex 扩展或六状态全覆盖列为保底。
- 合并、公开 Release、部署、正式参赛提交或无关全局配置修改。

## Further Notes

- 本规范仅以最近 Q1–Q11 已确认的开发路径为需求来源；不从更早对话或旧工单正文继承新增要求。
- 用户本人负责受控输入、公平评测及最终整合；另外两位技术成员分别承接 APK 构建和浏览器/离线交付，具体认领人及日工时仍待落实。
- 目前只确认用户约 8H/日，不按全队 24H/日估算；AI 账号类型不替代开发能力或时间核实。
- 校内真实收件日与具体赛道附件规范仍待核实；10/17 是内部冻结日，不冒充官方截止。
- 现有源码构建环境尚未落实，工具链准备须计入任务，不假装已有完整 Android 工程。
- 本工单是最近已确认范围的统一验收规范，不另建同名执行任务，也不自动关闭或重开已有工单。
- 发布本规范仅表示已确认的需求进入 tracker，不表示实现、测试、交付或外部发布已经完成。

<!-- privacytrace-spec:recent-q1-q11:2026-10-10 -->
