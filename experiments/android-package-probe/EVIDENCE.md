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

## 2026-10-19｜PR #90 P2 收据问题修复

此前 Code Review 指出：同一路径先产生 PASS 收据、下一次设备验证失败时，历史 PASS 文件仍然存在，会被下游误认作当前运行结果。本次仅修改实验目录，保留 Android 包读取算法、原有收据字段与设备测试范围。

- `verify-device.ps1`：指定 `-Receipt` 时在 APK/ADB 检查**之前**清除旧收据，清除失败则拒绝验证；成功后在目标目录写临时 UTF-8 JSON，再以同目录重命名提交；无论设备、Git、哈希或文件写入哪个环节失败，均不将部分 JSON 作为成功收据发布。未提供收据参数时仍仅输出成功 JSON。
- `verify-device.tests.ps1`：提供隔离的假 ADB 与假 APK 字节模拟，计划检查 7 个场景：成功→无设备、成功→缺 APK、成功→安装失败、成功→instrumentation 失败但 ADB 退出 0、成功→再次成功、写入目标路径发生冲突以及未传 `-Receipt` 的 stdout 行为。使用 `.gradle/` 下临时文件，不连接 Android 设备。
- **运行与证据边界：** 本轮代码编辑执行环境未提供 `pwsh` 或连接的 Android 设备，因此新增脚本回归及真机 instrumentation 尚未在本环境运行。待在有 PowerShell 的环境执行 `pwsh -NoProfile -File ./verify-device.tests.ps1` 并记录输出；可检查的 GitHub CI 不替代该专项回归。旧记录中 14 项 JVM 测试及 Android 构建仍属于此前开发者报告，不能冒充本轮重新执行。
- 真实跨应用 base/splits 可读性、OEM / 工作资料差异、更新竞争、界面生命周期、Tauri 桥和远程上传仍未验证。收据逻辑修复不证明 Android 平台可行性，也不关闭 #71 或解锁 #70/#73 的整体验收。

## 2026-10-19｜Android 模拟器实际验收

用户在原会话恢复推进，并明确选择“暂无真机，先做模拟器验证”。保留维护者所有 P2 修复，从远端 `1921a1b7d18dfa799953338670701a592001ed92` 正常合入 main `ffbd2b7`；本地归属调整前的历史引用单独保留，没有重写远端。

- **环境：** Android 14 / API 34 AOSP x86_64，官方 `system-images;android-34;default;x86_64` revision 4，Windows WHPX。测试进程强制检查普通应用 UID，未使用 adb root。该环境是模拟器，不能替代真机/OEM/工作资料验证。
- **实际 smoke：** 已查询并读取探针本体单 APK，以及另一受控应用的 base + `fixture_feature`；连续两次摘要一致，分别等于宿主所构建 APK 的 SHA-256。错误的期望 SHA 在实际 instrumentation 的 `artifact_hashes` 阶段返回失败，没有 PASS。
- **真实发现与修复：** 首次实际调用中 Android 测试已经输出成功，但宿主收据脚本拒绝。默认 `am instrument -w` pretty 输出不含结果码；改用 `-r -w` 后可核对 `INSTRUMENTATION_CODE`。回归假 ADB 同样模拟该差异：先证实旧命令失败，再修复并通过 8 项脚本回归，继续保留失败重验失效旧收据的维护者修复。
- **安装变化：** 新增 test-only 暂停点和 `verify-update-race.ps1`。真实 PackageManager 快照之后，以实际安装操作将受控 base/split 从 versionCode 1 换为 2，再继续读取。模拟器返回 `UNREADABLE`（旧安装路径不可读），没有完整结果；同时核对当前真实 versionCode 已为 2。它证明受控时序下的失败关闭，不推导自然竞争发生率或其他系统的表现。
- **界面：** 实际打开探针，选择受控 fixture，检查确认文案后开始读取，界面显示 versionCode 2、2 个包及各自摘要，截图已人工查看。仅此基本选择/确认/结果流程有证据；后台取消与中断恢复尚未验收。
- **构建与回归：** 4 个 APK、主模块 lint、14 项 JVM 算法回归与 8 项 PowerShell 收据回归分别验证；运行源码与实际 APK 哈希见 [evidence/](evidence/) 中收据。旧日期记录保留原 SHA，不以本次模拟器结果改写。
- **最新主线的本机检查限制：** Windows 权威入口执行到 API 为 1401 passed / 77 skipped / 8 failed。失败涉及新合入的 pipeline/多包隔离测试，表现为 `ISOLATED_INSPECTION_UNAVAILABLE` 或作业 FAILED；本机已无 `Ubuntu-24.04` WSL 发行版，Docker Desktop daemon 也未运行。与 main 比较，`apps/api`（含全部测试）和 `scripts/check.sh` 没有任何差异。本轮未修改隔离策略或伪造跳过；Ruff、schema 零差异、Web 53 项和生产构建另行通过。完整 Linux/Docker CI 结果由 PR 绑定最终交付 SHA，不能将此 Windows 命令记录为通过。

正式 Tauri 桥接、手机受保护配置、#80 真实运行时与 HTTPS/实例隔离/断网恢复、#73 整体主链路仍待完成。#70 业务接口已合入，不把它的关闭当作这些验收已通过。#71 保持开放，PR 仍为实验范围的草稿。

没有提交 APK、完整政策、缓存、签名材料、本机私有路径或个人设备清单。所有假数据来自自建测试；文件摘要不是运行时行为、隐私安全或法律结论。

## 2026-10-19｜Tauri 2 实际桥接部分交付

用户继续要求推进；在 #71 当前记录重核归属后，仅延伸同一实验目录与 PR #90。#72 已在其分支修改手机报告/候选页面，本轮没有触碰共享 Web、API、公共契约、CI 或其他 owner 的交付。

- 将原读取器移动到 `core/`，原生探针与 Tauri Android 插件编译同一份源码。网页只调用无参数的原生选择/确认，不接收整机清单或传入路径；结果只含当前选择的本机摘要。
- 实际打通 Vue → Rust command → Kotlin Plugin → PackageManager/文件流，再把两份摘要返回 WebView。Rust 与 JS API 版本一致，权限仅开放本地 Android 主窗口的两个命令；空闲 cancel IPC 也在每次开始时真实往返。
- 独立审阅发现 Activity 重建风险，并在旧 APK 通过系统字号变化实际复现：进程保留、新 Vue 页已加载，但选择一直返回 BUSY_OR_INACTIVE。修复当前 Activity 绑定、旧操作废弃与新 gate/worker，再以同一真实重建路径验证恢复；旧回调不能结算新请求。
- 干净源码 `44e5258f364897474192dd8ddabf39974da9d193` 的实际模拟器桥接五场景与抽取后原生两项 smoke 全部通过。桥接最终 UI 的 base/feature split SHA 与本机构建文件分别相同；源码/产物绑定见 [新增证据](evidence/README.md#同日后续真实-tauri-桥接实验)。截图由独立代理审阅，未截断或被系统栏遮挡；失败 UI dump 也通过 finally 清理。
- 19 项 JVM、8 项 PowerShell、原生四包与真实 Tauri x86_64 APK、Vue 类型/打包通过；原生 lint 通过（API 34 历史壳针对性忽略 OldTargetApi，其余仍 warnings-as-errors），桥接 lint 0 errors / 2 个版本提示；npm 审计 0 项。固定 Gradle 分发哈希与生成准备脚本已实跑。首个 MSVC 构建因缺 Windows SDK 失败；改为隔离的 GNU Rust 主机交叉构建后通过，没有修改全局 PATH 或共享隔离策略。
- Windows 权威入口再次实跑仍为 1401 passed / 77 skipped / 8 failed，同样是缺少隔离运行时的既有失败；本轮没有改 API、测试、check.sh 或 CI。最终 Linux/Docker CI 另由当前执行记录绑定交付 head；既有 CI 不运行本实验 Android 专项。

这些是自建应用的模拟器事实。真实手机/OEM/工作资料、自然竞争、读取中取消/后台传输、受保护配置、生产 Web 接线与真实 HTTPS/实例隔离仍未完成；不关闭 #71，不合并/发布/部署。

## 2026-10-20｜#71 查缺补漏，合并暂停

用户最新要求暂停 PR #90 合并并继续补缺。逐项核对 #71 的 12 条故事及 #72/#80/#81
当前归属，覆盖/剩余矩阵新增于 [ACCEPTANCE.md](ACCEPTANCE.md)。#70 契约已在 main，
#80 的唯一 PR #112 尚未合入；本轮不接管其运行时或 #72 的生产页面。

- **实际缺口及修复：** 原确认窗口只显示应用名，未展示版本/包数量/长度，读取也不绑定确认时的安装元数据。新增 UI 断言先在旧桥接 APK 上失败。共享核心新增 metadata-only prepare 和确认快照读取，两种原生壳显示版本、全部已安装包及长度；开始读取前变化则不开流并要求重选。读取后的完整性复核保持。原生返回、系统取消或后台离开会关闭本次确认并显示取消。
- **回归：** 20 项读取/确认 + 5 项生命周期 JVM 全过；8 项 PowerShell 收据回归、原生四包构建/lint、Tauri x86_64 APK/Vue 构建、Ruff 通过。桥接 lint 0 errors，保留两个既有版本提示。
- **干净源码设备证据：** `3bf5138db8dac6c58133380330bfad26ec6dab4c` 的三份收据均 dirty=false。真实 Tauri 8 场景、普通 UID 两项 smoke、原生确认/返回/系统取消/重选后摘要四项全部通过。确认后实际安装相同版本及内容仍拒绝；受控 force-stop 后新进程不继承旧确认，随后可重新选择并读取。截图及原生 UI 走查步骤见 [证据索引](evidence/README.md#2026-10-20确认范围绑定与补缺验收)。
- **失败保留：** 一次带截图预跑底层设备命令/解析中断，未输出成功 JSON；具体原因未定位，不归档失败截图为 PASS。并发根检查结束后，独占设备的干净源码完整重验通过；不推导自然竞争或任意系统回收恢复能力。
- **权威入口：** `pwsh -NoProfile -File scripts/check.ps1` 再跑为 1409 passed / 77 skipped / 8 failed / 3 warnings；与合并整合前相同的八项隔离运行环境失败，本机缺固定 WSL/Docker 扫描环境。API/Web/check.sh/CI 无本轮差异，未放宽或过滤测试。远端 CI 仍须绑定新 head，旧 head 绿灯不替代新验证。
- **审阅与边界：** 独立需求、代码及实际确认/拒绝/结果视觉审阅无阻塞意见。当前仅模拟器，旧收据保持原 SHA。受保护配置、真实 HTTPS/实例隔离/背压/断网恢复、生产 Web 整合与真机均为剩余事项；#71 保持 open，#90 合并继续暂停，不发布/部署。
