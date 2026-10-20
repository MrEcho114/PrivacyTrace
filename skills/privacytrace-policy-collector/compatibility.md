# #79 扩展兼容矩阵

核验日期：2026-10-19。消费基线：main `ffbd2b7b7f99ed57a1468881083f649fb6d9b0d2`，已包含 PR #84 的便携包装和 PR #88 的导入适配。本轮只维护包装和测试，未改公共业务模型、手机、队列或部署。

协议仍为 `privacytrace-policy-collector/1`，抽取 prompt `1.0.0`，ruleset `0.3.0`。精确来源及导出哈希见 [provenance.json](provenance.json)，不能把这些版本当作政策的生效或适用版本。

provenance 只覆盖生成器引用的模型、提示词和规则文件，不覆盖 web_intake 的运行逻辑。下表的导入／启动／报告断言由上述完整 main 基线及兼容测试绑定，不把生成哈希表述为运行时验收。

## 字段到报告

| 包装输入 | 现有导入／模型 | 原句／报告中可见结果 |
| --- | --- | --- |
| source.id、title、url、text | CollectedSourceInput → WebSource | 原 ID 保留；PolicyDocument `web-{id}` 保存逐字正文和哈希，快照及原句证据关联该文档和网址 |
| source_type | 未知为 null，不继承内部 WebSource 的官方默认值；导入未知类别返回 409 | 成功导入不证明来源官方性；SDK 来源不变成宿主政策 |
| version、package_name、version_code、region、product | 仅政策适用范围进入 PolicyApplicability | 搜索线索不能确认适用范围；未知版本 UNKNOWN，其他字段保持空值 |
| state、observed_at | external_imports 审计 | 报告 tools.web_external_imports 保留外部自报时点和取得状态；与服务端快照时间分开 |
| 按来源抽取的候选数组 | 宿主关联 source_id 后交既有 candidates 接口 | 原句、类型和引用继续受旧验证器约束；checked=false、UNREVIEWED、PARTIAL、NOT_CHECKED 保持 |
| status／provenance／sha256 等 | 非收集输入字段；由服务端构造 | 外部取得正文仍标 EXTERNAL_CHAT_EXPORT，不冒充 DIRECT_WEB_FETCH |

## 成功、失败与拒绝

| 情形 | 预期消费行为 | 本轮／现有可复现证据 |
| --- | --- | --- |
| RETRIEVED／PROVIDED，有明确类别 | ready／manual，正文保持；区别存入审计，均为外部导入出处 | 包内 examples 直接提交现有 HTTP；现有全状态专项 |
| URL_ONLY／OFFLINE，有链接无正文 | empty、无抓取时间；没有 PolicyDocument 可生成 | 包内未知类别先 409；现有已确认类别专项验证 empty 映射 |
| OFFLINE／NOT_FOUND，source=null | 只留审计，不造来源；单独请求生成材料时拒绝缺正文 | 包内 examples 直接提交并验证无正文拒绝 |
| UNAVAILABLE，无正文 | failed／SOURCE_UNAVAILABLE；原始外部状态仍在审计 | 未知类别先 409；现有全状态专项验证 failed 映射 |
| 缺失或 null 来源类别 | 409 SOURCE_TYPE_CONFIRMATION_REQUIRED，整批不写入 | 包内示例和实际受控模型输出的 HTTP 评分；现有缺类别负向回归 |
| 未知 source_type、畸形 JSON／版本、重复 ID、超限、状态正文矛盾、外部服务端字段 | 422／409，整批不写入 | 复用 test_external_collection_import.py；本包不另写验证器 |
| 错误原句、类型或跨来源引用 | 候选保存拒绝，原草稿不变 | 三入口对比都执行这三类负向请求 |
| 多来源及模型摘要 | 正文和原句分开，摘要不进入正文 | 相同两来源经 create／旧单来源／collector 生成报告，语义和原句引用一致；出处按入口分别保留 |
| 未勾选候选启动 | 合法候选可启动；不自动勾选或提升复核状态 | 三入口报告测试均以 checked=false 启动成功 |

复现入口（仓库根目录）：

```text
uv run --project apps/api --locked --extra worker python scripts/build-policy-collector.py --check
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_policy_collector.py apps/api/tests/test_policy_collector_compatibility.py apps/api/tests/test_external_collection_import.py -q
```

专项首次完整复跑 83 passed。报告对比使用合成 APK 和扫描替身；导入、保存候选、引用校验与报告构造使用真实现有实现。权威全量和远端 CI 的最终 SHA／计数记录在本轮 PR 与 #79 当前执行记录，不在此文件预填通过。

## 证据分层与剩余工作

- 离线合成：包内全部示例、六状态和负向回归、三入口同报告对比。它们证明程序行为，不证明实际网页来源、模型联网或真机流程。
- 受控模型：三个提示词各做原版／新版两轮对照，模型为 gpt-6-luna；第二轮复用相同代理上下文，受并发限制，部分运行串行启动。原版第三例代理此前读过原版集成代码。不是独立重复样本或盲比较，不能据此推断普遍成功率。结果与限制见 [evals/README.md](evals/README.md)。
- 真实来源尝试：本轮网页阅读工具能取得 [Signal 公开政策页面](https://signal.org/legal/)，但本机现有 fetch_policy 对同一 HTTPS URL 抛 FETCH_TIMEOUT。本机请求应为 UNAVAILABLE，不能写成 RETRIEVED；未取得本机正文，所以没有声称该次请求完成导入、原句或报告。该事实不证明网站普遍不可访问，也不绕过现有抓取安全边界。
- 真实个人模型／网页聊天：未调用用户个人模型 API，未在第三方聊天网站发送材料；受控模型对照不代表这些入口完成。
- #72 手机复制回填、个人 Key 直达模型、真实设备及 #80/#81 部署端到端：未验。仍由对应 owner 实施，#79 不修改共享实现，也不是 #73 主链路关闭的硬前置。

本轮交付到 PR／CI；#79 保持 Open。后续关闭需真实扩展入口和约定来源／模型／手机证据，不能以本矩阵、PR #84/#88 或旧 CI 替代。

## 2026-10-21 更新：已合入入口复核

上一节记录的是 2026-10-19 的事实。其后 [PR #120](https://github.com/MrEcho114/PrivacyTrace/pull/120) 合入 main `19c9ebff7452d4b16e323eda26d0d032a42e5888`，#72 已关闭；#71、#80、#81 也已交付。本节只补充对已合入入口的核对，不改变协议、示例、评分或此前的证据分层。

入口与实际动作：

- 复制入口：Web/手机的“复制收集指令”直接提供本包 `COPY.txt` 的生成镜像 `apps/web/src/policyCollector.generated.ts`，只在末尾追加一条用户输入的应用线索；前端只做形状预检和来源类型确认。
- 个人模型入口：手机原生 `collect_policy` 把同一提示词发到用户配置的非分析同源 HTTPS 端点；Key 不返回 JavaScript、不进入分析服务，返回文本仍需回填并确认来源类型。
- 两个入口都提交既有 `import-external`（collector/1），复用原句/taxonomy 校验、外部导入审计和同一报告构造。

2026-10-21 在 main `19c9ebf` 上的复核：

| 检查 | 实际结果 |
| --- | --- |
| `scripts/build-policy-collector.py --check` | current |
| 包装、导入、三入口同报告专项 | 85 passed（本轮新增结构与镜像检查） |
| Web 单测（含 `COPY.txt` 与生成镜像一致性） | 111 passed |
| Web 类型检查与生产构建 | 54 modules，通过 |
| `npm run acceptance:mobile` | PASS；生产 Vue + native bridge 替身，1 次 start、0 浏览器 API 请求，390/1440 与大字号截图 |
| 完整 `scripts/check.sh`（`PRIVACYTRACE_DOCKER_TESTS=1`） | API 1531 passed / 183 skipped；e2e 65 passed；Web 111 passed；Ruff、契约、类型与构建通过 |
| 本机真实网页抓取 | 本机无出网，HTTPS 连接超时；按 UNAVAILABLE 记录，未称取得正文 |

仍未验证：实际个人模型端点／付费调用、第三方网页聊天复制粘贴、#72 真机与完整 Tauri IPC、完整 APK 扫描及部署组合；这些属于 #72／#73 的验收项，不由本包或本节替代。原生 32 KiB 提示词上限和具体模型协议兼容性未实测。

本节新增的自动检查只覆盖包装结构、相对链接、入口镜像和原生提示词上限；结论限于“已合入入口消费同一包”，不升级任何政策复核状态，也不把桥接替身走查当作真机证据。
