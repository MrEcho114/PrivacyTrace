# PrivacyTrace S0 技术交接与阶段验收记录

- **日期**：2026-10-03
- **分支与提交**：基于 `main`（`ee23ddb`）建立 `codex/s0-contracts`，已成功推送到远程，远程 HEAD 核对为 `ec8f14bf116b6a86ba27a56dfbdab11272d850a1`（包含 4 个提交），`main` 未改动。
- **对应任务**：#7 PT-010、#8 PT-511、#9 PT-709，阶段跟踪 #2。
- **当前状态**：此前的 403 推送权限问题已由队友开通写权限解决。已创建 Pull Request #26（https://github.com/MrEcho114/PrivacyTrace/pull/26 ），状态为 open、非 draft、未合并，等待团队评审与合并。

## 1. 契约定义与规则更新（v0.2.0）

- **政策长文本**：`PolicyDocument` 全文放入 `artifact { text, sha256, normalization: NONE }`。文本上限 200,000 Unicode 码点，哈希采用 UTF-8。`normalization: NONE` 明确不修改原始换行（CRLF）与 emoji。
- **证据切片规则**：句子证据通过 `start_offset`、`end_offset`（Unicode 码点半开区间 `[start, end)`）定位，切片内容必须严格等于 `excerpt`（上限 10,000 码点）。快照证据引用 `artifact_sha256`，其 `excerpt` 可留空或放简短预览，短文本（<=10,000 码点）允许预览等于全文。
- **状态字段划分**：新增 `extraction_status`（NOT_STARTED / SUCCEEDED / PARTIAL / FAILED）、`review_status`（UNREVIEWED / REVIEWED）、`attachments_status`（NOT_CHECKED / COMPLETE / MISSING），与既有 `completeness` 独立，默认均为未完成。
- **声明语义判定**：`PolicyClaim` 包含 `polarity`（AFFIRMATIVE / NEGATIVE / UNKNOWN）、`condition`、`subject`（HOST_APP / THIRD_PARTY / UNKNOWN）。否定、附带条件或主体不明确的声明统一判定为 `AMBIGUOUS_DISCLOSURE`。静态分析中的 `purpose`、`recipient`、`transfer`、`temporal_scope` 始终为 `UNKNOWN`。
- **代码调用证据**：仅 `kind=API` 的证据必须填写 `api_call`（含 `target_descriptor`、`rule_id`、`ruleset_version`、`context`），其余证据类型禁止填写。
- **规则库映射**：`rules/taxonomy.v0.2.json` 提供 3 条真实 Android 示例规则（GPS 静态 `provider="gps"` 映射精确定位、未解析 provider 的一般 LOCATION、限定 contacts URI 的查询）以及 1 条仅限测试的 OAID 规则（真实 APK 禁止使用）。本阶段仅验证结构和规则匹配，不证明代码真实来自 DEX。
- **对照与冲突**：在比对冲突前，先判断包名、版本、地区、业务范围的适用性。未复核的正向声明不触发确定性跨来源冲突。判定强 `NOT_DECLARED` 需满足范围适用、快照完整、提取成功、完成复核且附件齐全。
- **类型同步与存储**：以 Python 模型为权威，通过 `scripts/export-schema.py` 导出 TypeScript 与 JSON Schema，遇未知类型直接报错，不降级为 `any`。SQL 结构已同步新增字段，但未接入运行时数据库连接，无自动迁移。

## 2. 真实样本与开发环境

- **首个样本 GKD**：开源应用 GKD v1.12.1（包名 `li.songe.gkd`，versionCode 92，体积 3,287,479 字节，SHA256 `edcc03be24bc54d44c04746b46e2e33244120638e2199450b4407195447466a6`，匹配官方 release 摘要）。样本存放在 `samples/private/` 并被 git 忽略，`git ls-files` 无 APK。元数据登入 `samples/real-world/manifest.csv`（manifest 内 policy 字段留空）。
- **候选政策**：官方政策候选链接为 `https://gkd.li/guide/privacy`（v1.0），记在交接资料中，标记为 `APK_FROZEN_POLICY_PENDING`，留待 S1 阶段处理。
- **校验脚本**：`scripts/verify-real-samples.py` 仅比对哈希并检查 ZIP 包内存在 `AndroidManifest.xml`，不运行 APK，不校验签名与 ZIP 规范。包名和版本由 Androguard 在临时环境中静态读取确认。
- **环境检查**：Node 24.17.0、npm 11.13.0、uv 0.11.23；项目虚拟环境 Python 3.12.13（`uv sync --project apps/api --locked` 成功）。系统 PATH 下的 python 是无法直接执行的 WindowsApps 占位符。检查 PATH 发现 JDK 与 Android SDK 未配置，未做全局修改，工具链选型留待 S1。

## 3. 验证与 CI 结果

- **本地验证**：
  - 后端测试通过：`uv run --project apps/api --locked pytest apps/api/tests -p no:cacheprovider`（120 项测试通过，含 1 个 Starlette/HTTPX 弃用警告）。
  - 静态检查通过：`uv run --project apps/api --locked ruff check apps/api/src apps/api/tests scripts/export-schema.py scripts/verify-real-samples.py --no-cache`。
  - 模式与前端构建通过：`scripts/export-schema.py`、`npm run build`、`npm run typecheck`。
  - 本地私有样本验证通过：`scripts/verify-real-samples.py`。
  - 界面核对：浏览器查看合成 demo 界面，显示切片位置数值、对应原句、“待复核”标签及 REVIEWED 文档状态（无原文高亮算法），截图见 `docs/stages/s0-report-proof.jpg`（为 demo 截图，非 GKD 分析）。
- **远程 CI**：针对提交 `ec8f14b` 的 pull_request CI 已成功通过（Verify scaffold run 37121821632）：https://github.com/MrEcho114/PrivacyTrace/actions/runs/37121821632 。api 与 web 任务全部 success，涵盖单元测试、Ruff 检查、Schema 同步校验与 npm build。远程环境不包含私有真实 APK 文件，脚本由测试 fixture 覆盖。后续提交文档会再次触发 CI，本次结果严格对应提交 `ec8f14b`。
