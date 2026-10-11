# Issue #39：Spec30 主线整合

执行授权来自用户于 2026-10-11 要求完成 [Issue #39](https://github.com/MrEcho114/PrivacyTrace/issues/39)，后续要求继续。交付分支为 `integration/spec30-20261011`，待审 PR 指向 main。合并、关闭工单、发布和部署仍需另行授权。

## 基线与逐文件决策

开始执行时重新 fetch 并通过 GitHub 核对：main 为 `4b066fecfef7b96b93a3866bef850d9dad7722d0`，#37 HEAD 为 `be3230e8ce056b4113460c1fd40340639c891e46`，#38 HEAD 为 `44275a29ccb8b243967777aaf14a51b611570e59`，两个旧 PR 均 OPEN。工作区无继承修改；未导入未跟踪研究资料。main/#38 merge-base 为 `1d0be28b09ecfd15e81de943c7e6c18daa239dd2`，main/#37 与 #38/#37 merge-base 均为 `7e2e018c18a9db4159687b932e0d9b064a8428ec`。不把 PR 返回的 base SHA 当作 merge-base。

从最新 main 建新分支，合并 #38 的提交；没有修改两个原开发分支，也没有合并 #37。实际文本冲突只有 `App.vue` 一处，其余下表项目进行了语义核验。

| 文件 | 处理与理由 |
|---|---|
| `apps/web/src/App.vue` | 同时保留主线 SDK 证据独立入口、25 条分页及重置，并接入 #38 受控来源、离线标签和只读控件。失败任务也显示受控来源；历史 UNKNOWN 和人工 UI fixture 不被新增来源区域描述成实际 CLI 扫描。 |
| `apps/api/src/privacytrace/models.py` | 以主线 `source_origin` 为基础增加 `CONTROLLED_APK` / `CONTROLLED_POLICY`；受控 APK 要求 CONTROLLED 来源。保留其他原输入与未知状态。 |
| `apps/api/src/privacytrace/pipeline.py` | 普通输入继续 REAL_SCAN、未知地区与原政策状态；受控入口核对扫描所得 APK/hash/package/version，再使用冻结场景事实。 |
| `apps/api/src/privacytrace/runtime_models.py` | 保留主线 `delivery_mode` 与 `sdk_attribution_limitations`，允许受控 APK 持久化。旧记录默认回放及 UNKNOWN 迁移边界保持原实现。 |
| 3 个 JSON Schema、`contracts.generated.ts` | 从 Python 权威模型执行 `scripts/export-schema.py` 重导出，不手工拼接。 |
| `docs/backlog.md` | 保留主线 SDK 与 JobStore 进度并加入 #38 的六场景记录；历史验证仍按其原版本解释。 |
| `.github/workflows/check.yml` | 逐字保留 main 已修复的 OasisViridis owner 与固定 SHA/policy-ref。 |
| JobStore、SDK 扫描/归属模块和已有测试 | 保留 main 实现，完整工程回归与原 Browser Acceptance 继续运行。新增浏览器观察 SDK 面板及其与政策判定的区别。 |
| `benchmarks/controlled/**` | 与 #38 HEAD 字节一致，包括源码、六份自建政策、特征、标签和所有锁文件。没有导入 #37 同名但不同含义的 CAMERA/MICROPHONE 场景。 |
| `docs/stages/spec30/*`、`spec30-verification.md` | 原样保留 #38 的历史证据；其中原 SHA 与 implementation hash 不代表此次整合的执行结果。新结果使用新的 CI artifact。 |

## #37 独有实现的取舍

| #37 能力/文件 | 决策 | 当前实现与理由 |
|---|---|---|
| `controlled_build.py` 源码编译、D8/AAPT2、确定性 ZIP | 已覆盖 | 使用 #38 六场景构建脚本与锁定官方归档，实际两次构建与冻结 APK 哈希比较。 |
| 本机 JDK24 / SDK37 / Tools36 路线 | 不采纳 | 与 #38 冻结工具链不同，不修改已冻结评测版本。 |
| `controlled_inputs.py` 输入/源码/政策/APK 绑定 | 已覆盖 | `controlled.load_features()` 与扫描后身份核对。 |
| 严格构建收据与工具链校验 | 移植 | 适配 #38 收据，核 schema、artifact_use、原工具链锁；补篡改收据/APK/源码负例，不引入旧数据模型。 |
| `controlled.py` 三方案预测 | 已覆盖 | `benchmark_algorithms.py` 在无标签、断网容器中对同一材料预测。 |
| `controlled_compare.py` 独立冻结和失败分母 | 已覆盖 | 原 `benchmark.run` 核真值摘要和输入锁，保留全部 18 行。 |
| 导入任意旧 prediction 的比较器 | 不采纳 | 当前 runner 消费本次子进程结果，并核对独立预测与持久化报告；没有任意预测导入需求。 |
| 比较器的伪收据、缺记录负例思想 | 移植 | 新 CLI 篡改测试及失败构建仍保留 18 行的外部回归；不引入旧 freeze API。 |
| `controlled_case_id` / `CONTROLLED_EVALUATION` 契约 | 不采纳 | 统一使用 Issue 要求的 CONTROLLED_APK/CONTROLLED_POLICY；来源仍是主线 CONTROLLED。 |
| 模型/流水线/网页来源能力 | 已覆盖 | 主线来源与投递方式，加 #38 受控事实适配；另修 HTTP 自报受控事实绕过 CLI 的问题。 |
| `test_controlled_cli.py` 标签注入拒绝 | 已覆盖 | 保留 #38 外部 CLI 回归，拒绝 expected_answer 输入且不创建 Job。 |
| `test_controlled_source_cli.py` 重建、篡改、CLI→HTTP | 移植 | 新 source CLI 专项测试覆盖 C02/C06 实际扫描与 HTTP；统一入口核两次源码构建哈希。 |
| Web 失败/加载状态仍显示受控来源 | 移植 | 从 activeJob 取得来源，失败态回归不依赖已生成报告。 |
| `controlled-scenarios.yml` 独立专项 CI | 移植 | 新 `spec30-integration.yml` 核交付 HEAD、六场景、普通入口边界、实际浏览器和独立断网，always 上传脱敏证据。 |
| `check.yml` owner 更名修正 | 已覆盖 | 最新 main 已包含，保留现有配置。 |
| `validate-controlled.sh` 专项入口 | 移植 | 以 `validate-spec30.py` 组合现有六场景能力；保留失败、独立运行目录及版本收据。 |
| `verify-controlled-browser.cjs` 两场景实际浏览器 | 已覆盖 | 保留 #38 浏览器脚本并新增主线 SDK 面板观察，不搬旧场景和固定 job ID。 |
| 旧 C02/C06 源码、政策、真值和 `toolchain.json` | 不采纳 | 与六场景冻结含义冲突，保持 #38 原定义。 |
| 旧受控 README | 不采纳 | 当前六场景 README 为可复现入口，取舍在本文件记录。 |
| `pt910-acceptance-20261010.md` 与旧收据 | 历史保留 | 通过 [不可变 #37 提交](https://github.com/MrEcho114/PrivacyTrace/tree/be3230e8ce056b4113460c1fd40340639c891e46/docs/stages) 查阅原失败、原 SHA 与两场景结果，不倒改或冒充本次验证。 |
| `docs/workflow.md` 专项交付责任 | 移植 | 记录工程、Browser Acceptance、六场景与离线验收各自的职责。 |

## 原评审缺陷映射

| 原评审 | 整合修复与证据 |
|---|---|
| [P2：构建失败后丢失比较结果](https://github.com/MrEcho114/PrivacyTrace/pull/37#discussion_r4237300257) | `validate-spec30.py` 记录构建阶段非零后仍执行 benchmark；构建收据缺失的场景保留为失败。`test_spec30_acceptance_runner.py` 实际调用空缓存构建失败路径，核 18 行、三个六场景分母和失败收据。失败不算验收通过。 |
| [P3：固定输出目录无法复跑](https://github.com/MrEcho114/PrivacyTrace/pull/37#discussion_r4237300259) | 默认时间戳+UUID 目录，随机 Job ID；显式输出目录须不存在，不覆盖历史。相同回归连续运行两次，核 run_id 不同且首次收据字节不变。 |

旧 PR 评审记录保持原状。本文件说明整合实现如何解决问题，不替旧 PR 标记 resolved。

## 新执行与证据

权威工程入口：`pwsh -NoProfile -File scripts/check.ps1`（委托 Git Bash 同一 `scripts/check.sh`）。本机缺 Ubuntu-24.04、Docker daemon 未运行，开启 Docker 的首次检查失败；无 Docker 的工程检查可以执行，所有跳过明确报告。实际 Docker 检查、源码重复构建与离线验收由新提交的 CI 执行，不使用旧 CI 代替。

新专项入口：

```bash
# npm ci、uv locked sync 后，在线准备与 #38 相同版本的测试浏览器
npm install --prefix tmp/spec30-browser --no-save --package-lock=false playwright@1.62.1
node tmp/spec30-browser/node_modules/playwright/cli.js install --with-deps chromium
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py
```

依次实际构建两次（不改变工具链）、核冻结哈希、构建原隔离 worker、C02/C06 优先的六场景/三方案比较、源码 CLI 与 HTTP 回归及普通 C02 信任边界、生产页面、浏览器、独立 `--network=none` 容器。Linux 输出容器使用非 root 调用者 UID/GID 写自己的 bind 目录；普通 APK 扫描的隔离用户与限制保持原样。

每次新运行的 `integration-receipt.json` 记录 commit SHA、工作区是否有修改、逐阶段返回码/耗时和证据文件 SHA256。CI 检出 PR HEAD，本次新结果只以 `dirty_checkout=false` 的交付 SHA 收据和对应 CI 链接为准。最终 PR 的 Verification 提供运行链接和实际计数；本文件不提前把待执行步骤写为通过。

专项 artifact 中包括两次 build-receipt、18 行 comparison、浏览器 proof/截图、断网 proof/DOM，以及统一收据。没有 APK、job store、原政策 capture、工具归档、原始日志或凭证。既有 GKD 1.12.1 真实案例保持版本绑定的历史记录，不称本次重新扫描；工程测试、六场景专项与真实案例分别报告，不相加。

## 风险与停止条件

受控 CLI 只接受冻结的自建材料。HTTP evaluate 不接受自报 CONTROLLED_APK；读取已持久化受控报告继续使用现有 HTTP 路径。回放标注来源和分析/打包时点，SDK 静态归属不参与政策判定。APK 哈希、冻结输入或工具链不一致时停止该路径，不静默改锁或真值。

六份自建政策沿用 #38 记录的提交授权；完整真实政策与 APK 不入库。历史 receipts 保留原 SHA。离线包仍仅内部核验，公开分发许可证和正式参赛提交授权待项目负责人决定；本任务交付到待审 PR，不自动合并或关闭工单。
