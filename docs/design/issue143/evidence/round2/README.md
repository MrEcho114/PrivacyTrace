# Issue #143 第二轮宽屏证据（1920×1080 / 1440×900 / 1280×720）

- 采集代码：`scripts/verify-issue143-hierarchy.cjs`
- 采集命令：`node scripts/verify-issue143-hierarchy.cjs`
- 采集环境：Windows 宿主，Playwright 自带 headless Chromium；`npm run dev`（Vite，`PRIVACYTRACE_WEB_PORT=5189`）
- 采集树：`codex/issue143-round2` @ `ddb458843f606369484e167a0ef7d40a9294d22d`，`git status --porcelain` 为空
- 采集时间：2026-10-21T13:07:46Z（Asia/Shanghai 2026-10-21 21:07）
- 机器回执：`verification.json`（同一脚本写出，含 10 组断言、视口清单、截图清单、`errors: []`）

## 场景与数据来源

每个场景各 3 张：`<场景>-1920.png`、`<场景>-1440.png`、`<场景>-1280.png`。

| 场景 | 页面状态 | 数据来源标注 |
| --- | --- | --- |
| `example-import` | 示例流程第 1 步：导入材料，含超长 APK 名、两份政策来源、完整度/未复核/附件脚注 | 浏览器内示例流程，SYNTHETIC 固定示例材料；未接真实 APK |
| `example-candidates` | 示例流程第 2 步：一条来源上下文 + 政策原文与候选双栏、编辑表单 | 同上 |
| `example-progress` | 示例流程第 3 步：阶段轨 + 当前阶段卡（离散「阶段 1 / 5」） | 同上 |
| `example-report` | 示例流程第 4 步：来源摘要一行、证据对照表、线索下钻 | 同上 |
| `reports` | 「已有报告」查看器：长包名/长网址/哈希、身份先于元数据、三项指标、紧凑成功任务行 | mock：确定性 persisted report / taxonomy / jobs fixture，非真实 APK |
| `reports-evidence` | 同上，展开某项证据后的证据面板（截图聚焦 `#evidence-panel`） | 同上 |
| `live-progress` | 真实 `LiveWorkflow` 进度模板：页标题 → 材料版本 → 状态摘要 → 事件时间线 → 取消/重读 | mock：只读 draft + 运行中 job 路由，未执行扫描或模型 |
| `live-report` | 真实 live 流程完成后的「对照报告」步：页标题 + 材料版本入口 + 已保存报告 | mock：draft/job/report fixture |
| `offline-reports` | 注入 `presentation=offline` 的只读回放包：无工作台外壳，保留来源选择与持久化回放徽标 | mock：saved report fixture，离线回放包 |

## 边界

- 以上均为浏览器模拟截图：没有真实 APK、Docker 扫描、真实模型、Android 真机/模拟器或系统读屏参与。
- `reports*`、`live-*`、`offline-reports` 使用脚本内的确定性 mock fixture；`example-*` 使用页面内置的固定示例材料。
- 这些图证明 1920/1440/1280 的布局、层级与 36px 桌面操作契约，不证明隐私结论或政策核验状态。

## 与第一轮证据的关系

`../before-*`、`../after-*` 采集于第一轮基线 `83f42ea`，早于 `#150` 的 Pioneer 主题统一（`76b9f4d`），只作「层级意图」的历史对照；当前树的视觉证据是本目录。
