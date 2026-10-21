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
| H01 / H04 / H07 / H10（自动政策） | **首轮 FAILED（BUG-01），修复后 H01 复验通过** | 首轮：交付拓扑下 `POST /sources/discover` 返回 503 `ISOLATED_INSPECTION_UNAVAILABLE`。已按 BUG-01 修复并在本机复验，见 4.4 |
| H02（网页辅助补入） | **主链路通过，政策对照未覆盖** | 上传 → 辅助补入 → 分析 → 报告 → 删除全链路成功；但服务端未配置模型，自动候选提取产出 0 条，报告不含政策声明对照 |
| H03 / H06 / H09 / H12（手机直连模型） | NOT_RUN | 现有执行器在模型收集后会用辅助文本覆盖回填框，不能证明模型来源与审计；且第二实例 J 未准备 |
| H04 / H05 / H10 / H11（base＋splits） | NOT_RUN | 受控 splits 集合未安装（当前仅 `base.apk` 安装态），需 `install-multiple` 重装 base+split 后重跑 |
| H07–H12（第二实例 J） | NOT_RUN | 未准备第二套本机 HTTPS 实例 J |
| N01–N12 | NOT_RUN | 需要人工注入（取消时点、安装态变更、跨实例访问材料、证书负向、抓包、离线恢复等），当前执行器不具备这些控制点 |
| F01–F10 | NOT_RUN | 需要运行时故障注入（停 API/broker、worker 租约中断、重复投递、备份恢复、磁盘满等），本轮未执行 |
| R01 | **通过** | `bash scripts/check.sh`（C 盘干净 worktree，修复分支）全绿：1516 passed / 200 skipped，ruff、web 111 单测、build 全过 |
| R02 / R03 | NOT_RUN | 本轮窗口未执行 |
| R04 | **通过（首轮）** | R1–R6 37/37，见 4.1 |

### 4.4 BUG-01 修复与本机复验（2026-10-21 下午）

**修复**：`WebIntake` 新增 `inspect_metadata`，`DurableWebIntake` 覆写为 `runner.inspect_metadata`，`_discover_sources` 改调 `self.inspect_metadata`，与上传校验共用同一隔离边界。分支 `codex/issue73-discover-inspector-fix`，提交 `0a3d61e`，Draft PR #127。

**权威验证**：`bash scripts/check.sh` 在 C 盘干净 worktree 全绿（D 盘 worktree 因 IO 慢触发 2 例 e2e 的 15s 硬超时，已用 pristine 基线和 C 盘对照排除与本改动相关）。

**API 层复验**（同一实验室实例、同一夹具 APK、同一 `replay-discover.py`）：

| 端点 | 修复前 | 修复后 |
| --- | --- | --- |
| `POST /api/v1/web/drafts` | 200 | 200 |
| `POST /api/v1/web/drafts/{id}/package-set` | 200 | 200 |
| `POST /api/v1/web/drafts/{id}/sources/discover` | **503** `ISOLATED_INSPECTION_UNAVAILABLE` | **200**，新增 `Auto Discovered Policy`（`http://1.1.1.1/policy.html`） |
| `GET /api/v1/web/drafts/{id}` | revision 2，无新来源 | revision 3，含自动来源 |
| `DELETE /api/v1/web/drafts/{id}` | — | 200 `{"deleted":true,"cleanup_pending":false}`，随后读 404 |

证据：`evidence/bug-01-fixed-discover-200.md`。

**客户端复验**（真实 Android 客户端 + 本机实验栈）：

| 用例 | 结果 | 端到端观察 | 证据 |
| --- | --- | --- | --- |
| H01 单 APK + 自动政策 | **通过（主链路）** | 原生窗口输入 origin → 能力协商 → 选包 → 原生确认上传 `SERVER_CONFIRMED` → 自动准备（discover 200 → fetch 受控政策 200）→ 候选页 → 分析 `SUCCEEDED` → 报告已生成 → `删除远端材料` 原生双确认 → 服务端 `deleted:true` | `evidence/H01-local-single-auto-*.txt/json` |
| H02 单 APK + 网页辅助补入 | **通过（主链路）** | 上传 → 辅助回填 JSON 补入（服务端确认“来源和未检查候选已补入”，来源 1→2）→ 分析 `SUCCEEDED` → 报告 → 删除确认 | `evidence/H02-local-single-assist-*.txt/json` |

**两例共同的口径限制**：实验室实例没有配置服务端模型，自动候选提取返回 0 条（页面提示“自动候选未完成…缺证据状态仍保留”）。因此报告已生成、任务 `SUCCEEDED`，但**报告内没有政策声明对照**。这两例只证明“上传→政策路径→分析→报告→删除”主链路，不证明政策对照结论；不得据此宣称 H01/H02 完全通过。

**为完成上述复验修复的本机环境问题**（均属实验室拓扑，不是产品缺陷，已持久化）：

1. Docker CLI 的 `proxies.default.noProxy` 缺 `1.1.1.1`，容器内抓取走宿主代理 → 在 `/root/.docker/config.json` 补齐并重建 api。
2. netns DNAT 回程缺 `10.215.134.0/24` 路由 → 在根命名空间补回程路由。
3. dockerd 重启后 `FORWARD` 的 ACCEPT 被挤到 `DOCKER-FORWARD` 之后并被 internal 网络 DROP → 改写入 `DOCKER-USER` 双向规则。
4. 容器无默认路由 → 显式加 `1.1.1.1/32 via 10.215.134.1`。
   以上由 `policy-egress.sh` + `pt73-policy-egress.service` + `pt73-lab-up.service.d/egress.conf` 幂等保证，`systemctl restart pt73-lab-up` 与 `systemctl restart privacytrace73-docker` 后复验均返回 200。

### 4.5 验收执行器与用例矩阵（本轮补齐）

- 用例总数按 `scenarios.md` 为 **38**（H01–H12、N01–N12、F01–F10、R01–R04）。
- 现有执行器可自动跑 **8** 条（H01/H02/H04/H05/H07/H08/H10/H11），其余 26 条需要人工注入或第二实例。
- 执行器本轮补强：uiautomator 崩溃后不再读取旧 dump、输入后回读校验、原生删除双对话框、采集器 JSON 补 `state` 字段、服务端确认文案作为导入判据。

## 5. 环境阻塞（如实记录）

**首轮**：本机 WSL 发行版多次被外部触发重启，`privacytrace73-docker.service` 随之停止/启动，实验容器与临时转发反复中断；已用持久化 systemd 单元减小影响，但单次窗口内不足以跑完矩阵。

**本轮处理**：定位到持续重启的直接原因之一是已结束的保活/清理流程，已改为长驻 `wsl` 会话保活 + 幂等恢复单元；并在 `reset-lab-state.sh` 中固化“重置业务态（保留 PKI）”的步骤，用于用例之间清空 per-IP 草稿配额。策略性环境修复见 4.4 末段。


## 6. 结论与下一步

- 本机环境已按要求准备并可复现（工具链、客户端、受控样本、实例 I、转发与 CA 信任边界均已落地）。
- **BUG-01 已修复**（PR #127），并在 API 层与真实客户端两个层面复验：`discover` 由 503 变为 200；H01/H02 客户端主链路端到端 `SUCCEEDED` 并完成服务端删除确认。
- 本机部署专项 R1–R6 37/37 通过（R04）；仓库权威检查 `bash scripts/check.sh` 在本机通过（R01）。
- **整票最终验收仍不通过**：38 个场景中只有 H01、H02 在本轮拿到主链路证据（且两例的政策对照未覆盖），H03–H12 未执行（模型路径执行器缺口、splits 未安装、实例 J 未准备），N01–N12 与 F01–F10 全部未执行，R02/R03 未执行。
- 下一步（按优先级）：
  1. 配置服务端模型或补一条可产出的受控政策文本，让 H01/H02 的报告真正含政策对照，再据此判定这两例是否完全通过；
  2. 安装受控 splits 集合（`install-multiple`）→ 补 H04/H05；
  3. 准备第二套实例 J → 补 H07–H12 与 N06；
  4. 按 N/F 场景逐个补人工注入能力，再执行负向与故障矩阵。

