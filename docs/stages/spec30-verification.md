# Spec30 验证记录（2026-10-11）

[Issue #30](https://github.com/MrEcho114/PrivacyTrace/issues/30) 的六场景保底已完成本地实际验收。结果基于主线 `4b066fecfef7b96b93a3866bef850d9dad7722d0` 整合后的实现，保留 PR34 的 SDK 证据与 PR35 的并发锁修复；每个 API 模块及当前 taxonomy / SDK 规则的执行字节哈希在 [comparison.json](spec30/comparison.json)。交付 commit 与对应远端 CI 另由 PR 绑定，不借用历史 CI。

## 工程检查

执行 `PRIVACYTRACE_DOCKER_TESTS=1 pwsh -NoProfile -File scripts/check.ps1`，由它委托同一 `scripts/check.sh`：API **469 passed**，Web **44 passed**，均无 skip；ruff、契约校验、TypeScript 和生产构建通过。保留一条既有 Starlette/httpx 弃用警告。此前 10/10 及较早主线的检查和报告只是历史运行，不作为这次主线整合的验证。

新增测试经公共 CLI/HTTP 检查标签字段不能作为受控输入、缺失 APK 时 18 行/三组六分母仍保留、普通 APK 输入拒绝 CONTROLLED_POLICY。这些工程用例不计入六场景评测规模。

远端原有浏览器套件发现生成来源说明复用 `.demo-note` 导致唯一选择器冲突，已改为独立 `.report-provenance` 并保留同样外观。最终主线整合后重跑 44 个 Web 测试、类型/生产构建、原有 TC-01～TC-05 实际浏览器套件，以及受控查看和独立断网包验证，均通过；原套件产生的临时截图保留本地，不改写主线历史 evidence。

## 源码构建与冻结输入

三次实际 javac → D8 → AAPT2 构建的六个 APK 哈希全部相同，且与 `artifacts.lock.json` 一致。产物未签名、未安装或执行，仅供静态分析；[构建 receipt](spec30/build-receipt.json) 记录每份源码、APK、官方工具归档哈希及真实版本输出：Temurin 17.0.20.1+1、Android 35 rev2、Build Tools 35.0.0，D8 8.6.2-dev、AAPT2 2.19-11948202。

真值在首轮受控评测前冻结于 `2026-10-10T00:39:16.422477+08:00`，SHA256 `9a0a10392d2d052f95e78c69231c27556120c0eff131a403f05d6f5c8cc10c40`。整合主线没有修改特征、政策、源码或真值。逐句核对的四条候选采用 agent 辅助整理；人类工时未测量，保留 null，没有独立人工语义签字记录，也不声称自动政策抽取准确率。

## 六场景与三方案

10/11 整合后的 runner 先执行 C02/C06，再执行其余四个。实际 APK 经现有受限扫描入口生成报告，三方案读取同一材料；预测环境断网、只读、非 root，仅挂载 API 源码和规则，通过 stdin 收到特征，没有真值/既有结果目录或 Docker socket。容器重算特征材料哈希，现有引擎预测与持久化报告相同。

| 场景 | 冻结目标 | 权限＋关键词 | 同一 API＋扁平匹配 | 现有引擎 |
|---|---|---|---|---|
| C01 | INSUFFICIENT_EVIDENCE | EXACT_MATCH | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE |
| C02 | EXACT_MATCH | EXACT_MATCH | EXACT_MATCH | EXACT_MATCH |
| C03 | CATEGORY_MATCH | NOT_DECLARED | NOT_DECLARED | CATEGORY_MATCH |
| C04 | NOT_DECLARED | NOT_DECLARED | NOT_DECLARED | NOT_DECLARED |
| C05 | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | EXACT_MATCH | AMBIGUOUS_DISCLOSURE |
| C06 | INSUFFICIENT_EVIDENCE | NOT_DECLARED | NOT_DECLARED | INSUFFICIENT_EVIDENCE |

六场景覆盖五类状态。名义状态一致数为 **2/6、3/6、6/6**；失败数均 0，弃判数分别 0、1、2。C01 的目标动作是 CAPABILITY，其余为 ACCESS；权限基线始终只有能力依据，名义 EXACT_MATCH 不升级为访问证明。API 基线无 invoke 时弃判；肯定/否定精确短语都可命中，缺少上位类别及完整性判断，因此 C03/C05/C06 的错误如实保留。

[18 行完整结果](spec30/comparison.json) 保存每场景预期/实际、引用、覆盖、失败与耗时。六份 DEX 均 COMPLETE；完整 descriptor、gps context、规则/类型、场景 caller、classes.dex、offset_bytes=4 和政策原文码点区间均核对。COMPLETE 只表示枚举/处理完成，不代表全面行为检出。耗时包括共享扫描/报告/三方案执行，另记方案计算耗时；不是性能基准。没有 P/R/F1、统计泛化或商业应用全局召回结论。

普通公共 APK CLI 另以相同自建 C02 材料运行边界检查：`input_mode=APK`、`source_origin=REAL_SCAN`、地区 null；政策快照完整性 COMPLETE，但提取 PARTIAL、复核 UNREVIEWED、附件 NOT_CHECKED，两项结果仍 INSUFFICIENT_EVIDENCE。这只是普通入口信任边界检查，不增加真实应用案例数。详见 [验证摘要](spec30/verification-summary.json)。

## 实际浏览器与独立断网验收

[浏览器 proof](spec30/browser-proof.json) 来自 Playwright 1.62.1 / Chromium 152.0.7977.8 的生产页面与实际持久化 HTTP 报告：C02 字节码/原句/完整政策下钻，C06 谨慎结果，合成与受控来源分离；2000 条候选分页、长文本按需展示、HTML 作为文字、390px 无页面横向溢出；HTTP 409 与重试、取消请求、延迟旧响应不覆盖新来源。独立 UI fixture 还验证失败提示、真实取消请求及持久化 CANCELLED，未混入六场景计数。

离线包含六份自建报告与比较结果，12 个清单文件及 manifest；无 APK、真实应用政策、本机路径、备注身份或凭证。标准库 viewer 绑定 loopback，启动校验精确文件清单与哈希；页面明确标注 CONTROLLED_APK 与 OFFLINE REPLAY，显示原分析时间和打包时间，没有 demo/复核写控件，POST 返回 405。用户于 10/11 明确允许六份自建政策 fixture 随源码提交；真实政策仍禁止提交。

[独立离线 proof](spec30/offline-proof.json) 在新容器 `--network=none` 内实际执行：仅 loopback、外网连接失败、六报告 HTTP 成功、真正渲染 Vue 并切换六来源、原分析时间保留、page_errors=[]。仅挂载包、验证脚本、预备浏览器依赖和输出，不挂载仓库、开发虚拟环境或模型密钥。测试依赖预备时联网，独立验收过程断网；交付 viewer 只需 Python 3.11+ 标准库。

包 manifest SHA256：`d5e33fcad27515a1938a558e31d8993089fad828f347163327044a6ee36fb08a`。六份回放报告均保留实际 SDK 规则版本 `1.0.0`。proof 记录不可变测试镜像 ID、验证脚本/浏览器驱动哈希、Playwright 版本，以及实际挂载 Chromium 版本和可执行文件 SHA256。系统库没有冒充构建工具链锁。

最终交付前已将执行目录的 API 文件换行字节与 Git 提交对象对齐，并重新实际运行六场景、普通入口边界、浏览器和独立断网回放，结果不变。验证 JSON 保留原始字节；提交对象中所有实现/receipt 哈希逐一匹配记录，避免 Windows 换行转换破坏版本绑定。

## 真实案例、审查与交付边界

真实案例沿用 [GKD 1.12.1 / versionCode 92 的历史技术核验](s1-pr29-real-sample-verification-20261009.md)，绑定实现 `bb342843b50dc45aec3df111a51537998c81a632`、APK SHA256 `edcc03be24bc54d44c04746b46e2e33244120638e2199450b4407195447466a6`。历史两次扫描与浏览器记录保留原日期、状态、哈希；不称本次重扫或完整真值，不纳入六场景分母或离线包。[10/09 接受决定](s1-acceptance-20261009.md) 撤销团队 A/B 流程，不将政策事实改为已复核。

Standards 与 Spec 两轴由独立只读检查代理检查：建议补原分析时间断言、浏览器版本/哈希存证，两项均已实现并实际重跑通过。主代理复核完整源码/契约/fixture/脚本与材料 diff，没有遗留合并前阻塞项；子代理未执行外部写操作。

包仅供本任务内部核验；源码许可证待团队决定，包带 Vue/Vite 许可证，不授予公开分发或比赛提交权限。本次交付止于任务分支、PR 和绑定 SHA 的 CI，不合并、发布、部署或关闭已有工单。复现命令见 [使用说明](../../benchmarks/controlled/README.md)。
