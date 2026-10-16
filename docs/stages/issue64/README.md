# Issue #64：十二场景受控评测

本次为 PT-907/3 新增 **6 项（C07–C12）**，加上逐字节复用的 C01–C06，总计 **12 个源码构建场景、36 行三方案比较**。工程回归、synthetic 理解测试演练和真实 App 均不计入这个分母。原六场景冻结版本未改写。

场景定义、源码、配对自建政策及候选见 [`benchmarks/controlled-v2`](../../../benchmarks/controlled-v2/README.md)。真值先于本版首次算法运行提交冻结，SHA256 为 `0beb0e990c27668658c24341978f871082dc53952affcff1b444d7eb864baeb3`；后续没有按输出调整标签。候选为 agent 辅助整理并核对原句，不声称独立人类签字或自动抽取准确率。

## 实际结果

| 方案 | 全分母 | 状态一致 | 执行失败 | 无目标输出 | INSUFFICIENT_EVIDENCE | 完整 DEX 处理 | 截断 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| permission_keyword | 12 | 2 | 0 | 1 | 0 | 12 | 0 |
| api_flat | 12 | 4 | 0 | 0 | 1 | 12 | 0 |
| privacytrace | 12 | 12 | 0 | 0 | 3 | 12 | 0 |

逐项结果及混淆计数见 [comparison.json](evaluation/comparison.json)，可读表见 [comparison.md](evaluation/comparison.md)。12 份实际预测保存在同目录，包含材料、候选、APK、报告与存储记录的哈希、工具镜像、规则版本、API descriptor/context/caller/DEX/offset、处理限制及非目标发现；`prediction_sha256` 固定每份输出的原始字节。

本系统的三次弃判对应 C01（仅权限）、C06（政策片段／范围未知）和 C10（政策完整但地区范围未知），均符合运行前预期。C12 只将参数未知的调用映射到 LOCATION，另保留精确定位权限的 CAPABILITY 结果；权限基线无法输出该 LOCATION 目标，仍计入 12 项分母。旧 `failures` 汇总列包含这种“无目标输出”，`diagnostics` 另列实际执行失败，不能把它写成程序崩溃。

两种基线沿用原版本的完整描述符、上下文和固定短语词表，材料与本系统相同。C03 的类别声明、C05/C07 的否定、C08 的条件、C09 的第三方主体和 C06/C10 的适用性缺口导致名义状态差异。**C11 还暴露了既有短语表未覆盖“粗略位置”的词汇缺口**；不能把这项差异全归因于语义推理能力。未调整基线词表或政策来追求结果，不主张统计代表性或商业 App 全局召回。

映射／定位核对为 12/12，其中 C01 验证预期没有敏感 invoke，其余 11 项验证实际调用。政策码点区间逐项核对。DEX COMPLETE 只表示枚举和处理完成，不能说明行为全覆盖；报告保留 JADX 不可用时的字节码降级和静态分析限制。五类状态是多类对应关系，未定义二元实际采集／合法性目标，TP/FP/FN 和 P/R/F1 为 N/A；CPU、峰值内存和人工准备成本未测，保留 null。实际耗时保存在运行产物中，不作性能基准。

## 构建、HTTP 与浏览器证据

最终本地运行绑定干净提交 `b0b3c74f5a2f209000d7caaaf3c4a30ecee0776e`，见 [integration-receipt.json](integration-receipt.json)。它已吸收 main 的 PR #61（`e4ba90d`），未修改该 PR 的工具格式。该运行开始后没有修改代码。

两次真实构建的 12 个 APK 字节哈希一致，且与 `artifacts.lock.json` 一致；原六个 APK 的哈希也与旧版本完全相同。工具为 Temurin javac 17.0.20.1、D8 8.6.2-dev、AAPT2 2.19-11948202，官方归档校验和及实际版本输出见两份 build receipt。APK 未安装或动态执行，原件只在忽略目录；扫描和三方案预测均经过受限、断网、只读、非 root 容器。

CLI/HTTP 专项为 **19 passed**，包括全部 12 场景、输入篡改拒绝及同一 APK 经普通入口时保留未知／未核验事实。真实 Chromium 的 [browser-proof.json](browser-proof/browser-proof.json) 覆盖全部 12 场景的受控来源标识、状态、代码定位及原句，页面错误为 0；逐项截图与哈希同目录保存。API 与浏览器使用实际持久化 job，不是手工报告 fixture。

本地权威入口 `PRIVACYTRACE_DOCKER_TESTS=0 bash scripts/check.sh` 已通过：API **775 passed / 21 skipped**，Web **46 passed / 0 skipped**，Ruff、准备包校验、schema 导出零差异、类型与生产构建通过。21 个跳过属于 opt-in Docker／fresh-source 场景，不能写成全量 Docker 回归通过；十二场景及 19 项真实源码专项另行实际执行。当前 Docker Desktop 使用 cgroup v1，既有 cgroup v2 runtime probe 仍受环境限制。**最终 PR 的全量 Docker、原六场景独立离线回放和新增十二场景 CI 另绑定实际交付 head，以 Issue 当前执行记录与 Actions 结果为准**，不用本地旧 SHA 的检查替代。

复现命令：

```bash
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py --suite pt907 --output tmp/pt907-acceptance
bash scripts/check.sh
```

第二条在 CI 自动开启 Docker。Windows 仍可使用既有 Git Bash／PowerShell 权威入口和项目约定的 Linux daemon；本轮本地以 Docker Desktop 的 Linux supervisor 执行相同入口。该 supervisor 有编排权限，实际解析／预测容器没有 Docker socket、标签目录或整个仓库挂载。临时构建依赖、浏览器运行时、job store、APK 和原始日志不提交。

## 失败与边界

首轮实际评测被 daemon 默认 host cgroup namespace 拒绝，12 场景／36 行全部保留为 `ISOLATION_REJECTED`，见 [失败比较](failures/isolation-rejected/comparison.json) 和 [原收据](failures/isolation-rejected/integration-receipt.json)。回归先复现失败，再显式指定 `--cgroupns=private`；原严格 inspect 条件没有放宽。第二轮比较已通过，但 CLI 测试的临时文件位于 supervisor 私有 `/tmp`，daemon 不可见；[原收据](failures/cli-mount/integration-receipt.json) 保留专项失败，随后将测试基目录放在本次唯一输出内，最终 19 项通过。失败轮次属于诊断历史，不代替最终干净提交的证据。

工具准备阶段另遇到 JDK 直连下载失败、旧 builder 不支持 Dockerfile heredoc、非 root 输出目录权限；分别经代理下载同一校验和归档、启用 BuildKit 和本地任务输出权限修正解决。未从这些未完成构建声称产生场景结果。早期全量本机 Docker 检查也因不可见临时路径及 cgroup v2 probe 失败，未记为通过；最终门禁以 PR CI 为准。

本版不覆盖多来源 `POLICY_SOURCE_CONFLICT`、Multidex、动态抓包、运行时采集或外传、新 SDK 能力、真实参与者测试或商业 App 精度。C07 是同一政策内矛盾，不能冒充多来源冲突。本次交付不自动合并、发布或验收父任务 #23；默认 Spec30 六场景离线范围保持原样。

`manifest.json` 可逐文件重算归档 SHA256；其中失败比较保留全样本分母和错误代码，含本机路径的历史原始预测仅留本地，不宣称其原件已公开。最终预测已通过路径排除检查。所有可提交政策均为本任务自建配对文本，真实政策和私有材料没有加入归档。
