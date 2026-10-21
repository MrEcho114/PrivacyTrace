# #129 验收 A 执行记录（PT-MOB-301 自动政策、包输入与可复用环境样本）

状态：**EXECUTED / 已执行，未合并**。本记录只覆盖 #129 票边界；H02/H05/H08/H11 属其他票，本票未执行，也不据此推算通过。

被测候选：`main` `ffadeb06af70072b5ee2d931ee565e5b7e546acd`（已合入 PR #127/#137）。客户端用例全部在 **1080×1920 竖屏**（密度 480，`wm size 1080x1920`，`mRotation=0`）下重跑；服务器侧 N03/N04 不依赖屏幕，记录同一候选。

## 1. 结论速览

| 用例 | 输入 / 配置 | 结果 | 关键观察 |
| --- | --- | --- | --- |
| H01 | 单 APK / 标准配置 I | **PASSED** | 真实客户端上传、自动发现并抓取政策、自动候选、真实受限扫描、非空政策对照、原生删除确认 |
| H04 | base + fixture_feature / I | **PASSED** | 报告扫描 `split:fixture_feature:classes.dex`，对照表含 split 独有的通讯录访问线索 |
| H07 | 单 APK / 自托管配置 J | **PASSED** | 独立实例 J，与 I 分项目/卷/PKI/端口；同候选、同套客户端步骤 |
| H10 | base + fixture_feature / J | **PASSED** | J + splits；独立 outbox/队列投递 `DELIVERED` |
| N01 | 选择前取消、确认时取消、随后重选 | **PASSED** | 三种变体均未产生新草稿/上传，重选可用 |
| N02 | 确认窗口卸载、版本变化、不可读 | **PASSED** | 三变体均 `INSTALLATION_CHANGED`，草稿数增量 0 |
| N03 | 缺必需 split、错版本、错包名、重名、损坏 | **PASSED** | 服务端真实入口逐个明确拒绝；正常基线接受 |
| N04 | 总量/流式超限、慢上传、断流、重试 | **PASSED** | 413/超时/断流均有界，草稿保持 `uploaded=false`，重试不复用残留 |

未执行：H03/H06/H09/H12（手机模型路径，属其他票）；H02/H05/H08/H11（网页辅助，属其他票）；N05–N12、F01–F10、R01–R04（其他票或父票汇总范围）。本票不将上述任何项计为通过。

## 2. 候选与材料身份

| 产物 | 身份 |
| --- | --- |
| 源码 | `main` `ffadeb06af70072b5ee2d931ee565e5b7e546acd` |
| API 镜像 | `privacytrace-api:issue130-ffadeb0` = `sha256:30825e3640138465446fdd1d05dde21529ab63db98f587387142e2b1ed3f6aa2`，revision `ffadeb0…` |
| Web 镜像 | `privacytrace-web:issue130-ffadeb0` = `sha256:22a340efbcde68ab1b46fad3eec8a7f49658c9dba88cdf29b93207e4fefd26c5` |
| Runner 镜像 | `privacytrace-runner:issue130-ffadeb0` = `sha256:473975aeb2a77f115ec5d5c2b2ffc6b693add882a3001231ad7c6ec13c830c24` |
| 扫描镜像 | `privacytrace-scanner:issue130-ffadeb0` = `sha256:1a36604312f9d1e6184dd1ab0e4b49fd6c0674842f478d79f8f6b54541f94354` |
| 客户端 APK | `client-local-ca.apk`，SHA-256 `8bb257dfd3a63d295b858decba7ba0dcee44d6e20c063c01feb1813f4f3fddc8`，内嵌本机测试 CA（CN=PrivacyTrace73-Local-Test-CA，SAN 含 localhost/127.0.0.1） |
| 受控 base APK | `fixture-debug.apk`，SHA-256 `4f949286464a163886de6cdd9bd89651d19a622282c117339edfcb1c8e1055c1`，版本 1，`org.privacytrace.probe.fixture`，含 `ACCESS_FINE_LOCATION`、`READ_CONTACTS` 与 `<meta-data privacy_policy=http://1.1.1.1/policy.html>` |
| 受控 split | `fixture_feature-debug.apk`，SHA-256 `1467df6802cd638095e55f8d4c9e6e58a50fe76f393e5e284da78456b0da8db7`，`split="fixture_feature"`，install-time，同签名同版本 |
| 受控政策正文 | 472 字节 UTF-8，SHA-256 `2d9a31a5f1b1a64c5d9d800c5e64963f7207b095d4c8fdc64a1e7e3a1b6e7106`，由 `http://1.1.1.1/policy.html` 提供 |
| 静态线索 | base：`LocationProbe.readLastKnownGps` 调用 `LocationManager#getLastKnownLocation("gps")`（dex/方法/字节偏移可定位）；split：`ContactsProbe.readContacts` 调用 `ContentResolver#query(content://com.android.contacts/contacts)` |
| 执行器 | PR #137 移动执行器 `add79b6` 的 `client-case.cjs`，加本票本地执行补丁：候选页前重试点击（避免 busy 竞态）、报告页等待 `隐私声明对照` 而非宽松的“证据/政策”关键字（见 `harness/README.md`） |

## 3. 环境与隔离

- 实验室宿主：WSL 发行版 `PrivacyTrace73-Control`，独立 dockerd（netns `privacytrace73`，数据根 `/var/lib/privacytrace73/docker`），网络命名空间 `10.250.73.0/24`，政策源 `1.1.1.1:80 → 10.250.73.1:8080` 的受控 DNAT。
- 实例 I：Compose 项目 `pt81-c36811dfa963`，实例 `18dee246-d274-49d3-9bfa-73832a51a6d2`，HTTPS `127.0.0.1:60866`，宿主转发 `28443`。
- 实例 J：Compose 项目 `pt81-43f6be29e5c0`，实例 `fa470b68-ecc3-471d-93a1-102b3c5daa45`，HTTPS `127.0.0.1:59080`，宿主转发 `29444`。
- 两实例各自拥有 PostgreSQL/Redis/outbox、材料卷、PKI、Runner 容器与访问材料；共享的只有只读镜像和 docker daemon。
- 设备：MuMu 实例 `MuMu安卓设备-4`（Android 15，x86_64，`<SERIAL>`），分辨率 **1080×1920**、密度 480、rotation 0；`adb reverse tcp:29443 tcp:28443`（I）与 `tcp:29444 tcp:29444`（J）。
- 持久性：共享 daemon 曾被并行会话重启，`pt73-lab-watchdog`（I）与 J 转发/探针在健康检查失败时自动 `lab-up`/重启 relay；每个客户端用例前执行 `preflight.sh`/`preflight-j.sh` 修复政策出口、校验 mock/model/政策抓取。环境中断只影响中断时的尝试；本记录中的用例均在恢复后完整重跑。

## 4. 成功组合（H01/H04/H07/H10）

四例均满足：

1. 实际 Android 客户端选择并确认安装集合，报告中的 APK SHA-256 与安装材料一致；H04/H10 的扫描范围明确包含 `split:fixture_feature:classes.dex` 与 `classes2.dex`。
2. 服务端 PostgreSQL `outbox_events` 中 `privacytrace.job.ready` 为 `DELIVERED`、attempts=1（I：09:54:43Z H01、09:58:16Z H04；J：09:56:42Z H07、10:00:06Z H10）；对应报告为 `REAL_SCAN`。
3. Runner 容器镜像 `sha256:473975…` 与扫描镜像 `sha256:1a3660…` 一致，报告来自本次输入，不是预制回放。
4. 政策来源为 `Auto Discovered Policy · 已获取网页正文 · Manifest 发现`，请求/最终 URL 均为 `http://1.1.1.1/policy.html`；对照表非空：H01/H07 三行（精确位置、通讯录、位置），H04/H10 四行（另有 split 的通讯录访问行）。
5. 结论限定为 `证据不足 / 待复核`，没有把静态线索说成实际采集或一致性 MATCH；删除材料通过客户端的原生两步确认，结果 `DELETED`。

证据：`evidence/H01-I-*`、`H04-I-*`、`H07-J-*`、`H10-J-*`（result JSON、报告正文、1080×1920 设备截图）。

## 5. 负向与边界

### N01（选择/确认取消与重选）

- N01a：应用列表点“取消”，无新草稿（草稿数 1→1），UI 回到材料页。
- N01b：选中应用后在“确认上传所选应用”按返回键取消，无新草稿（1→1），回到材料页。
- N01c：取消后可再次“选择应用并上传”、输入实例并重新进入应用列表（1→1），未触发未确认上传。
- 证据：`evidence/n01a-*`、`n01b-*`、`n01c-*`。

### N02（确认窗口安装态变化）

- 卸载：在确认窗口 `adb uninstall` 目标包后点“确认上传”，客户端显示 `INSTALLATION_CHANGED`，草稿数 1→1。
- 版本变化：确认窗口内把 v1 覆盖安装为 v2（versionCode 2）后确认，`INSTALLATION_CHANGED`，1→1。
- 不可读：以 `adb root` 将 base.apk 置为 `chmod 000` 后确认，`INSTALLATION_CHANGED`，1→1；随后恢复 `644` 并核对文件模式。
- 证据：`evidence/n02-*`、`n02v-*`、`n02u-*`。未提交部分集合，也没有服务端接收。

### N03（受控包集合变体）

对真实 HTTPS `/package-set` 入口逐个上传 ZIP：

| 变体 | 结果 |
| --- | --- |
| 正常 v1 base + fixture_feature | 200；`package_set` 记录 base/split 名称、SHA-256、`total_size_bytes=15225`，`uploaded=true` |
| 缺必需 split（base `isSplitRequired=true`，无 split） | 400 `MISSING_REQUIRED_SPLIT` |
| split 版本 2 / base 版本 1 | 400 `VERSION_CODE_MISMATCH` |
| split 包名 `org.privacytrace.probe.other` | 400 `SPLIT_PACKAGE_MISMATCH` |
| 两个 `fixture_feature` 重名 split | 400 `DUPLICATE_SPLIT_NAME` |
| split 字节截断（ZIP 内 APK 损坏） | 400 `CORRUPTED_FILE` |

所有拒绝后草稿均为 `uploaded=false`，未降级为 base-only。证据：`evidence/N03-results.json`。

### N04（上传大小、流式、慢上传、断流、重试）

| 变体 | 观察 |
| --- | --- |
| 160 MiB 定长 body（上限 150 MiB） | 413 `UPLOAD_TOO_LARGE`，实际发送 114,294,784 字节、0.57 s，草稿 `uploaded=false` |
| 160 MiB chunked（无 Content-Length） | 413，发送 167,772,160 字节、0.81 s，`uploaded=false` |
| 190 s 慢速发送 | 连接被服务端关闭（客户端 `TimeoutError`，总观测 460 s），`uploaded=false` |
| 发送 1 MiB 后直接断开 | 4 s 后草稿仍 `revision=1 / uploaded=false`，无半成品 |
| 413 后用同一草稿重试合法 ZIP | 200，`uploaded=true`；不复用残留 |

证据：`evidence/N04-fast.json`、`N04-extra.json`、`N04-slow.json`。

## 6. 环境样本与复现

`environment-recipe.md` 给出可复用配方：独立项目名、端口范围、数据卷、daemon/网络命名空间、模拟器显式目标、政策出口、受控提取器与 preflight/看门狗。`harness/` 保留脱敏后的脚本模板；本机绝对路径已在提交副本中替换为占位符。

## 7. 边界与未覆盖

- 受控提取器是 **本机容器内的确定性 OpenAI 兼容 mock**，用于走通既有服务端提取路径；不证明外部模型质量，也不是 H03/H06/H09/H12 的手机模型路径。
- 政策对照结论为 `INSUFFICIENT_EVIDENCE / 待复核`；按 #129 测试决策，不要求 MATCH，也不把 UNKNOWN/PARTIAL/UNREVIEWED 提升为已复核。
- N03/N04 走真实 HTTPS 服务端入口，不经 Android 界面；因此不受分辨率指令影响，也未把它们伪装成客户端截图证据。
- 共享 daemon 的并行会话重启会造成短时中断；本记录不把他人的运行结果混入，用例均在恢复后从客户端重新执行。
- 未合并、未部署、未提交商店；PR #137 执行器的两处重试补丁仍需由执行器 owner 决定是否上游化。

## 8. 证据清单

`evidence/` 下的文件及 SHA-256 见 `evidence-manifest.sha256`。清单包含四组 H 的 result/报告正文/1080×1920 截图、N01/N02 的摘要与截图、N03/N04 的 JSON 结果。原始运行日志、APK 与完整政策正文留在受保护的私有运行区，不进入仓库。
