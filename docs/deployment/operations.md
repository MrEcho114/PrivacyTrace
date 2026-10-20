# 运维、备份与回滚

当前仍处于隔离候选验证阶段。以下是利用已合入 #80 运行时组件需要实际演练的步骤和停止条件，不是已执行收据。任何实际公网流量、DNS、证书账户、镜像发布另需授权。

## 首次部署顺序

1. 锁定同一候选源码 SHA、API/Web/编排/Runner/扫描镜像 registry digests、DB 迁移版本及协议版本；核对 [兼容矩阵](validation.md)。确认 #80 的单 APK 和 #70 的完整 split 业务可以共用该组合。
2. 独立扫描主机或 VM 上安装 owner 交接的 Runner。daemon 只允许该主机内部控制，防火墙拒绝公网 Docker API；APK 容器无网络、凭据或其他任务材料，固定镜像、非 root、只读根、drop ALL、资源/时间限制须有实际 inspect。不得将扫描主机根目录共享给 API 或用 Compose 冒充跨主机编排。
3. 在控制面建立保护目录和按 UID 初始化的命名卷。秘密独立备份，环境文件只含非敏感引用。检查总盘量、剩余空间、inode、备份窗口与证书卷；不能靠应用文件字节配额代表全盘容量。
4. DB 空库初始化后，由独立 operator 建立运行时/迁移角色。当前打包 `apps/api/alembic.ini` 和 migration head `0080_05`；隔离环境必须先创建 `privacytrace_runtime` / `privacytrace_migrator` 独立角色，使用 `docker compose --profile migration run --rm migrate` 单次执行并核对 RLS/权限。停止接收任务后，用只持有 migration 文件秘密的单次进程升级；全局只能一个迁移执行者。该角色不常驻 API，API 启动不自动跑迁移，不默认退回 JSON。
5. 依次启 DB/broker、投递器/编排、Runner、API，验证真正依赖 readiness 与 heartbeat；最后启代理及经授权的证书配置。`service_healthy` 只排序启动，不能替代断线重连、重投和 fencing。
6. 初始扫描并发 1，完成两个独立作用域的单 APK/base+splits、跨作用域/跨实例拒绝、取消/删除/迟到结果、重启重投/孤儿回收与容量测试后再评估放量。失败停止入口并保留脱敏证据，不承诺未经测量的用户数。

## 一致备份与恢复

- 备份对象：PostgreSQL 权威状态、私有材料卷、删除 tombstone/审计日志、证书卷、非敏感配置和版本矩阵；秘密单独加密保管。Redis 不是作业账本，不能只恢复 broker 当作任务恢复。
- 先停止新接收，暂停投递/调度并等待或显式停止在途扫描，冻结结果提交。由 #80 的一致性协议登记快照水位；在同一水位备份 DB 和材料索引/文件，记录文件摘要、DB/迁移/镜像版本。不能在工作进程仍写材料时只做一次 `pg_dump` 声称一致。
- 备份清单只保存受控引用/摘要，不复制 APK、政策全文、DB dump 或私有路径到仓库/CI。备份访问与生产凭据分离；保留期、容量、删除窗口须由运维明确，不能静默缩短“材料保留至主动删除”的约定。
- 恢复在独立私网、关闭入口和消费者后进行：恢复匹配 DB/材料、验证摘要和对象完整性，再从快照水位重放删除/撤销记录；恢复旧备份不可复活已删除材料。无法获得完整删除日志时保持关闭，不能猜测。
- 验证任务、作用域、凭据撤销、孤儿对象、fencing/租约和预算，再允许有限重投。迟到旧 Runner 结果必须失效；没有 owner 证明的恢复工具前，不手工删除 DB 状态掩盖失败。

## 升级、回滚与轮换

先做向前兼容的 schema 扩展，验证旧/新消费者与 Runner 协议兼容，再按固定版本组合切换；生产候选不使用可移动 tag。停止条件包括未知 migration head、协议不兼容、跨作用域拒绝失败、依赖不就绪、材料摘要缺失、磁盘或备份不可用。

回滚前停止入口和投递，撤销旧 attempt 结果资格，保存故障水位；仅当旧镜像与当前 schema/消息/材料格式兼容时退镜像。破坏性迁移或不兼容消息不能只退镜像：从已验一致快照恢复，并重放删除/撤销，再验证后开放。不能让旧消费者消费新 schema 的任务。

轮换按服务分开：发布新数据库 runtime 凭据并验证，再撤旧凭据；broker ACL/Runner 内部认证独立轮换；迁移秘密只在单次 operator 进程授予。保护文件原子替换，重建相关容器使挂载更新，不把秘密放入 `docker inspect` 环境、进程 argv 或普通日志。不得通过轮换设备/任务 Key 重置已删除作用域。

## 故障与容量记录

每次演练记录源码 SHA/镜像 digest/迁移/协议、受控输入摘要、硬件/磁盘/内存、命令、开始结束、水位、预期/实测、脱敏证据位置与未测项。需要覆盖 API/broker/worker/Runner 重启与断连、OOM/超时、磁盘满及 inode 耗尽拒绝、心跳过期、取消/删除和结果竞争、孤儿容器/材料回收、恢复后删除重放。

容量从并发 1 开始，记录单 APK 与完整 splits 的耗时、CPU、峰值内存、输入/临时/持久/日志/备份盘量、排队、限流和容量拒绝。静态内存上限和容器启动通过不等于容量实测；磁盘满应拒绝新接收而不是删除长期材料。尚无实测值时保留“未测”。

## 跨机材料网关的受控私网装配（待实测）

控制面网关在 Docker `control` 用户定义子网中使用显式私有容器 IP（`PT_GATEWAY_CONTAINER_IP`）；`PRIVACYTRACE_GATEWAY_BIND` 必须绑定该地址，不使用被运行时拒绝的 `0.0.0.0`。宿主机只能将 8443/TCP 发布到已有的私网或 VPN 网卡地址 `PT_GATEWAY_HOST_IP`；`PT_CONTROL_SUBNET` 不得与宿主/扫描 VM 路由冲突。Runner 通过该私网地址访问 `PRIVACYTRACE_GATEWAY_URL`，需要证书 SAN 与 IP 匹配、真实 CA/mTLS 与对端指纹。上述值只能在已配置私网和防火墙的隔离环境中提供。

API/Worker 可以通过控制网络连接私有 Runner，但宿主机/VM 防火墙必须只允许既定的 Runner 目的地、专用网关端口及授权对端。禁止将网关绑定到 `0.0.0.0`、公网 IP 或发布 Docker API。Compose 配置负测与实际私网连通/拒绝演练是两个证据层级：后者完成前仍不得宣称 R1–R3 全部通过。

## 独立删除日志卷

API 与 Worker 的 `PRIVACYTRACE_DELETION_JOURNAL_ROOT` 指向单独命名卷 `deletion_journal`，不同于任务材料卷 `materials`。日志必须独立做保全与恢复，且恢复旧快照时需重放删除记录，不能只恢复数据/材料后丢弃日志。不同卷不意味着物理独立备份或一致快照：这需要隔离环境另行验证。当前没有真实恢复演练收据。

## 受控材料回收单次任务与调度（待部署验收）

常驻七服务以外的 `reclaim` 仅在 `reclamation` profile 下可见；由受控宿主 systemd timer 在业务低峰周期性执行（建议每 30 分钟，实际按备份/任务负载设置），不以后台无限循环进程偷偷替代。仅在部署已完成数据库迁移且具备受限 runtime 角色后运行：

```bash
docker compose --env-file /etc/privacytrace/deployment.env -f deploy/compose.yaml \\
  --profile reclamation run --rm reclaim
```

宿主调度必须设置 `flock` 或 systemd 单实例锁、有限超时和非零退出告警。失败时保留原有数据库指针和材料，下一次安全重试；不得对正常、未主动删除的作用域按年龄强行删材。生产执行周期、实际退出码、删除/非删除对象计数、异常孤儿恢复和脱敏日志需要在隔离部署中取得真实收据；此文档不代表已进行调度验收。

## 隔离 Control 桥接网与专用 Runner 中继（尚待实测）

`control` 现为 `internal: true`、禁用 IPv6 的隔离 IPv4 bridge，不允许 API/Worker 直接访问公网或扫描 VM 地址。指定 `PT_CONTROL_GATEWAY_IP` 为桥接网关私有 IP，`PT_RUNNER_URL=https://<PT_CONTROL_GATEWAY_IP>:8444`；只允许通过宿主机上最小权限的 **TCP 透传** relay 将该端口转发到唯一专用 Runner 的 mTLS 端口。Relay 不终止 TLS、不解密 APK 或任务资料；Runner 证书 SAN 必须与客户端连接使用的网关 IP 匹配。Relay 应限制来源为容器控制网、目的为经授权 Runner IP:8444，同时由宿主 INPUT 防火墙拒绝控制网到其他宿主端口。禁止将 control 改回普通具有缺省外部路由的 bridge，也不得将 Docker TCP API 转发。

**停止条件：** 尚未在实际宿主配置和测试 relay/INPUT 白名单前，真实 Runner 全链路仍是 NOT_TESTED，不能以 docker compose config 通过替代。需要实际容器内到 relay 的 mTLS 连接、到公网/其他私网/宿主其他端口拒绝、IPv6 拒绝以及容器重启后的策略持久证据。

## 受控回收 timer 模板

`docs/deployment/systemd/` 包含 `privacytrace-reclaim.service`、`privacytrace-reclaim.timer`、`privacytrace-reclaim-failed.service` 示例。Operator 应在创建 `privacytrace-deploy` 专用账户、准备非敏感 env-file、固定部署工作目录和 Docker socket 权限边界后安装并审查这三份 unit；通过 `systemctl enable --now privacytrace-reclaim.timer` 开始计划任务。日志错误通过 syslog authpriv.err 标记，**真正的远端告警需要外部日志平台订阅，尚未验证**。Docker 管理权限接近宿主 root，不能授权不可信用户。timer 仅演示 30 分钟周期；未在本轮用户环境安装或启用。
