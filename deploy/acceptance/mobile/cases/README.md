# Issue 73 本机 Android 验收用例矩阵

本目录是 `client-case.cjs` 的用例清单。判定依据是仓库内的
`docs/acceptance/issue73/scenarios.md`（2026-10-21 版本）。本文只描述本机执行方式，
不修改验收文档、不改变案例分母。

## 0. 结论速览

- 文档实际用例：**38 个** = H01–H12（12）＋ N01–N12（12）＋ F01–F10（10）＋ R01–R04（4）。
- 本执行器可自动跑：**8 个**，全部是 H 组：
  H01、H02、H04、H05、H07、H08、H10、H11。
- 需人工执行：**26 个** = H03/H06/H09/H12（4）＋ N01–N12（12）＋ F01–F10（10）。
- R01–R04 不是人工逐条点，而是**另走既有入口**（仓库检查、Spec30、Browser Acceptance、
  部署专项），不在本执行器覆盖范围内。
- H01/H04/H07/H10 虽然可自动跑，但本分支基线上仍被 **BUG-01**（`/sources/discover` 503，
  #127 未合入）阻断，预期失败；#127 合入后应重跑，不能沿用旧结果。
- scenarios.md 实际有 **R04**；本表按文档实际编号纳入 R04。

脚本级判定（**不等于案例 PASSED**）不是只看进程退出码：

```text
exit code == 0
且 <evidencePrefix>-result.json 存在、可解析
且 job_state == SUCCEEDED
```

它只说明驱动流程走完；`result.json` 会记录 `policy_comparison`，为 `EMPTY` 时 H 案例
不得计 PASSED，仍须按 #128/#129/#130 核对非空、可复核政策对照与证据。`cleanup=true`
只表示请求删除远端材料；`deletion` 的
`DELETED / UNCONFIRMED / SKIPPED / NOT_REQUESTED` 单独记录，不直接等同于 job 失败，
但 `UNCONFIRMED` 可能仍占用配额（见第 4.2 节）。

## 1. 全量对照表

| 用例 | 标题（文档口径） | 本执行器可自动跑 | policyMode | 需要的特殊前置条件 |
| --- | --- | --- | --- | --- |
| H01 | 单 APK + 官方配置 I + 自动政策 | 是（当前受 BUG-01 阻断） | `auto` | 只装 fixture base；I 绑定 28443；BUG-01 修复后复跑 |
| H02 | 单 APK + 官方配置 I + 网页辅助补入 | 是 | `assist` | 只装 fixture base；I 绑定 28443；不依赖 discover |
| H03 | 单 APK + 官方配置 I + 手机直连模型补入 | 否（`model` 模式会被 assist 覆盖） | `model` | 手工核对模型来源、回填、审计；模型端点 + 一次性 Key |
| H04 | base + 全部已安装 splits + I + 自动政策 | 是（当前受 BUG-01 阻断） | `auto` | base 与 `fixture_feature` 均安装；I 绑定 28443；BUG-01 修复 |
| H05 | base + 全部已安装 splits + I + 网页辅助 | 是 | `assist` | base 与 `fixture_feature` 均安装；I 绑定 28443 |
| H06 | base + 全部已安装 splits + I + 模型补入 | 否（同 H03） | `model` | splits 安装集；手工模型路径 |
| H07 | 单 APK + 自托管配置 J + 自动政策 | 是（当前受 BUG-01 阻断） | `auto` | J 的 28443 映射；J 独立凭据/卷；只装 base；BUG-01 修复 |
| H08 | 单 APK + 自托管配置 J + 网页辅助 | 是 | `assist` | J 的 28443 映射；只装 base |
| H09 | 单 APK + 自托管配置 J + 模型补入 | 否（同 H03） | `model` | J 的 28443 映射；手工模型路径 |
| H10 | base + 全部已安装 splits + J + 自动政策 | 是（当前受 BUG-01 阻断） | `auto` | J 的 28443 映射；splits；BUG-01 修复 |
| H11 | base + 全部已安装 splits + J + 网页辅助 | 是 | `assist` | J 的 28443 映射；splits |
| H12 | base + 全部已安装 splits + J + 模型补入 | 否（同 H03） | `model` | J 的 28443 映射；splits；手工模型路径 |
| N01 | 选择前取消、确认时取消，随后重新选包 | 否 | — | 人工点取消，保留网络请求计数与 UI 状态 |
| N02 | 安装中变更版本/卸载/不可读后再确认或读取 | 否 | — | 在确认/读取窗口注入真实安装变更 |
| N03 | splits 缺必需 split、错版本/包名/重复名/坏摘要 | 否 | — | 逐变体安装负向包集合，记录接收与拒绝 |
| N04 | 包/集合超限、慢上传、中途断流 | 否 | — | 配额、网络整形、断流注入与清理观察 |
| N05 | 用 A 的访问材料读写 B 的状态/材料/报告/删除 | 否 | — | 双任务 A/B 作用域；直接 API 越权请求；前后状态对照 |
| N06 | I 切 J 复用 I 的材料，保留迟到响应 | 否 | — | 双实例切换 + 延迟/乱序响应注入 |
| N07 | 不受信 CA、错主机名、过期证书、TLS 降级、HTTP | 否 | — | 负向证书环境；系统信任对照构建；同一已配置信任环境 |
| N08 | 请求 API 管理探针、DB/broker/Runner/daemon 入口 | 否 | — | 从客户端网络探测；真实监听/隔离配置佐证 |
| N09 | 政策地址指向回环/私网/元数据、重定向、超大/慢响应 | 否 | `auto`（政策抓取） | 逐变体政策源或 APK 元数据；来源安全与资源限制观察 |
| N10 | 已有可用政策时注入抓取失败，再补畸形原句/冲突候选 | 否 | `auto`/`assist` | API 侧故障注入；候选区间/引用构造；审计保留 |
| N11 | 手机模型凭据、切换模型地址、观察客户端出站 | 否 | `model` | 抓包/端点观察；执行器无捕获能力；Key 只到预定端点 |
| N12 | 离线、后台/系统回收恢复、断网取消、显式重试 | 否 | `assist`/`auto` | 网络切换、后台/杀进程、任务 ID 对比、不重复提交 |
| F01 | 持久接收后停止 API，再按交接命令启动 | 否 | — | 服务编排与重启；接收点前后事件 |
| F02 | 待投递/已投递阶段停 broker 或 outbox publisher | 否 | — | broker/outbox 控制；消息与作业关联 |
| F03 | worker/Runner 领取后中断，租约到期前后恢复 | 否 | — | worker/租约/fencing token 注入；无双重有效终态 |
| F04 | 同一投递重复交付，旧尝试在新尝试后回报 | 否 | — | 消息重复/乱序注入；结果索引与事件一致 |
| F05 | 排队、上传/扫描中、提交前分别取消 | 否 | — | 精确定时取消；执行器只等到终态 |
| F06 | 与 F05 同时点删除，再送达迟到结果/旧访问 | 否 | — | 删除与迟到响应注入；各存储层核对 |
| F07 | 扫描容器超时/崩溃、测试主机重启、重建角色 | 否 | — | 容器/主机级故障注入；实际 inspect |
| F08 | 并发 1 下提交第二任务，耗尽准入/队列/磁盘预算 | 否 | — | 并发提交与资源限额；峰值内存/磁盘记录 |
| F09 | 备份专用 DB/材料，删除一个任务后恢复旧备份并重放删除 | 否 | — | DB/材料备份恢复；删除水位与旧访问材料 |
| F10 | 可回滚副本上升级/回滚、凭据轮换、磁盘满恢复 | 否 | — | 可回滚副本、凭据轮换、磁盘填充 |
| R01 | 仓库权威检查 `scripts/check.ps1` / `check.sh` | 否（另用既有入口） | — | 同 SHA；Docker 项记录实际执行与 skip |
| R02 | Spec30 Integration 的 six / twelve 两组 | 否（另用既有入口） | — | 原有受控源码、真实隔离扫描、HTTP/浏览器/回放 |
| R03 | Browser Acceptance；`acceptance:frontend` / `acceptance:live` | 否（另用既有入口） | — | 按 Mock、预置输入或真实 Docker 分别记录 |
| R04 | 部署专项 `deploy/check_acceptance.sh` | 否（另用既有入口） | — | 固定版本镜像/受限配置/合成 HTTPS；不能替代 H/F |

## 2. 可自动跑的 8 个用例

| 文件 | caseId | 输入 | 实例 | 说明 |
| --- | --- | --- | --- | --- |
| `case-H01.json` | `H01-local-I-single-auto` | 单 APK | I | 自动政策；已知 BUG-01，当前预期失败 |
| `case-H02.json` | `H02-local-I-single-assist` | 单 APK | I | 网页辅助；建议首个跑 |
| `case-H04.json` | `H04-local-I-splits-auto` | base+splits | I | 自动政策；已知 BUG-01，当前预期失败 |
| `case-H05.json` | `H05-local-I-splits-assist` | base+splits | I | 网页辅助；证明 splits 主链路 |
| `case-H07.json` | `H07-local-J-single-auto` | 单 APK | J | 自动政策；J 映射 + BUG-01 |
| `case-H08.json` | `H08-local-J-single-assist` | 单 APK | J | 网页辅助；J 映射 |
| `case-H10.json` | `H10-local-J-splits-auto` | base+splits | J | 自动政策；J 映射 + BUG-01 |
| `case-H11.json` | `H11-local-J-splits-assist` | base+splits | J | 网页辅助；J 映射 + splits |

所有文件都按执行器契约填全：`origin` 固定 `https://localhost:28443`、
`uploadAttempts: 1`、`cleanup: true`；`appLabel` 统一为
`Controlled split fixture`。`notes` 是本文约定的附加字段，执行器会忽略。

### 单 APK 与 splits 不能靠 appLabel 区分

`experiments/android-package-probe/fixture` 的 base manifest 标签就是
`Controlled split fixture`；`fixture-feature` 是 install-time split，没有独立
launcher 标签。因此单 APK 与 base+splits 在应用列表里**显示同名**：

- 单 APK 用例：运行前只安装 fixture base，`pm path` 只应返回 base。
- splits 用例：运行前安装 base + `fixture_feature`，`pm path` 应返回 2 个包。

`appLabel` 不能区分二者；写一个不存在的标签会让 `adb-ui.cjs` 的 `tapText` 超时。
这也是为什么 8 个文件都使用同一个 `appLabel`。

## 3. 必须人工的用例与一句话原因

### H 组模型路径（4 个）

- **H03 / H06 / H09 / H12**：执行器 `policyMode: "model"` 会先收集模型结果，
  随后调用 `importAssist(cdp, POLICY_JSON)` 覆盖 `#collector-result` 并补入 assist
  文本；真正被分析的是 assist 来源，模型来源/审计没有被证明。需要人工跑模型路径，
  或先修执行器（见第 6 节）。

### N 组负向（12 个）

- **N01**：执行器只会一路确认上传，没有“选择前取消 / 确认时取消”的控制点。
- **N02**：执行器不能在确认/读取窗口注入版本变更、卸载或不可读。
- **N03**：执行器一次只选一个安装集，不能逐变体安装缺包/错版本/坏摘要集合。
- **N04**：执行器不控制服务端配额、网络整形或断流。
- **N05**：执行器不持有 A 的访问材料去直接请求 B 的端点。
- **N06**：执行器一次只连一个 origin，不能切 I→J 并保留迟到响应。
- **N07**：执行器不切换 CA/主机名/证书有效期/协议，也不会发起 HTTP 目标。
- **N08**：执行器不探测管理探针、DB/broker/Runner/daemon 端口。
- **N09**：执行器不改变 APK 内政策地址，也不注入重定向/超大/慢响应。
- **N10**：执行器不注入抓取失败，也不能构造畸形原句区间/冲突候选。
- **N11**：执行器能配置模型，但不抓包、不观察 Key 目的地，且模型结果会被 assist 覆盖。
- **N12**：执行器不切离线、不把应用放后台/杀进程，也不在断网时取消或显式重试。

### F 组运行时/删除/运维（10 个）

- **F01**：需要停 API 再按交接命令启动，执行器没有服务控制。
- **F02**：需要停 broker/outbox publisher 并恢复，执行器没有 broker 控制。
- **F03**：需要中断 worker/Runner 并等租约到期，执行器没有租约/fencing 注入。
- **F04**：需要重复投递/乱序回报，执行器不控制消息层。
- **F05**：需要排队、上传/扫描中、提交前精确取消；执行器只等终态。
- **F06**：需要在删除同时点注入迟到结果/旧访问，执行器没有删除时序控制。
- **F07**：需要扫描容器崩溃/主机重启/角色重建，执行器没有容器/主机故障注入。
- **F08**：需要并发第二任务和资源预算耗尽，执行器串行且不控限额。
- **F09**：需要 DB/材料备份恢复和删除重放，执行器没有备份入口。
- **F10**：需要可回滚副本上升级/回滚/凭据轮换/磁盘满，执行器不控部署。

### R 组既有入口（4 个，不是“人工逐条点”）

- **R01**：`pwsh -NoProfile -File scripts/check.ps1` 或 `bash scripts/check.sh`。
- **R02**：Spec30 Integration 的 six / twelve 两组。
- **R03**：Browser Acceptance；`npm run acceptance:frontend` / `acceptance:live`。
- **R04**：`deploy/check_acceptance.sh`（本机 R1–R6 已通过 37/37，见执行记录）。

这些是独立入口，不属于 `client-case.cjs` 的覆盖范围；不能把它们的绿色结果替代
H01–H12 或 F01–F10。

## 4. 矩阵执行顺序建议

### 4.1 先证明核心链路，再跑自动政策和边界

推荐顺序（每一步都先确认安装集）：

1. **I + 单 APK**：`H02`（assist）。先证明“上传 → 受控政策补入 → 分析 → 报告”
   在没有 discover 的情况下能走通。
2. **I + splits**：`H05`（assist）。证明 base+全部已安装 splits 的集合上传与分析。
3. **I + 单 APK**：`H01`（auto）。复现/确认 BUG-01；如果失败，它不否定前两步。
4. **I + splits**：`H04`（auto）。同上。
5. **切 J**：重新建立 `adb reverse tcp:28443` 到 J 的宿主 HTTPS 端口，撤销 I 的映射，
   确认 J 的实例 ID/凭据/数据卷与 I 独立。
6. **J + 单 APK**：`H08`（assist）。
7. **J + splits**：`H11`（assist）。
8. **J + 单 APK**：`H07`（auto），**J + splits**：`H10`（auto）。

理由：assist 用例是当前唯一能绕开 BUG-01 证明完整主链路的组合；先跑它们，
即使后面 auto 失败，也能把“主链路是否可用”和“自动政策是否可用”分开。

### 4.2 每 IP 3 份草稿的硬限制

服务端 `MAX_DRAFTS_PER_IP = 3`（`apps/api/src/privacytrace/web_intake.py`）。
`cleanup: true` 会尝试走原生两步删除（输入 origin → 检查并继续 → 确认删除），
但仍要读回 `result.json` 的 `deletion`：

- `DELETED`：配额已释放，可以继续。
- `UNCONFIRMED` / `SKIPPED`：不要假设已释放；在客户端手工完成删除，或运行
  `lab-reset.sh` 重置业务态后再跑下一个用例。

执行器不会自动重试删除；连续跑第 4 个用例前先检查。

### 4.3 推荐命令

```powershell
cd <repo>/deploy/acceptance/mobile

# 0) 先看计划，不碰 adb / 不执行 node
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases H02,H05,H01 -OutDir .\evidence\matrix-20261021-I -DryRun

# 1) I 组核心链路（失败继续，便于一次看全）
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases H02,H05,H01 -OutDir .\evidence\matrix-20261021-I -ContinueOnError

# 2) 读回 deletion；若为 UNCONFIRMED，手工清理后跑 I 组剩余
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases H04 -OutDir .\evidence\matrix-20261021-I -ContinueOnError

# 3) 切到 J（示例：把 28443 反向映射指向 J 的宿主端口）
adb -s <serial> reverse --remove tcp:28443
adb -s <serial> reverse tcp:28443 tcp:<J_HOST_PORT>

# 4) J 组
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases H08,H11,H07 -OutDir .\evidence\matrix-20261021-J -ContinueOnError
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases H10 -OutDir .\evidence\matrix-20261021-J -ContinueOnError
```

> `adb reverse` 的具体宿主端口以本机 I/J 实际部署为准；不要照抄占位符。
> 如果实验室用其他转发方式（命名空间转发 + 宿主回环转发），按同样原则切换。

## 5. `run-matrix.ps1` 用法

### 5.1 参数

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `-Cases` | 否 | 字符串数组或通配符；默认 `*`（全部 `case-*.json`）。支持 `H01`、`H02,H05,H01`、`H0*`、`case-*.json`、完整路径。显式列出的顺序会保留；通配符匹配结果按 H/N/F/R 排序。 |
| `-OutDir` | 是 | 证据目录。脚本会设置为 `PT_EVIDENCE_DIR`，执行器的 `-webview.txt`、`-device.png`、`-result.json` 都落在这里。 |
| `-ContinueOnError` | 否 | 某个用例失败后继续；不加则首个失败即停并汇总。 |
| `-DryRun` | 否 | 只解析并打印计划，不连接 adb、不检查健康、不执行 node。 |
| `-CaCert` | 否 | 健康检查 CA；默认 `PT_CA_CERT` → `<本目录>\tls\ca.crt`。 |
| `-Adb` | 否 | adb 路径；默认 `PT_ADB` → PATH。 |
| `-AdbSerial` | 否 | adb 序列号；默认 `PT_ADB_SERIAL`；缺失即报错，不猜测设备。 |

### 5.2 行为

1. 解析 `-Cases`，读取每个 JSON 的 `caseId`、`origin`、`policyMode`、`evidencePrefix`。
2. 预检：
   - `client-case.cjs` 存在、`node` 可用；
   - adb 设备 `get-state` 为 `device`；
   - `org.privacytrace.mobile` 已安装（`org.privacytrace.probe.fixture` 缺失只警告）；
   - `adb reverse --list` 有 `tcp:28443`（没有只警告）；
   - 对每个唯一 origin 做 TCP 探测 + `curl.exe --noproxy * --cacert ... /api/v1/health` 期望 200；
   - 计划里同时出现 single/splits 时警告安装集切换。
3. 逐例串行执行 `node <env>\client-case.cjs <case 文件>`，cwd 设为 `<env>`，
   `PT_EVIDENCE_DIR=<OutDir>`，`PT_ADB`/`PT_ADB_SERIAL` 传给执行器。
4. 每例写日志 `<OutDir>\logs\<caseId>.log`（UTF-8 无 BOM），并重写
   `<OutDir>\matrix-results.csv`（UTF-8 带 BOM，Excel 可直接打开）。
5. 失败判定：退出码非 0，或结果 JSON 缺失/解析失败，或 `job_state != SUCCEEDED`。
   `deletion != DELETED` 只警告，不单独判失败；但它可能仍占用配额。`policy_comparison`
   为 `EMPTY`/`UNKNOWN` 时只警告，但该用例不能作为案例 PASSED。此判定只到脚本级。
6. 退出码：`0` 全部脚本级完成；`1` 有失败/提前停止；`2` 用例解析或预检失败。

### 5.3 CSV 列

| 列 | 内容 |
| --- | --- |
| 时间 | 该用例开始时间（本地 `yyyy-MM-dd HH:mm:ss`） |
| 用例 | JSON 内的 `caseId` |
| 退出码 | `node client-case.cjs` 的退出码 |
| 结果 JSON 路径 | 存在的 `<OutDir>\<evidencePrefix>-result.json`；缺失时留空 |
| job_state | `SUCCEEDED` / `FAILED` / `CANCELLED`；未写出结果时留空 |
| 政策对照 | `PRESENT` / `EMPTY` / `UNKNOWN`（来自 `result.json` 的 `policy_comparison`）；未写出结果时留空 |
| deletion | `DELETED` / `UNCONFIRMED` / `SKIPPED` / `NOT_REQUESTED`；未写出结果时留空 |
| 错误首行 | 失败时优先取含 `CASE_FAILED` 的第一行，否则取首个非空行；成功时留空 |

### 5.4 常用示例

```powershell
# 全部可自动用例（会混跑 I/J，默认顺序 H01→H02→H04→H05→H07→H08→H10→H11）
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -OutDir .\evidence\matrix-all -ContinueOnError

# 只跑 I 组
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases H01,H02,H04,H05 -OutDir .\evidence\matrix-I -ContinueOnError

# 只跑 J 组
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases H07,H08,H10,H11 -OutDir .\evidence\matrix-J -ContinueOnError

# 通配符
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases 'case-H0*.json' -OutDir .\evidence\matrix-H0

# 精确文件路径
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-matrix.ps1 `
  -Cases .\cases\case-H02.json -OutDir .\evidence\matrix-H02
```

> 默认 `-Cases *` 会把 I/J 用例排在一起。除非已经在两次运行之间切换了 28443 的
> 反向映射，否则不要直接跑默认全量；先按第 4 节分组。

## 6. 已知缺口、冲突与文档缺口

1. **`model` 模式不证明模型政策路径（执行器缺口）**
   `client-case.cjs` 在 `runModelCollect()` 之后调用
   `importAssist(cdp, POLICY_JSON)`，把 `#collector-result` 覆盖为固定 assist JSON，
   再按 assist 来源补入。模型端点/收集 UI 被走到了，但真正分析的是 assist 文本，
   模型来源、审计和“手机直连模型 API 补入”都没有被证明。因此本目录没有
   H03/H06/H09/H12 的 JSON；需要人工跑或先修执行器。`model` 模式还要求显式设置
   `PT_MODEL_ENDPOINT` / `PT_MODEL_KEY`；即使设置，结果也会被 assist 覆盖。
2. **`cleanup` 的删除结果仍可能是 `UNCONFIRMED`**
   `removeDraft()` 会驱动 WebView 按钮后的原生两步对话框（输入 origin →
   “检查并继续”→“确认删除”），但 UI、网络或服务端超时都可能让
   `deletion` 停在 `UNCONFIRMED`/`SKIPPED`。结合 `MAX_DRAFTS_PER_IP = 3`，
   连续跑第 4 个用例前要读回 `deletion`；未确认时手工删除或重置实例（第 4.2 节）。
3. **I/J 无法写进 case JSON**
   `origin` 固定 `https://localhost:28443`，但 H07–H12 需要实例 J。JSON 只能表达
   “模拟器访问 localhost:28443”，不能表达“这个 28443 背后是 I 还是 J”。必须在
   组与组之间重新建立 `adb reverse`/宿主转发；`run-matrix.ps1` 不会自动切换。
4. **单 APK / splits 没有不同 appLabel**
   两者都显示 `Controlled split fixture`；只能靠安装状态（`pm path` 返回 1 或 2 个包）
   区分。任务描述里“用 appLabel 区分单 APK / splits”在本 fixture 上不可行。
5. **R04 容易漏**
   scenarios.md 实际有 R04（部署专项）；早期任务描述只写到 R01–R03。本表纳入 R04，
   总数因此是 38 而不是 37。
6. **BUG-01 仍然阻断 auto**
   H01/H04/H07/H10 的自动政策组合在交付拓扑下 `POST /sources/discover` 返回 503
   `ISOLATED_INSPECTION_UNAVAILABLE`；执行器会在候选页之前超时退出（通常 exit 1，
   不写 `-result.json`），CSV 的 `job_state`/`deletion` 会留空。这是已知产品缺陷，
   不是用例脚本错误。
7. **`uploadAttempts: 1` 与实验室重启**
   执行记录写明 WSL 发行版会在窗口期被外部重启。`uploadAttempts: 1` 表示不重试，
   瞬时 TLS/连接失败会直接记为该用例失败；应在稳定窗口重跑，而不是静默改成 5。
8. **健康检查路径/CA 是本地约定**
   `run-matrix.ps1` 使用 `/api/v1/health` 和 `tls/ca.crt`，依据是本机
   `health.sh` 与 `tls/` 目录；验收文档没有把这两个值写成正式契约。换实例/换 CA
   时用 `-CaCert` 覆盖，或先确认健康路径。
9. **`cleanup` 与 N/F 用例冲突**
   N/F 组需要保留远端材料、任务、删除水位和恢复状态来观察；这些用例不能套用
   `cleanup: true`。本目录只给 H 组生成 JSON；N/F 人工执行时按场景表决定清理时机。
10. **早期临时样例不是完整契约**
    早期临时目录里的样例缺少 `uploadAttempts`/`cleanup`。本目录的 8 个文件才是矩阵
    使用的完整字段版本；不要混用。
11. **手工候选不等于非空对照**
    8 个 JSON 均未配置 `addCandidate`。受控夹具的静态数据类型为 0，即使手工补入候选，
    报告也不会形成对照行（H01 历史记录已证实）；`policy_comparison` 会保持 `EMPTY`。
    `addCandidate` 只在夹具含对应静态数据类型时才有意义；不能据此判定 H 通过。

## 7. 证据与安全

- `-OutDir` 建议放在 Git 忽略目录（例如仓库根的 `tmp/`）；不要提交
  原始截图、请求、访问材料、APK 或含凭证的日志。
- 公开证据必须逐文件脱敏；本目录的 `notes` 只写别名和前置条件，不含秘密。
- 每个用例至少保留：`matrix-results.csv`、`logs/<caseId>.log`、
  `<evidencePrefix>-candidates.txt`、`<evidencePrefix>-webview.txt`、
  `<evidencePrefix>-webview.png`、`<evidencePrefix>-device.png`、
  `<evidencePrefix>-result.json`（若执行到写结果）。
- 执行后逐个读回 `result.json` 的 `job_state`/`policy_comparison`/`deletion`，并核对证据文件 SHA256；
  不能只看 CSV 的“脚本级完成”。
