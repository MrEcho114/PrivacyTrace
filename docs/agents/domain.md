# 领域文档

Engineering skills 探索 codebase 前，应读取此 repo 的领域词汇和相关架构决策。团队技能协作流程详见权威指南：[`docs/agents/skills-workflow.md`](skills-workflow.md)。

## 探索前先读取这些

- 根目录 **`GLOSSARY.md`**：本 repo 采用 single-context，共用一份领域词汇表。
- **`docs/adr/`**：读取与当前工作区域相关的 ADRs。
- **`docs/architecture.md`**：此仓库已有的架构决策文档（标题为 ADR-001），继续按相关主题读取；不因采用新布局而自动搬迁。
- 如果后续引入根目录 **`GLOSSARY-MAP.md`**，按其映射读取当前话题涉及的 glossary；多领域布局还需检查相关 `src/<context>/docs/adr/`。

如果 glossary 或 ADR 路径不存在，**静默继续**。不要将缺失列为问题，不要提前建议创建。`/domain-modeling` 会在实际确定术语或决策时按需创建文件。

## 文件结构

当前采用 **single-context**：

```text
/
├── GLOSSARY.md
├── docs/
│   ├── architecture.md       # 已有架构决策
│   └── adr/                  # 后续 ADRs，按需创建
├── apps/
│   ├── api/
│   └── web/
└── packages/contracts/
```

前后端和共享 contracts 使用同一套领域词汇；无需按技术目录拆分 glossary。

## 使用 glossary 的词汇

输出命名 domain concept 时（issue title、refactor proposal、hypothesis、test name），使用 `GLOSSARY.md` 中定义的 term，避免其明确列出的 synonyms。

所需概念尚未定义时，先判断是否引入了项目未使用的语言；确认属于缺口后，为 `/domain-modeling` 记录。

## 标记 ADR 冲突

如果输出与已有 ADR 矛盾，明确指出对应决策和建议重开的理由，不要静默覆盖：

> 与 ADR-0007 冲突；建议重新讨论，因为……
