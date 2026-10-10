# 协作约定

日常交付以根部 [AGENTS.md](AGENTS.md) 的 Context Router 和 [工作流](docs/workflow.md) 为准。

- 用户提出目标即可；复杂任务用 Issue，小修复可直接按会话授权执行。
- 一个主交付责任人负责范围、验证、完整 diff、push 和 PR；PR 模板与五项自审由代理完成，不再要求 A/B 签字或逐条评论。
- 验证统一运行 `bash scripts/check.sh`；Windows 的 `scripts/check.ps1` 委托 Git Bash。CI 使用同一入口并强制开启 Docker 回归。
- 代码通过、S1 技术验收与 PR 合并是不同状态。未经对应授权，不合并、发布、部署或改分支保护。
- 主线保持 Evidence Model → Taxonomy → Consistency Engine → Explainable Report。事实、声明、上下文推断分开；UNKNOWN 不编造。权限/静态 invoke 不证明实际采集或外传。
- SDK 政策不能替宿主补声明；没有足够政策证据时不返回“未声明”。组织流程豁免不把政策标为 REVIEWED，不改变合法性/安全性边界。
- 分类或匹配规则改变时更新版本、迁移说明和语义测试；不使用 LLM 作最终事实裁决。
- 不提交密钥、APK、个人数据、数据库或完整政策/反编译材料；不补造开发记录、访谈或评测数据。
- 保留未知本地改动；不强推、不移动已发布 tag。提交信息简短说明目的即可。
