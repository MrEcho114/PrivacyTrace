# Android 14 模拟器证据（2026-10-19）

运行源码：`76e7a577e205c5b27f9273fa0ec2ff44712e550b`，两份实际运行收据均为 `source_dirty=false`。后续证据归档提交只增加本目录文件，不修改执行源码。PR 的最终 CI 与本次 Android 运行源码分别绑定，不混用收据。

环境为 AOSP Android 14 / API 34 / x86_64（官方 system image revision 4）、Windows WHPX、普通应用 UID。用户确认本轮没有真机，因此下列结果均为**模拟器证据**。

| 材料 | 证明的范围 |
| --- | --- |
| [android34-smoke.json](android34-smoke.json) | 探针本体单 APK、另一受控应用 base+完整已安装 feature split；两次读摘要稳定，且各文件等于构建产物哈希 |
| [android34-update.json](android34-update.json) | 真实安装 versionCode 1→2；在 test-only 暂停点后继续旧快照读取，得到 UNREADABLE，拒绝完整结果 |
| [android34-negative.json](android34-negative.json) | 实际 Android instrumentation 对错误 SHA 返回失败码 0，artifact_hashes 阶段拒绝，未返回 PASS |
| [android34-result.png](android34-result.png) | 实际“选择受控应用→确认→结果”的界面，versionCode 2、两个包，显示的两份摘要均与受控版本 2 构建文件核对 |

普通 smoke 收据的 `unverified` 只描述该 smoke 自身没有验证的内容；安装更新由另一份独立收据覆盖。更新实验在确定性调度点调用真实安装操作，不能推导自然竞争的发生概率。截图仅包含自建应用的界面与摘要，不含整机列表、设备序列号、路径或 APK 字节。

仍未覆盖：真机/OEM/工作资料、自然更新/卸载竞争、后台取消、Tauri 桥接、受保护配置、远程上传和生产运行时。没有关闭 #71，也没有公开发布客户端。

本机 Windows 统一检查的环境限制、14 项 JVM 与 8 项脚本回归、构建及其他验证，见 [EVIDENCE.md](../EVIDENCE.md)；远端结果见 [PR #90](https://github.com/MrEcho114/PrivacyTrace/pull/90)。
