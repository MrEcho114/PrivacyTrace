# Issue #130 B 执行记录（2026-10-21）

本文件是 [README](README.md) 的详细执行日志。所有时间为 UTC（北京时间减 8 小时），
最终 H 案例在 1080×1920 竖屏下复跑。`PASSED` 仅表示本票定义的案例变体完成，
不表示父票 #128 的全矩阵通过。

## 1. 范围与结果

本票主责：H02、H05、H08、H11、N09、N10。H 案例按「单 APK / 完整 splits ×
本机官方配置 I / 本机自托管配置 J × 网页辅助」的四组合执行；N09/N10 在实例 I
用同一任务的服务端政策准备接缝注入。A/C/D/E/F/G 的案例不在本记录中。

| ID | 结果 | 说明 |
| --- | --- | --- |
| H02 | PASSED | 单 APK、I、网页辅助；非空对照与原句区间 |
| H05 | PASSED | base＋全部已安装 splits、I；split 独有通讯录调用被识别 |
| H08 | PASSED | 单 APK、J；与 H02 相同的非空对照 |
| H11 | PASSED | base＋全部已安装 splits、J；与 H05 相同的 split 证据 |
| N09 | PASSED | 回环/私网/元数据、危险重定向、超大、慢响应全部按预期拒绝/有界 |
| N10 | PASSED | 抓取失败保留旧材料；畸形输入拒绝；冲突候选不升级；报告保持未复核 |

## 2. 被测身份

| 项 | 实际值 |
| --- | --- |
| 源码 | `ffadeb06af70072b5ee2d931ee565e5b7e546acd`（main，含 #127/#137） |
| API / Web / Runner / Scanner | `privacytrace-*:issue130-ffadeb0`；经 `deploy/Dockerfile`、`Runner.Dockerfile`、`Scan.Dockerfile` 构建 |
| 客户端 | debug `client-local-ca.apk`，SHA-256 `53416AEE102B3184F10FB7903FECE66DCC713AC73B327CD139C811911F11F474`，大小 157558870 |
| 受控样本 | base `51419844C6305B99EE930DD77D15162F606E39A94B57F1939858EDA43BEDC44F`（7501 B）；split `9991311FB07B8EA2F595578F442E514BA138FA04B1367BCBB4F14FF114F848FF`（7620 B） |
| 实例 I | project `pt81-6914bd8e34aa`，instance `5dcdd930-84a7-433f-bbd5-373b6bd491e6`，内部 HTTPS 60944，移动转发 28544 |
| 实例 J | project `pt81-ab4f0a59aa79`，instance `b0509091-925e-4d5f-8f9c-87b1bccf43e9`，内部 HTTPS 58910，移动转发 28545 |
| 模拟器 | MuMu `PrivacyTrace130`（索引 3），Android 15 / API 35 / x86_64，1080×1920 竖屏，ADB `127.0.0.1:16480` |
| 测试 CA | `CN=PrivacyTrace130-Local-Test-CA`，SHA-256 指纹 `86:14:D8:D0:98:57:88:1A:0B:BD:13:01:D3:FF:56:2B:3F:13:99:E0:C2:72:0F:D2:0A:79:B3:86:D3:5E:FE:B3` |
| 受控策略源 | `http://1.0.0.1/policy.html` → 命名空间 DNAT → `10.250.73.2:8082`；正常、重定向、超大、慢响应、错误类型、500 均由同一服务提供 |

## 3. 首轮执行器缺陷与保留

首轮 H02 在真实客户端和实例 I 上完成了上传、辅助导入、保存候选和分析
`SUCCEEDED`，但执行器停在进度页：`policy_comparison=UNKNOWN`、页面文本 884 字符。
报告页的「查看报告」按钮在终态刚出现时仍是 disabled；且执行器用「证据/政策」
作为报告页判断，而进度页本身也含这两个词。失败观察保存在
`evidence/harness-bug/H02-local-I-single-assist-first-run-result.json` 与
`...-webview.txt`。

随后发现证据面板的实际文案是「政策快照引用」「原文位置」，不是「代码位置」。
修复内容（`deploy/acceptance/mobile/client-case.cjs`）：

1. `clickEnabled`：等到按钮 enabled 后再点击「查看报告」。
2. 报告页等待条件改为「隐私声明对照 / 扫描覆盖」。
3. `captureEvidence`：按行打开全部「查看 N 条证据」并写入 `-evidence-N.txt`；
   面板等待「原文位置」。
4. 支持 `policyText` 与 `candidates` 数组，便于同一受控来源对基础/分裂样本
   各补一条有效原句。

修复后先复跑 H02（PRESENT），再在竖屏下完成四个 H 案例；原始失败未被覆盖。

## 4. H 案例

四例共同观察：

- 报告页显示 `REAL_SCAN · 真实 APK 静态扫描` 与 `PERSISTED_REPLAY`；
  JADX 不可用时保留字节码证据。
- 网页辅助导入的来源保持 `UNREVIEWED`、提取 `PARTIAL`、快照 `PARTIAL`、
  附件 `NOT_CHECKED`；对照结论为 `INSUFFICIENT_EVIDENCE · 待复核`，
  未升级为 `MATCH`。
- 每例最终 `job_state=SUCCEEDED`、`deletion=DELETED`、`policy_comparison=PRESENT`。

### H02

| 项 | 实际 |
| --- | --- |
| 输入 | 单 base APK；仅安装 `base` |
| 实例 / origin | I / `https://localhost:28544/` |
| 涉及数据类型 | 1（`PRECISE_LOCATION`） |
| 对照行 | 2（快照来源 1 条证据；官网政策来源 2 条证据） |
| 代码证据 | `base:classes2.dex`，caller `ProbeBehavior.accessLocation`，`offset_bytes=4`，target `LocationManager.getLastKnownLocation`，rule `android.location.last-known.gps`，context `{"provider":"gps"}` |
| 原句 | `我们访问精确位置。`，codepoints `[25,34)` |
| 结果 | `SUCCEEDED`；2 条证据面板；`DELETED` |

证据：`H02-local-I-single-assist-webview.txt`、`-evidence-1.txt`、`-evidence-2.txt`、
`-candidates.txt`、`-result.json`。

### H05

| 项 | 实际 |
| --- | --- |
| 输入 | `install-multiple` base + `fixture_feature` split |
| 实例 / origin | I / `https://localhost:28544/` |
| 扫描范围 | `base:classes.dex`、`base:classes2.dex`、`split:fixture_feature:classes.dex`、`split:fixture_feature:classes2.dex`，失败无 |
| 涉及数据类型 | 2（`PRECISE_LOCATION`、`CONTACTS`） |
| 对照行 | 3 |
| 精确定位证据 | `base:classes2.dex`，`offset_bytes=4`，rule `android.location.last-known.gps`，原句 `[25,34)` |
| 通讯录证据 | `split:fixture_feature:classes2.dex`，caller `ProbeBehaviorFeature.accessContacts`，`offset_bytes=24`，target `ContentResolver.query`，rule `android.contacts.query`，context `{"uri":"content://com.android.contacts/contacts"}`，原句 `我们读取联系人。` `[34,42)` |
| 结果 | `SUCCEEDED`；3 条证据面板；`DELETED` |

证据：`H05-local-I-splits-assist-webview.txt`、`-evidence-1.txt`、`-evidence-2.txt`、
`-evidence-3.txt`、`-candidates.txt`、`-result.json`。

### H08

单 base APK、实例 J、origin `https://localhost:28545/`。观察与 H02 相同：
1 个数据类型、2 条对照行、原句 `[25,34)`、`SUCCEEDED`、2 条证据面板、
`DELETED`。证据前缀 `H08-local-J-single-assist`。

### H11

base + `fixture_feature` split、实例 J。观察与 H05 相同：2 个数据类型、
3 条对照行、通讯录原句 `[34,42)`、split 字节码证据、`SUCCEEDED`、3 条证据面板、
`DELETED`。证据前缀 `H11-local-J-splits-assist`。

## 5. N09 变体

全部在实例 I 上通过真实的 `POST /api/v1/web/drafts/{id}/sources/{id}/fetch`
执行；受控服务记录每个实际到达的请求。`请求增量` 是受控源请求日志的差值；
直接回环/私网/元数据在连接前即被拒绝，重定向在解析目标时被拒绝。

| 变体 | 目标 | 拒绝码 | 耗时 | 请求增量 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 回环 | `http://127.0.0.1:19090/secret` | `PUBLIC_URL_REQUIRED` | 0.089s | 0 | PASS |
| 私网 | `http://10.0.0.1/secret` | `PUBLIC_URL_REQUIRED` | 0.622s | 0 | PASS |
| 元数据 | `http://169.254.169.254/latest/meta-data/` | `PUBLIC_URL_REQUIRED` | 0.744s | 0 | PASS |
| 重定向到回环 | `http://1.0.0.1/redirect-local` | `PUBLIC_URL_REQUIRED` | 0.527s | 1（仅初始请求） | PASS |
| 重定向到私网 | `http://1.0.0.1/redirect-private` | `PUBLIC_URL_REQUIRED` | 1.028s | 1 | PASS |
| 重定向到元数据 | `http://1.0.0.1/redirect-metadata` | `PUBLIC_URL_REQUIRED` | 1.070s | 1 | PASS |
| 无限重定向 | `http://1.0.0.1/redirect-loop` | `FETCH_REDIRECT_LIMIT` | 1.948s | 4（初始＋3 次跟随） | PASS |
| 超大响应 | `http://1.0.0.1/huge` | `FETCH_TOO_LARGE` | 0.569s | 1 | PASS |
| 慢响应 | `http://1.0.0.1/slow` | `FETCH_TIMEOUT` | 15.081s | 1 | PASS |
| 错误 Content-Type | `http://1.0.0.1/wrong-type` | `FETCH_HTML_REQUIRED` | 0.533s | 1 | PASS |
| 正常受控源 | `http://1.0.0.1/policy.html` | `ready`、非空正文 | 0.628s | 1 | PASS |

附加观察：在 API 容器网络命名空间内绑定 `127.0.0.1:19090` 的内部标记监听，
执行重定向到回环的同一路径，监听连接数为 **0**，耗时 0.587s，拒绝码
`PUBLIC_URL_REQUIRED`，正文为空；见 `redirect-local-egress.json`。

所有失败来源均保留 `status=failed`、`error_code`、无正文；没有把拒绝改成成功，
没有关闭 SSRF 守卫，也没有放开私网规则。

## 6. N10 变体

在实例 I 上创建一个同时含手动正文来源 A、失败抓取来源 B、空来源 C 的草稿，
先上传 base APK，再注入失败和畸形/冲突候选：

| 步骤 | 预期 | 实际 | 结果 |
| --- | --- | --- | --- |
| 抓取 B `/fail` | 失败显式呈现，A 不变 | B `failed` / `FETCH_HTTP_FAILED`；A 文本、SHA、状态均不变；revision 1→3 | PASS |
| 原句不在来源 | 拒绝 | 409 `INPUT_OR_VERSION_REJECTED`；候选未变 | PASS |
| offset 与原文不符 | 拒绝 | 409；候选未变 | PASS |
| 引用不存在来源 | 拒绝 | 409；候选未变 | PASS |
| 原文出现两次且未给 offset | 拒绝 | 409；候选未变 | PASS |
| 冲突候选 | 保留但不确认 | 两个候选接受；分析 `SUCCEEDED`；报告 2 行 `INSUFFICIENT_EVIDENCE · 待复核`；文档 `UNREVIEWED/PARTIAL/PARTIAL/NOT_CHECKED`；claims=2 | PASS |
| 自动重新抽取/升级 | 不应发生 | `model_audit` 空；无新候选；未升级为 `MATCH` | PASS |

N10 的“冲突候选”是**同一原句、不同 data_type/极性**的候选；产品保留两者并
不把它们变成确定匹配。报告仍按 `INSUFFICIENT_EVIDENCE` 展示，符合
“不升级 UNKNOWN/PARTIAL/UNREVIEWED”的要求。

## 7. 清理与边界

- 每个 H 案例通过客户端原生双确认删除远端材料，结果均为 `DELETED`；
  N09/N10 每个草稿结束后通过 API 删除。
- 证据读回并哈希后已执行清理（UTC 2026-10-21T10:21Z）：停止 28544/28545 relay
  和受控政策源/内部标记监听；移除 B 专用 `1.0.0.1:80` DNAT 与宿主返回路由；
  purge 实例 I/J 的容器、卷和状态目录；停止专用模拟器 `PrivacyTrace130`
  （保留已安装包供复核，不再运行）。清理后确认两个 lab 状态目录、lab 容器和
  relay 端口均不存在。
- 未执行：物理设备、OEM/其他 ABI、真实公网、外部模型质量、商店审核；
  未合并、未部署、未正式提交。
- 本票不因本记录自动关闭 #130/#128；父票仍需汇总全部子票。
