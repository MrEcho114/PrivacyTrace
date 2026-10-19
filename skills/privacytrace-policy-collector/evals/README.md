# 受控 Skill 行为评估

这三个提示词覆盖离线链接、未知来源的用户正文、取得正文中的指令注入。输入均为合成材料，example.invalid 不可访问；评估器不搜索、不调用个人模型、不读取 Key 或 APK。

使用 skill-creator 的同提示词原版／新版对照：原版快照来自本轮 main 基线；新版使用当前 SKILL.md。每轮每例每配置实际运行一次 gpt-6-luna。执行代理原始 JSON 由 [grade.py](grade.py) 交给现有 ExternalPolicyCollectionInput 与 import-external 接口评分，没有新增政策／原句业务验证器。

六项客观条件见 [evals.json](evals.json)：既有契约合法、取得状态和原文正确、类别不猜测、适用范围保持未知、外部时点真实、接口成功或原子拒绝。来源未知的输出可满足收集约定，但导入仍应 409；不能为了提高成功率猜官方类别。

评分入口：

```text
uv run --project apps/api --locked --extra worker python skills/privacytrace-policy-collector/evals/grade.py tmp/privacytrace-policy-collector-workspace/iteration-2
```

目录按 `eval-{id}-{name}/{with_skill,old_skill}/run-1/outputs/response.json` 组织；评分生成 grading.json，使用 text/passed/evidence 字段。提示词与六项条件固定，两轮之间不放宽评分。

完整输出与评分使用 skill-creator 自带 aggregate_benchmark.py 和 eval-viewer/generate_review.py 汇总／生成审查页；不复制第三方查看器到技能包。原始输出、生成后的查看器和临时工作区不随技能分发。可审计的响应、分数、模板／技能哈希保存在 [results.json](results.json)。

第一轮原版与新版均 17/18：原版把搜索包名写进适用范围，新版把无网络误判为 URL_ONLY。用户确认按现有三场景继续后，新版明确能力优先的状态顺序和搜索线索不得写入适用字段，再运行第二轮。最终分数以 results.json 为准。

这些分数只描述本次输出，样本很小，未做触发准确率优化或统计显著性检验。第二轮复用相同执行代理上下文，部分运行受并发限制串行启动；不能称为全新独立重复或盲测。大部分条件两版均通过，无区分度；离线例暴露了状态和适用范围两个不同缺口。代理工具未返回 token／耗时计数，timing.json 明确记为不可用；上游查看器中的零值代表缺失，不能据此比较成本或速度。人工审查反馈与自动评分分开，本轮不声称用户已逐项批准所有输出。
