# 最新基线全流程端到端验收（2026-10-23）

状态：**已收口（2026-10-23T03:15Z）**。本文件是本次验收的协调入口与 lane 索引；判定以各 lane 回执与 [最终结论](e2e-final-report-20261023.md) 为准。结论为**未全部通过**：R01/R02/R04 PASSED、R03 一项 FAILED（测试漂移）、F 17/17 执行变体 PASSED 但 F07-E/F08–F10 未完成、H 仅客户端冒烟 PASSED 且 H01 FAILED（缺原句区间）、H/N 其余 NOT_RUN。

## 1. 基线与组合

| 项 | 值 |
| --- | --- |
| 基线（被测源码） | **`origin/main` = `83a7983ee6e9bd580dfe41623e06f83c435b9d34`**（`2026-10-23T00:20Z` 锁定；tree 以 `git rev-parse HEAD^{tree}` 回读） |
| 基线漂移 | 组织时首次锁定 `a1a6386`（`00:10Z`），执行中远端前进到 `83a7983`：28 个文件，产品行为差异仅 `scripts/export-schema.py` / `export-offline.py` 的说明文字与 `package.json`/`Cargo.toml` 的 MIT 许可字段，其余为提交材料文档、LICENSE、README。重跑以 `83a7983` 为准；`a1a6386` 的首跑只作漂移对照，不单独构成结论 |
| 工作分支 / worktree | `codex/e2e-acceptance-20261023` / `.agents/worktrees/codex/e2e-acceptance-20261023` |
| 上一轮已接受组合 | `deccced59d6dec7f442be4ce06b257403794bc46`（#128 于 2026-10-22 收口，接受 7 项缺口） |
| 截止 / 冻结 | 2026-10-23 22:00 北京时间；18:00 冻结功能修改（本轮不修改产品代码） |

与上次组合的关系：`2626152 → deccced` 之间的 #171/#174 已在上一轮记录；`deccced → a1a6386` 之间又合入产品代码变更（#176/#178/#185/#188/#206/#210–#217/#227/#229/#231/#232/#235/#242/#244/#245/#250–#255），以及 #256 对 #228/#234/#236/#237 的 revert（提交材料文档回退，不是产品代码回退）。**上一轮 H/N/F/R 收据不自动适用于本基线**；能否引用旧收据必须按 [基线影响分析](e2e-baseline-impact-20261023.md) 逐项说明，不能把旧 SHA 的绿灯改写成新基线的通过。

判据沿用 [提交前最终端到端测试方案](../pre-submission-e2e-plan-20261021.md)：H 12/12、N 12/12、F 10/10、R01–R04；状态只用 `PASSED` / `FAILED` / `BLOCKED` / `NOT_RUN`。豁免、跳过和未执行单列，绝不计入 `PASSED`。缺陷只登记不修复（本轮未获修复授权）；阻断项留给用户决定。

## 2. 车道与分工

| Lane | 覆盖 | 入口 | 回执（提交） | 原始证据（不进 Git） |
| --- | --- | --- | --- | --- |
| R01（Lead） | 权威入口 + Docker 分支 | `PRIVACYTRACE_DOCKER_TESTS=1 bash scripts/check.sh` | `docs/acceptance/e2e-r01-20261023.md` | `tmp/e2e/20261023/r01/` |
| R03（web-shell） | Browser / frontend / live / mobile / reading / motion / hierarchy / preview / 设计合同 / 品牌资产 | 见 `package.json` 的 `acceptance:*` 与 `scripts/verify-*.cjs` | `docs/acceptance/e2e-web-shell-20261023.md` | `tmp/e2e/20261023/web/` |
| R02（engine-suite） | Spec30 六场景 + pt907 十二场景（源码重复构建、隔离扫描、CLI/HTTP、浏览器、独立断网回放） | `scripts/validate-spec30.py --suite spec30/pt907` | `docs/acceptance/e2e-engine-suite-20261023.md` | `tmp/e2e/20261023/spec30/`、`tmp/e2e/20261023/pt907/` |
| R04（deploy-gate） | 部署专项 R1–R6（源码/镜像/迁移/协议/豁免） | WSL root：`bash deploy/check_acceptance.sh`（干净 clone） | `docs/acceptance/e2e-deploy-20261023.md` | `tmp/e2e/20261023/deploy/` |
| F（fault-lane） | F01–F04、F07 变体；F08–F10 按现有 drill 能力评估 | WSL root：`python3 -m deploy.acceptance.issue134.f01 …` 等 | `docs/acceptance/e2e-faults-20261023.md` | `tmp/e2e/20261023/faults/` |
| H/N 手机客户端 | 真实 APK 的 H/N 组合 | 需要本基线 APK；见第 4 节 | 视 toolchain 子代理结果另开回执 | `tmp/e2e/20261023/apk/` |
| 基线影响分析（子代理） | `2626152/deccced → a1a6386` 变更对旧证据适用性的逐项判定 | 只读 `git diff` + 既有收据 | `docs/acceptance/e2e-baseline-impact-20261023.md` | — |

## 3. 环境事实（2026-10-23 实测，不作推测）

- 宿主：Windows，20 逻辑核 / 31.6 GB RAM；Git Bash 5.3.15；Node `v24.17.0`；npm `11.13.0`；uv `0.11.23`；Python 3.14.6。
- Docker：Windows 无 `docker` CLI；WSL `Ubuntu-24.04` 内 Docker `29.7.2` 可用，`isolated_scan.docker_prefix()` 走 `wsl.exe -d Ubuntu-24.04 --exec docker` 回退。
- 设备：MuMu Player 12，VM 2–5 可用（VM 0 为他人日常实例，禁止触碰）；`adb` 在 `D:\Games\MuMu Player 12\shell\adb.exe`（或 `nx_main\adb.exe`）。
- **客户端 APK 构建链（执行中已恢复）**：组织时 Windows 无 JDK、无 Android SDK、无 Rust/cargo（`~/.rustup` 存在但 `~/.cargo/bin/cargo.exe` 不存在）。本轮子代理恢复了工具链（JDK 17 在 `C:\Users\Oasis\.jdks\jdk-17.0.20.1+1`、SDK 在 `D:\Tools\android-sdk`（platform 36 / build-tools 36.0.0 / NDK 27.3）、Rust 1.99.1 + `x86_64-linux-android`、MinGW-w64 作为 host linker 替代），并在 `83a7983` 上构建出可安装 APK（`CD33C6EC…345A`，含 #73 测试 CA 的 debug overlay）。`apps/mobile/src-tauri/src` 原生壳在 `2626152..83a7983` 之间无差异，APK 差异来自 web 资源。旧 APK `955d484b…6088` 仍只能作为混合组合的历史客户端。
- 旧承载体：上一轮实验室、镜像与私有证据位于 `.scratch/`；本轮不复用其结果，除非按基线影响分析逐项说明适用性。
- **本轮执行前环境修复（2026-10-23，非产品代码）**：WSL Docker 的 `daemon.json` 曾把代理指向 `127.0.0.1:7897`（WSL NAT 内不可达），`/root/.docker/config.json` 与 `/home/oasis/.docker/config.json` 又分别指向不可达的 `10.155.217.182:7898`、`172.20.10.3:7898`；Docker CLI 会把后者注入 build/run，导致所有容器内 `uv sync` 下载超时。修复：`daemon.json` 去除代理并设 `mtu: 1280`（WSL eth0 MTU=1280），两个 CLI 配置备份为 `*.bak-20261023T003347Z` 后置 `{}`，重启 dockerd；同时把 `iptables -P FORWARD` 恢复 `ACCEPT`（`docs/agents/local-environment.md` §4 记录的已知环境假失败）。修复后实测容器 egress 可用（root/oasis 两种 CLI）。修复前 `a1a6386` 上的 R01/R02/R04/F 首跑失败均为该环境问题，证据保留但不计产品结果。

## 4. 放行与缺口规则

1. 只有同一基线上的实际执行证据才能写 `PASSED`；跨基线引用必须注明源 SHA 与适用范围。
2. 任何 lane 失败或阻塞，保留首个可复现证据，不通过重试/放宽断言/跳过隐藏。
3. 客户端面（本基线 APK）无法重建时，H/N 的客户端结论记 `BLOCKED`，不得用 web-shell 或旧 APK 冒充；已执行的服务端/Web 证据照常记录，但组合名称必须写清。
4. 18:00 后只做读回、汇总与缺口登记，不再启动新的重型执行；未完成项按 `NOT_RUN`/`BLOCKED` 报告给用户，由用户决定交付范围。
5. 本轮不合并、不部署、不改 Issue 状态；回执提交只在本分支。

## 5. 收口清单（执行完成后回填）

- [x] R01：**PASSED**（`83a7983`，1684 passed / 183 skipped / 65 e2e passed；回执 `e2e-r01-20261023.md`）
- [x] R02：**PASSED**（spec30 6/6 + pt907 12/12，WSL Linux CI 等价；回执 `e2e-engine-suite-20261023.md`）
- [x] R03：**12/13 PASSED，1 FAILED**（`acceptance:mobile` 为 harness 文案漂移，非产品行为；回执 `e2e-web-shell-20261023.md`）
- [x] R04：**PASSED**（R1–R6 = 40 PASS / 0 FAIL / 0 skip / 0 untested，1 项既有豁免；回执 `e2e-deploy-20261023.md`）
- [x] F 组：**17/17 执行变体 PASSED**（F01 A–C / F02 A–D / F03 A–D / F04 A/B / F07 A–D），F07-E **BLOCKED**（无独立可销毁内核 VM），F08–F10 **NOT_RUN**（需 `check_acceptance.sh` 两实验室 harness；F10 另缺上一基线 API 镜像）。按 F01–F10 十项口径未满足 10/10。回执 `e2e-faults-20261023.md`
- [x] H/N 手机客户端组合：客户端安装/启动冒烟 **PASSED**；**H01 FAILED**（报告缺政策原句区间，`policy_comparison=UNKNOWN`；根因未定位到产品缺陷）；H04/H07/H10 **NOT_RUN**；N01–N12 **NOT_RUN**（旧收据不适用于本基线）。回执 `e2e-mobile-h-20261023.md`
- [x] 基线影响分析（`e2e-baseline-impact-20261023.md`：must-rerun 37 项，旧 PASSED 折算本基线 = 0）
- [x] 最终结论：**未全部通过**，缺口与需用户决定项见 `e2e-final-report-20261023.md`

## 6. 本轮新增的验收发现（非产品代码修改）

1. **`android:prepare` 模板漂移（仓库侧 GAP）**：CLI 2.12.3 生成的 Android 工程没有 `mipmap-anydpi-v26/ic_launcher.xml`，`apply-brand-android-icons` 失败；本次 APK 使用 Tauri 默认图标，品牌图标未生效（不影响功能，影响交付观感）。
2. **`acceptance:mobile` 脚本与产品文案漂移**：3 个标签、9 处选择器仍找旧文案，导致 4 个场景 30s 超时；补充复跑（仅 `tmp/` 副本改选择器）显示 #239 可过、其余仍卡在其余旧文案。官方入口记 FAILED，不修改仓库测试脚本。
3. **CI 门禁覆盖缺口**：`browser-acceptance.yml` 未包含 `acceptance:mobile`、`verify-frontend-round2`、`verify-issue145-a11y`、`verify-round2-primitives`、`verify-brand-assets`，漂移长期未被发现。
4. **`verify-offline.py` 的 Windows 前提**：要求 `browser_runtime.startswith("/")`，Windows 上 `executablePath()` 为 `C:\...`，导致 spec30 的独立断网回调无法在 Windows 宿主收 PASSED；WSL Linux 权威跑已通过。这是工具可移植性缺陷，不是产品缺陷。
5. **#256 revert 的交付材料缺口**：回退了 6 个 PR 的材料（deck、90s 视频、AI/第三方披露、PT-906 阶段材料），`apps/` 仅 3 文件 6 行文案/注释/测试改动；材料是否需要恢复由用户决定，不属于本 E2E 门禁。
