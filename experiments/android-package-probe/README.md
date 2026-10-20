# Android 安装包平台 PoC（#71 部分交付）

2026-10-17，用户单独授权的本机平台实验。它回答“怎样验证可见应用和当前安装包集合读取”，尚不能回答“哪些真机已经可用”。旧 PR #83 的实现没有复用。当前执行记录见 [#71](https://github.com/MrEcho114/PrivacyTrace/issues/71#issuecomment-6214077158)。

## 运行内容与边界

2026-10-20 接续：新增 [Android 包集合上传](UPLOAD.md)，含独立能力协商、原生上传确认、
按实例加密的访问材料、回执读回、刷新和删除。以下“仅本机”描述仍适用于原有本机读取入口；
上传使用单独命令和确认，不会因读取摘要自动发送材料。完整产品和部署验收保持未完成。

`app` 是 Kotlin 原生测试壳：主动列出可见的可启动应用 → 用户选中并确认 → 在普通应用 UID 下流式读取该 App 当前 base 与全部已安装 splits → 显示每文件和本机集合 SHA-256。只有主线程展示结果，读取在独立线程；取消或离开前台会取消结果交付。

- 本轮为原生只读 HTTPS 健康检查增加 `INTERNET`；不申请 `QUERY_ALL_PACKAGES`、存储、安装或跨用户权限，不使用 root。列表及摘要只在内存中，不复制或上传 APK，不调用模型；健康请求不携带这些材料，见 [HTTPS.md](HTTPS.md)。
- 列表只是当前用户下可查询的启动应用子集。不可见与不存在均返回 `NOT_VISIBLE_OR_MISSING`，不据此判断安装事实。
- 每次读取前后重查包名、versionCode、更新时间、base/split 标识、路径、长度和修改时间。缺包、不可读、变化、超限或取消时不返回部分成功。它不是 Android 原子安装快照，也不能保证完成之后安装内容不再改变。
- 选中后先读取受限的安装元数据，原生确认窗口显示版本、包数、逐包长度及总大小；此时不打开 APK 字节流。开始读取前再次核对确认快照，变化或已不可读时返回 `INSTALLATION_CHANGED`，必须重新选择确认。网页不能提供或修改该快照。
- 默认本机实验预算：64 个文件、单文件 128 MiB、合计 256 MiB。检查声明大小与实际流字节数，避免加法溢出；这些值不是服务端能力或 #70 限额。
- `localSetSha256` 使用带长度前缀的 UTF-8 字段：域 `privacytrace-local-package-probe-v1`、包名、十进制 versionCode，再按 base 优先／split 名排序，依次放入角色标识（`base` 或 `split:<name>`）、十进制长度、文件 SHA-256。它是 PoC 私有指纹，**不作为 #70 API 契约、上传凭据或报告证据**。

本实验保留 Kotlin 平台测试壳，并新增隔离的 **Tauri 2 + Vue + Kotlin 桥接验证壳**，详见 [BRIDGE.md](BRIDGE.md)。生产客户端仍采用这一优先路线，没有替换技术栈的架构决定。本轮不改现有 Web、API、模型、生成契约或 CI。2026-10-19，#70 的业务接口已随 PR #88 合入，生产运行时组合验收仍在 #80；本实验没有接入远程上传，#81/#73 的部署及端到端验收仍独立。

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

设备不可用、包不可见、split 数不符、读失败、摘要不稳定或与本机构建 APK 的哈希不符时脚本失败，不产出 PASS 收据（包括清除本次指定路径上旧的 PASS 收据）。它使用 `am instrument -r -w` 的 raw 输出检查实际结果码、PASS 和哈希核对标记；默认 pretty 输出会隐藏结果码，仅看 adb 进程返回 0 不足以判断成功。收据记录源码 HEAD、工作树是否有改动、APK 哈希、Android 版本、模拟器标记和明确用例，不包含设备序列号、整机清单、安装路径或个人包名。源码 HEAD 只供追溯；APK 哈希记录实际被安装的字节，不把可能有本地改动的构建当成可复现证明。

### 收据生命周期与脚本回归

指定 `-Receipt` 时，验证开始前会删除同路径的旧成功收据；如果旧收据无法安全清除，脚本立即失败，不继续执行设备操作。收据目录必须已存在，且目标路径必须是文件名。所有设备、Git 源码状态及 APK 摘要检查完成后，脚本在**收据同目录**写入唯一临时文件，再使用文件系统重命名发布完整 JSON；失败时清理临时文件。这样重复使用同一路径进行**顺序重验**时，失败不会让历史 `PASS` 继续充当本次结果。请勿对同一收据路径并发运行多个验证实例。

未提供 `-Receipt` 时仅向标准输出返回 JSON，不创建收据文件。失败不会输出成功 JSON。收据仍是本次本地测试的事实记录，并非云端上传确认。

无需 Android 设备即可运行模拟回归（需 PowerShell 7 或兼容 PowerShell、Git）：

```powershell
pwsh -NoProfile -File ./verify-device.tests.ps1
```

测试在此目录被忽略的 `.gradle/` 内创建隔离副本、伪 APK 字节与假 ADB 命令，覆盖先成功后无设备、缺 APK、安装失败、instrumentation 失败（ADB 退出 0）、未核对安装摘要、成功重验替换收据、原子发布冲突以及 stdout 模式，共 8 个场景；假 ADB 还模拟不加 `-r` 时隐藏结果码的真实行为。自动删除临时环境，**不会连接设备、安装 APK 或产生真实平台通过证据**。现有根目录检查与远端 CI 不包含这组回归，必须单独运行并记录结果。

两个 smoke case：

1. 探针在自己的普通应用 UID 下读取本体单 APK，期望 1 个文件。这不是跨应用读取证据。
2. 同一探针读取另一个已安装的自建 fixture，期望 base + `fixture_feature` 共 2 个文件；连续两次的文件/集合摘要必须一致，并分别等于本机构建的 base/split 哈希。只有实际设备通过才形成跨应用 splits 读取证据。

模拟器收据不替代真机收据。查看界面用 `adb -s <设备> shell am start -n org.privacytrace.probe/.ProbeActivity`，分别走查确认、取消、切后台和重新选择；截图只保留自建受控应用内容。

### 实际安装更新拒绝实验

先构建 fixture 的版本 2 并保存，再恢复普通 smoke 所需的版本 1；以下 PowerShell 命令在本目录运行。所有安装目标都是本仓库的受控 debug 应用。

```powershell
./gradlew.bat :fixture:assembleDebug :fixture_feature:assembleDebug -PfixtureVersionCode=2
New-Item -ItemType Directory -Force .gradle/fixture-v2 | Out-Null
Copy-Item fixture/build/outputs/apk/debug/fixture-debug.apk .gradle/fixture-v2/base.apk
Copy-Item fixture-feature/build/outputs/apk/debug/fixture_feature-debug.apk .gradle/fixture-v2/split.apk
./gradlew.bat :fixture:assembleDebug :fixture_feature:assembleDebug -PfixtureVersionCode=1
./verify-device.ps1 -Serial '<测试设备>'
./verify-update-race.ps1 -Serial '<测试设备>' -UpdatedBaseApk .gradle/fixture-v2/base.apk -UpdatedSplitApk .gradle/fixture-v2/split.apk
```

instrumentation 在真实 PackageManager 快照之后、第一次打开 APK 之前停在**测试代码专有的暂停点**。宿主通过实际 `adb install-multiple -r` 更新 fixture，随后由应用 UID 继续读取。测试要求真实版本已从 1 变成 2，并且读取返回 `INSTALLATION_CHANGED` 或旧路径不可读的 `UNREADABLE`，不得返回完整成功。脚本有超时与进程清理，只向 stdout 输出独立更新收据，不复用普通 smoke 收据；失败不输出 PASS JSON。普通 smoke 允许降级这个自建 debug fixture，以便重复实验。

它验证了可控时序下的真实安装更换，不覆盖自然竞争的概率或所有 OEM 行为。Android 14 / API 34 AOSP x86_64 模拟器已完成两项 smoke、错误摘要拒绝及更新拒绝，详见 [evidence/](evidence/)；真机仍未验证。

## 仍需实施与验证

| 场景 | 当前状态／下一步 |
| --- | --- |
| metadata 缺包、重复 split、尺寸不符、变化、不可读、取消、限额 | JVM 确定性回归；不冒充平台真实事件 |
| 真实 PackageManager 查询、跨 App base/splits 可读性 | Android 14 AOSP 模拟器通过；真机与其他系统仍待实测 |
| OEM / Android 24、30+、近期系统与工作资料隔离 | 待选代表真机；分别记录环境和可见性限制 |
| 安装期间更新／卸载、同版本重装、后台取消 UI | 受控版本更新、同版本重装拒绝与 HOME 取消已有模拟器证据；自然竞争、卸载及读取中取消时延仍待验 |
| 无 Launcher 的应用 | 本实验不列出；先评估有限 queries 是否满足正式产品范围 |
| Tauri 2 → Kotlin 调用、生命周期与受保护配置 | 独立桥接与受保护配置实验已实现；网页不传包名/路径/Key，原生选择确认；生产接线待完成 |
| HTTPS、实例隔离、服务端确认/背压、断网/恢复、删除 | #70 业务接缝与 #80/#112 运行时源码已合入；客户端与真实部署组合验证仍待完成，最终由 #73 验收 |
| Google Play 权限材料与资格 | 尚未申请；构建可用不代表获批 |

平台调查和本轮执行事实见 [EVIDENCE.md](EVIDENCE.md)。
完整 #71 用户故事的覆盖、缺口与整合归属见 [ACCEPTANCE.md](ACCEPTANCE.md)。

2026-10-20 追加独立[受保护模型配置](PROTECTED-CONFIG.md)：原生输入与删除确认，
AndroidKeyStore/AES-GCM 加密保存服务 Key，网页仅接收端点和非秘密状态。
不赋予网络权限、不调用真实模型；上表中的受保护配置部分由此阶段补齐，生产整合仍待完成。
#80/#112 运行时源码现已合入 main，真实部署组合、HTTPS 上传和 #73 验收仍独立进行。
