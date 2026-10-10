# PrivacyTrace

加油，你可以做到的

## TheMasterplan

> 本文件由 /TheMasterplan 接入生成；规则由 TheMasterplan 管理区块声明。

<!-- THEMASTERPLAN:BEGIN MANAGED -->
# TheMasterplan

This block is the project Context Router. Load guidance only when the task needs it.

- routine delivery and external-ownership decisions: `core/workflow.md`
- authorization / merge / release / destructive remote action: `core/policy.md`
- VCS release/tag: load the selected installed profile under `profiles/`
  (the adopted project contains only its selected profile)
- adoption/update maintenance: use the installed `.themasterplan/bin/themasterplan.py`
  commands; consult upstream adoption/update docs only for that maintenance task

Do not preload the whole rule stack.

Within the authorized scope, continue until the requested result exists, relevant
validation passes, failures caused by the change are fixed and revalidated, and
the final diff is reviewed — or until a genuine human decision boundary is reached.
<!-- THEMASTERPLAN:END MANAGED -->

## 项目事实与边界

- 项目：PrivacyTrace；Android APK 静态证据与政策声明对照，不判断违法/安全/实际采集。
- 默认分支：`main`；短期任务分支：`codex/`；保留现有 Git，不自动迁移 jj。
- 权威验证：`bash scripts/check.sh`；Windows 用 Git for Windows Bash，`pwsh -NoProfile -File scripts/check.ps1` 委托同一入口。
- 当前交付责任人：执行当前授权的主代理；子代理只调查/检查，不独立 push、改 Issue 或合并。
- 当前任务来自 Issue 或用户直接授权；小任务不要求另填表或补造工单编号。
- 2026-10-09 用户撤销 S1 双人逐条 comment/签字门槛，接受现有技术核验；见 `docs/stages/s1-acceptance-20261009.md`。不再因缺 A/B 表单阻塞交付。
- PR 信息、验证记录、五项自审由交付代理填写，不要求用户重复填表。用户只提出目标、回答必要的范围问题、决定是否合并。
- 合并/发布/部署不包含在一般“通过验收”中；本次不自动合并 #27/#28/#29，不改远端保护设置。
- APK/完整政策/反编译全文、密钥、数据库和本机私有路径不提交；真实 APK 仅在受限 Docker 中处理。
- 权限是能力，invoke 是静态潜在线索；事实、声明、推断分开，未知保留 UNKNOWN。
- 政策 UNREVIEWED/PARTIAL/附件未检查仍为数据事实；取消团队流程不把政策标为已复核，不降低引擎缺证据条件。
- 任务索引：`docs/backlog.md`；当前交付流程：`docs/workflow.md`；旧报告/receipts 保留原 SHA 和当时状态，不倒改历史。

## Agent skills

### Skills workflow

团队技能协作流程与任务路由详见权威指南：[`docs/agents/skills-workflow.md`](docs/agents/skills-workflow.md)。

- **显式调用原则**：用户调用型技能（如 `ask-matt`、`grill-with-docs`、`diagnosing-bugs`、`wayfinder` 等）需由开发者显式调用。Agent 仅承担流程导航、指针引导与规则提醒职责，不作自动触发保证。
- **任务路由提醒**：
  - 遇到入口或下一步不确定时，提醒用户调用 `ask-matt` 获取适配建议；
  - 遇到新功能想法或模糊需求时，提醒用户调用 `grill-with-docs` 结合领域文档对齐边界；
  - 遇到复杂棘手缺陷时，提醒用户调用 `diagnosing-bugs` 依根因循环与回归守卫排查；
  - 遇到已明确范围的小任务或工单，直接进入 `implement` 实施，避免冗余规划；
  - 遇到范围明确的小改动，直接执行最少必要步骤，无需过度设计；
  - 跨会话需求推进提醒使用 `to-spec` 整理 spec 并拆分为带依赖的 child tickets；
  - 遇到未分流的外部反馈或 Issues 时，提醒使用 `triage` 评估、补齐上下文并贴标签；
  - 遇到需要整份 Spec 批量推进或编排时，提醒使用 `implement-spec` 统一调度。
- **工单流转与交接约束**：
  - 任务创建与结构遵循模板 [`.github/ISSUE_TEMPLATE/task.yml`](.github/ISSUE_TEMPLATE/task.yml)；
  - 领取工单时明确 Assignee（`gh issue edit <n> --add-assignee @me`）并检查阻塞依赖（`Blockers`）；
  - **若存在未解除的 open blocker 必须原地等待，严禁在阻塞未解除前提前启动开发**；
  - 任务交接或跨会话暂停时，必须在对应 Issue 留下接手材料（包含分支名、最新提交、已有进展与剩余工作清单）；
  - 提交 PR 审查遵循模板 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md)。
- **证据边界**：遵循 Single-context 领域文档（[`GLOSSARY.md`](GLOSSARY.md)）；严格区分静态证据（仅代表潜在线索/能力）、政策声明与上下文推断，严禁超出材料支持范围引申结论。

### Issue tracker

Issues 和 specs 使用 GitHub Issues（`MrEcho114/PrivacyTrace`），通过 `gh` CLI 操作。See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md)。

### Triage labels

五个 triage roles 使用同名标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。See [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md)。

### Domain docs

采用 single-context：根目录 [`GLOSSARY.md`](GLOSSARY.md) + [`docs/adr/`](docs/adr/)；已有架构决策仍在 [`docs/architecture.md`](docs/architecture.md)。See [`docs/agents/domain.md`](docs/agents/domain.md)。
