# 兼容矩阵与验收证据

本文件记录配置基线和证据边界。实时验收以 #81 当前执行记录、PR 最终 head 及对应 CI artifact 为准；不能把本文的版本组合当作生产验收。

| 组件 | 当前固定基线 | 状态 |
| --- | --- | --- |
| 应用源 | main `e2313e19cd9e43b30aad2044ccf6624e929511cd` | #69/#70、PostgreSQL 第一阶段已合入 |
| Python | `3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36` | 与既有扫描基础镜像一致 |
| uv | `0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479` | 仅构建阶段；apps/api/uv.lock 不变 |
| Node | `24.17.0-bookworm-slim@sha256:862263c612aa437e3037674b85419622a9d93bff80aa1eee5398dfe686375532` | 仅构建阶段；package-lock.json 不变 |
| Caddy | `2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d` | 静态/代理 runtime |
| PostgreSQL | `17.9-alpine@sha256:c7526c0f6c3f30260a563d7bcf8ad778effac59a44f8ffa86678c35418338609` | 配置锁定；本票不声称实际 DB 专项 |
| Redis | `7.4.8-alpine@sha256:7aec734b2bb298a1d769fd8729f13b8514a41bf90fcdd1f38ec52267fbaa8ee6` | 配置锁定；投递角色/ACL 待 #80 |
| migration | 已打包 `0080_01` | 最终 runtime migration head 待 #80 |
| API/Web registry digest | 未发布 | CI 记录本地构建 image ID；不可冒称 registry digest |
| 编排/outbox/Runner/扫描 digest 与协议 | 未交接 | 生产入口 BLOCKED |

Node/Caddy/PostgreSQL/Redis 的 manifest 摘要于 2026-10-19 经 Docker 官方 registry 读取；Python/uv 复用仓库既有固定摘要。Linux CI 的实际拉取/构建结果绑定候选 SHA。更新必须重新审查兼容矩阵并跑专项，不能只改 tag。当前单 Linux Docker 测试不代表多架构验证。

## 已提供的自动验证入口

- `deploy/tests/test_deployment.py`：生产默认/拼写错误启动拒绝、smoke 秘密/真实 DB 拒绝、只读路径不调用业务、完整 Origin、内部 probe 隔离、live 与 ready 区分、上下文审计拒绝私有输入。
- `.github/workflows/deployment.yml`：干净 Linux 构建 API/Web，真实 BuildKit context canary 检查，生产 Caddy 配置验证；真实受限容器中跑 HTTP 合成 demo/规则/静态字体、Host/Origin/伪本机请求、转发头去除、probe/管理面拒绝、写入拒绝及 API 重启，再用本地 CA 验证真实 HTTPS 的证书信任、主机名与 SNI/Host 拒绝。无公网证书账户或系统 trust 变更。
- `deploy/check_linux.py`：在实际 Compose 渲染配置上检验边界并对 12 类破坏配置做负测，生产 preflight 必须失败；输出 `tmp/deployment-receipt.json`，含源码 SHA、容器 image ID、真实 user/只读根/限额/socket inspect 和未测项，不输出完整 config/env/secrets。
- 权威 `bash scripts/check.sh` 保留原门禁，部署专项不替代现有后端/前端/受控 Docker 业务验证。

## #81 六项最终验收

| 原验收项 | 当前覆盖 | 仍缺证据 |
| --- | --- | --- |
| Linux 构建/启动控制面及专用扫描面、锁版本/资源 | API/Web 构建和只读 smoke、配置和资源审计入口 | 实际 DB/队列/Runner 全拓扑与 registry digest、最终迁移/协议 |
| 双作用域 HTTPS→真实 APK/splits→报告与拒绝场景 | 合成 HTTP/本地 CA HTTPS demo、代理限制，写入统一拒绝 | 全部真实业务 E2E、公网证书、跨实例、超限/恶意来源专项 |
| API/编排无 socket，APK 隔离与 daemon 边界 | API 真实容器 inspect；生产配置静态门禁 | 编排及专用扫描主机和 APK 实际 inspect |
| 重启/依赖故障/取消删除迟到/孤儿清理 | API 合成 smoke 重启，live/ready 区分 | 持久任务、broker/worker/Runner 故障与恢复竞争 |
| 一致备份/删除重放/升级回滚/轮换/磁盘满 | 运维步骤和停止条件 | 全部实际演练与收据 |
| 并发 1 容量及无秘密 | 构建上下文 canary/文件白名单 | 硬件/受控 APK 耗时、峰值与拒绝行为实测 |

Linux 镜像与受限 Compose 结果以实际运行收据为准；本机 Windows/WSL 与干净 Linux CI 分开记录，最终 CI 和镜像源码标签须绑定交付 SHA。本机权威检查如有跳过，在 PR 精确列出。Mock、配置渲染、HTTP/本地 CA HTTPS 合成 smoke、真实 DB/broker、专用扫描、真实外网是不同证据层级。#81 保持 open，未合并、未公网部署、未触发公网证书账户或修改 DNS。
