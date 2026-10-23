# PrivacyTrace · 作品评审片（专家版）· BEATS

> 目标：120.000 秒、1920×1080、30 fps、H.264/AAC、原创配乐、无旁白。
> 面向专家评审，按「定位 / 创新 / 关键实现 / 真实成果 / 学生原创贡献」五段组织。
> 本文件是制作分镜与事实绑定表，不是对外提交声明。成片与源文件见 `delivery/`。
> 状态：v0.2 成片已重渲并通过 EAC 技术质检（`qa.ok=true`、`deterministic=true`、无缺失素材）；采集批次 `20261023-v02`，冻结基线 `f81ca201b932a11e24a9f7175a9583150d44e9ed`；媒体实测与哈希见 `delivery/manifest.json`。

## 音乐与切点

- 音乐：沿用本项目原创器乐 `assets/soundtrack.m4a`（SHA-256 `FB7E005F…54A30C`，96 BPM，48 小节 × 2.5 s = 120.000 s，48 kHz 立体声，无采样、无人声）。
- 结构：0–9 s 引子；9–65 s 正常密度；66–89 s 降密度阅读段；89–113 s 恢复；113–120 s 尾奏。
- 所有主切点落在 96 BPM 的整小节网格（0.625 s 拍、2.5 s 小节）上：

| 段落 | 起 | 止 | 小节 | 评审要素 |
| --- | ---: | ---: | ---: | --- |
| 00 冷开场 | 0.000 | 9.375 | 0–3.75 | 钩子 / 片名 |
| 01 定位 | 9.375 | 21.875 | 3.75–8.75 | 它是什么、明确不是什么 |
| 02 创新 | 21.875 | 40.625 | 8.75–16.25 | 证据链的形状 |
| 03 关键实现 | 40.625 | 65.000 | 16.25–26 | 一条流水线、同一证据链 |
| 04 真实成果 | 65.000 | 90.000 | 26–36 | 四类数字分开报 |
| 05 学生原创贡献 | 90.000 | 108.750 | 36–43.5 | 团队提出 / AI 辅助 / 提交绑定 |
| 06 结语 | 108.750 | 120.000 | 43.5–48 | 证据先于结论 |

## 分镜

| # | 时间 | 画面 | 屏上文字（要点） | 事实 / 来源 |
| --- | --- | --- | --- | --- |
| 00a | 0.9–4.9 | 暗场；左侧三句，右侧代码/政策细线列，中间证据线 | 权限说它能做什么。代码说它可能怎么做。政策说它承诺了什么。 | 定位边界：权限=能力、invoke=静态线索 |
| 00b | 5.25–6.55 | 三句压暗，问题居中 | 把两边摆到一起，才有对照。 | — |
| 00c | 6.8–9.375 | 片名卡 | PrivacyTrace / Android APK 静态隐私线索 × 政策原文 / 作品评审 · 专家版 · 120 秒 | — |
| 01 | 9.375–21.875 | Android App 开发版窗口 + 三条要点 + 纸卡「它说越权」 | 读取静态线索，对齐政策原文。越权，就是越权。 | `docs/project-introduction-draft.md#L31-L59`；`GLOSSARY.md` |
| 02a | 21.875–29.0 | 证据解剖纸卡：代码位置 ↔ 政策原句 | ① 代码位置 ② 政策原句；[0,18)；按 Unicode 码点、半开区间 | `samples/demo/evaluation-input.json`（人工构造示例）；`docs/stages/s0-report.md#L10-L11` |
| 02b | 29.5–38.5 | 三张原则卡 | 一条证据两个终点；事实/声明/推断分层；12 场景三方案同材料 | `GLOSSARY.md`；`benchmarks/controlled-v2/README.md`；`docs/stages/issue64/README.md` |
| 02c | 33.95–40.35 | 大号总结句 | 代码位置、原文区间、材料来源，都留在同一份报告里。 | 同上 |
| 03a | 40.625–44.2 | 五节点流水线 | APK+政策材料 → 隔离扫描 → 证据+候选 → 一致性对照 → 报告/回放 | `README.md#L99-L103` |
| 03b | 44.4–62.5 | 四页实现细节 + 报告窗口滚动 | 非 root 65534、network none、只读根、cap-drop ALL、1 CPU/1 GiB/PID 32；Androguard 4.1.3；[start,end) 切片==excerpt、快照不覆盖；FastAPI/Pydantic、PostgreSQL outbox、Redis/Celery、mTLS Runner | `docs/stages/s1-pr29-real-sample-verification-20261009.md#L25`；`README.md#L90-L92`；`docs/stages/s0-report.md#L10-L11` |
| 03c | 59.35–65.0 | Android App 报告窗口滚动 | 开发版 Android App（移动壳） | 移动视口模拟截图（Chromium 390×844，非真机）；2026-10-23 @ f81ca20 |
| 03b-label | 44.0–65.0 | 报告窗口标签 | 报告 · 持久化回放 · 真实 APK（S1 夹具）· **2026-10-23 @ f81ca20** | `fixtures/acceptance-jobs/gkd-s1-first.json`（REAL_SCAN · PERSISTED_REPLAY，原生成 2026-10-03）；不当作 2026-10-23 新扫描 |
| 04a | 65.9 | 工程门禁卡 | 1578 passed / 179 skipped；e2e 65；Web 111；生产构建通过 | `65b49f7`，2026-10-21，`docs/acceptance/issue136/execution-20261022.md` |
| 04b | 68.9 | 部署验收卡 | 40 pass / 0 fail / 0 skip；四入口 4/4；唯一既有豁免 `dedicated-scan-host-verification`（用户授权） | `65b49f7`；`deployment-summary.json` |
| 04c | 71.9 | 受控评测卡 | 12/12 · 4/12 · 2/12（状态一致）；36 行；执行失败 0 | `b0b3c74`；`docs/stages/issue64/README.md` |
| 04d | 74.9 | H 矩阵 + GKD 卡 | 11 通过 / 1 未通过；H12（J × splits × 手机模型）失败复现 2 次；GKD v1.12.1（仅 1 个历史样本）：6 证据 / 3 行为 / 2 声明 / 3 问题，3 条结论均 `INSUFFICIENT_EVIDENCE` | `2626152`；`docs/acceptance/h-matrix-final-20261022.md`；`s1-pr29…` |
| 04e | 80.0–86 | 三级阶梯 + 结论 | 工程测试 → 受控评测 → 真实 App；证据不足，也要写进报告。 | `README.md#L129-L132`；`benchmarks/controlled-v2/README.md#L32` |
| 05a | 90.0–99.3 | 团队原创卡 + AI 披露卡 | 团队提出并执行：定位/证据模型/规则归因/受控基准/验收治理；AI：脚手架、测试、文档文案；工具、用途与人工修改记录保留在仓库 | `docs/submission/07-ai-usage-disclosure.md#L45-L53`；`docs/ai-usage-disclosure.md#L46-L49` |
| 05b | 99.3–108.75 | 提交绑定账本 + 保留项 | 65b49f7 / 323780c9 / b0b3c74 / 9e56771 / 2626152；H12 失败保留；提交头以维护者冻结为准 | 同各段；`docs/acceptance/issue136/final-package-20261022.md` |
| 06 | 108.75–120 | 结语卡 | 越权，就是越权。权限声明 / 代码线索 / 政策原句。 | 定位边界；交付边界 |

## 素材与可复核性

| 素材 | 来源 | 采集/绑定 | 约束 |
| --- | --- | --- | --- |
| `assets/android-import.png` | 本批次 `showcase/materials-20261023-v02/capture-android-flow.cjs`（`127.0.0.1:6173`） | 2026-10-23 @ `f81ca20` | 开发版；固定演示数据；不当作最终视觉 |
| `assets/android-report-full.png` | 同上脚本；`job:gkd-s1-first` 持久化回放全页（1440×2978） | 2026-10-23 @ `f81ca20` | `fixtures/acceptance-jobs/gkd-s1-first.json`（REAL_SCAN · PERSISTED_REPLAY，原生成 2026-10-03）；不当作 2026-10-23 新扫描 |
| `assets/android-evidence-full.png` | `showcase/materials-20261023-v02/capture-android-flow.cjs`；生产 `MobileApp.vue` + 假原生桥，390 CSS px 移动视口 | 2026-10-23 @ `f81ca20` | 移动视口模拟（非真机）；同一 `gkd-s1-first` 回放数据； |
| `assets/soundtrack.m4a` | `showcase/privacytrace/assets/soundtrack.m4a` | 原项目原创配乐 | 96 BPM；无采样、无人声；许可见原项目 |

## 已知限制（必须随片保留）

- H12（J × splits × 手机模型）失败，复现 2 次；片内保留，不剪成 12/12。
- 受控场景是自建源码场景的**名义状态对照**，。
- 真实 App 仅 1 个历史样本（GKD v1.12.1），三条结果均为 `INSUFFICIENT_EVIDENCE`。
- 界面截图统一标注「开发版 · 2026-10-23 @ f81ca20」，。
- Android App 画面是 Chromium 390×844 视口模拟（生产移动壳 + 假原生桥），不是 Android 真机；ADR-0004 的真客户端是 Android App。
- 提交头以维护者冻结为准；本片不写「当前版本」，每个数字绑定各自提交。
- AI 用途与受影响文件记录在仓库。
- 不宣称开源；项目源码许可证仍待团队最终决定。
