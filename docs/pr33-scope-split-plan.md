# PR33 范围拆分方案（评审 Section 三）

评审结论：PR33 把 PT-808 浏览器端验收与大量无关的规划/流程产物混在同一个 PR，建议拆分。
本文件给出**可执行的拆分清单**，供拆分 PR 时直接使用。

> 说明：本文件是修复工作的附带产物，只做清单与命令建议，不自动改动仓库结构——
> 拆分应在独立的 PR 中进行，以免在修复 PR 里再次引入范围混杂。

## 1. 现状量化

`16f6d3f` 单提交共 **128 个文件**，按性质分为：

| 分类 | 文件数 | 与 PT-808 的关系 |
|---|---|---|
| **A. PT-808 实质交付** | 22 | ✅ 本次 PR 的核心 |
| B. 规划 / Issue 重建快照（`docs/planning/**`） | 90 | ❌ 无关 |
| C. 开发计划与协作流程文档 | 10 | ❌ 无关 |
| D. ADR（`docs/adr/**`） | 2 | ❌ 无关 |
| E. 研究报告（`docs/research/**`） | 4 | ❌ 无关 |

## 2. 应保留在 PT-808 PR 中的文件（22 个）

```
.gitignore
apps/api/src/privacytrace/runtime_models.py
apps/api/tests/test_challenger_review.py
apps/web/index.html
apps/web/src/App.vue
apps/web/src/contracts.generated.ts
apps/web/src/main.ts
apps/web/tests/challenger_stress.test.ts
evidence/acceptance-matrix-pt808.md
evidence/browser-proof.json
evidence/screenshots/*.png                (9 → 修复后 10 张)
packages/contracts/review-request.schema.json
scripts/challenger-adversarial-suite.cjs
scripts/verify-browser-acceptance.cjs
scripts/verify_workflow.py
```

本次修复新增（同样属于 PT-808）：

```
fixtures/acceptance-jobs/*.json           (6 个最小 fixtures)
scripts/build_acceptance_fixtures.py
package.json / package-lock.json          (声明 playwright devDependency 与脚本入口)
apps/web/vite.config.ts                   (代理/端口可配置)
apps/api/src/privacytrace/{main,models,pipeline,policy_intake}.py
apps/api/tests/test_jobs_api.py
packages/contracts/{evaluation-input,jobs-response,report}.schema.json
samples/demo/evaluation-input.json
```

## 3. 建议拆出的文件（106 个）

| 目标 PR | 文件 | 命令 |
|---|---|---|
| **PR-A｜规划与 Issue 重建快照** | `docs/planning/**`（90 个） | `git checkout <base> -- docs/planning` 后在新分支反向提交 |
| **PR-B｜开发计划与协作流程** | `docs/development-plan.md`、`docs/agents/**`（4 个）、`AGENTS.md`、`CONTRIBUTING.md`、`GLOSSARY.md`、`PROJECT.md`、`.github/ISSUE_TEMPLATE/task.yml`、`.github/PULL_REQUEST_TEMPLATE.md` | 同上 |
| **PR-C｜架构决策记录** | `docs/adr/0001-*.md`、`docs/adr/0002-*.md` | 同上 |
| **PR-D｜研究报告** | `docs/research/**`（4 个） | 同上 |

### 拆分操作建议

从 PT-808 分支中移除这些文件（保留文件本身，不改内容），把它们放到独立分支：

```bash
# 在 PT-808 分支上，仅移除无关文件（不删除磁盘内容到无处可去）
git rm -r --cached docs/planning docs/agents docs/adr docs/research \
  docs/development-plan.md AGENTS.md CONTRIBUTING.md GLOSSARY.md PROJECT.md
git commit -m "chore(PT-808): 将规划与流程文档移出验收 PR，另开独立 PR"

# 另建分支承载这些文档，避免丢失
git checkout -b chore/planning-and-workflow-docs <base>
git checkout <pt808-branch>@{1} -- docs/planning docs/agents ...   # 从原提交取回
git commit -m "docs: 归档规划快照、协作流程、ADR 与研究报告"
```

> ⚠️ 若这些文件已被其他分支/PR 依赖，先确认引用关系再移动。

## 4. 拆分后的评审收益

- PT-808 PR 的 diff 从 **128 个文件**降到约 **22 个**，评审者能聚焦在异常边界、防 XSS、来源分类与可选备注这四条验收线。
- 规划类文档可走独立的「文档变更」评审路径，不占用代码审查额度。
- 每个 PR 的 `evidence/` 与实现一一对应，SHA 溯源不再与其他变更耦合。
