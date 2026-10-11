# Spec30：六个源码受控场景

验收来源为 [Issue #30](https://github.com/MrEcho114/PrivacyTrace/issues/30)。这里保存自建 Android 源码、配对政策、输入特征、冻结真值和工具链锁；不是商业应用评测数据集。APK 由源码实际编译，未安装或动态执行。

| 场景 | 源码／政策事实 | 冻结目标 |
|---|---|---|
| C01 | 有定位权限，没有敏感 invoke | INSUFFICIENT_EVIDENCE |
| C02 | GPS invoke；精确位置肯定声明 | EXACT_MATCH |
| C03 | 相同 invoke；只声明位置信息类别 | CATEGORY_MATCH |
| C04 | 相同 invoke；完整适用政策未声明定位 | NOT_DECLARED |
| C05 | 相同 invoke；否定精确位置声明 | AMBIGUOUS_DISCLOSURE |
| C06 | 相同 invoke；政策片段、地区未知 | INSUFFICIENT_EVIDENCE |

六场景覆盖五类状态。C02–C06 的 `readLocation` 方法含静态调用，启动界面不执行该方法；C05 不能据此认定违反承诺。COMPLETE 仅指 DEX 枚举与处理完成。

## 可重复构建

在仓库根目录执行。需要 Python/uv、本地 Docker，以及 Windows 上现有的 Ubuntu-24.04 WSL daemon；不切换远端 Docker，不修改全局配置。

```powershell
uv sync --project apps/api --locked --extra worker
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --output tmp/build-a
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --cached --output tmp/build-b
```

首次下载官方 Temurin 17.0.20.1+1、Android API 35 rev2、Build Tools 35.0.0 归档并逐一校验 SHA256；具体 URL/hash 在 `toolchain.lock.json`。Android 构建采用 [javac → D8](https://developer.android.com/tools/d8) 与 [AAPT2](https://developer.android.com/tools/aapt2)，无需 Gradle 或系统 Android 安装。容器离线编译，源码只读，固定 ZIP 排序／时间／属性生成分析用未签名 APK。`build-receipt.json` 记录真实工具输出、源码和六个 APK 哈希。比较两次 receipt 的 `apks` 字段，应均与 `artifacts.lock.json` 一致。归档、APK、镜像和本机路径均留在忽略目录。

`inputs.lock.json` 固定特征和源码；政策 SHA 在特征文件中。`.gitattributes` 保留本目录原始字节，避免换行转换破坏已冻结哈希。更换源码或工具链时建立新评测版本，不能修改这次的真值以迎合结果。

## 分析与公平比较

```powershell
# 单场景入口；不接受 expected/status 标签参数
uv run --project apps/api --locked --extra worker python -m privacytrace.controlled --features benchmarks/controlled/features/C02.json --artifacts tmp/build-a --store-dir tmp/c02/jobs

# 构建既有隔离 worker（Windows；Linux 可直接 docker build）
$taskRoot = (wsl.exe -d Ubuntu-24.04 --exec wslpath -a $PWD.Path).Trim()
wsl.exe -d Ubuntu-24.04 --exec docker build -f "$taskRoot/apps/api/worker.Dockerfile" -t privacytrace-worker:s1 $taskRoot

# 全六场景，先执行 C02/C06；输出目录须不存在
uv run --project apps/api --locked --extra worker python -m privacytrace.benchmark run --artifacts tmp/build-a --output tmp/evaluation
```

单场景命令也需要已构建的 worker。真实解析仍走原有受限扫描入口。仅冻结且经实际构建核对的自建样本可断言已知版本、范围和政策事实；报告标识 `CONTROLLED_APK` / `CONTROLLED_POLICY`。普通 APK CLI 没有此模式参数，仍保留未知地区及 UNREVIEWED/PARTIAL/附件未检查；HTTP 也拒绝将受控政策用于普通 APK 输入。

真值来自场景定义、源码和自建政策，运行前冻结于 `ground-truth.json` / `.sha256`，独立检查过原句与特征。它只在宿主计分器中读取。预测容器仅得到同一份特征材料（权限、API 证据、完整政策、候选声明、已知范围），挂载 API 源码和规则，没有真值目录、既有结果或 Docker socket，网络关闭。三方案在该容器内独立预测；输入哈希由容器重算，规则输出须与 CLI 持久化报告一致。

| 方案 | 使用相同材料中的哪些信息 | 明示限制 |
|---|---|---|
| permission_keyword | 清单权限映射＋完整文本中的精确数据类型短语 | 输出动作始终 CAPABILITY；不检查极性／上位类别／完整性 |
| api_flat | 同一 invoke，完整 descriptor＋context＋rule 映射；相同全文的扁平短语匹配 | 无 invoke 弃判；不检查上位类别／极性／适用性 |
| privacytrace | 既有规则引擎、同一证据及政策候选／范围 | 无标签；静态潜在行为不证明采集、违法或安全 |

每方案分母始终是六个场景目标（C01 为 CAPABILITY，其余为 ACCESS）。权限基线只比较名义状态，不把能力升级为访问证明。18 行保留预期／实际、证据引用、descriptor/context/type/caller/DEX/offset 核对、覆盖、失败、弃判和耗时。总耗时是共享扫描＋报告＋三方案执行，另有各方案计算耗时；不是性能基准。部分覆盖仍留在结果中，不能获得完整六场景通过。P/R/F1 未报告；没有定义二元“实际采集／合法性”真值。

候选是人工整理方式的 agent 辅助注释，逐句核对原文／码点区间，4 条候选，非自动政策理解。独立语义人工签字和人类工时未测量，`human_preparation_seconds=null`，不填成零或伪造团队投入。原始候选审计身份为未认证本地事件。

## HTTP、浏览器与离线包

```powershell
uv run --project apps/api --locked --extra worker python scripts/serve-reports.py --store-dir tmp/evaluation/jobs
# 第二终端
npm ci
npm run build
npm run preview --workspace @privacytrace/web -- --host 127.0.0.1 --port 5173
# 导出仅包含自建报告的只读回放包
uv run --project apps/api --locked --extra worker python scripts/export-offline.py --run tmp/evaluation --output tmp/offline
python tmp/offline/viewer.py --port 8765
```

浏览器分别打开 5173（本地 CLI 已生成报告）和 8765（离线回放）。两者显示不同来源；回放同时显示原分析和打包时间、无 demo／复核写控件。报告不会因打开页面重新扫描。回放只需要 Python 3.11+ 标准库，无 API 服务、Node 或模型密钥；启动时校验精确文件清单及 SHA256，只服务 loopback，拒绝 POST。

实际浏览器验收脚本为 `scripts/verify-browser.cjs`，需要预先安装的 Playwright 1.62.1 和 Chromium；`PLAYWRIGHT_MODULE_PATH` / `PRIVACYTRACE_CHROMIUM` 可指定本机安装。先用 `uv run --project apps/api --locked --extra worker python scripts/prepare-browser-check.py --store-dir tmp/evaluation/jobs --output tmp/browser-jobs` 创建独立作业副本（另含 queued/failed 界面材料），API 改用 `--store-dir tmp/browser-jobs`。启动上述三服务后执行 `node scripts/verify-browser.cjs tmp/browser-proof`。长文本／2000 条候选是界面测试材料，不加入六场景评测集。脚本覆盖代码／原文下钻、分页、390px 视口、异常 HTTP、请求取消与来源切换、防止旧响应覆盖、离线六来源及只读拒绝。

独立断网验收须在线预备 **测试环境** 的 Playwright 1.62.1、Linux Chromium 与系统库，然后运行：

```powershell
# 模块目录含 playwright 与 playwright-core；browser-runtime 是本地 daemon 的 Linux 路径
uv run --project apps/api --locked --extra worker python scripts/verify-offline.py --package tmp/offline --browser-runtime /path/to/chromium-1237 --playwright-modules tmp/browser-test/node_modules --output tmp/offline-proof
```

首轮构建测试镜像，之后可加 `--prepared`。测试镜像记录不可变 image ID，但系统库不是构建工具链锁的一部分。新容器 `--network=none`，只挂载回放包／验证脚本／预备浏览器依赖，无仓库、开发虚拟环境或模型密钥；确认仅 loopback、外网连接失败、六份 HTTP 报告与真正渲染的 Vue 页面，再输出 DOM/hash/浏览器版本存证。准备依赖时联网不算断网验收；未经实际执行不能称通过。

## 授权与证据口径

离线包仅供本任务内部核验。源码许可证尚待团队决定，不自动选择许可证或授权公开分发／正式参赛提交。包内仅自建政策和报告、Vue/Vite 许可证；不包含 APK、真实 App 资料、本地路径、审阅姓名／备注、凭证或依赖二进制。对外发布前另行核对项目与 SDK/JDK 分发条件。

保底真实案例沿用 [GKD 1.12.1 的版本绑定历史核验](../../docs/stages/s1-pr29-real-sample-verification-20261009.md) 与 [接受决定](../../docs/stages/s1-acceptance-20261009.md)。它不进入六场景分母、不进入离线包，不称本次重扫或完整真值。工程回归、受控六场景和历史真实案例分别记录在 [Spec30 验证记录](../../docs/stages/spec30-verification.md)。不合并、部署、公开 Release 或关闭其他工单。
