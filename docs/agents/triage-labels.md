# Triage 标签

Skills 使用五个 canonical triage roles。本 repo 保留默认同名标签。

| Label in mattpocock/skills | Label in our tracker | 含义 |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | 维护者需要评估此 issue |
| `needs-info` | `needs-info` | 等待报告者补充信息 |
| `ready-for-agent` | `ready-for-agent` | 执行范围已充分说明，仍须通过协作检查清单确认可开始 |
| `ready-for-human` | `ready-for-human` | 需要人工实施 |
| `wontfix` | `wontfix` | 不予处理 |

当 skill 提到某个 role 时，使用右侧列的 label 字符串。需要更换词汇时直接编辑右侧列。完整分流场景与技能流程说明详见权威指南：[`docs/agents/skills-workflow.md`](skills-workflow.md)。

标签是分流提示，不是执行权；认领、依赖及状态冲突的处理统一遵循 [协作检查清单](skills-workflow.md#6-工单流转阻塞依赖与交接规范)。
