# #128 / #136：H01–H12 在最终交付组合上的复跑收据（2026-10-22）

Refs #128、#136、#129、#130、#131、#173。本记录是 H01–H12 十二个成功组合在**最终交付组合**上的重跑结果（旧证据在 ffadeb0 组合，不能直接相加），使用真实 Android 客户端、两套独立本机实例、受控政策源与受控模型接收器、真实 PostgreSQL/outbox/Redis/Celery 与受限 Docker Runner。它不是父票最终放行结论。

## 1. 必测组合与身份

| 项 | 值 |
| --- | --- |
| 交付 head | `262615242161e0371ec151a5f07ef19d360a35e3`（Merge PR #173），tree `1a662a23eb9eea57135391f3f2d63ca73456fc16` |
| 客户端 APK | `client-local-ca-2626152.apk`，sha256 `955d484ba0a01bcf0472e7d97b24fe0d84698af8c61b0efe38b762ca7d3e6088`，0.1.0（1000），`x86_64`，debug 签名证书 `4172668f…`，仅对 `localhost` 追加 #73 测试 CA |
| 设备 | MuMu VM index 2，`127.0.0.1:16448`，Android 15 / API35 / `x86_64`，竖屏 `1080×1920` |
| 标准配置实例 I（旧 state，H01/H02/H04/H05 运行时） | `pt81-b4de8c2e1ef6`，实例 `36e82feb-8eeb-4625-9244-1d78f18702a5`，port 28450；镜像 api `ebde04d2…` / web `d30e3fde…` / runner `35c31024…` / scanner `b19fe5fa…`（VCS_REF=2626152） |
| 标准配置实例 I（新 state，H03/H06） | `pt81-552a0a7ecdfd`，实例 `d4dc77ca-471e-40d8-9c1c-154be226335c`，port 28450；镜像 api `b9c3a009…` / web `38f349d6…` / runner `56cfdc06…` / scanner `64ca44df…` |
| 自托管实例 J（H07–H12） | `pt81-bf2d8a73d7bd`，实例 `61c54331-0003-449d-abea-fefea8eed965`，port 28451；镜像与 I（新 state）同组 |
| 客户端 origin | 固定 `https://localhost:28443`（跑 J 用例时把 `adb reverse tcp:28443` 切到 28451） |

**为什么有两个 I state：** 17:0x 共享镜像 tag `privacytrace-*:issue81-test` 被恢复 F 票实验室的重建操作 re-tag，旧 state 记录的部分镜像 ID 被回收；H 组改用私有 tag `privacytrace-*:hmatrix-2626152` 重建同一棵最终树，并把 I 重新 provision 成新 state。前四个用例（H01/H02/H04/H05）保留运行时记录的旧 state/镜像 ID，结论不变；两组镜像都构建自同一交付 tree。

## 2. 用例矩阵与结果

**组合时间线（必须与结果一起读）：** 本记录的全部客户端/服务端证据产生于 `2626152` 树与由该树构建的 APK（`955d484b`）。此后 `main` 前进到 `392555f`，包含 **#171（设计基座/品牌图标/文案合同，改动 web 产品 UI 与静态资产）** 与 **#174（R4 注入前等待就绪基线，仅改 `deploy/acceptance/r4_fault_recovery.py` 与其测试）**。#171 会改变新 APK 内的 web 资产，本轮**没有**在 #171 之后重建 APK 复验客户端面；#174 不影响本记录的用例。父票放行时应把「#171 之后的客户端面未复验」当作明确缺口，而不是把本记录当作 `392555f` 的客户端证据。

| 组合 | 输入 | 模式 | 结果 | 关键观测 | 证据（受限保存） |
| --- | --- | --- | --- | --- | --- |
| H01 | 单包 / I | 自动政策 | **PASSED** | job SUCCEEDED、对照 PRESENT、证据 2、原文位置 `[25, 34)`、扫描行 `已扫描 base:classes.dex…` | `I/H01-local-I-single-auto-result.json`、`H01-cleanup.json` |
| H02 | 单包 / I | 网页辅助 | **PASSED** | 同上；辅助正文导入、候选页面、非空对照 | `I/H02-local-I-single-assist-result.json`、`H02-cleanup.json` |
| H03 | 单包 / I | 手机模型 | **PASSED** | 模型来源标题/原句/`[25, 34)` 出现在报告；静态 assist 标题不出现；证据面板 1 | `I/H03-model-assertion.json`、`H03-cleanup.json` |
| H04 | splits / I | 自动政策 | **PASSED** | 2 数据类型、split 扫描行、证据 3、原文位置 `[25, 34)` | `I/H04-local-I-splits-auto-result.json`、`H04-cleanup.json` |
| H05 | splits / I | 网页辅助 | **PASSED** | 精确位置 + 通讯录、`split:fixture_feature:classes2.dex … caller=ProbeBehaviorFeature`、原文位置 `[34, 42)` | `I/H05-local-I-splits-assist-result.json`、`H05-cleanup.json` |
| H06 | splits / I | 手机模型 | **PASSED** | 模型原句与区间、split 扫描行；静态 assist 标题不出现 | `I/H06-model-assertion.json`、`H06-cleanup.json` |
| H07 | 单包 / J | 自动政策 | **PASSED** | 受控政策源 `http://1.0.0.1/policy.html` 抓取 200/147B/sha `f08b0f7f…`；对照 PRESENT、证据 2 | `J/H07-local-J-single-auto-result.json`、`H07-cleanup.json` |
| H08 | 单包 / J | 网页辅助 | **PASSED** | 对照 PRESENT、证据 2、原文位置 `[25, 34)` | `J/H08-local-J-single-assist-result.json`、`H08-cleanup.json` |
| H09 | 单包 / J | 手机模型 | **PASSED** | 由运行期捕获证据派生的补充断言：模型标题/原句/`[25, 34)`/声明来源 `web-policy-model-controlled`/无静态 assist 标题/base 扫描行 | `J/H09-model-assertion.json`、`J/H09-local-J-single-model-evidence*.txt` |
| H10 | splits / J | 自动政策 | **PASSED** | 3 证据、split 扫描行、对照 PRESENT | `J/H10-local-J-splits-auto-result.json`、`H10-cleanup.json` |
| H11 | splits / J | 网页辅助 | **PASSED** | 2 数据类型、3 证据、原文位置 `[34, 42)` | `J/H11-local-J-splits-assist-result.json`、`H11-cleanup.json` |
| H12 | splits / J | 手机模型 | **FAILED**（复现 2 次） | job SUCCEEDED、对照 PRESENT、`已扫描 base:classes.dex、split:fixture_feature:classes.dex`、模型来源标题出现；但报告与证据面板**均缺少模型原句与 `[25, 34)` 下钻**（`model_quote_in_report=false`、`quote_offsets_present=false`，证据面板仅权限项） | `J/H12-local-J-splits-model-*`、`J/H12b-local-J-splits-model-*`、`J/H12-model-assertion.json`、`J/H12b-model-assertion.json`、`J/logs/H12*.log` |

**方法说明（必须与结果一起读）：**
- 每个用例通过真实客户端完成「选应用 → 确认上传（单包或完整已安装 splits）→ 政策（自动发现/受控网页辅助/手机模型）→ 候选 → 分析 → 报告 → 原生两步删除」。
- 自动政策用例通过受控政策源 + Docker 网桥 DNAT 让 API 容器真实抓取受控正文，并走产品既有服务端抽取路径，抽取端点是容器内回环的 OpenAI 兼容受控 mock（记录请求日志与正文哈希），**不代表外部模型质量**。
- 模型用例通过一次性 Key 的受控 HTTPS 接收器（证书由客户端信任的同一测试 CA 签发），Key 只写入本机原生配置，不进公开证据。
- **执行器缺口（如实记录，不据此减分也不据此升级）**：`client-case.cjs` 的 `removeDraft()` 在 #160 后找不到已移入「服务与存储设置」sheet 的删除入口，因此 `result.json` 的 `deletion` 为 `SKIPPED`；每个用例的删除由独立 helper 只驱动产品 UI 完成并单独落 `Hxx-cleanup.json`（含「服务器已确认删除」原文、删除前报告 SHA 与删除后回读）。同理，执行器的 model 断言在展开证据面板之前取样，H03/H06 首跑 `exit 1` 日志保留，H03/H06 以 `Hxx-model-assertion.json` 为准，H09 以由运行期捕获文本派生的补充断言为准。
- 清理：H01–H11 均有独立 cleanup 回执；H12 未产生业务任务（上传阶段失败），随实例销毁；两个 H 实例在收据冻结后由 `provision down --purge` 销毁，设备 `reverse --remove-all`。

## 3. 与旧组合的关系

- H01–H12 的旧通过记录属于 ffadeb0 组合（#129/#130/#131），本记录是最终组合（客户端 `2626152` + 同树服务端）的重跑，不把旧绿灯折算为最终组合通过。
- 唯一未通过的组合是 **H12（J/splits/模型）**：在最终组合上复现两次，报告保留模型来源标题与非空对照、split 扫描行正确，但缺少模型原句与 `[25, 34)` 下钻。
- **可定位的对照事实（供后续排查）**：同为「splits × 手机模型」的 **H06（标准实例 I）通过**，报告含模型原句与区间；H03（I/单包/模型）与 H09（J/单包/模型）也通过（H09 由运行期捕获证据派生断言）。因此 H12 的差异目前只与 **J 实例（自托管配置）× splits × 模型导入**这一组合相关，尚未定位到具体组件；本 PR 不改产品代码，也不把该缺口写成通过。

## 4. 未覆盖边界

- 仅 `x86_64`、MuMu VM / Android 15（API35）竖屏；真机、其它 ABI、API36、商店审核未覆盖。
- 受控政策源、容器内抽取 mock 与一次性 Key 接收器都是本机受控替身：它们验证产品协议与流程，不证明外部政策站点可达性、外部模型质量或公网路径。
- 上传阶段取消/删除、进程回收、跨实例迟到响应等属 #133 的 N12/F05/F06；服务与队列故障属 #134；本记录不重复主张。
- H12 的缺口（见上表）需要独立补跑窗口与可用实例；不因本记录关闭父票 #128。