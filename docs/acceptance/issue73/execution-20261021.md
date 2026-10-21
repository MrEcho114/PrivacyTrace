# 本机端到端验收执行记录（2026-10-21）

本文件记录接手 Codex 后在**本机**实际执行的 #73 验收步骤、真实产物身份、已通过项、失败项与未执行项。**结论：整票最终验收未通过**；自动政策组合被产品缺陷 BUG-01 阻断，多场景因本机虚拟化环境反复重启未能完成。

## 1. 授权与范围

- 用户要求从 Codex 接手 #73，并按本机测试要求执行：本机 Android 模拟器、本机 Linux 虚拟化环境、两套独立本机 HTTPS 实例、真实 PostgreSQL/outbox、Redis/Celery、Runner 与受限 Docker。
- #81 已在本轮完成合并后核验并关闭（见 #81 收口评论）；#73 保持 Open。
- 未执行：生产部署、公网发布、商店提交、公开分发；未合并任何产品代码变更。

## 2. 版本锁定

| 项目 | 实际值 |
| --- | --- |
| 被测源码 | main `aa414073859463abfaa133c1d12ac1f24c93eeb7` |
| 控制面镜像 | `privacytrace-api:issue81-test`（构建于该 SHA，本地 tag；CI 已有同 SHA 收据） |
| Web 镜像 | `privacytrace-web:issue81-test` |
| Runner 镜像 | `privacytrace-runner:issue81-test` |
| 扫描镜像 | `privacytrace-scanner:issue81-test` |
| 正式客户端 | `client-local-ca.apk`，sha256 `8bb257dfd3a63d295b858decba7ba0dcee44d6e20c063c01feb1813f4f3fddc8`（debug 清单 + 仅 localhost 本地测试 CA 信任，源码默认不变） |
| 受控样本 | `fixture-base-policy.apk` sha256 `1d14eaddecd7ed2d32a1afe491a8f996e23c76ef30e9330842315e47a13408bf`（内含政策 URL 元数据）；`fixture-feature.apk` sha256 `802550145ec94f69c98e722813d63dfcb015805436d2136d0c59a04c1260b538` |
| 本机测试 CA | `PrivacyTrace73-Local-Test-CA`，SHA-256 指纹 `2D:43:3E:B9:FC:2B:B7:C6:E5:59:C4:1B:64:6C:93:31:44:E1:95:03:9D:3E:42:9C:09:8D:68:96:E2:85:D0:A0` |

## 3. 本机环境

- 宿主机：Windows 11 Pro（26200），i9-13900H，32 GB，Windows 侧 Docker，WSL2 `networkingMode=mirrored`。
- 控制面/扫描面：专用 WSL2 发行版 `PrivacyTrace73-Control`、`PrivacyTrace73-Runner`（Ubuntu 24.04，独立数据根 `/var/lib/privacytrace73/docker`，专用网络命名空间 `privacytrace73`，网络命名空间与宿主不同）。
- 模拟器：MuMu Player 12 专用实例 `PrivacyTrace73`（Android 15 / API 35 / x86_64，`adb 127.0.0.1:16480`）；系统分区只读，因此不使用系统信任区，改用内置本地 CA 的 debug 客户端。
- 工具链：JDK 17.0.20.1、Android SDK platform 36 / build-tools 36 / NDK 27.2、Rust 1.99.1（x86_64-pc-windows-gnullvm）、llvm-mingw；客户端与受控样本均由该工具链在本机构建。
- 网络通路：实验室 HTTPS 端口经两级 TCP 转发暴露到 Windows 回环，再用 `adb reverse` 让模拟器以 `https://localhost:<port>/` 访问；证书链、主机名校验、API Host/Origin 规则保持开启（未使用 trust-all、未关闭 TLS 校验）。
- 受控政策源：受控样本的 manifest 声明 `http://1.1.1.1/policy.html`（`public_target()` 只接受全局地址）。仅对该占位地址在实验室命名空间内做 DNAT 指向本机受控 HTTP 服务，抓取路径、HTML 类型、大小与超时守卫仍真实执行；未访问外部主机。
- 受控模型源：本机 HTTPS `https://localhost:19543/v1/chat/completions`，使用一次性测试凭据，返回受控政策收集 JSON。

## 4. 已执行结果

### 4.1 本机部署专项 R1–R6（R04 入口）

`nsenter --net=/run/netns/privacytrace73 bash deploy/check_acceptance.sh`，源码 SHA `aa41407…`，收据目录 `tmp/deployment-acceptance`。

**结果：`ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER`，37/37 必需检查通过（fail 0、skip 0、not_tested 0）。**

| 组 | 通过 |
| --- | --- |
| R1 完整部署装配与版本锁定 | 1/1 |
| R2 双作用域 HTTPS 业务链路（单 APK 与 base+splits、拒绝类） | 12/12 |
| R3 真实隔离 inspect | 1/1 |
| R4 故障注入与恢复 | 12/12 |
| R5 备份恢复与删除重放 | 4/4 |
| R6 容量与秘密审查 | 7/7 |

豁免：`dedicated-scan-host-verification = WAIVED_BY_USER`（不计 PASS，生产要求不变）。运行中修正了两项本机环境问题并如实记录：Docker 客户端代理注入导致容器内 `api:8000` 被走代理（502），以及实验室命名空间内的回环。收据保留在忽略目录，摘要与原文不随公开材料发布。

### 4.2 Android 真实客户端主链路（部分通过）

已在模拟器上用**实际客户端**完成到上传确认的一段真实链路：

- 客户端原生窗口输入 `https://localhost:28443/` → 能力协商通过（实例 `d37dbfa8-a9cf-4817-b6da-87ee9f177920`）→ 选择受控应用 `org.privacytrace.probe.fixture` → 原生确认上传 → **`SERVER_CONFIRMED`**，界面显示“当前分析材料 材料版本 2”。
- 服务端只读回读确认：`POST /api/v1/web/drafts` 200、`POST …/package-set` 200（经 Runner 的隔离元数据检查）、`GET …/drafts/{id}` 200，`uploaded=true`、`apk_sha256=1d14eadd…`。
- 该组合包含真实的 PostgreSQL/outbox、Redis/Celery、专用 Runner 与受限扫描容器，不是 Mock 或 bridge 替身。

### 4.3 失败项

| 场景 | 结果 | 原因 |
| --- | --- | --- |
| H01 / H04 / H07 / H10（自动政策） | **FAILED** | 产品缺陷 BUG-01：交付拓扑下 `POST /sources/discover` 返回 503 `ISOLATED_INSPECTION_UNAVAILABLE`，客户端显示 `SERVER_BUSY`，无法产生自动来源 |
| H02 / H03 等其余成功组合 | NOT_RUN | 本机虚拟化环境反复重启（见第 5 节），未能在稳定窗口内完成 |
| N01–N12、F01–F10 | NOT_RUN | 同上；BUG-01 未修复前自动政策相关负向也不具备通过条件 |
| R01/R02/R03 | 部分 | R1–R6 已按 R04 本机执行；仓库权威入口与 Spec30/浏览器入口未在本轮窗口内跑完 |

## 5. 环境阻塞（如实记录）

本机 WSL 发行版在本轮多次被外部触发 `systemctl poweroff` 并重启（`wsl-pro.service` 持续重启计数上升，`privacytrace73-docker.service` 随之停止/启动）。每次重启会终止实验容器与临时转发，已通过持久化 systemd 单元（模型/政策/转发/实验室恢复）减小影响，但仍不足以在单次窗口内连续跑完 12 个组合与负向/故障矩阵。这不是产品缺陷，也不能据此把未执行项记为通过。

## 6. 结论与下一步

- 本机环境已按要求准备并可复现（工具链、客户端、受控样本、两套实例自动化、转发与 CA 信任边界均已落地）。
- 本机部署专项 R1–R6 37/37 通过；Android 客户端真实主链路已走到上传确认。
- **整票最终验收不通过**：自动政策组合被 BUG-01 阻断；其余组合与负向/故障矩阵未执行。
- 下一步：先修复 BUG-01（`web_intake._discover_sources` 应使用注入的 Runner 检查器），再在稳定窗口内补跑 H01–H12、N01–N12、F01–F10，并保留 R01–R04 本机入口结果。
