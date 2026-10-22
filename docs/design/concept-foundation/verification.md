# 验证与截图

这些是**实际构建产物在 Chromium 中的合成材料界面**，不是真实 APK/Android 实机，也不是用户上传的概念图重画。概念来源见 [规范](README.md)。

## 已执行

| 检查 | 结果 / 边界 |
| --- | --- |
| `npm run acceptance:design` | 87 项通过，22 张实际浏览器截图；5 种视口、空/未知/长文本、320/390 的 200% 文字、证据选择/定位/返回焦点、政策原文、字段/等待/禁用、skip link、减少动效、旧入口隔离 |
| 视觉合同 | 白色主要面板、仅顶栏米白、红主操作/白字、四色品牌与唯一重点信息条、1px 直角面板、Pioneer 三类字体角色；5 种错误样式/字体注入被守卫拒绝 |
| `npm run acceptance:frontend` | 既有导入/候选/报告/设置/焦点流程通过；14 个 mock 报告请求、12 项手机断言、政策辅助 10 项 HTTP/UI 检查通过 |
| 独立需求审阅 | 四项用户决定和静态证据语义符合；UNKNOWN 条目与报告复核状态矛盾已修复并补断言 |
| 独立标准审阅 | 完整新增组件/构建接线/验证逻辑审阅无未修阻塞；旧入口样式不依赖设计 CSS |
| 独立视觉审阅 | 常规双端符合参考；320px/200% 数量和色板逐字换行已改为自动单列并复看；最新对照结论四色重点条复看无阻塞 |
| 权威 `scripts/check.ps1` | 通过：API 1567 passed / 200 skipped，e2e 61 passed / 4 skipped，前端 111 passed；schema/治理/lint/构建通过。最后一处大字等宽标签换行样式修正后，重跑构建与87项专项通过；远端最终 SHA 的权威检查另由 PR CI 核对 |

[verification.json](evidence/verification.json) 包含代码输入 SHA-256、生成时间、逐项结果及 22 张截图哈希。仓库保留以下 6 张代表图，其余由专项命令生成，并由 CI 工件归档。输入哈希覆盖设计组件、样式、Vite 入口、package.json 与验证脚本，避免用自指的文档提交 SHA 伪造同版截图；最终交付 SHA 记录在 PR/Issue 中。

## 实际截图

- [1440 桌面完整报告](evidence/report-1440.png)
- [1280×720 首屏](evidence/report-1280-viewport.png)
- [390 手机完整报告](evidence/report-390.png)
- [390 组件展示页](evidence/components-390.png)
- [320 / 200% 报告](evidence/large-text-320-report.png)
- [320 / 200% 组件展示](evidence/large-text-320-gallery.png)

## 范围和未执行项

- 本轮不调用业务 API、模型服务或真实扫描；合成材料明确标记 DEMO。
- Android APK/WebView、物理真机、真实 IME、安全区、系统字体与 TalkBack：**NOT_RUN**。
- 完整导入→候选→进度→报告新视觉接入：留给 DS 后续开发；既有业务回归通过不表示这些页面已改为本次视觉。
- 没有合并、部署、发布或关闭原任务。
- 无新增运行依赖，复用已选 Vue/UiButton/UiField/StatusTag 和 Pioneer 本地字体。此次构建的独立设计资产约 17.02kB JS / 14.97kB CSS（gzip 7.09 / 3.70kB，另有与现有入口共享的 Vue/控件 chunk）；这不是整站包体差值。
