# #134：持久任务与故障恢复执行记录（2026-10-22 F 组补跑）

Refs #134、#128。本记录是 **F01–F04、F07 服务端故障链** 的本轮补跑结果；F05/F06/F08–F10
不在本票范围。真实 Android 客户端观察单独标注，未完成的边界如实保留。

**本轮 F01–F04 与 F07 非重启子步骤达到逐变体 PASSED；F07 宿主运行中重启子步骤 BLOCKED。
这不是 #128 父票或产品部署的最终放行。**

## 候选身份

| 项 | 值 |
| --- | --- |
| 源码 SHA | `42088231db0817e385b64f7a0809e31010b3e81e`（origin/main，#170 合并后） |
| 镜像（rev=4208823） | api `sha256:e815623b9086a3daeba8fc9886e64fc861639cd66a093fe0294990ba48f9264e`；web `sha256:ac734a62845946e1c975b85a28b27edcb6e443fb38e1f9cca0516b467352fbae`；runner `sha256:f95ac4b00c429fa7e0eb3a88577b4b58fa0ea7868941b4ac3d8a70accc47f2f7`；scanner `sha256:f31a68584c0a5ff969b87987c422e134373e46963fcf14741981a691c38c9290` |
| 实验室实例 UUID | `9b419ee8-c700-4ab8-bdec-958a48f0b894` |
| Compose 项目 | `pt81-0056bf64e802`（独立 PostgreSQL/Redis/outbox/dispatcher/worker/gateway/runner，独立 CA 与端口） |
| 迁移/协议 | `0080_05` / runtime contract version 1 |
| 主机 | WSL Ubuntu-24.04 + Docker 29.7.2；容器共用宿主内核，不是独立扫描主机或独立内核 VM |
| 客户端 | 最终候选 APK `955D484BA0A01BCF0472E7D97B24FE0D84698AF8C61B0EFE38B762CA7D3E6088`（源 head `2626152`，versionCode 1000/0.1.0，x86_64，信任范围 `localhost`）；服务端故障链不依赖该 APK，镜像构建于 4208823 |
| 设备 | MuMu VM index 5，`127.0.0.1:16544`，`adb reverse tcp:47759 tcp:47759`；不触碰其它 VM |

执行器：`deploy/acceptance/issue134/{f134_common,f01,f02,f03,f04,f07}.py`（本轮新增）。
观测器为内部 SQL/产品 intake 读取，**不是** Android/Web 客户端请求；客户端证据单独标注。
每变体只注入一个因素，`finally` 恢复 `laboratory.json` 与角色。

## F01 持久接收后停止 API，再按已交接命令启动

| 变体 | UTC 起止 | 注入与预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- |
| A | 05:28:18–05:28:45 | 确认 start 后 `compose stop api`；停 API 期间客户端读不到，durable 行保留；按交接命令 `start api` 后读取同一任务，事件前缀保留 | 停 API 时客户端 502；job/outbox 行仍在；重启后同一 job 可读；事件序列 `QUEUED→…` 前缀一致；最终 SUCCEEDED，报告 200 | **PASSED** |
| B | 05:28:55–05:29:06 | 完整发送 start 请求后**不读响应**（未确认接收）；同 `request_id` 重试必须返回同一 job | 重试/二次重放均 200；draft run 计 1、outbox 1、execution 1；最终 SUCCEEDED | **PASSED** |
| C | 05:56:43–05:57:06 | 维护窗口同时停 `api/dispatcher/worker`（lease=5s）后恢复 | 同一 job 可读并恢复 SUCCEEDED；事件前缀保留 | **PASSED** |

接收点证据：`runtime_inputs` 行、draft `current.json` 事件、`outbox_events` 行在 API 停机期间
持续存在（SQL 观察，不依赖 API 进程）。

## F02 待投递与已投递阶段分别停 broker / outbox publisher

| 变体 | UTC 起止 | 注入与预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- |
| A | 05:30:57–05:31:13 | PENDING 时停 dispatcher；恢复后同一任务可投递 | outbox PENDING attempts=0、队列 LLEN=0、job QUEUED；恢复后 DELIVERED attempts=1、SUCCEEDED | **PASSED** |
| B | 05:31:13–05:31:37 | PENDING 时停 Redis；有限重试且错误可见；恢复后无丢单 | attempts 增长至 3、`last_error_code=BROKER_UNAVAILABLE`、job QUEUED；恢复后 DELIVERED、同 job SUCCEEDED | **PASSED** |
| C | 05:31:44–05:32:10 | DELIVERED 且 RUNNING 时停 broker | worker 依靠 PostgreSQL lease 完成；outbox 保持 DELIVERED；报告可读 | **PASSED** |
| D | 05:32:10–05:32:18 | DELIVERED 后停 publisher | 任务不受影响；outbox 保持 DELIVERED | **PASSED** |

消息凭据不公开：证据只记录 event/job 别名、outbox 状态与 attempts；broker DSN/密码不写入。

## F03 worker / Runner 领取后中断，租约到期前后恢复

| 变体 | UTC 起止 | 注入与预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- |
| A | 05:40:12–05:40:44 | lease=5s；RUNNING 后 SIGKILL worker，5s 内重启 | 到期前 fence/attempt 不变（不抢占）；到期后 fence 1→2（重排）→3（新领取）、attempt=2、同 job SUCCEEDED | **PASSED** |
| B | 05:40:49–05:41:27 | 同上但停机 8s（超过 lease）后恢复 | dispatcher 在无 worker 时把过期 RUNNING 转为 RETRY；恢复后 attempt=2 完成；旧 owner 撤销 | **PASSED** |
| C | 05:44:00–05:44:32 | 受控慢扫描镜像，扫描容器出现后停 Runner | worker 观测 `RETRY`、fence 递增；Runner 重启 `_recover` 回收旧扫描容器与 operations；新 fence 完成 | **PASSED** |
| D | 05:49:35–05:50:29 | `docker pause` 旧 worker → 租约过期重排 → 第二 worker 完成 → unpause 旧 worker | `last_error_code=LEASE_EXPIRED`、audit `EXECUTION_RETRY`；fence 1→2→3；旧 worker 释放后报告字节不变、execution 单行、无第二终态 | **PASSED** |

F03-D 的额外探针「worker 日志出现独立 lease-lost 诊断码」**未命中**，原因见「可观测性发现」；
判定按 scenarios.md 原文（回收/重试、旧 fencing token 不得提交、无双重有效终态），未删除该探针。

## F04 重复交付与迟到旧结果

| 变体 | UTC 起止 | 注入与预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- |
| A | 05:52:55–05:53:09 | 首次投递后经产品 `CeleryPublisher` 再发 2 条同 event 消息 | 队列清空；attempt/fence 未再增长（仍 1）；报告字节不变；1 execution / 1 job / 1 SUCCEEDED 事件 | **PASSED** |
| B | 05:53:13–05:54:12 | 旧 worker 冻结过租约；新 worker SUCCEEDED 后释放旧 worker | 报告 SHA 不变；事件仍单终态；材料计数不异常增长；无第二 execution | **PASSED** |

## F07 扫描超时/崩溃、孤儿清理、角色重建

| 变体 | UTC 起止 | 注入与预期 | 实际 | 判定 |
| --- | --- | --- | --- | --- |
| A | 05:54:20–05:54:45 | 受控 `sleep 360` 扫描镜像 + runner timeout=6 | job FAILED、runner `TIMEOUT`、receipt `cleanup_verified/input_removed=true`、无残留容器；运行中 inspect 通过 | **PASSED** |
| B | 05:54:45–05:55:04 | 受控 `bytearray(2GiB)` 镜像 | job FAILED、runner `OOM`、receipt `exit_state.OOMKilled=true`、清理验证 | **PASSED** |
| C | 05:55:12–05:55:48 | 扫描中 `docker kill -s SIGKILL runner` | 扫描容器成为可证明孤儿；Runner 重启回收；同 job 新 fence SUCCEEDED；operations 残留为空 | **PASSED** |
| D | 05:56:20–05:56:36 | `compose up -d --no-deps --force-recreate worker runner dispatcher` | 三个容器 id 变化；全角色 inspect：非 root、只读根、cap_drop ALL、仅 Runner 挂 socket、无意外 host bind；新任务 SUCCEEDED | **PASSED** |
| E | 05:56:37（未执行） | 测试主机运行中重启 | **BLOCKED**：本机无独立内核可销毁 Linux VM；不用嵌套 daemon 或共享宿主内核冒充 | **BLOCKED** |

F07 运行中扫描容器 inspect（A/B/C）实际确认：`NetworkMode=none`、`ReadonlyRootfs=true`、
`CapDrop=["ALL"]`、`Privileged=false`、`User=65534:65534`、`PidsLimit=32`、`Memory=1GiB`、
唯一只读 mount `/input/sample.apk`、无 `/var/run/docker.sock`、env 无 SECRET/PASSWORD/TOKEN/KEY。
这是本任务的实际 Docker inspect，不是只看 YAML。

## 可观测性发现（不计入案例判定，报告 owner 决定归属）

`runtime_worker.py` 的 Celery 配置 `worker_task_log_format` / `worker_log_format` 不含
`%(message)s`，容器日志只出现空的 `[privacytrace runtime WARNING]`；固定诊断码
（`LEASE_LOST`、`EXECUTION_NOT_ACQUIRED` 等）在容器日志中不可读。本轮改用数据库行为证据
（execution/attempt/fence、outbox、报告字节、audit 事件）判定，未降低标准；该可观测性缺口
建议另行修复，不影响 F01–F04/F07 的原通过条件。

## 证据索引

私有证据在 `.scratch/issue134-evidence-20261022/`（不提交）：

| 文件 | SHA256 |
| --- | --- |
| F01-A.json | `563df4603718742cffc4520f2f3382f843997b92b864a1f94e3998d04370664f` |
| F01-B.json | `0e3f7f1dec3e6e610704ca96ef650c347199dc87a4465f28b65bce39707d6678` |
| F01-C.json | `8537769d3316b8d0c1aa8885124248f789375d4c81c5d44fe597cd250eed4126` |
| F02-A.json | `bf8f4369e7dfdbf01c91c9a5e876445c4886592fb7b28973639786c72f22df5b` |
| F02-B.json | `03a16cc1c222864867777ea02acb35b1f2271ebb47b2f29cfaad079ea0ee7ba0` |
| F02-C.json | `03a728c2e190806b740819dc2647b89119841c14d2b1e8e336ab95b6cf55613e` |
| F02-D.json | `922cbf1618bf0695465be0ff9424f77783ae6673428cb5e5c4c72b299b5f27d8` |
| F03-A.json | `ec9a2615245115294ea53ef15598ffe27a6616b3a42da003b1956e6dbc730b70` |
| F03-B.json | `c61fe48f57b4ac99ba4c08878236b0732dec8feb081cd92f499dadddaa705a9f` |
| F03-C.json | `12d949ab0df75681bb2450f85cbd3d1199a94ea3caaac9df04146f153ed4b8d0` |
| F03-D.json | `dc0d6049fb4858975e461e1b717897a6d2cee909a9a344428a1d84eb1e1c64aa` |
| F04-A.json | `491ead3e530dc6908a24889c739d9d241c012dc71367f221736ec4e62aab38d3` |
| F04-B.json | `4672b6f09c2ac9d953a285208cce4cc662ec51c04248387dcc20f70a8d1ad4ef` |
| F07-A.json | `78abc37af786034f42326dbb4b08ad12605cd7bcd5f97a681de536339a3392b6` |
| F07-B.json | `f4d3dc01555a238924b18b9c2d12315f4ccabab109d0a799a05ca2e070c0f136` |
| F07-C.json | `026ea7aec523d7795accec3df038a87251cdc9beacb62f3ebe5581124d5fe64a` |
| F07-D.json | `e2cea84d3c4c71894ba3b501e70dc8e7287cdd60b27b4081cd4de6af196c4a55` |
| F07-E.json | `f445f3dd063432c073405731703b6b3a32d4a7c81b13d93ed95dadeb1eb1d037` |

每份 JSON 含：变体目的、UTC 时间线（步骤名/预期/实际）、逐项 checks（含失败探针的
`probes`）、关键 artifacts（报告 SHA256、event 别名）、执行器标识。

### 证据可失败自检

私有目录的 `selfcheck.py` 对全部 18 份证据做正向校验（PASSED 必须有阻塞 checks 全真、
时间线不倒置、报告摘要为 SHA256 且删除前后一致、存在具体数值/摘要断言），再用**同一校验器**
跑三个负向控制：篡改报告摘要、倒置时间线、把某阻塞 check 置 false。三个负向控制全部被拒绝，
输出 `SELFCHECK PASSED (positive + negative controls)`。这证明本轮的判定不是恒真断言；
F03-D/F04-A/F04-B 的日志诊断探针保持 `observed=false` 并单列为非阻塞，也没有被删掉。

## Android 客户端观察（F01）

最终候选 APK `955d484b…`（源 head `2626152`，versionCode 1000/0.1.0）安装在分配设备
`127.0.0.1:16544`（`adb reverse tcp:47759`），按 Lead 的配方执行：

1. **产品动作**：客户端原生选择受控夹具、上传确认、assist 导入政策正文 → 开始分析。
   真实 job `868b4a64…` 创建并 **SUCCEEDED**；客户端页面随后显示终态并可打开报告
   （验证 #173 的顺序化轮询修复）。报告 SHA256 `385994d9…`、APK SHA256 `65047dbc…`，
   扫描来自受控 Runner 镜像 `sha256:f31a6858…` 且 `cleanup_verified/input_removed=true`。
2. **驱动注入**：仅本实验室项目 `compose stop api`；客户端「恢复当前实例材料」显示
   「正在处理当前请求」，API 日志记录 2 次 `GET route=UNMATCHED status=503`；
3. **驱动注入**：按交接命令 `compose start api` 并等 ready；客户端再次执行
   「恢复当前实例材料」，2 分钟内页面仍停留在「正在处理当前请求」；API 日志记录 3 次
   `POST /api/v1/web/drafts/{draft_id}/sources/{source_id}/extract status=409`；
4. **断言**：报告 SHA 在创建后 / 重启后 / 最终三个时点完全一致（`385994d9…`），
   DB job 计数保持 40 → 40（没有新任务）；但**页面未出现同一 job id**，客户端恢复读取
   同一任务这一外部观察**未完成**。
5. **清理**：产品 UI 删除远端材料未完成（`NOT_DELETED`）；执行器用实验室内部草稿删除
   路径清掉 1 个本轮草稿（执行器动作，非产品动作），回读 drafts=0、
   `intake_documents/runtime_inputs/runner_materials/upload_reservations=0`、
   jobs 行保留 40、原 job execution 因删除变为 REVOKED。

结论：
- F01 的**服务端持久接收、API 客户端读取同一任务、幂等重试**由 F01-A/B/C 覆盖并 PASSED；
- **Android 客户端恢复读取同一任务**记为 **NOT_RUN**，不并入 PASSED；
- 恢复入口在 `extract` 返回 409 后持续 busy、不退出，**不在本 lane 判产品缺陷**，留证交
  Lead/客户端 lane 复验（已知本实验室容器无外网，extract/政策读取路径受限）。
- 证据目录 `.scratch/issue134-evidence-20261022/F01-android/`：`F01-android-observation.json`
  （SHA256 `da832345…`）、`SHA256SUMS`、页面转储/截图、`role-logs.json`、DB 快照
  （pre/post/final-cleanup）；产品动作与驱动注入在 JSON 中分开列出。
- 证据完整性说明：原始页面转储/截图与 db 快照在 native 重试准备步骤中被执行器误删；
  `F01-android-observation.json` 依据首轮完整运行日志 `run.log` 重建（`reconstructed:true`，
  SHA256 `6189ca7e…`）。native 重试（force-stop App 后走原生恢复流程）未能执行：
  实验室 `owner.json` 的 runner 镜像 `sha256:f95ac4b0…` 已被本地镜像重建替换为
  `privacytrace-runner:final-2626152`（`35c31024…`），`compose start/up runner` 均报
  `No such image` 并使 Runner 退出（`RUNNER_UNAVAILABLE`）、api unhealthy、`package-set` 503，
  客户端显示 `SERVER_BUSY`。该阻塞属于**环境缺口**，不作为产品缺陷；需要恢复旧 runner 镜像
  或在稳定环境复验 native 路径。
### 环境修复后的 native 重试

- **环境修复**（均落在实验室状态，属环境缺口，不影响合同判定）：Lead 将已删除的 runner/scanner
  镜像按同一 4208823 源码树重建（runner `sha256:764351d4…`、scanner `sha256:e073a47b…`，
  owner.json `repairs[]` 有记录）；api/worker 仍从 `deployment.env` 读取旧 scanner id，执行器把
  `PT_RUNNER_IMAGE_ID` 更新为新值（原文件备份 `deployment.env.bak-f01`）并重建 api/worker；
  另清理了残留草稿配额（`POST /api/v1/web/drafts` 曾 429）。镜像内 healthcheck 仍显示 unhealthy
  是 `probe.py live` 的已知假失败，就绪以 `https://localhost:47759/api/v1/health` = 200 为准。
- **结果（09:17:58–09:27:31 UTC）**：客户端 UI 创建新任务 `cb768082…` 并 SUCCEEDED
  （报告 SHA256 `708046fc…`、APK `65047dbc…`、受控 Runner 镜像 `e073a47b…`）；
  `stop api` 后恢复入口 busy（API 日志 503）；`start api` + HTTPS health 200 后，
  `adb force-stop` 重启 App，再点「恢复当前实例材料」，**39.5 秒内落定（settled）但页面渲染
  `INVALID_SERVER_ORIGIN`**：客户端未持有 server origin，需要先按原生流程重新输入
  `https://localhost:47759` 再恢复。
- **断言**：报告 SHA 三时点一致（`708046fc…`）、DB `jobs_count` 41→41（无新任务）；
  但同一 job id 未在页面出现 → **NOT_RUN**。
- **产品观察（非阻断）**：force-stop 后恢复入口需要重新输入 origin，否则渲染
  `INVALID_SERVER_ORIGIN`；本轮未完成 origin 重输步骤，未据此判产品缺陷。
- **清理回读**：产品 UI 删除未完成（`NOT_DELETED`）；执行器内部删除 1 个草稿，回读 drafts=0、
  `intake_documents/runtime_inputs/runner_materials/upload_reservations=0`、jobs 行保留 41、
  原 job execution 因删除变为 `REVOKED`。


## 清理回读

- 每变体结束通过该 scope 自身 capability 删除草稿（HTTP 200），删除前报告 SHA 留存；
  删除后回读 `intake_documents`/`runtime_inputs`/`upload_reservations` 回落到基线。
- 所有变体后：`docker ps` 无本实验室扫描容器残留、`runner/operations` 为空、角色
  `api/worker/dispatcher/redis/gateway/runner` 恢复 running（api healthy）。
- 只操作 `pt81-0056bf64e802` 项目的容器；未执行 `docker system prune`、卷清理、其它项目
  down、共享 dockerd/WSL/宿主重启。测试镜像只新增本票 tag（scanner 派生镜像）。

## 逐例状态与未覆盖边界

| 案例 | 本轮状态 | 覆盖边界 |
| --- | --- | --- |
| F01 | **PASSED**（A/B/C；服务端与 API 客户端） | 未确认接收用真实 HTTP「完整发送后不读响应」注入；断流代理级响应丢弃未做（等价形态已覆盖）。**Android 客户端恢复读取同一任务 = NOT_RUN**（最终 APK 已能到 SUCCEEDED；恢复入口在 `extract` 409 后持续 busy，见上节） |
| F02 | **PASSED**（A–D） | 停 broker/publisher 只覆盖 Redis/outbox dispatcher 这一交付拓扑；未覆盖 broker 数据丢失（非停进程） |
| F03 | **PASSED**（A–D） | worker/runner 中断为 SIGKILL/优雅停止/pause；未覆盖网络分区与磁盘故障；日志诊断码因产品日志格式不可读（见上） |
| F04 | **PASSED**（A/B） | 重复交付经产品发布路径重发；未覆盖恶意构造消息（decode 拒绝已有回归） |
| F07 | A–D **PASSED**；E **BLOCKED** | 无独立内核可销毁 VM，宿主重启子步骤未执行；未覆盖物理扫描主机、cgroup v1 差异、长期运行磁盘耗尽 |
| Android/Web 外部对应 | **待补** | 本轮 Android 观察只用于 F01 客户端恢复同一任务；Web 报告对应未补造 |

旧记录与历史 SHA 不重写；本轮只追加本文件与私有证据。
