# 交付工作流

用户只说要做什么，不再填写双人核验表。复杂任务用 Issue，简单任务直接引用会话授权；代理负责执行和记录。

1. 主交付责任人确认范围、工作区和已有改动；按 AGENTS.md 只读相关规则。
2. 在任务分支实现并运行 `bash scripts/check.sh`，修复本次引入的失败，阅读完整 diff。
3. 代理填写 PR 模板、自审和验证结果并推送；等待中央 CI 通过。有问题继续修，不把工作转回用户填表。
4. 用户决定是否合并。验收、merge、release、部署各按授权边界，不自动串联。

## 采纳信息

- 来源：TheMasterplan `v5.0.0` / `20eee37922175ad443270e1ab38df7ab38ca5d7b`，固定中央 reusable workflow；selection/state 与执行器受 hash 检查。
- 范围：中央调用 + AGENTS.md 管理块、core、Git profile、薄 Skill、受管 CLI；项目自己的测试入口和说明仍由项目维护。未初始化 jj，不改全局模型、MCP、登录、sandbox 或 GitHub 保护。
- 日期：2026-10-09。授权：本会话用户要求采纳 themasterplan、撤销繁琐复核，并授权 push/PR。
- 当前首次交付：PR #29；验证与最终交付 SHA 在该 PR 记录。合并前不把分支内采纳写成 main 已采用。
- Git 2.55.0.windows.2 / Git Bash 5.3.15 / Windows + PowerShell 7。目标平台验证结果见 PR；包含合并/清理的完整采用烟雾仍为 PARTIAL，未获合并授权，不宣称完成上游全平台演练。

## 不变的边界

S1 双人门槛已撤销，见 [接受决定](stages/s1-acceptance-20261009.md)。产品的本地备注可选，既不是账号认证，也不是政策已复核证明；不要求用户填写。

`.github/workflows/check.yml` 是唯一交付 CI，通过固定 v5.0.0 调用中央检查，使用 `scripts/check.sh` 执行全部 API/web 回归及 CI 的 Docker 分支。自动检查由代理维护，不新增人类表单。

缓存、事务记录、私人样本不提交。升级不自动进行；日常实现不预加载发布/升级资料。采纳工具可运行 `.themasterplan/bin/themasterplan.py verify/doctor/check-update`。

首次只读版本检测发现 v5.1.0 已发布。本次按所加载的技能与已审阅来源固定 v5.0.0；不自动生成升级计划或升级，中央 uses/policy-ref 保持一致。

## 首次交付的本地检查

2026-10-09，Windows 同一权威入口开启真实 Docker：API 308 passed / 0 skipped（112.01 秒，一条既有 Starlette 弃用警告），Web 11 passed / 0 skipped，Ruff、schema 导出零差异、类型/生产构建通过。verify/doctor 和中央消费者契约通过；执行器与固定来源逐字节一致。远端中央 CI 另在 PR29 绑定实际交付 SHA，不用旧 CI 代替。
