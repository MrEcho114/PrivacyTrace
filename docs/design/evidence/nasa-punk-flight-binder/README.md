# 证据：NASA-punk Flight Binder 设计原型

状态：**设计研究/静态原型**，不是产品运行、不是 Android 实机/模拟器、不是 #160 验收。
源文件：[`nasa-punk-flight-binder.html`](../../nasa-punk-flight-binder.html) · 规范：[`nasa-punk-flight-binder.md`](../../nasa-punk-flight-binder.md)
源码 SHA：`f7c2a6ad725386dceefa7a617c4543df43c84254`（本目录截图采集时）。

## 截图

| 文件 | 视口 | 内容 | 平台 |
| --- | --- | --- | --- |
| `desktop-report-1440.png` | 1440×1000，fullPage 1085 | 桌面报告双页、索引栏、组件样例 | Chromium headless + 本地静态 HTML |
| `desktop-candidates-1440.png` | 1440×1000，fullPage | 候选/政策原文双页 | 同上 |
| `mobile-report-390.png` | 390×844，fullPage 1372 | 移动报告单页 | 同上 |
| `mobile-candidates-390.png` | 390×844，viewport | 移动候选 + 固定操作栏 | 同上 |
| `mobile-report-320.png` | 320×568，fullPage 1416 | 最窄边界 | 同上 |

均为固定中文内容 + 本地 CSS，无外部图片/字体/库/CDN；不执行 APK、模型、Docker 或原生桥。

## 已检查

- 1440/390/320 无横向溢出；白色画布、`#ECE5D6` 仅顶栏、主按钮 `#D63A2C`、四色身份条 4 段、0 个外部资源。
- `<details>` 可展开；键盘焦点有 ≥2px outline；按钮/链接/输入/摘要均可聚焦。
- 红色只出现在主 CTA、当前步骤/证据标记和铅笔提醒；四色条不映射业务状态。
- 对比度（文档计算）：红/白 4.67:1，墨/白 14.49:1，线/白 7.07:1，辅助/白 5.07:1；红/米白 3.72:1，不用于普通小字。

## NOT_RUN

- 真实 Android APK/设备/WebView、IME、安全区、系统字体缩放、TalkBack。
- 真实应用页面/现有 A–E 回归、200% 字号截图（原型为 px 字；实现需改 rem 后在应用内测）。
- 产品实现、合并、部署、发布；本目录不替代 #160 或 #136 的证据。

## 与 Codex 的关系

这是**并列第二方向**，不覆盖 Codex 在 [#142](https://github.com/MrEcho114/PrivacyTrace/issues/142) 的规范评论，也不修改其工作树。是否采纳、合并 token 或只吸收版式，由 #141 整合 owner/用户决定；在选定前不写入 `apps/web`。
