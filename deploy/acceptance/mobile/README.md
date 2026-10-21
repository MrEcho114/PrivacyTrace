# 移动端本机验收执行器

驱动一台已安装 PrivacyTrace Android 客户端的模拟器，跑「选择应用 → 上传 → 政策补入 → 分析 → 报告 → 删除」的一条端到端用例，并把脱敏证据落盘。它是 Issue 73 本机验收拓扑对应的执行入口；场景定义见 `docs/acceptance/issue73/scenarios.md`。

## 不覆盖什么

- 覆盖可自动化的 **H 组**（单 APK / splits × 自动政策 / 网页辅助补入 / 手机模型）。模型路径（H03/H06/H09/H12）只有在配置一次性 HTTPS 接收器并核对 `modelExpect` 与报告原句后才算完成；接收器日志只证明协议/Key 去向，不证明外部模型质量。
- **N/F 组大部分需要人工注入**（取消时点、安装态变更、跨实例材料、证书负向、离线恢复、停 API/broker、租约中断、重复投递、备份恢复、磁盘满），不在本执行器范围内；N11 只覆盖模型接收端观察和单次 Key 去向，地址切换/分析服务负对照仍需额外步骤。
- 不替代 `deploy/check_acceptance.sh`（R1–R6 部署专项）；两者互补。

## 前置

1. Node 24（`cdp.cjs` 依赖全局 `fetch`/`WebSocket`；仓库权威检查固定 24.17.0）。
2. 实验室实例已就绪：`https://localhost:<port>/api/v1/health` 返回 200，CA 在本机可信（用 `--cacert` 或系统信任区）。
3. 模拟器在线，客户端已安装：`adb -s <serial> shell pm list packages | grep privacytrace`。
4. `adb reverse tcp:<port> tcp:<port>` 已建立，且**同一个 port 指向当前要测的实例**（换实例就是改这条 reverse）。
5. 实例草稿配额未被占满：`MAX_DRAFTS_PER_IP = 3`，第 4 个新草稿会 409 `quota reached`。用例之间用 `cleanup: true` 删除远端材料，或重置实例业务态。

环境变量（按需设置；`PT_ADB_SERIAL` 必填，缺省会直接报错而不是猜设备）：

| 变量 | 用途 |
| --- | --- |
| `PT_ADB` | adb 可执行文件；缺省用 PATH 里的 `adb` |
| `PT_ADB_SERIAL` | adb 序列号；**必须提供**，否则执行器直接报错，避免连错设备 |
| `PT_EVIDENCE_DIR` | 证据输出目录；缺省 `<本目录>/evidence`（已加入 `.gitignore`） |
| `PT_CA_CERT` | `run-matrix.ps1` 健康检查 CA；缺省 `<本目录>/tls/ca.crt` |
| `PT_MODEL_ENDPOINT` / `PT_MODEL_KEY` | 仅 `policyMode: "model"` 用；两者都必填；Key 只写入本机原生配置 |

模型接收器由 `model-receiver.cjs` 另起进程，环境变量为
`PT_MODEL_PORT`、`PT_MODEL_KEY`、`PT_MODEL_CERT`、`PT_MODEL_KEY_FILE`、
`PT_MODEL_RESPONSE_FILE`、`PT_MODEL_LOG`；证书 SAN 必须覆盖客户端访问的
`localhost`，并由客户端信任的 CA 签发。手机侧用 `adb reverse tcp:19543
tcp:<接收器宿主端口>` 把设备 `localhost:19543` 接到接收器。

`lab-reset.sh` 另有自己的环境变量：`PT_LAB_STATE`（必填，实验室状态目录）、
`PT_COMPOSE_DIR`（缺省为仓库的 `deploy/`）、`PT_PROJECT`、`PT_CA`、`PT_HEALTH_PORT`。

## 跑一条

先按上表设置 `PT_ADB_SERIAL`（缺省会直接报错）：

```bash
PT_ADB_SERIAL=<serial> node client-case.cjs cases/case-H02.json
```

`client-case.cjs` 接受 JSON 文件路径或 JSON 字符串。它自己会：清客户端状态、启动、发现 WebView 调试 socket、`adb forward tcp:9222`，然后通过 CDP 点 WebView、通过 `uiautomator dump` 点原生对话框。

## 跑一组

```powershell
powershell -NoProfile -File .\run-matrix.ps1 -Cases H02,H05 -OutDir .\evidence\matrix-I -ContinueOnError
```

- `-Cases` 支持 `H01`、`H02,H05`、`H0*`、`case-*.json` 或完整路径；显式顺序保留。
- 预检 adb 在线、客户端已安装、实例健康；任一用例失败即停（加 `-ContinueOnError` 继续）。
- 每例写 `logs/<caseId>.log`，并重写 `outDir/matrix-results.csv`。
- CSV 的“脚本级完成”只表示驱动流程退出 0 且 `job_state=SUCCEEDED`；`policy_comparison=EMPTY` 或 UNKNOWN 时 H 案例不能算 PASSED，须核对报告中的非空政策对照与证据。

## case 契约

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `caseId` | 是 | 用例标识，进 CSV |
| `origin` | 是 | 形如 `https://localhost:28443` |
| `policyMode` | 是 | `auto` / `assist` / `model` |
| `evidencePrefix` | 否 | 证据文件前缀，缺省用 `caseId` |
| `uploadAttempts` | 否 | 上传阶段重试次数；环境稳定时用 `1`，让失败立刻暴露 |
| `cleanup` | 否 | 结束时走原生两步确认删除远端材料，释放配额 |
| `appLabel` | 否 | 应用选择器；同一 fixture 的 base 与 splits 标签相同，靠安装态区分 |
| `addCandidate` | 否 | `{sourceTitle, quote, dataType}`：服务端未配置模型时，手工补一条候选，让报告有政策对照项；保存失败会令本用例失败 |
| `modelExpect` | `model` 必填 | `{sourceId, sourceTitle, quote, dataType}`：断言模型结果中的 source id 进入候选页、原句进入报告；静态 assist 来源出现即失败 |
| `packageName` | 否 | 受控包名；用例开始前把 `pm path`/`dumpsys package` 的安装集快照写入 `<prefix>-package-set.txt`，用于区分单包与完整 splits |

## 已知的“假失败”

这些不是产品缺陷，执行器已内置处理，改动时别退回去：

- `uiautomator dump` 在部分镜像上写完文件就段错误退出；崩溃时会留下**上一次**的 XML。dump 前必须删文件，且只接受含 `<hierarchy>` 的新文件（`adb-ui.cjs` 的 `dump()`）。
- IME 会在字段刚出现时吞掉开头几次 `input text`；普通字段输入后要回读 EditText 确认。模型 Key 字段是密码框，uiautomator 读不到值，`clearAndTypeAt(..., {secret:true})` 只验证请求端收到的 Key，不伪造回读。
- 原生对话框的标题里含按钮文字（如「确认上传所选应用」vs 按钮「确认上传」），匹配时要优先取可点击节点。
- 「删除远端材料」是**两步原生对话框**（输入 origin → 检查并继续 → 确认删除）；只点 WebView 按钮删不掉。
- 候选保存后页面会重渲染，此时点「保存候选并开始分析」可能落在已替换的节点上；要重试到进度页出现。
- 采集器 JSON 必须带 `state`（`PROVIDED`/`RETRIEVED`/…），少了会 409 映射成 `SERVER_REJECTED`。

## 文件

| 文件 | 作用 |
| --- | --- |
| `client-case.cjs` | 单用例驱动：上传、政策补入（auto/assist/model）、分析、报告、删除 |
| `client-case.test.cjs` | 模型模式回归：模型结果只导入一次，静态 assist 不得覆盖 |
| `model-receiver.cjs` | 受控 HTTPS Chat Completions 接收器：一次性 Key、固定响应、Key 指纹/请求体日志 |
| `adb-ui.cjs` | 原生层：快速 dump、点击、输入回读、密码框、截图、反向转发 |
| `cdp.cjs` | WebView 调试协议客户端（无第三方依赖） |
| `run-matrix.ps1` | 串行矩阵 + CSV 汇总（Windows PowerShell 5.1 可用） |
| `cases/*.json` | H 组用例定义与判定说明 |
| `lab-reset.sh` | 重置实例业务态（保留 PKI/证书），用于清配额与草稿残留 |
