## 当前基线（2026-10-10）

[PR26](https://github.com/MrEcho114/PrivacyTrace/pull/26)、[PR29](https://github.com/MrEcho114/PrivacyTrace/pull/29)均已合并。main为7e2e018c18a9db4159687b932e0d9b064a8428ec，PR29 head为d410caebd55e7e7ccbbc8d478ee65136bba7ea20，合并于北京时间2026-10-09 20:32:49。

S1#3及#10–15已按用户接受决定关闭，强制A/B评论/签字已撤销。GKD案例的真实扫描/浏览器证据保留原版本绑定，3项结果仍为INSUFFICIENT_EVIDENCE，政策未核验；不是本次重测或合法性结论。

统一验收规范：[#30](https://github.com/MrEcho114/PrivacyTrace/issues/30)；#4是S2阶段索引，执行任务各自引用规范。

## 本期目标

证据可追溯与谨慎降级为主，公平评测支撑，演示顺畅。保底1个既有真实案例+6个独立源码/可重复构建场景，覆盖5类状态；人工准备候选，运行前冻结独立真值。只做本地CLI+浏览器报告，实时扫描与回放分开。

## 阶段

| 阶段 | 任务 | 当前/目标 |
|---|---|---|
| S0 #2 | #7–9 | 子任务closed、PR26merged，父索引同步收尾 |
| S1 #3 | #10–15 | closed、PR29merged |
| S2 #4 | [#31](https://github.com/MrEcho114/PrivacyTrace/issues/31)、#16、#25、#17 | 10/12双场景，10/15六场景/比较/异常 |
| S3 #5 | #18、#19、#20 | 10/16首次离线验收、10/17冻结、材料/正式提交后续 |
| P1 #6 | #21–24 | 本期暂停，不阻塞 |

## 领取顺序

PT-910无open blocker；#17可并行。之后PT-910→#16→#25；#17和#25→#18→#19→#20。阶段索引不当实现工单领取；按native blockers关闭后领取，代理维护验证与记录，不要求用户填复核表。

用户主抓受控输入/公平评测/整合；两位技术队友负责构建和浏览器/离线，具体人及工时未知。用户约8H/日，不推算全队24H/日。辅助成员整理材料，不裁定技术事实。

## 检查点与止损

10/10–12打通C02/C06源码构建→隔离扫描→受控输入→三方案→HTTP/浏览器；10/13–15扩至C01–C06并完成异常矩阵；10/16干净环境真正断网回放；10/17内部代码冻结，之后只修交付阻塞且记录新SHA重验。

10/12未通取消C07/C08并停止非必要修改；若多状态入口仍实质阻塞，重新确认目标，不偷偷减少六场景。工程回归、受控评测、真实案例分别统计，不用测试总数作作品精度。

## 现在核实的风险

- PT-910：JDK/Android SDK/Gradle、构建队友与工时。
- 负责人/#20：校内实际收件日、具体赛道附件规范与资格；不能等最后提交才查。
- 官方主通知仍写全国提交至2026-10-23 23:59:59；10/20–22只是暂定提前窗口，10/17是内部冻结日。[官方通知](https://admin1.cmit.cn/html/tongzhigonggao/show-144-45826-1.html)
- 本机旧工作区先保护原改动，在最新main基线实施；不能把旧脚本/未跟踪资料整体混入新任务。

不做LLM自动抽取主线、SDK/动态分析、上传或多人公网。实际输入/政策/私有路径不公开；合并、Release、部署与正式提交各按授权边界。

## 历史推进记录

下列旧记录保留原文，用于追溯当时版本与验证；其中未合并、A/B复核待办、未来排期均已被上面的当前状态替代。

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

<!-- privacytrace-plan:2026-10-10:overview -->
