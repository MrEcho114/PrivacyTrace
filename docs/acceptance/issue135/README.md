# PT-MOB-301 · Issue 135 容量背压与运维演练（F08 / F09 / F10）

对应 [#135](https://github.com/MrEcho114/PrivacyTrace/issues/135)，父票 [#128](https://github.com/MrEcho114/PrivacyTrace/issues/128)。案例原定义沿用 [Issue 73 场景表](../issue73/scenarios.md)，不新增分析 pipeline，也不改变父票分母。

**当前状态：本票范围（F08 / F09 / F10）三项均有同一被测提交上的真实演练证据，判定 PASSED。** 整套 R1–R6 汇总为 `ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER`（40 pass / 0 fail / 0 skip），唯一保留项是既有的用户豁免 `dedicated-scan-host-verification`，见「未覆盖与边界」。

被测代码版本：`d12eeb79deeeedd65880717d3b10a703ddbc97a8`（分支 `codex/issue135-ops-acceptance`，基线 `83f42ea2b8a59e34c84d348ef996973643bb5a94`）。本目录只追加记录，不改被测代码；`evidence/` 每份收据的 `source_sha` 都是这个提交。

## 拓扑与入口

演练在 GitHub Actions 的 `deployment-acceptance` 作业里跑：该作业按仓库既有入口 `deploy/check_acceptance.sh` 一次性 provision 两套彼此独立的 compose 项目（各自的镜像、卷与网络），再用仓库既有收集器 `deploy/acceptance/run.py`（R1–R6）执行，不使用任何旁路脚本代替。

被测主机（收据 `r6.hardware_identity`）：4 vCPU（AMD EPYC 7763）、`memory_bytes` 16766414848、磁盘 154894188544 B（可用 89033199616 B）、内核 6.17.0-1022-azure、git 2.55.0 / Python 3.12.3。

汇总：R1 1 / R2 13 / R3 1 / R4 12 / R5 4 / R6 9 = **40 pass / 0 fail / 0 skip**，`pass_rate_of_verified` 1.0。相比单实验室的本机复跑，这里多出的 `r2.cross_instance` 由第二套实验室覆盖，因此不再有 SKIP。

## F08 容量背压

**预期**：并发 1 下提交第二个任务，分别耗尽准入、队列与磁盘预算；系统给有界排队或明确背压而不是无限增长；硬件、限额、耗时、峰值内存/磁盘与拒绝响应都要有实测值，不能用补零代替未测。

**实际**：

- 并发基线（同一入口，3 次重复）：单 APK 任务耗时中位 4.253s（min 2.193s / max 4.269s，输入 1602 B、`input_origin` SYNTHETIC）；base+splits 中位 4.257s（min 2.197s / max 4.259s，输入 5554 B）。扫描端峰值并发实测 1，采样 104 / 201 次 @0.1s，`transient_sampling_failures` 0。
- 峰值资源：扫描端峰值内存 57548800 B / 57782272 B，worker 峰值 80224256 B / 81125376 B，runner 采样峰值磁盘 76198 B / 128502 B，材料区采样峰值 15560 B / 35482 B，`disk_delta_bytes` 0。
- 准入预算：实验室签发 12 份草稿后第 13 份 429 `DRAFT_QUOTA_REACHED`；单客户端预算 3，第 4 份 429 `CLIENT_DRAFT_QUOTA_REACHED`（elapsed 3.89s，`implied_existing_drafts` 0）。
- 队列预算：worker 停住后 4 个任务停在 QUEUED（`active_job_budget` 4），第 5 个 `/start` 返回 429 `ADMISSION_CAPACITY_REACHED` 并带 `Retry-After: 5`（elapsed 20.65s，采样 127 次）；恢复 worker 后 4 个任务全部 SUCCEEDED，扫描端峰值并发仍为 1。
- 磁盘预算：一次性 tmpfs 作有界测试盘（limit 536870912 B），真实 ENOSPC（已用 536821760 B、errno 28）；上传按容量契约被拒 **HTTP 507 `MATERIAL_DISK_SPACE_REACHED`**，释放空间后同一上传 200，保留材料哈希校验通过，演练前残留草稿 4 份已清理为 0。

## F09 一致备份与独立删除重放

**预期**：按既有运维步骤备份专用 DB 与私有材料；删除一个任务后恢复较早备份，再重放删除记录；备份点、材料与索引一致，已删对象不可复活；保留恢复点、删除水位与旧访问材料被拒的证据。

**实际**：备份 69510 B（sha256 `e75978645fa3ed60c39598a1e8d95ec4e916948be07382166e62967e05d854cd`），材料清单 10 个文件（`manifest_sha256` `c346c091abade09cddc2bb89bb6b19c299d17e849d3df1af742a482a658cddd1`），材料在独立卷（`separate_material_volume` true）；恢复到全新数据库（`fresh_database` true）后重放独立删除日志（`independent_deletion_journal` true）共 19 条删除记录；读回校验 `deleted_material_absent` true、`retained_hash_verified` true。旧访问被拒的相邻证据见 `r4.delete_submitted_scope`：删除返回 200，删除后报告 404，材料与索引不重建。

## F10 升级/回滚、凭据轮换与磁盘满恢复

**预期**：在可回滚测试副本上执行既有升级与回滚、内部凭据轮换与磁盘满恢复；版本与迁移兼容或明确阻止危险回滚；新旧凭据按策略生效/失效；没有永久假就绪，数据可核对。

**实际**：

- 升级与回滚（旧镜像 `sha256:6942d1c2be7c94d8218f95ca4d9f5c3a3f2ea14a9656f1f63048c024d8d059cf` → 候选 `sha256:9d09dbb3d59b6aedd176bae77b89a0fedcdb3f0878a6eccb41fee9d0e78fb81e` → 回滚回旧镜像）：每段都实际跑迁移（`0080_05`，protocol 1）并重建角色，每段保留作业的报告均 `retained_report_readable` true；回滚终点与起点是同一镜像 ID。
- 内部凭据轮换：旧数据库口令 `authentication rejected`、旧 broker 口令 `rejected:AUTH`、旧控制面 TLS 对端 HTTP 403；新凭据就绪（`new_control_peer_ready` 200）且完成一次真实扫描，新叶证书指纹 `ab3191b92242c0f01754ef8629437b20e369b8ead439ee18723e58d090f07dde`。
- 磁盘满恢复：与 F08 同一演练实现的独立复跑（临时盘占用 536821760 B，errno 28），上传拒绝 **507 `MATERIAL_DISK_SPACE_REACHED`**、释放后 200、保留材料哈希校验通过，残留草稿 0。

## 证据

- [summary](./evidence/acceptance-summary-20261021T160851Z.json)：总收据（各 scope 计数、豁免与 `untested`）。
- [topology](./evidence/local-r1-r6-topology.json)：角色、镜像 ID、用户、只读根、能力裁剪、限额与扫描主机分离字段。
- `evidence/acceptance-r1..r6-*-20261021T160851Z.json`：六个收集器的逐项收据，同一次运行、同一个 `source_sha`；内含脱敏后的注入命令、时间线与采样值。

## 未覆盖与边界

- 豁免 `dedicated-scan-host-verification`（状态 `WAIVED_BY_USER`，`blocks_this_acceptance` false，`production_requirement_unchanged` true）：独立扫描主机/VM 分离与跨主机防火墙持久化不在本轮证据内，生产要求不变。
- 汇总 `conclusion` 为 `ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER` 只由这一条豁免造成，不是断言失败：fail 0、skip 0、`pass_rate_of_verified` 1.0。
- CI 作业会为 PKI 窗口设置容器内时钟；收据时间与耗时以该作业内的时钟为准，不影响断言结果。
- 收据里实验室内部的绝对路径已归一为 `<lab-state>`（本次 2 处，均在 `r4`），个人主目录由收据自身脱敏为 `<private-home>`；字段、计数、哈希与断言结果保持原样，逐份 JSON 解析验证通过。
- 演练产物只落在 CI 作业的一次性测试区，tmpfs 已在收尾释放；收据经 `r6.receipt_redaction` 与 `r6.secret_audit` 检查（908 个受跟踪文件，其中 68 个二进制跳过），不含能力令牌、凭据 URL 或私有材料。

## 命名空间说明

Issue #135 建议本票写入 `deploy/acceptance/issue135/`。实际新增的演练驱动 `deploy/acceptance/capacity_drill.py`、`deploy/acceptance/client_probe.py` 与 `deploy/tests/test_capacity_drill.py` 留在共享位置，因为 main 上既有的 `deploy/acceptance/r6_capacity_audit.py` 正是从这里调用演练的；搬家会同时改动收集器导入与 CI 引用，收益只是目录归属。改动面与理由在 PR 正文中逐条披露。
