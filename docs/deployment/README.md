# PT-SRV-102 部署交付基线

本目录对应 [Issue #81](https://github.com/MrEcho114/PrivacyTrace/issues/81)。当前可交付固定依赖的 API/静态前端镜像、受限配置和 Linux HTTP/本地 CA HTTPS 合成 smoke。**生产启动仍被代码明确拒绝；不得作为公网服务使用。** #80 的持久调度、专用 Runner、故障恢复尚未交接，不能通过挂 Docker socket 或启用 JSON 绕过。

入口：[`deploy/Dockerfile`](../../deploy/Dockerfile)、[生产清单](../../deploy/compose.yaml)、[独立 smoke](../../deploy/compose.smoke.yaml)、[运行时交接契约](../../deploy/runtime-contract.json)、[恢复手册](operations.md)、[证据与兼容矩阵](validation.md)。没有修改应用业务、既有 worker 镜像、依赖锁、根 `.dockerignore` 或权威检查入口。

## 构建与验证

在干净 Linux checkout 根目录运行。需要 Docker Engine、BuildKit、Compose v2、Python 3.12 和 uv 0.11.23；不需要公网 DNS、凭据或 APK。

```bash
uv sync --project apps/api --locked --extra worker
uv run --project apps/api --locked --extra worker python -m unittest discover -s deploy/tests -v
uv run --project apps/api --locked --extra worker ruff check --config apps/api/pyproject.toml deploy
docker build -f deploy/Dockerfile --target api --build-arg VCS_REF="$(git rev-parse HEAD)" -t privacytrace-api:issue81-test .
docker build -f deploy/Dockerfile --target web --build-arg VCS_REF="$(git rev-parse HEAD)" -t privacytrace-web:issue81-test .
uv run --project apps/api --locked --extra worker python deploy/check_linux.py
bash scripts/check.sh
```

专项使用固定名 `privacytrace-smoke` 和 `privacytrace-deployment-infra-test` 临时 Compose 项目，最后删除对应容器/网络/卷。不要让其他服务复用这些名字；不要同时跑两份专项。只在 `127.0.0.1:18081` 暴露 HTTP，`Host: privacytrace.test`；随后叠加 `compose.tls-smoke.yaml`，在 loopback 18443 验证本地 CA HTTPS、证书信任、主机名与 SNI/Host 不一致拒绝。只复制 CA 公共证书给测试客户端，并实际 inspect 私钥存储为容器 tmpfs；不修改系统 trust store。另启动不发布端口的空 PostgreSQL 测试库及 Redis，检查文件秘密认证、非 root/只读根、数据卷/AOF 重建。密码为本次随机合成值，父目录私有；不使用生产材料或应用 schema。它们不是 #80 持久调度、备份恢复或 HTTPS→APK→报告验收。

API runtime 只安装锁定的运行依赖，不安装 Androguard/pytest/Ruff/uv，不运行 APK。通过 `PYTHONPATH=/app/apps/api/src` 保留当前 `resources.ROOT` 预期目录；镜像带 active taxonomy、SDK signatures、明确的合成 demo JSON。前端由锁定 Node/npm 构建，Caddy 仅保存 dist、两份字体及许可证。依赖下载只发生于构建阶段。

Dockerfile 专用 `Dockerfile.dockerignore` 的优先级见 [Docker 官方说明](https://docs.docker.com/build/concepts/context/)。白名单不改变已有扫描 worker 的根构建上下文。实际 BuildKit context 在构建中再由 `audit_context.py` 检查；CI 在 data/private/.env 放无敏感值的 canary，确保它们不会进入 context。API 最终层没有构建工具或项目缓存，也不复制整个仓库。API 依赖用 [uv 的 locked sync](https://docs.astral.sh/uv/guides/integration/docker/)。

## 配置边界

`deployment.env.example` 仅含非敏感字段。构建后的应用镜像必须由后续授权的镜像发布步骤得到 registry digest，再替换两个占位符；本票不推送镜像或发布 tag。生产清单上的 PostgreSQL/Redis 摘要已固定，配置检查拒绝应用镜像标签。不能用本机 image ID 冒充 registry digest。

```bash
python deploy/preflight.py --env-file /etc/privacytrace/deployment.env --config-only
python deploy/preflight.py --env-file /etc/privacytrace/deployment.env
```

第一个命令仅验证渲染清单，不打印环境或秘密；第二个命令无条件拒绝生产启动，直到 #80 集成提交替换该门禁。`docker compose config --quiet` 可单独检查语法；不把完整渲染结果写入公开日志。不要直接执行生产 `compose up`：即使绕过 preflight，API launcher 仍拒绝启动，健康依赖无法放行代理。

生产设计：Caddy 唯一公开 80/443，容器内使用无特权端口 8080/8443；管理端点关闭。API 不发布端口，PostgreSQL/Redis 只在内部网络；Caddy 不加入数据库网络。API 也没有默认出站通路，后续政策抓取必须通过经 #80 交接的目的地白名单代理，不得开放任意 egress。Compose 不负责跨主机调度。

全部服务非 root、只读根、drop ALL、no-new-privileges、pids/内存/CPU 限额。写入限于命名卷及带大小上限的 tmpfs；API/编排不得挂 socket、宿主根或特权设备。命名卷初始化后的权限须实际检查，不能以 YAML 的 user 字段替代 inspect。初始重启策略为 `no`，便于保留失败现场并避免配置错误无限重启；运行时恢复策略待 #80 验证。

代理只信任配置中的单一 Host，API smoke 强制 remote 模式、完整 Origin（scheme/host/port）相等，并拒绝所有写请求与非白名单资源。代理删除客户端 forwarding 头，Uvicorn 关闭 proxy-header 信任；smoke 共享单 API 限流预算，不提供按真实客户端 IP 的生产容量承诺。150 MB 代理上限及 API 既有更细限额不放宽；实际上传、分块超限和慢请求验收仍待运行时交接。Caddy 的 [反向代理行为](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) 与 [请求体限制](https://caddyserver.com/docs/caddyfile/directives/request_body) 以官方文档为准。

探针在 API 容器内执行：`probe.py live` 只判断当前 HTTP 进程；`probe.py ready` 返回失败。网络内其他容器及公开代理无法读取内部 probe。生产 readiness 必须检查 DB/schema、broker/dispatcher 及 Runner freshness；不能把现有 `/api/v1/health` 固定 `ok` 当成就绪。当前无 Runner 心跳实现或假心跳文件。

不启用请求 access log；Caddy runtime 日志丢弃，避免错误日志附带完整 URL/headers。保留容器退出码、外部探针和脱敏收据用于诊断；后续启用结构化日志之前必须验证 URL、capability、DB URL、模型 Key 和异常脱敏。Docker 本地日志有轮转上限。静态响应采用 no-store、no-referrer 与 CSP；不改变静态证据、UNKNOWN 或政策未复核语义。

## Secrets 与下一步交接

实际秘密在 checkout/镜像/context 之外的受保护宿主文件中。Compose secrets 是文件挂载，不是加密 vault。独立 `runtime_database_url` 仅授 API；`postgres_password` 仅授 DB；含认证及持久化配置的 `redis.conf` 仅授 Redis。迁移 URL 不授 API，模型 Key 不入任何服务。API 当前不消费 `_FILE`，生产门禁避免静默忽略配置；文件加载接缝与运行时 role 命令一起等待 #80 串行交接。

Standalone Compose 文件 secret 的 uid/gid 不可假定会重映射。按实际容器 UID（API 10001、PostgreSQL 70、Redis 999）设置宿主文件所有者和只读权限，父目录禁止普通用户访问；不要在共享宿主运行未经信任的容器。Redis 配置需至少认证、`appendonly yes`、`appendfsync everysec`、`maxmemory-policy noeviction`、小于容器限额的 `maxmemory`，并由 #80 明确投递/消费 ACL。不能将密码放在命令行或普通消息内。DB bootstrap 超级用户只作空库初始化，应用和迁移使用独立角色；不能把 bootstrap URL 授 API。

`runtime-contract.json` 列出尚未交付的 API dispatch、outbox publisher、Celery worker 和专用 Runner 角色。这里没有用 `sleep`、占位消费者或任意命令拼出可运行的假服务。收到 owner 提供的 role 命令、依赖锁、migration/protocol 版本、内部凭据和实际恢复收据后，先整合在一个受控候选提交，再开放生产启动。扫描主机或 VM 的安装、系统服务、固定扫描镜像摘要、内部 mTLS/认证和防火墙清单都须以实际 Runner 为准；当前契约是交接清单，不是安装完成证据。
