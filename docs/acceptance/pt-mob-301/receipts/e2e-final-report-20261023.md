# 最新基线全流程端到端验收结论（2026-10-23）

状态：**未全部通过**。按 [提交前最终端到端测试方案](../pre-submission-e2e-plan-20261021.md) 的放行口径（H01–H12、N01–N12、F01–F10、R01–R04 全部变体满足才可写“本机组合按本方案通过”），本轮只完成了 R01–R04 与 F 组大部分、H 组两个最小组合、N 组未执行；失败、阻塞、未执行均不计通过。

本文件是最终结论与缺口索引；逐 lane 的命令、时间线、原始证据和 SHA256 以各 lane 回执为准。本轮未修改产品代码、未合并、未部署、未改 Issue 状态。

## 1. 候选与判据

| 项 | 值 |
| --- | --- |
| 被测基线 | `origin/main` = `83a7983ee6e9bd580dfe41623e06f83c435b9d34`（tree `b3922fa3e808b6c9f6a4f4c19be00e3f3b53652f`；`2026-10-23T00:20Z` 锁定） |
| 基线漂移 | 组织时首次锁定 `a1a6386`；执行中远端前进到 `83a7983`。差异 28 文件：MIT 许可元数据、提交材料文档、`export-schema.py`/`export-offline.py` 说明文字与一处 web 页脚文案；重跑以 `83a7983` 为准，`a1a6386` 的首跑只作漂移对照 |
| 工作分支 / worktree | `codex/e2e-acceptance-20261023` / `.agents/worktrees/codex/e2e-acceptance-20261023` |
| 上一轮已接受组合 | `deccced59d6dec7f442be4ce06b257403794bc46`（#128 于 2026-10-22 收口，接受 7 项缺口） |
| 判据 | 同一基线的实际执行证据；状态只用 `PASSED` / `FAILED` / `BLOCKED` / `NOT_RUN`；旧 SHA 的绿灯不折算 |

基线适用性判定见 [基线影响分析](e2e-baseline-impact-20261023.md)：37 项必须在新基线重跑；可带 SHA 沿用的旧结论仅 3 条（N08 BLOCKED、F07-E BLOCKED、Web 同任务下钻 NOT_RUN）；旧 `PASSED` 折算到本基线 = 0。

## 2. 结果总览

| 组 | 方案要求 | 本轮实际 | 结论 |
| --- | --- | --- | --- |
| R01 权威入口 | `check.sh` + Docker 分支 | 1684 passed / 183 skipped；e2e 65 passed；web 141 passed；构建通过；退出 0 | **PASSED** |
| R02 引擎套件 | spec30 6/6 + pt907 12/12（Linux CI 等价） | 两 suite `integration-receipt passed=true`，`dirty_checkout=false`，场景 6/6、12/12 | **PASSED** |
| R03 Web/移动壳 | browser / frontend / live / mobile 四入口 + 扩展入口 | 13 个入口中 12 PASSED；`acceptance:mobile` **FAILED**（脚本与产品文案漂移，非产品行为失败） | **FAILED（1 项）** |
| R04 部署专项 | R1–R6 | R1 1/1、R2 13/13、R3 1/1、R4 12/12、R5 4/4、R6 9/9 = 40 PASS / 0 FAIL / 0 skip / 0 untested；既有豁免 1 项 | **PASSED（含既有豁免）** |
| F 故障恢复 | F01–F10 十项 | F01 A–C、F02 A–D、F03 A–D、F04 A/B、F07 A–D 共 **17/17 变体 PASSED**；F07-E **BLOCKED**；F08–F10 **NOT_RUN** | **未满足 10/10** |
| H 成功组合 | H01–H12 | 客户端安装/启动冒烟 **PASSED**；H01 **FAILED**（报告缺政策原句区间，`policy_comparison=UNKNOWN`）；H04/H07/H10 **NOT_RUN**；其余 H 项 **NOT_RUN** | **未满足 12/12** |
| N 负向场景 | N01–N12 | 本轮 **未执行**（旧收据绑定旧 SHA，不适用） | **未满足 12/12** |

## 3. 逐项明细

### 3.1 R01（回执：[e2e-r01-20261023.md](e2e-r01-20261023.md)）

- 命令：`PRIVACYTRACE_DOCKER_TESTS=1 PRIVACYTRACE_E2E_JOB_BUDGET_SECONDS=300 bash scripts/check.sh`，独立 worktree 执行，UTC `00:39:18Z → 00:57:30Z`，退出 0。
- 实际：Docker worker 镜像构建成功（`privacytrace-worker:s1`，ID `0467cd9d6b57`）；`pytest apps/api/tests` **1684 passed / 183 skipped / 13 warnings**（616 s）；`tests/e2e` 65 passed；Ruff 两处全过；schema 导出无差异；web 单测 141/141；生产构建通过；最终 `PrivacyTrace checks passed.`
- 183 skipped 的原因分布已单独回读：130 条需显式一次性 PostgreSQL runtime/migration URL，3 条需 fresh controlled source build，1 条 Linux-only Runner，1 条 Redis/Celery opt-in，1 条缺 runtime extra；**skipped 不计通过**，其覆盖缺口由 R04/F 组分别承担。
- 完整日志 `tmp/e2e/20261023/r01/check-83a7983.log`（sha256 `9E364D82…FD9B`）、跳过原因 `api-tests-skip-reasons.log`（`A098A126…7AFD`）。

### 3.2 R02（回执：[e2e-engine-suite-20261023.md](e2e-engine-suite-20261023.md)）

- 权威执行在 WSL Linux（CI 等价，非 root 用户），`83a7983` 干净 clone；spec30 `00:52:03Z → 00:55:06Z`（183 s，12/12 stage 退出 0），pt907 `00:55:38Z → 00:59:05Z`（207 s，9/9 stage 退出 0）。
- `integration-receipt.json`：spec30 `passed=true`、`scenario_count=6`；pt907 `passed=true`、`scenario_count=12`；`commit_sha=83a7983…`、`dirty_checkout=false`。三方案对比：`privacytrace` 方案 spec30 6/6、pt907 12/12 一致；`execution_failures=0`，`coverage.status=COMPLETE`。
- 首跑（Windows 宿主）在 `independent-offline` 阶段失败：`scripts/verify-offline.py:30` 要求 `browser_runtime.startswith("/")`，Windows 绝对路径 `C:\…` 永不满足——这是工具可移植性缺陷（CI 为 Linux），不是产品行为失败；首跑证据保留，权威结论取 WSL Linux。

### 3.3 R03（回执：[e2e-web-shell-20261023.md](e2e-web-shell-20261023.md)）

- 组合 B（`83a7983`）13 个入口：round2-primitives、brand-assets、reading、hierarchy、motion、frontend、browser、design、preview、standalone-round2、standalone-a11y、live **PASSED**；`acceptance:mobile` **FAILED**。
- FAILED 原因：执行器仍在找已改名的产品文案（`恢复当前实例材料`×4、`设置模型配置`×1、`自动准备政策并继续`×4，共 3 个标签 9 处选择器；产品 `MobileApp.vue:275/:310`、`ImportPage.vue:112` 已改名），4 个场景各 30 s 超时。补充复跑只用 `tmp/` 副本改选择器，仅作判定依据，**不构成官方 PASSED**。
- 顺带发现门禁覆盖缺口：`browser-acceptance.yml` 未跑 `acceptance:mobile`、`verify-frontend-round2`、`verify-issue145-a11y`、`verify-round2-primitives`、`verify-brand-assets`，所以漂移长期未被发现。
- 证据：`tmp/e2e/20261023/web-b/`（339 文件，manifest sha256 `aaa58f82…0656e`）。

### 3.4 R04（回执：[e2e-deploy-20261023.md](e2e-deploy-20261023.md)）

- WSL root 干净 clone（`83a7983`，`status --porcelain` 空），`bash deploy/check_acceptance.sh` 正式跑 `00:41:18Z → 00:59:40Z`（18 分 22 秒）。
- 收据：R1 `r1-full-deployment` 1/1、R2 `r2-dual-scope-business-loop` 13/13、R3 `r3-actual-isolation` 1/1、R4 `r4-fault-injection-recovery` 12/12、R5 `r5-backup-recovery-drills` 4/4、R6 `r6-capacity-and-secret-audit` 9/9；合计 **40 PASS / 0 FAIL / 0 SKIP / 0 NOT_TESTED**，`pass_rate_of_verified=1.0`，`untested_scopes=0`。
- 既有豁免：`dedicated-scan-host-verification` = `WAIVED_BY_USER`（独立扫描主机/VM 分离与跨主机防火墙持久化），不计 PASS、生产要求不变；WSL 共用内核，**不是**独立扫描主机。
- 正式跑前两次中止均为环境问题（死代理/重启 dockerd），首跑日志保留、不计产品结果。

### 3.5 F 组（回执：[e2e-faults-20261023.md](e2e-faults-20261023.md)）

- 基线 `83a7983`，`git archive` 私有构建上下文；私用镜像 `e2e-f-{api,web,runner,scanner}:83a7983`（revision 标签实测为基线 SHA）；实验室 `pt81-d588f714f6e3`（UUID `735badcf…`，HTTPS `127.0.0.1:48271`）。
- 逐变体：F01 A–C、F02 A–D、F03 A–D、F04 A/B、F07 A–D **17/17 PASSED**（真实 HTTP 入口、PostgreSQL outbox/执行台账、真实 broker、受限 Runner）。
- F07-E（宿主运行中重启）**BLOCKED**：本机无独立可销毁内核的 Linux VM，未用嵌套 daemon 冒充。F08/F09/F10 **NOT_RUN**：drill 是 R5/R6 收集器库函数，需 `check_acceptance.sh` 两实验室 harness；F10 另缺 `PT_ACCEPTANCE_PREVIOUS_API_IMAGE`。
- 清理：`down --purge` 回读本实验室 0 容器 / 0 卷 / 0 网络、状态目录已删、0 自有扫描器、Runner RUNNING 操作 0；未做全局 prune/重启共享 daemon。
- 实验室级适配（不改产品代码，均有备份与指纹）：补 `localhost` Caddy 站点与证书 SAN；`f134_common.Client` 默认 `Host: localhost` 与基线 `ALLOWED_HOSTS=PT_PUBLIC_HOST` 冲突，用包装器改发 `privacytrace.test`。这两条作为执行器/实验室交接项记录。

### 3.6 H 组（回执：[e2e-mobile-h-20261023.md](e2e-mobile-h-20261023.md)）

- 客户端 APK：本基线源码构建（`83a7983`，debug，x86_64，含 #73 测试 CA 的 debug overlay），sha256 `CD33C6EC12E4B5BDB7F1FB40AD02F9D2AA1CEB1863CA971BE1329F04E51A345A`；嵌入本基线 web 产物。构建与 CA overlay 细节见 [APK 回执](e2e-apk-build-20261023.md) 附录。
- **客户端安装/启动冒烟：PASSED**——`install -r` 成功、冷启动 COLD 481 ms、前台 `MainActivity`、进程存活、首屏截图、设备回拉 APK sha256 与构建产物一致。
- **H01（单包 / 自动政策）：FAILED**。真实客户端确实走完「选包 → 原生确认上传 → 受控政策源抓取（6 次命中 200/472 B，正文 sha256 `2d9a31a5…`）→ 真实 Docker 扫描 → `REAL_SCAN` 报告（扫描行 `base:classes.dex、base:classes2.dex`）→ 证据下钻 → 原生两步删除（回读“服务器已确认删除。”）」。但报告始终没有政策原句/区间：受控抽取器已回应 2 条逐字候选、客户端 2/2 保存为已检查，报告仍只给「有政策快照 · 对应条款未确认」，`policy_comparison=UNKNOWN`、`quote_offsets=false`。按判据「至少实际核对一处政策原句区间」不能记 PASSED。
- 根因未定位到产品缺陷：需对照实验区分「受控 mock 返回字段不足」与「`83a7983` 候选→报告映射变化」；回执只记录事实，不写产品缺陷结论。
- **H04 / H07 / H10：NOT_RUN**（时间盒内未启动，不据 H01 推算）；**H02/H03/H05/H06/H08/H09/H11/H12：NOT_RUN**（分别需要网页辅助/模型接收器/自托管实例等，未在本轮执行）。
- 实验室 `pt81-37f9ad2004be`（实例 `3b55e180…`，HTTPS 51707）；镜像 `e2e-h-{api,web,runner,scanner}:83a7983`；政策源、DNAT、设备 reverse 与实验室均按归属清理并回读（DNAT 0、容器/网络/卷全空、VM4 已关机、未触碰 fault-lane 实验室）。
- 首跑 `SERVER_RESPONSE_INVALID` 已定位为部署 `Host` 头问题（`PT_PUBLIC_HOST=privacytrace.test` vs 客户端 `Host: localhost`，API 返回 400/空 200），只改本实验室 state 后用 #73 CA 重签叶证书修复；首跑证据保留。执行器与新 UI 的 4 处文案漂移在 `tmp` 副本中适配，仓库执行器未改。

### 3.8 逐项状态矩阵（本轮）

| 组 | 编号 | 状态 | 说明 |
| --- | --- | --- | --- |
| R | R01 | PASSED | 权威入口 + Docker 分支 |
| R | R02 | PASSED | spec30 6/6 + pt907 12/12（WSL Linux CI 等价） |
| R | R03 | **FAILED** | 12/13 入口 PASSED；`acceptance:mobile` FAILED（测试文案漂移） |
| R | R04 | PASSED | 40/40 + 既有扫描主机豁免（不计 PASS） |
| F | F01 | PASSED | A/B/C |
| F | F02 | PASSED | A/B/C/D |
| F | F03 | PASSED | A/B/C/D |
| F | F04 | PASSED | A/B |
| F | F05 | NOT_RUN | 需真实客户端取消/删除注入；旧收据绑定 2626152，不折算 |
| F | F06 | NOT_RUN | 同上 |
| F | F07 | **部分** | A–D PASSED；E（宿主重启）BLOCKED（无独立内核 VM） |
| F | F08 | NOT_RUN | 需 `check_acceptance.sh` 两实验室 harness |
| F | F09 | NOT_RUN | 同上 |
| F | F10 | NOT_RUN | 同上 + 缺上一基线 API 镜像 |
| H | H01 | **FAILED** | 主链走通但缺政策原句区间（`policy_comparison=UNKNOWN`） |
| H | H02/H03/H05/H06/H08/H09/H11/H12 | NOT_RUN | 需网页辅助/模型接收器/自托管实例，本轮未执行 |
| H | H04/H07/H10 | NOT_RUN | 时间盒内未启动 |
| N | N01–N12 | NOT_RUN | 本轮未执行；旧收据绑定 ffadeb0/2626152，不适用于本基线 |

> H/N 的 34 个场景本轮没有一个记 `PASSED`；H01 已证明客户端主链可真实运行，但判据要求的政策原句区间缺失。任何“基本可用”“主链已通”的表述都不替代上表状态。

### 3.7 N 组

本轮**未执行**。N01–N12 需要真实客户端 + 双实例/证书/网络/取消删除等注入，且旧收据绑定 `ffadeb0`/`2626152` 等旧 SHA；按基线影响分析不能折算到 `83a7983`。本轮只完成了其中 N12/F05/F06 之外的服务端故障链（F 组）。状态：**NOT_RUN（11 项）+ 无 BLOCKED 豁免**；具体缺什么见 §5。

## 4. 本轮验收发现（缺陷/差距台账）

| # | 类别 | 发现 | 证据 | 影响 |
| --- | --- | --- | --- | --- |
| 1 | 仓库/构建 | `npm run android:prepare` 在 Tauri CLI 2.12.3 模板上失败：`apply-brand-android-icons` 要求 `mipmap-anydpi-v26/ic_launcher.xml`，生成树没有该目录；本次 APK 用默认启动图标 | [APK 回执](e2e-apk-build-20261023.md) GAP-1 | 交付观感，不影响功能 |
| 2 | 测试漂移 | `acceptance:mobile` 与产品文案漂移（3 标签/9 选择器），4 场景超时 | [R03 回执](e2e-web-shell-20261023.md) §5 | R03 记 FAILED；需测试维护 |
| 3 | CI 覆盖 | `browser-acceptance.yml` 未覆盖 `acceptance:mobile`、round2、a11y、primitives、brand-assets | 同上 §6.1 | 漂移长期未发现 |
| 4 | 工具可移植性 | `verify-offline.py` 要求 POSIX 绝对路径，Windows 宿主无法收 PASSED | [R02 回执](e2e-engine-suite-20261023.md) 第 5 节 | Windows 本地 R02 需改用 WSL |
| 5 | 执行器/实验室 | `f134_common.Client` 默认 Host 与 `ALLOWED_HOSTS` 冲突；`provision.py` Caddyfile 缺 localhost 站点/SAN | [F 回执](e2e-faults-20261023.md) §1/§10 | 已用实验室级修复绕过，建议回归执行器 |
| 6 | 材料 | #256 回退 6 个 PR 的交付材料（deck、90s 视频、AI/第三方披露、PT-906 阶段材料）；`apps/` 仅 3 文件 6 行文案/注释/测试 | [基线影响分析](e2e-baseline-impact-20261023.md) | 非 E2E 门禁，但影响提交包完整性 |

环境类（不计产品缺陷）：WSL Docker 死代理 + MTU 1500/1280 + registry 直连不可达；Windows 缺 JDK/SDK/Rust，子代理恢复工具链后以 MinGW host linker 完成构建（GAP-2，MSVC 字节可复现性未建立）。

## 5. 需用户决定

1. **是否接受本轮结论**：R01/R02/R04 PASSED、R03 一项 FAILED（测试漂移）、F 17/17 变体 PASSED 但 F07-E/F08–F10 未完成、H 仅最小组合、N 未执行。按原方案门禁，本轮**不能**写“按方案通过”。
2. **H/N 是否另开补跑窗口**：完整 H01–H12 需要两套实例 + 受控政策源 + 模型接收器；N01–N12 需要真实设备注入矩阵。以本次已验证的 APK/实验室/执行器基础，预计仍需 1–2 个工作日；本机当前无独立扫描主机/独立内核 VM。
3. **H12（旧组合已 FAILED）**：是否单开缺陷票（I/J × splits × model 对照事实已在旧收据）。
4. **测试维护授权**：是否允许修复 `acceptance:mobile` 选择器与 CI 覆盖缺口（测试/CI only 的 PR；本轮未改）。
5. **#256 材料缺口**：deck/视频/AI/第三方披露材料是否恢复或另发。
6. **合并/发布**：仍按各自独立授权；本轮验收结论不构成合并或发布。

## 6. 证据索引

| 内容 | 位置 |
| --- | --- |
| 协调入口与 lane 索引 | [e2e-latest-baseline-20261023.md](e2e-latest-baseline-20261023.md) |
| R01 / R02 / R03 / R04 / F / APK / 基线影响 | 本目录 `e2e-*.md` |
| 原始证据（不提交） | `tmp/e2e/20261023/{r01,web,web-b,spec30-run3,pt907,deploy,faults,h,apk}/` |
| 旧收据（历史，仅按 SHA 引用） | `docs/acceptance/h-matrix-final-20261022.md`、`issue133/execution-20261022.md`、`issue134/execution-20261022.md`、`issue136/h-mainline-final-20261022.md`、`frontend-round2/20261022.md` |
