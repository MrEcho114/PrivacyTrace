# Android 14 模拟器证据（2026-10-19）

## 原生平台阶段（较早记录）

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

## 同日后续：真实 Tauri 桥接实验

本节独立绑定干净源码 `44e5258f364897474192dd8ddabf39974da9d193`，不改写上面的原生平台记录。归档提交只增加证据/说明。两份新增设备 JSON 都是实际运行输出，`source_dirty=false`；它们同时记录各自安装产物的 SHA。相同 AOSP Android 14/API 34 模拟器，仍无真机证据。

| 材料 | 证明的范围 |
| --- | --- |
| [android34-bridge.json](android34-bridge.json) | 实际 Vue → Rust → Kotlin 的选择器取消、确认取消、HOME 暂停后恢复拒绝、同进程字号变化导致 Activity 重建后恢复，以及最后读取 base/feature split 的 UI 哈希逐一匹配 |
| [android34-shared-core-smoke.json](android34-shared-core-smoke.json) | 读取核心抽取到共享源码后，原生探针的两项普通应用 UID smoke 再次通过；这份收据的 unverified 只描述该 runner，桥接由上一份收据单独覆盖 |
| [android34-bridge.png](android34-bridge.png) | 干净源码运行后的真实 Tauri WebView 结果页，所选自建 fixture 版本 1、2 个包及两份实际摘要；独立视觉审阅确认内容完整 |

开发中先实际复现“同进程改大字号→新 Vue 页面→插件始终 BUSY_OR_INACTIVE”，随后修复 Activity 绑定和操作状态。新增字体用例真实修改专用模拟器的系统设置，并在 finally 恢复；既核对进程不变、新页面出现和选择器重新可用，也在恢复后重新读到两份正确 APK。它不证明 OEM、所有配置变化、进程死亡恢复或读取中取消的时延。

实际构建：Tauri CLI 2.12.3，Rust Tauri / JS API 2.12.4，Rust 1.99.1 Windows GNU 主机，JDK 17 / NDK r27c / AGP 9.3.1 / Kotlin 2.2.10 / Gradle 9.6.1，编译/目标 API 36，APK 只含 x86_64。最终 APK 权限仅 AndroidX 自定义 signature 接收器权限，无 INTERNET、存储或 QUERY_ALL_PACKAGES；备份与 cleartext 关闭。19 项 JVM、8 项 PowerShell 回归、原生四包与 Tauri APK 构建通过，原生 lint 通过；桥接 lint 0 errors / 2 个版本更新提示，Vue 类型/打包通过，npm 审计 0 项。构建/最低版本不是商店资格或系统范围验收。

真实手机、读取中取消/自然竞争矩阵、受保护配置、生产 Web 接线、HTTPS 与完整 #71 仍待完成；复现命令与接口边界见 [BRIDGE.md](../BRIDGE.md)。
