# TheMasterplan

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

## 项目事实

- 项目：PrivacyTrace；Android APK 静态证据与政策声明对照，不判断违法/安全/实际采集。
- 默认分支：`main`；短期任务分支：`codex/`；保留现有 Git，不自动迁移 jj。
- 权威验证：`bash scripts/check.sh`；Windows 用 Git for Windows Bash，`pwsh -NoProfile -File scripts/check.ps1` 委托同一入口。
- 当前交付责任人：执行当前授权的主代理；子代理只调查/检查，不独立 push、改 Issue 或合并。
- 当前任务来自 Issue 或用户直接授权；小任务不要求另填表或补造工单编号。
- 2026-10-09 用户撤销 S1 双人逐条 comment/签字门槛，接受现有技术核验；见 `docs/stages/s1-acceptance-20261009.md`。不再因缺 A/B 表单阻塞交付。
- PR 信息、验证记录、五项自审由交付代理填写，不要求用户重复填表。用户只提出目标、回答必要的范围问题、决定是否合并。
- 合并/发布/部署不包含在一般“通过验收”中；本次不自动合并 #27/#28/#29，不改远端保护设置。

## 项目边界与资料

- APK/完整政策/反编译全文、密钥、数据库和本机私有路径不提交；真实 APK 仅在受限 Docker 中处理。
- 权限是能力，invoke 是静态潜在线索；事实、声明、推断分开，未知保留 UNKNOWN。
- 政策 UNREVIEWED/PARTIAL/附件未检查仍为数据事实；取消团队流程不把政策标为已复核，不降低引擎缺证据条件。
- 任务索引：`docs/backlog.md`；当前交付流程：`docs/workflow.md`；旧报告/receipts 保留原 SHA 和当时状态，不倒改历史。
- 开始时保护来源不明的本地修改；不要导入主工作区未跟踪的研究资料、配置或 PROJECT.md。

加油，你可以做到的。

## Completion Contract

在授权范围内实现结果、修复本次引入的失败、通过权威检查、审阅完整 diff 并推送交付；远端 CI 结果须绑定交付 SHA。合并等独立授权边界到此停下，不要求用户补填复核表。
