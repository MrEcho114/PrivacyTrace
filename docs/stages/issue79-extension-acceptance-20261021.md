# #79 扩展入口验收记录（2026-10-21）

- 授权：用户在本会话直接要求完成 #79 的开发任务；本轮接续已结束的 2026-10-19 执行会话，是 #79 的唯一写入会话。
- 基线：main `19c9ebff7452d4b16e323eda26d0d032a42e5888`（PR #120 合并），已包含 #71、#72、#80、#81 交付；#72 已关闭。
- 范围：`skills/privacytrace-policy-collector/`、`scripts/build-policy-collector.py` 的维护与兼容验收，以及包装专项测试和映射说明；不修改 #70/#72 的 API、客户端、原生插件、CI 或部署。
- 已有事实：PR #84 的包装、PR #88 的导入适配、PR #111 的兼容矩阵与受控评估均已合入；本记录不重复这些实现。

## 入口映射

| 入口 | 实际动作 | 共同消费 |
| --- | --- | --- |
| 复制（Web/手机） | `collectionInstructions(app)` 输出 `COPY.txt` 的生成镜像，并在末尾追加一条 JSON 应用线索；用户自行粘贴到网页聊天 | 回填 JSON → `POST /api/v1/web/drafts/{id}/import-external` |
| 个人模型（手机） | 原生 `collect_policy` 把同一提示词发给用户配置的非分析同源 HTTPS 端点，Key 不返回 JavaScript | 回填框 → 用户确认来源类型 → 同一导入接口 |

两者继续使用既有原句/taxonomy 校验、外部导入审计（`web_external_imports`）与同一报告构造；没有新增抽取器、声明格式、校验器或抓取器。

## 本轮变更

- 新增 Skill 结构、引用版本与包内相对链接检查（`test_skill_structure_references_and_relative_links_resolve`）。
- 新增入口镜像检查：`apps/web/src/policyCollector.generated.ts` 必须逐字等于 `COPY.txt`；并从原生 Kotlin 源码读取提示词上限，验证“原文 + 200 字符应用线索”不超过 UTF-8/UTF-16 32 KiB（`test_web_and_mobile_entries_serve_the_package_prompt_within_native_bounds`）。
- 更新 `integration.md` 的已交付入口与维护约束；在 `compatibility.md` 追加 2026-10-21 复核与证据分层，不改 2026-10-19 历史结论。

## 验证

| 检查 | 实际结果 |
| --- | --- |
| `scripts/build-policy-collector.py --check` | current |
| 包装、导入、三入口同报告专项（3 个测试文件） | 85 passed |
| Web 单测 | 111 passed / 0 failed |
| Web 类型检查与生产构建 | 54 modules，通过 |
| `npm run acceptance:mobile` | PASS；1 次 start、0 浏览器 API 请求、0 page errors；390/1440 与大字号截图 |
| 完整 `scripts/check.sh`（`PRIVACYTRACE_DOCKER_TESTS=1`，2026-10-21 本机） | API 1531 passed / 183 skipped；e2e 65 passed；Ruff、契约零差异、类型与生产构建通过；输出 `PrivacyTrace checks passed.` |
| 远端 CI（Check workflow，Linux） | API 1535 passed / 179 skipped；e2e 65 passed；Web 111 passed；输出 `PrivacyTrace checks passed.` |
| 镜像负向对照 | 改动生成镜像原文后入口测试失败；还原后通过 |

跳过项按条件保留，未记为执行。本机与 Linux 的计数差异来自 Docker／平台条件，不把跳过项记为通过。

## 交付与远端 CI

PR [#122](https://github.com/MrEcho114/PrivacyTrace/pull/122)，base `main`。远端 Check、Browser Acceptance、Spec30 Integration 与 Deployment Baseline 以 PR head 绑定的运行结果为准；本机检查与远端 CI 分列，不用旧 head 的结果替代。

## 证据分层与未验项

- 结构、链接、镜像和提示词上限：仓库静态检查，可复算。
- 合成导入与同报告：使用合成 APK 与扫描替身；导入、候选保存、原句校验与报告构造使用真实实现。
- 手机入口：生产 Vue 加 native bridge 替身走查；不等于实际 Tauri IPC 或真机。
- 受控模型：2026-10-19 的 gpt-6-luna 两轮记录，小样本，未做盲测。
- 真实来源：本机直连 HTTPS 超时（环境仅通过本地代理访问外网，抓取按安全策略直连已验证地址）；此前网页阅读工具的局部摘录也不等于本机 fetch 成功。
- 未验：实际个人模型端点／付费调用、第三方网页聊天粘贴、#72 真机、完整 APK、部署组合；这些由 #72／#73 分别验收。

## 结论

包装与已合入入口的兼容性有可复现证据；#79 的独立范围具备收口条件。关闭与合并由负责人决定，本记录不代替 #72／#73 的真机与部署验收。
