# #132：访问隔离与 TLS 验收

2026-10-22 审查修订：**N05–N07 保留原本机 PASSED；N08 为 BLOCKED**。
旧N08只包含设备回环与额外隧道子证据，不能支持完整隔离结论；旧收据及原SHA保留。
新版31项既有子检查成功（含四个内部探针的准确空正文404），但14个真实目标均未建立
无隧道正向路径，因此对应真实拒绝未执行。超时不能当作隔离通过。

当前入口：[审查修订记录](review-20261022.md)、[当前逐例结果](case-results-review-r1.json)、
[当前证据清单](evidence-manifest-review-r1.sha256)。原
[执行记录](execution-20261021.md)/[逐例结果](case-results.json)是ba46f2a历史，N08总结果
已撤回。父票#128最终组合复核独立进行；四例 `final_acceptance_passed=false` 保持。

下文“开发检查”及 NOT_RUN 表格为 **PR #139 当时的历史范围**，原文与子收据状态保留。
新场景结果组合实际 Android、持久链路、全部变体和清理证据，没有回写旧收据。

## 新增实际 Android 网络入口

`deploy/acceptance/issue132/android_network.py` 在明确指定的已安装 debug 客户端 UID 下
运行 Android 自带 curl。先按 [配方](environment-recipe.md) 准备两个可销毁 I/J、
公开 CA、ADB reverse 和四条操作者临时探测隧道，再复制
[配置样例](../../../deploy/acceptance/issue132/network-config.example.json) 到忽略目录。
ADB 可执行文件、显式 serial、I/J 各自任务 capability 仅通过配置指定的环境变量提供。

```powershell
python -m deploy.acceptance.issue132.android_network --config tmp/issue132/network.json --output-dir tmp/issue132/network-first
```

配置必须引用实际inspect/监听绑定清单及SHA，见
[绑定样例](../../../deploy/acceptance/issue132/network-bindings.example.json)；模板不能执行。
覆盖I/J API、DB、broker、Runner、Gateway及两端daemon端口，共14个真实目标。
每项先访问同一IP独立端口的临时真实监听，准确核对200和正文摘要，再检查真实服务拒绝。
直连使用字面IP，无代理、connect-to/resolve或ADB reverse；对照不是TCP代理。

完整59项：20项HTTP、7项设备回环、4条额外管理隧道、14项同IP路由对照、14项真实拒绝。
路径未证明则对应真实拒绝不执行，整体BLOCKED/退出2；真实管理资源可取得则FAILED/退出1；
只有完整成功退出0。回环与临时隧道不能代替直连。本轮45项观察中31项成功、14项路由
未证明，14项真实拒绝未执行。CA/主机名验证保持开启。

curl 使用显式 `--noproxy` 主机列表，避免 `adb shell` 展开星号后出现多 URL 假成功；
HTTP只接受单个状态标记、预期状态、无stderr和准确通用拒绝体；内部路径404必须严格
为空正文，夹带管理信息、JSON或换行均失败。
管理面探测必须收到客户端证书要求的 TLS alert，断连、坏 CA 或协议错误不能算通过。
令牌经 stdin 的 curl 配置传入，不进 argv 或公开收据。

输出目录必须全新；`receipt.json` 为脱敏子收据，`private-responses.json` 只留本机。
执行器不负责删除任务、设备 CA、reverse 或隧道；调用者须另行清理并核验。
其 `scenario_status=NOT_RUN` 是子检查的固定边界，完整案例由逐例结果组合。
定向守卫回归见 `apps/api/tests/test_issue132_android_network.py`，合成返回值不计实际验收。

## PR #139 开发检查历史

本目录仅维护 [#132](https://github.com/MrEcho114/PrivacyTrace/issues/132) 的独立交付。
原 N05–N08 定义见 [原场景](../issue73/scenarios.md)。本交付补齐可运行检查与复用入口，
没有实际 Android / 持久队列 / Runner 全链路验收结论，不改变父票分母。

## HTTP 逐端点检查

`deploy/acceptance/issue132/access_matrix.py` 显式列出 19 个受保护接口：草稿读取/删除、
APK/package-set 上传、政策 fetch、提取预约/状态/执行、候选保存、start、discover、
external import，以及任务状态、报告、证据、复核、取消、重试、删除。

每个端点分别使用缺失材料、损坏 Bearer、错配 Bearer、损坏自定义头、错配自定义头。
共 95 次拒绝检查；前后由 B 所有者读取草稿、提取状态、任务、报告和证据，比较完整 JSON 摘要。
必须先有可读的真实 B 报告/证据。拒绝必须是准确 HTTP 状态与无额外字段的通用错误；
404/422/429/503、代理认证失败、目标变化和传输失败均不能当作通过。
第一个失败即停止；后续请求未执行，不补造结果，不从变化后的目标重新取基线。

执行者先用本票独占的实际客户端和独立 I/J 栈建立任务、确认只针对可销毁且静止的材料。
复制 [配置样例](../../../deploy/acceptance/issue132/config.example.json) 到忽略目录，填入实际
origin、实例 UUID、CA 公钥文件、草稿/任务/来源/证据及 revision。令牌只通过样例指定的
环境变量提供；不写入配置、命令参数、日志或公开收据。脚本验证 live mobile-capabilities
报告 durable 支持且实例身份匹配；HTTPS、证书链和主机名校验保持开启，不跟随重定向。

```powershell
uv run --project apps/api --locked --extra worker python -m deploy.acceptance.issue132.access_matrix --config tmp/issue132/I.json --output tmp/issue132/I-first.json
```

默认每次请求前等待 1.1 秒，保留默认每分钟 60 请求限制；完整运行约 11 分钟。
不要通过增大生产限额绕过限流。任务/提取状态应保持静止；若预约过期或目标发生正常变化，
此轮失败/中止，重新固定夹具后用新输出文件执行，保留旧结果。
只在专属实验室确已配置足够配额时才缩短 `--pause`。

同实例 A→B 形成 N05 的 HTTP 子证据；J 配置中 owner 为 J/B、other 为 I/A 可检查 N06
的已存在目标错配材料拒绝。另须将 I 原始 ID/材料投至 J，并记录不存在目标的拒绝。
脚本不创建/删除任务或环境；结束后由执行者使用各任务自己的材料确认删除与实际资源清理，
在原运行模板补清理记录。隔离有缺陷时探针可能真的删除 B，因此禁止对共享/真实任务运行。

每份新收据有 UTC 时点、源码提交、脚本哈希、逐请求预期/实际、返回体摘要和 B 状态摘要；
写入后读回校验，终端显示整份 SHA256。`subset_status=PASSED` 仅表示 HTTP 子检查完成；
`scenario_status` 保持 NOT_RUN，必须另按原定义完成并核对全部证据才可升级场景状态。
不含目标 ID、政策/报告正文、访问材料或本机私有路径的输出仍需人工审查后才公开。

两种执行器的 JSON 收据都固定以 UTF-8/LF 字节写入，逐字节读回比较后再计算实际字节的
SHA256，避免 Windows 文本换行转换与通用文本读取掩盖 CRLF 差异。读回不一致时不打印摘要。

## 原生组件检查

`verify_native.py` 编译当前 checkout 的既有 Kotlin core 与三个既有测试类，运行
ProbeOperationTest、HttpsHealthCallTest、AnalysisTransportTest：真实回环 TLS 握手、正向
测试信任对照、坏证书/错主机名拒绝、HTTP 输入/降级重定向拒绝、实例凭据作用域及取消旧操作。
HTTP 响应由 MockWebServer 提供；没有实际 Android UI、独立服务实例或真实 APK 扫描。

无需安装 Android SDK。使用 JDK17 和本机已有依赖缓存；脚本不下载/安装依赖、不更改系统信任。
所需 jar 固定名称/版本在脚本 `JARS` 列表，来自对应 Maven 制品；缓存内容的 SHA256 逐个记入收据，
这不是供应链签名认证。缓存不存在则明确失败，不能用缺依赖替身标记通过。

```powershell
uv run --project apps/api --locked --extra worker python -m deploy.acceptance.issue132.verify_native --java java --dependency-cache tmp/jvm-dependencies --output-dir tmp/issue132/native-first
```

输出目录必须全新。原始编译/JUnit 日志只在忽略目录，可能含机器路径，不公开提交。
收据记录实际源文件与依赖摘要、源码提交/dirty、两阶段退出码与日志摘要，并读回校验。

## 自动回归与剩余验收

```powershell
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_issue132_access_matrix.py -q
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_issue132_receipts.py -q
```

这些是受控存储报告的 in-process HTTP 合同回归，权限判断/存储使用真实产品代码。
I/J 使用独立存储/凭据并刻意令 job ID 相同，避免仅凭随机 ID 的 404 冒充实例隔离。
另覆盖 I 原 ID→J、远程 settings/list 禁止、端点清单漂移，以及检查器遇到泄露、错误状态、
状态变化、断连和错误正向夹具必须失败。测试限流配置仅适用于该进程夹具。
草稿 DELETE 只有 durable 服务安装；本地夹具只覆盖其 pre-routing 授权，不能证明真实删除处理。
收据专项只使用受控 HTTP/JVM 返回值验证序列化：覆盖平台默认/模拟 Windows CRLF 写入、
打印摘要与文件实际字节一致、固定 LF 和读回差异拒绝，不构成额外实跑验收。

| 案例 | 本交付开发覆盖 | 完整验收仍需 |
| --- | --- | --- |
| N05 | 19 端点×5凭据变体执行器、受控存储回归及状态对照 | 实际客户端与持久部署全端点结果、真实 B 材料/报告/清理 |
| N06 | 独立存储同 ID/错配材料、原生实例作用域/旧操作组件回归 | 实际 I/J 身份/独立凭据/卷、切换和迟到响应 UI 观察 |
| N07 | 原生组件真实 TLS sockets、正向对照、坏 CA/主机名/HTTP/重定向 | 同一 Android 构建实测全部证书/协议降级变体、证书与 APK/签名身份 |
| N08 | API settings/list 远程拒绝合同 | 实际客户端网络探测 API 探针、DB/broker/Runner/daemon/未公开端口，结合监听/容器实况 |

上述四例在本轮全部保留 NOT_RUN（组件/HTTP 子证据单列），不据 CI 或本 PR 合并升级为 PASSED。
本机未提供可归属本票的 ADB 目标、客户端 APK/签名及独立 durable I/J 组合，外部矩阵未运行。
历史 #126/#127/#137 的源码、收据与 owner 保留；本票不改共享产品源码或父票汇总。
