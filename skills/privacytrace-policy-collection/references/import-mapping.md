# 导入映射与交接

本包是 #79 的便携内容，`privacytrace-policy-collection/1` 是最小来源发现外层，非新政策声明格式。#70 拥有实际导入器、外层校验与公共契约，#72 拥有手机复制/回填和模型直连；这两项尚未完成，不把本说明当成可调用的新 API。

## 对既有入口的映射

1. 仅接受已支持的 format_version、1–8 项结果、下表列出的状态，以及收集指令列出的 source 输入字段。未知版本/字段、状态正文矛盾、重复 source.id、超限、畸形 JSON 应拒绝并保留明确失败。此为 #70 待实现的校验要求，不由 Skill 文本替代执行。
2. source 非 null 时按既有 WebSource 校验。URL_ONLY/FETCH_FAILED 必须有网址且正文为空；TEXT_RETRIEVED 必须有网址和正文；USER_PROVIDED 必须有正文；NO_NETWORK 可为 null 或只有候选网址的来源；NOT_FOUND 必须为 null。来源类型与适用性要有依据，source_type 不确定时请用户补线索，不借默认值宣称官方来源。
3. 外层 discovery_status 保留在导入审计，不能塞进 WebSource.status；可选 reported_at 为外部自报的获取/尝试时点，未知为 null 或省略。非空时须校验为带时区 ISO 8601，保持外部来源标记，不能覆盖服务端 captured_at 或冒充政策生效日期。导入材料的捕获时间代表接收时间，不能冒充工具原先抓取时间。

| 发现结果 | 旧草稿入口可表达的投影 | 必须另存或保留的区别 |
| --- | --- | --- |
| TEXT_RETRIEVED / USER_PROVIDED | 仅复制允许的 source 字段；有正文规范化为 manual | 外部工具取得/用户材料的区别；不声称本服务抓取成功 |
| URL_ONLY | source + status=empty | 未访问；不作为 PolicyDocument |
| FETCH_FAILED | source + status=failed | 外部访问失败；旧入口统一为 SOURCE_UNAVAILABLE |
| NO_NETWORK 且有 source | source + status=empty | 无联网而非已查找失败 |
| NO_NETWORK / NOT_FOUND 且 source=null | 没有可建的来源，不强造 DraftInput | 无联网与查找无结果分别告知 |

仅用于当前 Web 的手动回填时，逐来源粘贴正文/网址；无可用正文不能启动成功分析。旧 create 会清空 model_audit/final_url 并重建 captured_at/sha256；不从外部导入这些收据。未知适用字段按既有空值约定保存，version 默认为 UNKNOWN。取得正文、JSON 符合格式、网址来源真实与适用性成立是分别验证的事实。

## 可选候选抽取

`extraction-prompt.txt` 逐字导出现有 SYSTEM_PROMPT，覆盖中英文，版本见 manifest.json。只在已取得正文且明确请求抽取时使用。宿主应用继续复用既有 build_user_prompt 与不可信文本隔离，不自行拼接未经转义的边界。

候选 JSON 数组沿用 excerpt/data_type/polarity/condition/subject/action/declared_purpose/declared_recipient；#70 导入须复用原句、taxonomy、码点和候选整合校验，建立本地 id/source_id。重复原句须由既有偏移规则消歧。checked 默认 false，不伪造人工检查。原文保持原样，摘要与候选不能覆盖它。不存在新的声明校验器或一致性引擎。

当前 Web 启动仍要求剩余候选 checked；自动流程去除强制检查启动门归 #70，不用 checked=true 绕过。PolicyDocument 保持 PARTIAL、UNREVIEWED、附件 NOT_CHECKED，直至相应证据支持改变。

## 版本、更新与验证

在源码仓库运行 `uv run --project apps/api python scripts/export-policy-collection.py`，从现有提示词、WebSource 和 taxonomy 导出可复制指令、原抽取提示词及内容哈希。用同命令加 `--check` 检查漂移。manifest 的源码路径相对仓库根，哈希按 UTF-8/LF 计算，避免 Windows 换行差异；内容哈希不代表政策来源真实性。

完整复制 `privacytrace-policy-collection/` 即可携带 Skill；不需安装到全局、不含 Key、模型调用器或联网服务。网页工具只需复制 collection-instructions.md 并补所选 App 线索；可选抽取时单独使用 extraction-prompt.txt。模板与导出器仅供维护，不要求目标聊天工具运行 Python。

assets/examples.json 全部为合成材料，example.invalid 为无效域名；成功例仅表示结构和既有模型兼容。测试分列：生成一致性/Skill 结构、原入口 HTTP 材料投影与语义、Mock 候选校验。真实网页模型行为、来源发现、#70 新导入器、#72 手机模型与最终远程报告未验收。静态权限只代表能力、API 调用只代表潜在线索，不据政策或本包输出判断实际采集或违法/安全。
