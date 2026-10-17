# #71 平台调查与验证记录

日期：2026-10-17。授权：当前用户恢复 #71 并明确授权独立 Android PoC。基线：main `48648b0a1e53038b55a964199e719189045aec6c`。分支：`codex/issue71-platform-poc`。本文件是部分交付记录，不关闭完整工单。

## 一手资料与实现判断

| 来源（本轮查阅） | 支持的事实／本实验的选择 |
| --- | --- |
| [Android 包可见性](https://developer.android.com/training/package-visibility)；[声明 queries](https://developer.android.com/training/package-visibility/declaring) | Android 11+、target 30+ 的查询会被过滤；queries 能按包或 Intent 声明可见范围。本实验采用 MAIN/LAUNCHER queries；没有“全部已安装应用可见”的结论。 |
| [ApplicationInfo](https://developer.android.com/reference/android/content/pm/ApplicationInfo)；[PackageInfo](https://developer.android.com/reference/android/content/pm/PackageInfo) | sourceDir / splitSourceDirs 描述安装包位置；splitNames 描述当前安装 splits，lastUpdateTime 描述最近更新时间。本机 SDK 34 的公开 API 同时核对。文档字段存在不能证明任意 OEM 上 APK 字节都可读。 |
| [Google Play 广泛包可见性政策](https://support.google.com/googleplay/android-developer/answer/10158779) | 整机清单属敏感信息；QUERY_ALL_PACKAGES 要满足核心用途、说明较窄方案不足并完成声明。PrivacyTrace 的批准状态未知。本 PoC 不申请该权限，也不据本地成功推导上架资格。 |
| [Tauri 移动插件](https://v2.tauri.app/develop/plugins/develop-mobile/)；[前置工具](https://v2.tauri.app/start/prerequisites/) | 正式插件可由 Kotlin Plugin / Command 暴露移动能力；完整 Android 壳还需 Rust Android targets、SDK/NDK 等。本次仅构建独立 Kotlin harness，没有 Tauri 桥接验收或替换技术栈决定。 |
| [AGP 8.4 兼容表](https://developer.android.com/build/releases/agp-8-4-0-release-notes)；[Gradle 8.7](https://docs.gradle.org/8.7/release-notes.html) | 选择已有工具可复现的 JDK 17 / SDK 34 / AGP 8.4.2 / Gradle 8.7，仅用于平台实验。Wrapper 校验值来自官方分发源。 |
| [Android feature module 配置](https://developer.android.com/guide/playcore/feature-delivery) | 自建资源 feature 与 base 使用同一应用配置/签名，以两个本机构建 APK 准备已安装 split 测试，不依赖商业 APK 或商店下载。 |

结论是**值得按 Tauri 2 + Kotlin 接缝继续真机验证**，不是“平台可行性已证实”。读取只覆盖当前安装集合，不含尚未下载的模块；对工作资料及其他用户不作越界查询。

## 本轮验证事实

- 新增 14 项 JVM 测试通过（0 skipped）：已知 SHA-256、单 APK、全部 split、顺序稳定、重复/缺失/错误包名、版本/时间/路径/split 变化、读取后卸载、不可见、不可读且关闭流、流增长/缩短、预算及溢出、取消、split 身份改变摘要。
- 探针主 APK、设备测试 APK、自建 fixture base 与资源 feature APK 均本机构建成功；`:app:lintDebug` 通过，零问题。首次 lint 的备份配置、图标和显示字符串问题已修复后重验，没有用 baseline 隐藏。
- 已核对主 APK 合并 Manifest：无 uses-permission，只有有限启动 Intent queries；没有网络权限、广泛包可见性或存储权限。设备 smoke 强制检查普通应用 UID，并在包不可见或期望包数不符时失败。
- ADB 查询返回零连接设备。**未安装到设备、未执行 instrumentation、未声称跨 App APK 可读、未测真实安装更新竞争或 UI。** 设备脚本语法、无设备拒绝及脚本级模拟通过；模拟核对参数转发、两用例收据，以及 adb 退出 0 但 instrumentation 失败时拒绝。模拟不作为设备证据，真实运行待设备验证。
- 仓库权威入口 `pwsh -NoProfile -File scripts/check.ps1` 通过：API 1053 passed / 71 skipped，Web 46 passed；Ruff、schema 零差异、类型及生产构建通过。未开启本机 Docker 专项；条件跳过和既有弃用警告保留。
- Wrapper JAR 已与 Gradle 官方 8.7 校验值逐字节哈希核对。Android 任务使用同版本本机 Gradle 8.7 运行；未把 Wrapper 首次联网下载作为已测事实。
- 最终提交与远端 CI 结果由对应 PR 和 #71 当前执行记录绑定实际交付 SHA；既有 CI 不包含新增 Android 任务。

没有提交 APK、完整政策、缓存、签名材料、本机私有路径或个人设备清单。所有假数据来自自建测试；文件摘要不是运行时行为、隐私安全或法律结论。
