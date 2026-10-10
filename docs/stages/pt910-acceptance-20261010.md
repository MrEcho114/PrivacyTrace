# PT-910：C02/C06 源码链路验证记录

任务 [#31](https://github.com/MrEcho114/PrivacyTrace/issues/31)，[Draft PR #37](https://github.com/MrEcho114/PrivacyTrace/pull/37)。本记录对应 `744b7009cbf7209a926fabfe2505919ab84dcea4`，不把后续文档提交当作同一次运行。

## 实际完成的验证

- [源码专项 CI](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38043694460)：Ubuntu 24.04，源码重复构建、篡改拒绝、真值隔离、真实隔离 CLI → HTTP 共 **8 passed / 0 skipped**；随后重新冻结并运行两个独立场景。
- Chromium **145.0.7632.6** 实际查看两份 HTTP 报告，核对受控来源、API 字节码定位/完整描述符、政策原句及 C06 未知适用边界。两例均通过，page errors / console errors 均为 0；Agent 已查看两张完整页面截图。
- 本地 Windows 权威入口：API **312 passed / 14 skipped**，Web **13 passed**，Ruff、契约导出、类型及生产构建通过。跳过项不当作成功；本机缺少指定 Ubuntu WSL，两次场景扫描保留 `FAILED / CONTAINER_ERROR`，比较器仍保留 2 个目标、6 行弃判。
- 人工准备/核对时间：用户于 2026-10-10 明确回复 **0 分钟，未额外准备或核对**。源码、政策、候选由 Codex 编写，不声称真人复核；政策状态仍为 UNREVIEWED/PARTIAL/NOT_CHECKED。

## 三方案实际结果

固定计数单位为 `(case_id, data_type, ACCESS)`，2 个目标、每方案 2 行。权限能力行仍在原报告，不混入 API ACCESS 目标。

| 场景 | 独立预期 | 权限＋关键词 | API＋扁平匹配 | PrivacyTrace |
|---|---|---|---|---|
| C02 / CAMERA | EXACT_MATCH | EXACT_MATCH | EXACT_MATCH | EXACT_MATCH |
| C06 / MICROPHONE | INSUFFICIENT_EVIDENCE | EXACT_MATCH | EXACT_MATCH | INSUFFICIENT_EVIDENCE |

两次 Linux 扫描均 SUCCEEDED，DEX coverage COMPLETE、failed_dex 为空；这只表示支持的 DEX 处理完成。JADX 不可用，使用字节码证据，未声称恢复 Java 源码或运行时行为。两个朴素基线没有考虑 C06 的地区适用性，结果如实保留；2 个诊断场景不支持精度优势或统计代表性结论。

## 来源、哈希与时间

- JDK：Temurin 24.0.2；SDK：android-37.0 revision 2；Build Tools：36.0.0；Androguard：4.1.3；规则：0.3.0。
- 容器镜像：`sha256:39a333869dfecff391c045400da7ed9e94cb797644eea77d5b40c8ae26615df1`。
- C02 APK：`74ee535955306ba270558910d51edc0b2ea9c1ec10ae76c664d63ec2afc6dc14`；构建 1.403 秒，预测链路 0.927 秒。
- C06 APK：`08d45a9f0098f3c6def96715718d6a4822b70a4f1600b581ead6e94447b3e272`；构建 1.412 秒，预测链路 0.920 秒。
- 真值 SHA-256：`e2bbbac009dda14fdc06443648886b694f322b9e3c93c54e9fa1580f6c6d8639`；冻结时间 `2026-10-10T10:06:22.106896Z`，早于两次预测开始。
- [Actions 产物](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38043694460/artifacts/11666620918) 保存输入/源码/工具指纹、构建收据、脱敏报告、比较输出、截图和浏览器收据，2026-10-24 到期；ZIP SHA-256：`b6566d16666783ece3b585db2e89749cf3512b55e0a8c2ad93aff5f982b770a5`。下载后已核对该哈希。
- 永久保留的结构化摘要：[pt910-receipt-744b700.json](pt910-receipt-744b700.json)。不包含 APK、私有路径或完整反编译产物。

## Standards

独立规范审查未发现必修项；已修正文档中“唯一 CI”的过时描述。重复的输出路径安全检查可后续整理，本轮未扩张重构。

## Spec

独立需求审查发现三方案计算未计入耗时，已修复并复验；最终复核无新增必修代码缺陷。人工工作量已由用户明确提供。源码 → 隔离 CLI → 三方案 → HTTP → 实际浏览器已在上述 SHA 验证。

## 尚未通过的交付门

[中央 Check](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38043694540) 在创建任何 job 前失败：固定引用的 `OasisSaber/TheMasterplan/.github/workflows/themasterplan-check.yml@20eee37922175ad443270e1ab38df7ab38ca5d7b` 被 GitHub 报为找不到。尚未记中央 CI 通过，不把专项验收当作中央检查替代品。PR 保持 Draft，未合并；C01/C03/C04/C05、离线交付及真实 App 重跑不属于本记录。

后续定位到同一上游仓库 owner 已改为 `OasisViridis`，repository ID 仍是 `1309061768`。仅纠正 `uses` 地址并保留固定 SHA 和 policy-ref；此修复后的检查另绑定新 PR head，结果见 PR，不倒改本次失败记录。
