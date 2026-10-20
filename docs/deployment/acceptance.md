# PT-SRV-102 实际部署验收入口

对应 [Issue #81](https://github.com/MrEcho114/PrivacyTrace/issues/81)。本次交付增加可重复运行的 Linux 临时环境、Runner/Scanner 镜像、私网 TCP relay、R1–R6 收据及 CI。生产启动授权仍关闭。

## 执行

在干净、已提交的 Linux checkout 中执行 `sudo bash deploy/check_acceptance.sh`。需要 Docker Engine、BuildKit、Compose、Git、OpenSSL 和 Python 3.12。脚本构建当前 SHA 的镜像及历史兼容镜像，生成两个独立实例的临时秘密和本地 CA，通过真实 PostgreSQL、Redis、Celery、mTLS Runner 与受限扫描容器运行合成 APK；退出时只清理本次随机项目。收据输出到 `tmp/deployment-acceptance/`，CI 按源码 SHA 归档 JSON。不要归档 `/var/tmp` 中私有实验目录。

未配置环境、缺少观测或执行失败不能算通过：CLI 对失败返回 1，对未完成返回 2。容量只报告实际测量；三任务排队和 draft 限额不代表测过队列满载拒绝。Runner 停机探针证明 readiness 降级；运行中租约回收由受控孤儿任务演练单独验证。timeout/OOM 使用专门故障镜像，其结果不作为 APK 分析证据。

## 本次证据与剩余项

2026-10-20 本机 WSL 的候选演练已实际跑通 HTTPS 单 APK/base+splits 至报告、跨 scope 拒绝、无认证拒绝、代理超限拒绝、限流，以及备份后删除→新数据库/材料卷恢复→独立删除日志重放、数据库/Broker/mTLS 凭据轮换、历史版本升级回滚。它们属于提交前候选演练，不能替代最终交付 SHA 的 CI。

最终新增完整 R1–R6 组合尚待 CI；本机 ENOSPC 演练仍失败，不能将 Issue 标为全部通过。新增故障和容量测量也须以最终 CI 收据为准。

独立扫描主机/VM、跨机防火墙及持久化验证经用户明确授权跳过，记录见 [acceptance-scope.json](acceptance-scope.json) 与其中的 Issue 评论。状态为 `WAIVED_BY_USER`，不伪记为 PASS。此次没有公网部署、DNS/ACME、镜像发布、合并或关闭 Issue。

## 独立 Runner 与 relay

`deploy/Runner.Dockerfile` 从同版 API 镜像加入校验哈希的 Docker CLI；`deploy/Scan.Dockerfile` 保持非 root、独立入口且不带 CLI。专用宿主使用 `deploy/runner.compose.yaml`，`PT_RUNNER_ROOT` 在容器与 daemon 宿主上必须是同一绝对路径。

`deploy/relay.py` 配合 `systemd/privacytrace-runner-relay.service` 提供受限 TCP 转发，TLS 在调用端与 Runner 间终止。服务账号、环境文件、固定私网地址和宿主防火墙由部署环境提供：仅允许控制面至 Runner 8444，以及 Runner 至材料网关 8443。应用来源 CIDR 检查不能替代宿主防火墙。此安装流程尚无独立宿主运行证据。
