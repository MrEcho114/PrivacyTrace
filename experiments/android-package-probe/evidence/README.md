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

## 2026-10-20：确认范围绑定与补缺验收

运行源码 `3bf5138db8dac6c58133380330bfad26ec6dab4c`，以下三份 JSON 均为
`source_dirty=false`，后续提交只归档证据/说明。用户已暂停 PR #90 合并，
本轮只补实验确认范围及验证，不关闭 #71。

| 材料 | 证明的范围 |
| --- | --- |
| [android34-confirmation-bridge.json](android34-confirmation-bridge.json) | 真实 Tauri 桥接 8 场景：既有取消/暂停/字号重建，新增确认版本/包数/逐包与总量、确认后同版本真实重装拒绝、受控 force-stop 后新进程清空旧确认，最终两份 UI SHA 与构建产物一致 |
| [android34-confirmation-smoke.json](android34-confirmation-smoke.json) | 本体单 APK、跨 App base/feature split 的普通 UID 设备 smoke，读取路径使用本轮确认快照约束；不能替代确认 UI 走查 |
| [android34-confirmation-native-walk.json](android34-confirmation-native-walk.json) | 宿主驱动的原生 UI 走查：确认元数据、返回取消、系统返回取消、重新选择后读取两份正确摘要；本机操作辅助脚本不随产品交付，步骤可按下文重现 |
| [android34-confirmation.png](android34-confirmation.png) | Tauri 原生确认窗口：versionCode 1、2 包/13525 字节、base 6679 与 split 6846 字节，以及重新确认告知 |
| [android34-confirmation-reinstall-rejected.png](android34-confirmation-reinstall-rejected.png) | 窗口打开后重新安装相同 APK，开始读取返回 INSTALLATION_CHANGED，没有成功摘要 |
| [android34-confirmation-result.png](android34-confirmation-result.png) | 重新选择确认后的完整摘要；两份 SHA 与本机构建 APK 相符 |

原生 UI 步骤：在已授权模拟器先运行 `verify-device.ps1` 安装自建探针/fixture，
打开探针，依次“选择可见应用 → Controlled split fixture → 返回”，确认 CANCELLED；
再次选择并用系统返回键取消；第三次选择并开始读取，核对两个 APK 的 SHA。
原生确认截图背景有系统应用列表，故只留本机、不提交；公开确认图使用无清单的 Tauri 图。

旧 APK 曾被新增确认信息断言明确拒绝；修复后 25 项 JVM 与上述实际场景通过。
带截图的预跑曾有一次底层设备命令/解析中断，未生成成功 JSON；本节只归档随后
独占设备、干净源码的成功运行，不将失败截图作为通过证据。字号恢复 1.0，临时 UI XML 清除。

这是同一 AOSP Android 14/API 34/x86_64 模拟器的受控实验。真实自然重装竞争、
任意系统进程回收/网络任务恢复、读取中取消时延、OEM/工作资料和真实手机仍未验收。
受保护配置、生产页面和真实 HTTPS/实例隔离缺口见 [ACCEPTANCE.md](../ACCEPTANCE.md)。

## 2026-10-20：本机受保护模型配置

运行源码 `6465f0e6889a01b7d436b325aa88712dd767f3c6`，以下三份 JSON 均为
`source_dirty=false`，APK 已在该干净提交重新构建，后续提交仅归档证据与说明。
同一 AOSP Android 14/API 34/x86_64 专用模拟器、普通应用 UID，未使用 adb root。

| 材料 | 证明的范围 |
| --- | --- |
| [android34-protected-model.json](android34-protected-model.json) | 18 项：真实 Keystore、不可导出的 AES 包装密钥、端点认证、篡改/缺密钥拒绝、不完整写入恢复、受控进程重启、遮罩控件无 Autofill type/value、原生取消、HOME/字号重建丢弃待输入、大字体键盘展开后取消、HTTP 拒绝、仅状态返回、改地址须新 Key、删除取消/确认及重启、本 UID logcat 不含合成 UI Key |
| [android34-protected-bridge.json](android34-protected-bridge.json) | 本轮 Tauri APK 的既有 8 场景回归全部通过；确认后实际同版本重装拒绝、force-stop 后清空、字号重建恢复，最终 base/feature split 的 UI SHA 与构建产物相同 |
| [android34-protected-smoke.json](android34-protected-smoke.json) | 本轮原生探针与测试 APK 的普通 UID 两项 smoke；本体单 APK 与跨 App base/feature split 的稳定摘要核对 |
| [android34-protected-model-status.png](android34-protected-model-status.png) | 同一保护配置成功运行的非秘密状态页，只有 `.test` 端点及状态；密码窗口不截图，不关闭 FLAG_SECURE |

复现见 [受保护配置](../PROTECTED-CONFIG.md)；设备 runner 使用固定合成值，结束后确认删除
两个实验 app 的测试配置。39 项 JVM、8 项 PowerShell、原生四包/lint、实际 Tauri APK 与
Vue 构建通过。桥接 lint 为 0 errors / 4 warnings；没有以更新依赖或关闭全局 lint 掩盖问题。

预跑曾因 `setSingleLine` 覆盖密码变换而失败；修正顺序后，真实 Android 断言密码变换、
保存状态关闭和超长输入哨兵，重新预跑与上述干净提交均通过。一次 smoke 宿主调用的相对收据
目录解析失败，设备验证未启动；改为显式输出路径后单独重跑通过，不将前次失败算作 PASS。

三份收据的 APK 哈希互相一致；系统字号已恢复 1.0，临时 UI XML 已清除。
独立需求、代码和非秘密状态视觉审阅无阻塞发现。此处不证明完整 ViewStructure/Autofill 服务、
IME、JS 存储或全部日志出口，也不证明硬件 Keystore、所有 OEM 备份/迁移、断电/fsync 故障持久性。
真实模型/TLS/重定向、生产 #72 接线、HTTPS 上传/实例隔离/背压/恢复及真机仍未验收。
#71 保持开放，PR #90 合并继续暂停。
