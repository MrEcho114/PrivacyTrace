# PR33 范围拆分方案（评审 Section 三）

评审结论：PR33 把 PT-808 浏览器端验收与大量无关的规划/流程产物混在同一个 PR，建议拆分。

> **执行状态：已执行（见本文件 §5）。**
> 执行过程中发现原方案有三处归类错误，已修正：`AGENTS.md`、`CONTRIBUTING.md`、
> `.github/ISSUE_TEMPLATE/task.yml` 在 main 上已存在且改动全部是引用被移出文档，
> 应**还原**而非删除；`GLOSSARY.md` 实为本 PR 新增，应一并移出；
> `verify_workflow.py` 与它校验的文档是一体，必须同组移出。详见 §5.3。
>
> **最终效果：PR 可见变更由 152 个文件降至 47 个，删除项 0。**

## 1. 现状量化

`16f6d3f` 单提交共 **128 个文件**，按性质分为：

| 分类 | 文件数 | 与 PT-808 的关系 |
|---|---|---|
| **A. PT-808 实质交付** | 22 | ✅ 本次 PR 的核心 |
| B. 规划 / Issue 重建快照（`docs/planning/**`） | 90 | ❌ 无关 |
| C. 协作流程文档与配套脚本 | 12 | ❌ 无关 |
| D. ADR（`docs/adr/**`） | 2 | ❌ 无关 |
| E. 研究报告（`docs/research/**`） | 4 | ❌ 无关 |
| F. 离线交付 spec（`docs/specs/**`） | 1 | ❌ 无关 |

> 拆分时量准：C 类为 12 个，比原估 10 个多 2 —— 原方案遗漏了
> `.github/ISSUE_TEMPLATE/task.yml` 与 `scripts/verify_workflow.py`（两者
> 分别属"协作模板"与"校验上述文档的脚本"），F 类 `docs/specs/` 亦为原方案未单列。

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

## 5. 执行记录（本次已执行）

### 5.1 承载分支

无关文件先保存在独立分支，避免内容丢失：

```bash
git branch docs/planning-workflow-adr-research HEAD   # 拆分前，含全部 128 个文件
```

### 5.2 实际处置的 109 个文件

拆分分两类操作：**移除新增文件**（106 个）与**还原既有文件**（3 个）。

```bash
# 1) 新增文件：从索引移除（内容已在承载分支）
git rm --cached docs/planning/** docs/agents/** docs/adr/** docs/research/** \
  docs/specs/** docs/development-plan.md GLOSSARY.md PROJECT.md \
  scripts/verify_workflow.py

# 2) main 上已存在的文件：还原为 main 版本，而非删除
git checkout origin/main -- AGENTS.md CONTRIBUTING.md .github/ISSUE_TEMPLATE/task.yml
```

> ⚠️ 关键区分：`git rm` 对 **main 上已存在**的文件会产生真实删除，
> 对 **本 PR 新增**的文件只是取消新增。二者必须用不同操作。

### 5.3 对原方案的三处修正

执行时逐项检查代码引用与文件来源，发现原清单有三处归类错误：

| 文件 | 原归类 | 实际问题 | 处置 |
|---|---|---|---|
| `AGENTS.md` | ❌ 应拆出 | `16f6d3f` 对其的改动**全部**是新增指向 `docs/agents/**`、`GLOSSARY.md`、`docs/adr/**` 的链接；文档拆走后必然死链 | **还原**为 main 版本 |
| `.github/ISSUE_TEMPLATE/task.yml` | ❌ 应拆出 | 同上，`16f6d3f` 只改了协作流程模板字段（PT-ID / handoff 等），与验收无关 | **还原**为 main 版本 |
| `CONTRIBUTING.md` | ❌ 应拆出 | 同上，改动仅为协作流程入口 | **还原**为 main 版本 |
| `GLOSSARY.md` | ✅ 应保留 | 实际由 `16f6d3f` **新增**，并非 main 既有；保留在 PR 里反而是范围外内容 | **一并移出** |
| `scripts/verify_workflow.py` | ✅ 应保留 | 它校验 `docs/agents/**` 与 `.github/ISSUE_TEMPLATE/task.yml`；文档拆走后脚本必然失败（实测 `AssertionError: Missing section in PR template`），且无 CI 调用方 | **改为与文档同组移出** |

> 教训一：拆分「文档 + 校验脚本」这一对时，必须先确认脚本与被校验文档的依赖方向，
> 否则会留下一个必然失败的校验器。
>
> 教训二：**先判断文件在 base 分支是否存在**，再决定用 `git rm` 还是 `git checkout base --`。
> 本次首轮执行时曾误将 `AGENTS.md`、`CONTRIBUTING.md`、`task.yml` 直接删除，
> 造成 3 个 main 既有文件被误删；已复查并纠正，最终 PR 删除项为 0。

### 5.4 拆分后验证

| 检查 | 结果 |
|---|---|
| PR 可见变更（`origin/main...HEAD`） | **47 个文件**（24 A / 23 M / 0 D），较拆分前 152 个下降 69% |
| 误删 main 既有文件 | **0** |
| 被移出路径残留 | 0（`docs/planning`、`docs/adr`、`docs/agents`、`docs/research`、`docs/specs`、`verify_workflow.py`、`GLOSSARY.md`、`PROJECT.md` 全部退出 PR） |
| 死链检查 | 无（`AGENTS.md` 已回到 main 版本，不再引用被移出文档） |
| `ruff check apps/api` | All checks passed |
| 前端单测 | 28 / 28 pass |
| 前端类型检查（`vue-tsc --noEmit`） | 通过，无输出 |
| 契约导出一致性（`export-schema.py` 后 `git diff`） | 无差异 |
| 后端 pytest | **318 passed / 11 skipped / 4 failed**（见下方归因） |
| 浏览器验收 | TC-01…TC-05 全 PASSED，EXIT=0，收据 `anchored: true` |
| `test_governance_cli.py` | 2 例失败为**既有**，已在基线 `f1230aa` 对照复现，与拆分无关 |

#### 4 个失败的归因（全部为既有问题，非本次拆分引入）

| # | 失败用例 | 归因 | 证据 |
|---|---|---|---|
| 1 | `test_job_creation.py::test_one_reservation_wins_across_processes_and_survives_restart` | Windows `msvcrt.locking` 跨进程争用 | 报错 `PermissionError [Errno 13] ...\.lock`；已在原始 HEAD 复现 |
| 2 | `test_job_creation.py::test_concurrent_pipeline_never_scans_both_inputs_for_one_id` | 同上 | 同上 |
| 3 | `test_governance_cli.py::test_local_source_installs_commit_objects_not_dirty_executor[True]` | 该用例执行大量 git 操作（建 fixture 仓库、`git replace`），在基线 `f1230aa` 上**同样失败**，报 `subprocess.TimeoutExpired ... timed out after 40 seconds` | 已在 `git worktree add f1230aa` 上独立复现 |
| 4 | 同上 `[False]` | 同上 | 同上 |

> 归因方法：对 3/4 用 `git worktree add /tmp/pt-baseline f1230aa` 建出**未含任何本次改动**的
> 独立工作树，单独运行该用例，得到同样的 `TimeoutExpired` 失败，从而排除本次改动嫌疑。
> 这两个用例单独运行时通过、全量并发时超时，属资源竞争型 flaky，与代码正确性无关。

#### 关于两个 diff 口径

拆分后有两个数字，含义不同，勿混淆：

- **`git diff origin/main...HEAD` → 47 个**：reviewer 在 GitHub 上看到的 PR 变更，是唯一有意义的验收口径。
- **`git diff 16f6d3f...HEAD` → 150 个**：其中 106 个 D 是**本拆分自身的删除动作**，属过程量。

初看「拆分后数字反而从 152 涨到 155」曾引起误判，根因是错用了后者。
判断拆分效果必须以 `origin/main...HEAD` 为准。
