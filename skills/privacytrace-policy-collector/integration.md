# 接入、复用与验收边界

本包属于 #79。`COPY.txt` 整份复制即可使用，`SKILL.md` 使用同一模板生成。源码以 `provenance.json` 的相对路径、版本和 UTF-8/LF 哈希追溯。维护入口为 `uv run --project apps/api python scripts/build-policy-collector.py`；加 `--check` 检测漂移，不能手工改生成物掩盖漂移。

上游正文边界函数新增全局依赖或内部导入时，生成和检查均明确失败，先复核便携环境再更新生成器；隔离运行回归继续核对独立脚本与原函数的输出。

## 字段复用与确有缺口

| 需求 | 既有权威 | 本包处理 |
| --- | --- | --- |
| 来源地址、原文、版本、适用范围 | CollectedSourceInput、WebSource、PolicyDocument | source 字段说明从导入输入模型生成；原文逐字保留，未知字段保留原空值约定 |
| 发现与访问失败 | WebSource.status 是 ready/manual/empty/failed/url_only | 最小外层 state 区分仅网址、无网络、未找到、取得正文、用户正文、访问失败 |
| 外部取得/尝试时点 | WebSource.captured_at 由旧入口重新生成 | observed_at 单独作为外部自报信息；不能覆盖服务端时间或政策版本 |
| 候选与原句 | 既有 SYSTEM_PROMPT、WebCandidate、PolicyClaim | 一次一个选定 source.id，原提示词和边界函数自动导出，不新增声明协议 |
| 验证与状态 | 原句/taxonomy/码点核对、候选整合和审计 | 仍走原链路，checked=false、UNREVIEWED、PARTIAL、附件 NOT_CHECKED 保持 |

## 给 #70 / #72 的映射

#70 已随 PR #88 交付实际导入器、严格外层校验、公共模型和生成契约；本包消费该实现，不证明实例已部署。#72 拥有手机复制/回填和用户模型直连，相关入口已随 PR #120 合入 main（见下节）。本包不发送请求，不接收个人 Key，不创建另一套抓取器/校验器。

实际导入须校验 version、1–8 项结果、状态与正文一致性、source.id 唯一、未知字段/超限/畸形输入；source 复用 WebSource 校验。source_type 没有依据时先要求补确认，尤其不能靠模型默认值将未知来源当作官方来源。外部 state 和 observed_at 保留在导入审计，不直接塞进旧模型。

- RETRIEVED / PROVIDED：collector 导入分别保存 ready / manual，两者的 provenance 均为服务端派生的 EXTERNAL_CHAT_EXPORT；ready 只说明有正文，不冒充 DIRECT_WEB_FETCH。原 create 入口的正文规范化为 manual。
- URL_ONLY / OFFLINE 且有候选网址：正文为空、旧状态 empty，仅作为线索，不建 PolicyDocument。
- UNAVAILABLE：正文为空、旧状态 failed；旧入口会把错误统一为 SOURCE_UNAVAILABLE。
- NOT_FOUND / OFFLINE 且 source=null：没有来源可建，保留失败记录，不创建虚构草稿。

WebIntake.create 会清空 model_audit/final_url，重建 captured_at/sha256。导入器也自行生成时间、哈希和出处，不能让包装回填这些字段。外部时点不作为抓取收据。只有正文足够且通过既有校验才可形成政策材料；JSON 结构合法不证明网页真实或适用性。

可选准备工具复制现有 sanitize_untrusted_text / build_user_prompt 的源码及 SYSTEM_PROMPT。输出 source_id 是宿主上下文，messages 仍为原有模型消息；不把 source_id 作为模型候选字段。多来源逐个调用并绑定 source_id，候选交回旧验证器后再关联 WebCandidate，不拼接政策。用户已选择多份时依次处理，不强制缩减选择；网页分段标识由回填入口关联，不将段标题当候选字段。现有 start 以 require_checked=False 接受合法的未勾选候选；保持 checked=false 不阻止启动，也不把政策标为已复核。

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

## 已交付入口（2026-10-21 核对）

#72 的 Web/手机辅助入口已合入 main，本包仍是唯一指令源：

- 复制入口：`apps/web/src/policyCollector.generated.ts` 是 `COPY.txt` 的生成镜像（`node scripts/sync-policy-instructions.cjs`）。Web 与手机的“复制收集指令”都在原文后追加一条用户输入的应用线索 JSON，前端只做形状预检和来源类型确认；接受或拒绝仍由 #70 的导入器与旧校验器决定。
- 个人模型入口：Tauri 原生 `collect_policy` 只把同一提示词发送到用户配置的 HTTPS Chat Completions 端点，且拒绝与分析实例同源的地址；单次非流式、`max_tokens=8192`，Key 不返回 JavaScript、不进入分析服务。返回文本进入同一回填框，不自动导入。
- 两个入口都提交到 `POST /api/v1/web/drafts/{id}/import-external`，继续复用原句/taxonomy 校验、外部导入审计和同一报告构造，不新增 schema、抓取器或校验器。

维护约束：

- 改动本包后重新运行 `scripts/build-policy-collector.py` 和 `node scripts/sync-policy-instructions.cjs`；两者的 `--check`、Web 单测和本包兼容测试都会拒绝漂移。
- 原生 `collect_policy` 同时限制 UTF-8 字节和 UTF-16 长度不超过 32 KiB。当前原文约 9 KB，加一条应用线索仍远低于上限；扩展模板前先复核手机入口。
- 个人模型返回只是普通文本；是否联网、是否取得正文、来源类型与适用版本仍由用户和既有校验分别确认，不能由格式合法推出。

## 验证分类

examples.json 为合成材料，example.invalid 无效。自动化检查生成漂移、复制后独立运行、标记转义和单来源绑定，以及既有 HTTP/原句校验兼容。包装专项读取已发布 examples，直接提交现有导入接口；缺来源类型的示例预期 409，不偷偷补官方来源。三入口报告回归比较原 create、旧单来源导入和 collector/1 的同材料语义，同时保留不同出处；扫描使用合成 APK 和隔离扫描替身，不能冒充真实 Docker 或手机验收。

模型评估的提示词与评分入口见 [evals/README.md](evals/README.md)；评估复用现有模型和导入器，不提供业务验证器。已合入入口的复核、真实度分层和仍待验的外部模型／真机路径见 [compatibility.md](compatibility.md)。结构、来源 HTTP、受控模型行为、真实用户模型、真机和完整端到端分列；本包不把入口存在当作真实模型或真机验收。
