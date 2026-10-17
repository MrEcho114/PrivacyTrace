# 接入、复用与验收边界

本包属于 #79。`COPY.txt` 整份复制即可使用，`SKILL.md` 使用同一模板生成。源码以 `provenance.json` 的相对路径、版本和 UTF-8/LF 哈希追溯。维护入口为 `uv run --project apps/api python scripts/build-policy-collector.py`；加 `--check` 检测漂移，不能手工改生成物掩盖漂移。

上游正文边界函数新增全局依赖或内部导入时，生成和检查均明确失败，先复核便携环境再更新生成器；隔离运行回归继续核对独立脚本与原函数的输出。

## 字段复用与确有缺口

| 需求 | 既有权威 | 本包处理 |
| --- | --- | --- |
| 来源地址、原文、版本、适用范围 | WebSource、PolicyDocument | source 仅用既有输入字段；原文逐字保留，未知字段保留原空值约定 |
| 发现与访问失败 | WebSource.status 只有 ready/manual/empty/failed | 最小外层 state 区分仅网址、无网络、未找到、取得正文、用户正文、访问失败 |
| 外部取得/尝试时点 | WebSource.captured_at 由旧入口重新生成 | observed_at 单独作为外部自报信息；不能覆盖服务端时间或政策版本 |
| 候选与原句 | 既有 SYSTEM_PROMPT、WebCandidate、PolicyClaim | 一次一个选定 source.id，原提示词和边界函数自动导出，不新增声明协议 |
| 验证与状态 | 原句/taxonomy/码点核对、候选整合和审计 | 仍走原链路，checked=false、UNREVIEWED、PARTIAL、附件 NOT_CHECKED 保持 |

## 给 #70 / #72 的映射

#70 拥有实际导入器、严格外层校验、公共模型和生成契约；本包只是待消费的包装约定。#72 拥有手机复制/回填和用户模型直连。本包不发送请求，不接收个人 Key，不创建另一套抓取器/校验器。

实际导入须校验 version、1–8 项结果、状态与正文一致性、source.id 唯一、未知字段/超限/畸形输入；source 复用 WebSource 校验。source_type 没有依据时先要求补确认，尤其不能靠模型默认值将未知来源当作官方来源。外部 state 和 observed_at 保留在导入审计，不直接塞进旧模型。

- RETRIEVED / PROVIDED：source 原文字段可投影进旧草稿，旧入口会规范化为 manual；外部获取与用户材料的区别须另存，不冒充服务端抓取成功。
- URL_ONLY / OFFLINE 且有候选网址：正文为空、旧状态 empty，仅作为线索，不建 PolicyDocument。
- UNAVAILABLE：正文为空、旧状态 failed；旧入口会把错误统一为 SOURCE_UNAVAILABLE。
- NOT_FOUND / OFFLINE 且 source=null：没有来源可建，保留失败记录，不创建虚构草稿。

WebIntake.create 会清空 model_audit/final_url，重建 captured_at/sha256。外部时点不作为抓取收据。只有正文足够且通过既有校验才可形成政策材料；JSON 结构合法不证明网页真实或适用性。

可选准备工具复制现有 sanitize_untrusted_text / build_user_prompt 的源码及 SYSTEM_PROMPT。输出 source_id 是宿主上下文，messages 仍为原有模型消息；不把 source_id 作为模型候选字段。多来源逐个调用并绑定 source_id，候选交回旧验证器后再关联 WebCandidate，不拼接政策。用户已选择多份时依次处理，不强制缩减选择；网页分段标识由回填入口关联，不将段标题当候选字段。旧启动仍要求候选 checked，该门槛的业务变更归 #70，本包不自动勾选绕过。

## PR #88 候选导入接口

`POST /api/v1/web/drafts/{draft_id}/import-external` 接受本包的
`{"version":"privacytrace-policy-collector/1","results":[...]}`；远程模式使用该草稿的访问凭据。
非空来源须先明确 `source_type`；缺失时返回 409 `SOURCE_TYPE_CONFIRMATION_REQUIRED`，不写入草稿。
`source.id` 保留为草稿来源 ID，与已有来源冲突时整批拒绝。导入不联网，不把外部取得正文标为服务端抓取成功。

兼容的单来源格式仍为 `{"source":{...},"claims":[...],"summary":"..."}`，也须明确来源类型。
claims 继续经既有原句、类型及引用校验，保持未复核；摘要不进入政策原文。
标准收集包不增加 claims 字段，按返回的来源 ID 使用既有候选保存接口关联抽取结果。

外部 state、observed_at 和来源 ID/类别保存在草稿 `external_imports` 审计中，
经过后续抓取和提取仍保留，并进入报告 `tools.web_external_imports`；observed_at 是外部自报时点。
`source=null` 仅保留审计，不建虚构来源。每个草稿最多保留 64 次导入审计；批量失败不部分保存。
公共 schema 为 `web-external-collection-input` 和 `web-external-policy-input`。

## 验证分类

examples.json 为合成材料，example.invalid 无效。自动化检查生成漂移、复制后独立运行、标记转义和单来源绑定，以及既有 HTTP/原句校验兼容。Skill 结构、合成行为、真实联网、#70 新导入器、#72 手机直连与最终报告分别验收。本包未完成后三类，不因此关闭完整 #79。
