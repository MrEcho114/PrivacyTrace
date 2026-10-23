# R03 Web/移动壳端到端验收（2026-10-23）

状态：**未通过**。以组合 B（`83a7983`）为结论：13 个官方入口中 **12 个 PASSED、1 个 FAILED**（`acceptance:mobile`，测试脚本文案漂移）；另有一项非官方补充复跑，结论不计入官方状态。

- Lane：R03（web-shell）
- 回执负责人：web-shell（子代理）
- 执行日期：2026-10-23，`08:21`–`08:52`（+08:00）
- 共享 worktree：`.agents/worktrees/codex/e2e-acceptance-20261023`
- 原始证据：`tmp/e2e/20261023/`（`tmp/` 被 `.gitignore` 忽略，未提交）
- 未修改产品代码、未执行 `npm ci`、未 push、未改动仓库内测试脚本。

## 1. 基线与组合

| 组合 | 基线 SHA | 说明 | 执行窗口 |
| --- | --- | --- | --- |
| A（对照） | `a1a6386ab4a18739445b8ffc1025c94e1af5b5d7` | 任务初始基线；只跑了当时已开始的入口 | 08:21:03–08:29:50 |
| **B（结论）** | **`83a7983ee6e9bd580dfe41623e06f83c435b9d34`** | Lead 通知的更新基线（`origin/main`）；全部入口重跑，含 `acceptance:live` | 08:31:39–08:52:02 |

- A/B 之间 28 个文件：MIT 许可元数据、提交材料/披露文档、`scripts/export-*.py` 说明文字、`package.json` 的 `license` 字段；另有 `apps/web/src/App.vue` 的 AI 披露页脚一句话及其单测断言、`contracts.generated.ts` 注释。无被 R03 断言覆盖的行为变更。
- 两组证据分开保存：A 在 `tmp/e2e/20261023/web/`，B 在 `tmp/e2e/20261023/web-b/`；A 的日志未被 B 覆盖。
- 最终结论只引用 B 的实际执行结果；A 仅用于说明失败在两组合上可复现。

环境（实测）：Windows 宿主；Node `v24.17.0`；npm `11.13.0`；Playwright Chromium `156.0.8078.4`（本地 `ms-playwright`）；uv `0.11.23`；WSL `Ubuntu-24.04` 内 Docker `29.7.2`，worker 镜像 `privacytrace-worker:s1` 已存在。依赖为任务开始时已 `npm ci` 的状态，本轮未重装。

## 2. 执行方法与证据纪律

- 所有命令都在 worktree 根目录执行；每个入口由 `tmp/e2e/20261023/web/_run-entry.ps1` 串行启动，完整 `stdout+stderr` 重定向到 `tmp/e2e/20261023/web-b/<entry>/run.log`，并写 `meta.json`（开始/结束时间、耗时、退出码、日志行数、日志 SHA256）。
- 入口独立端口/存储（脚本自身实现，未改代码）：`acceptance:browser` 使用 API `8123` + 每次分配的空闲 Web 端口 + 独立临时 store；`acceptance:live` 使用 API `8134` + 空闲 Web 端口 + `mkdtemp` store；`acceptance:frontend` 的 policy-assist 用系统空闲端口，copy-contract 单独起 dev server；preview 用受管 5184（落在 Windows 保留段时由 OS 分配）。全程未使用 `5173`（该端口的 vite 属其他会话，未触碰）。
- **受保护的已跟踪证据**：`docs/acceptance/issue165/**`（28 个跟踪文件，copy-contract 会写入）与 `evidence/**`（`browser-proof.json` + 10 张截图，browser 入口会写入）。运行前先快照，运行后把本次输出归档到 `web-b/<entry>/artifacts/`，再用快照字节还原；最终 `git status --porcelain docs/acceptance/issue165 evidence` 为空，旧证据未被改写。归档显示本次 copy-contract 重绘了 23 张截图与 `copy-contract.json`（已还原，未提交），仅如实记录该事实。
- 未跳过、未放宽任何断言；失败入口保留首次日志与退出码。

## 3. 八个 `verify-*.cjs` 的独立入口判定

判定依据：`package.json` 的 `acceptance:*`、`scripts/check.sh`、`.github/workflows/browser-acceptance.yml`、脚本自身是否可独立 CLI，以及是否被其他脚本 import/调用。

| 脚本 | 独立 CLI | 被哪个入口覆盖 | 本轮执行方式 |
| --- | --- | --- | --- |
| `verify-design-foundation.cjs` | 无 npm 入口 | `acceptance:design` = `npm run build && node scripts/verify-design-foundation.cjs`；无其他脚本调用 | 随 `acceptance:design` 执行（含构建） |
| `verify-copy-contract.cjs` | 有（但无 npm 脚本名） | `acceptance:frontend` 第 3 阶段；CI 同一入口 | 随 `acceptance:frontend` 执行，不单独跑 |
| `verify-brand-assets.cjs` | `npm run verify:brand`；`scripts/check.sh:61` 接线 | 不在任何 `acceptance:*` 内；R01 会覆盖 | 独立执行（R03 品牌资产范围） |
| `verify-frontend-round2.cjs` | 有（无 npm 入口） | 仅被 `verify-mobile-reading.cjs` 读取 `main()` 之前的 helper 源码，完整矩阵从不被其他入口执行；CI 未运行 | 独立执行 |
| `verify-round2-primitives.cjs` | 有（无 npm 入口） | 无其他入口调用；CI 未运行 | 独立执行 |
| `verify-issue143-hierarchy.cjs` | `acceptance:hierarchy` | 该入口 | 随 `acceptance:hierarchy` 执行 |
| `verify-issue145-a11y.cjs` | 有（无 npm 入口） | 无其他入口调用；CI 未运行 | 独立执行 |
| `verify-issue146-motion.cjs` | `acceptance:motion` | 该入口 | 随 `acceptance:motion` 执行 |

补充事实：`.github/workflows/browser-acceptance.yml` 的步骤只覆盖 `browser/frontend/hierarchy/reading/motion/design/preview/live`，**不运行 `acceptance:mobile`、`verify-frontend-round2`、`verify-issue145-a11y`、`verify-round2-primitives`**；`verify-brand-assets` 只经 `check.sh` 进入 R01。因此 `acceptance:mobile` 的文案漂移不会在浏览器 CI 中暴露。

## 4. 组合 B（`83a7983`）逐入口结果 — 最终结论

| 入口 | 命令 | 耗时 | 退出码 | 通过/失败断言 | 状态 | 首个失败证据 |
| --- | --- | --- | --- | --- | --- | --- |
| round2-primitives | `node scripts/verify-round2-primitives.cjs` | 0.16 s | 0 | 15 / 0 | PASSED | — |
| brand-assets | `node scripts/verify-brand-assets.cjs` | 0.95 s | 0 | 18 / 0（另 1 项 NOT_RUN：Gradle/真机渲染） | PASSED | — |
| **acceptance:mobile** | `npm run acceptance:mobile` | 140 s | **1** | 4 场景失败；0/4 通过；脚本失败时未输出总计数（前序阶段无报错，产出 14 张截图） | **FAILED** | `run.log`：`#239: locator.click: Timeout 30000ms exceeded.`（`scripts/verify-mobile-flow.cjs:245` 点击 `恢复当前实例材料`；产品 `apps/web/src/mobile/MobileApp.vue:275` 已是 `恢复当前材料`） |
| acceptance:reading | `npm run acceptance:reading` | 15.3 s | 0 | 8 / 0 | PASSED | — |
| acceptance:hierarchy | `npm run acceptance:hierarchy` | 11.4 s | 0 | 11 / 0 | PASSED | — |
| acceptance:motion | `npm run acceptance:motion` | 15.1 s | 0 | 20 / 0 | PASSED | — |
| acceptance:frontend | `npm run acceptance:frontend` | 68.8 s | 0 | 三阶段：frontend-flow（103 品牌检查 + 5 输入恢复 + 5 守卫反证 + 15 移动断言 + 17 mock 报告请求，脚本不打印汇总数）、policy-assist 10 / 0、copy-contract 42 / 0（23 图） | PASSED | — |
| acceptance:browser | `npm run acceptance:browser` | 22.8 s | 0 | 6 / 6 测试（TC-01…TC-06），10 张截图；proof 锚定 `83a7983` | PASSED | — |
| acceptance:design | `npm run acceptance:design` | 19.2 s | 0 | 构建通过（`vue-tsc` + `vite build`）+ 158 / 0 检查（28 图） | PASSED | — |
| acceptance:preview | `npm run acceptance:preview` | 14.1 s | 0 | 8 场景 / 0 失败 | PASSED | — |
| standalone-round2 | `node scripts/verify-frontend-round2.cjs` | 25.1 s | 0 | 21 / 0（23 截图 + walkthrough） | PASSED | — |
| standalone-a11y | `node scripts/verify-issue145-a11y.cjs` | 19.7 s | 0 | 14 / 0 | PASSED | — |
| acceptance:live | `npm run acceptance:live` | 24.7 s | 0 | 流程通过；3 来源 / 3 候选；隔离回执 `container_created=true, input_removed=true, cleanup_verified=true` | PASSED | — |

`acceptance:live` 的验证口径：`LOCAL_HTTP_FIXTURES_WITH_TEST_DNS_TARGET` + `CONSTRUCTED_BINARY_APK_ON_ORDINARY_LANE` + `RESTRICTED_DOCKER`（真实 Docker 隔离扫描，非公共网页、非真实模型）。本轮无 `BLOCKED` 项。

### 4.1 组合 A（`a1a6386`）对照

A 上执行了 10 个入口：`round2-primitives`、`brand-assets`、`acceptance:reading/hierarchy/motion/frontend/browser/design/preview` 均 PASSED，`acceptance:mobile` 同样 FAILED（四个 30 s 超时，日志与 B 逐字节相同）。A 未执行 `standalone-round2`、`standalone-a11y`、`acceptance:live`（`NOT_RUN`，由 B 补齐；A 不作为结论）。

## 5. `acceptance:mobile` FAILED 详情（harness 文案漂移）

- 断言/操作基线：`scripts/verify-mobile-flow.cjs` 的 `#239/#243/#248/#249` 四个场景，首步都执行
  `page.getByRole('button', { name: '恢复当前实例材料', exact: true }).click()`（`:245/:263/:313/:345`）。
- 产品现状：`apps/web/src/mobile/MobileApp.vue:275` 已改为 `恢复当前材料`；重命名来自 `767f955 copy(frontend): cut disclaimer and system phrasing`（`git merge-base --is-ancestor 767f955 HEAD` 成立）。选择器 30 s 内匹配不到 → 四场景同时超时，与产品运行时报错无关。
- 失败日志只有 Playwright 首行（脚本在 `:387` 汇总时截断），首个可复现证据：`tmp/e2e/20261023/web-b/acceptance-mobile/run.log` 第 6 行 + 上述源码行。
- 官方结论保持 **FAILED**；未修改仓库脚本，未用补丁结果替换官方状态。

### 5.1 非官方补充证据（不计入 PASSED，未提交）

目的：确认失败是 harness 漂移而非产品行为失败。副本位于 `tmp/e2e/20261023/web-b/mobile-patched/`，与仓库脚本的完整 diff 见 `patch.diff`，改动仅三类：

1. 重定位（副本在 `tmp/` 下，`root` 指向仓库根）；
2. 把 4 处 `恢复当前实例材料` 改为 `恢复当前材料`；
3. 第二次运行前追加“失败选择器 + 页面状态”诊断日志（不改变断言/流程）。

结果：

| 运行 | 结果 |
| --- | --- |
| run-1（重定位 + 文案） | 退出码 1；`#239` 通过；`#243/#248/#249` 仍超时 |
| run-2（加诊断） | 退出码 1；失败选择器为 `设置模型配置`（`#243`）与 `自动准备政策并继续`（`#248/#249`） |

漂移点清单（脚本 → 产品当前文案，共 3 个标签、9 处选择器）：

1. `恢复当前实例材料` ×4（`scripts/verify-mobile-flow.cjs:245/263/313/345`）→ `apps/web/src/mobile/MobileApp.vue:275` 现为 `恢复当前材料`；
2. `设置模型配置` ×1（`scripts/verify-mobile-flow.cjs:266`）→ `MobileApp.vue:310` 现为 `配置模型`/`修改模型`；
3. `自动准备政策并继续` ×4（`scripts/verify-mobile-flow.cjs:272/315/347/361`）→ `apps/web/src/pages/ImportPage.vue:112` 现为 `获取政策并检查候选`。

因此 `acceptance:mobile` 的官方失败属于 **harness drift，不是已证实的产品行为缺陷**；这也意味着该入口当前无法对移动壳行为提供有效门禁，需在有授权的后续变更中同步脚本（本轮未做）。

## 6. 未覆盖边界

- 真实 Android/Tauri/APK/模拟器/WebView、真实系统栏与刘海安全区、真实软键盘 IME、系统字体缩放、TalkBack/VoiceOver/TalkBack 读屏：**NOT_RUN**；`mobile/reading/round2/a11y` 均为 Chromium 模拟 + mock native bridge，不是设备证明。
- `acceptance:mobile` 的官方入口在本基线不可用（harness drift），移动壳的 4 个 issue 回归场景未获得有效官方证据；补充复跑只到“定位失败选择器”为止。
- `acceptance:live` 使用构造 APK、本地 HTTP 政策夹具与测试 DNS，不覆盖公共网页抓取、真实模型与真实 APK；Docker 隔离为真实执行（WSL Docker），但宿主为 Windows/WSL 组合，不等同 CI Ubuntu 宿主。
- 组合 A 未跑 `standalone-round2`、`standalone-a11y`、`acceptance:live`（A 仅对照）。
- `acceptance:design` 会执行 `npm run build`，产物写入被忽略的 `apps/web/dist/`，未提交；本轮不评估构建产物之外的美术质量。脚本验收不等于视觉/审美验收。
- 部分 verification JSON 记录 `dirty: true`：worktree 中存在其他 lane 的未跟踪文档（`docs/acceptance/e2e-*.md`）与 `tmp/` 产物；`git status` 确认无产品代码或已跟踪证据改动。

### 6.1 交付缺口：门禁覆盖（验收发现，本轮未改 CI）

`.github/workflows/browser-acceptance.yml` 的 `acceptance` job 只执行：

```text
npm run acceptance:browser
npm run acceptance:frontend
npm run acceptance:hierarchy
npm run acceptance:reading
npm run acceptance:motion
npm run acceptance:design
npm run acceptance:preview
npm run acceptance:live
```

以下入口没有 `acceptance:*` 脚本或没有 CI 步骤，只能在本地手工执行：

| 入口 | 无 `acceptance:*` 入口 | CI 未执行 | 后果 |
| --- | --- | --- | --- |
| `npm run acceptance:mobile` | 否（有 npm 入口） | **是** | 产品文案改名后脚本选择器未同步，漂移不会被流水线发现（本轮 FAILED 的直接原因） |
| `node scripts/verify-frontend-round2.cjs` | 是 | 是 | 完整移动壳矩阵只被 `verify-mobile-reading.cjs` 当作 helper 源码复用，本轮需手工独立执行 |
| `node scripts/verify-issue145-a11y.cjs` | 是 | 是 | 无障碍回归只在手工执行时生效 |
| `node scripts/verify-round2-primitives.cjs` | 是 | 是 | token/原语静态合同只在手工执行时生效 |
| `node scripts/verify-brand-assets.cjs` | 否（`verify:brand`） | 是（仅 `scripts/check.sh:61` → R01） | 品牌资产依赖 R01 门禁，不在浏览器验收 job 内 |

影响与建议（不改本轮范围）：`acceptance:mobile` 的 harness 已与产品文案脱节，其 FAILED 不能作为移动壳行为结论，同时该入口当前也无法阻止类似回归；建议在有授权的后续变更中同步脚本选择器，并评估把上述独立入口并入同一门禁。**本轮未修改 CI、未修改任何仓库测试脚本。**

## 7. 证据清单（相对 worktree 根，SHA256）

B 组全量清单：`tmp/e2e/20261023/web-b/manifest.json`（339 个文件，46,975,198 字节，SHA256 `aaa58f825ebc7d857e2ccbc4069a709ef6840e50f5e85f5780d9eb6f5df0656e`；manifest 自身不计入清单）。

### 7.1 组合 B（结论）

| 入口 | 日志 | run.log SHA256 | 关键产物 |
| --- | --- | --- | --- |
| round2-primitives | `tmp/e2e/20261023/web-b/round2-primitives/run.log` | `6bd89f8dfb9aceb4a3d00d9f48b8f868e77a8652aaf406a8185ae8be7f0f3e0c` | 终端 15/15（无 JSON） |
| brand-assets | `tmp/e2e/20261023/web-b/brand-assets/run.log` | `3027d5ef9c5f6b8c9cf3f48582e0d75619bf4bb7419f049d1a096fc59ace6e8a` | `.../brand-assets/artifacts/verification.json` `2f9b364adaef846b74777f6977c8be93640d402c246ad081a2dd3e120af6bf48` |
| acceptance:mobile | `tmp/e2e/20261023/web-b/acceptance-mobile/run.log` | `a2f9fba9850dd0299fc157c0bf736bfe518197a5d6804527ec513181cfbea333` | 14 张截图：`.../acceptance-mobile/artifacts/` |
| acceptance:reading | `tmp/e2e/20261023/web-b/acceptance-reading/run.log` | `9523dcafe1c262f8511151b9bfdf4bffa6c68f87211b535c94dd48b38a2a1777` | `.../acceptance-reading/artifacts/verification.json` `518955485fb6d6dd6bd0ee9f3c50cf3050a67ab2f2fe80703892e8fdddc16100` |
| acceptance:hierarchy | `tmp/e2e/20261023/web-b/acceptance-hierarchy/run.log` | `886984bdf7cdf635e606f4f550a8375039ae62bec293c9c77bb5466d659cbc96` | `.../acceptance-hierarchy/artifacts/verification.json` `a2b70e67addf0264b0dffbb5e5261753cc6a9a88a5d0f86cbcc81874d080271a` |
| acceptance:motion | `tmp/e2e/20261023/web-b/acceptance-motion/run.log` | `31ba80ba7f91261a02678d54d84ff0115d5a5b9f479d7aabd9157efbdc562bda` | `.../acceptance-motion/artifacts/verification.json` `71192d5f46e226b2884d462c3b69123ec4f74f1f4cbf6b4c75e5bba56e86154e` |
| acceptance:frontend | `tmp/e2e/20261023/web-b/acceptance-frontend/run.log` | `aa767cd32771a4048daa1cb625f37074f471c6dfb1a40ffcc3abadcb25f58b13` | `.../artifacts/issue165-run/copy-contract.json` `cb2efb55c35f4c94eafbdd449e924116c508a3e5e7b06f73cd7f7780b4dfd588`；另存 `issue44-ui/`、`issue72-policy-assist/` |
| acceptance:browser | `tmp/e2e/20261023/web-b/acceptance-browser/run.log` | `169c2e6044822517231838c9067c68c52bb2cd88231c054074e4082422e8b413` | `.../artifacts/browser-proof.json` `5ed8cbfc08633e0e0c64011bd1a0bda06c8152ede02eeeab5bd88681732f915a` |
| acceptance:design | `tmp/e2e/20261023/web-b/acceptance-design/run.log` | `6339f19900c3d8f5ea63ebc61a9a6e06f13452e409654ca0fe0159ce04cd0a01` | `.../artifacts/verification.json` `af308420a5708f6b5bd3aaf4d8366514632229072a46b1314a9e7b8ea45edae8` |
| acceptance:preview | `tmp/e2e/20261023/web-b/acceptance-preview/run.log` | `577887a8d91ecbde4e05ac2849c2b53160712facfe1c91e50a0357e2bdb868f1` | `.../artifacts/verification.json` `9660182369eced8c527e1f8d54066b79ae8612ce8993261ac0757259a78f2590` |
| standalone-round2 | `tmp/e2e/20261023/web-b/standalone-round2/run.log` | `2815d380f03882b71d1fd108af6bbf26e8673a119cbe50f3c69778e6f4ae303a` | `.../artifacts/mobile-round2-walkthrough.json` `b83a1aaf67cf204b9fba5d7e87536874fafcbddee8550a84f89b782d8b1e2bcb` |
| standalone-a11y | `tmp/e2e/20261023/web-b/standalone-a11y/run.log` | `eae069765d58aa6915c6566430846f2ac66a8c181ae9cc222212fb6e81a774d2` | `.../artifacts/verification.json` `ae2a252a367bd9c7c43ad97b2b8baa406b9eaee11101c11dba17e1eb24e62ef7` |
| acceptance:live | `tmp/e2e/20261023/web-b/acceptance-live/run.log` | `c58bf5999b040124616966884b066df4ba6472d3e619e3161d5e75eff0bf7650` | `.../artifacts/verification.json` `a8d653295b3af6302383004581380435f92b7d92d30b430a4fbbdca378185c25` |
| 非官方 mobile-patched | `tmp/e2e/20261023/web-b/mobile-patched/run.log` | `904ffc07f6a146bf218a3494b369adb246aa22c48439853058383b408158a401` | `run-1.log`、`patch.diff`、`README.md`、`artifacts-issue72-native/` |

### 7.2 组合 A（对照）

日志根目录 `tmp/e2e/20261023/web/<entry>/run.log`：

| 入口 | 退出码 | 耗时 | run.log SHA256 |
| --- | --- | --- | --- |
| round2-primitives | 0 | 0.2 s | `6bd89f8dfb9aceb4a3d00d9f48b8f868e77a8652aaf406a8185ae8be7f0f3e0c` |
| brand-assets | 0 | 1.2 s | `3027d5ef9c5f6b8c9cf3f48582e0d75619bf4bb7419f049d1a096fc59ace6e8a` |
| acceptance:mobile | 1 | 143 s | `a2f9fba9850dd0299fc157c0bf736bfe518197a5d6804527ec513181cfbea333` |
| acceptance:reading | 0 | 14.5 s | `cfe7da98c0cfc6112bc8522870fafd4046d0a5262d956baae93fe01c6b009e87` |
| acceptance:hierarchy | 0 | 22.2 s | `886984bdf7cdf635e606f4f550a8375039ae62bec293c9c77bb5466d659cbc96` |
| acceptance:motion | 0 | 25.1 s | `2adfa6a991e03e28562afd38292bd8984d5e04d007ec498dcdb8fd7f40ca0d0b` |
| acceptance:frontend | 0 | 66.7 s | `aa767cd32771a4048daa1cb625f37074f471c6dfb1a40ffcc3abadcb25f58b13` |
| acceptance:browser | 0 | 21.7 s | `6da42f6f3b803cbf91c766326570fd4bf4ce0d99d2950a7eadb3db760daba9a8` |
| acceptance:design | 0 | 21.0 s | `208e2593fd61e6ff79906a56629e295165468a26230b51d79526d46e13c9f6ee` |
| acceptance:preview | 0 | 14.7 s | `c64e52ef240038b8718ae83709d37182c220ff532b502dad6ddd7985d9ff2384` |

已跟踪证据还原校验：`git status --porcelain docs/acceptance/issue165 evidence` 为空；`git status --porcelain` 仅剩其他 lane 的未跟踪文档。

## 8. 结论与需决策项

1. 组合 B 上 12/13 官方入口 PASSED；唯一 FAILED 为 `acceptance:mobile`，性质是 **测试脚本文案漂移**（3 个标签、9 处选择器与产品当前文案不一致），不是产品行为缺陷的证明；补充复跑仅作判定依据，不构成官方 PASSED。
2. 该入口不在浏览器 CI 中执行，漂移未被流水线发现；修复需要改 `scripts/verify-mobile-flow.cjs`（本轮无授权，未改）。
3. `standalone-round2`、`standalone-a11y`、`round2-primitives`、`brand-assets` 也没有 `acceptance:*` 入口或 CI 步骤；本轮已按独立 CLI 实际执行，门禁覆盖缺口已单列在 6.1，建议后续把它们纳入同一门禁。
4. 未覆盖的设备/真机/IME/读屏与公共网页/真实模型项见第 6 节；不影响“Web/移动壳脚本验收”的已执行结论，但不能当作客户端实机验收。
