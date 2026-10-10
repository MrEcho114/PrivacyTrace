# 贡献与协作指南

欢迎参与 PrivacyTrace 开发。本项目结合 Matt Pocock skills 工作流规范，建立清晰的技能导航、工单流转与代码审查机制。

---

## 技能工作流与协作入门

本项目采用结构化的技能协作体系，完整规则维护在单一权威文档中：**[技能协作流程指南](docs/agents/skills-workflow.md)**。新成员请先阅读该指南。

### 1. 技能安装与环境配置
- **推荐技能来源（中文技能库）**：[`vinvcn/mattpocock-skills-zh-CN`](https://github.com/vinvcn/mattpocock-skills-zh-CN)
- **上游参考库**：[`mattpocock/skills`](https://github.com/mattpocock/skills)
- **多 Agent 支持**：团队成员可选用 Claude Code、Codex、Antigravity、OpenCode 等任何 Coding Agent，通过各自工具的技能目录或同步插件安装对应技能。团队不强制统一单一 Agent。
- **版本基线与升级**：以安装时中文技能库的最新可用稳定基线为准；技能升级由团队统一协调并走查兼容性，禁止私自单独升级造成流程分歧。

### 2. 读取已有项目配置
新成员无需重复初始化协作配置，进入项目后直接复用既有体系：
- **Issue Tracker**：统一使用 GitHub Issues（`MrEcho114/PrivacyTrace`），通过 `gh` CLI 操作（详见 [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md)）。
- **Triage 标签**：使用 `needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`（详见 [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md)）。
- **领域文档**：遵循 Single-context 规范，使用根目录 [`GLOSSARY.md`](GLOSSARY.md)、[`docs/adr/`](docs/adr/) 与 [`docs/architecture.md`](docs/architecture.md)（详见 [`docs/agents/domain.md`](docs/agents/domain.md)）。

### 3. 任务类型与入口速查
根据任务规模和类型选择必要步骤（详细路由见 [权威流程指南](docs/agents/skills-workflow.md)）：
- **入口不确定**：显式调用 `ask-matt` 获取下一步流程建议；
- **新功能需求梳理**：显式调用 `grill-with-docs`，对照领域文档对齐术语与边界；
- **跨会话中大型需求**：整理为 Spec 并拆分为带依赖的 child tickets；
- **已明确工单**：直接进入 `implement` 实施，小改动无需冗余规划；
- **范围明确的小改动**：跳过冗长规划直接实施，使用最少必要步骤；
- **外部反馈**：使用 `triage` 分流、补齐信息与贴标签；
- **棘手 Bug 排查**：显式调用 `diagnosing-bugs`，依根因循环和回归守卫排查；
- **整份 Spec 编排推进**：使用 `implement-spec` 统一编排并依次调度各子任务；
- **换人交接**：通过工单关联的 Handoff 材料识别进展与剩余工作接手。

> **注意**：用户调用型技能须由开发者显式调用，Agent 仅承担导航提醒与流程指针职责，不保证自动触发。

### 4. 工单创建、领取、依赖等待与交接
- **创建任务**：统一使用开发工单模板 [`.github/ISSUE_TEMPLATE/task.yml`](.github/ISSUE_TEMPLATE/task.yml)，填写 PT 编号、目标、范围、范围外事项、关联 Spec/ADR、阻塞依赖、验收条件与接手材料。
- **领取任务**：在 GitHub Issue 上指定 Assignee（`gh issue edit <n> --add-assignee @me`）。
- **依赖等待**：检查工单中的阻塞依赖（`Blockers`），**若存在未关闭的 blocker，必须原地等待，严禁在阻塞未解除前提前启动开发**。
- **任务交接**：暂停或换人时，须在 Issue 的接手材料字段或最新 Comment 留下分支名、最新 Commit、已有进展与剩余工作清单。
- **提交 PR 与代码审查**：遵循 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) 提交 Pull Request，对照关联 Issue 验收条件逐项确认完成情况，完成 Review 结论自查，并如实标注未验证项与证据边界。

---

## 核心开发守则

日常交付以根部 [AGENTS.md](AGENTS.md) 的 Context Router 和 [工作流](docs/workflow.md) 为准。

- 用户提出目标即可；复杂任务用 Issue，小修复可直接按会话授权执行。
- 一个主交付责任人负责范围、验证、完整 diff、push 和 PR；PR 模板与五项自审由代理完成，不再要求 A/B 签字或逐条评论。
- 验证统一运行 `bash scripts/check.sh`；Windows 的 `scripts/check.ps1` 委托 Git Bash。CI 使用同一入口并强制开启 Docker 回归。
- 代码通过、S1 技术验收与 PR 合并是不同状态。未经对应授权，不合并、发布、部署或改分支保护。
- 主线保持 Evidence Model → Taxonomy → Consistency Engine → Explainable Report。事实、声明、上下文推断分开；UNKNOWN 不编造。权限只能说明授权能力，静态证据不能证明运行时收集或外传。权限/静态 invoke 不证明实际采集或外传。
- SDK 政策不能替宿主补声明；没有足够政策证据时不返回“未声明”。组织流程豁免不把政策标为 REVIEWED，不改变合法性/安全性边界。
- 分类或匹配规则改变时更新版本、迁移说明和语义测试；不使用 LLM 作最终事实裁决。
- 不提交密钥、APK、个人数据、数据库或完整政策/反编译材料；不补造开发记录、访谈或评测数据。
- 保留未知本地改动；不强推、不移动已发布 tag。提交信息简短说明目的即可。
