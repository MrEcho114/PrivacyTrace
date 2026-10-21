# Issue #130 · B 验收记录（网页辅助、政策来源与引用保留）

> 执行日期：2026-10-21（北京时间，UTC+08:00）。本票只覆盖 B 的六个主责案例：
> H02、H05、H08、H11、N09、N10。父票 [#128](https://github.com/MrEcho114/PrivacyTrace/issues/128)
> 的其余 H/N/F/R 案例不在本记录内，本记录不替代父票放行。

## 结论

| 案例 | 输入 / 实例 | 结果 | 关键证据 |
| --- | --- | --- | --- |
| H02 | 单 APK / 本机官方配置 I / 网页辅助 | **PASSED**（范围：本票定义的单变体） | 报告含 1 个可定位静态数据类型、2 条对照行、`INSUFFICIENT_EVIDENCE · 待复核`；精确定位原句 `[25,34)` |
| H05 | base＋全部已安装 splits / I / 网页辅助 | **PASSED**（范围：本票定义的单变体） | 扫描覆盖 `base` 与 `split:fixture_feature`；通讯录原句 `[34,42)`；split 字节码 `android.contacts.query` |
| H08 | 单 APK / 本机自托管配置 J / 网页辅助 | **PASSED**（范围：本票定义的单变体） | 与 H02 相同的非空对照，实例 J |
| H11 | base＋全部已安装 splits / J / 网页辅助 | **PASSED**（范围：本票定义的单变体） | 与 H05 相同的 split 证据与通讯录原句，实例 J |
| N09 | 回环/私网/元数据、危险重定向、超大/慢响应 | **PASSED** | 目的地类别、拒绝码、实际出站请求数、耗时均记录；内部标记监听 0 连接 |
| N10 | 已有政策＋抓取失败、畸形原句/引用/冲突候选 | **PASSED** | 旧材料文本/SHA 不变；4 类畸形输入 409；冲突候选保留但不升级；报告保持 `UNREVIEWED/PARTIAL` |

本结论仅覆盖本机受控环境，不判断违法、安全或实际采集，也不外推到真机、OEM、公网、外部模型质量或商店审核。

## 环境与版本

- 被测源码：`ffadeb06af70072b5ee2d931ee565e5b7e546acd`（main，含 #127、#137）。
- 控制面镜像（同源构建）：`privacytrace-api:issue130-ffadeb0`、`privacytrace-web:issue130-ffadeb0`、`privacytrace-runner:issue130-ffadeb0`、`privacytrace-scanner:issue130-ffadeb0`。完整 image id 见 [evidence/environment.json](evidence/environment.json)。
- 客户端：仅对 `localhost` 追加本机 B 测试 CA 的 debug APK，SHA-256 `53416AEE102B3184F10FB7903FECE66DCC713AC73B327CD139C811911F11F474`；未使用 trust-all，未修改正式默认信任。
- 受控夹具：base `51419844…`、feature split `9991311F…`，版本码 130；base 含 `LocationManager.getLastKnownLocation("gps")`，split 含 `ContentResolver.query(content://com.android.contacts/contacts)`。
- 模拟器：MuMu Player 12 专用实例 `PrivacyTrace130`（索引 3），Android 15 / API 35 / x86_64，**1080×1920 竖屏**（`SurfaceOrientation=0`）；ADB `127.0.0.1:16480`。
- 实例：I `pt81-6914bd8e34aa` / instance `5dcdd930-84a7-433f-bbd5-373b6bd491e6`；J `pt81-ab4f0a59aa79` / instance `b0509091-925e-4d5f-8f9c-87b1bccf43e9`。
- 移动端入口：I `https://localhost:28544/`，J `https://localhost:28545/`；经 `adb reverse` + 独立 TCP relay 暴露，TLS 证书链和主机名校验保持开启。
- 受控政策源：`http://1.0.0.1/policy.html`，在实验室命名空间内 DNAT 到 `10.250.73.2:8082`；正常/重定向/超大/慢响应/错误类型/失败由同一受控服务提供。

## 证据与输出

- 证据索引与逐文件 SHA-256：[evidence/manifest.json](evidence/manifest.json)。
- 环境身份（镜像、实例、PKI、客户端、夹具、模拟器）：[evidence/environment.json](evidence/environment.json)。
- H 案例原始页面/证据面板文本与执行器结果 JSON：`evidence/H02-*`、`H05-*`、`H08-*`、`H11-*`。
- N09/N10 逐变体结果：[evidence/n09-n10-results.json](evidence/n09-n10-results.json)。
- 回环重定向的 API 容器内标记监听结果：[evidence/redirect-local-egress.json](evidence/redirect-local-egress.json)。
- 截图（webview/evidence/device）保留在本机 `tmp/issue130-evidence/`，其 SHA-256 也已写入 manifest 的 `local_only_screenshots`；不把本机路径提交进仓库。

## 执行器缺陷与修复

本次在首轮 H02 实际运行中发现了验收执行器的两个问题，先保留失败观察，再修复并复跑：

1. **报告页等待条件过宽。** `waitFor` 只等待「证据」或「政策」，而进度页本身也包含这两个词；同时「查看报告」按钮在终态刚出现时仍为 disabled。首轮 H02 因此停在进度页，记录为 `policy_comparison=UNKNOWN`、884 字符。
2. **证据面板断言错误。** 报告面板没有「代码位置」文案，实际是「政策快照引用」「原文位置」；逐行捕获时只应等待「原文位置」。

修复位于 `deploy/acceptance/mobile/client-case.cjs`：等待已启用的「查看报告」按钮、使用报告页专有标题、按行捕获证据面板、支持 `policyText` 与多候选。失败观察与修复后结果均保留，未用修复覆盖原始失败记录。

## 复跑命令

```powershell
$env:PT_ADB_SERIAL = '127.0.0.1:16480'
$env:PT_ADB = '<adb.exe>'
$env:PT_EVIDENCE_DIR = '<本次证据目录>'
$env:PT_CA_CERT = '<B 测试 CA>'
node deploy/acceptance/mobile/client-case.cjs deploy/acceptance/mobile/cases-b/case-H02.json
```

H05/H11 需先安装 base＋feature split；H08/H11 使用实例 J 的 origin 与对应 `adb reverse`。
完整拓扑、镜像和夹具身份见 [environment.json](evidence/environment.json)。N09/N10 的注入方式与
逐项结果见 [执行记录](execution-20261021.md)。夹具注入文件在
`deploy/acceptance/issue130/fixtures/`；受控政策源与 DNAT 拓扑在
`deploy/acceptance/issue130/policy-source/`。这两份是测试资料，不是产品组件。

## 边界

- 报告中的对照结论为 `INSUFFICIENT_EVIDENCE`（来源完整度未知、未复核、附件未检查），不是 `MATCH`；本记录没有升级任何 `UNKNOWN/PARTIAL/UNREVIEWED`。
- 扫描只证明有限规则的静态潜在行为，不证明运行期实际访问、收集或外传；JADX 不可用时保留字节码证据。
- 这是本机模拟器 + 受控服务 + 本机 Docker 的组合，不是物理设备、真实公网、外部模型或商店审核证据。
- 本记录不关闭 #130/#128，不改变父票分母；合并、部署和正式提交仍按独立授权边界处理。
