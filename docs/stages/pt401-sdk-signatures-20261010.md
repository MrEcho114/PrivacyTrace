# PT-401 · 常见第三方 SDK 特征签名

日期：2026-10-10。工单：[#22](https://github.com/MrEcho114/PrivacyTrace/issues/22)（P1 #6，选做，A 负责）。
基线：`codex/s1-integrated`（PR #29 整合分支），即面向已合并 S0/S1 `main` 的当前交付基线。

## 交付内容

1. **有据签名规则集** — `rules/sdk-signatures.v1.0.json`，版本 `1.0.0`，状态 `LIMITED_SOURCED_SEED`。
   替换建仓期 `sdk-signatures.v0.1.json` 的 `SYNTHETIC_SEED_ONLY`（该文件保留为已被取代的合成快照，不删除）。
   每条签名记录 `package_prefixes`、`potential_data_types`、`source`、`source_url`、`license`、`verified_at`、`note`。
2. **包路径归属模块** — `apps/api/src/privacytrace/sdk_attribution.py`。
   按包段边界匹配，最长前缀优先；平台与语言运行时命名空间（`android`、`androidx`、`java`、`kotlin`、`com.android`、`org.apache` 等）一律排除。
3. **扫描接入** — `apps/api/src/privacytrace/apk_worker.py`。
   `scan(..., sdk_rules=...)` 在 DEX 类遍历中产出 `kind=SDK`、`status=STATIC_POTENTIAL` 的证据；CLI 新增 `--sdk-rules`（缺省启用，传空可关闭）。
   worker 镜像 `worker.Dockerfile` 增加该规则文件拷贝，容器内可用。
4. **回归测试** — `apps/api/tests/test_sdk_attribution.py`（匹配层）与 `apps/api/tests/test_sdk_worker.py`（端到端 worker 装配）。

## 评审后修复（2026-10-10，同日）

首次提交后经两轴代码评审（`docs/stages/pt401-code-review-20261010.md`），对确认的缺陷做了修复：

| 编号 | 问题 | 修复 |
| :--- | :--- | :--- |
| SP1 | SDK 截断警告被写入 `coverage.behavior_limitations`，而本模块不产生任何行为；前端把该字段渲染在"行为识别"标题下，会把 SDK 缺口误读成行为缺口 | 新增独立字段 `coverage.sdk_attribution_limitations`（`runtime_models.ScanCoverage`），截断警告改写入此处；`App.vue` 增加独立的第三方 SDK 归属段落 |
| S1 | 新增的版本化规则集未纳入契约生成，与其他资源相比缺少模型权威 | 新增 `sdk_ruleset.py`（`SdkSignature` / `SdkSignatureRuleset` 模型，校验前缀形状、来源 URL、日期格式、前缀冲突与重名）；注册进 `scripts/export-schema.py`，产出 `packages/contracts/sdk-signatures.schema.json` 与 TS 类型；契约测试断言磁盘规则集可通过模型校验 |
| S2 | `resources.py` 中两个版本化加载函数逐行重复 | 抽出 `_load_versioned()`，两个入口共用同一套"版本 → 快照 → 版本自校验"机制 |
| smell | 描述符解析重复实现、匹配结果用裸 dict、`attributed` 命名含糊、魔数 500 内联 | worker 复用 `descriptor_to_class()`；匹配返回模型实例而非 dict；`attributed` 改为带类型注解的 `set[tuple[str, str]]`；提取 `MAX_SDK_ATTRIBUTIONS` 常量 |
| 越界 | `docs/backlog.md` 把 PT-402..PT-406 一并改写为"已完成"，但本次只交付 PT-401 | 回退 PT-402..PT-406 为"待开发"，仅保留 PT-401 一行 |
| SP3 | worker 级正例只覆盖 11 条签名中的 4 条 | 补足全部 11 条签名，并加 `test_every_shipped_signature_has_a_worker_level_positive` 守护：新增签名若无正例即失败 |

顺带修掉一个被静默吞掉的真实缺陷：重构时 worker 未导入 `descriptor_to_class`，`NameError` 被 `except Exception` 捕获后只记为 `DEX_PARSE_FAILED`，导致**所有** SDK 归属静默失效。除补上导入外，错误记录现在带上异常消息（此前只记异常类型），避免同类问题再次难以定位。

## 有据来源（厂商公开包名）

| signature | 厂商 | 包前缀 | 依据 |
| :--- | :--- | :--- | :--- |
| `sdk-amap-location` | 北京高德图强科技有限公司 | `com.amap.api.location` | 高德开放平台定位 SDK 下载页（合规告知标注包名） |
| `sdk-amap-maps` | 北京高德图强科技有限公司 | `com.amap.api.maps` | 高德地图开放平台隐私权政策 |
| `sdk-umeng-analytics` | 友盟同欣（北京）科技有限公司 | `com.umeng.analytics`、`com.umeng.commonsdk` | 友盟+开发者中心初始化与合规文档 |
| `sdk-bugly` | 深圳市腾讯计算机系统有限公司 | `com.tencent.bugly` | 腾讯隐私政策第三方 SDK 目录 / Bugly 接入指引 |
| `sdk-jpush` | 深圳市和讯华谷信息技术有限公司 | `cn.jpush.android` | 极光文档中心资源下载页（标注包名与版本） |
| `sdk-jiguang-core` | 深圳市和讯华谷信息技术有限公司 | `cn.jiguang.verifysdk`、`cn.jiguang.sdk` | 极光 Android 集成文档 |
| `sdk-tencent-map` | 深圳市腾讯计算机系统有限公司 | `com.tencent.tencentmap.mapsdk` | 腾讯地图 SDK 隐私文档 |
| `sdk-wechat-opensdk` | 深圳市腾讯计算机系统有限公司 | `com.tencent.mm.opensdk` | 微信 OpenSDK 隐私文档 |
| `sdk-mob` | 上海游昆信息技术有限公司 | `com.mob`、`cn.sharesdk` | 腾讯隐私政策第三方 SDK 目录（列出 `com.mob`） |
| `sdk-turingfd` | 深圳市腾讯计算机系统有限公司 | `com.tencent.turingfd` | 腾讯隐私政策第三方 SDK 目录 |
| `sdk-tencent-tbs` | 深圳市腾讯计算机系统有限公司 | `com.tencent.smtt`、`com.tencent.tbs` | 腾讯隐私政策第三方 SDK 目录 |

包前缀的公开性以厂商自己发布的说明为准（不依赖第三方博客的包名列示）。

## 验收对照

| 完成标准 | 证据 |
| :--- | :--- |
| 自建样本中能正确标记已知 SDK 特征范围内的调用点 | `test_worker_labels_known_sdk_packages`（15 条，覆盖全部 11 条签名的每条包前缀），断言 locator 含包路径、excerpt 含厂商；`test_every_shipped_signature_has_a_worker_level_positive` 守护覆盖率 |
| 负例：结构相似的自定义类不误碰 | `test_worker_does_not_label_lookalikes`（6 条：`com.tencent.buglyx`、`cn.jpush.androidx`、`com.example.bugly`、`androidx.*`、`com.android.*`、宿主自身类） |
| 不声称全量覆盖生态 | 规则集 `status=LIMITED_SOURCED_SEED` + `boundaries` 四条显式边界；`test_boundaries_state_the_limits_of_attribution` 断言边界文案存在 |
| 签名来源与版本可查 | `test_every_signature_is_sourced_and_versioned` 逐条断言 source/source_url(https)/license/verified_at |

## 边界声明（写入规则集并测试锁定）

- SDK 的静态存在**不等于**实际收集或外发；归属标签只描述包路径与已公开声明的对应关系。
- SDK 自身政策**不能替代**宿主 App 的声明，归属结论**不参与**政策一致性判定。
- 启发式归属**不构成法律主体认定**，也不推断第三方服务器地址或数据用途。
- 仅收录**有据的有限签名**，不承诺覆盖全国产生态。

实现上对应一条硬约束：SDK 证据**不生成**任何 `PrivacyBehavior`。
`test_sdk_attribution_creates_no_privacy_behavior` 断言没有任何 behavior 引用 SDK 证据，且 SDK 证据状态恒为 `STATIC_POTENTIAL`。

## 不做

- 不构建全量商业 SDK 数据库（11 条厂商签名，均为公开发布包名）。
- 不把“检测到某 SDK”判定为隐私违规。
- 不自动推测第三方服务器地址或数据用途。
- 不引入版本号级匹配（当前只匹配包路径；SDK 版本识别属后续工作）。
