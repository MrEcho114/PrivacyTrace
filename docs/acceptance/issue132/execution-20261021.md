# #132 本机验收执行记录

负责人 Follotrain；唯一执行会话 `01a15d61-89c4-73a0-afa8-30e85b08b3b8`。
授权为用户要求接手 #132、补齐剩余工作并继续推进。当前执行记录仍使用
[#132 唯一评论](https://github.com/MrEcho114/PrivacyTrace/issues/132#issuecomment-6310742815)。
本轮只写本票检查器、夹具源码、测试和验收资料；父票矩阵由 #128 整合 owner 维护。
PR #139 已交付开发入口；本轮是实际客户端全变体验收及网络检查器补充。

## 结果与原定义覆盖

四例在下述本机组合均 **PASSED**，结果逐条列于 [case-results.json](case-results.json)。
`final_acceptance_passed=false` 保留，交父票核对最终集成版本，不据本票提前放行父票。
子收据中的 `scenario_status=NOT_RUN` 表示它们自身只检查子集，字节和状态没有改写。

| 原案例 | 实际动作与预期/实际 | 主要证据 |
| --- | --- | --- |
| N05 | 同一 J 中真实独立 A 对 Android 建立的 B；19 个任务端点 × 缺失/损坏 Bearer/错配 Bearer/损坏自定义头/错配自定义头，95/95 精确 401/403、固定通用拒绝体；每次后完整 B 状态摘要不变 | [95 项收据](evidence/N05-live-receipt.json)、[真实 A 扫描](evidence/matrix-setup-resume-receipt.json) |
| N06 | 用 J 材料访问现存 I/B：95/95；两边原 ID/原材料投至对方：38/38 精确通用 404，区别于现存目标 403。实际 I 响应延迟 60s，点击停止请求、原生切到 J；旧 I 响应确实在服务器写出，J 选择及页面摘要未变，无 I 任务内容 | [95 项](evidence/N06-live-receipt.json)、[原 ID 双向](evidence/N06-original-materials-receipt.json)、[实际迟到 UI](evidence/N06-latest-switch-late-receipt.json) |
| N07 | 同一最终 APK：I/J 两个正向 capabilities 对照，另覆盖坏 CA、错误 SAN、过期、TLS1.0、TLS1.1、HTTPS→HTTP 重定向、HTTP 输入，7/7 拒绝；CA/时间/主机名验证始终开启 | [正向 I](evidence/dedicated-positive-I-native-check.json)、[正向 J](evidence/dedicated-positive-J-native-check.json)、逐例结果内列出全部七项与公开证书指纹 |
| N08 | 已安装客户端 UID 实际探测 31/31：20 项 I/J HTTP、7 个普通端口不可达、4 个操作者另加隧道触及真实管理 TLS 入口但因无客户端证书被拒；结合两端真实监听、容器及挂载实况 | [实际 Android 网络](evidence/N08-android-network-receipt.json)、[控制端](evidence/topology-control.json)、[扫描端](evidence/topology-scan.json) |

N05/N06 均用真实可读报告、证据、草稿及 terminal FAILED 提取 attempt 固定目标；
FAILED 原因是未配置模型，409 为预期准备结果，随后同任务辅助回填继续正常扫描。
每次拒绝后比对完整 JSON 摘要，矩阵不把 404/422/429/503 或传输错误当现存目标通过。
两矩阵并行时每次间隔 1.3s，原 ID 检查间隔 10s，保留生产默认限流。
N07 正向到 capabilities 对话框后主动取消，因此尾部 CANCELLED 不表示 TLS 失败；
最终业务另由 I/J 同包集合主流程验证。旧 TLS1.0/1.1 夹具仍可在显式强制时握手，
[夹具预检](evidence/tls-fixture-preflight.json) 保留原 UTC，不能当 Android 通过证据。

## 实际业务链路与证据边界

专用 Android 模拟器原生选已安装 App、确认 base + 真 feature split，经 HTTPS 上传；
同一任务补入自编研究声明和手动候选，走 PostgreSQL/outbox → Redis/Celery →
扫描发行版 Runner 的真实受限 Docker → Android 原生报告读取及 WebView 政策/API 下钻。
没有新建分析 pipeline、预制报告或 bridge 扫描替身。

[输入与扫描身份](evidence/input-and-scan-identity.json) 从 Android 实际已安装组件计算
指纹，并与服务端包名/version/全部组件/集合指纹相等；夹具源码在
[fixtures](../../../deploy/acceptance/issue132/fixtures/README.md)。静态独立预期固定为
两条 manifest 能力和未被界面调用的 Camera.open 潜在线索。I/J 均实际生成 5 条证据、
1 条政策声明、3 条非空对照，全部 INSUFFICIENT_EVIDENCE、requires_review=true。
清单权限和 invoke 不证明实际采集；声明 polarity UNKNOWN，政策仍
PARTIAL/UNREVIEWED/NOT_CHECKED，JADX 为 UNAVAILABLE_BYTECODE_FALLBACK。

[持久链路读回](evidence/pipeline-ledger.json) 记录 I/J outbox DELIVERED、delivery attempt1、
execution/job SUCCEEDED、attempt1/fence1、事件绑定及结果/Runner 摘要。
[报告下钻投影](evidence/report-drill-projection.json) 将实际原生报告与实际 DOM 摘要关联，
验证政策原文切片 `[25,34)` 恰好等于短原句，claim 链接正确；API 给出 split/DEX/
caller/offset/target。完整政策、报告、DOM 和 APK 只留受保护本机，公开投影仅含摘要、
长度/偏移和自建样本的小段 API 定位。源类型 OFFICIAL_WEB_POLICY 是导入器标签，
本例使用自编研究声明，不是真实官方政策，也没有外部模型质量结论。

## 版本与环境

被测组合主基线为 `798ecf2e1ee65d60dcd5500ab1cb56b05c80cdf1`。
实际 API/Runner/scanner 镜像构建自 `d3c397c8e0b8e8e7586cbc67219ca87d9c495a3b`，
Web/Android 构建自 `0ad5f565dc6f414ac2b9c35661296dc9352e3fef`。
[源码与构建身份](evidence/source-and-build-identity.json) 逐路径记录 Git 对象一致性、
客户端 APK/签名证书、公开 CA 指纹、输入签名、工具链、迁移/规则/契约和来源。
未把实际构建版本改称新提交。镜像使用本地 immutable image ID，未推 registry。

控制端 `PrivacyTrace132-Control` 与扫描端 `PrivacyTrace132-Scan` 是独立 Ubuntu24.04.5
WSL2 根文件系统，ID 分别 `698f31ca623a3881` / `dbb93f153c951951`，独立 Docker
data-root/socket/containerd、net/mount namespace；**共享 WSL 内核**。控制端 14 角色，
扫描端 2 Runner，API/worker 无 socket/扫描盘挂载。Runner 仅使用扫描端本地 socket；
子扫描容器实际 nonroot65534、network none、只读根、drop ALL、no-new-privileges、
1CPU、1GiB memory=swap、pids32，输入只读且退出后移除。不能将两套文件系统称独立内核
或物理 VM；控制角色 inspect 的 memory_swap=-1 原样保留，本票不作 R6 容量结论。

设备为本票专用 LDPlayer14、Android14/API34、x86_64、WebView146.0.7680.119。
系统 fingerprint 来自清理前原始工具回读，清理后从本会话恢复，其“Samsung”字符串
是模拟器自报，不代表 Samsung 真机。日用模拟器未参与。
最终 APK SHA256 `5713eacc19875fe9c61ab5af7a9b9e599b9686224e1f909c7bc726370fee5826`；
仅生成的测试构建在 localhost 增加两轮共四个明确 CA，默认系统信任、明文禁止，
产品跟踪 manifest 未改。补充默认信任构建只证明拒绝旧轮私有 CA，不外推新端点或公网。

## 失败保留、修复与验证

[失败历史](evidence/failures-and-history.json) 分类保留环境、驱动器和验证问题。
旧实验室只有命名空间，没有独立扫描文件系统，不能满足本轮门槛；旧 N08 的 shell
星号扩展可能让 curl 最后 URL 成功掩盖早先失败，旧 19 项结果不计最终分母。
新增本票网络入口修复此探针缺陷，九项回归覆盖假成功、多标记、泄露体、坏 mTLS、
默认设备误用、凭据进入 argv/公开收据与 Windows 字节换行。原产品隔离断言未降低。
冷 cgroup 造成真实 ISOLATION_REJECTED、原生旧缓存 404、并发驱动、早出 UNKNOWN、
清理解析中止、首次 lint 失败均保留独立历史；最终结果有新收据，不覆盖旧文件。

[Linux 完整入口](evidence/linux-authority.json)：`bash scripts/check.sh` 退出0，
API **1567 passed / 179 skipped**、E2E **65 passed**、两次 Ruff、契约无 diff、
Web **111/111**、类型检查及生产构建全部通过。源为主基线加三份新检查器/测试/样例，
各源 SHA 单列；首次仅新增测试导入分组 Ruff I001，修正后完整重跑通过。
本票定向回归28 passed。证据文件另做 JSON 解析、逐字节复制/摘要读回、实际令牌/完整
政策缺失审计。发布提交的精确 head CI 见新 PR 和 Issue 当前记录，不回填进历史收据。

## 清理与交接

[客户端删除](evidence/final-client-cleanup.json) I/J 均明确确认、cleanup_pending=false、
上下文清空；[旧材料检查](evidence/final-task-cleanup.json) 全部404，独立 A 自有材料删除200。
[实验室清理](evidence/final-lab-cleanup.json) 中 active scopes、文档、runtime inputs、
Runner materials、上传、回收 pending 全0，14控制角色+2Runner、项目卷/网、私有 PKI/
扫描工作目录移除，16个本票代理进程停止，八个新回环监听关闭。
[设备清理](evidence/final-device-cleanup.json) 两个本票 app 卸载、6 CA文件与43 UI文件
删除、18个预期 reverse 均不存在、CDP/独有 ADB 关闭，专用模拟器移除，日用实例保留。

新控制/扫描 [daemon 清理](evidence/daemon-control-cleanup.json)、
[扫描 daemon 清理](evidence/daemon-scan-cleanup.json) 后，仅注销
[本票两个发行版](evidence/final-host-cleanup.json)。旧轮本票 systemd/daemon/relay/TLS
服务及回环端口也已[关闭](evidence/legacy-services-cleanup.json)；最后按原调度时点和父子
链核对后关闭了自己创建的[两个 WSL CLI keepalive](evidence/legacy-keepalive-cleanup.json)，
未终止原共享发行版或默认 daemon。只保留忽略目录内的构建缓存和私有原始证据。

本轮证据供 #128 owner 对照最终集成组合复核。没有修改共享总矩阵、关闭 #132/#128、
合并新 PR、发布或生产部署。真机/OEM、独立内核、LAN/公网、外部模型质量、商店审核
与更高并发/容量仍未验证。
