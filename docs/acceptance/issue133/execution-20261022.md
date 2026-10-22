# #133：N12 / F05 / F06 canonical 本机执行记录（2026-10-22）

Refs #133、#128。本记录只覆盖 E 票：N12、F05、F06。执行使用 Lead 指定的
localhost 实验室与专用 MuMu 设备；未修改服务端共同终态、协议、共享前端或
父票矩阵。原始证据在私有目录 `.scratch/issue133-evidence-20261022/`，不提交
真实访问材料、完整报告或私有绝对路径。

**组合结论（2026-10-22 更新）：** pre-fix 4208823 保留为历史/缺陷证据；最终验收在
**final 2626152 客户端 APK（955D484B）** 上补跑最小手机侧矩阵，**4/4 PASSED
（187 项断言）**。N12 的 `BUSY_OR_INACTIVE` 在 final APK 上**不再出现**；F05 扫描中
取消和 F06 提交前删除+迟到结果均在 final APK 上通过。服务端/DB/材料层在
F05/F06 补跑时使用同源码树的 4208823 镜像（PR #173 只改 `flow.ts`），组合差异
已在下表逐项注明。pre-fix 行仍为 OBSERVED / HISTORICAL，不作为 final PASSED。

## 组合矩阵

| 组合 | 客户端源码 / APK | 服务端镜像 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| pre-fix | `4208823` / `0be49358…` | `4208823` | 历史证据与 PR #173 缺陷复现 | OBSERVED / HISTORICAL |
| final | `2626152` / `955D484B` | 4208823 / 2626152（服务端代码等价；N12 在 final 服务端上跑，F05/F06 在 4208823 上跑） | 最终验收手机侧与材料层 | 4/4 PASSED |

服务端/DB/材料层代码在 2626152 与 4208823 之间没有变更（PR #173 只改
`apps/web/src/mobile/flow.ts`）；因此 pre-fix 的持久状态、删除、旧访问拒绝
证据可在 final 表中引用，但必须注明“产品树相同、手机侧未复跑”的边界。
**F05/F06 其余变体在 pre-fix 组合完成，产品树相同（#173 只改 flow.ts），
因此结论适用。**

## 候选身份与环境

| 项 | 值 |
| --- | --- |
| 源码 SHA | `42088231db0817e385b64f7a0809e31010b3e81e` |
| API 镜像 | `sha256:e815623b9086a3daeba8fc9886e64fc861639cd66a093fe0294990ba48f9264e` |
| Web 镜像 | `sha256:ac734a62845946e1c975b85a28b27edcb6e443fb38e1f9cca0516b467352fbae` |
| Runner 镜像 | `sha256:f95ac4b00c429fa7e0eb3a88577b4b58fa0ea7868941b4ac3d8a70accc47f2f7` |
| Scanner 镜像 | `sha256:f31a68584c0a5ff969b87987c422e134373e46963fcf14741981a691c38c9290` |
| 实验室 | `pt81-0c0f8a8a048d`，实例 `e5652925-aa8e-4c34-acec-15311e21d363` |
| 入口 | `https://localhost:55483`（客户端 origin；仅 `localhost` 被 APK 信任） |
| 迁移版本 | `0080_05`，文件 SHA256 `3fdade25d8ba86706bd3ba784e2631b8a90bff0e457745c3f63676df9f5d11e3` |
| Runner 协议 | `apps/api/src/privacytrace/runner_protocol.py` SHA256 `9f36fe16102a8748ca9e3c3e48367061ef9c0020aa60ce81dbb102150e59e589` |
| 规则 | taxonomy `e63297c70dcb3ec67b797e315fdfe469d617296b7bd51084a5ed8e950f513951`；SDK signatures `f4987d328ac7b6697cd3fd92c4f6327cfdeea84566ad6e9934c8aa5bc14150e4` |
| 运行时契约 | `deploy/runtime-contract.json` SHA256 `e2d5f757229d4b250bda319b2c713f1e32aa3c34431722b877d7169c9f6395f6` |
| 客户端 APK | `0be49358bc20128f66eb1a5a386d42dd130eec8846f8c363aa0fc7880a7b8c17`（157,543,412 B，versionCode 1000，x86_64，debug） |
| 受控夹具 APK | `65047dbcf0b3ef4876d422b68e5bde777a13dd84f59bd946c66c1279921ab981`（`org.privacytrace.probe.fixture`） |
| 设备 | MuMu Player 12 VM index 4，显式 adb serial `127.0.0.1:16512`，隔离 adb server 端口 5038，CDP `18778` |
| 客户端流程源码 | `apps/web/src/mobile/flow.ts` SHA256 `70dabdaedffed4393cc66445282559d953a918921bedea1de2ca0a40ddd3c8bf` |

入口是真实 Android 客户端 → 原生包选择/确认 → 验证证书的 HTTPS →
PostgreSQL/outbox/Redis/Celery → Runner → `network=none`、read-only、非特权、
cap-drop ALL 的真实扫描容器；不是 bridge harness、Mock 或预置报告。客户端
包只信任 `localhost` 的 #73 测试 CA，TLS 验证未关闭。

## 执行入口

- 设备动作：`deploy/acceptance/issue133/client.cjs`（配置化 origin/serial/CDP 端口；
  新增 reset、background-wait、force-stop/reclaim、restore、offline 网络阻断、
  delete、snapshot、identity 等动作）。
- 服务端观测/控制：`deploy/acceptance/issue133/control.py` + `state_query.py` +
  `observe.py`，通过 `pt133e-controller` 读取 PostgreSQL、outbox、deletion journal、
  runner ledger、材料目录和 Caddy 访问日志；原始 capability 只留在实验室私有目录。
- 逐变体驱动：`deploy/acceptance/issue133/driver.cjs`，矩阵与判定规则见
  `matrix.json`；每个变体写 `result.json`、UTC timeline、命令、截图、
  DB/API 观测和 SHA256SUMS。
- 最终回读：`finalize.cjs` 校验全部证据哈希、tombstone、扫描器、runner 操作和
  设备侧残留规则。

## pre-fix 4208823 历史：N12

### N12-restore（后台 + force-stop 恢复）

- 时间：2026-10-22T06:14:28Z–06:18:19Z；41 项断言通过。
- 变体：HOME 后台 40 s；force-stop 进程死亡；`恢复当前实例材料` 回读；无重复 start。
- 关键观察：同一 job alias `26f42b88b4b8` 在后台和冷启动后都保持 `QUEUED`；
  `POST .../start` 计数始终为 1（后台前后、恢复前后均 1）；DB 中始终 1 个 job、
  1 条 runtime input、1 条 outbox；取消后 execution `REVOKED`、fence `0→1`、
  无报告；worker 恢复后旧投递未复活任务；删除后墓碑持久。
- `BUSY_OR_INACTIVE`：06:15:53Z 首次观察到，服务端 job 当时仍是 `QUEUED`；
  force-stop→restore 后同一 job 可正常读取且错误消失，分类为**执行器/原生读取
  竞态**（单设备/单 APK，非自然回收证明）。该观察单列，不作为整例失败。
- 证据：`N12-restore/`，result SHA256
  `44e9b6b445c8f2b55cb10d61f381ed6a942a61329aa3818df735937a0528069e`。

### N12-offline-retry（离线读取/取消 + 显式重试 + 旧报告）

- 时间：2026-10-22T07:06:32Z–07:10:21Z；74 项断言通过。
- 基线：job alias `78aace4d54a8`，独立报告内容哈希
  `97a1323ddf8ee4da4dff6f305fd7211fa8777e17cad6b30d52891b56ef3eaa1d`；
  经 force-stop→restore 从真实客户端读到报告。
- 离线注入：设备侧 `OUTPUT` REJECT 到 `127.0.0.1:55483` / `[::1]:55483`
  （MuMu root console）。真实 UI 显示 `SERVER_UNREACHABLE`；刷新后服务端 job
  `5ef89fdd4424` 仍为 `QUEUED`、execution `READY`；离线取消也显示错误，服务端
  状态不变。
- 在线取消：`CANCELLED`、execution `REVOKED`、fence `0→1`、无报告。
- 离线重试：创建 0 个新 job；在线显式重试创建 job `98186b8782c4`，
  `retry_of=5ef89fdd4424`；start 请求计数 1→1，retry 请求 1；旧 job 保持
  `CANCELLED`，基线报告仍为 `SUCCEEDED` 且内容哈希不变。
- 证据：`N12-offline-retry/`，result SHA256
  `21781fe49a3b1962e3684183a22e9c0b48b7ffa9d097932c5cc8fd295a02769a`。

## pre-fix 4208823 历史：F05

以下三行为 pre-fix 历史观察，服务端状态/停机和旧结果拒绝证据有效，但不作为
final 组合的 PASSED。

| 变体 | UTC 时间线（关键点） | 预期 / 实际 | 证据 |
| --- | --- | --- | --- |
| 排队中取消 | 06:00:37 开始；06:01:30 job `c6d31516893e` `QUEUED`；06:01:40 取消；06:02:33 删除确认 | `QUEUED→CANCELLED`、`REVOKED`、fence `0→1`、无报告/扫描器；worker 恢复后旧投递不复活；start=1、cancel=1 | `F05-queued/` result `7e2e22aa4e6363f0fd9cef36972736549d0f8a1df91fcf00190deebd20af3c63` |
| 扫描中取消 | 07:12:30 开始；07:13:22 job `cf18b0f9bb4e`；07:13:24 真扫描容器 RUNNING（network=none/read-only/cap-drop ALL）；07:13:31 取消；07:14:40 删除 | 容器 RUNNING 时取消；`CANCELLED`、`REVOKED`、fence `1→2`、扫描器回收、无报告；迟到扫描输出不能提交 | `F05-scanning/` result `c344307cfa8728e69e230adf8117b0537d2af2c4b613ae24147cb3b196f41e5f` |
| 提交前取消 | 07:18:43 开始；07:19:34 job `6f7c29ae01ac`；07:19:37 扫描；07:20:03 取消；07:20:04 恢复消费者 | worker 暂停后取得真实 Runner result+receipt（输出哈希 `a4dee99ec6579cb2f9458e782a324da499058cd83a1bfd70bbcc7...`）；取消后 unpause，旧结果被 lease/fence 拒绝，job 保持 `CANCELLED`、无报告 | `F05-precommit/` result `e3e26cbf4a60ffef1736c1a7063254a9fee742fbd3fae15adbde3c7b335031d2` |

F05 的删除动作只用于释放本票合成材料，不改变取消语义；“取消确认点”由 client
snapshot（`分析已取消`）+ DB 状态（CANCELLED/REVOKED/fence）对应记录。

## pre-fix 4208823 历史：F06

以下三行为 pre-fix 历史观察；删除/材料/旧访问证据与 final 的 server/DB 代码
相同，但 final 手机侧仍需复跑至少 F06-precommit。

| 变体 | UTC 时间线（关键点） | 预期 / 实际 | 证据 |
| --- | --- | --- | --- |
| 排队中删除 | 07:34:34 开始；07:35:23 job `61342cf97870` `QUEUED`；07:35:52 原生删除确认；07:36:12 墓碑回读 | draft/job tombstone、token 撤销、documents/runtime/runner materials 归零、draft 目录消失；worker 恢复消费旧 outbox 不重建；旧 9 条访问路由全 404；10 s 后仍墓碑 | `F06-queued/` result `4a6cfda1924e99081727b56ac7a016f7861d001a87509bf40e0c20a72e0f422b` |
| 扫描中删除 | 07:36:52 开始；07:37:48 job `1e1d4eda1fd4`；07:37:50 真扫描 RUNNING；07:38:16 删除；07:38:38 墓碑 | 删除时扫描器仍运行；删除后扫描器回收、runner idle；超过原扫描窗口 30 s 再读仍 tombstone、无报告/索引重建；旧 9 条访问路由全 404 | `F06-scanning/` result `96b20776bb9e046b22827ee9d72e3b783c4c66267150a1e033151ea37041e84e` |
| 提交前删除 + 迟到结果 | 07:39:29 开始；07:40:24 job `b80328c6ead2`；07:40:27 扫描；07:41:14 删除；07:41:37 迟到结果消费 | 真实 result+receipt（输出哈希 `6227e694133f3ad06f5b9b9e4995cedf8746bc7bce51a11bc78c5d9d72b9cc1b`）在删除后送达；迟到提交被拒绝；墓碑、无报告；documents/runtime inputs/runner materials 均为 0；旧 9 条访问路由全 404 | `F06-precommit/` result `d6452e48dbaa97d595535e56401aafb5a312c0fcaf062555a0a2d531ac6a15e4` |

F06 三个变体的删除都通过客户端原生两步确认（输入 origin → 检查并继续 → 确认
删除）；旧访问材料来自本票合成 capability 的私有捕获，公开记录只保留别名/哈希。
删除后的存储层读回覆盖：analysis scope tombstone、job record 无 bundle、
token digest 为空、deletion_intents/journal 保留、intake documents/runtime inputs/
runner materials/upload reservations 清零、draft 目录删除、`.objects` 无未引用
对象、报告索引为空。

## pre-fix 清理回读

`finalize.cjs` 于 2026-10-22T07:43:39Z 回读：

- pre-fix 8/8 canonical 运行的断言全部通过（323 项），其中 N12 手机侧同时保留
  `BUSY_OR_INACTIVE` 缺陷观察；所有 `result.json` 与证据
  SHA256 一致，`SHA256SUMS` 数量匹配。
- 实验室最终：73 个 analysis scope 全部 tombstone；38 个 job 墓碑；0 份报告；
  0 条 intake documents / runtime inputs / runner materials / upload reservations；
  `.objects` 0 个对象、0 字节；deletion_intents 73 条；deletion journal 存在。
- 0 个活动扫描器，0 条 RUNNING runner 操作；设备侧无残留 REJECT 规则。
- 所有合成草稿已删除；未清理/重启其他 Compose 项目、共享 dockerd 或 WSL。

## final 2626152 组合结果

final 客户端源码 `262615242161e0371ec151a5f07ef19d360a35e3`，APK
`955d484ba0a01bcf0472e7d97b24fe0d84698af8c61b0efe38b762ca7d3e6088`
（与 `017f031` 构建字节相同）。final 证据目录：
`.scratch/issue133-evidence-final-20261022/`。四例均 PASSED：

| Case | Status | Checks | UTC 时间线（关键点） | 证据 |
| --- | --- | ---: | --- | --- |
| N12-restore | PASSED | 42 | 08:46:39 开始；08:48:32 任务 `e988b8a55443` `QUEUED`；08:49:10 后台 40 s，UI 无错误；08:50:24 `BUSY_OR_INACTIVE` **未观察**；force-stop→restore 同一 alias，start 计数 1 | `N12-restore/` result `2c3b31af475c33fa8d14c4f45c3aa09dc6448b26c39b28a2972e1b8a47414fdf`，81 文件 |
| N12-offline-retry | PASSED | 73 | 08:39:52 开始；08:41:45 基线 `e153466d8234` `SUCCEEDED`（报告哈希 `4b8b4d2f0d8a…`）；08:43:32 目标 `9f70323f5a67`；08:43:40 离线读、08:43:44 离线取消均 `SERVER_UNREACHABLE` 且服务端保持 `QUEUED`；08:43:52 在线取消 fence 0→1；08:45:04 重试 `20e824d3e961`（`retry_of` 指向旧 job）；start 1→1、retry 1、旧报告哈希不变 | `N12-offline-retry/` result `6f049062b656c268f7e9cccacb4dedfe820b56954de26e13ddb1b0a4fc1fe030`，137 文件 |
| F05-scanning | PASSED | 38 | 09:05:26 开始；09:07:30 任务 `022152446b8e`；09:07:32 真扫描容器 RUNNING（`network=none`/read-only/cap-drop ALL）；09:07:39 取消，fence 1→2；无报告；扫描器回收 | `F05-scanning/` result `23a91441fa6d247108a330760ad5a2afddbfb3df2ed7b70cbbb24ea5f2ea310e`，52 文件 |
| F06-precommit | PASSED | 34 | 09:16:45 开始；09:18:54 任务 `72daa6775945`；09:18:56 扫描；09:19:43 原生删除确认；09:20:03 墓碑/材料层清零；09:20:05 迟到真实结果（输出哈希 `d9580bb8df36…`）被拒；旧访问 404 | `F06-precommit/` result `94a4483a61061c4bf6ff2449e740866d11e29f0fd966e3eca82699edc8d53ffe`，51 文件 |

final 组合合计 187 项断言通过；`finalize.cjs` 回读 0 个活动 scope、0 个活动
扫描器、0 条 RUNNING runner 操作、0 条设备侧 REJECT 规则，所有证据哈希匹配。
F05 清理时出现一次 `restore-scanner` 执行器失败（镜像引用被并发重建移动），
但随后的 final 清理已恢复，最终回读无残留；该失败不影响 F05 的产品断言。

### final 清理回读

- 销毁前：保存的 44 个 scope 全部 tombstone（`live_scopes=[]`）；
  DB `analysis_scopes=93`、`jobs=46` 均为墓碑；`runner_materials=0`、
  `runtime_inputs=0`、`upload_reservations=0`、`reports=0`；活动扫描器 0、
  RUNNING runner 操作 0、设备 REJECT 规则 0。`intake_documents=6`、
  `.objects` 6 个/2680 B，属于两笔失败上传留下的草稿（无活动 scope、
  无 capability），随私有 lab root 一起销毁，未进入公开证据。
- 销毁：`provision down --state /var/tmp/pt81-0c0f8a8a048d --purge` 清空
  Compose 容器和私有目录内容；最后的空 root 删除报了一次 OSError，随后用
  已校验路径的 `rmdir` 完成。`pt133e-controller` 已停止并删除；设备
  `adb reverse --remove-all` 已执行（回读为空）。证据目录保留，未清理其他
  Compose 项目或共享 Docker 资源。
- 详细 JSON：`.scratch/issue133-evidence-final-20261022/cleanup-readback.json`。

### final 执行中发现的环境修复

并行 lane 在 17:0x 重建并 retag 了共享 `issue81-test` 镜像，导致本实验室原
`laboratory.json` 中的镜像 ID 失效。为完成 final 补跑，本 lane 将实验室
固定到本票私有 tag：`pt133e-api:pre-fix-e815`、`pt133e-web:4208823`、
`pt133e-runner:4208823`、`pt133e-scanner:4208823`，并把 owner.json 的
`source_sha` 记为 4208823、`client_source_sha` 记为 2626152；未执行任何
`docker image prune` / `docker system prune`，未 retag 共享 `issue81-test` 的
语义标签（只在私有 tag 上冻结）。该环境修复不改变产品代码或断言。

## 未覆盖边界（final）

以下边界对 pre-fix 与 final 均适用；final 只补跑了四例最小集，未扩大矩阵。

1. 自然 LMKD/OEM 进程回收未复现；N12 使用 force-stop 作为进程死亡注入。
2. 离线使用设备侧 REJECT 等同路径，不是飞行模式/射频关闭；一次 radio-off
   尝试导致 adbd 不可达，已恢复且未计入证据。
3. 上传检查阶段的取消/删除不在本次收敛矩阵；排队、扫描、提交前三时点已覆盖。
4. F06 的“删除事实持久”覆盖 10 s 回读、tombstone/DB/journal；API 重启后的
   再读未在 canonical 运行中完成（重启后 API 就绪超过预算，未把超时记为通过）。
5. 扫描取消针对 RUNNING 容器，不证明 APK 解析中途任意瞬间的取消。
6. 单台 MuMu x86_64 设备、单实例、单 Docker daemon；物理设备、OEM、公网、
   外部模型质量未验证。
7. 未使用真实用户数据；所有任务、政策文本和 APK 均为受控合成材料。
