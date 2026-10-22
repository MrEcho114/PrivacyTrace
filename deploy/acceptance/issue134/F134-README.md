# #134：F 组故障注入执行器（2026-10-22 轮）

本目录的 `f134_common.py` + `f01.py`…`f07.py` 是 F01–F04、F07 的可重复故障驱动。
它们在**已由 owner 创建**的实验室上运行，按实验室状态目录里的随机 Compose 项目名
限定所有破坏性操作；不创建/销毁实验室，不对共享 daemon、WSL、宿主或其它项目执行任何操作。

## 前置

- 一个已 provision 的实验室状态目录（`owner.json` 含 `project`、`instance_id`、`https_port`、
  `images`）。由 `deploy.acceptance.provision` 或等价流程创建。
- 驱动运行在能访问 `docker compose` 和实验室端口的 Linux 控制器中（本机为 WSL root）。
- 客户端测试 CA（web 入口证书由它签发）与源码 checkout 路径。

环境变量（全部有默认值，仅作覆盖）：

| 变量 | 用途 |
| --- | --- |
| `PT_F_LAB_STATE` | 实验室状态目录（含 `owner.json`、`laboratory.json`、`deployment.env`、`ports.yaml`） |
| `PT_F_SOURCE` | 候选源码 checkout（compose 文件与测试夹具来源） |
| `PT_F_CA` | 客户端验证 web 入口的测试 CA |
| `PT_F_EVIDENCE` | 私有证据输出目录 |

## 运行

```bash
# 一个变体
python3 -m deploy.acceptance.issue134.f01 --variant A
# 多个变体（串行，失败继续，各自独立证据）
python3 -m deploy.acceptance.issue134.f03 --variant A --variant B --variant C --variant D
```

变体：

| 模块 | 变体 | 注入 |
| --- | --- | --- |
| `f01` | A / B / C | 停 API 后恢复；未确认 start 响应 + 同 request id 幂等重试；维护窗口停启 API/dispatcher/worker |
| `f02` | A / B / C / D | PENDING×停 publisher / PENDING×停 broker / DELIVERED×停 broker / DELIVERED×停 publisher |
| `f03` | A / B / C / D | worker 租约到期前/后恢复；Runner 扫描中中断；旧 fencing token 不得提交 |
| `f04` | A / B | 同一 event 重复交付；旧尝试在新尝试完成后回报 |
| `f07` | A / B / C / D / E | 扫描超时 / OOM / 硬崩溃孤儿回收 / 角色重建；E（宿主重启）BLOCKED |

## 观测与判定

每个变体写一份 `<case>-<variant>.json`：UTC 时间线、预期/实际、`checks`（参与判定）、
`probes`（非阻塞附加探针，例如容器日志诊断码）、artifacts（报告 SHA256、event 别名）。
状态只允许 PASSED / FAILED / BLOCKED / NOT_RUN；脚本退出码、任务 SUCCEEDED、截图或
哈希本身都不能单独提升案例状态。

内部观察器（SQL / 产品 intake 读取）**不是** Android/Web 客户端请求；客户端证据需单独观察。

## 变体的环境恢复

- `f03`/`f04`/`f07` 通过本实验室 `laboratory.json` 临时覆盖 lease/timeout/runner 镜像，
  `finally` 恢复原文件并重建受影响角色。
- 派生扫描镜像用 `docker commit` 从本实验室 scanner 镜像生成（daemon 无外网，`docker build`
  无法解析本地 image id），打完即用，不推送、不影响其它项目。
- `f07` 的 E（测试主机运行中重启）需要独立内核的可销毁 Linux VM；本机没有满足条件的资源，
  因此**不执行**并记 BLOCKED，不用嵌套 daemon 或共享宿主内核冒充。

## 证据

私有证据目录与 SHA256 清单见执行记录
[`docs/acceptance/issue134/execution-20261022.md`](../../../docs/acceptance/issue134/execution-20261022.md)。
