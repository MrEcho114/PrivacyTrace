# Android 安装包平台 PoC（#71 部分交付）

2026-10-17，用户单独授权的本机平台实验。它回答“怎样验证可见应用和当前安装包集合读取”，尚不能回答“哪些真机已经可用”。旧 PR #83 的实现没有复用。当前执行记录见 [#71](https://github.com/MrEcho114/PrivacyTrace/issues/71#issuecomment-6214077158)。

## 运行内容与边界

`app` 是 Kotlin 原生测试壳：主动列出可见的可启动应用 → 用户选中并确认 → 在普通应用 UID 下流式读取该 App 当前 base 与全部已安装 splits → 显示每文件和本机集合 SHA-256。只有主线程展示结果，读取在独立线程；取消或离开前台会取消结果交付。

- 不申请 `INTERNET`、`QUERY_ALL_PACKAGES`、存储、安装或跨用户权限，不使用 root；列表及摘要只在内存中，不复制 APK，不调用模型或服务端。
- 列表只是当前用户下可查询的启动应用子集。不可见与不存在均返回 `NOT_VISIBLE_OR_MISSING`，不据此判断安装事实。
- 每次读取前后重查包名、versionCode、更新时间、base/split 标识、路径、长度和修改时间。缺包、不可读、变化、超限或取消时不返回部分成功。它不是 Android 原子安装快照，也不能保证完成之后安装内容不再改变。
- 默认本机实验预算：64 个文件、单文件 128 MiB、合计 256 MiB。检查声明大小与实际流字节数，避免加法溢出；这些值不是服务端能力或 #70 限额。
- `localSetSha256` 使用带长度前缀的 UTF-8 字段：域 `privacytrace-local-package-probe-v1`、包名、十进制 versionCode，再按 base 优先／split 名排序，依次放入角色标识（`base` 或 `split:<name>`）、十进制长度、文件 SHA-256。它是 PoC 私有指纹，**不作为 #70 API 契约、上传凭据或报告证据**。

本实验只验证 Kotlin 平台接缝。正式客户端仍优先 **Tauri 2 + 现有 Vue + Kotlin 桥接**，没有基于缺少 Rust 工具链就改成原生客户端的架构决定。本轮不改现有 Web、API、模型、生成契约或 CI。#70 仍阻塞真实上传，#81/#73 的部署及端到端验收仍独立。

## 构建与本机检查

固定工具：JDK 17、Gradle 8.7（Wrapper 带官方 SHA-256）、AGP 8.4.2、Kotlin 1.9.24、Android SDK platform 34 / build-tools 34.0.0。配置 `JAVA_HOME` 和 `ANDROID_HOME`；首次构建需要访问 Google Maven、Maven Central 和 Gradle 分发源。已有完整缓存时可加 `--offline`。

在本目录运行（PowerShell 用 `./gradlew.bat`，Bash 用 `bash ./gradlew`）：

```powershell
./gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :fixture:assembleDebug :fixture_feature:assembleDebug
```

`minSdk=24` 和 `targetSdk=34` 仅为此测试壳的构建配置；不表示正式客户端最低版本已经通过真机验证，也不代表满足当前商店发布要求。APK、Gradle 缓存、签名材料和本机路径均不提交。

| 产物（相对本目录） | 用途 |
| --- | --- |
| `app/build/outputs/apk/debug/app-debug.apk` | 本机探针，可手动选择有权处理的 App |
| `app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk` | 设备烟雾测试，不显示整机清单或材料路径 |
| `fixture/build/outputs/apk/debug/fixture-debug.apk` | 自建受控应用的 base |
| `fixture-feature/build/outputs/apk/debug/fixture_feature-debug.apk` | 同包同签名的 install-time 资源 split |
| `app/build/test-results/testDebugUnitTest/` | JVM 算法回归 XML |
| `app/build/reports/lint-results-debug.html` | Android lint 报告 |

仓库根目录仍使用 `pwsh -NoProfile -File scripts/check.ps1`。该入口和既有远端 CI 不执行本目录的 Android 任务，需要分别报告结果。

## 设备验证入口

仅在已授权的测试设备上安装上述自建包；脚本会安装/更新探针、测试 APK 和受控 fixture，不读取任意个人 App。构建完成后，在本目录运行：

```powershell
adb devices -l
./verify-device.ps1 -Serial '<本次选择的测试设备>' -Receipt '<本机私有输出文件>'
```

设备不可用、包不可见、split 数不符、读失败或摘要不稳定时脚本失败，不产出 PASS 收据（包括清除本次指定路径上旧的 PASS 收据）。它检查 `am instrument` 的实际结果码及 PASS 内容；仅看 adb 进程返回 0 不足以判断测试成功。收据记录源码 HEAD、工作树是否有改动、APK 哈希、Android 版本、模拟器标记和明确用例，不包含设备序列号、整机清单、安装路径或个人包名。源码 HEAD 只供追溯；APK 哈希记录实际被安装的字节，不把可能有本地改动的构建当成可复现证明。

### 收据生命周期与脚本回归

指定 `-Receipt` 时，验证开始前会删除同路径的旧成功收据；如果旧收据无法安全清除，脚本立即失败，不继续执行设备操作。收据目录必须已存在，且目标路径必须是文件名。所有设备、Git 源码状态及 APK 摘要检查完成后，脚本在**收据同目录**写入唯一临时文件，再使用文件系统重命名发布完整 JSON；失败时清理临时文件。这样重复使用同一路径进行**顺序重验**时，失败不会让历史 `PASS` 继续充当本次结果。请勿对同一收据路径并发运行多个验证实例。

未提供 `-Receipt` 时仅向标准输出返回 JSON，不创建收据文件。失败不会输出成功 JSON。收据仍是本次本地测试的事实记录，并非云端上传确认。

无需 Android 设备即可运行模拟回归（需 PowerShell 7 或兼容 PowerShell、Git）：

```powershell
pwsh -NoProfile -File ./verify-device.tests.ps1
```

测试在此目录被忽略的 `.gradle/` 内创建隔离副本、伪 APK 字节与假 ADB 命令，覆盖先成功后无设备、缺 APK、安装失败、instrumentation 失败（ADB 退出 0）、成功重验替换收据、原子发布冲突以及省略 `-Receipt` 的 stdout 模式。自动删除临时环境，**不会连接设备、安装 APK 或产生真实平台通过证据**。现有根目录检查与远端 CI 不包含这组回归，必须单独运行并记录结果。

两个 smoke case：

1. 探针在自己的普通应用 UID 下读取本体单 APK，期望 1 个文件。这不是跨应用读取证据。
2. 同一探针读取另一个已安装的自建 fixture，期望 base + `fixture_feature` 共 2 个文件；连续两次的文件/集合摘要必须一致。只有实际设备通过才形成跨应用 splits 读取证据。

模拟器收据不替代真机收据。查看界面用 `adb -s <设备> shell am start -n org.privacytrace.probe/.ProbeActivity`，分别走查确认、取消、切后台和重新选择；截图只保留自建受控应用内容。

## 仍需实施与验证

| 场景 | 当前状态／下一步 |
| --- | --- |
| metadata 缺包、重复 split、尺寸不符、变化、不可读、取消、限额 | JVM 确定性回归；不冒充平台真实事件 |
| 真实 PackageManager 查询、跨 App base/splits 可读性 | 设备 runner 已准备，本轮无连接设备，待实测 |
| OEM / Android 24、30+、近期系统与工作资料隔离 | 待选代表真机；分别记录环境和可见性限制 |
| 安装期间更新／卸载、同版本重装、后台取消 UI | 算法守卫已测，真实系统竞争和界面仍待设备复现 |
| 无 Launcher 的应用 | 本实验不列出；先评估有限 queries 是否满足正式产品范围 |
| Tauri 2 → Kotlin 调用、生命周期与受保护配置 | 待搭建正式壳；桥只接收已选包名，不能接收任意文件路径 |
| HTTPS、实例隔离、服务端确认/背压、断网/恢复、删除 | 等 #70 合入并验证后消费稳定契约，最终由 #73 验收 |
| Google Play 权限材料与资格 | 尚未申请；构建可用不代表获批 |

平台调查和本轮执行事实见 [EVIDENCE.md](EVIDENCE.md)。
