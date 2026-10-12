# 协作落地记录

## 范围与版本

2026-10-12，用户先要求审查重复交叉工作，再显式调用 implement 要求落地。选择为：每个执行任务唯一执行会话、明确交接、先用规则与 Agent 清单。规则权威源为 [协作指南第 6 节](../agents/skills-workflow.md#6-工单流转阻塞依赖与交接规范)；本记录只保存当前业务交付快照及文档场景走查，不复制另一套规则。

来源为 [协作地图](https://github.com/MrEcho114/PrivacyTrace/issues/48) 及其 [交付覆盖问题](https://github.com/MrEcho114/PrivacyTrace/issues/49)、[执行会话问题](https://github.com/MrEcho114/PrivacyTrace/issues/50)、[共享归属问题](https://github.com/MrEcho114/PrivacyTrace/issues/51)、[清单维护问题](https://github.com/MrEcho114/PrivacyTrace/issues/52)。后续执行授权见地图的 [当前执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/48#issuecomment-6116224109)。

本轮只落地指南、指针、模板及当前任务覆盖记录，未修改业务代码、受管 core/state 或自动检查程序。现有业务负责人、原工单/PR 状态与原分支保持不变；合并、正式分发、部署和参赛提交仍需对应授权。

核查 main 基线：`c06803b48cf6d29412b4f118e49272708e11c7ee`。以下为 2026-10-12 快照，任务恢复前须重读 GitHub 最新正文、交接、head 与依赖，不能用这份记录代替当前状态。旧工作区未跟踪资料未导入。

| 交付角色 | 当前 PR/head | 使用方式 |
| --- | --- | --- |
| 双场景来源 | [双场景受控闭环](https://github.com/MrEcho114/PrivacyTrace/pull/37)，`be3230e8ce056b4113460c1fd40340639c891e46` | 来源/评审追溯，不另开实现 |
| 六场景来源 | [六场景与离线验收](https://github.com/MrEcho114/PrivacyTrace/pull/38)，`9a282098e7b960ae0d9dab63dd794e0094b16a77` | 受控主体来源，不整支平行合并 |
| 统一整合 | [主线整合交付](https://github.com/MrEcho114/PrivacyTrace/pull/47)，`0f730b8106b4d2220cafcf8bee23a08b492c4f65` | 受控功能唯一现有评审入口，关联 [整合任务](https://github.com/MrEcho114/PrivacyTrace/issues/39)，负责人 MrEcho114 |
| 部分前端 | [四步示例工作台](https://github.com/MrEcho114/PrivacyTrace/pull/46)，`da17c3b06b968868551b5890fd64bd3acdd2f284` | [完整前端规格](https://github.com/MrEcho114/PrivacyTrace/issues/44) 的示例切片，负责人 OasisViridis |
| 可选插件 | [政策抽取插件](https://github.com/MrEcho114/PrivacyTrace/pull/42)，`01734fdc1ee9cac9ffd087809a9fcf182cda4310` | [模型任务](https://github.com/MrEcho114/PrivacyTrace/issues/21) 的唯一现有候选，前端后续复用，负责人 OasisViridis |
| 材料草稿 | [项目说明草稿](https://github.com/MrEcho114/PrivacyTrace/pull/41)，`42d225deff580f39cb286888f1476893d5f0b7d7` | [说明与演示任务](https://github.com/MrEcho114/PrivacyTrace/issues/19) 的草稿，负责人 Onikamicpj |

所有这些 PR 均未合并。当前关联检查的成功不授予合并权限，也不表示原工单已经完成。既有 Assignee 仅记录现有负责人，不表示其已接受新的执行会话或残余工作；无人负责的缺口先等待指派。

## 原任务验收覆盖与剩余项

以下按原 Issue 验收顺序分组。**已有记录**表示在固定版本交付/代码/自动化证据中可定位；**待核验**表示本轮没有独立重跑或逐项正式验收。对候选覆盖先做验收/补缺口，不重建已有受控工程、runner、比较器或示例界面。

共同证据：

- 固定整合版本的 [逐文件取舍/验收记录](https://github.com/MrEcho114/PrivacyTrace/blob/0f730b8106b4d2220cafcf8bee23a08b492c4f65/docs/stages/issue39-integration.md) 和 [运行说明](https://github.com/MrEcho114/PrivacyTrace/blob/0f730b8106b4d2220cafcf8bee23a08b492c4f65/README.md)。
- 绑定整合 head 的 [Check](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38190815259)、[Spec30 Integration](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38190814790) 和 [Browser Acceptance](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38190814748) 均成功；本轮查证了状态/版本，未重新执行这些业务验收。
- 前端的 [交付范围及验证说明](https://github.com/MrEcho114/PrivacyTrace/pull/46) 与绑定该 head 的 [Check](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38144428763)、[Browser Acceptance](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38144428109)；影片取材时仍须重新核对可运行版本。

| 原任务／验收项 | 已有记录 | 待核验／真正剩余范围 |
| --- | --- | --- |
| [双场景闭环](https://github.com/MrEcho114/PrivacyTrace/issues/31) A1：源码、锁定工具、输入/标签哈希 | 整合版本记录两次源码构建与冻结哈希核对 | 复用该工程；工单最终验收及 main 可用性待整合审阅/合入 |
| 双场景 A2–A4：隔离扫描、标签隔离、HTTP/浏览器 | C02/C06 实际 CLI→持久化 HTTP→Vue；普通入口保留未知/未复核边界 | 受控样本证据不替代真实 APK 泛化；组合前端后重验对应行为 |
| 双场景 A5：环境、失败、工时与版本 | 有版本绑定的专项、错误记录和哈希失配回归 | 人工准备成本未测；正式验收不得补造工时 |
| 双场景 A6：检查点/止损 | 正常受控闭环已有交付 | 不因日期或旧计划重复开发；负责人按当前验收缺口决定排期 |
| [六场景](https://github.com/MrEcho114/PrivacyTrace/issues/16) A1–A2：独立定义、输入/标签与实际运行 | C01–C06 源码、工具链和固定输入；专项记载两次构建、浏览器及回放 | 逐项采用整合证据，未作本轮独立重新验收；保留源文件/标签哈希 |
| 六场景 A3：三方案输出 | 18 行比较，失败/弃判保留 | 复用比较器；正式结果范围由评测任务确认 |
| 六场景 A4–A5：统计边界、版本与回归 | 受控/普通入口区分及对应回归、专项 CI | 不把工程用例算独立场景；不把六场景推广为真实应用代表性 |
| [公平评测](https://github.com/MrEcho114/PrivacyTrace/issues/25) A1–A2：三方案、材料、真值与描述符 | 六场景 18 行，配对材料与冻结标签，保留来源/版本 | 可复用已有输出；最终逐项材料使用/映射审校仍待负责人确认 |
| 评测 A3–A4：分母、可测目标、P/R/F1 | 已报告状态一致数 2/6、3/6、6/6，弃判 0/1/2，正常运行执行失败 0/0/0 | 一致数不等于 P/R/F1；须先明确可测目标与 TP/FP/FN，适用才计算，不适用写 N/A 并解释。现有记录不能支持这些数值 |
| 评测 A5：耗时、资源、人工成本 | 当前交付未提供可用于这些指标的完整实测依据 | 补真实观测及方法，无法补的保留“未测”；不能从 CI 用时推算扫描耗时或编造人工成本 |
| 评测 A6–A7：真实案例单列、失败与边界 | GKD 保留历史版本，正常六场景结果及弃判独立报告 | 不称真实案例本轮重扫、不把回归数量当作品精度；正式误差报告/验收待确认 |
| [离线交付包](https://github.com/MrEcho114/PrivacyTrace/issues/18) A1–A2：包与独立断网运行 | 独立只读 `--network=none` 容器经 HTTP/Vue/Chromium 回放 | 复用现有导出/回放能力；正式包内容、预置环境、运行指引和目标交付验收仍待核 |
| 离线包 A3：来源/时点与真实材料授权 | 受控报告回放保留原来源与生成时点 | 商业 APK/全文政策不自动进入包，授权不足保持脱敏范围 |
| 离线包 A4–A5：许可、清单、SHA/包哈希 | 有专项证据与允许的 CI artifact 清单 | 正式可分发包、逐项依赖/素材许可、完整文件清单/包哈希与参赛提交授权未处理；CI 回放不能替代它们 |
| [完整前端](https://github.com/MrEcho114/PrivacyTrace/issues/44)：布局、候选示例、既有报告接口与交互 | 前端 PR 交付四步示例、已有 HTTP 报告、五种视口及交互检查 | 部分交付；完整规格保持开放，不重新做已交付示例 |
| 完整前端：真实 APK 上传/新扫描、抓取、模型候选及真实进度 | 本次前端 PR 明确未覆盖这些真实新流程 | 另定授权和执行切片，复用已有插件/后端契约；用户人工视觉验收也未进行 |

旧 [哈希失配评审](https://github.com/MrEcho114/PrivacyTrace/pull/47#discussion_r4241957117) 锚定 `f34a929c...`，thread 已 outdated、尚未 resolved。当前 head 的 [runner](https://github.com/MrEcho114/PrivacyTrace/blob/0f730b8106b4d2220cafcf8bee23a08b492c4f65/scripts/validate-spec30.py#L88)、[比较器](https://github.com/MrEcho114/PrivacyTrace/blob/0f730b8106b4d2220cafcf8bee23a08b492c4f65/apps/api/src/privacytrace/benchmark.py#L224) 及 [回归断言](https://github.com/MrEcho114/PrivacyTrace/blob/0f730b8106b4d2220cafcf8bee23a08b492c4f65/apps/api/tests/test_spec30_acceptance_runner.py#L38) 已包含保留失败比较行的修复。本轮静态核查，未重跑；评审 thread 的处理与代码是否已修分别判断。

## 共享文件与整合顺序

本轮流程分支只编辑协作指南、导航、模板和本记录，主代理是这些文件的唯一写入者，子代理只调查/审查。原业务分支不改写；后续它们吸收本次规则时保留第 6 节权威源，业务专项说明只补相应指针。

| 接缝 | 归属与默认次序 | 必须保留／组合验收 |
| --- | --- | --- |
| 受控模块、models/pipeline、生成契约/schema、构建与 runner | 整合任务负责人统一取舍来源，沿整合 PR 评审 | 源模型/生成物成组，冻结输入与真值不变；Check、受控专项及普通入口负例 |
| App.vue、browser-acceptance.yml、README、docs/workflow（前端与整合 PR 共改） | 保底受控整合先评审；获合并授权并进 main 后，前端负责人吸收新基线，承担双方接缝整合。负责人若改变次序，在当前记录指定后整合 owner | 保留报告来源/回放/SDK与静态边界，以及四步示例/已有报告路径；新组合 SHA 的权威入口和双方相关浏览器专项，不复用两份独立绿灯 |
| docs/backlog（插件与整合 PR 共改） | 后整合 PR 的负责人合并状态导航，保留当前 tracker 指针 | 不覆写他人进度，不把可选插件变成保底评测门槛 |
| 完整前端消费模型候选 | 插件任务保持唯一抽取实现，前端负责适配；只依赖实际复用的契约/可用版本 | 不再造 extractor；未真实调用仍标未验 |
| 总说明／影片 | 说明任务负责事实/贡献/许可和装配；[影片任务](https://github.com/MrEcho114/PrivacyTrace/issues/45) 负责 HTML/MP4 并交回说明任务 | 最终材料等评测/离线包事实，完整流程镜头等真实前端版本；影片不回写前端来伪造能力 |

这规定默认整合责任与等待条件，不指派他人的新会话、不授权任何合并。原 native blocker 暂保留；关闭/改依赖之前先完成原验收项核对及对应授权，不能为解锁任务提前关闭来源工单。前端/影片的扩展排期与保底交付分开。

## 文档场景走查

2026-10-12 依据指南第 6 节逐场景走查以下输入与动作；结果只证明规则能给出明确下一步，没有模拟真实并发锁或成员端到端试用。

| 输入 | Agent 应采取的动作 | 走查结果／规则 |
| --- | --- | --- |
| 同账号两个 Agent 打开同一执行任务 | 第二会话读负责人指定，保持只读；同时争领时双方等待裁决 | 明确，6.2 步骤 2/5 |
| 总规格、阶段索引和子任务都有 ready 标签 | 先定位执行任务及剩余验收项，续用已有交付 | 明确，6.2 工作项与步骤 1 |
| blocker open，或 closed 但产物仅有待审 PR | 等待受阻实现；允许另定范围的准备草稿 | 明确，6.2 步骤 3 |
| 来源与整合 PR 都 open | 沿唯一整合入口核查覆盖，只补缺口 | 明确，6.4 |
| 前端/整合同改 App.vue，即使各自 CI 绿 | 先定共享 owner/次序，最终组合版本重验 | 明确，6.2 步骤 4、6.4 |
| 正文待启动，但 PR 已部分交付 | 恢复最新授权/交接与剩余范围；不重新实现或关闭整个规格 | 明确，6.2 步骤 1、6.3/6.5 |
| PR head 更新，旧评论与 CI 仍绿 | 更新当前记录，验证实际新 head | 明确，6.5 |
| 原会话失联或陈旧记录 | 由负责人冻结并指定接手；旧会话恢复先读指定 | 明确，6.3 |
| tracker 不可读或出现未知本地改动 | 暂停写入，保护原改动，继续只读调查 | 明确，6.2 步骤 1/5 |
| 交付后另一 Agent 想继续补改 | 先重新指定执行会话，按清单核对范围与新基线 | 明确，6.3 步骤 3 |

真实协作验证尚未进行。真实任务中出现冲突时在其唯一当前执行记录保存发生条件、执行会话、涉及范围及处理结果，再回访本清单；若规则仍不能协调，单独决定是否增加自动化，不将本次实现称为绝对防重复保障。
