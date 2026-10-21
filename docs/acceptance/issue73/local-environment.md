# 本机环境与启动要求

本文件按 #73 当前授权定义本机验收。环境准备可以先行；#81 完成并关闭后立即读取交付记录、核对 main 和安装产物，开始探针、构建安装及场景执行。本文件写于执行前，实际准备结果见文末“实际准备结果”，执行结论以[执行记录](execution-20261021.md)为准。

## 拓扑与覆盖

| 角色 | 本机准备 | 执行要求 |
| --- | --- | --- |
| Android | 专用 Android 模拟器，独立于日常实例 | 记录 API、ABI、WebView、系统构建；安装实际 `apps/mobile` 包及普通/splits 样本；固定 ADB 目标，禁止默认设备或批量操作 |
| 控制面 | 专用 Ubuntu 24.04 WSL2 发行版 | 两套不同实例身份/凭据/数据卷的标准与自托管配置；真实 PostgreSQL/outbox、Redis/Celery、API/材料网关和恢复器 |
| 扫描面 | 另一个专用 Ubuntu 24.04 WSL2 发行版 | 独立文件系统与本地 Docker daemon；仅 Runner 可控扫描 daemon；不得向 API/编排共享 socket、宿主根目录或特权 |
| 政策与模型 | 本机受控 HTTPS 服务 | 正常政策、重定向/超限/拒绝变体；模型协议受控响应、一次性测试 Key 和目的地观察，禁止使用个人真实 Key |
| 证据 | Git 忽略目录 | 客户端包、签名、证书、数据库、原始请求/日志和环境实际路径留本机；公开材料仅保留审查后的结果和摘要 |

WSL2 发行版拥有独立用户空间，但共享宿主虚拟机内核和网络环境；不能将它们称为独立物理主机或独立内核 VM。它们用于本机功能和隔离配置验收。若 #81 交付要求独立内核/网络边界，必须在本机独立虚拟机补齐对应场景，不用 WSL 发行版替代该项证据。扫描仍须使用无网络、无秘密的受限容器。

不修改宿主全局 WSL 配置，不重启/关闭他人发行版，不操作 #81 在用的容器、网络、卷或镜像标签。两个专用 daemon 启动前检查共享网络中的端口、桥接地址及防火墙冲突；使用独立地址池和 Compose 项目，无法证明隔离则停止该项。所有故障注入与磁盘满试验只针对本次专用资源。

## 构建与安装准备

正式入口见 [移动客户端](../../../apps/mobile/README.md)。准备 JDK、Android SDK platform 36、对应 build-tools、Android NDK、Rust Android x86_64 target 和固定 Tauri CLI。compile/target API36 不表示运行系统必须 API36，安装时据最终 Manifest 的 minSdk 判断；API35 不能证明 API36 平台行为。

在干净 checkout 根目录 `npm ci; npm run build`，随后在 `apps/mobile` 运行：

```powershell
npm ci
npm run android:prepare
npm run android:build -- --target x86_64
```

从实际构建配置确定 JDK/NDK 版本，不凭旧 PoC 配置猜测。读取最终 Manifest、签名指纹、ABI 和 APK SHA256；只向专用设备安装。普通包与真正 base/splits 使用 [平台样本源码](../../../experiments/android-package-probe/README.md)构建并按其验证入口核对，不能把 base APK 改名当作 split。

初始化环境后保存本机配置：专用发行版名、模拟器索引与 ADB 目标、SDK/JDK/Rust 路径、受限资源和下载校验值。运行 [环境探针](../../../scripts/check-local-acceptance.ps1)输出本机 JSON。`toolchain_ready` 表示工具、指定模拟器和两个专用 daemon 检查通过；不放行完整业务拓扑或最终验收，也不向外部发布信息。探针读取角色标记 `/etc/privacytrace-issue73-environment`、服务 `privacytrace73-docker.service`、数据根 `/var/lib/privacytrace73/docker`，核对 daemon 网络命名空间不同于宿主。实际路由与 TLS 另行实测，`final_acceptance_ready` 始终为 false。

在 WSL 共享网络之外，为每个 daemon 建立独占网络命名空间，并由服务每次启动重建。使用 `nsenter --net` 保留原 cgroup 挂载；不要用会重挂 sysfs 的方式启动 Docker 后误报缺少 devices controller。WSL 的 systemd 服务本身不保证实例持续运行，准备期间另持有专用 keepalive；重启后重新跑探针，不能假定 `/run` 仍存在。

配置放在 Git 忽略的 `tmp/`，以下路径均为示例，须改为实际工具路径；示例不指向真实用户目录，公开记录不写本机私有路径，也不要加入任何秘密。当前探针以 MuMu 主机清单校验专用实例和 ADB 端点，再对比 API/ABI，不能把设备自报型号当作物理设备证明。

```json
{
  "android_sdk": "C:/PT73Tools/android-sdk",
  "android_platform": "android-36",
  "build_tools_version": "36.0.0",
  "ndk_version": "27.2.12479018",
  "java_home": "C:/PT73Tools/jdk",
  "rust_toolchain": "C:/PT73Tools/rustup/toolchains/stable-x86_64-pc-windows-gnu",
  "rust_android_target": "x86_64-linux-android",
  "windows_gnu_tools": "C:/PT73Tools/mingw/bin",
  "adb": "C:/PT73Tools/android-sdk/platform-tools/adb.exe",
  "adb_target": "127.0.0.1:16480",
  "device_kind": "EMULATOR",
  "emulator_manager": "C:/MuMu/nx_main/MuMuManager.exe",
  "emulator_index": 3,
  "emulator_name": "PrivacyTrace73",
  "expected_api": 35,
  "expected_abi": "x86_64",
  "control_distribution": "PrivacyTrace73-Control",
  "runner_distribution": "PrivacyTrace73-Runner"
}
```

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
pwsh -NoProfile -File scripts/check-local-acceptance.ps1 -ConfigurationPath tmp/local-config.json -OutputPath tmp/environment-probe-01.json -RequireToolchainReady
```

每次使用新的输出文件名，探针拒绝覆盖旧收据。实际构建还要把完整 GNU host 工具加入当前进程 PATH；Rust 自带包装器不等于独立完整的 MinGW。不能仅有 Android target 文件就宣称编译通过。

## HTTPS 与本机网络

正向端点必须由 Android 原生 HTTP 实际信任，保持证书链、有效期及 SAN/主机名校验。记录端点别名、CA 公钥指纹、信任安装方式及其范围。Android 用户证书库不必然被目标应用信任；在专用可恢复的模拟器系统信任区安装本机测试 CA 后，必须实测应用请求。若需专用测试构建，另记包哈希、配置差异和覆盖限制，不能修改正式默认信任或使用 trust-all。

本机官方配置 I、自托管配置 J、政策和模型服务使用不同端点/作用域。地址须从模拟器实际可达；不要把主机 loopback、AVD 特定网关或 MuMu 网关互相套用。校验路由、监听、容器隔离和防火墙后，以 Android 请求验证。坏 CA、错主机名、过期证书和 HTTP 的 N07 在同一已配置信任环境中执行。

政策安全校验默认拒绝私网来源；本机政策测试不能关闭 SSRF 守卫或随意允许私网。按上游实际交接使用受控来源/解析与本机隔离路由；若当前交付无法安全提供正向政策来源，明确 BLOCKED 并修复测试基础设施，禁止把 N09 拒绝改成成功。模型接口的受控响应只证明协议、输入最小化与 Key 去向，不证明外部服务质量。

## #81 完成并关闭后的执行顺序（历史计划）

1. 重新读 #81 关闭证据及交付 SHA、部署清单、运行时/扫描版本和操作交接；核对 #72/#71 客户端来源。完成只由证据决定，不能自动合并上游 PR 或关闭 Issue。
2. 在本机新建运行目录与版本快照，实跑环境探针、构建、安装及正向/拒绝 TLS；配置两个实例及任务 A/B。未部署/未信任/未安装的项目保持 BLOCKED。
3. 执行 [H01–H12、N01–N12、F01–F10、R01–R04](scenarios.md)，沿同一实际业务链路取证；所有回归、浏览器、Docker、runtime/部署专项也在本机运行。跳过不计通过。
4. 每项读回脱敏证据及哈希。最终结论只覆盖实测本机组合；物理设备、公网、外部模型与商店审核保持独立未验证。

恢复时重新检查环境和上游，不复用旧准备包中的 OPEN/CLOSED 快照。#79 扩展不阻塞主流程。合并、生产部署、商店提交和分发不包含在本机测试授权中。

## 实际准备结果（2026-10-21）

准备已按本节要求完成，实际值与差异如下：

- **工具链（实测）**：JDK 17.0.20.1、Android SDK platform 36 / build-tools 36.0.0 / NDK 27.2.12479018、Rust 1.99.1（`stable-x86_64-pc-windows-gnullvm` + llvm-mingw host 工具）、Tauri CLI 2.12.3。工具与缓存位于本机忽略目录，不提交。
- **客户端（实测）**：由上述工具链在本机构建的 debug 客户端 `client-local-ca.apk`，sha256 `8bb257dfd3a63d295b858decba7ba0dcee44d6e20c063c01feb1813f4f3fddc8`；其网络配置**仅**对 `localhost` 追加本机测试 CA 作为信任锚，其余仍用系统信任，未使用 trust-all。默认系统信任的对照构建计划用于 N07 负向，本轮未执行 N07。
- **受控样本（实测）**：`fixture-base-policy.apk`（sha256 `1d14eadd…`，manifest 内声明 `http://1.1.1.1/policy.html`）与 `fixture-feature.apk`（sha256 `802550145ec9…`），同一 debug 签名；不是把 base 改名冒充 split。
- **模拟器（实测）**：专用实例 `PrivacyTrace73`，Android 15 / API 35 / x86_64 / `adb 127.0.0.1:16480`。该镜像 **/system 为只读**，无法在系统信任区安装 CA，因此改用上一条的专用 debug 客户端；这一差异已如实记录，不作为系统信任证据。
- **控制面/扫描面（实测）**：两个专用 WSL2 发行版，独立 Docker 数据根与专用网络命名空间；探针确认守护进程网络命名空间与宿主不同。
- **网络通路（实测）**：实验室 HTTPS 端口经“命名空间内转发 + 宿主机回环转发 + `adb reverse`”三步映射到模拟器的 `https://localhost:<port>/`；证书链与主机名校验保持开启。宿主回环可达性用一次性 TCP 监听实测确认。
- **受控来源（实测）**：政策占位地址只在实验室命名空间内 DNAT 到本机受控 HTTP 服务；客户端侧模型接收器为本机 HTTPS 且使用一次性测试凭据。两者都不访问外部主机；客户端模型接收器只证明协议与 Key 去向，服务端自动候选提取未配置模型（见执行记录 4.4）。
- **环境限制（实测）**：准备期间本机 WSL 发行版被外部反复停启，实验容器与临时转发随之中断；已用持久化 systemd 单元缓解，但仍不足以在单次稳定窗口内连续完成全部矩阵。该限制已记入[执行记录](execution-20261021.md)，不把未执行项记为通过。
