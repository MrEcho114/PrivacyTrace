# #136 / #128：H 手机主线在最终交付组合上的补测（2026-10-22）

Refs #136、#128、#145、#173。本记录补齐父票门禁中“从最终交付组合安装声明支持 ABI 的实际 APK、单包与 splits 各一条完整主线、停启后恢复旧任务、Web 对照”的本机手机侧证据。它不是父票最终放行结论，也不替代 H01–H12 组合矩阵、N/F/R 各自收据。

## 1. 必测组合身份

| 项 | 值 |
| --- | --- |
| 交付 head | `262615242161e0371ec151a5f07ef19d360a35e3`（Merge PR #173），`merged_at 2026-10-22T07:45:27Z` |
| 源码树 | `1a662a23eb9eea57135391f3f2d63ca73456fc16`（与 `017f031` 同树；`git diff --stat 017f031 2626152` 为空） |
| 客户端 APK | `client-local-ca-2626152.apk`，sha256 `955d484ba0a01bcf0472e7d97b24fe0d84698af8c61b0efe38b762ca7d3e6088`，157,543,412 B |
| APK 版本/ABI | `org.privacytrace.mobile` 0.1.0（versionCode 1000），minSdk 24 / targetSdk 36 / compileSdk 36，`x86_64` |
| 签名 | Android debug keystore（v2），证书 SHA-256 `4172668f29d3523bd5585ab9a2cb7dff237cf751b8cb39084565acd3f2205df2` |
| 嵌入前端 | `index-BxZBQKot.js` sha256 `41de266408ef5835a643ab4b5eefb105a83e799e56d1427e412810eba5bbfaf6` |
| CA 信任 | 仅对 `localhost` 追加 `CN=PrivacyTrace73-Local-Test-CA`（PEM sha256 `1a9330d8…e0f9`）；base-config 保持系统锚点、禁止明文，无 trust-all |
| 服务端 | 候选源码同 head 的 API/Web/Runner/Scanner 镜像（rev=4208823，产品树与 2626152 相同）；独立一次性实验室，实例 UUID 与端口逐次记录在受限证据中 |
| 设备 | MuMu VM3（Android 15 / API35 / x86_64），`1080×1920` 竖屏 |

**APK 字节一致性：** `017f031`（PR #173 head 的产品树）与 `2626152` 的 product tree 相同，按 `2626152` 重建的 APK 与按 `017f031` 构建的 APK **sha256 完全相同**（`955d484b…6088`）；因此两次构建的产品内容一致，splits/停启恢复项引用 017f031 组合的运行，单包主线在 2626152 APK 上实跑。

## 2. 逐项结果

| 项 | 状态 | UTC 时间（含时区） | 实际观察 | 证据（受限保存，含 SHA256 索引） |
| --- | --- | --- | --- | --- |
| 最终 APK 安装 | PASSED | 2026-10-22T07:55:36Z | `adb install -r` Success；`pm path` 指向新安装；`dumpsys package` versionCode/versionName/primaryCpuAbi 回读一致 | `apk-install-final-2626152.txt`、`package-dump-2626152.txt` |
| 单包主线（2626152 APK 实跑） | PASSED | 2026-10-22T08:04:04Z | 真实客户端选包→确认→HTTPS 上传→受控政策补入→候选→真实 Docker 扫描→报告：`job_state=SUCCEEDED`、`policy_comparison=PRESENT`、`evidence_captured=2`、`evidence_quote=true`；报告扫描行 `已扫描 base:classes.dex、base:classes2.dex；失败 无。`；证据面板 `原文位置：[25, 34)`；原生 1080×1920 截图 | `canonical-2626152/single/` 结果 JSON、webview 正文、evidence、设备 PNG、包集快照、上传确认框；`evidence-sha256.txt` |
| splits 主线（同树组合，引用 017f031 运行） | PASSED | 2026-10-22T06:03:31Z | `install-multiple` 两包；上传确认框 `2 个包`；报告扫描行含 `split:fixture_feature:classes.dex`；split 调用点/offset=24 可下钻；证据 3 条 | `splits/…-result.json`、包集快照、上传确认框、设备 PNG |
| 停启恢复 | PASSED | STOP `06:03:57Z` → START `06:04:16Z`；恢复 `06:13:16Z` | 保留卷的 `compose stop/start` 后 health 200；停前/停后/恢复后 DB 均为 `job_count=2` 且同一 job 集合、outbox 2/2；客户端「恢复当前实例材料」回到 job `996357aa…` 的同一报告（含 split 扫描行），**未新建任务** | `db-before-restart.json`、`db-after-restart.json`、`db-after-restore.json`、`recovery/` |
| Web 同一任务下钻 | **NOT_RUN** | 2026-10-22T06:05–06:15Z 探测 | 浏览器可打开工作台（HTTP 200），但 remote-mode 拒绝 `X-PrivacyTrace-Local`（`POST /api/v1/web/drafts` → 403 `Local header forbidden in remote mode`）；同一草稿读取需要只存在于 Android Keystore 原生加密存储的 `pt_cap_` capability（`GET /api/v1/web/drafts/{id}` → 401）。**未使用 Web 侧新建任务冒充同任务对照，也未伪造截图。** | `web/web-draft-probe.log`、`web/web-single-result.json` |
| 清理 | PASSED | 2026-10-22T08:07Z | 自建实验室 `down --purge`（state REMOVED）；设备 reverse/forward 清理；未触碰其它实验室或设备 | 清理回读日志 |

## 3. 夹具身份

| 用途 | sha256 | 观察 |
| --- | --- | --- |
| 空夹具（早期观察，未用于最终对照） | `65047dbcf0b3ef4876d422b68e5bde777a13dd84f59bd946c66c1279921ab981` | 静态行为 0：报告“数据类型 0 / 未产生对照项”，没有“查看 N 条证据”入口，不满足非空对照要求 |
| 受控行为夹具 base（最终） | `51419844c6305b99ee930dd77d15162f606e39a94b57f1939858eda43bedc44f` | label `Controlled B fixture`，versionCode 130，`ACCESS_FINE_LOCATION` + `getLastKnownLocation("gps")` |
| 受控行为夹具 split（最终） | `9991311fb07b8ea2f595578f442e514ba138fa04b1367bcbb4f14ff114f848ff` | `ContentResolver.query(content://com.android.contacts/contacts)` |

## 4. 4208823 → 2626152：主线阻断缺陷与修复

- 在 `4208823` 的候选 APK 上，服务端任务已 `SUCCEEDED`、DB `coverage.scanned_dex=[base:classes.dex]`，客户端进度页却停在“等待处理 + `BUSY_OR_INACTIVE`”，必须手动点“刷新进度”才出现“报告已生成”。
- 根因：#145（`fc075fe`）把后台轮询改成 `Promise.all([bridgeRequest('job'), bridgeRequest('read')])`，原生 `ProbeOperationGate` 同一时刻只允许一个 workflow 操作（`experiments/android-package-probe/core/src/main/java/org/privacytrace/probe/ProbeOperation.kt:17`），第二个请求被判 busy；`schedule()` 只把 `SERVER_BUSY` 视为可重试，其它错误直接停止轮询。ffadeb0 的顺序实现不复现。
- 修复：PR #173（顺序读取 + 有界 `BUSY_OR_INACTIVE` 快速重试；新增 3 条回归，先红后绿 15/15），用户 2026-10-22 批准合并，main 前进到 `2626152`。

## 5. 未覆盖边界（不得省略）

- 仅 `x86_64`、MuMu VM3 / Android 15（API35）；真机、`arm64-v8a`/`armeabi-v7a`、API36 运行时未覆盖。
- debug 签名（v2），不是发布/store 签名；`localhost` 追加测试 CA 是验收构建与产品默认信任的差异，不能外推其它主机或系统信任。
- 单包 canonical 运行的 `deletion` 为 `SKIPPED`（随后实验室整体 purge），不覆盖删除生命周期；删除/取消/重试由 #133 的 N12/F05/F06 收据覆盖。
- 本记录不覆盖 H01–H12 的政策组合矩阵（自动/网页辅助/模型 × 单包/splits × 两实例），也不覆盖 N/F/R 矩阵。
- 停启恢复只覆盖服务暂停/恢复后客户端“恢复当前实例材料 → 同一任务同一报告”；不覆盖进程被杀、浏览器刷新、跨实例切换。
- Web 同一任务下钻为已记录缺口（安全模型：capability 只在设备原生存储）；Web 起源任务的下钻由 #130 的 H02/H05 覆盖。
