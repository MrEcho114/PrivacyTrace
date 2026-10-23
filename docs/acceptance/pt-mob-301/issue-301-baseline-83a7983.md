<!-- privacytrace-e2e-acceptance-record:20261023:83a7983 -->

> 关联父票：[#128](https://github.com/MrEcho114/PrivacyTrace/issues/128)（已关闭；2026-10-22 以 `deccced` 组合收口并接受 7 项缺口）
> 方案依据：[`docs/pre-submission-e2e-plan-20261021.md`](docs/pre-submission-e2e-plan-20261021.md)
> 验证基线：`origin/main` = `83a7983ee6e9bd580dfe41623e06f83c435b9d34`（tree `b3922fa3e808b6c9f6a4f4c19be00e3f3b53652f`，2026-10-23T00:20Z 锁定）
> 同主题的另一条记录：[#291](https://github.com/MrEcho114/PrivacyTrace/issues/291)（基线 `682ca54`，另一执行会话；组合不同，本记录**不替代、不改写**它）

- **PT task ID**：PT-MOB-301-E2E / `83a7983`

## 任务目标 (Goal)

在最新 `main` 基线上重新组织并执行完整端到端验收（R01–R04、F 组、H/N 手机组合），以同一基线的实际执行证据判定是否可以写“本机组合按方案通过”，并如实登记失败、阻塞、未执行项与交付缺口。本轮不修改产品代码、不合并、不部署。

## Input, output and scope

**输入**
- 基线：`83a7983`；组织时首次锁定 `a1a6386`，执行中远端前进到 `83a7983`（差异 28 文件：MIT 许可元数据、提交材料文档、`export-schema.py`/`export-offline.py` 说明文字、一处 web 页脚文案），重跑以 `83a7983` 为准。
- 方案与判据：`docs/pre-submission-e2e-plan-20261021.md`（H 12/12、N 12/12、F 10/10、R01–R04；`PASSED`/`FAILED`/`BLOCKED`/`NOT_RUN`）。
- 本机环境：Windows 20 核 / 31.6 GB + WSL `Ubuntu-24.04` Docker `29.7.2`；MuMu Player 12（VM 3/4/5）；客户端工具链在本轮恢复（JDK 17 / Android SDK 36 / Rust 1.99.1 + MinGW host linker）。

**输出（本地分支，未 push）**
- 分支 / worktree：`codex/e2e-acceptance-20261023` / `.agents/worktrees/codex/e2e-acceptance-20261023`，提交 `41d5019cf1720151d5b98d08ba575694d8b14c77`。
- 回执（`docs/acceptance/e2e-*.md`，10 份）：最终结论、协调入口、R01/R02/R03/R04、F、H、APK 构建、基线影响分析。
- 原始证据（`tmp/e2e/20261023/{r01,web,web-b,spec30-run3,pt907,deploy,faults,h,apk}/`，不进 Git）。

**范围**
- R01 权威入口（含真实 Docker worker 构建）、R02 spec30 + pt907（源码重复构建/隔离扫描/CLI/HTTP/浏览器/独立断网回放）、R03 Web 与移动壳验收入口、R04 部署专项 R1–R6、F01–F04/F07 故障链变体、H 组最小真机组合（H01/H04）与客户端安装冒烟。

## 范围外事项 (Out of scope)

- H02/H03/H05–H12、N01–N12 的完整矩阵（本轮未执行，状态 `NOT_RUN`，不折算、不推算）。
- F05/F06（真实客户端取消/删除）、F08–F10（需 `check_acceptance.sh` 两实验室 harness，F10 另缺上一基线 API 镜像）。
- 公网 DNS/ACME、商店审核、外部模型质量、真机/其它 ABI、独立扫描主机（WSL 共用内核，既有豁免不升级为 PASS）。
- 合并、发布、部署与 Issue 关闭；本记录不修改 #128/#291 的既有结论。

## 关联 Spec / ADR

- [#128 提交前最终验收：并行协作与交付收口](https://github.com/MrEcho114/PrivacyTrace/issues/128)（已关闭）
- [`docs/adr/0004-client-is-android-app.md`](docs/adr/0004-client-is-android-app.md)（客户端定义）
- [`docs/pre-submission-e2e-plan-20261021.md`](docs/pre-submission-e2e-plan-20261021.md)（矩阵与放行口径）
- [`docs/agents/local-environment.md`](docs/agents/local-environment.md)（本机环境假失败与恢复）

## 当前执行记录（Agent 维护）

- 执行方式：Team Lead + 4 个 durable teammate（web-shell / engine-suite / deploy-gate / fault-lane / mobile-h 共 5 条 lane）+ 2 个只读子代理（基线影响分析、Android 工具链恢复）；lane 证据目录互不重叠。
- 执行时间（UTC）：`2026-10-23T00:10Z` 组织 → `2026-10-23T03:10Z` 收口；本地提交 `41d5019`。
- 环境修复（均非产品代码）：WSL Docker 死代理（daemon + 两处 CLI 配置）、MTU 1280、docker.io 镜像源、`iptables -P FORWARD ACCEPT`；恢复 JDK/SDK/Rust 工具链。
- 判定：**未全部通过**（详见下表）。

## 阻塞依赖 (Blockers)

- 无阻断本轮 R/F 执行的外部阻塞。
- 未完成项的真实前置：H/N 完整矩阵需要两套独立实例 + 受控政策源 + 模型接收器 + 设备注入矩阵；F07-E 需要独立可销毁内核的 Linux VM；F08–F10 需要 `check_acceptance.sh` 两实验室 harness。

## Acceptance criteria and evidence

### 结果总览

| 组 | 方案要求 | 本轮实际 | 状态 |
| --- | --- | --- | --- |
| R01 权威入口 | `check.sh` + Docker 分支 | 1684 passed / 183 skipped；e2e 65 passed；web 141 passed；构建通过；退出 0 | **PASSED** |
| R02 引擎套件 | spec30 6/6 + pt907 12/12 | 两 suite `integration-receipt passed=true`、`dirty_checkout=false`，场景 6/6、12/12 | **PASSED** |
| R03 Web/移动壳 | browser / frontend / live / mobile + 扩展入口 | 13 入口中 12 PASSED；`acceptance:mobile` FAILED（测试文案漂移，非产品行为失败） | **FAILED（1 项）** |
| R04 部署专项 | R1–R6 | 40 PASS / 0 FAIL / 0 skip / 0 untested；既有豁免 1 项 | **PASSED（含既有豁免）** |
| F 故障恢复 | F01–F10 十项 | F01–F04、F07 A–D 共 17/17 变体 PASSED；F07-E BLOCKED；F08–F10 NOT_RUN | **未满足 10/10** |
| H 成功组合 | H01–H12 | 客户端安装/启动冒烟 PASSED；H01 FAILED（缺政策原句区间）；H04/H07/H10 及其余 NOT_RUN | **未满足 12/12** |
| N 负向场景 | N01–N12 | 本轮未执行；旧收据绑定旧 SHA，不折算 | **未满足 12/12** |

### 关键明细

- **R01**：Docker worker 镜像 `privacytrace-worker:s1`（ID `0467cd9d6b57`）；API 套件 1684 passed / 183 skipped（130 条需显式一次性 PostgreSQL runtime/migration URL 等，已逐类回读，skipped 不计通过）；e2e 65 passed；Ruff 两处通过；schema 导出无差异；web 141/141；生产构建通过；`PrivacyTrace checks passed.`。完整日志 `tmp/e2e/20261023/r01/check-83a7983.log`（sha256 `9E364D82E693201A82C9F9571099D26E4247BC161D4DF89F1D61FA2C525EFD9B`）。
- **R02**：WSL Linux（非 root）干净 clone；spec30 `00:52:03Z→00:55:06Z`（183 s，12/12 stage），pt907 `00:55:38Z→00:59:05Z`（207 s，9/9 stage）；`commit_sha=83a7983…`；`privacytrace` 方案 spec30 6/6、pt907 12/12 与预期一致，`execution_failures=0`。Windows 首跑在 `independent-offline` 因 `verify-offline.py:30` 要求 POSIX 绝对路径失败（工具可移植性缺陷，非产品失败）。
- **R03**：12 个入口 PASSED（round2-primitives、brand-assets、reading、hierarchy、motion、frontend、browser、design、preview、standalone-round2、standalone-a11y、live）；`acceptance:mobile` FAILED，执行器仍在找已改名的产品文案（3 个标签 9 处选择器；4 场景各 30 s 超时）。补充复跑只用 `tmp/` 副本改选择器，不构成官方 PASSED。
- **R04**：`bash deploy/check_acceptance.sh` 正式跑 `00:41:18Z→00:59:40Z`（18 分 22 秒）；R1 1/1、R2 13/13、R3 1/1、R4 12/12、R5 4/4、R6 9/9；`conclusion=ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER`；豁免 `dedicated-scan-host-verification` = `WAIVED_BY_USER`，不计 PASS、生产要求不变。
- **F 组**：镜像 `e2e-f-{api,web,runner,scanner}:83a7983`（revision 标签实测为基线 SHA）；实验室 `pt81-d588f714f6e3`（UUID `735badcf…`，HTTPS `48271`）；17/17 变体 PASSED；F07-E BLOCKED（无独立内核 VM）；F08–F10 NOT_RUN（缺失前置见 Blockers）。清理回读：本实验室 0 容器/0 卷/0 网络、状态目录已删、0 自有扫描器。
- **H 组**：APK `tmp/e2e/20261023/apk/privacytrace-mobile-83a7983-local-ca-x86_64-debug.apk`，sha256 `CD33C6EC12E4B5BDB7F1FB40AD02F9D2AA1CEB1863CA971BE1329F04E51A345A`（debug/x86_64，含 #73 测试 CA debug overlay，嵌入本基线 web 产物）。冒烟 PASSED（install -r、COLD 481 ms、前台 MainActivity、进程存活、首屏截图、回拉哈希一致）。H01 走通「选包→原生确认上传→受控政策源抓取→真实 Docker 扫描→REAL_SCAN 报告→证据下钻→原生两步删除」，但报告无政策原句/区间（`policy_comparison=UNKNOWN`、`quote_offsets=false`），按判据 FAILED；根因未定位到产品缺陷（受控抽取器字段 vs 候选→报告映射差异待对照实验）。
- **N 组**：未执行；理由与旧证据适用性见基线影响分析（旧 `PASSED` 折算本基线 = 0）。

### 本轮验收发现（缺陷/差距台账）

| # | 类别 | 发现 | 影响 |
| --- | --- | --- | --- |
| 1 | 仓库/构建 | `npm run android:prepare` 在 Tauri CLI 2.12.3 模板上失败（`apply-brand-android-icons` 要求不存在的 `mipmap-anydpi-v26/ic_launcher.xml`） | 品牌启动图标未叠加，不影响功能 |
| 2 | 测试漂移 | `acceptance:mobile` 9 处选择器仍找旧文案（恢复当前实例材料/设置模型配置/自动准备政策并继续等） | R03 记 FAILED；需测试维护 |
| 3 | CI 覆盖 | `browser-acceptance.yml` 未覆盖 `acceptance:mobile`、round2、a11y、primitives、brand-assets | 漂移长期未被发现 |
| 4 | 工具可移植性 | `verify-offline.py` 要求 POSIX 绝对路径，Windows 宿主无法收 PASSED | Windows 本地 R02 需走 WSL |
| 5 | 执行器/实验室 | `f134_common.Client` 默认 `Host: localhost` 与 `ALLOWED_HOSTS=PT_PUBLIC_HOST` 冲突；`provision.py` Caddyfile 缺 localhost 站点/SAN | 已用实验室级修复绕过，建议回归执行器 |
| 6 | 材料 | #256 回退了 deck、90s 视频、AI/第三方披露、PT-906 阶段材料（`apps/` 仅 3 文件 6 行文案/注释/测试） | 非 E2E 门禁，但影响提交包完整性 |

## Validation plan

```bash
# R01（独立 worktree，避免 npm ci 干扰其他 lane）
PRIVACYTRACE_DOCKER_TESTS=1 PRIVACYTRACE_E2E_JOB_BUDGET_SECONDS=300 bash scripts/check.sh

# R02（WSL Linux，CI 等价；--playwright-modules 指向 tmp/spec30-browser/node_modules）
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py --suite spec30 --output <out> --playwright-modules <modules>
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py --suite pt907  --output <out> --playwright-modules <modules>

# R03
npm run acceptance:browser && npm run acceptance:frontend && npm run acceptance:live && npm run acceptance:mobile

# R04（WSL root，干净 clone，固定 HEAD）
bash deploy/check_acceptance.sh

# F 组（WSL root，自建实验室；逐变体）
python3 -m deploy.acceptance.issue134.f01 --variant A   # f02/f03/f04/f07 同
```

## 接手材料与交接信息 (Handoff)

- 最终结论：`docs/acceptance/e2e-final-report-20261023.md`（分支 `codex/e2e-acceptance-20261023` 提交 `41d5019`）。
- 回执 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `e2e-final-report-20261023.md` | `029155FF301B65C287D691E9CDE70DBE316025BBD52855BBAF8C34CE1CD112A3` |
| `e2e-latest-baseline-20261023.md` | `7322B4E760116E839D380DE813112D56D403171DE7B93021B670473DC817DEFE` |
| `e2e-r01-20261023.md` | `F131143BD58BB2372DAD1F822B0F17419DAB4FBD6E60240882524B9C06563076` |
| `e2e-engine-suite-20261023.md` | `A2DFF9AC97B8E9648C7CA31D7AF4F3851AA8A49D7B236C735CC88A6AC7C5DA6D` |
| `e2e-web-shell-20261023.md` | `408509186C0D7D92C3975991F020C93B4203E1B35AE4C846E5D744578546CA2B` |
| `e2e-deploy-20261023.md` | `3708243BF09F17C5D8C668244764732DAC85B3FD276E464CDBAFCED1096EF2EC` |
| `e2e-faults-20261023.md` | `BAAA614D0CAF26B66B8826DAFEF512F35E82930601DCAFA754B5B562816FA2D8` |
| `e2e-mobile-h-20261023.md` | `849ADC382D0DCFA84A9E8AA7CE4B9788CBEA3AFF702D04194E986059D2ED1508` |
| `e2e-apk-build-20261023.md` | `3A38D2E9C7ABD3732A5004C4263083B3C9685355165670275AEEB216A2EAEB4E` |
| `e2e-baseline-impact-20261023.md` | `D019D48A7E004B756D00C0B13B4DF53F8648410D61CF46EBF7168E7A8AAEFE87` |

- 原始证据：`tmp/e2e/20261023/`（r01/web/web-b/spec30-run3/pt907/deploy/faults/h/apk；`tmp/` 不入 Git）。
- 分支为本地提交、**未 push**；如需让收据进入仓库，请授权提交 PR（不自动合并）。

## 需用户决定

1. 是否接受本轮“未全部通过”的结论与缺口清单；
2. H/N 全矩阵是否另开补跑窗口（预计 1–2 个工作日）；
3. `acceptance:mobile` 选择器与 CI 覆盖缺口是否授权修复（仅测试/CI）；
4. H12 旧组合 FAILED 与 H01 本轮缺原句区间是否单开缺陷票；
5. #256 回退的 deck/视频/AI/第三方披露材料是否恢复；
6. 是否授权 push 分支并发起收据 PR（合并需另行授权）。

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
