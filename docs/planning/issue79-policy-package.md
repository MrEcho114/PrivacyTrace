# PT-MOB-203：政策收集包装首轮盘点

2026-10-16；Issue [#79](https://github.com/MrEcho114/PrivacyTrace/issues/79)。
核对基线 main `e5124b07bcf0b24d8c098864dcbeae80a050c339`。
执行会话 `issue71-79-01a1443c-20261016`；本文件是前置调查，不是包装交付或导入兼容验收。

## 已有权威与复用

以下链接均固定到核对版本，后续包装须记录来源版本与内容校验值。

| 需求 | 现有权威 | 包装决策 |
| --- | --- | --- |
| 中英文声明抽取、固定 JSON 字段 | [policy_llm_extractor.py](https://github.com/MrEcho114/PrivacyTrace/blob/e5124b07bcf0b24d8c098864dcbeae80a050c339/apps/api/src/privacytrace/policy_llm_extractor.py) 的 `PROMPT_VERSION=1.0.0`、`SYSTEM_PROMPT` | 生成导出既有提示词；不手工维护第二份声明协议 |
| 来源网址、原文、主体适用范围与失败 | [web_models.py](https://github.com/MrEcho114/PrivacyTrace/blob/e5124b07bcf0b24d8c098864dcbeae80a050c339/apps/api/src/privacytrace/web_models.py) 的 `WebSource` | 复用 url/text/version/region/product/package_name/version_code；未知沿用各字段约定，不填猜测 |
| 引文、类型、主体、条件、目的与接收方 | 同上 `WebCandidate` | 保留 excerpt/data_type/polarity/subject/action/condition/declared_purpose/declared_recipient；包装不要求来源收集时生成候选 |
| 原文快照、复核及完整度 | [models.py](https://github.com/MrEcho114/PrivacyTrace/blob/e5124b07bcf0b24d8c098864dcbeae80a050c339/apps/api/src/privacytrace/models.py) 的 `PolicyArtifact`、`PolicyDocument`、`PolicyClaim` | 快照摘要、证据 ID 与时间由可信导入链路建立；不允许模型自报已复核或完整 |
| 原句真实性与 taxonomy | `policy_llm_extractor.py` 的候选校验 | 复用精确子串、重复引文歧义、码点偏移与 taxonomy 核对；JSON 合法不等于原句成立 |

## 来源发现缺口

`WebSource.status` 仅有 ready/manual/empty/failed，不能分别表达「只找到网址但未访问」「无联网」「未找到」。`error_code` 是自由字符串，但现有入口会规范化它，不能据此声称旧入口已经无损接收这些状态。

建议仅在收集结果外层表达上述发现状态；不向现有严格模型直接塞入新字段。最小外层字段名称与版本留待包装及 #70 薄适配共同确定。其必要信息是：是否实际访问、是否取得正文、失败原因，以及链接仅为候选的事实。它不是新的政策声明模型。

已取得正文与用户主动提供正文必须区分材料来源；来源适用性未知、政策版本未知及部分正文不因发现成功而升级。摘要、模型解释、搜索片段不冒充政策原文；不同来源保持独立。

## 旧入口的实际边界

[web_intake.py](https://github.com/MrEcho114/PrivacyTrace/blob/e5124b07bcf0b24d8c098864dcbeae80a050c339/apps/api/src/privacytrace/web_intake.py) 的 `create` 清空输入的 model_audit/final_url，重建 captured_at/sha256；有正文会规范化为 manual，无正文一般为 empty，失败码归一为 SOURCE_UNAVAILABLE。因此不能把网页工具声称的抓取时间、重定向网址或哈希作为服务端收据。

同文件 `captures` 保持文档 PARTIAL、UNREVIEWED；现有启动路径仍要求剩余候选 checked。#70 负责按新规格移除自动流程的强制逐条检查启动门，同时保留用户主动修正。本票只说明差异，不改启动行为，也不让包装自动填 checked=true 绕过现有限制。

## 首批验证与后续顺序

1. 包装输出从现有提示词生成，验证版本、字段、taxonomy 与源码一致，覆盖中英文及不可信文本中的指令。
2. 合成示例覆盖仅网址、正文、用户材料、无联网、未找到、访问失败、未知版本/主体，以及畸形 JSON、错误引文、重复引文。
3. #70 导入时复用旧验证器；与原入口比较来源分离、原句、偏移及未复核语义。当前尚无新薄适配，未声称本项通过。
4. #72 消费同一包装及映射，个人 Key 留手机；不把 APK、整机清单、任务凭据或 Key 放进指令、样例或包装产物。

首轮仅完成源码盘点与缺口定位；当时尚未生成 Skill、调用外部模型或完成实际联网行为验证。

## 包装实现与验证（2026-10-16 续）

已在 [skills/privacytrace-policy-collection](../../skills/privacytrace-policy-collection/SKILL.md) 交付便携入口、网页整份可复制指令、既有抽取提示词导出、合成示例与导入映射。`scripts/export-policy-collection.py` 从权威源码生成提示词/字段约束与 UTF-8/LF 哈希，`--check` 可检测漂移。

最小发现外层为 `privacytrace-policy-collection/1`：results 各项包含 discovery_status、source 及可选 reported_at。source 使用既有 WebSource 输入字段；仅新增发现状态及外部自报时点，避免把它们塞进服务端收据。source_type 未确定时不借原模型默认值宣称官方来源；导入前需要补确认。具体规则以包内 [导入映射](../../skills/privacytrace-policy-collection/references/import-mapping.md) 为准，#70 拥有实际接入、验证与公共契约，#72 拥有客户端。

- 19 项专项通过：版本/哈希一致性、引用便携性、8 个来源收集示例、8 个既有 Mock 抽取校验场景及原 HTTP 入口投影语义；不是新导入器验收。
- Skill 结构验证通过。一次独立离线合成走查中，用户正文中的注入指令作为原文保留，未写 checked 或已核验标记；网址与无联网分别记录。该走查不证明真实联网或普遍抵抗注入。
- 本地权威入口通过：API 787 passed / 20 skipped（未开启 Docker），Web 46 passed；Ruff、既有用户研究准备包检查、公共契约零差异、类型和生产构建通过。补充外部自报时点说明后重跑专项与生成检查；源码行为未变。

尚未执行真实来源发现、真实网页模型收集、#70 新薄适配、#72 手机调用及最终远程报告验证。完整工单保持开放；本次仅交付其可独立完成的包装，公共模型、生成契约与 CI 未改。
