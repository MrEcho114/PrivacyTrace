# 客户端 APK 构建与安装冒烟（2026-10-23）

状态：**PASSED（构建 + 安装 + 首屏冒烟）**，附带两条已知缺口：品牌启动图标未叠加（`android:prepare` 模板漂移，GAP-1）、宿主机 Rust 工具链改用 MinGW 而非 MSVC（GAP-2）。完整 H/N 验收未执行，不在本记录范围。

本文件只记录本次实际执行的命令、实际产物指纹和实际读数；未执行项写入 §8，不做推断。

## 1. 基线与工作区

| 项 | 值 |
| --- | --- |
| 被构建源 | `origin/main` = `a1a6386ab4a18739445b8ffc1025c94e1af5b5d7` |
| 分支 / worktree | `codex/e2e-acceptance-20261023` / `.agents/worktrees/codex/e2e-acceptance-20261023` |
| 工作区状态 | 构建前 `git status` 仅有他人未跟踪的 `docs/acceptance/e2e-latest-baseline-20261023.md`；本任务未修改产品代码、未 commit、未 push |
| 旧参考 APK | `.scratch/apk/client-local-ca-2626152.apk`（源 `262615242161e0371ec151a5f07ef19d360a35e3`，仅作对比，不是本基线产物） |

## 2. 工具链（全部装在仓库外）

| 组件 | 版本 | 位置 / 来源 |
| --- | --- | --- |
| Node / npm | v24.17.0 / 11.13.0 | 已有 |
| JDK | Temurin 17.0.20.1+1 | `C:\Users\Oasis\.jdks\jdk-17.0.20.1+1`（Adoptium API `latest/17/ga/windows/x64` zip 解压，190,817,615 B） |
| Android cmdline-tools | latest（revision 23.0） | `D:\Tools\android-sdk\cmdline-tools\latest`（`commandlinetools-win-13114758_latest.zip`，143,040,480 B） |
| platform-tools | 37.0.1 | `D:\Tools\android-sdk\platform-tools` |
| platforms | `android-36`（rev 2） | `D:\Tools\android-sdk\platforms\android-36` |
| build-tools | 36.0.0 | `D:\Tools\android-sdk\build-tools\36.0.0` |
| NDK | 27.3.13750724（r27d，Windows） | `D:\Tools\android-sdk\ndk\27.3.13750724`（Tauri CLI 自动识别：`Info Using installed NDK`） |
| CMake | 3.31.6 | `D:\Tools\android-sdk\cmake\3.31.6` |
| Rust | 1.99.1（满足 `rust-version = 1.90`） | `%USERPROFILE%\.rustup` / `%USERPROFILE%\.cargo`；**host = `x86_64-pc-windows-gnu`**（见 GAP-2） |
| Rust Android target | `x86_64-linux-android` | `rustup target add ... --toolchain stable-x86_64-pc-windows-gnu` |
| MinGW-w64 | gcc 16.2.0（ucrt, posix, seh, Brecht Sanders r3） | `D:\Tools\mingw\mingw64` |
| Tauri CLI | 2.12.3 | `apps/mobile/node_modules/@tauri-apps/cli` |
| Gradle | 9.6.1（wrapper，`distributionSha256Sum=9c0f7fae…9e14`） | `%USERPROFILE%\.gradle` |
| AGP / Kotlin GP | 9.3.1 / 2.2.10 | 由 CLI 2.12.3 模板生成 |
| adb | 1.0.41（36.0.0-13206524） | `D:\Games\MuMu Player 12\shell\adb.exe` |

完整版本快照：`tmp/e2e/20261023/apk/toolchain-versions.txt`。
环境入口脚本（可复用）：`D:\Tools\android-env.ps1`（设置 JAVA_HOME/ANDROID_HOME/NDK_HOME/PATH）。

## 3. 构建命令与实际耗时

```powershell
. D:\Tools\android-env.ps1
cd <worktree>
npm ci                     # 首次被占用文件阻塞，见 GAP-4；恢复后 exit 0
npm run build              # vue-tsc + vite，exit 0，14.7s → apps/web/dist

cd apps/mobile
npm ci                     # @tauri-apps/cli 2.12.3，exit 0
npm run android:prepare    # exit 1（init + API36/manifest 补丁成功，品牌图标叠加失败，GAP-1）
npm run android:build -- --target x86_64   # exit 0，189.0s（cargo 已热缓存）
```

- 首次 `npm run android:build` 在 cargo host 链接阶段失败（52.8s，`link: extra operand`，见 GAP-2 证据），修复宿主机工具链后的成功运行为 189.0s。
- `android:build` 会自行执行 `beforeBuildCommand`（`npm run web:build`），因此 APK 内嵌的 web 资源是构建时刻的 `apps/web/dist`，不是 §3 手工那次 dist 的缓存。
- Tauri 传给 cargo 的实参（日志原文）：`cargo build --package privacytrace-mobile --manifest-path .../src-tauri/Cargo.toml --target x86_64-linux-android --features "tauri/custom-protocol tauri/custom-protocol" --lib`。
- Gradle 产物同时包含 AAB：`bundle/universalDebug/app-universal-debug.aab`（本次未使用）。

## 4. 产物

| 项 | 值 |
| --- | --- |
| 归档路径 | `tmp/e2e/20261023/apk/privacytrace-mobile-a1a6386-x86_64-debug.apk` |
| 构建原始路径 | `apps/mobile/src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk` |
| 大小 | 157,574,871 B（≈150.28 MiB） |
| SHA-256 | `04dd6273824ae752ddf3f0c532f4a838c9c3cb8a822b2aae83cb578288bee404` |
| 包名 | `org.privacytrace.mobile` |
| versionCode / versionName | `1000` / `0.1.0` |
| minSdk / targetSdk / compileSdk | 24 / 36 / 36 |
| 原生 ABI | `x86_64`（`lib/x86_64/libprivacytrace_mobile.so`，142.76 MB；`classes.dex` 9.49 MB） |
| 启动组件 | `org.privacytrace.mobile.MainActivity`（`launchable-activity`） |
| 权限 | `android.permission.INTERNET`、`org.privacytrace.mobile.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` |
| manifest 关键项 | `android:allowBackup="false"`、`android:usesCleartextTraffic="false"`（`prepare-android.ps1` 补丁已生效） |
| 签名 | debug 签名（`~/.android/debug.keystore`）；`adb install -r` 覆盖既有安装成功，说明与既有安装同签名 |

回读命令：`aapt2 dump badging <apk>`（build-tools 36.0.0）。原始输出见 `tmp/e2e/20261023/apk/android-build-4.log` 与 §6 冒烟日志。

## 5. 与旧 APK 的差异

| 项 | 旧 `client-local-ca-2626152.apk` | 本次 `a1a6386` |
| --- | --- | --- |
| 大小 | 157,543,412 B | 157,574,871 B（+31,459 B，+0.02%） |
| SHA-256 | `955d484ba0a01bcf0472e7d97b24fe0d84698af8c61b0efe38b762ca7d3e6088` | `04dd6273…bee404` |
| 包名 / 版本 / SDK / ABI | `org.privacytrace.mobile` / 1000 / 0.1.0 / 24→36 / x86_64 | 完全相同 |

原生壳未变的依据（不是猜测）：

- `git diff --stat 2626152 a1a6386 -- apps/mobile/src-tauri/src experiments/android-package-probe apps/mobile/src-tauri/Cargo.toml apps/mobile/src-tauri/tauri.conf.json apps/mobile/package.json` → 仅两个 `package.json` 各 1 行变化（CLI/端口相关），原生 Rust 源码零改动。
- 同期整仓 diff 为 304 文件 / 23,081 插入，集中在 web 与引擎侧。
- APK 内嵌资源取自本基线 web 构建：`.so` 内可检出 `apps/web/dist/assets` 中全部 6 个产物的文件名（`app-DGvnQ9dG.js`、`app-DJsvZfbq.css`、`design-DKsR9bU6.js`、`design-OFNm0FuO.css`、`_plugin-vue_export-helper-*.{js,css}`），逐个命中。
- 体积差 0.02% 与“原生壳不变、仅内嵌 web 资源变化”一致；未做二进制级等价比对，不作为已证明项。

## 6. 安装与冒烟证据（MuMu Player 12，VM index 5）

设备：MuMu VM 5，Android 15（API 35），`ro.product.cpu.abi=x86_64`，`127.0.0.1:16544`（`MuMuManager info -v 5` 报告 `adb_host_ip`/`adb_port`）。VM 0 未触碰。

| 步骤 | 读数 |
| --- | --- |
| `adb install -r` | `Success: streamed 157574871 bytes` → `Success` |
| `am start -W -n org.privacytrace.mobile/.MainActivity` | `Status: ok`，`LaunchState: COLD`，`TotalTime: 788`，`WaitTime: 791` |
| 进程存活 | `pidof` = 2487；17s 后复读仍为 2487 |
| 前台组件 | `topResumedActivity=org.privacytrace.mobile/.MainActivity`；`mCurrentFocus=Window{… org.privacytrace.mobile/org.privacytrace.mobile.MainActivity}` |
| 已安装版本 | `versionCode=1000 minSdk=24 targetSdk=36`，`versionName=0.1.0` |
| 崩溃 | `logcat -d -s AndroidRuntime:E` 无输出（无 FATAL） |
| WebView | 启动 `com.android.webview:sandboxed_process0…SandboxedProcessService0` 进程，`Displayed … +788ms` |
| 首屏 | `screen-1.png`（1920×1080）：标题「APK 与政策材料」、四步指示（APK / 核对 / 扫描 / 报告）、卡片「选择要对照的应用」+「选择应用并上传」「恢复当前材料」、底栏「重新读取材料」「准备政策并继续」 |
| 安装一致性 | 从设备 `pm path` 拉回 `base.apk`，SHA-256 = `04dd6273…bee404`，与构建产物**逐字节一致** |

证据文件（`tmp/e2e/20261023/apk/`，不进 Git）：

| 文件 | 说明 | SHA-256 |
| --- | --- | --- |
| `smoke/screen-1.png` / `screen-2.png` | 首屏截图（99,550 B，间隔 7s 内容一致） | `dc7de2166971c5a5fa36b7e3fbea0a4b31666121cce20ceaf5ebacd5849c674a` |
| `smoke/smoke.log` | 安装/启动/进程/焦点/版本/崩溃检查全流程日志 | 见文件 |
| `smoke/installed-base.apk` | 设备回拉副本，用于哈希对齐 | `04dd6273…bee404` |
| `android-build.log` | 首次失败（MSVC 缺失）原始日志 | 见文件 |
| `android-build-4.log` | 成功构建完整日志（含 `Finished 1 APK at:`） | 见文件 |

## 7. 缺口与偏离（可复现）

### GAP-1：`npm run android:prepare` 在品牌图标叠加步骤失败（仓库侧，非本机环境）

- 实际退出码 1；`tauri android init --ci --skip-targets-install` 成功（`Project generated successfully!`），`prepare-android.ps1` 的 API36/manifest 补丁也已写入（`Prepared PrivacyTrace mobile workflow (API 36).`）。
- 首个错误（原文）：
  `[apply-brand-android-icons] ERROR: Generated Android template drifted: expected mipmap-anydpi-v26/ic_launcher.xml, but it is missing.`
- 生成树实际内容（`apps/mobile/src-tauri/gen/android/app/src/main/res`）：`drawable/ic_launcher_background.xml`、`drawable-v24/ic_launcher_foreground.xml`、`mipmap-{m,h,xh,xxh,xxxh}dpi/ic_launcher*.png`、`values*`、`layout/`、`xml/` —— **没有 `mipmap-anydpi-v26/`**，而 `scripts/apply-brand-android-icons.cjs` 要求它存在，`brand/android/res/` 里也确实带这两个自适应图标 XML。
- 后果：本次 APK 使用 Tauri 模板默认启动图标。对比：生成树 `mipmap-xxhdpi/ic_launcher.png` sha256 前缀 `0b250fc4451dfd1e` ≠ 品牌源 `b8b1308cfa1c163a`。**品牌图标未生效，标记为未通过项**。
- 影响面：`npm run android:prepare` 作为文档化入口在 CLI 2.12.3 上不能整条跑绿；后续要么补模板适配、要么把该步骤从构建前置里拆开。本任务按“不改产品代码”约束未修脚本。

### GAP-2：宿主机没有 MSVC，Rust host 改用 MinGW-w64 + `windows-gnu`

- 实测：`vswhere` 不存在、`C:\Program Files*\Microsoft Visual Studio` 不存在、`Windows Kits\10\Lib` 不存在；`where link.exe` 只命中 `C:\Program Files\Git\usr\bin\link.exe`（GNU coreutils 的 `link`）。
- 首次构建失败证据（`android-build.log`，52.8s，exit 1）：`linking with link.exe failed: exit code 1` + `link: extra operand '…rcgu.o'` —— rustc 找到的是 GNU `link`，不是 MSVC 链接器。本会话非管理员、审批被禁用，无法用 winget 装 VS Build Tools。
- 处理：MinGW-w64 16.2.0（便携 zip，免提权）+ `rustup default stable-x86_64-pc-windows-gnu` + 给该工具链加 `x86_64-linux-android` target；Android 目标仍用 NDK 27.3 的 clang 链接（Tauri CLI 自行注入 `CARGO_TARGET_X86_64_LINUX_ANDROID_LINKER` 等变量）。链接能力先用 hello-world 验证（编译、运行输出 `Hello, world!`）。
- 限制：这与 Tauri 文档/CI 假设的 MSVC 宿主不同。产物能装能跑，但**与 MSVC 产物的字节级可复现性未建立**；如需严格复现仍应装 VS Build Tools。

### GAP-3：Gradle 依赖下载需要代理/镜像调整

- 现象：直连时 daemon 挂起（`~/.gradle/caches` 停在 64 文件，几十条到 Cloudflare 的 ESTABLISHED 无进展）；改用本机代理（`127.0.0.1:7897`）后同样挂起（85 条待处理 CONNECT，缓存停在 428 MB）。
- 处理：`~/.gradle/gradle.properties` 去掉代理（此前不存在该文件，备份路径 `gradle.properties.bak-20261023` 未产生）；在生成目录 `gen/android/build.gradle.kts` 与 `gen/android/buildSrc/build.gradle.kts` 的 `repositories` 最前面加入阿里云镜像（`maven.aliyun.com/repository/{google,public,gradle-plugin}`）。生成目录本来就被忽略、由 `android:prepare` 重建，但**重跑 prepare 会覆盖这两处补丁**。
- 该调整只影响依赖来源，不改编译参数；本次产物仍由 AGP 9.3.1 / Gradle 9.6.1（wrapper sha256 未变）产出。

### GAP-4：worktree 里被占用的 `node_modules`（并行会话残留）

- `npm ci` 首次失败：`EPERM unlink …\node_modules\@esbuild\win32-x64\esbuild.exe`，占用者是本 worktree 里一个残留的 `vite` dev server（PID 29820，父 PID 30044 `npm run dev`）。
- 处理：不改动那个进程，改为把整个 `node_modules` 移走（`D:\Tools\node_modules-locked-20261023`）后重新 `npm ci`（exit 0）。
- 现状：该 vite 进程（29820/30044）现在已不存在，无需额外清理。此事若要追究，属于跨会话撞车，不影响本记录结论。

## 8. 未执行 / 未覆盖

- 完整 H/N 用例（本轮授权只做“构建 + 安装冒烟”），未执行、不计入通过。
- release 构建、AAB 分发、`aarch64`/`armv7`/`i686` 目标、真机（非模拟器）验证：未执行。
- 未验证品牌启动图标（GAP-1 直接导致未生效）；未验证应用内上传/抓取/报告等业务链路。
- 未做与 MSVC 产物的字节级等价验证（GAP-2）。
- 冒烟设备为 MuMu 模拟器（Android 15 / API 35、横屏 1920×1080），与真机行为不同，不作为真机结论。

## 9. 复用入口

```powershell
# 环境
. D:\Tools\android-env.ps1                 # JAVA_HOME / ANDROID_HOME / NDK_HOME / PATH（含 MinGW）
# 构建（每次）
cd <worktree>\apps\mobile
npm run android:build -- --target x86_64    # 产物在 src-tauri/gen/android/app/build/outputs/apk/universal/debug/
# 设备（VM 5）
& "D:\Games\MuMu Player 12\nx_main\MuMuManager.exe" control -v 5 launch
& "D:\Games\MuMu Player 12\nx_main\MuMuManager.exe" info -v 5      # 读 adb_port，本次为 16544
& "D:\Games\MuMu Player 12\shell\adb.exe" connect 127.0.0.1:16544
# 冒烟（安装/启动/进程/焦点/版本/截图/崩溃检查）
powershell -NoProfile -File D:\Tools\smoke.ps1 -ApkPath <apk> -OutDir <out>
& "D:\Games\MuMu Player 12\nx_main\MuMuManager.exe" control -v 5 shutdown
```

未使用 dockerd、未改动产品代码、未 commit/push；VM 5 已在冒烟后 `control -v 5 shutdown`（`is_android_started=false`，`errcode 0`）。


---

## 附：最终基线 `83a7983` 的 CA 信任版 APK（Lead 追加，2026-10-23T02:0xZ）

主文记录的是 `a1a6386` 的构建与冒烟。最终候选基线在 `2026-10-23T00:20Z` 前进到
`83a7983ee6e9bd580dfe41623e06f83c435b9d34`（`a1a6386` 之后仅 MIT 许可元数据、提交材料文档与
`export-schema.py`/`export-offline.py` 说明文字；web 增加一处页脚文案）。为让 H 组用**当前基线**的真实
客户端，Lead 在该 SHA 上补构建了带 #73 测试 CA 信任的 debug APK。

### 产物

| 项 | 值 |
| --- | --- |
| APK | `tmp/e2e/20261023/apk/privacytrace-mobile-83a7983-local-ca-x86_64-debug.apk` |
| SHA256 | `CD33C6EC12E4B5BDB7F1FB40AD02F9D2AA1CEB1863CA971BE1329F04E51A345A` |
| 大小 | 158,611,786 B |
| 基线 | `83a7983ee6e9bd580dfe41623e06f83c435b9d34`（构建时 worktree `git rev-parse HEAD` 已核对） |
| 包 / 版本 / ABI | `org.privacytrace.mobile` / 0.1.0（1000）/ `x86_64`，debug 签名 |
| 嵌入前端 | `lib/x86_64/libprivacytrace_mobile.so` 内可检出 `app-DGvnQ9dG.js`、`app-DJsvZfbq.css`、`index.html`（即 `83a7983` 的 `apps/web/dist` 产物） |
| CA 信任 | APK 内含 `res/raw/pt73_local_ca.crt`（sha256 `1A9330D8D792810F8F767D5F5076FA6345F6CEB1BA7F58A5FD362B619AC8E0F9`）与 `res/xml/pt73_network_security_config.xml`；packaged manifest 含 `android:networkSecurityConfig="@xml/pt73_network_security_config"`，仅对 `localhost` 追加 #73 测试 CA，base-config 保持系统锚点、禁止明文 |

### 做法（debug source-set overlay，不改产品代码）

Tauri 生成的 Android 工程支持 `app/src/debug/` 覆盖层；在该目录加入：

- `AndroidManifest.xml`：`<application android:networkSecurityConfig="@xml/pt73_network_security_config" />`
- `res/xml/pt73_network_security_config.xml`：`base-config` 用系统锚点，`domain-config` 仅 `localhost` 信任 `@raw/pt73_local_ca`
- `res/raw/pt73_local_ca.crt`：`tmp/issue73-local-env/tls/ca.crt`（#73 测试 CA）

该形态与上一轮 `client-local-ca` 构建一致（对照 `tmp/issue73-local-acceptance-20261021/apps/mobile/src-tauri/gen/android/app/src/debug/`）。

### 一个必须记录的构建陷阱

第一次在 `83a7983` 上直接 `npm run android:build -- --target x86_64` 得到与 `a1a6386` APK **完全相同的
sha256**（`04DD6273…E404`）：Gradle/配置缓存复用了旧构建，且 Tauri 未触发前端重打包，等于是假重建。
处理：先 `npm run build` 重建 `apps/web/dist`，删除 `apps/mobile/src-tauri/target/x86_64-linux-android` 与
`gen/android/app/build`，再构建；随后产物 hash 变为 `CD33C6EC…345A`，并逐项验证了新的 web 产物文件名与 CA
资源。最终 H lane 使用的就是这个 `CD33C6EC…345A` 版本（`a1a6386` 版 `04DD6273…E404` 只作调试）。

### 未覆盖

- 仅 `x86_64` debug 签名；未建立 MSVC 产物的字节级可复现性（GAP-2 仍成立）。
- 品牌启动图标仍未叠加（GAP-1 仍成立，仓库侧 `android:prepare` 模板漂移）。
- 安装/启动冒烟在新 APK 上由 H lane 重新执行，本附不再重复声称冒烟结果。
