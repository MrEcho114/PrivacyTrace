### 项目当前状态与基线（2026-10-09）

S0 已在 main 合并；S1 整合在 [PR #29](https://github.com/MrEcho114/PrivacyTrace/pull/29)，提交 `c328e812f0d767cbd9baaee2a099489620f26879`，[中央 CI](https://github.com/MrEcho114/PrivacyTrace/actions/runs/37917697368) 已通过。用户要求“撤销复核直接通过”，S1 已按现有技术证据接受，#3 与 #10–15 按该决定关闭，不再要求 A/B 填表。政策仍未人工核验；PR29 尚未合并，main 仍为 d4a685d。

日常工作采用 [TheMasterplan](https://github.com/MrEcho114/PrivacyTrace/blob/c328e812f0d767cbd9baaee2a099489620f26879/docs/workflow.md)：用户提出目标，代理维护验证、PR 和自审，合并/发布单独授权。S2 的受控场景、公平基准和异常浏览器矩阵尚未完成。

本期保底目标仍为 1 个真实国产 App + 6 至 8 个自建受控 APK 场景 + 可溯源报告 + 完整提交包。以下排期/分工保留原计划；10/05 推进记录是历史状态，其双人复核待办已撤销。
---

### 阶段导航与关键时间节点
- [S0 #2](https://github.com/MrEcho114/PrivacyTrace/issues/2) **规范确认与契约改造**（2026-10-03 至 10-04，必做）：核验环境依赖，重构数据契约以支持长文本与原句切片。
- [S1 #3](https://github.com/MrEcho114/PrivacyTrace/issues/3) **单样本端到端跑通**（2026-10-05 至 10-08，必做）：**10/08 止损评估**。必须跑通 1 个真实样本全流程。3 至 5 条发现为预期目标，真实结果偏少则按事实交付，失败如实记录并不虚装通过。
- [S2 #4](https://github.com/MrEcho114/PrivacyTrace/issues/4) **受控场景与基准评测**（2026-10-09 至 10-16，必做）：**10/12 止损评估**。评估并冻结可复现范围，若进度紧张优先舍弃 SDK 与在线大模型，保留证据链与人工复核；保底 6 至 8 个受控 APK 场景可推进至 10/16 完成。
- [S3 #5](https://github.com/MrEcho114/PrivacyTrace/issues/5) **提交包与交付归档**（2026-10-17 至 10-22，必做）：**10/17 代码冻结**。停止增加新功能，全面转入离线运行验证、说明材料整理与审核提交流程。10/23 23:59:59 为官方平台截止时间，校内实际截止时间待确认且通常更早，严禁将 10/23 视作校内截止日。
- [P1 #6](https://github.com/MrEcho114/PrivacyTrace/issues/6) **进阶探索能力**（选做，主线通过后按余力推进）：包含大模型抽取插件、第三方 SDK 特征、样本扩充与赛后动态分析预研，绝不阻塞主线提交流程。

---

### 角色分工说明
- **角色 A（代码）**：负责 APK 清单与 DEX 字节码调用提取、受控测试 APK 编写。
- **角色 B（代码）**：负责数据模型契约、政策解析规范、对照判定规则与后端持久化支持。
- **角色 C（代码）**：负责前端证据下钻展示、复核交互、自动化测试脚本与离线环境验证。
- **角色 D（辅助）**：负责样本与公开政策采集录入、材料与视频模板整理。技术判断与事实核验由 A/B/C 完成。

<!-- privacytrace-plan:2026-10-03:overview -->

### 2026-10-05 历史推进记录与后续计划（不作当前门禁）

| 任务编号 | 本轮输出 | 验证与待办 |
| :--- | :--- | :--- |
| **#10 PT-101 / PT-102** | 补齐 SDK-23 权限及 SDK 适用边界，兼容十六进制版本号 | 自建 AXML/DEX 正负回归通过；等待代码复审 |
| **#13 PT-004** | 同名任务跨进程原子登记 | 四进程抢占与流水线竞态回归通过，重复请求不进入扫描 |
| **#14 PT-807 / #17 PT-808** | 区分真实 `demo` 任务与人工示例，接入前端回归 CI | 六项组件测试及浏览器切换、备注验证通过 |

- **实际验证**：本机后端 215 passed / 7 skipped（Docker 引擎未启动）；前端 6 passed，Ruff、契约零差异、类型检查及构建通过。实现提交 `15e79bb3` 的 [CI run 37319818762](https://github.com/MrEcho114/PrivacyTrace/actions/runs/37319818762) 已通过 api / web / isolated-worker 三项；worker 为 27 passed，与 api 用例重叠，不相加。
- **资料索引**：[修复计划](https://github.com/MrEcho114/PrivacyTrace/blob/codex/s1-hardening/docs/stages/s1-hardening-plan.md)、[技术报告](https://github.com/MrEcho114/PrivacyTrace/blob/codex/s1-hardening/docs/stages/s1-hardening-report.md)、[10/05 开发日志](https://github.com/MrEcho114/PrivacyTrace/blob/codex/s1-hardening/docs/dev-log/2026-10-05.md)。
- **下一步**：10/06 建议复审 #28；10/08 前完成 S1 止损评估和 Issue #15 的 A/B 逐条 comment；随后按 S2 推进 #16、#25、#17，保留 10/12 止损节点。
- **边界**：本轮未重跑 GKD，自动化备注不算人工验收；没有关闭工单或合并 PR。

<!-- privacytrace-progress:2026-10-05:S1-hardening -->
