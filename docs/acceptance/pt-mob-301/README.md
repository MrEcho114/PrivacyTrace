# PT-MOB-301 端到端验收记录归档（2026-10-23）

> 归档对象：[#291](https://github.com/MrEcho114/PrivacyTrace/issues/291)、[#301](https://github.com/MrEcho114/PrivacyTrace/issues/301)。
> 两条记录同属 PT-MOB-301-E2E，引用同一方案 [docs/pre-submission-e2e-plan-20261021.md](../../pre-submission-e2e-plan-20261021.md)，但**基线不同、覆盖不同、结论不同**。
> 本归档逐字保留两份原文与 #301 的 10 份回执（行尾按仓库 `eol=lf` 规范化，正文文字未改动；另去掉抓取工具追加的末尾空行），只做索引、对照与缺口台账；不重跑、不改写、不折算任何历史判定。

## 0. 一句话结论

#291 在 PT-906-B4 原分支 head `682ca54` 上按自定的 R1–R4 电池记录“全部通过”；#301 在最新 `main` `83a7983` 上按完整方案（R01–R04 + F + H/N）复核，结论为**未全部通过**。两者不是同一基线上的同一套矩阵，任何一方都不能替代另一方。若引用“提交前方案门禁”的现状，应以 #301 的完整矩阵为准；#291 是另一组合上的历史执行记录，不构成该门禁的通过证据。

## 1. 归档内容

| 文件 | 内容 |
| --- | --- |
| [issue-291-baseline-682ca54.md](issue-291-baseline-682ca54.md) | #291 正文 + 唯一评论，逐字保留 |
| [issue-301-baseline-83a7983.md](issue-301-baseline-83a7983.md) | #301 正文，逐字保留 |
| [receipts/](receipts/) | #301 的 10 份回执，自本地分支 `codex/e2e-acceptance-20261023` @ `41d5019` 内容原样导入（行尾按 `eol=lf` 规范化） |
| [receipts/SHA256SUMS](receipts/SHA256SUMS) | 回执 SHA-256 清单（按 LF 规范化字节）；8 份与 #301 正文表一致，2 份为行尾差异，见 §7.3 |

## 2. 两条记录的定位

| 项 | #291 | #301 |
| --- | --- | --- |
| 标题 | 全流程端到端深度集成验收执行记录与收据核验 | 最新基线 `83a7983` 全流程端到端验收结果与缺口 |
| 作者 / Assignee / 标签 | `OasisViridis` / `OasisViridis` / `documentation` | 同左 |
| 抓取时状态 / 创建时间（UTC） | OPEN，2026-10-23T02:22:58Z | OPEN，2026-10-23T03:16:32Z |
| 抓取时更新时间 / 评论数 | 2026-10-23T03:17:06Z / 1 | 2026-10-23T08:57:16Z / 0 |
| 执行窗口（UTC） | 00:13:31 → 02:10:57 | 00:10 → 03:10（组织 → 收口） |
| 执行组织 | 多代理：编排器 + Worker 1/2/3 + 独立胜利审计员 | Team Lead + 5 条 lane + 2 个只读子代理 |
| 被测基线 | `682ca54`（PT-906-B4 原分支 head） | `83a7983`（`origin/main`，#262 合并提交） |
| 判据 | 方案文档 + 自定 R1–R4 验收项 | 方案文档 H12/N12/F10/R01–R04，状态只记 `PASSED` / `FAILED` / `BLOCKED` / `NOT_RUN` |
| 记录结论 | 1,818/1,818 校验通过；部署 40/40；`VICTORY CONFIRMED` | **未全部通过**：R01/R02/R04 PASSED，R03 FAILED 1 项，F 17/17 变体 PASSED 但未满足 10/10，H01 FAILED，N NOT_RUN |
| 入库证据 | 8 份 JSON 收据（`tmp/`，未入库）+ 交接文档（`.agents/`，未入库） | 10 份 Markdown 回执（本归档已入库）+ 原始证据（`tmp/`，未入库） |

## 3. 基线谱系（Git 事实）

| 项 | 值 |
| --- | --- |
| `682ca54` | `docs(acceptance): record PT-906-B4 third-party resource revision`，父提交 `ed0d28f`；位于本地分支 `codex/pt-906-b4-third-party-20261023`，**不是** `83a7983` 的祖先，也不在 `main` 历史 |
| 与 `83a7983` 的关系 | merge-base `4208823`；`682ca54..83a7983` 154 个提交，反向 5 个提交 |
| `83a7983` | `Merge pull request #262 from MrEcho114/codex/pt-906-b4-third-party-rc2`，parents `920d3cd` + `d40e24f`，tree `b3922fa3e808b6c9f6a4f4c19be00e3f3b53652f`，位于 `main` |
| `d40e24f` | PT-906-B4 rc2 分支 head（tip `d40e24f`，父为同主题提交 `b86a624`）；经 #262 合入 `83a7983` |
| 中间事件 | #256 于 `a1a6386` 回退 #236（原 PT-906-B4 第三方材料合并）；#261/#262 随后重新合入 rc2 |

结论边界：这里只陈述可回读的 Git 事实；`682ca54` 与 `d40e24f` 上的同主题提交是否逐 patch 等价，本归档未验证（UNKNOWN）。#291 与 #301 正文各自声明互不替代，本归档沿用该边界。

## 4. 覆盖对照

| 方案要求 | #291 | #301 |
| --- | --- | --- |
| R01 权威入口 | 覆盖：`check.ps1`/`check.sh`，1,778 项断言通过 | 覆盖：1684 passed / 183 skipped；e2e 65 passed |
| R02 引擎套件 spec30 + pt907 | 未记录（正文无对应项） | 覆盖：6/6 + 12/12，**PASSED** |
| R03 Web/移动壳 13 入口 | 仅前端单测 126 + `vue-tsc` + 构建；未记录验收入口 | 12/13 PASSED；`acceptance:mobile` **FAILED**（测试文案漂移） |
| R04 部署专项 R1–R6 | 覆盖：40/40 PASS | 覆盖：40/40 PASS + 1 项既有豁免（不计 PASS） |
| F01–F10 | 未覆盖；部署故障注入 R4 12/12 不等同客户端 F 组 | F01–F04、F07 A–D 共 17/17 变体 PASSED；F07-E **BLOCKED**；F08–F10 **NOT_RUN** |
| H01–H12 | 未覆盖 | 客户端安装/启动冒烟 PASSED；H01 **FAILED**；其余 **NOT_RUN** |
| N01–N12 | 未覆盖 | **NOT_RUN** |

数字口径：#291 的 1,778 分项相加为 1,591（API）+ 61（e2e）+ 126（web）= 1,778；再加部署 40 项得 1,818。该复算只是算术核对，正文未显式声明总口径。#301 的数字绑定 `83a7983`，不得与 #291 在 `682ca54` 上的读数直接比较。

## 5. 缺陷与缺口台账（合并）

#291 未登记缺陷，正文称“存量 15 项 Issues 状态已核对，本次集成测试未引入未记录的新增缺陷”。以下 6 项为 #301 登记的发现，归档时均**未修复**（该轮无修复授权）：

| # | 类别 | 发现 | 影响 |
| --- | --- | --- | --- |
| 1 | 仓库/构建 | `npm run android:prepare` 在 Tauri CLI 2.12.3 模板上失败：`apply-brand-android-icons` 要求不存在的 `mipmap-anydpi-v26/ic_launcher.xml` | 品牌启动图标未叠加，不影响功能 |
| 2 | 测试漂移 | `acceptance:mobile` 9 处选择器仍找旧文案（3 个标签），4 场景各 30 s 超时 | R03 记 FAILED；需测试维护 |
| 3 | CI 覆盖 | `browser-acceptance.yml` 未覆盖 `acceptance:mobile`、round2、a11y、primitives、brand-assets | 漂移长期未被发现 |
| 4 | 工具可移植性 | `scripts/verify-offline.py:30` 要求 POSIX 绝对路径，Windows 宿主无法收 PASSED | Windows 本地 R02 需走 WSL |
| 5 | 执行器/实验室 | `f134_common.Client` 默认 `Host: localhost` 与 `ALLOWED_HOSTS=PT_PUBLIC_HOST` 冲突；`provision.py` Caddyfile 缺 localhost 站点/SAN | 已用实验室级修复绕过，建议回归执行器 |
| 6 | 材料 | #256 回退了 deck、90s 视频、AI/第三方披露、PT-906 阶段材料（`apps/` 仅 3 文件 6 行文案/注释/测试） | 非 E2E 门禁，但影响提交包完整性 |

归档时另发现三项证据可用性缺口：

| # | 类别 | 事实 |
| --- | --- | --- |
| A1 | 证据不可得 | #291 正文所列 8 份 JSON 收据（`tmp/deployment-acceptance/`）在归档时不存在；所列 `teamwork_preview_victory_auditor`、`orchestrator` 交接路径也不存在，`sentinel` 等目录仅剩其它历史任务的文件。可复核的只剩正文数字与结论 |
| A2 | 证据不可得 | #301 的原始证据 `tmp/e2e/20261023/{r01,web,web-b,spec30-run3,pt907,deploy,faults,h,apk}/` 在归档时不存在；10 份回执保留了命令、时间线、SHA 与结论，原始日志/截图不可复核 |
| A3 | 入库状态 | #301 的 10 份回执原仅存在于未推送的本地分支 `41d5019`；本归档已原样导入（内容不变，行尾按 `eol=lf` 规范化），8 份哈希与正文表一致，2 份行尾差异见 §7.3 |

## 6. 归档时仍未处理的事项

以下来自 #301 的“需用户决定”，关闭 issue **不等于**已决策：

1. 是否接受 #301“未全部通过”的结论与缺口清单；
2. H/N 全矩阵是否另开补跑窗口（原文估计 1–2 个工作日）；
3. `acceptance:mobile` 选择器与 CI 覆盖缺口是否授权修复（仅测试/CI）；
4. H12 旧组合 FAILED 与 H01 缺政策原句区间是否单开缺陷票；
5. #256 回退的 deck/90s 视频/AI/第三方披露材料是否恢复；
6. #301 的执行分支 `41d5019` 是否另行推送（回执本身已由本归档保存；原始证据仍需另存才能复核）。

另：A1 所列 #291 收据与交接材料已不可得；若要复核其数字，只能重新执行或另找当时的本地副本。

## 7. 证据清单

### 7.1 #301 回执（本归档入库，哈希按 LF 规范化字节计算）

| 回执 | 内容 | SHA-256 |
| --- | --- | --- |
| [e2e-final-report-20261023.md](receipts/e2e-final-report-20261023.md) | 最终结论、缺口索引、需用户决定项 | `029155ff301b65c287d691e9cde70dbe316025bbd52855bbaf8c34ce1cd112a3` |
| [e2e-latest-baseline-20261023.md](receipts/e2e-latest-baseline-20261023.md) | 协调入口、lane 索引、环境事实 | `7322b4e760116e839d380de813112d56d403171de7b93021b670473dc817defe` |
| [e2e-r01-20261023.md](receipts/e2e-r01-20261023.md) | R01 权威入口执行记录 | `f131143bd58bb2372dad1f822b0f17419dab4fbd6e60240882524b9c06563076` |
| [e2e-engine-suite-20261023.md](receipts/e2e-engine-suite-20261023.md) | R02 spec30 / pt907 | `a2dff9ac97b8e9648c7ca31d7af4f3851aa8a49d7b236c735cc88a6ac7c5da6d` |
| [e2e-web-shell-20261023.md](receipts/e2e-web-shell-20261023.md) | R03 Web/移动壳 13 入口 | `408509186c0d7d92c3975991f020c93b4203e1b35ae4c846e5d744578546ca2b` |
| [e2e-deploy-20261023.md](receipts/e2e-deploy-20261023.md) | R04 部署专项 R1–R6 | `3708243bf09f17c5d8c668244764732dac85b3fd276e464cdbafced1096ef2ec` |
| [e2e-faults-20261023.md](receipts/e2e-faults-20261023.md) | F 组故障恢复 | `baaa614d0caf26b66b8826dafef512f35e82930601dcafa754b5b562816fa2d8` |
| [e2e-mobile-h-20261023.md](receipts/e2e-mobile-h-20261023.md) | H/N 手机组合与 H01 | `849adc382d0dcfa84a9e8aa7ce4b9788cbea3aff702d04194e986059d2ed1508` |
| [e2e-apk-build-20261023.md](receipts/e2e-apk-build-20261023.md) | 本基线 APK 构建与冒烟 | `a4a09f03c2e9284086301389df1c3494cf6b9f4efa41c648a055b3c67b1b6586`† |
| [e2e-baseline-impact-20261023.md](receipts/e2e-baseline-impact-20261023.md) | 旧收据对新基线的适用性 | `88ec9c3b252ad8f2fe880b055a0ba31fd79850c28e82e42a25c96b0bf4d48b50`† |

### 7.2 未入库/不可得证据

| 内容 | 位置 | 归档时状态 |
| --- | --- | --- |
| #301 原始执行证据 | `tmp/e2e/20261023/*`（分支 `41d5019` 记录） | 不在 Git；本归档核对时已不存在 |
| #301 执行分支 | `codex/e2e-acceptance-20261023` @ `41d5019` | 仅本地，未推送；回执已由本归档保存 |
| #291 8 份 JSON 收据 | `tmp/deployment-acceptance/*.json` | 不在 Git；已不存在 |
| #291 交接材料 | `.agents/teamwork/{teamwork_preview_victory_auditor,sentinel,orchestrator}/` | 不在 Git；所列路径不存在或内容属于其它任务 |

### 7.3 行尾差异说明（2 份回执）

仓库 `.gitattributes` 设定 `eol=lf`，本归档按 LF 规范化后的字节计算哈希。#301 正文表中有 2 项是在当时 CRLF 工作副本上计算的：

| 回执 | 正文表 SHA-256（CRLF 工作副本） | 本归档 SHA-256（LF 规范化） |
| --- | --- | --- |
| `e2e-apk-build-20261023.md` | `3a38d2e9c7abd3732a5004c4263083b3c9685355165670275aeeb216a2eaeb4e` | `a4a09f03c2e9284086301389df1c3494cf6b9f4efa41c648a055b3c67b1b6586` |
| `e2e-baseline-impact-20261023.md` | `d019d48a7e004b756d00c0b13b4df53f8648410d61cf46ebf7168e7a8aaefe87` | `88ec9c3b252ad8f2fe880b055a0ba31fd79850c28e82e42a25c96b0bf4d48b50` |

两份文件内容相同，差异只有 CRLF→LF；已用“CRLF→LF 规范化后的 SHA-256 = Git blob SHA-256”核对。其余 8 份正文表哈希与 Git blob 哈希一致。

## 8. 归档边界

- 未重新执行任何验收；未修改产品代码；未合并/部署。
- `PASSED` / `FAILED` / `BLOCKED` / `NOT_RUN` 全部保持原文；本归档不新增、不升级、不折算任何状态。
- 未导入 APK、完整政策、反编译全文、原始日志/截图、密钥、数据库或本机私有路径。
- 不替代 #128 父票结论、`docs/acceptance/` 既有历史收据，也不替代 #301 分支上的原始提交。
- 关闭 #291/#301 的语义是“记录已归档”，不是缺口解除、缺陷修复或交付验收通过。

## 9. 归档与关闭记录

- 归档变更：docs-only，合并提交以 `git log -- docs/acceptance/pt-mob-301/` 为准。
- 关闭记录：#291、#301 于 2026-10-23 以 `completed` 关闭，关闭评论均指向本文件。
- 原 issue 与评论保留在 GitHub，可继续追溯。
