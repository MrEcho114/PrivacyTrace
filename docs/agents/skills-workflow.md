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

团队成员可根据个人使用的 Coding Agent / CLI 选择对应配置路径进行挂载或加载：

- **Claude Code**：
  - 用户级技能路径：`~/.claude/skills/`
  - 项目级技能路径：`.claude/skills/`
  - 挂载方式：通过目录软链接或按配置载入，例如：
    ```bash
    ln -s ~/.skills-zh-CN/skills/* ~/.claude/skills/
    ```
- **Codex / OpenCode**：
  - 技能配置路径：`~/.codex/skills/` 或 OpenCode 指定配置路径
  - 挂载方式：将技能目录软链接或复制至配置目录，按工具规范加载。
- **Google Antigravity / WorkBuddy**：
  - 技能路径：`~/.gemini/config/skills/` 与 `~/.workbuddy/skills/`
  - 挂载方式：使用技能同步管理工具（如 `cross-tool-skill-sync`、`find-skills`）同步，或建立软链接指向已检出的技能目录。
- **Cursor / 其他开发环境**：
  - 规则/提示词路径：`.cursor/rules/` 或系统提示词目录
  - 挂载方式：按需将技能 Markdown 规则说明直接挂载或载入系统提示。

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
  3. 升级若涉及 prompt 指令、模板字段或任务路由变化，须同步更新本文档与验证套件。

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
| **3. 跨会话 Spec / Ticket 拆分** | 中大型需求需要跨会话推进，或由多位成员分别接手 | `to-spec` / spec 拆分 tickets | 将讨论结果整理为 Spec（如放入 `docs/specs/` 或对应 Issue），并拆分为带依赖的 child tickets 录入 GitHub Issues | 形成具备明确目标、输入输出、验收条件与依赖关系的 Issues（打上 `ready-for-agent` 等标签） |
| **4. 已明确工单实施** | 已有明确 Issue，范围小且具备 PT 编号、输入输出与验收条件 | `implement`（直接实施） | 读取 Issue 字段，按测试驱动推进代码修改与对应验证 | 满足验收条件、通过本地测试/构建与 lint，无多余范围扩散 |
| **5. 范围明确的小改动** | 微小修复、配置微调或文档补充，范围高度清晰 | `implement`（直接实施） | 跳过冗长拆分与规划，执行最少必要修改并运行对应回归测试 | 改动紧凑聚焦、通过本地验证并直接提交合规 PR，避免过度设计 |
| **6. 外部反馈分流** | 收到外部用户提报的 Bug、功能请求或未经分流的 Issues | `triage`（维护者评估） | 复现确认、补齐必要信息、判定可实施性，分配对应 Triage 标签 | 转化为带清晰上下文的有效工单（如 `ready-for-agent`）或规范关闭（`wontfix`） |
| **7. 棘手 Bug 排查** | 复杂故障、偶发性异常、性能回退或根因不明显的问题 | 显式调用 `diagnosing-bugs` | 严格执行结构化诊断循环：稳定复现、定位真实根因、编写回归守卫测试 | 根因确定、包含回归测试、修复代码最小化且通过既有测试集 |
| **8. 整份 Spec 编排推进** | 负责人统筹整份 spec 的多个关联合并或批量 tickets | `implement-spec` | 统一编排并依次调度各子任务，跟踪每个 ticket 交付状态 | 所有子 tickets 验收通过，整体 spec 目标完整达成 |
| **9. 换人交接 / 跨会话接手** | 任务因人员变动、会话中断暂停，需他人无缝接手 | 工单关联材料 / Handoff | 从 Issue 的接手材料字段读取分支、已有进展、未完工作及剩余清单 | 接手者凭工单材料直接开工，不依赖私人聊天记录 |

### 尺度控制原则
- **范围明确的小改动**：直接进入实施，使用最少必要步骤，流程开销与任务规模相称，严禁为微小修复强制经历整套冗长的需求规划流程。
- **大型未知探索**：仅在路径高度不清晰、存在较多技术迷雾且需要多分支探针时，才考虑通过 `wayfinder` 建立 map 与 frontier 调度。

---

## 5. 显式调用原则与 Agent 角色职责

- **用户显式调用型技能**：
  `ask-matt`、`grill-with-docs`、`diagnosing-bugs`、`wayfinder` 等技能属于**用户调用型技能**，必须由人类开发者在交互中显式触发。
- **Agent 职责边界**：
  仓库中的 Agent 指令（如 `AGENTS.md`）仅承担**流程导航、指针引导与规则提醒**职责。Agent **不作自动触发上述技能的执行保证**，不可擅自静默替用户决定或跳过必要的人工决策环节。

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

### 6.2 领取工单 (Claim) 与阻塞等待
1. **明确 Assignee**：领取时在 GitHub Issue 上指定负责人（`gh issue edit <n> --add-assignee @me`），避免多人并行重复工作。
2. **检查阻塞依赖 (Blockers)**：
   - 检查 Issue 中的 `blockers` 字段及 GitHub 依赖关系。
   - **硬性约束**：如果任务存在未解除的阻塞依赖（有处于 open 状态的 blocker），**必须原地等待前置任务解决，严禁在阻塞未解除前提前启动该任务！**

### 6.3 任务交接 (Handoff)
1. 任务暂停、换人或跨会话结束时，必须在对应 GitHub Issue 的接手材料或最新 Comment 中留下可访问的信息：
   - 所在 Git 分支与最新 Commit SHA；
   - 当前已完成的工作与验证结果；
   - 剩余工作清单（Remaining Work）；
   - 关键设计决策或需要注意的陷阱。
2. 接手者仅需依据 Issue 与代码仓库已有材料，即可立即识别当前状态并继续开发。

---

## 7. PR 提交与代码审查规范

### 7.1 PR 模板要素
提交 PR 时使用 [`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md)，完整填写：
1. **关联 Issue**：明确标注 `Closes #<id>` 或 `Refs #<id>`；
2. **Problem and resulting behavior**：描述解决的问题与行为变更，标注 PT task；
3. **验收结果**：对照关联 Issue 验收条件逐一勾选并说明结果；
4. **Validation**：记录实际运行的测试命令与输出；
5. **Review 结论**：自查清单（无范围蔓延、阅读完整 diff、单测通过等）；
6. **Evidence and limits**：遵循证据边界（保持证据可溯源、政策来源独立、静态证据仅表达潜在行为）；
7. **未验证项**：如实列出未覆盖的边界测试或未进行真实成员试用的情况。

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
