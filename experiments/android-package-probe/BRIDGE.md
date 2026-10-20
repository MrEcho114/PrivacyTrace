# Tauri Android 桥接实验（#71 部分交付）

后续上传入口与新增能力协商见 [UPLOAD.md](UPLOAD.md)。本文下方保留先前只读桥接阶段的说明，
不能用旧 APK 的运行证据代替新增上传命令的设备验证。

本阶段复用已有读取核心，将本地调用贯穿 Vue → Tauri Rust command → Kotlin 插件 → PackageManager / APK 流。目录仍是独立实验，#72 的生产页面、服务端契约和远程上传均未接入。

## 调用边界

- `tauri-plugin/guest-js/index.ts` 提供 `inspectSelected()` 和 `cancel()`，使用 Tauri 的真实 `invoke`。应用须在 Rust 注册 `tauri_plugin_package_probe::init()`，并在仅适用于本地 Android 主窗口的 capability 中逐项允许两个命令；插件没有默认全开权限。
- `inspectSelected()` 不接收包名、文件路径、URL 或密钥。应用列表只在原生内存和原生选择器中出现；用户选择一个应用，再在独立原生窗口确认本机读取。未确认不会读取 APK 字节。返回值仅包含所选包的版本、文件数/长度和摘要。
- 确认窗口展示实际安装版本、base/全部已安装 splits 的数量、逐包长度和总大小。元数据查询在线程中执行并应用同一本机预算，尚未打开 APK 流；确认快照仅留在 Kotlin。开始读取时重新查询并逐项比较快照；即使 versionCode 与 APK 内容相同，重装导致时间或位置变化也要求重新确认，不能悄悄读取新安装。
- `versionCode` 跨桥时使用十进制字符串，避免 Android 64 位版本号在 JavaScript 中丢失精度。文件长度受原核心本地预算约束，仍可安全表示为 JavaScript number。
- Android 插件直接编译既有 `PackageProbe.kt`、`AndroidPackageSource.kt` 和操作门控源码，不维护第二套平台读取器。核心前后快照、完整性、流字节预算和拒绝逻辑不变。
- 同时只允许一个原生操作；取消令牌属于本次操作。读取取消后，等待该 worker 退出才接收新操作，防止连续点击堆积后台读取。取消选择器/确认窗口会拒绝本次调用；取消读取在流检查点生效，不保证能立刻打断平台阻塞 IO。
- `onPause` 保守取消本次操作，恢复前台也不能让旧结果重新成功；销毁废弃当前 Activity 的门控并关闭 worker。Tauri 因配置变化保留插件时，`onResume` 绑定新 Activity、建立新门控/worker，旧 Activity 的生命周期不再干扰它。读取结果在主线程完成时再次核对操作身份，迟到响应不会解除下一次操作的锁或返回部分摘要。
- Kotlin 只返回固定错误码；Rust 只转发白名单中的取消/变化/不可读/缺包/超限等代码，其他平台异常统一为 `NATIVE_PROBE_FAILED`。不转发异常信息、安装路径或 JNI 诊断。

`localSetSha256` 仍是实验私有指纹，不能作为 #70 的上传集合摘要或材料句柄。返回摘要不能让之后的上传绕过重新验证安装状态。

## 隔离验证壳

`bridge-harness/` 是 Vue 3 / TypeScript 的最小实验壳，用于验证实际桥接和用户选择；它不是产品页面或新的报告实现。打包本地资源，CSP 不允许网页外部请求；本轮原生 health 需要 INTERNET，准备脚本保留该权限、关闭备份和 cleartext。APK、生成的 Android 工程、Rust target、node_modules 及本机配置均忽略。

固定版本和依赖见 `package-lock.json` / `src-tauri/Cargo.lock`。Tauri CLI 2.12.3、Rust Tauri / JS API 2.12.4，Android 编译/目标 API 36，minSdk 24；Gradle 9.6.1 的官方分发校验和由准备脚本固定。模板的 AGP/Kotlin 版本由固定 CLI 生成。构建版本不代表真机、商店准入或最低系统范围已验收。

配置 Rust（MSVC 主机需要完整 Visual C++ 与 Windows SDK，或使用具有原生链接器的 Windows GNU Rust 主机进行 Android 交叉构建）、Android NDK、JDK 和 SDK。环境变量只需在当前终端设置：`JAVA_HOME`、`ANDROID_HOME`、`NDK_HOME`，并把 Cargo 放入 PATH。Android x86_64 用于模拟器；其他 ABI 需要分别构建和实测。

```powershell
# 在 bridge-harness/ 内；首次下载需要访问 npm、crates、Google Maven 和 Gradle。
npm ci
rustup target add x86_64-linux-android
npm run android:prepare
npm run tauri -- android build --debug --target x86_64 --apk
```

准备脚本会重新生成被忽略的工程，校核固定模板后切换到已安装的 API 36 并应用上述本机实验约束。不要在生成目录保存人工修改；模板漂移时脚本拒绝继续，应先审阅。普通浏览器构建 `npm run build` 只验证类型和资源，不提供模拟的 Android 成功结果。

## 验证范围

5 项操作门控 JVM 回归覆盖忙碌/取消后排空、旧操作无法影响新操作、暂停后恢复仍拒绝旧结果、销毁及 Activity 重建后的独立门控；与 20 项读取/确认测试一起执行。新增确认测试要求元数据查询不开流、确认后版本/时间/位置/包数/长度/标识变化拒绝、不可见/不可读拒绝、确认取消，以及读取中变化仍拒绝；不能只比较显示文案。原生 API 34 测试壳有针对性的 `OldTargetApi` lint 例外，因为其历史目标有意固定为 34；其余 lint 仍以 warnings-as-errors 执行。新桥接壳单独面向 API 36。

`verify-bridge.py` 安装自建验证壳与默认 versionCode 1 的 base/split fixture，实际走选择器取消、确认取消、HOME 暂停后恢复拒绝、确认信息与宿主 APK 长度比对、确认后同版本真实重装拒绝、待确认时受控 force-stop 后新进程状态清空，再重新选择读取并逐一比对 UI 文件 SHA 与本机构建产物。force-stop 是明确的测试动作，不证明任意系统杀进程时能恢复网络任务。它只向 stdout 输出成功 JSON；不输出设备标识、整机清单或平台路径，失败不输出成功 JSON。UI 临时 XML 每次在 finally 清理；设备断开时清理只能尽力完成。对同一设备按顺序运行。

在仓库根目录执行（Python 仅用标准库，也可用项目 `uv run --project apps/api python`）：

```powershell
python experiments/android-package-probe/verify-bridge.py --serial '<已授权测试设备>'
# 仅用于本任务的专用模拟器：改大系统字号触发真实 Activity 重建，然后恢复原设置。
python experiments/android-package-probe/verify-bridge.py --serial '<专用模拟器>' --verify-recreation
```

可加 `--screenshots '<已存在的本机输出目录>'` 保存受控应用的确认、重装拒绝和结果截图。
截图不能替代成功 JSON 中的源码/产物绑定，失败运行的截图也不作为 PASS 收据。

可选字号用例要求进程保持不变、新 Vue 页面出现、原生选择器可再次打开，随后在恢复字号后完成同一 split 集合读取。未指定选项时该项明确为 NOT_RUN；它不改变普通手机上的系统字号。主验证命令和旧平台证据仍见 [README](README.md) 与 [evidence/](evidence/)。实际 Tauri APK 构建和模拟器运行结果应另附当轮记录，不以 JVM 或原生 Activity 截图代替桥接证明。

追加的 `modelStatus()`、`configureModel()`、`clearModel()` 均为无参数、逐项授权命令，
使用同一个原生操作门控。配置命令在原生窗口接收 Key，Rust/网页返回类型仅为
`{ configured, endpoint }`；没有 Key getter 或 JS Key 参数。受保护配置的存储、取消与
设备测试边界详见 [PROTECTED-CONFIG.md](PROTECTED-CONFIG.md)。

新增无参数 `checkServer()` 仅打开原生服务 origin 输入，固定 GET `/api/v1/health`，返回
`{ origin, version, mode, scope: 'HEALTH_ONLY' }` 或白名单错误；没有请求路径、凭据或信任绕过参数。
取消共用同一门控并主动取消网络/DNS 等待；原始 body 不跨桥，地址不保存。
详见 [HTTPS.md](HTTPS.md)；成功只说明本次 health 响应，不能推导上传兼容或生产 ready。

后续正式接线仍需与 #72 owner 串行整合；实例能力、上传传输/服务端确认、后台传输、真实手机和完整 #71 验收尚未由本实验覆盖。
逐项缺口和前置归属见 [ACCEPTANCE.md](ACCEPTANCE.md)；本次确认元数据不等于远程上传的目标实例和保留规则确认。

接口依据：[Tauri mobile plugin](https://v2.tauri.app/develop/plugins/develop-mobile/)、[插件权限](https://v2.tauri.app/develop/plugins/#command-permissions)、[移动工具链](https://v2.tauri.app/start/prerequisites/#configure-for-mobile-targets)。本轮使用的实际接口也对照了固定 `tauri-v2.12.4` 标签下的 [Plugin.kt](https://github.com/tauri-apps/tauri/blob/tauri-v2.12.4/crates/tauri/mobile/android/src/main/java/app/tauri/plugin/Plugin.kt) 与 [Rust mobile API](https://github.com/tauri-apps/tauri/blob/tauri-v2.12.4/crates/tauri/src/plugin/mobile.rs)。
