# Issue tracker：GitHub

这个 repo 的 issues 和 specs 存放在 GitHub Issues：`MrEcho114/PrivacyTrace`。所有 tracker 操作使用 `gh` CLI。

本地 [`docs/backlog.md`](../backlog.md)、[`docs/planning/`](../planning/) 和开发日志用于导航和记录；工单当前状态以 GitHub 为准。关联已有 PT 编号时遵循 [`CONTRIBUTING.md`](../../CONTRIBUTING.md) 和 [`.github/ISSUE_TEMPLATE/task.yml`](../../.github/ISSUE_TEMPLATE/task.yml)。

## 约定

以下命令在此仓库 clone 内执行，`gh` 从 origin 识别仓库。在其他目录执行时，显式加 `--repo MrEcho114/PrivacyTrace`。

- **Create an issue**：`gh issue create --title "..." --body-file <body.md>`。多行正文先保存为 UTF-8 文件，再使用 `--body-file`。
- **Read an issue**：`gh issue view <number> --comments`；需要结构化数据时使用 `--json number,title,body,labels,comments`。
- **List issues**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`；按需加 `--label` 和 `--state`。
- **Comment on an issue**：`gh issue comment <number> --body-file <comment.md>`。
- **Apply / remove labels**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`；标签映射见 [`docs/agents/triage-labels.md`](triage-labels.md)。
- **Close**：`gh issue close <number>`；需要关闭说明时，先按上述方式发表 comment。

## Pull requests 作为 triage surface

**PRs as a request surface: no.**

如果此 repo 后续把 external PRs 当作 feature requests，可以把该 flag 改为 `yes`；`/triage` 会读取它。

设为 `yes` 时，PRs 使用与 issues 相同的 labels 和 states，并使用 `gh pr` 对应命令：

- **Read a PR**：`gh pr view <number> --comments`；用 `gh pr diff <number>` 获取 diff。
- **List external PRs for triage**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`；只保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的请求。
- **Comment / label / close**：`gh pr comment <number> --body-file <comment.md>`、`gh pr edit <number> --add-label "..."` / `--remove-label "..."`、`gh pr close <number>`。

GitHub 的 issues 和 PRs 共享编号；裸 `#42` 可能属于任意一种。先用 `gh pr view 42` 解析，确认不是 PR 后再用 `gh issue view 42`；网络或认证失败时不要把失败视为“不存在”。

## 当 skill 说 "publish to the issue tracker" 时

创建 GitHub issue。

## 当 skill 说 "fetch the relevant ticket" 时

运行 `gh issue view <number> --comments`。

## Wayfinding 操作

供 `/wayfinder` 使用。**map** 是单个 issue，**child** issues 是 tickets。

- **Map**：带 `wayfinder:map` label 的 issue，正文保存 Notes / Decisions-so-far / Fog。使用 `gh issue create --label wayfinder:map --title "..." --body-file <map.md>`。
- **Child ticket**：通过 GitHub sub-issues endpoint（`gh api`）链接到 map。未启用 sub-issues 时，在 map body 的 task list 中添加 child，并在 child body 顶部写 `Part of #<map>`。Labels：`wayfinder:<type>`（`research` / `prototype` / `grilling` / `task`）。Claim 后 assign 给 driving dev。
- **Blocking**：使用 GitHub native issue dependencies 表达依赖。用 `gh api --method POST repos/MrEcho114/PrivacyTrace/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` 添加 edge；database id 来自 `gh api repos/MrEcho114/PrivacyTrace/issues/<n> --jq .id`，不是 issue number 或 node_id。GitHub 的 `issue_dependencies_summary.blocked_by` 只计 open blockers。依赖功能不可用时，在 child body 顶部记录 `Blocked by: #<n>, #<n>`；所有 blockers 关闭后才视为 unblocked。
- **Frontier query**：读取 map 的 open children（sub-issues 或 task list），排除存在 open blocker 或 assignee 的 ticket；按 map 顺序选择第一个。
- **Claim**：`gh issue edit <n> --add-assignee @me`，是该工作 session 的第一次 tracker 写入。
- **Resolve**：使用 `gh issue comment <n> --body-file <answer.md>` 记录结论，再 `gh issue close <n>`；随后向 map 的 Decisions-so-far 追加 context pointer（gist + link）。
- **技能协作体系**：团队完整技能协作规范与任务路由参见权威指南：[`docs/agents/skills-workflow.md`](skills-workflow.md)。
