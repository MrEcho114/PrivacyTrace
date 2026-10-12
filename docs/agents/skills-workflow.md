# 技能协作流程指南 (Skills Workflow Guide)

本文档是 PrivacyTrace 项目团队技能协作流程的**权威且单一维护源**。它连接新开发者贡献指南（[`CONTRIBUTING.md`](../../CONTRIBUTING.md)）、Agent 导航指针（[`AGENTS.md`](../../AGENTS.md)）、开发工单模板（[`.github/ISSUE_TEMPLATE/task.yml`](../../.github/ISSUE_TEMPLATE/task.yml)）与代码审查 PR 模板（[`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md)），为人类开发者与 Coding Agent 提供一致的协作协议。

---

## 1. 技能安装来源与环境配置

团队采纳 Matt Pocock skills 工作流体系，并支持中文技能库。

- **主要安装来源（中文技能库）**：[`vinvcn/mattpocock-skills-zh-CN`](https://github.com/vinvcn/mattpocock-skills-zh-CN)
- **上游参考源**：[`mattpocock/skills`](https://github.com/mattpocock/skills)

### 1.1 最小可执行安装步骤

为确保跨成员、跨 Coding Agent 协作的可复现性与语义一致性，团队所有成员及 Coding Agent 必须基于固化 Commit SHA (`bf98e53f92089fec9b4885f128a565d7eac0337f`) 进行安装与配置：

1. **克隆技能库到本地目录**：
   ```bash
   git clone https://github.com/vinvcn/mattpocock-skills-zh-CN.git ~/.skills-zh-CN
   ```
2. **切换至团队固化 Commit SHA**：
   ```bash
   cd ~/.skills-zh-CN
   git checkout bf98e53f92089fec9b4885f128a565d7eac0337f
   ```
3. **核验当前 Commit SHA**：
   ```bash
   git rev-parse HEAD
   ```
   *核验输出必须严格为：`bf98e53f92089fec9b4885f128a565d7eac0337f`*。

### 1.2 各 Coding Agent 配置路径与挂载方式

团队成员可根据个人使用的 Coding Agent / CLI 选择对应配置路径进行挂载或加载。

**为什么不能直接用通配符批量链接**：技能库按类别组织（`engineering`、`productivity`、`misc`、`in-progress`、`deprecated`），而每个类别目录下都有一个同名 `README.md`。因此 `skills/*/*` 这类通配符是确定性错误的安装方式：

- 5 个类别目录各含一个 `README.md`，通配符会展开出 5 个同名条目并试图全部写入同一目标目录，除第一个外全部报 `ln: failed to create symbolic link '.../README.md': File exists`，整条命令以非 0 退出（已在固定 SHA 上复现）；
- 目标目录不存在时命令直接失败：`ln: target '.../skills/': No such file or directory`；
- 会连带装入 `in-progress` 分类下的实验性技能；
- 重复执行时已存在的链接会导致整条命令失败，不具备幂等性。

正确做法是：**先创建目标目录，再只链接包含 `SKILL.md` 的真实技能目录**，排除 `deprecated`（废弃）与 `in-progress`（实验）两个分类，并对已存在的链接做幂等覆盖。下面两个版本沿用固定 SHA 内自带的 [`scripts/link-skills.sh`](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/bf98e53f92089fec9b4885f128a565d7eac0337f/scripts/link-skills.sh) 的做法（`find -name SKILL.md` + `mkdir -p` + 幂等覆盖），并在其基础上额外排除 `in-progress`；只需把 `DEST` 换成下表对应目录即可。

**Linux / macOS / Windows Git Bash**：

```bash
SKILLS_REPO="$HOME/.skills-zh-CN/skills"
DEST="$HOME/.claude/skills"        # 替换为下表对应目录

mkdir -p "$DEST"
find "$SKILLS_REPO" -name SKILL.md -not -path '*/deprecated/*' -not -path '*/in-progress/*' -print0 |
while IFS= read -r -d '' skill_md; do
  src="$(dirname "$skill_md")"
  name="$(basename "$src")"
  target="$DEST/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then rm -rf "$target"; fi
  ln -sfn "$src" "$target"
done
```

> Git Bash 的 `ln -s` 行为取决于 Windows 符号链接权限与 MSYS 链接仿真设置（开发者模式下默认可创建真符号链接）；若你的环境不支持，`ln -s` 会失败或退化成复制目录，请改用下面的 PowerShell 方案。

**Windows PowerShell（目录联接 Junction，无需管理员）**：

```powershell
$repo = "$HOME/.skills-zh-CN/skills"
$dest = "$HOME/.claude/skills"     # 替换为下表对应目录

New-Item -ItemType Directory -Force -Path $dest | Out-Null
Get-ChildItem -Path $repo -Recurse -Filter SKILL.md |
  Where-Object { $_.FullName -notmatch '\\(deprecated|in-progress)\\' } |
  ForEach-Object {
    $target = Join-Path $dest $_.Directory.Name
    if (Test-Path $target) { [System.IO.Directory]::Delete($target, $false) }
    New-Item -ItemType Junction -Path $target -Target $_.Directory.FullName | Out-Null
  }
```

> 清理旧链接请用 `[System.IO.Directory]::Delete($target, $false)`：它只删除联接本身，不会进入技能库。Windows PowerShell 5.1 下 `Remove-Item -Force`（不带 `-Recurse`）对目录联接会直接报错，无法作为替代写法。

**各 Coding Agent 的目标目录**：

| Coding Agent | 技能目录（`DEST`） | 说明 |
| :--- | :--- | :--- |
| Claude Code | 用户级 `~/.claude/skills/`；项目级 `.claude/skills/` | 也可直接运行技能库自带的 `bash ~/.skills-zh-CN/scripts/link-skills.sh`（默认链接到 `~/.claude/skills`） |
| Codex / OpenCode | `~/.codex/skills/` 或 OpenCode 指定配置路径 | 将 `DEST` 换成该路径后执行上面的命令 |
| Google Antigravity | `~/.gemini/config/skills/` | 同上 |
| WorkBuddy | `~/.workbuddy/skills/` | 同上；也可配合 `cross-tool-skill-sync`、`find-skills` 等同步工具 |
| Cursor / 其他开发环境 | `.cursor/rules/` 或系统提示词目录 | 按需将技能 Markdown 规则载入系统提示，无需逐目录链接 |

**安装后核对**（两种平台一致）：链接条目数应等于技能库中经上述过滤后的技能数，且目标目录内不应出现 `README.md`。

```bash
find "$SKILLS_REPO" -name SKILL.md -not -path '*/deprecated/*' -not -path '*/in-progress/*' | wc -l   # 固定 SHA 下为 31
ls "$DEST" | wc -l                                                                                    # 应与上一行一致
```

团队不强制统一单一 Coding Agent，但所有成员须基于相同固化 Commit SHA 遵循统一的任务路由与协作产出约束。

---

## 2. 版本基线与统一升级约定

- **固化版本基线**：
  为确保跨成员、跨 Coding Agent 协作的可复现性与语义一致性，团队明确固化已核验的技能来源基准，不再使用浮动的主分支最新描述：
  - **来源仓库**：[`https://github.com/vinvcn/mattpocock-skills-zh-CN`](https://github.com/vinvcn/mattpocock-skills-zh-CN)
  - **核验基准 Commit SHA**：`bf98e53f92089fec9b4885f128a565d7eac0337f`
  - **核验日期**：2026-10-10

  所有团队成员与 Coding Agent 均按此固化基线进行安装、配置与对齐。
- **协同升级约定**：
  1. 任何团队成员不得擅自私自升级技能库或引入未经核验的提交，以避免协作分歧；
  2. 技能库升级必须在团队沟通后，由指定成员通过专门的流程维护工单统一步调执行，并完成场景兼容性走查与基线 SHA 更新；
  3. 升级若涉及 prompt 指令、模板字段或任务路由变化，须同步更新本文档，并运行非强制工作流自检套件核验：
     ```bash
     uv run --with pyyaml python scripts/verify_workflow.py
     ```

---

## 3. 读取既有协作配置（无需重复初始化）

新加入成员或初次接触本项目的 Agent 在探索 codebase 前，应先读取仓库既有协作配置，**严禁重新执行全套项目初始化命令**：

1. **Issue Tracker**：统一使用 GitHub Issues（`MrEcho114/PrivacyTrace`），通过 `gh` CLI 操作。工单当前状态以 GitHub 为权威来源。详见 [`docs/agents/issue-tracker.md`](issue-tracker.md)。
2. **Triage 角色标签**：使用五个标准角色标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。详见 [`docs/agents/triage-labels.md`](triage-labels.md)。
3. **领域文档布局**：遵循 Single-context 规范，统一读取根目录 [`GLOSSARY.md`](../../GLOSSARY.md)、[`docs/adr/`](../adr/) 及 [`docs/architecture.md`](../architecture.md)。详见 [`docs/agents/domain.md`](domain.md)。

---

## 4. 任务路由表 (Task Routing Table)

根据任务特点选择必要步骤与技能。小改动直接实施，跨会话任务拆分 spec/tickets，路径不清晰的大型探索才考虑 wayfinder。

| 场景类型 | 典型情境 | 推荐入口 / 技能 | 下一步动作 | 完成与产出标准 |
| :--- | :--- | :--- | :--- | :--- |
| **1. 入口不确定** | 不确定当前任务类型、缺少明确下一步方向 | 显式调用 `ask-matt` | 开发者显式输入意图，获取最适合当前上下文的入口和流程建议 | 明确匹配到的工作流入口（如需求梳理、工单实施或诊断） |
| **2. 新功能需求梳理** | 需求处于初步想法阶段，范围、边界或术语尚不明确 | 显式调用 `grill-with-docs` | 对照 `GLOSSARY.md` 与 ADR 对想法做持续追问，压力测试关键决策与范围 | 术语对齐现有领域模型，明确要做与不做，形成清晰设计共识 |
| **3. 跨会话 Spec / Ticket 拆分** | 中大型需求需要跨会话推进，或由多位成员分别接手 | 显式调用 `to-spec` → `to-tickets` | 先由 `to-spec` 把讨论结果整理为 Spec（如放入 `docs/specs/` 或对应 Issue），再由 `to-tickets` 拆分为带 blocking edges 的 tracer-bullet tickets 并录入 GitHub Issues；两步是不同技能，只跑 `to-spec` 不会自动完成拆分 | 形成具备明确目标、输入输出、验收条件与依赖关系的 Issues（打上 `ready-for-agent` 等标签） |
| **4. 已明确工单实施** | 已有明确 Issue，范围小且具备 PT 编号、输入输出与验收条件 | 显式调用 `implement`（直接实施） | 读取 Issue 字段，按测试驱动推进代码修改与对应验证 | 满足验收条件、通过本地测试/构建与 lint，无多余范围扩散 |
| **5. 范围明确的小改动** | 微小修复、配置微调或文档补充，范围高度清晰 | 显式调用 `implement`（直接实施） | 跳过冗长拆分与规划，执行最少必要修改并运行对应回归测试 | 改动紧凑聚焦、通过本地验证并直接提交合规 PR，避免过度设计 |
| **6. 外部反馈分流** | 收到外部用户提报的 Bug、功能请求或未经分流的 Issues | 显式调用 `triage`（维护者评估） | 复现确认、补齐必要信息、判定可实施性，分配对应 Triage 标签 | 转化为带清晰上下文的有效工单（如 `ready-for-agent`）或规范关闭（`wontfix`） |
| **7. 棘手 Bug 排查** | 复杂故障、偶发性异常、性能回退或根因不明显的问题 | `diagnosing-bugs`（model-invoked，用户也可显式调用） | 严格执行结构化诊断循环：稳定复现、定位真实根因、编写回归守卫测试 | 根因确定、包含回归测试、修复代码最小化且通过既有测试集 |
| **8. 整份 Spec 编排推进** | 负责人统筹整份 spec 的多个关联合并或批量 tickets | 显式调用 `implement-spec` | 统一编排并依次调度各子任务，跟踪每个 ticket 交付状态 | 所有子 tickets 验收通过，整体 spec 目标完整达成 |
| **9. 换人交接 / 跨会话接手** | 任务因人员变动、会话中断暂停，需他人无缝接手 | 工单关联材料 / Handoff | 从 Issue 的接手材料字段读取分支、已有进展、未完工作及剩余清单 | 接手者凭工单材料直接开工，不依赖私人聊天记录 |

### 尺度控制原则
- **范围明确的小改动**：直接进入实施，使用最少必要步骤，流程开销与任务规模相称，严禁为微小修复强制经历整套冗长的需求规划流程。
- **大型未知探索**：仅在路径高度不清晰、存在较多技术迷雾且需要多分支探针时，才考虑通过 `wayfinder` 建立 map 与 frontier 调度。

---

## 5. 显式调用原则与 Agent 角色职责

技能按**谁能调用它**分为两类，判定依据是技能自身的 `SKILL.md` frontmatter（`disable-model-invocation: true`）及其 `agents/openai.yaml`（`policy.allow_implicit_invocation: false`）。分组以上游 [`docs/invocation.md`](https://github.com/vinvcn/mattpocock-skills-zh-CN/blob/bf98e53f92089fec9b4885f128a565d7eac0337f/docs/invocation.md) 与 README「参考」小节为准。

- **用户显式调用型技能（User-invoked）**：
  只能由人类显式输入名称触达，其他技能也不能调用它。固定 SHA 下属于此类的技能为——
  - 工程：`ask-matt`、`grill-with-docs`、`triage`、`improve-codebase-architecture`、`setup-matt-pocock-skills`、`to-spec`、`to-tickets`、`implement`、`implement-spec`、`wayfinder`、`retro`；
  - 通用：`grill-me`、`handoff`、`teach`、`to-questionnaire`、`wait-what`。
- **模型可调用型技能（Model-invoked）**：
  人类可以显式调用，Agent 也可以在任务语义匹配时主动触发，例如 `diagnosing-bugs`、`code-review`、`pr`、`tdd`、`domain-modeling`、`codebase-design`、`prototype`、`research`、`wizard`、`grilling`、`writing-for-agents` 等。
  **`diagnosing-bugs` 属于这一类**：它的 frontmatter 没有 `disable-model-invocation`，因此**不要求**人类先显式调用，不应被当作额外的人工操作步骤。
- **Agent 职责边界**：
  仓库中的 Agent 指令（如 `AGENTS.md`）仅承担**流程导航、指针引导与规则提醒**职责。
  - 对**用户显式调用型**技能，Agent 不作自动触发保证，只能提醒用户显式调用，不得擅自静默替用户决定或跳过必要的人工决策环节；
  - 对**模型可调用型**技能，Agent 可在任务匹配时主动使用，但**不保证所有 Agent harness 都会自动触发**，用户仍可随时显式调用。

---

## 6. 工单流转、阻塞依赖与交接规范

### 6.1 工单创建与结构
使用统一的开发工单模板（[`.github/ISSUE_TEMPLATE/task.yml`](../../.github/ISSUE_TEMPLATE/task.yml)），确保任务具备：
- **PT 编号** (`pt-id`)：对应 PrivacyTrace backlog 编号；
- **任务目标** (`goal`)：明确本次任务解决的核心问题；
- **输入输出与范围** (`scope`)：明确具体输入产出与涉及模块；
- **范围外事项** (`out-of-scope`)：明确划清界限，防止 scope creep；
- **关联 Spec / ADR** (`specs-and-adrs`)：链接对应的架构或设计依据；
- **阻塞依赖** (`blockers`)：列出前置依赖工单；
- **验收条件与证据** (`acceptance`)：可复核的客观验收标准；
- **验证计划** (`validation`)：本地测试、构建与检查命令；
- **接手材料** (`handoff`)：供换人或跨会话接手的上下文。

### 6.2 开始与恢复：先查重，再确认执行权

本节是开始、恢复、分派、扩大范围、更新 PR 和交接时的协作检查清单，由 Agent 执行和维护，不要求用户另填表；当前状态以对应 Issue 的“当前执行记录”为准，历史正文和收据继续保留原版本。

先区分工作项：**阶段索引**只导航排期，**规格**定义目标与验收，**执行任务**承载一个明确授权的交付范围。父 Issue 的 Assignee 协调分工，执行任务只有一个 Assignee。整份规格已有子任务时，先复用其分解；聚合执行须先记录覆盖哪些子任务及剩余边界。简单任务可用会话授权和 PR 记录，无须补造工单。

每次可能写入前依次检查：

1. 读取最新 main、任务正文、当前执行记录、最新交接、关联 PR 和 native blockers；保留工作区来源不明的修改。通过 tracker 搜索相同目标的开放任务、待审交付及已合并实现，逐项核对验收覆盖；完成条件是找到唯一执行入口和真正剩余项。已有候选时续做审查/补缺口，阶段索引或规格标签不提供第二个实现入口。
2. 确认启动授权、范围、唯一 Assignee 和由负责人指定的**唯一执行会话**。同一人打开多个工具或 Agent，仍只有被指定会话可写该任务；新会话须先查记录。Assignee 的 API 写入不是原子抢占锁，`ready-for-agent` 只是分流标签。两个会话同时认领、负责人不明或记录矛盾时均保持只读，等待负责人指定唯一写入者；不凭先写评论、评论陈旧或超时自动抢占。
3. **检查阻塞依赖 (Blockers)**：若存在未解除的 open blocker，必须原地等待，严禁在阻塞未解除前提前启动开发。关闭 blocker 后还要核对规定产物已进入 main、对应验收通过且版本可用，不能只看 Issue closed 或来源 PR 的绿灯。明确标注的独立调查、模板/环境准备和材料草稿可先做；它们不授权受阻实现或最终验收。调查/决策票按其约定结论解除，不能将其与业务代码合入条件混为一谈。
4. 声明拟修改文件和共享接口，检查现有 PR 的文件交集。共享代码、接口、源模型及其生成契约/schema、CI、工作流和状态文档均指定一个编辑/整合 owner；其他会话只读提交建议，或由 owner 划定边界后串行交接。不同目录、Git 可合并和独立 CI 成功都不证明没有行为交叉。
5. 将结果写入并回读“当前执行记录”，完成条件是授权、执行会话、剩余范围、依赖和共享归属均明确且无冲突；任一未知、远端不可读或记录变化时暂停写入，只读调查可继续。子代理只调查/检查，主代理负责 tracker、VCS 和最终交付。

当前执行记录由 Agent 维护，可放在 Issue 正文的独立当前区，或最新的同名评论；正文放一个指针，避免维护两份细节。无 Issue 的小任务在 PR 维护同样信息，开始前暂存会话授权与查重结果：

```markdown
## 当前执行记录

- 状态／确认时点：未开始 | 进行中 | 暂停 | 部分交付 | 待审 | 待合并 | 已合入
- 授权／范围：来源、覆盖任务、写入范围、排除项、真正剩余工作
- 负责人／执行会话：单一 Assignee、工具及可区分的会话标识、负责人指定依据
- 基线／交付：main SHA、分支、最新提交 SHA、唯一 PR 或尚未创建
- 依赖／共享归属：前置产物及验收版本、共享文件/接口 owner、整合顺序
- 验证／交接：证据链接、未测项、已完成进展、剩余工作、执行权是否移交
```

标识只使用非敏感的工具/会话编号，不写凭证、本机私有路径或原始数据。父任务协调人不自动取得每个子任务的执行权；一个 Assignee/会话可以拥有多个任务，但各任务的范围、依赖和共享归属须分别清楚。

### 6.3 暂停、换人及释放执行权 (Handoff)

1. 原执行会话先停止写入，在当前记录留下分支、最新提交、已有进展/验证、剩余工作清单及共享文件状态/关键取舍；负责人明确指定接手会话，接手者回读并按 6.2 重查后才写入。移除 Assignee 或创建另一 worktree 本身不表示交接完成。
2. 原会话失联时，由负责人明确冻结其执行权并指定接手者；接手者保护未知改动，不能猜测旧会话已经停止。旧会话恢复后先读最新指定，保持只读直到重新获得执行权。
3. 暂停保留负责人和恢复条件；交付结束后记录当前 PR/SHA 与剩余项，释放会话写入权，后续修订须重新指定。部分交付、技术检查通过、待审和已合入分别记录，原规格只有全部验收项获证据支持才可称完成；关闭、合并、发布与部署遵守各自授权。

### 6.4 分派与串行整合

并行工作拆成可独立验收的执行子任务，父子关系表达分解，native blocking 表达次序；尚无 native 支持时按 tracker 的正文约定记录。主责任人分派前先盘点目标和文件，指定共享 owner。源模型与生成物成组归属，验证工具随被验证行为一起整合。

来源 PR 被整合交付吸收时，在当前记录明确唯一交付入口和逐项取舍；来源只供追溯，不再作为平行实现/整支合并入口。对缺口补剩余任务，不重做已覆盖功能；其 owner 与启动授权不明确时等待。

多个交付共享行为时，默认由后整合的交付负责人吸收新 main，保留双方约定行为并运行权威检查和相关专项；具体先后由交付负责人在当前记录确认。该记录只指定整合范围，不代替用户合并授权。保底主线与后续扩展分别排期，新增前端/影片/插件不默默成为保底交付的新门槛。

### 6.5 交付与状态同步

更新 PR 前后、范围扩大、上游合入、恢复或换人时重跑 6.2 清单。唯一执行会话回写当前记录的最新 PR/head、验收覆盖、剩余项、共享顺序与确认时点；总计划/backlog 仅指向该记录，旧日期、原授权及 receipts 保持原样。

维护 `ready-for-agent` 时区分规划就绪与执行就绪；阶段索引、规格、被阻塞/已认领/待审/部分交付任务在当前记录明确状态，不能凭标签开工。标签矛盾由负责人确认后统一，不能靠移除标签、关闭 blocker 或未经核查关闭工单消除冲突。后续改动重验实际交付 SHA，不复用旧 head 的 CI。

检查清单是团队约定，不是自动锁或新 CI 门禁。复核场景与当前业务交付的覆盖/缺口见 [协作落地记录](../stages/workflow-coordination-20261012.md)；文档场景走查不证明真实多人协作已经有效。

---

## 7. PR 提交与代码审查规范

### 7.1 PR 模板要素
提交 PR 时使用统一模板 [`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md)，遵循 TheMasterplan 治理与 Issue #32 规范，完整填写：
1. **Related task**：明确标注 `Issue: Closes #<number>` 或明确人类授权来源与范围；
2. **Result**：描述解决的核心问题与最终表现，包含对应的 PT 编号；
3. **Changes**：列出主要修改的文件及改动要点；
4. **Verification**：记录实际执行的验证命令、自动化测试及结果，并在「验收结果」小节对照关联 Issue 验收条件逐项说明；
5. **Agent self-review**：交付代理的五项自审检查清单（满足授权、未扩大范围、已阅读完整 diff、必要验证已通过、无遗留调试代码与缓存）；
6. **Evidence and limits**：遵循证据边界（保持证据可溯源、政策来源独立、静态证据仅表达潜在行为）；
7. **未验证项**：如实列出未覆盖的边界测试或未进行真实成员试用的情况（标记为文档场景走查）；
8. **Notes for human**：供人类审阅者参考的上下文与注意事项。

### 7.2 审查者判断标准
- 审查者依据**变更合理性、测试验证结果、证据边界准确性**来评估 PR，严禁以“是否记录技能调用日志”等无意义形式主义作为审查标准。

---

## 8. 证据边界与领域规范约束

PrivacyTrace 涉及 Android 隐私静态分析与政策比对，必须在协作产物中严格遵循以下准则：

1. **遵守 Single-context 领域词汇**：
   使用根目录 [`GLOSSARY.md`](../../GLOSSARY.md) 中定义的术语，严格避免使用明确列出的禁用词/同义词（例如禁止使用“实际采集证据”、“违规证据”、“已验证政策”、“隐私测谎”、“合规认证”等）。
2. **严格区分三类材料**：
   - **静态证据（Static evidence）**：仅代表授权能力（如权限）或代码潜在线索（如 API 调用位置）。**静态证据不能证明运行时已发生数据收集或外传**；
   - **政策声明（Policy claims）**：由政策原文提出的声明，未经核验不得当作既定事实；
   - **上下文推断（Context inference）**：推断与事实必须分离存储，未知字段严格保留为 `UNKNOWN`。
3. **真实度与验证边界**：
   - 在未经团队真实成员端到端试用前，所有关于本工作流规范的测试结果均应准确标识为**“文档场景走查”（Document scenario walkthrough）**；
   - 严禁补造虚假成员访谈、真实试用数据或伪造审核结论。
