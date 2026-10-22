# Android 竖屏证据（PrivacyTrace 移动客户端）

- 生成时间（UTC）：2026-10-22T00:10Z 左右
- 执行者：受委派的取证子代理（未修改任何受版本控制的文件，未提交）
- 证据目录：`.scratch/android-portrait/`
- 结论：**竖屏截图已拿到 11 张（1080×1920 原生竖屏）**；上传前的本地流程、原生选择器、上传确认、材料与政策候选界面均可达；
  **分析启动被 `UPLOAD_CONFLICT_REFRESH` 阻断，任务/报告界面未取得**（如实记录，未伪造）。

---

## 1. ADB 端点与运行状态

| 项 | 值 |
| --- | --- |
| adb 可执行文件 | `<MuMu>/nx_main\adb.exe`（1.0.41 / 36.0.0-13206524） |
| **序列号 / 端点** | **`127.0.0.1:16384`** |
| 设备状态 | `device`（在线，模拟器**保持运行中，未关闭**） |
| MuMu 实例 | VM index 0，名称「日常」，Android 15.0 引擎，`vt_enabled=true`，`hyperv_enabled=true` |
| 启动命令 | `MuMuManager.exe control -v 0 launch` → `{"errcode":0,"errmsg":""}`，`launch_time=9550ms` |
| 其他实例 | 未启动、未触碰（含 `MuMuPlayer-15.0-3`「PrivacyTrace130」，疑属其他会话） |

启动与连接命令（PowerShell 5.1）：

```powershell
& "<MuMu>/nx_main\MuMuManager.exe" control -v 0 launch
& "<MuMu>/nx_main\adb.exe" connect 127.0.0.1:16384
# boot 等待：adb shell getprop sys.boot_completed -> 1（2026-10-21T23:51:26Z）
```

设备信息（`getprop` / `wm size` / `wm density`）：

| 项 | 值 |
| --- | --- |
| 品牌 / 型号 / device | Samsung / `SM-S9280` / `e3q`（MuMu 伪装机型） |
| 指纹 | `Samsung/e3q/e3q:15/V417IR/1137:user/release-keys` |
| Android 版本 | **15**（SDK **35**），build type `user` |
| ABI | `x86_64`；abilist `x86_64,arm64-v8a,x86` |
| 物理分辨率 | **1080x1920**（原生竖屏）/ density **280** |
| WebView | `com.android.webview` **110.0.5481.154.1**（versionCode 548115537，targetSdk 33） |
| UA（WebView 实测） | `... Android 15; SM-S9280 Build/V417IR; wv) ... Chrome/110.0.5481.154 Safari/537.36` |
| CSS 视口 | 618×1098，`devicePixelRatio=1.75`，`scrollWidth==innerWidth`（无横向溢出、无裁切） |

### 竖屏锁定（必要步骤）

MuMu 默认自动旋转，首张截图拿到的是 **1920×1080 横屏**。竖屏需关闭自动旋转：

```powershell
adb -s 127.0.0.1:16384 shell settings put system accelerometer_rotation 0
adb -s 127.0.0.1:16384 shell settings put system user_rotation 0
```

探测结果：`user_rotation=0` → 1080x1920；`=1` → 1920x1080；`=2` → 1080x1920；`=3` → 1920x1080。
最终保持 `accelerometer_rotation=0, user_rotation=0`。

---

## 2. APK 身份、签名与来源

| 项 | 值 |
| --- | --- |
| 路径 | `.scratch/issue131-evidence/client.apk` |
| 大小 | **158,593,090** 字节 |
| **SHA-256** | **`8BB257DFD3A63D295B858DECBA7BA0DCEE44D6E20C063C01FEB1813F4F3FDDC8`** |
| 文件 mtime（UTC） | `2026-10-21T08:08:46Z` |
| 包名 / 版本 | `org.privacytrace.mobile` / versionCode **1000**，versionName **0.1.0** |
| min / target SDK | 24 / **36**；compileSdk 36（`platformBuildVersionName='16'`） |
| 启动 Activity | `org.privacytrace.mobile/.MainActivity` |
| native-code | `x86_64`（仅此一个 ABI） |
| 设备内安装路径 | `/data/app/~~mWWQWmuJ7XrCgMSiJnnbMQ==/org.privacytrace.mobile-4sW665q8cVxJDliruJtE3w==/base.apk` |
| 安装后 `primaryCpuAbi` | `x86_64` |

签名（`apksigner verify --print-certs`，JDK 用 `tmp\pr117-tools\jdk\jdk-17.0.20.1+1`）：

| 项 | 值 |
| --- | --- |
| DN | `C=US, O=Android, CN=Android Debug` |
| **证书 SHA-256** | **`4172668f29d3523bd5585ab9a2cb7dff237cf751b8cb39084565acd3f2205df2`** |
| 证书 SHA-1 | `c42bbb315be5108edddf8d920a7274f1098fbe7b` |
| 证书 MD5 | `39c277dc3f88d35f755c4435bb577dd6` |
| 签名方案 | v1 `false` / **v2 `true`** / v3 `false` / v3.1 `false` / v4 `false`；`Verifies` |

> 该 APK 使用 **Android Debug 调试证书**签名，属调试构建产物，不是发布签名。

**来源（provenance）——严格按既有事实记录，不声称在 00f9263 重建**

- 这是**此前已构建好的候选 APK**（candidate APK built earlier），本次**没有重新构建**。
- 委派方说明其构建来源为 issue #131 的应用源码，且与最终 main `00f9263` 的 `apps/mobile`、`apps/web` 差异为空。
- 本次会话**未验证**这一等价性；也未在本会话中检出或切换到 `00f9263`。
- 本机当前检出为分支 `codex/issue145-states-a11y`，HEAD = `5f12bcf3d2590030358b46b8b4e92f16ef45e343`，与 `00f9263` **不同**，故此 APK 不能称为「本检出构建」。
- 结论口径：**仅可作为候选 APK 的安装/运行/UI 证据，不可作为 00f9263 重新构建的证据。**

---

## 3. 安装与启动命令

```powershell
$adb = "<MuMu>/nx_main\adb.exe"; $S = "-s","127.0.0.1:16384"
& $adb @S install -r -t "<workspace>\.scratch\issue131-evidence\client.apk"
# -> Performing Streamed Install / Success: streamed 158593090 bytes / Success
& $adb @S shell am start -W -n org.privacytrace.mobile/.MainActivity
# -> Status: ok / LaunchState: COLD / TotalTime: 816~2011ms
```

为稳定截图，另关闭了动画（设备侧改动，非仓库改动）：

```powershell
adb @S shell settings put global window_animation_scale 0
adb @S shell settings put global transition_animation_scale 0
adb @S shell settings put global animator_duration_scale 0
```

截图统一用 `screencap` 落盘再 pull（避免 PowerShell 5.1 重定向破坏 PNG 二进制）：

```powershell
& $adb @S shell screencap -p /sdcard/shot.png
& $adb @S pull /sdcard/shot.png "<out>\<name>.png"
```

---

## 4. 截图清单（全部 1080×1920 原生竖屏 PNG）

目录：`<workspace>\.scratch\android-portrait\`

| # | 文件 | 分辨率 | 字节 | SHA-256 |
| --- | --- | --- | --- | --- |
| 01 | `01-launch-home_20261021T235308Z.png` | 1080x1920 | 94,213 | `D47DFC597C0DB57135B94125C377E36309B0DA88FF0BA858E46B04F826F45CC1` |
| 02 | `02-upload-origin-dialog_20261021T235419Z.png` | 1080x1920 | 171,608 | `89BDC39C09D8C2DA829E363B93E65E67B2AABFA65BB4774F2044A8A72572ED4C` |
| 03 | `03-origin-typed-unreachable_20261021T235547Z.png` | 1080x1920 | 167,813 | `6691AB442EBD99E9AC0F203BF4252AE5E777BDCF1A4808ACADF9313CC37F8365` |
| 04 | `04-server-unreachable_20261021T235607Z.png` | 1080x1920 | 99,111 | `2F9FFCA2D09E7EA5917C7B7C865181E258D29A05621E1DCF73D53C687F94A5E1` |
| 05 | `05-app-picker-native_20261021T235855Z.png` | 1080x1920 | 149,122 | `BDA430A6C060F3351832DE8559096F934EB141FA89F170C9174CCA54D3A2CA6D` |
| 06 | `06-limit-exceeded-apk-too-large_20261021T235927Z.png` | 1080x1920 | 96,934 | `907D93A962275911496984A6A42D8457DFBC0A8ADD098A10B53C58FF824CBA82` |
| 07 | `07-confirm-upload-scope_20261022T000126Z.png` | 1080x1920 | 203,732 | `62778A9496364FD9CF0AC5C9C3E639C2E7E4BFD63D7719210803ED493B6593B4` |
| 08 | `08-materials-and-policy-source_20261022T000218Z.png` | 1080x1920 | 154,299 | `B2E6BB08708C620A199E09B230A444E6B2FD6710628650CD342DA2E7DD115657` |
| 09 | `09-policy-candidates_20261022T000325Z.png` | 1080x1920 | 212,587 | `6D4FE7F5D87DFD6B6634C9F03604AB7608CA646539340842CFB5EC298573103E` |
| 10 | `10-delete-remote-busy_20261022T000815Z.png` | 1080x1920 | 213,437 | `9DB769FBD63180C19E2C144D5BBB12B2BCAA019A34E83143125619936A4496C6` |
| 11 | `11-final-clean-state_20261022T000826Z.png` | 1080x1920 | 94,012 | `51116E2175B289C1E882AA4F6B5FB0DE9438F98AB90EDFD0F350A513E2793F12` |

文件名内为 **UTC** 时间戳（`yyyyMMddTHHmmssZ`），与截图时刻一致。

### 每张的画面内容

| # | 画面 | 说明 |
| --- | --- | --- |
| 01 | 应用与政策（首页） | 标题「应用与政策」、说明「静态线索不证明实际采集」、卡片「选择要对照的应用」+ 两个按钮 |
| 02 | 选择上传实例（原生对话框） | 标题「选择上传实例」，正文说明协议/限额/加密本地保存，输入框「HTTPS 分析服务根地址」，按钮「取消」「检查并继续」 |
| 03 | 已填入不可达地址 | 输入框内容 `https://127.0.0.1:9` |
| 04 | `SERVER_UNREACHABLE` | 对话框关闭，首页红色错误码 `SERVER_UNREACHABLE`（未继续） |
| 05 | 原生应用选择器 | 标题「选择要读取的应用」，列出 10 个已安装应用：PrivacyTrace、图库、应用分身、文件、明日方舟、浏览器、游戏中心、相机、虚拟身份管理、设置 + 「取消」 |
| 06 | `LIMIT_EXCEEDED` | 在 05 中选择 **PrivacyTrace（158MB）** 后返回首页并显示红色 `LIMIT_EXCEEDED` |
| 07 | 确认上传所选应用（原生） | `设置 / com.android.settings · versionCode 35`、1 个包 · **29,267,536 字节**、`目标：https://localhost:28443/`、`实例：18dee246-d274-49d3-9bfa-73832a51a6d2`、`上传上限：157286400 字节（含打包开销）` + 「取消」「确认上传」 |
| 08 | 当前分析材料 + 政策来源 | 「材料版本 2」、`https://localhost:28443/`、`com.android.settings`、按钮「选择应用并上传」「恢复当前实例材料」「删除远端材料」；「政策来源」卡：尚未补入政策、两个辅助入口、「自动准备政策并继续」 |
| 09 | 检查政策候选 | 「政策待补充 · UNKNOWN」「重新提取候选」「候选声明 0」「已检查 0 / 0 条」「添加候选」「保存候选并开始分析」 |
| 10 | 删除远端材料的挂起态 | 首页显示「正在处理当前请求。停止本次请求」，请求未在 20s+ 内返回 |
| 11 | 干净最终态 | force-stop 后冷启动回到首页，无错误码、无挂起条 |

---

## 5. 可达流程（逐步，均已在设备上实际观察到）

1. **冷启动 → 首页**（截图 01）：`LaunchState: COLD`。
2. **点「选择应用并上传」→ 原生 `UploadOriginDialog`**（截图 02）。
   该对话框为原生 Android `AlertDialog`，与 uiautomator 节点一致（TextView / EditText / Button），
   源码对应 `experiments/android-package-probe/tauri-plugin/android/src/main/java/org/privacytrace/probe/UploadOriginDialog.kt`；
   WebView 的 `document.body.innerText` **不包含**该对话框文本，可据此区分原生与 Web 层。
3. **不可达地址 → `SERVER_UNREACHABLE`**（截图 03→04）：填入 `https://127.0.0.1:9`，点「检查并继续」，
   对话框关闭并显示 `SERVER_UNREACHABLE`，**不进入**选择器。
4. **可达实验室地址 → 原生应用选择器**（截图 05）：填入 `https://localhost:28443`（配合第 6 节的 `adb reverse`），
   健康检查通过后弹出「选择要读取的应用」。
5. **选择 158MB 的 PrivacyTrace → `LIMIT_EXCEEDED`**（截图 06）。
   客户端上传上限为 **157,286,400 字节**（见截图 07），该 APK 为 158,593,090 字节，
   因此在选择器里选它必然超限；探针侧也有 `maxFileBytes`/`maxTotalBytes`/`maxParts` 限制
   （`PackageProbe.kt`、`AnalysisTransport.kt` 中 `413 -> LIMIT_EXCEEDED`、`>8MB -> LIMIT_EXCEEDED`）。
6. **改装小包 `com.android.settings` → 确认上传对话框**（截图 07），点「确认上传」后**上传成功**。
7. **材料加载完成 → 政策来源界面**（截图 08）：「材料版本 2」、目标与包名、三个操作按钮，以及政策来源卡。
8. **「自动准备政策并继续」→ 检查政策候选界面**（截图 09），页面结构完整可用。

---

## 6. 实验室实例（WSL 侧）与打通方式

| 项 | 结果 |
| --- | --- |
| WSL 发行版 | `Ubuntu-24.04`（Running）；另有 `PrivacyTrace73-Runner`（Stopped） |
| WSL 内监听 | `LISTEN 127.0.0.1:28443` |
| WSL 内健康检查 | `curl -k https://localhost:28443/api/v1/health` → **http_code=200** |
| **Windows 宿主机** | **不可达**：`Test-NetConnection 127.0.0.1 -Port 28443` 返回 True（TCP 握手被接受），但 `https://localhost:28443/api/v1/health` **超时**；`netstat` 中 **无 28xxx LISTENING** 的 Windows 进程；`docker` 不在 PATH |
| 判断 | 该 listener 绑定在 WSL 的 `127.0.0.1`，Windows→WSL 的 localhost 转发能接受连接却无法完成请求（典型 127.0.0.1 绑定不回环转发）；`adb reverse` 的宿主机端也在 Windows，故默认不能用 |
| 实际打通方式 | `adb reverse tcp:28443 tcp:28443`（设备 `127.0.0.1:28443` → 宿主机 adb server → Windows `127.0.0.1:28443`）**仍然成功**：设备侧 TCP `nc` 返回 `rc=0`，且应用健康检查通过并弹出选择器，随后 29MB 上传成功 |
| 观察到实例 ID | `18dee246-d274-49d3-9bfa-73832a51a6d2` |
| 该实例来源 | **WSL 中既有的遗留实例**，不是本会话启动；freshness / 归属**未知**，**未做 reset**（避免影响其他会话的验收状态） |

> 说明：本次**没有**在设备上安装任何 CA，但客户端接受了该实例的 TLS 连接（健康检查通过、上传成功）。
> 本会话**无法解释**其信任来源（可能来自既有设备信任区或客户端校验策略），故不臆断，仅记录观察结果。

---

## 7. 被阻断的步骤（精确错误，未伪造）

| 步骤 | 触发 | 结果 |
| --- | --- | --- |
| 启动分析 | 截图 09 界面点「保存候选并开始分析」 | 首页红色错误码 **`UPLOAD_CONFLICT_REFRESH`**；等待 6×6s 后仍为该状态 |
| 启动分析（重试） | 再次点同一按钮 | **仍为 `UPLOAD_CONFLICT_REFRESH`** |
| 删除远端材料 | 点「删除远端材料」→ 又重新弹出**同一个来源对话框**（标题变为「删除远端材料」）→ 填 `https://localhost:28443` → 「检查并继续」 | 首页显示「正在处理当前请求。停止本次请求」，**20 秒以上未返回**（截图 10 即该挂起态） |
| 任务 / 报告界面 | 依赖分析启动成功 | **未取得任何截图** |

补充事实：**输入的服务根地址不会跨操作保留** —— 「选择应用并上传」「删除远端材料」都要重新填写来源地址。

---

## 8. 缺口清单（exact gaps）

1. **无任务/报告截图**：被 `UPLOAD_CONFLICT_REFRESH` 阻断，分析未启动，报告页面从未出现。
2. **`UPLOAD_CONFLICT_REFRESH` 根因未定位**：未判定是服务端材料版本冲突、草稿配额（README 提到 `MAX_DRAFTS_PER_IP = 3`）、还是 adb reverse 链路问题；未查看服务端日志。
3. **「删除远端材料」挂起未定位**：请求 20s+ 无响应，未抓服务端日志，未确认是否最终超时返回。
4. **未做实验室 reset**：未执行 `deploy/acceptance/mobile/lab-reset.sh`（需 `PT_LAB_STATE`，且会重建实例业务状态），故实例可能仍带前序会话残留。
5. **本构建不存在独立「设置」页**：首页仅有两个按钮，未发现设置/偏好路由；因此「app selection/settings」类截图由**原生应用选择器**（截图 05）与**上传确认范围**（截图 07）承担，**没有**设置页截图。
6. **APK 与 `00f9263` 的等价性未验证**，且本机 HEAD 为 `5f12bcf`（`codex/issue145-states-a11y`），不可据此声称重建。
7. **未覆盖横屏**：为满足竖屏要求强制 `user_rotation=0`，横屏布局仅在最初的误捕获中出现（已移入 `_internal/`，不列入交付清单）。
8. **未验证深度链路**：政策原文录入、候选逐条检查、模型/网页辅助等分支未逐个走通（停在空候选状态）。

---

## 9. 交接信息（供 lead 继续）

设备侧当前状态（本会话结束后**保持**）：

| 项 | 值 |
| --- | --- |
| **adb 端点** | **`127.0.0.1:16384`** |
| 模拟器 | **仍在运行**（未关闭、未 shutdown） |
| 旋转 | `accelerometer_rotation=0`，`user_rotation=0`（竖屏） |
| 动画 | 三个 scale 均为 0 |
| `adb reverse` | `host-12 tcp:28443 tcp:28443`（保留，用于继续打通实验室） |
| `adb forward` | `tcp:19222` → `localabstract:webview_devtools_remote_4338`（应用 pid 会变，需按新 pid 重建） |
| 应用状态 | 干净首页（截图 11 状态） |

继续全链路的建议入口：

```powershell
$adb = "<MuMu>/nx_main\adb.exe"; $S = "-s","127.0.0.1:16384"
# 1) 确认实验室健康（WSL 内）
wsl -d Ubuntu-24.04 -- bash -lc "curl -k -s -m 6 -o /dev/null -w '%{http_code}\n' https://localhost:28443/api/v1/health"
# 2) 若配额/草稿冲突，按仓库文档重置实例业务状态（会重建 PostgreSQL + materials + broker）
#    bash deploy/acceptance/mobile/lab-reset.sh   （需 PT_LAB_STATE）
# 3) 重连并保持 reverse
& $adb @S reverse tcp:28443 tcp:28443
# 4) 冷启动后走：选择应用并上传 -> 填 origin -> 检查并继续 -> 选小包(设置) -> 确认上传
#    -> 自动准备政策并继续 -> 保存候选并开始分析（当前卡在此步 UPLOAD_CONFLICT_REFRESH）
# 5) WebView DOM 读取（pid 换成当前值）
& $adb @S forward tcp:19222 localabstract:webview_devtools_remote_<pid>
node .scratch\android-portrait\_tools\cdp-eval.js ws://127.0.0.1:19222/devtools/page/<id> "document.body.innerText"
```

辅助脚本：`.scratch/android-portrait/_tools/cdp-eval.js`（Node 24 原生 WebSocket，无需依赖，用于读 DOM / 取控件坐标）。

---

## 10. 合规声明

- **未修改任何受版本控制的文件**：`git status --porcelain` 中无 tracked 变更（仅 `.scratch/` 等既有未跟踪项）。
- **未提交、未推送、未改 Issue**。
- 所有截图、错误码、设备属性均来自本会话实际命令输出；未出现推断性「已通过」结论。
