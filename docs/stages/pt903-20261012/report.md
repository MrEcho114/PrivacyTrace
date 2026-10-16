# PT-903 六场景公平评测与误差报告

2026-10-12（香港时间）。本地待审报告，关联 [#25](https://github.com/MrEcho114/PrivacyTrace/issues/25) 和 [Spec #30](https://github.com/MrEcho114/PrivacyTrace/issues/30)。本文件不发布工单验收完成结论。

## 结果与证据版本

复用合并后 main `323780c9a77d7de2bb1857b1b67b4f05fd94a525` 的实际运行结果，六个源码场景、三方案、18 行全部保留。权限＋关键词、同一 API＋扁平匹配、PrivacyTrace 的状态一致数分别为 **2/6、3/6、6/6**，状态错误数为 **4、3、0**，执行失败数均为 **0**，弃判数为 **0、1、2**。这是冻结目标的名义状态对照，不是实际采集准确率；正确的证据不足结果同时属于状态一致与弃判。

- [原始 comparison.json](evidence/comparison.json)：完整输出文件，字节未改，SHA256 `630b3af1feddf1014f3b738d89c5ee5c2e3810464bffe5389ae67dd101adf8d1`。
- [可复算 results.json](results.json)：每场景输入哈希、18 行引用与派生行摘要、矩阵、计数、计时、环境和未知项。
- [生成的 Markdown 表](tables.md)：全部结果、三份状态混淆矩阵、逐场景计时与执行阶段。
- [原始集成收据](evidence/integration-receipt.json)：同 SHA、dirty_checkout=false、passed=true、11 阶段退出码均为 0。
- [实际运行](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38215788997) / [Artifact 11731418196](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38215788997/artifacts/11731418196)：ZIP SHA256 `cd68b9802b8d0d9fe500991d62cda64cc0179533621836ce9e4a7cd0e820b480`，原始在线 artifact 有效至 2026-10-26 15:09:32（香港时间）。这里保存的允许文本证据不依赖在线 artifact 才能复算。

本轮只审计和整理既有产物，没有重新构建、扫描或运行三方案。证据中的结果生成时点为 2026-10-12T07:08:57.020529+00:00；报告交付提交与上述评测实现 SHA 分开。本目录不替换 `docs/stages/spec30/` 的旧版本收据。

## 冻结目标、计数与公平输入

协议于 2026-10-10T00:39:16.422477+08:00 冻结，[独立真值](https://github.com/MrEcho114/PrivacyTrace/blob/323780c9a77d7de2bb1857b1b67b4f05fd94a525/benchmarks/controlled/ground-truth.json) SHA256 为 `9a0a10392d2d052f95e78c69231c27556120c0eff131a403f05d6f5c8cc10c40`。输入锁 SHA256 为 `32f7a4bbd9a73d261f2d0e2100f31a0b6b38f51ace363841ac06415336295c87`。复算工具逐一核对该提交的 20 项实现/规则指纹、12 项源码/manifest、6 份特征和政策、工具链锁及两份构建收据；不根据实际输出修改标签。

计数单位为“一个场景的一个 PRECISE_LOCATION 目标状态”。C01 的动作是 CAPABILITY，C02–C06 是 ACCESS；每方案分母始终为 6，独立场景总数仍为 6。权限基线只输出 CAPABILITY，原比较器对它比较名义状态，不将权限提升为访问证明。六场景覆盖五类状态；C07 多来源冲突和 C08 Multidex 未测，不扩大分母。

三方案得到同一份 APK 解析证据、权限、完整提供文本、候选声明及适用范围材料。每场景三行 `material_sha256` 一致，`truth_files_absent=true`。原 worker 重算输入材料摘要；无真值目录、既有结果或 Docker socket，断网、只读、非 root。宿主运行前核对冻结摘要，算法只读取特征，执行完后比较器读取预期标签计分。

| 方案 | 实际使用的信息 | 解释边界 |
| --- | --- | --- |
| permission_keyword | 权限映射＋提供全文中的精确数据类型短语 | 不使用 invoke、类别层级、极性和完整性门禁；CAPABILITY 和状态名称为实验基线输出 |
| api_flat | 同一 invoke、完整 descriptor、provider context 与规则映射；相同全文中的精确类型短语 | 无 invoke 时弃判；不处理类别层级、极性和适用性门禁；没有故意削弱 descriptor |
| privacytrace | 相同材料中的既有确定性规则引擎、候选和受控已知事实 | 候选为 agent 辅助人工注释；可选本地备注不是语义签字 |

每行完整输出文件摘要可核验；`results.json` 另列 18 个 `derived_row_sha256`，其规范编码为 UTF-8、JSON `ensure_ascii=False`、排序键、紧凑分隔符。**派生行摘要是本次复算校验值**。CI 的允许上传清单没有保留六份 `Cxx.prediction.json`、完整 job store 或原始 worker stdout，因此其逐文件哈希仍为 null；不能把派生行摘要称为原预测输出哈希。相同材料摘要和原计时来自 runner 的已保存记录，本轮不能重新从缺失的完整材料重建该摘要。

## 逐场景定位、映射与误差分析

C01 源码没有敏感 invoke；C02–C06 的冻结完整目标均为：

```text
Landroid/location/LocationManager;->getLastKnownLocation(Ljava/lang/String;)Landroid/location/Location;
context = {"provider": "gps"}
caller = Lorg/privacytrace/controlled/c0N/MainActivity;->readLocation(Landroid/location/LocationManager;)Landroid/location/Location;
source = classes.dex; offset_bytes = 4
```

`c0N` 对应场景独立 package。实际比较器按完整 descriptor、context、rule、数据类型、caller、DEX 和偏移核对；18 行的 `api_mapping_and_locator_checked` 和 `policy_spans_validated` 均为 true。C01 的 API 数为零，不能将它的“核对通过”写成发现了一次访问。逐行 evidence ID 保留在原 comparison 与派生 JSON；源码引用和原句码点区间也在 JSON 保存。这里复算保存的核对结论与源码定义；完整 job 的定位内容未随 artifact 保留，不能声称本轮重新打开了每份 job。

| 场景 | 原始定义与政策核对 | 实际错误及原因 |
| --- | --- | --- |
| C01 | ACCESS_FINE_LOCATION 权限，无敏感 invoke；肯定原句“我们访问精确位置。”区间 [25,34) | 权限基线 EXACT_MATCH，与冻结证据不足不一致；把权限能力和短语共同当作名义对应。API 基线和本系统保留证据不足 |
| C02 | GPS 静态 invoke；PRECISE_LOCATION / AFFIRMATIVE / HOST_APP / ACCESS，原句 [23,32) | 三方案均 EXACT_MATCH。权限基线动作仍为能力；其状态相同不能证明 API 定位或运行时访问 |
| C03 | 同一 GPS invoke；“本自建测试应用访问位置信息，用于静态规则测试。”[0,23)，声明类型为上位 LOCATION | 两基线 NOT_DECLARED，漏掉类型层级对应；本系统 CATEGORY_MATCH。不能用 API descriptor 错误解释此处误差 |
| C04 | 同一 invoke；政策仅有本地欢迎文字、无附件、无定位声明；自建 package/versionCode 1，scope_known=true、policy_complete=true，候选为空 | 三方案 NOT_DECLARED。完整性事实只适用于该自建政策；此项不测真实政策完整性判定能力 |
| C05 | 同一 invoke；“本自建测试应用不访问精确位置。”[0,15)，NEGATIVE | 两基线 EXACT_MATCH，短语命中忽略否定；本系统 AMBIGUOUS_DISCLOSURE。readLocation 未由欢迎页调用，静态潜在线索不能证明违反承诺 |
| C06 | 同一 invoke；只有政策节选，范围未提供，scope_known=false、policy_complete=false、region=null、UNREVIEWED | 两基线 NOT_DECLARED，缺少适用性与完整性门禁；本系统证据不足。此谨慎结果保留为正确弃判 |

误差归因基于已核对的 [固定算法源码](https://github.com/MrEcho114/PrivacyTrace/blob/323780c9a77d7de2bb1857b1b67b4f05fd94a525/apps/api/src/privacytrace/benchmark_algorithms.py) 与受控输入，不是人类试用反馈。协议没有要求改进基线或进行人工修正后的第二轮实验，本轮不调整算法来追求更高结果。

## 覆盖、失败、partial、弃判与指标适用性

三份矩阵在 [tables.md](tables.md)，行是冻结预期，列是实际输出，另保留 FAILED_OR_NO_STATUS 列。共有 18 行，各方案六行；每份矩阵单独合计为 6。失败不当作 FP，也不算正确弃判。状态一致数含正确证据不足输出；弃判数是成功输出 INSUFFICIENT_EVIDENCE 的数量，与状态错误和运行失败并非互斥分区。

本次保存结果六场景均为 DEX COMPLETE、scanned_dex=[classes.dex]、failed_dex=[]，执行错误列表为空；partial DEX 为 0/6、未知覆盖为 0/6。三方案共享同一次场景扫描，不把 18 行当作 18 次独立扫描。COMPLETE 只表示 DEX 枚举/处理范围完成；反射、动态加载、Native、加壳、Flutter、复杂跨过程行为仍受限。18 行均保留“JADX unavailable or timed out; bytecode evidence retained”，源码片段并非保证可用。C06 的政策不完整与 DEX COMPLETE 是两项不同事实。

本次没有实际失败或 partial 样本；原 runner 对缺失记录、构建/worker 准备失败、APK 摘要失配和 partial 保留全部六场景/三方案记录，actual=null 的失败不冒充弃判或一致。相关失败回归属于工程验证，不能作为本次额外受控评测样本。不能把“负例回归通过”写成此次六场景实验中发生了失败或 partial。

冻结协议列明可测目标为状态一致、弃判、失败、处理覆盖与 elapsed_seconds，`pr_f1` 为 `NOT_REPORTED: no binary collection/legality target`。**本报告 P/R/F1、TP/FP/FN 为 N/A / null**：没有冻结二元实际采集/合法性正类，亦不事后为五状态选择新正类。状态矩阵可直接复算状态一致数，不能由此生成实际采集指标。适用时的公式是 P=TP/(TP+FP)、R=TP/(TP+FN)、F1=2PR/(P+R)，零分母为 N/A；这里不填 0，也不虚构 TP/FP/FN。

完整 job 的报告截断/每份报告长度观测未被允许 artifact 单列保留，因此记未观测；18 行 comparison 本身完整，不宣称全文报告从未截断。UI 的 2000 候选/长文本属于展示用 fixture，不能弥补这一观测缺口，也不能扩充行为覆盖分母。

## 耗时、资源和准备成本

原 runner 使用 `time.perf_counter()` 记录墙钟区间。每场景 `elapsed_seconds` 包含共享隔离扫描、报告生成与三方案执行，它在三行中重复存储，合计时只计一次。六场景共享区间合计 **10.115092093 秒**；外围 runner 六场景阶段为 **11.541916018 秒**。二者边界不同，不将差额虚构为已测的某项开销。

各方案 `scheme_elapsed_seconds` 是同次 worker 内的计算区间；六场景分别合计 **0.000049754、0.000037150、0.001262923 秒**。逐行原始浮点数在原 comparison 保留，展示值按九位小数四舍五入；两次 APK 构建、worker 构建、浏览器与独立断网阶段单列在生成表中。无计时字段的 rebuild-hashes 阶段为未测。这里没有独立性能重复实验、置信区间或跨机器比较，不能据单次微小计时得出性能优势。

没有保存 Docker stats、CPU profiler、RSS 或 I/O 采样：CPU 秒、峰值内存、I/O 字节均为 null / 未测。预测容器 `--memory=256m`、PID32、tmpfs16m 是配置限制，不是资源消耗。已有断网 proof 是环境与观察点证据，不是资源测量。

四条候选由 agent 辅助人工式 fixture 注释，逐句核对原文/码点；并未记录独立人类语义签字。`human_preparation_seconds=null`，不知道人类实际准备工时。构建时间、推定每日工作量和 AI 运行时长不能替代这项成本，也不算作已完成自动政策抽取评测。

环境可核对部分：锁定 Temurin 17.0.20.1+1、Android35 rev2、Build Tools35.0.0、D8 8.6.2-dev、AAPT2 2.19-11948202；Androguard4.1.3、taxonomy0.3.0、SDK规则1.0.0。该专项 workflow 使用 ubuntu-latest 选择器，评测宿主的具体 OS/Python 版本未在本目录收据中单列，保留未知；不能把工程 Check 的宿主版本套给专项。实际浏览器 proof 为 Chromium151.0.7922.34 / Playwright1.62.1；独立回放测试 runtime 为 Python3.12.13-slim 容器，记录不可变镜像 ID与浏览器摘要。这些是既有环境记录，本轮没有安装或升级工具链。

## 工程、受控评测与历史真实案例分列

| 证据类别 | 数量与结果 | 版本与边界 |
| --- | --- | --- |
| 合并后工程 [Check](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38215789511) | API506 passed / 10 skipped；Web46 passed；lint、Schema、类型检查和生产构建通过 | 绑定评测 SHA；直接回读 CI 状态及 Check 日志。跳过项为9项专项执行的源码回归与1项 Windows WSL 前置路径测试，分列说明，不抹掉 skip |
| [Browser Acceptance](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38215788694) | acceptance success；可选 challenger skipped | 同 SHA；challenger 没有执行，不计通过 |
| 受控专项 | 六个源码场景、五类状态、18 行三方案结果；11阶段通过 | 同 SHA。源码回归、8组浏览器观察和独立断网 proof 不增加受控样本数 |
| 交接前补充工程负例 | 41 passed；1条既有 Starlette/httpx 警告 | 引用 [#16 原验收记录](https://github.com/MrEcho114/PrivacyTrace/issues/16#issuecomment-6119990710)，本轮未重跑；不与主 CI 或六场景相加 |
| 历史真实案例 | GKD1.12.1 / versionCode92；6 evidence、3 behavior、2 claim、3 issue；三结果均 INSUFFICIENT_EVIDENCE | 原扫描实现 `bb342843b50dc45aec3df111a51537998c81a632`、2026-10-09 的两次同环境隔离核验；本輪未重扫，不加入六场景或离线包 |

GKD APK SHA256 `edcc03be24bc54d44c04746b46e2e33244120638e2199450b4407195447466a6`；历史语义报告归一化摘要 `19e550c636ddbf805fb1c3f67c7567e1858e8398f384b25d5f0ecda8ef3c2157`。历史政策快照采集于 2026-10-03T12:47:10.664110Z，文本摘要 `bf5917c5c4e9fa2e0700f25db7c17fc0672de0c48de04f6e84e01053871374ea`，提取 PARTIAL、复核 UNREVIEWED、附件 NOT_CHECKED、地区 UNKNOWN。沿用 [历史记录](https://github.com/MrEcho114/PrivacyTrace/blob/323780c9a77d7de2bb1857b1b67b4f05fd94a525/docs/stages/s1-pr29-real-sample-verification-20261009.md) 和 [S1接受决定](https://github.com/MrEcho114/PrivacyTrace/blob/323780c9a77d7de2bb1857b1b67b4f05fd94a525/docs/stages/s1-acceptance-20261009.md)。取消 A/B 流程不代表政策已经核验；不计算商业 App 全局召回，也不声称其政策当前最新。

## 复算与复跑说明

仅复算本目录允许文本，不需要 Docker、网络或 Android 工具。需要已有 Git 对象 `323780c9…`、Python3.11+；完整 clone 已具备该提交。仓库根目录运行：

```powershell
python docs/stages/pt903-20261012/recalculate.py --check
# 在独立输出目录重新生成 JSON 和 Markdown 表，再与保存文件比较
python docs/stages/pt903-20261012/recalculate.py --output-dir tmp/pt903-recalculated
```

脚本固定读取原评测 SHA 的 Git 字节，核对原输出、冻结材料、实现与收据，然后独立从18行计算计数、矩阵和计时；`--check` 逐字节核对 results.json/tables.md，输入摘要失配或缺行时非零退出。当前机器使用已经存在的 `apps/api/.venv/Scripts/python.exe` 执行过生成与 `--check`。本次派生统计不把报告工具自身当作受控 runner，也不再运行被测算法。

如果需要重新构建/扫描，沿用 [固定版本原复现指引](https://github.com/MrEcho114/PrivacyTrace/blob/323780c9a77d7de2bb1857b1b67b4f05fd94a525/benchmarks/controlled/README.md)，并绑定新实际运行 SHA和产物摘要：

```powershell
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --output tmp/build-a
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --cached --output tmp/build-b
# 必须先按原指引构建现有隔离worker，再运行
uv run --project apps/api --locked --extra worker python -m privacytrace.benchmark run --artifacts tmp/build-a --output tmp/evaluation
```

这些是既有命令，不是本轮执行历史。实际重跑需要原 Docker/Windows WSL 条件；本机 Docker daemon/Ubuntu-24.04 不可用的交接事实未被新执行推翻，因此本轮没有声称本机重跑通过。

## 七项验收覆盖与下游边界

| #25 条目 | 本地可审阅成果 | 未测或未保留事实 |
| --- | --- | --- |
| 1 六场景实际运行/哈希/定位 | 同SHA18行原输出、输入锁/特征/政策/APK收据、20项实现摘要、逐行定位与映射核对结论 | 原逐场景prediction文件与完整job未上传；对应哈希未知。派生行摘要已区别标识 |
| 2 冻结与公平材料 | 固定真值、同材料摘要、完整descriptor、输入使用表及原复跑命令 | 不改真值/特征/工具链；本轮不重跑 |
| 3 全分母/混淆/失败/弃判 | 每方案6行，三矩阵、失败独列、partial覆盖与弃判说明 | 当前实际失败/partial为0；负例回归不新增评测样本 |
| 4 P/R/F1适用性 | 冻结可测目标与N/A理由、通用公式、null字段 | 无二元采集/合法性真值；不事后选择正类 |
| 5 耗时/资源/人工 | 共享区间去重、方案区间、阶段计时、资源方法与null、人类成本null | CPU/RSS/I/O、重复性能实验、人类工时均未测 |
| 6 GKD历史案例 | 单列原日期/实现/输入摘要及政策未核验状态 | 未重扫、无全局召回、未加入离线材料 |
| 7 诚实结果/数量分列 | 错误基线、正确弃判和未测项保留；工程/六场景/历史案例分列 | 小样本不作泛化、采集、法律或安全结论 |

是否据这些覆盖正式验收/关闭 #25，留给用户审核。#18 原生依赖仍包含未关闭的 #25；已有独立断网 proof 不能替代当前可交付完整包。artifact 没有上传完整 viewer、manifest及全部回放依赖/报告，后续 #18 仍需实际完整包、清单/包摘要、许可与变更后的同版本验收。

#19 负责人 Onikamicpj 的 [草稿 PR #41](https://github.com/MrEcho114/PrivacyTrace/pull/41) head 为 `42d225deff580f39cb286888f1476893d5f0b7d7`，本轮只读核对其待补项；最终事实审校仍依赖 #18。#30 尚有离线包与材料等剩余范围，不因本报告准备完毕发布总验收完成结论。规则候选 #53 仍 Draft 未合入；本轮按用户指定遵从组长协调决定，没有编辑共享指南/模板或其他负责人分支。

本地目录只新增本任务允许的报告与文本证据，没有APK、真实政策全文、反编译全文、数据库、密钥或个人路径；它是评测报告证据归档，不是 #18 离线交付包，也不授予公开分发或参赛提交许可。
