# #80 第一阶段：PostgreSQL 持久存储与迁移

执行范围为用户指定的第一阶段；#80 整票继续开放。唯一会话与上一轮状态见 [远端执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/80#issuecomment-6215011665)。2026-10-17 用户授权同一会话修订审查问题，并明确禁止远端写入；本轮进展与证据另存本地修订记录，远端记录按原状态保留。

## 基线与归属

#69 已由 PR #85 合入 main `baee41e5ced809caac274928f576d9da7a984920`；本阶段分支为 `codex/issue80-postgres-stage1`。上一轮记录称七套 HTTP 检查 179 passed，但没有保存精确文件集和独立原始日志；本轮不倒造其命令，改用下文固定的七套件重新在 main 快照与修订版分别验证。已回读 Issue 的当前记录与单一负责人，开放 #76/#84 无本阶段文件交集；保留 #76 所有的 isolated_scan.py 不动。

本阶段维护 PostgreSQL 适配、Alembic、材料引用、专项及必要装配。`auth.py` / `JobStorageProtocol`、公共业务模型及生成契约保持现有来源；#70 拥有语义/多包整合，#81 拥有部署与生产 CI。

## 改动与理由

- `PostgresJobStore` 实现 #69 的 `JobStorageProtocol`；继承现有保存、取消、报告重算和备注校验。PostgreSQL 保存实例/分析作用域、凭据摘要、经过既有模型验证的 Job/报告/政策记录和事务审计；不会在启动时读取本机 JSON。
- `PostgresWebIntake` 复用现有政策/候选逻辑。完整草稿与政策输入写入私有卷中的不可变对象，数据库记录服务端生成的引用、SHA-256 和大小。读取核对摘要；数据库提交前的失败最多留下无引用文件，不替换已提交材料，也不把文件目录当授权来源。
- 稳定实例 UUID 进入数据库复合键和事务局部 RLS 上下文。独立实例即使共用数据库、相同 job_id，也不共享记录或凭据。HTTP 操作仍使用 #69 的能力授权；实例 UUID 是运维配置，不能取自请求。
- 使用数据库事务及每实例事务锁保持旧存储的串行修改语义，覆盖独立连接和进程。它不是执行租约或分布式调度器。审计与状态一并提交；运行时不能删除 tombstone 或修改既有审计。
- 保留进程内 worker，但先在事务中预留容量、提交登记，再启动执行。提交失败注入已先复现失败再修复，验证回滚的登记不会启动 worker；这不提供提交后进程崩溃的持久投递保证。
- 删除撤销 Job 摘要、移除在线 Job 中的报告/政策/备注内容并保留 tombstone，阻止迟到报告、状态更新或旧 ID 重建。取消后的报告同样不能覆盖终止状态。
- API 只消费运行时 URL，拒绝 schema owner、owner 成员、superuser/CREATEDB/CREATEROLE/BYPASSRLS 或不匹配的迁移版本。没有建表、自动升级或 JSON 降级兜底。Alembic 使用独立迁移 URL，运行时只有 schema USAGE 和明确的数据权限。
- 默认仍为 JSON，CLI 仍显式创建 JSON JobStore。Web pipeline 接收当前 store，避免写入另一个 JSON 后端；本机结果路径保持兼容，PostgreSQL 结果不会伪报一个不存在的 JSON 文件路径。

数据库中的报告包含原有报告契约所需的政策内容，属于私有数据，必须纳入数据库访问和备份保护。草稿输入的原文在材料卷。能力明文仅在创建响应中返回；数据库、材料及服务日志均不保存能力明文。

## 操作与复现

需要 PostgreSQL（本次实测 17.9）、Python 3.11–3.13、uv、Git Bash 和 Node/npm。依赖锁定在 `apps/api/uv.lock`。本次使用原生 PostgreSQL 服务，不是 SQLite、数据库 Mock 或 WASM 替代。

1. 在新的专用库由管理员参考 [`postgres-roles.sql`](../../scripts/postgres-roles.sql) 建立两个无特权 LOGIN。脚本只为新库准备，不重置已有角色或口令；密码由运维私密配置。迁移角色拥有数据库/schema，运行时不能继承该角色。
2. 仅向迁移进程提供 `PRIVACYTRACE_MIGRATION_DATABASE_URL=postgresql+psycopg://...`，执行：

   ```sh
   uv sync --project apps/api --locked --extra worker
   uv run --project apps/api --locked alembic -c apps/api/alembic.ini upgrade head
   uv run --project apps/api --locked alembic -c apps/api/alembic.ini current
   uv run --project apps/api --locked alembic -c apps/api/alembic.ini check
   ```

3. API 配置 `PRIVACYTRACE_STORAGE=postgres`、运行时 `PRIVACYTRACE_DATABASE_URL`、稳定 `PRIVACYTRACE_INSTANCE_ID` UUID、私有材料 `PRIVACYTRACE_STORE_ROOT`。远程机制检查另设 `PRIVACYTRACE_MODE=remote`；本地验证只监听回环：

   ```sh
   uv run --project apps/api --locked uvicorn privacytrace.main:app --host 127.0.0.1 --port 8000
   ```

   同一个实例重启必须保留 UUID、数据库及材料卷；不同实例必须使用不同 UUID。不能把实例 ID 当作用户或设备身份。不要向 API 进程分发迁移凭据。

4. 专项必须使用明确的、可丢弃且名字以 `_test` 结尾的数据库。提供 `PRIVACYTRACE_TEST_DATABASE_URL`（运行时）和 `PRIVACYTRACE_TEST_MIGRATION_DATABASE_URL`（迁移），二者连接同一测试库而使用不同角色。测试**包含删除测试表及重新升级**，不得提供正式库。执行：

   ```sh
   uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_postgres_storage.py -q -p no:cacheprovider --tb=short
   ```

   Windows 也可运行 `pwsh -NoProfile -File scripts/check-postgres.ps1`；该入口在缺少 URL 时失败，避免把跳过误作 PostgreSQL 验证成功。通用 pytest 不配置测试 URL 时会明确跳过专项；配置无效或服务不可达会失败。

5. 同样的测试库变量保留时，运行仓库权威入口 `pwsh -NoProfile -File scripts/check.ps1`（委托 `bash scripts/check.sh`）。本次本地 Docker 分支未开启，相关跳过单独报告。检查迁移文件另运行 `uv run --project apps/api --locked ruff check apps/api/migrations`；标准 Ruff 行已覆盖源码和测试。

## 迁移、回退和数据边界

初始版本为 `0080_01`。重复 `upgrade head` 保留已有记录；`alembic check` 验证元数据与实际表一致。没有自动导入器；现有 JSON、旧 job_id 或 JSON 中的旧摘要不会建立数据库作用域，也不会凭此得到远程访问。未来若增加明确选择导入，必须单独定义新作用域/凭据和 ID 映射。

`downgrade base` 是显式破坏性操作，会删除本阶段的表及在线数据，不是数据恢复方案；测试仅在可丢弃库执行。正式回退前需由运维做一致备份并明确批准，不能靠回退代码恢复数据库。API 不调用 downgrade 或迁移。

草稿和政策不可变对象在私有卷，APK 在服务器生成的 Draft 目录；数据库和整个实例材料目录必须成套备份。仅恢复数据库不能恢复原文/APK，缺失或不匹配的材料会拒绝读取。此阶段没有交付成套备份恢复及删除记录重放演练。

PostgreSQL 模式不以旧草稿 TTL 自动删除官方材料；达到现有数量/历史上限时拒绝新接收。本机 JSON 模式保留已有 TTL。材料生命周期、无引用对象清理、主动删除卷文件和容量运维属于后续阶段；不能把数据库 tombstone 表述为已擦除卷或备份。

## 验证与限制

真实 PostgreSQL 专项覆盖：迁移/无漂移、独立进程报告/备注读取、原来源与重放语义、事务回滚、并发重复创建、删除与发布竞争、取消与迟到结果、RLS、同 ID 跨实例隔离、角色权限、HTTP 跨 Job/Draft 操作、草稿/政策/未勾选候选/上传摘要重启读取、材料篡改、回滚修订重试、孤儿目录、旧 JSON 不导入，以及真实 TCP HTTP API 进程终止/重启后的授权和撤销。

数据库专项使用显式合成上传和既有受控报告契约夹具。pipeline 接入检查仅把 scanner 换成确定性替身，HTTP、intake、pipeline 和 PostgreSQL 保留真实实现；不声称进行了 APK 分析。TCP HTTP 为回环服务，不证明公网 HTTPS/代理或手机端行为。

保留现有单宿主 WebIntake 执行约束；此阶段没有 Celery/Redis、outbox 消费、执行租约/fencing、runner 或多副本恢复。不预建这些尚无消费者的表或冒称完成整票。数据库与材料卷的生产备份、删除重放、Linux 部署、真实 Docker 扫描、实际公网 HTTPS、Android、外部模型均未由本阶段验收。

## 上一轮实际结果（2026-10-16，保留当时计数）

- 初始主线 HTTP 记录：179 passed，0 skipped；因精确清单与独立日志缺失，不将该数字作为本轮可复现验收证据。
- 最终数据库专项 35 项，加上后端配置选择 5 项：40 passed，0 skipped；本地单命令入口已实际执行。
- `alembic current`：`0080_01 (head)`；`alembic check`：没有新的升级操作。迁移重复执行、运行时拒绝迁移、显式 downgrade/base 后重新 upgrade 均经真实库验证。
- 实际重启 PostgreSQL postmaster，核对其启动时间改变，受控报告重启前后完全一致。它与 API 进程重启、跨进程读取是分别执行的检查。
- 未过滤的权威入口：1 failed / 1014 passed / 20 skipped；失败为既有 `test_cache_writer_does_not_follow_directory_symlink_or_corrupt_parallel` 创建符号链接时的 Windows `WinError 1314`。在原始 main 快照执行同一用例，复现同样错误，未修改或弱化该测试。
- 最终版本显式以 `PYTEST_ADDOPTS='-k "not test_cache_writer_does_not_follow_directory_symlink_or_corrupt_parallel"'` 补跑同一权威入口：1021 passed / 20 skipped / 1 deselected；前端 46 passed；Ruff、TheMasterplan verify、准备包、契约零差异、类型检查与生产构建通过。最终计数包含后加的提交失败回归；不能称未过滤权威入口全绿。
- 跳过分类于 2026-10-17 核正：20 项由 11 个未开启的真实 Docker 用例与 9 个缺少受控源码构建产物的用例组成，不能全部称为 Docker 跳过。剩余 1 条既有 Starlette 弃用警告；npm 12 阻止 esbuild postinstall 的提示不影响已完成的类型/构建检查。迁移目录的独立 Ruff 和 `git diff --check` 通过。

最终 diff 为 18 个文件，未编辑 CI、授权机制、公共语义模型或生成契约。分支保留本地未提交改动和可查看的新文件，供用户本地检查；未 push、创建 PR、合并、部署或关闭 #80。本地收据绑定 main 基线和完整补丁 SHA-256，旧阶段收据保持原 SHA 与原状态。

## 审查修订（2026-10-17）

本轮只修订原 18 个文件中的 web_intake.py、pipeline.py、test_postgres_storage.py 和本文档；起始完整补丁与历史报告、日志、收据均保留原字节。

- 删除关联 Job：恢复、活动任务判断、在途执行结束及关闭服务时识别已知 tombstone。旧提交 ID 的重放仍返回 404，新提交 ID 可创建新 Job；未知缺失记录继续报错，不将损坏数据默认为已删除。不改凭据授权或引入新的公开状态。
- 上传失败：文件描述符和本次创建的 upload.pending 的清理覆盖初始事务退出，包括真实 COMMIT 失败；拒绝重复上传时保留另一个上传的标记。测试通过专用可丢弃库中的探针表和可延迟外键，让 PostgreSQL 在 COMMIT 时真实返回 23503；探针表在测试后删除，不进入产品迁移。
- APK 输入摘要：Web 将上传登记摘要传给既有 pipeline，在扫描返回的实际输入摘要与其不符时以 INPUT_DIGEST_MISMATCH 失败，拒绝发布报告。覆盖启动前替换和扫描期间替换。CLI 调用不传新增的可选函数参数，原受控输入的独立校验继续保留；不修改 scanner 或 runner 协议。

先补的 11 个回归全部失败，覆盖上述三项；修复后通过，另补 4 个保护用例，确认未知引用不会被吞掉、其他上传的标记不会被删除。新增 15 项，加上原专项与配置检查共 55 passed、0 skipped：43 项使用真实 PostgreSQL，7 项为 JSON 接缝，5 项为配置选择。新增涉及扫描的 HTTP 用例保留真实 executor、pipeline 与存储，只替换 scanner，不表示完成了实际 APK 分析。已有登记失败用例使用 executor.submit spy 和 COMMIT 前异常注入，与新上传用例的服务端真实 COMMIT 拒绝分列。

本轮固定的七个 HTTP 套件为 capability_tokens、endpoint_matrix、remote_transport、resource_bounds、pr85_security_followup、pr85_review_regressions、pr85_final_regressions。main 快照对应源码和测试先逐文件核对 HEAD 字节，再用相同七文件运行；main 与修订版均为 160 passed、0 skipped。完整 argv、输出、JUnit 和运行前后源码哈希保存在本地修订证据，通用复现命令为：

```sh
uv run --project apps/api --locked --extra worker python -B -m pytest \
  apps/api/tests/test_capability_tokens.py \
  apps/api/tests/test_endpoint_matrix.py \
  apps/api/tests/test_remote_transport.py \
  apps/api/tests/test_resource_bounds.py \
  apps/api/tests/test_pr85_security_followup.py \
  apps/api/tests/test_pr85_review_regressions.py \
  apps/api/tests/test_pr85_final_regressions.py \
  -q -p no:cacheprovider --tb=short -ra
```

- JSON/Web/CLI 指定回归：92 passed、3 skipped；3 项属于真实 Docker pipeline。
- 原样权威入口：1036 passed、20 skipped、1 failed；唯一失败仍为原有符号链接用例的 WinError 1314。
- 同一入口显式排除该一项：1036 passed、20 skipped、1 deselected；Web 46 passed，Ruff、治理、准备包、契约零差异、类型和生产构建通过。未改符号链接测试、CI 或系统权限；原样入口仍不能称为全绿。
- 完整跳过分类：test_isolated_cli.py 8 项与 test_pipeline_cli.py 3 项要求 PRIVACYTRACE_DOCKER_TESTS=1；test_controlled_source_cli.py 9 项另要求 PRIVACYTRACE_CONTROLLED_ARTIFACTS 指定新鲜受控构建产物。已逐用例收集并保存原因。

真实数据库 COMMIT 拒绝已覆盖；提交成功后确认丢失、数据库断连下结果不确定、掉电/文件系统目录耐久性及迁移中途故障恢复尚未验证。原有后续范围继续保持，不将正常服务重启冒称掉电恢复，也不把 scanner 替身、跳过用例或本机检查冒称真实 Docker、Linux 部署或远端 CI。后续进入 PR 流程时仍需按最终候选版本运行相应检查；本轮没有提交或远端状态变更。

权限与迁移依据：[PostgreSQL privileges](https://www.postgresql.org/docs/17/ddl-priv.html)、[SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)、[Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands)。这些资料不是本项目实测证据，实际检查结果以上述命令输出为准。

## PR #87 两项 P2 修复（2026-10-17）

用户明确要求修复 PR #87，本轮主交付代理接手这两项评审修订，唯一交付入口仍为原 PR／原远端分支；以上历史授权、SHA、计数与收据不倒改。范围限材料容量、活跃 Job 额度、相关启动恢复及回归；不进入第二阶段，不关闭 #80、不合并或部署。

- `.objects` 每实例最多 1536 MiB 文件字节、16384 个文件；每次写入在同一实例的 PostgreSQL 事务 advisory lock 内，扫描实际目录并预留本次完整对象的大小后才创建文件。旧 current/model 指针对应的对象、回滚与崩溃留下的未登记对象均计入；异常目录项拒绝写入，不能通过索引替换绕开容量检查。对象数量上限另限制小文件和零字节残留的增长。
- 达到上限时以 `Private material capacity reached; operator action required` 拒绝写入，不创建新对象或替换已提交引用。保留现有每草稿 128 MiB revision 逻辑检查；APK 仍由原有 Draft 数量和单文件大小约束，不计入这个 `.objects` 上限。文件字节／数量限制不等于整个卷的剩余空间、文件系统分配块或数据库容量保证。
- 启动时仅为实际被标记为中断失败的 Job 写回草稿事件；空闲草稿不再因每次重启产生对象，即使对象容量已满仍可启动并授权读取。若恢复在途 Job 需要新增事件对象而容量已满，恢复写入明确失败，需要运维处理容量后重试；不默默丢弃事件或删除旧材料。
- `MAX_RECORDS=1000` 只计当前实例中未 tombstone 的 JOB 作用域。删除释放活跃额度，但保留 tombstone、撤销访问凭据，旧 ID 不能重建，迟到 `save_job` 不能复活任务。墓碑与审计属于保留历史，不占活跃额度；数据库历史预算与清理仍属后续运维／生命周期范围。

修复前，最初六项真实数据库回归全部失败；修复后扩为八项，覆盖创建至上限／多轮删除重建／旧 ID 与迟到写保护、释放额度后的并发创建、current/model 连续覆盖至字节边界、回滚和未登记文件计量、零字节对象数上限、独立连接并发容量检查，以及满容量下三次 HTTP 服务重启读取。专项连同既有 PostgreSQL、JSON 接缝及配置检查为 **63 passed / 0 skipped**，使用隔离的 PostgreSQL 16.15 可丢弃测试实例与不同 runtime/migration 角色；不沿用上一轮 PostgreSQL 17.9 的版本声明。

完整 GC、自动释放残留文件、成套备份恢复、数据库历史容量管理、掉电及磁盘空间耗尽故障注入仍未交付。达到上限后需运维检查引用与一致备份、处理或扩充私有卷；不能直接把所有未索引文件视为可删除材料。本轮权威检查及最终 SHA 的远端结果以 PR #87 的最新修订记录为准。

本轮原样 `pwsh -NoProfile -File scripts/check.ps1` 已通过：后端 **1045 passed / 20 skipped**，前端 **46 passed / 0 skipped**；治理、Ruff、准备包、schema 零差异、类型检查与生产构建通过。未设置 `PYTEST_ADDOPTS`，没有排除符号链接用例；历史 Windows WinError 1314 仍是旧记录，本轮不复现。真实数据库 51 项已运行；跳过的 20 项仍为 11 个 Docker opt-in 与 9 个缺受控构建产物的用例，不能称本地 Docker 验收完成。额外迁移目录 Ruff 和 `git diff --check` 通过。
